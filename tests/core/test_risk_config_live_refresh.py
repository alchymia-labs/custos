"""Reconciler refreshes local guards from each spec's risk_config (04b-fix MED-3).

``docs/domain.md`` L104 promises: "daemon reads risk_config from the spec and
changes take effect next loop". The 04b squash-merge shipped local guards
constructed from an empty dict at startup only — an operator raising
``fallback_breaker.max_notional`` or ``max_notional_per_runner`` on the cloud
side had no runtime effect. This test locks in the live-refresh contract:
each accepted spec that advances generation triggers a re-read of
``risk_config`` and swaps the guard configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.engine_protocol import ConnectivityState, EngineStatus
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.zombie_watchdog import ZombieWatchdog


@dataclass
class _Host:
    async def deploy(self, spec: dict, credential: dict) -> str:
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool:
        return True

    def supports_venue(self, venue: str) -> bool:
        return True

    async def get_open_notional(self, spec_id: str) -> Decimal:
        return Decimal("0")

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=True, exec_connected=True, checked_at_epoch_s=0.0)

    async def flatten_positions(self, spec_id: str, reason: str) -> None: ...

    async def get_engine_status(self, spec_id: str) -> EngineStatus:
        return EngineStatus(
            phase="running",
            position_count=0,
            order_count=0,
            open_notional=Decimal("0"),
            peak_equity=Decimal("0"),
            current_equity=Decimal("0"),
            drawdown_pct=Decimal("0"),
        )


@dataclass
class _NoopNats:
    attempts: list = field(default_factory=list)

    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        self.attempts.append((spec_id, payload))


@dataclass
class _Vault:
    def decrypt(self, credential_id: str) -> dict:
        return {"credential_id": credential_id, "permission_scope": "trade_no_withdraw"}


def _make_reconciler() -> DeploymentReconciler:
    """Start with the conservative floors (paper cap 200, breaker 1000 / 20 %)."""

    return DeploymentReconciler(
        nats_client=_NoopNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=_Host(),  # type: ignore[arg-type]
        credential_vault=_Vault(),
        local_cap=RunnerNotionalCap(LocalCapConfig.from_spec({}, live=False)),
        fallback_breaker=FallbackBreaker(FallbackBreakerConfig.from_spec({})),
        zombie_watchdog=ZombieWatchdog(),
    )


async def test_local_cap_refreshes_when_spec_changes_max_notional() -> None:
    """Operator raises ``max_notional_per_runner`` in the spec — the very next
    reconciled spec must swap the local cap's config so orders up to the new
    ceiling are allowed."""

    reconciler = _make_reconciler()
    # Default floor: paper cap = 200. Spec 1 raises it to 500.
    await reconciler.handle_spec(
        {
            "spec_id": "s-1",
            "generation": 1,
            "lifecycle_state": "paper",
            "risk_config": {"max_notional_per_runner": "500"},
        }
    )
    assert reconciler.local_cap.config.max_notional_per_runner == Decimal("500")
    assert await reconciler.local_cap.allows(
        symbol="BTCUSDT", current_open=Decimal("0"), new_order_notional=Decimal("450")
    )

    # Spec 2 (generation +1) lowers the cap to 100 — the next order over 100
    # must be refused even though the previous cap allowed it.
    await reconciler.handle_spec(
        {
            "spec_id": "s-1",
            "generation": 2,
            "lifecycle_state": "paper",
            "risk_config": {"max_notional_per_runner": "100"},
        }
    )
    assert reconciler.local_cap.config.max_notional_per_runner == Decimal("100")
    allowed = await reconciler.local_cap.allows(
        symbol="BTCUSDT", current_open=Decimal("0"), new_order_notional=Decimal("450")
    )
    assert allowed is False


async def test_fallback_breaker_refreshes_when_spec_changes_max_notional() -> None:
    """Operator raises ``fallback_breaker.max_notional`` — the breaker must
    stop tripping at the old ceiling."""

    reconciler = _make_reconciler()
    # Default floor: breaker max_notional = 1000. Raise to 3000.
    await reconciler.handle_spec(
        {
            "spec_id": "s-1",
            "generation": 1,
            "lifecycle_state": "paper",
            "risk_config": {"fallback_breaker": {"max_notional": "3000"}},
        }
    )
    assert reconciler.fallback_breaker._config.max_notional == Decimal("3000")

    # Evaluate with 2000 open — old ceiling would have tripped; new ceiling
    # keeps us safe.
    verdict = reconciler.fallback_breaker.evaluate(open_notional=Decimal("2000"))
    assert verdict.tripped is False


async def test_risk_config_refresh_is_noop_when_unchanged() -> None:
    """Same spec re-sent (same generation) must be a no-op — the reconciler
    already skips at the generation check; refresh must not fire structlog
    on unchanged config in the second-generation path either."""

    reconciler = _make_reconciler()
    await reconciler.handle_spec(
        {
            "spec_id": "s-1",
            "generation": 1,
            "lifecycle_state": "paper",
            "risk_config": {"max_notional_per_runner": "500"},
        }
    )
    initial_cap = reconciler.local_cap.config
    initial_breaker = reconciler.fallback_breaker._config

    # A generation +1 spec with the same risk_config: refresh detects no
    # change and preserves the same config identity semantics (value equal).
    await reconciler.handle_spec(
        {
            "spec_id": "s-1",
            "generation": 2,
            "lifecycle_state": "paper",
            "risk_config": {"max_notional_per_runner": "500"},
        }
    )
    assert reconciler.local_cap.config == initial_cap
    assert reconciler.fallback_breaker._config == initial_breaker


async def test_risk_config_refresh_uses_lifecycle_for_live_floor() -> None:
    """When the spec has no explicit ``max_notional_per_runner``, ``from_spec``
    picks the paper or live floor from the ``live`` kwarg. The refresh must
    pass the current lifecycle_state so a spec flipped to ``live`` gets the
    live floor (higher default), not the paper floor."""

    reconciler = _make_reconciler()
    # Paper spec: no risk_config → paper floor.
    await reconciler.handle_spec({"spec_id": "s-1", "generation": 1, "lifecycle_state": "paper"})
    from custos.core.local_cap import LIVE_CAP_FLOOR_USD, PAPER_CAP_FLOOR_USD

    assert reconciler.local_cap.config.max_notional_per_runner == PAPER_CAP_FLOOR_USD

    # Flip to live: refresh must upgrade to the live floor.
    await reconciler.handle_spec({"spec_id": "s-1", "generation": 2, "lifecycle_state": "live"})
    assert reconciler.local_cap.config.max_notional_per_runner == LIVE_CAP_FLOOR_USD
