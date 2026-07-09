"""Runner fallback breaker — notional / drawdown trips, Decimal drawdown, freeze,
and autonomous flatten during an arx disconnect (red line 0.3 hard limit)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.engine_protocol import ConnectivityState
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig


def _breaker(max_notional: str = "1000", max_drawdown: str = "20") -> FallbackBreaker:
    return FallbackBreaker(
        FallbackBreakerConfig(
            max_notional=Decimal(max_notional), max_drawdown_pct=Decimal(max_drawdown)
        )
    )


# -- Breaker trip logic ---------------------------------------------------


def test_breaker_trips_on_notional_breach() -> None:
    verdict = _breaker(max_notional="1000").evaluate(open_notional=Decimal("1500"))
    assert verdict.tripped is True
    assert verdict.reason == "notional_breach"


def test_breaker_trips_on_drawdown_breach() -> None:
    breaker = _breaker(max_notional="100000", max_drawdown="20")
    breaker.evaluate(open_notional=Decimal("0"), current_equity=Decimal("1000"))  # peak = 1000
    verdict = breaker.evaluate(open_notional=Decimal("0"), current_equity=Decimal("700"))  # -30%
    assert verdict.tripped is True
    assert verdict.reason == "drawdown_breach"


def test_breaker_drawdown_uses_decimal_not_float() -> None:
    breaker = _breaker(max_notional="100000", max_drawdown="50")
    breaker.evaluate(open_notional=Decimal("0"), current_equity=Decimal("1000"))
    verdict = breaker.evaluate(open_notional=Decimal("0"), current_equity=Decimal("900"))
    assert isinstance(verdict.drawdown_pct, Decimal)
    assert verdict.drawdown_pct == Decimal("10")  # (1000 - 900) / 1000 * 100


def test_breaker_freezes_new_orders_after_trip() -> None:
    breaker = _breaker(max_notional="1000")
    assert breaker.allows_new_orders() is True
    breaker.evaluate(open_notional=Decimal("1500"))
    assert breaker.allows_new_orders() is False
    # Stays frozen even once exposure falls back within the limit.
    breaker.evaluate(open_notional=Decimal("0"))
    assert breaker.allows_new_orders() is False


def test_breaker_is_live_guard_relaxed_double() -> None:
    # No cap layer present — the breaker alone must trip on the notional breach,
    # proving it is an independent live guard, not a dead branch that only fires
    # because the cap already rejected.
    verdict = _breaker(max_notional="1000").evaluate(open_notional=Decimal("2000"))
    assert verdict.tripped is True


# -- Reconciler wiring (composition root + disconnect autonomy) -----------


@dataclass
class _BreachHost:
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
        return Decimal("5000")  # over any small breaker ceiling

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=True, exec_connected=True, checked_at_epoch_s=0.0)

    async def flatten_positions(self, spec_id: str, reason: str) -> None:
        self.flatten_calls.append((spec_id, reason))


@dataclass
class _FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {"credential_id": credential_id, "permission_scope": "trade_no_withdraw"}


@dataclass
class _FakeNats:
    status_calls: list = field(default_factory=list)

    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        self.status_calls.append((spec_id, payload))


async def test_breaker_trips_during_arx_disconnect() -> None:
    """The breaker flattens autonomously from the reconcile-loop tick — no cloud
    command needed while arx is unreachable (red line 0.3 hard limit)."""
    host = _BreachHost()
    breaker = _breaker(max_notional="1000")
    reconciler = DeploymentReconciler(
        nats_client=_FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=host,
        credential_vault=_FakeVault(),
        fallback_breaker=breaker,
    )

    await reconciler.handle_spec({"spec_id": "s-1", "generation": 1, "lifecycle_state": "paper"})
    await reconciler._breaker_tick()

    assert host.flatten_calls == [("s-1", "notional_breach")]
    assert breaker.allows_new_orders() is False


def test_reconciler_constructs_all_three_guards() -> None:
    """The composition root wires all three local guards into the reconciler
    (runtime wire, not just defined)."""
    from custos.cli.main import _build_reconciler

    args = SimpleNamespace(tenant_id="acme", runner_id="runner-7")
    reconciler = _build_reconciler(args, object(), object(), object())  # type: ignore[arg-type]

    assert reconciler.local_cap is not None
    assert reconciler.fallback_breaker is not None
    assert reconciler.zombie_watchdog is not None
