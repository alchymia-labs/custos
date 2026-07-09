"""G6 gate — capability-based multi-layer check, each layer independently proven.

The gate refuses a live deployment unless it clears every layer:
  1. host declares live capability
  2. host declares the spec's venue
  3. spec pins a code_hash that matches the on-disk strategy source
  4. credential permission_scope is trade_no_withdraw (vault-enforced; gate double-checks)

Each relaxed-double test keeps the other three layers valid and flips only the
one under test, so a green result proves that layer is a live guard and not a
dead branch shadowed by another (multi-layer fail-fast + independent testability).

check_g6_gate is exercised directly (not via the reconciler) so a single layer
can be isolated; NoopHost's backward-compatible live rejection is asserted too.
"""

from __future__ import annotations

import pytest
import structlog

from custos.core.g6_gate import check_g6_gate
from custos.engines.nautilus.host import NoopHost
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash


class _LiveCapableHost:
    """Relaxed double: satisfies the host-capability layers so a flipped
    venue / code_hash / scope can be proven the layer that rejects."""

    def __init__(
        self, *, live: bool = True, venues: tuple[str, ...] = ("binance", "binance_perpetual")
    ):
        self._live = live
        self._venues = {v.lower() for v in venues}

    async def deploy(self, spec: dict, credential: dict) -> str:
        return str(spec["spec_id"])

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, spec_id: str) -> None:
        return None

    def supports_live(self) -> bool:
        return self._live

    def supports_venue(self, venue: str) -> bool:
        return venue.lower() in self._venues


@pytest.fixture
def strategy_dir(tmp_path):
    d = tmp_path / "supertrend"
    d.mkdir()
    (d / "strategy.py").write_text("class SupertrendStrategy:\n    pass\n")
    return d


def _valid_spec(strategy_dir) -> dict:
    return {
        "spec_id": "live-1",
        "trading_mode": "live",
        "connector": "binance_perpetual",
        "strategy_path": str(strategy_dir / "strategy.py"),
        "code_hash": compute_strategy_dir_hash(strategy_dir),
    }


def _valid_credential() -> dict:
    return {"api_key": "k", "api_secret": "s", "permission_scope": "trade_no_withdraw"}


def test_ntlive_host_accepted_with_all_layers_passing(strategy_dir) -> None:
    # All four layers valid → gate returns (no raise). This is the positive
    # anchor every relaxed-double test flips exactly one layer away from.
    check_g6_gate(_LiveCapableHost(), _valid_spec(strategy_dir), _valid_credential())


def test_noophost_still_rejects_live(strategy_dir) -> None:
    # Backward compat: the paper stub is still refused on live, now via its
    # supports_live()=False capability declaration (layer 1) rather than isinstance.
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(NoopHost(), _valid_spec(strategy_dir), _valid_credential())
    assert "g6_gate_live_capability_denied" in [e.get("event") for e in logs]


class _CapabilityLessHost:
    """A host that satisfies deploy/reconfigure/stop but never declared the
    capability contract — stands in for a third-party host that forgot to."""

    async def deploy(self, spec: dict, credential: dict) -> str:
        return str(spec["spec_id"])

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, spec_id: str) -> None:
        return None


def test_undeclared_capability_host_gets_structured_reject(strategy_dir) -> None:
    # An undeclared capability must fail-safe with the structured G6 reason, not
    # an AttributeError (the contract promises g6_gate_live_capability_denied).
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_CapabilityLessHost(), _valid_spec(strategy_dir), _valid_credential())
    assert "g6_gate_live_capability_denied" in [e.get("event") for e in logs]


def test_layer1_capability_relaxed_double(strategy_dir) -> None:
    # Layers 2/3/4 valid; only host live-capability flipped off → layer 1 rejects.
    host = _LiveCapableHost(live=False)
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(host, _valid_spec(strategy_dir), _valid_credential())
    assert "g6_gate_live_capability_denied" in [e.get("event") for e in logs]


def test_layer2_venue_unsupported_relaxed_double(strategy_dir) -> None:
    # Host is live-capable; only the spec's venue is unsupported → layer 2 rejects.
    spec = _valid_spec(strategy_dir)
    spec["connector"] = "okx_perpetual"
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_LiveCapableHost(), spec, _valid_credential())
    assert "g6_gate_venue_unsupported" in [e.get("event") for e in logs]


def test_layer3_code_hash_mismatch_relaxed_double(strategy_dir) -> None:
    # Host + venue + scope valid; only code_hash disagrees with the source → layer 3.
    spec = _valid_spec(strategy_dir)
    spec["code_hash"] = "deadbeef" * 8
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_LiveCapableHost(), spec, _valid_credential())
    assert "g6_gate_code_hash_mismatch" in [e.get("event") for e in logs]


def test_layer3_code_hash_missing_relaxed_double(strategy_dir) -> None:
    # Live must pin a code_hash; the loader only skips it for sandbox, so the
    # gate is the layer that refuses a live spec with no pin.
    spec = _valid_spec(strategy_dir)
    spec.pop("code_hash")
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_LiveCapableHost(), spec, _valid_credential())
    assert "g6_gate_code_hash_mismatch" in [e.get("event") for e in logs]


def test_layer3_missing_strategy_path_refused(strategy_dir) -> None:
    # A live spec that pins a code_hash but carries no strategy_path is refused,
    # not silently hashed against the process CWD.
    spec = _valid_spec(strategy_dir)
    spec.pop("strategy_path")
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_LiveCapableHost(), spec, _valid_credential())
    assert "g6_gate_code_hash_mismatch" in [e.get("event") for e in logs]


def test_layer4_credential_scope_violation_relaxed_double(strategy_dir) -> None:
    # Host + venue + code_hash valid; only credential scope is unsafe → layer 4.
    # The vault rejects this first in production; passing it here directly proves
    # the gate's double-check is a live guard, not a branch the vault shadows.
    bad_credential = {"api_key": "k", "api_secret": "s", "permission_scope": "trade_and_withdraw"}
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            check_g6_gate(_LiveCapableHost(), _valid_spec(strategy_dir), bad_credential)
    assert "g6_gate_credential_scope_violation" in [e.get("event") for e in logs]


def test_layer4_skipped_when_no_credential(strategy_dir) -> None:
    # Reconfigure re-runs the gate without re-decrypting the credential; layers
    # 1-3 still guard, and layer 4 is skipped (scope was validated at deploy).
    check_g6_gate(_LiveCapableHost(), _valid_spec(strategy_dir), None)


def test_non_live_mode_bypasses_all_layers(strategy_dir) -> None:
    # paper/sandbox/testnet route through their own host path; the strict gate
    # guards live only, so a paper spec passes even with a stub host.
    spec = _valid_spec(strategy_dir)
    spec["trading_mode"] = "paper"
    check_g6_gate(NoopHost(), spec, None)
