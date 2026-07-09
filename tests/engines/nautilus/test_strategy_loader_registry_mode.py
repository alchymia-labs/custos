"""Registry-mode integration for the ps supertrend strategy.

Phase B: with the vendored toolkit in place, ``load_strategy_class`` +
``_instantiate_strategy``'s existing factory-probe path should reach the real
ps supertrend module (via ``toolkit/shared/nautilus``) and hand back a
``SuperTrendStrategy`` instance built by ps's own ``create_strategy(config)``
entry point. If this test is green, path (a) — reuse the existing loader,
zero custos-side loader changes — is confirmed as the production integration.

This is the sole gating spike for T1.2 (post-load registry introspection).
Phase A (temporary sys.path bridge into a live ps clone) is intentionally out
of scope here: it was only useful for confirming the probe *mechanism* before
the vendored toolkit landed, and the vendored path is what production actually
uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nautilus_trader")

# Importing the toolkit is what puts ``shared.*`` on sys.path so the ps
# strategy module can import its own dependencies during dynamic load.
import custos.engines.nautilus.toolkit  # noqa: F401 — vendored dep bootstrap
from custos.engines.nautilus.host import NtTradingNodeHost  # noqa: E402
from custos.engines.nautilus.strategy_loader import load_strategy_class  # noqa: E402

_PS_ROOT = Path(
    "/Users/wukai/data/repos/github/the-alephain-guild/alchymia-labs/philosophers-stone"
)
_REAL_SUPERTREND = _PS_ROOT / "trend" / "supertrend" / "refinement" / "nautilus" / "strategy.py"


def _spec_pointing_at_real_supertrend() -> dict:
    """A sandbox DeploymentSpec that points strategy_path at the real ps
    supertrend module. code_hash is left off (sandbox) so we exercise the
    factory-probe path without also gating on hash pinning."""
    return {
        "spec_id": "spike-real-supertrend",
        "strategy_path": str(_REAL_SUPERTREND),
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
        # No code_hash so the sandbox skip is exercised.
    }


def test_existing_loader_loads_real_supertrend_via_factory_probe() -> None:
    """The unmodified loader + existing _instantiate_strategy factory probe
    reach ps's module-level ``create_strategy(config)`` and produce a real
    ``SuperTrendStrategy``. Skips cleanly if the ps repo isn't present in the
    monorepo layout (so the test doesn't break independent-clone CI)."""
    if not _REAL_SUPERTREND.exists():
        pytest.skip(
            "ps supertrend not reachable at the workspace path; "
            "spike is monorepo-scoped by construction"
        )

    spec = _spec_pointing_at_real_supertrend()
    strategy_cls = load_strategy_class(Path(spec["strategy_path"]), spec.get("code_hash"))

    host = NtTradingNodeHost()
    strategy = host._instantiate_strategy(strategy_cls, spec)

    # Path (a) confirmed: the module-level factory-probe path in host.py
    # instantiated the ps strategy, not a raw class construction.
    assert type(strategy).__name__ == "SuperTrendStrategy", (
        "factory probe must resolve to ps's SuperTrendStrategy — "
        "if this fails, path (a) is broken and T1.2 must fall back to path (b)"
    )


def test_registry_name_matches_loaded_class_accepted() -> None:
    """Passing the correct registry name — the one strategy.py's
    module-level ``register_strategy`` call bound to ``SuperTrendStrategy`` —
    must let the load succeed. The check is additive, not a gate on happy
    path."""
    if not _REAL_SUPERTREND.exists():
        pytest.skip("ps supertrend not reachable at the workspace path")

    cls = load_strategy_class(
        _REAL_SUPERTREND,
        expected_code_hash=None,
        expected_registry_name="supertrend",
    )
    assert cls.__name__ == "SuperTrendStrategy"


def test_registry_name_mismatch_rejected() -> None:
    """When the loader's own heuristic (single ``*Strategy`` class in the
    module) finds a class that doesn't match the class registered under the
    caller-supplied name, the load must refuse. This is the guard against a
    silent misload where the heuristic silently picks the wrong class from a
    module that ships more than one strategy.

    Constructed by temporarily registering an unrelated class under a
    fake-name in the vendored toolkit's registry, then asking the loader to
    verify the ps supertrend module against that fake name. The registry has
    the fake-name (so the "unknown name" branch does not fire) but the
    binding disagrees with what the loader found (so the mismatch branch
    fires — the intended behaviour)."""
    if not _REAL_SUPERTREND.exists():
        pytest.skip("ps supertrend not reachable at the workspace path")

    from shared.nautilus import registry as ps_registry

    class _UnrelatedStrategy:
        pass

    ps_registry.register_strategy(
        name="_mismatch_probe",
        strategy_class=_UnrelatedStrategy,  # type: ignore[arg-type]
        config_class=type("_Cfg", (), {}),  # type: ignore[arg-type]
        parameters_builder=lambda _: None,
    )
    try:
        with pytest.raises(ValueError, match="does not match the loaded strategy"):
            load_strategy_class(
                _REAL_SUPERTREND,
                expected_code_hash=None,
                expected_registry_name="_mismatch_probe",
            )
    finally:
        ps_registry.unregister_strategy("_mismatch_probe")


def test_registry_mode_unknown_strategy_rejected() -> None:
    """Requesting a strategy_registry_name that no ps ``register_strategy``
    call ever bound must be refused with a structured error that lists what
    is available, so an operator can tell whether they mistyped the name or
    are pointing at the wrong strategy_path entirely."""
    if not _REAL_SUPERTREND.exists():
        pytest.skip("ps supertrend not reachable at the workspace path")

    with pytest.raises(ValueError, match="is not registered"):
        load_strategy_class(
            _REAL_SUPERTREND,
            expected_code_hash=None,
            expected_registry_name="not_a_real_strategy_name_xyz",
        )


def test_shared_import_failure_denied_at_load(tmp_path: Path) -> None:
    """A strategy module that tries to import something the vendored toolkit
    does not ship must fail loudly at load time — not silently degrade. The
    structured event carries the missing module name so ops can tell whether
    the closure is incomplete or the strategy has a typo. If this ever goes
    silent, the non-custodial observability red line is broken."""
    import textwrap

    broken_strategy = tmp_path / "strategy.py"
    broken_strategy.write_text(
        textwrap.dedent(
            """
            # Simulates a strategy whose transitive imports reach outside the
            # vendored toolkit's supported closure.
            from shared.definitely_not_in_toolkit import Nothing  # noqa: F401

            class FakeStrategy: ...
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModuleNotFoundError) as exc:
        load_strategy_class(broken_strategy, expected_code_hash=None)
    assert "definitely_not_in_toolkit" in str(exc.value)
