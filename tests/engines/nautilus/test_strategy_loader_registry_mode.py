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

import sys
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("nautilus_trader")

from custos.engines.nautilus.host import NtTradingNodeHost
from custos.engines.nautilus.strategy_loader import load_strategy_class

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_SUPERTREND = _REPO_ROOT / "tests/fixtures/real_supertrend/strategy.py"


def _spec_pointing_at_real_supertrend() -> dict:
    """Point a sandbox spec at the inventory-extracted Supertrend fixture."""
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
    """The loader and factory probe instantiate the extracted Supertrend."""

    spec = _spec_pointing_at_real_supertrend()
    strategy_cls = load_strategy_class(Path(spec["strategy_path"]), spec.get("code_hash"))

    host = NtTradingNodeHost()
    strategy = host._instantiate_strategy(strategy_cls, spec)

    # The module-level factory-probe path instantiates the extracted strategy,
    # rather than falling back to raw class construction.
    assert type(strategy).__name__ == "SuperTrendStrategy", (
        "factory probe must resolve to the extracted SuperTrendStrategy; "
        "if this fails, path (a) is broken and T1.2 must fall back to path (b)"
    )


def test_registry_name_matches_loaded_class_accepted() -> None:
    """Passing the correct registry name — the one strategy.py's
    module-level ``register_strategy`` call bound to ``SuperTrendStrategy`` —
    must let the load succeed. The check is additive, not a gate on happy
    path."""
    cls = load_strategy_class(
        _REAL_SUPERTREND,
        expected_code_hash=None,
        expected_registry_name="supertrend",
    )
    assert cls.__name__ == "SuperTrendStrategy"


def test_registry_binding_recovers_after_e2e_style_teardown(
    clear_strategy_module_cache,
) -> None:
    """Registry teardown must evict only the matching dynamic module family."""
    from custos_toolkit_nautilus.adapter import registry as ps_registry

    first_class = load_strategy_class(
        _REAL_SUPERTREND,
        expected_code_hash=None,
        expected_registry_name="supertrend",
    )
    module_name = first_class.__module__
    child_name = f"{module_name}._test_child"
    unrelated_name = f"{module_name}_unrelated"
    sys.modules[child_name] = ModuleType(child_name)
    sys.modules[unrelated_name] = ModuleType(unrelated_name)

    try:
        ps_registry.unregister_strategy("supertrend")
        removed = clear_strategy_module_cache(_REAL_SUPERTREND)

        assert set(removed) == {module_name, child_name}
        assert unrelated_name in sys.modules

        reloaded_class = load_strategy_class(
            _REAL_SUPERTREND,
            expected_code_hash=None,
            expected_registry_name="supertrend",
        )
        assert reloaded_class is not first_class
        assert ps_registry.get_strategy_info("supertrend")["strategy_class"] is reloaded_class
    finally:
        sys.modules.pop(child_name, None)
        sys.modules.pop(unrelated_name, None)


def test_registry_name_mismatch_rejected() -> None:
    """When the loader's own heuristic (single ``*Strategy`` class in the
    module) finds a class that doesn't match the class registered under the
    caller-supplied name, the load must refuse. This is the guard against a
    silent misload where the heuristic silently picks the wrong class from a
    module that ships more than one strategy.

    Constructed by temporarily registering an unrelated class under a
    fake-name in the extracted toolkit registry, then asking the loader to
    verify the Supertrend fixture against that fake name. The registry has
    the fake-name (so the "unknown name" branch does not fire) but the
    binding disagrees with what the loader found (so the mismatch branch
    fires — the intended behaviour)."""
    from custos_toolkit_nautilus.adapter import registry as ps_registry

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
            from custos_toolkit.definitely_not_in_toolkit import Nothing  # noqa: F401

            class FakeStrategy: ...
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ModuleNotFoundError) as exc:
        load_strategy_class(broken_strategy, expected_code_hash=None)
    assert "definitely_not_in_toolkit" in str(exc.value)
