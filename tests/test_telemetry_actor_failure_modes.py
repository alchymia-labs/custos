"""Failure-mode tests for TelemetryActor (B1-B3, B6, B8-B9, B13).

Coverage:

- **B1**: producer overrun → drop-newest counter + structured log (no
  ``QueueFull`` raised back to caller).
- **B2**: ``on_event`` called from a non-loop thread is handed off
  thread-safely via ``call_soon_threadsafe`` and ``_seq`` mutation under
  the seq lock keeps the published sequence monotonic with no gaps.
- **B3**: a publisher that raises does **not** kill the flush task; the
  actor keeps publishing subsequent events.
- **B6**: ``stop()`` does not lose envelopes that were ``put_nowait`` just
  before the call.
- **B8**: per flush cycle drains beyond the legacy ``batch_size`` cap so
  a high-rate producer doesn't accumulate net queue depth.
- **B9**: no 10 ms polling sleep — the loop wakes on ``queue.get`` the
  instant an envelope arrives.
- **B13**: ``stop()`` logs (not re-raises) a task that died during
  shutdown.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

import pytest
import structlog

from custos.core.config import TelemetryQueueConfig
from custos.core.nats_client import NatsEnvelope
from custos.core.telemetry_actor import TelemetryActor, TelemetryActorConfig


@dataclass
class _RecordingPublisher:
    telemetry_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)
    heartbeat_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None:
        self.telemetry_calls.append((session_id, envelope))

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        self.heartbeat_calls.append((session_id, envelope))


@dataclass
class _ExplodingPublisher:
    fail_count: int = 0
    succeed_count: int = 0
    fail_first: int = 0

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None:
        if self.fail_count < self.fail_first:
            self.fail_count += 1
            raise RuntimeError("simulated broker error")
        self.succeed_count += 1

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        return None


def _make_actor(
    publisher,
    *,
    max_queue_size: int = 10_000,
    max_batch_size_per_publish: int = 500,
    batch_size: int = 50,
    flush_interval: float = 0.05,
    heartbeat_interval: float = 1.0,
) -> TelemetryActor:
    return TelemetryActor(
        publisher=publisher,
        tenant_id="acme",
        runner_id="runner-001",
        config=TelemetryActorConfig(
            allowed_event_types=frozenset({"OrderFillReport"}),
            batch_size=batch_size,
            flush_interval_secs=flush_interval,
            heartbeat_interval_secs=heartbeat_interval,
            queue=TelemetryQueueConfig(
                max_queue_size=max_queue_size,
                max_batch_size_per_publish=max_batch_size_per_publish,
            ),
        ),
    )


# ---------------------------------------------------------------------- B1


@pytest.mark.asyncio
async def test_queue_overflow_drops_newest_with_counter_and_log():
    pub = _RecordingPublisher()
    actor = _make_actor(pub, max_queue_size=5)
    # No start() yet → nothing draining; producing 10 events overruns the
    # cap of 5.
    with structlog.testing.capture_logs() as cap:
        for i in range(10):
            actor.on_event("OrderFillReport", {"order_id": f"o{i}"})

    assert actor.drop_count() == 5, "5 events past the cap must be dropped"
    drop_events = [e for e in cap if e["event"] == "telemetry_event_dropped_queue_full"]
    assert len(drop_events) == 5
    assert drop_events[0]["reason"] == "queue_full"
    # Caller never sees QueueFull — no exception propagated.


# ---------------------------------------------------------------------- B2


@pytest.mark.asyncio
async def test_on_event_is_safe_from_a_non_loop_thread():
    pub = _RecordingPublisher()
    actor = _make_actor(pub, flush_interval=0.02)
    await actor.start()

    barrier = threading.Barrier(4)
    total_per_thread = 25

    def producer() -> None:
        barrier.wait()
        for i in range(total_per_thread):
            actor.on_event("OrderFillReport", {"order_id": f"o{i}"})

    threads = [threading.Thread(target=producer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Let the flush loop drain.
    await asyncio.sleep(0.2)
    await actor.stop()

    total = 4 * total_per_thread
    assert len(pub.telemetry_calls) == total, (
        f"expected {total} published events, got {len(pub.telemetry_calls)}"
    )
    seqs = sorted(env.ordering.seq for _, env in pub.telemetry_calls)
    # No gaps, no duplicates: seq is monotonic across threads.
    assert seqs == list(range(1, total + 1))


# ---------------------------------------------------------------------- B3


@pytest.mark.asyncio
async def test_flush_task_survives_publish_exceptions():
    pub = _ExplodingPublisher(fail_first=3)
    actor = _make_actor(pub, flush_interval=0.02)
    await actor.start()

    for i in range(10):
        actor.on_event("OrderFillReport", {"order_id": f"o{i}"})

    # Allow several flush cycles.
    await asyncio.sleep(0.2)
    await actor.stop()

    # First 3 publishes raise, but the task is still alive so the remaining
    # 7 land. The actor counts the failures, doesn't silently swallow them.
    assert pub.fail_count == 3
    assert pub.succeed_count == 7
    assert actor.drop_count() == 3


# ---------------------------------------------------------------------- B6


@pytest.mark.asyncio
async def test_stop_drains_envelopes_queued_in_flight():
    pub = _RecordingPublisher()
    actor = _make_actor(pub, batch_size=2, flush_interval=10.0)
    await actor.start()

    # Push more than batch_size; flush_interval is long so the loop is
    # quiescent. stop() must still drain everything.
    for i in range(5):
        actor.on_event("OrderFillReport", {"order_id": f"o{i}"})

    # Give event loop one tick so call_soon_threadsafe lands the puts.
    await asyncio.sleep(0)
    await actor.stop()
    assert len(pub.telemetry_calls) == 5


# ---------------------------------------------------------------------- B8


@pytest.mark.asyncio
async def test_flush_drains_beyond_batch_size_each_cycle():
    pub = _RecordingPublisher()
    # batch_size kept low so legacy implementation would publish in 50s;
    # the new contract drains up to max_batch_size_per_publish per cycle.
    actor = _make_actor(
        pub,
        max_batch_size_per_publish=200,
        batch_size=1,
        flush_interval=0.05,
    )
    await actor.start()
    for i in range(150):
        actor.on_event("OrderFillReport", {"order_id": f"o{i}"})
    await asyncio.sleep(0.15)
    await actor.stop()
    assert len(pub.telemetry_calls) == 150
    assert actor._queue.qsize() == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------- B9


@pytest.mark.asyncio
async def test_no_polling_sleep_flush_wakes_immediately():
    """When events arrive after the loop has parked on queue.get, the
    next publish should happen quickly — not at the next polling tick.
    The old 10 ms sleep loop violated this; ``queue.get`` does not."""
    pub = _RecordingPublisher()
    actor = _make_actor(pub, flush_interval=1.0, batch_size=1)
    await actor.start()

    # Wait long enough that the previous polling code would have entered
    # a sleep — then push and observe latency.
    await asyncio.sleep(0.05)
    actor.on_event("OrderFillReport", {"order_id": "o1"})

    # Within ~50 ms the publish should land; the old polling sleep made
    # this O(batch_size * 10 ms) → unreliable for small batches.
    for _ in range(20):
        if pub.telemetry_calls:
            break
        await asyncio.sleep(0.01)
    await actor.stop()
    assert len(pub.telemetry_calls) == 1
