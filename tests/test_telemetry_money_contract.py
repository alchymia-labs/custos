"""Money-field type contract at the telemetry boundary.

Money values entering NATS must already be strings (``str(Decimal)``) — a
raw ``float`` is structurally lossy and silently corrupts the
differential-test invariant against the Crucible Python reference. The
actor rejects floats at ``on_event`` so a buggy producer cannot leak
binary fractions into the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from arx_runner.nats_client import NatsEnvelope
from arx_runner.telemetry_actor import (
    MONEY_FIELD_NAMES,
    MoneyFieldFloatRejected,
    TelemetryActor,
    TelemetryActorConfig,
)


@dataclass
class _Recorder:
    telemetry_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)
    heartbeat_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None:
        self.telemetry_calls.append((session_id, envelope))

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        self.heartbeat_calls.append((session_id, envelope))


def _actor() -> tuple[TelemetryActor, _Recorder]:
    rec = _Recorder()
    actor = TelemetryActor(
        publisher=rec,
        tenant_id="acme",
        runner_id="runner-001",
        config=TelemetryActorConfig(allowed_event_types=frozenset({"snapshot"})),
    )
    return actor, rec


@pytest.mark.parametrize("field_name", sorted(MONEY_FIELD_NAMES))
def test_float_money_field_rejected(field_name: str) -> None:
    actor, _ = _actor()
    with pytest.raises(MoneyFieldFloatRejected) as exc:
        actor.on_event("snapshot", {field_name: 1.1, "equity_currency": "USD"})
    assert field_name in str(exc.value)


def test_string_money_field_accepted() -> None:
    actor, _ = _actor()
    # str(Decimal("1.1")) shape is the only legal form.
    actor.on_event("snapshot", {"equity": "1.1", "equity_currency": "USD"})


def test_int_money_field_accepted() -> None:
    # int is exact, not lossy — only float is rejected.
    actor, _ = _actor()
    actor.on_event("snapshot", {"equity": 1, "equity_currency": "USD"})


def test_non_money_float_still_allowed() -> None:
    # Fields outside the money set may carry float (e.g. ratios, durations).
    actor, _ = _actor()
    actor.on_event(
        "snapshot",
        {"equity": "1.1", "equity_currency": "USD", "latency_secs": 0.05},
    )


def test_bool_money_field_rejected() -> None:
    # bool is a float subclass in Python — must also be rejected to avoid
    # ``True`` silently round-tripping as ``1.0``.
    actor, _ = _actor()
    with pytest.raises(MoneyFieldFloatRejected):
        actor.on_event("snapshot", {"equity": True, "equity_currency": "USD"})
