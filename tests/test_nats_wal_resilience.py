"""WAL resilience tests for B4 (per-row drain) + B5 (size cap).

Cover three properties the audit said the original WAL implementation
broke:

1. A mid-stream publish failure leaves the **remaining** rows in the WAL
   so a future reconnect can retry — the original ``_drain_wal`` used a
   single batch ``forget`` so a failure on row N would lose rows 0..N-1.
2. The WAL trims oldest rows once ``max_rows`` is exceeded; the trim
   is observable through ``depth()``.
3. ``depth()`` is exposed for ops metrics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arx_runner.nats_client import (
    ArxNatsClient,
    NatsEnvelope,
    OrderingMeta,
    _OfflineWal,
)


def _envelope(seq: int = 1) -> NatsEnvelope:
    return NatsEnvelope(
        event_id=f"00000000-0000-0000-0000-{seq:012d}",
        tenant_id="acme",
        occurred_at="2026-06-25T10:00:00.000000000Z",
        payload={"event_type": "OrderFillReport", "order_id": f"o{seq}"},
        ordering=OrderingMeta(session_id="s1", seq=seq),
    )


class _FlakyJetStream:
    """Fails on the Nth publish; succeeds on every other call. Records
    every successful publish so the test can assert ordering."""

    def __init__(self, fail_on: int) -> None:
        self.fail_on = fail_on
        self.calls = 0
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("simulated broker hiccup")
        self.published.append((subject, payload))


@pytest.mark.asyncio
async def test_wal_drain_keeps_unsent_rows_on_publish_failure(tmp_path: Path):
    wal_file = tmp_path / "wal.db"
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r1",
        wal_path=wal_file,
    )

    # Stash 10 messages while disconnected.
    for i in range(1, 11):
        await client.publish_telemetry_envelope(
            f"arx.acme.telemetry.r1.s1.msg-{i}", _envelope(i)
        )
    assert client._wal.depth() == 10  # type: ignore[union-attr]

    # Reconnect with a flaky jetstream — fails on call 5 → rows 1..4 must
    # be forgotten, rows 5..10 must remain for a future retry.
    js = _FlakyJetStream(fail_on=5)
    client._js = js  # type: ignore[attr-defined]
    await client._drain_wal()

    assert len(js.published) == 4, "rows before failure must have been sent"
    remaining = client._wal.depth()  # type: ignore[union-attr]
    assert remaining == 6, "row that failed + tail must stay buffered"

    client._wal.close()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_wal_size_cap_drops_oldest_when_exceeded(tmp_path: Path):
    """Stash > max_rows messages; the oldest must be dropped."""
    wal = _OfflineWal(tmp_path / "wal.db", max_rows=5, max_age_secs=3600)

    for i in range(1, 11):
        wal.stash(f"arx.t.telemetry.r1.s1.{i}", b"x")

    # After 10 inserts the cap is 5 → the 5 oldest were trimmed.
    assert wal.depth() == 5

    # Order preserved: only the most recent 5 remain.
    rows = wal.drain()
    subjects = [s for _, s, _ in rows]
    assert subjects == [f"arx.t.telemetry.r1.s1.{i}" for i in range(6, 11)]
    wal.close()


def test_wal_depth_starts_empty(tmp_path: Path):
    wal = _OfflineWal(tmp_path / "wal.db")
    assert wal.depth() == 0
    wal.close()
