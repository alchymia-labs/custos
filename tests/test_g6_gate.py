"""G6 gate — live-mode capability gate exercised through the reconciler.

Reconciler-integration view (unit-level layer isolation lives in
test_g6_gate_capability_e2e.py):
- live + NoopHost → refused (RuntimeError "G6 gate") + structlog error, across
  trading_mode case variants (Rust TradingMode serialises PascalCase "Live")
- paper + NoopHost → allowed (deploy proceeds; no regression)
- live + a live-capable host with every layer valid → allowed (relaxed double
  proving the gate only refuses hosts that lack capability, not all live specs)

The gate sits in DeploymentReconciler._apply_spec before deploy/reconfigure
(stop is exempt: tearing a live+stub deployment down is safe). Tests drive
_apply_spec directly — the gate's guard layer; handle_spec's broad except would
swallow the raise, so this layer is where a rejection is observable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import structlog

from custos.core.deployment_reconciler import DeploymentReconciler, _ReconcileState
from custos.engines.nautilus.host import NoopHost
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash


@dataclass
class _FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {
            "credential_id": credential_id,
            "permission_scope": "trade_no_withdraw",
            "secret": "<fake>",
        }


@dataclass
class _FakeNats:
    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        return None


@dataclass
class _FakeNtHost:
    """Non-NoopHost host that declares live + Binance capability — stands in for
    NtTradingNodeHost so a live spec that clears every gate layer is admitted.

    relaxed double: declaring capability (not being a NoopHost) is what lets it
    through, proving the gate refuses on missing capability rather than on all
    live specs (the inner layers are live guards, not a dead branch)."""

    deploy_calls: list = field(default_factory=list)

    async def deploy(self, spec: dict, credential: dict) -> str:
        self.deploy_calls.append((spec, credential))
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, spec_id: str) -> None:
        return None

    def supports_live(self) -> bool:
        return True

    def supports_venue(self, venue: str) -> bool:
        return venue.lower() in {"binance", "binance_perpetual"}


def _make_reconciler(host) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=_FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=host,
        credential_vault=_FakeVault(),  # type: ignore[arg-type]
        runtime_log_emitter=object(),  # type: ignore[arg-type]
        lifecycle_fact_emitter=object(),  # type: ignore[arg-type]
        deployment_verifier=object(),  # type: ignore[arg-type]
    )


def _spec(spec_id: str, trading_mode: str) -> dict:
    return {
        "spec_id": spec_id,
        "deployment_instance_id": spec_id,
        "generation": 1,
        "trading_mode": trading_mode,
        "lifecycle_state": "running",
        "provenance_ref": {"credential_id": f"cred-{spec_id}"},
    }


def _live_spec(spec_id: str, trading_mode: str, strategy_dir) -> dict:
    spec = _spec(spec_id, trading_mode)
    spec["connector"] = "binance_perpetual"
    spec["strategy_path"] = str(strategy_dir / "strategy.py")
    spec["code_hash"] = compute_strategy_dir_hash(strategy_dir)
    return spec


@pytest.fixture
def strategy_dir(tmp_path):
    d = tmp_path / "supertrend"
    d.mkdir()
    (d / "strategy.py").write_text("class SupertrendStrategy:\n    pass\n")
    return d


@pytest.mark.parametrize("mode", ["Live", "live", "LIVE"])
@pytest.mark.asyncio
async def test_g6_gate_rejects_live_noophost(mode: str) -> None:
    # "Live" is the real Rust TradingMode serde wire value (PascalCase); case
    # variants are asserted together so a case mismatch can't turn the gate into
    # a dead gate. NoopHost is refused at layer 1 (supports_live()=False).
    reconciler = _make_reconciler(NoopHost())
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            await reconciler._apply_spec("s1", _spec("s1", mode), _ReconcileState())
    events = [entry.get("event") for entry in logs]
    assert "g6_gate_live_capability_denied" in events


@pytest.mark.asyncio
async def test_g6_gate_allows_paper_noophost() -> None:
    reconciler = _make_reconciler(NoopHost())
    container_id = await reconciler._apply_spec("s2", _spec("s2", "paper"), _ReconcileState())
    assert container_id == "container-s2"


@pytest.mark.asyncio
async def test_g6_gate_allows_live_nt_host(strategy_dir) -> None:
    host = _FakeNtHost()
    reconciler = _make_reconciler(host)
    # Real live wire value "Live" + a live-capable host clearing every layer →
    # gate admits (relaxed double).
    container_id = await reconciler._apply_spec(
        "s3", _live_spec("s3", "Live", strategy_dir), _ReconcileState()
    )
    assert container_id == "container-s3"
    assert len(host.deploy_calls) == 1
