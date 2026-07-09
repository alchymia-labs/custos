"""arx-disconnect chaos — the runner's local guards keep protecting while the
cloud is unreachable (red line 0.3: disconnect is not a stop). NATS disconnect is
simulated by publishes raising / a missing jetstream, following the established
WAL-resilience pattern; no broker or container is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.engine_protocol import ConnectivityState
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.nats_client import ArxNatsClient, NatsEnvelope, OrderingMeta
from custos.core.zombie_watchdog import ZombieWatchdog


@dataclass
class _ChaosHost:
    """A host whose engine is disconnected (zombie) and over-exposed (breaker)."""

    flatten_calls: list = field(default_factory=list)

    async def deploy(self, spec: dict, credential: dict) -> str:
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool:
        return False

    def supports_venue(self, venue: str) -> bool:
        return False

    async def get_open_notional(self, spec_id: str) -> Decimal:
        return Decimal("5000")

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=False, exec_connected=False, checked_at_epoch_s=0.0)

    async def flatten_positions(self, spec_id: str, reason: str) -> None:
        self.flatten_calls.append((spec_id, reason))


@dataclass
class _FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {"credential_id": credential_id, "permission_scope": "trade_no_withdraw"}


@dataclass
class _DisconnectedNats:
    """Cloud is unreachable: every status publish records the attempt then fails,
    so we can assert the guards still ran without the report ever landing."""

    attempts: list = field(default_factory=list)

    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        self.attempts.append((spec_id, payload))
        raise ConnectionError("arx disconnected")


async def _raising_reject_publisher(*_args) -> None:
    raise ConnectionError("arx disconnected")


def _reconciler(host: _ChaosHost, nats: _DisconnectedNats) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=host,
        credential_vault=_FakeVault(),
        local_cap=RunnerNotionalCap(
            LocalCapConfig(max_notional_per_runner=Decimal("1000")),
            reject_publisher=_raising_reject_publisher,
        ),
        fallback_breaker=FallbackBreaker(
            FallbackBreakerConfig(max_notional=Decimal("1000"), max_drawdown_pct=Decimal("20"))
        ),
        zombie_watchdog=ZombieWatchdog(grace_secs=0.0),
    )


async def test_arx_disconnect_reconciler_no_crash() -> None:
    host = _ChaosHost()
    nats = _DisconnectedNats()
    reconciler = _reconciler(host, nats)

    # Every status publish fails; the flow must still complete and advance state.
    await reconciler.handle_spec({"spec_id": "s-1", "generation": 1, "lifecycle_state": "paper"})
    await reconciler._watchdog_tick()
    await reconciler._breaker_tick()

    assert reconciler._state["s-1"].observed_generation == 1


async def test_arx_disconnect_cap_breaker_zombie_continue() -> None:
    host = _ChaosHost()
    nats = _DisconnectedNats()
    reconciler = _reconciler(host, nats)

    await reconciler.handle_spec({"spec_id": "s-1", "generation": 1, "lifecycle_state": "paper"})
    await reconciler._watchdog_tick()
    await reconciler._breaker_tick()

    # Cap: the local reject decision holds even though its cloud notify fails.
    cap_allows = await reconciler.local_cap.allows(
        symbol="BTCUSDT", current_open=Decimal("1000"), new_order_notional=Decimal("1")
    )
    assert cap_allows is False

    # Breaker: positions flattened + new orders frozen, no cloud command needed.
    assert host.flatten_calls == [("s-1", "notional_breach")]
    assert reconciler.fallback_breaker.allows_new_orders() is False

    # Zombie: the degraded escalation was produced locally and attempted (the
    # report never lands because the cloud is down, but detection continued).
    degraded_attempts = [p for _, p in nats.attempts if p["phase"] == "degraded"]
    assert degraded_attempts
    assert degraded_attempts[0]["health_reason"] == "engine_disconnected_zombie"


def _envelope() -> NatsEnvelope:
    return NatsEnvelope(
        event_id="00000000-0000-0000-0000-000000000001",
        tenant_id="acme",
        occurred_at="2026-06-25T10:00:00.000000000Z",
        payload={"event_type": "StateSnapshot", "spec_id": "s-1"},
        ordering=OrderingMeta(session_id="s1", seq=1),
    )


class _FakeJetStream:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))


async def test_arx_disconnect_snapshot_wal_cached(tmp_path) -> None:
    """A telemetry/snapshot publish during disconnect is WAL-cached and replays
    on reconnect — the durable path a periodic state snapshot rides."""
    wal_file = tmp_path / "wal.db"
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r1",
        wal_path=wal_file,
    )

    # Disconnected (no jetstream) → the publish is stashed rather than lost.
    await client.publish_telemetry_envelope("arx.acme.snapshot.state", _envelope())
    assert wal_file.exists()

    # Reconnect and drain: the cached snapshot replays.
    js = _FakeJetStream()
    client._js = js  # type: ignore[attr-defined]
    await client._drain_wal()  # type: ignore[attr-defined]

    assert len(js.published) == 1
    assert js.published[0][0] == "arx.acme.snapshot.state"

    client._wal.close()  # type: ignore[attr-defined]
