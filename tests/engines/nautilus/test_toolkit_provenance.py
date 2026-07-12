"""Vendored toolkit provenance + red-line 0.4 float money math audit.

The `engines/nautilus/toolkit/` directory is a vendored snapshot of the ps
`shared/` supertrend dependency closure (packaging option A). Two invariants
are guarded here:

1. **Provenance is recorded** — TOOLKIT_PROVENANCE.md must exist next to the
   vendored code and pin the upstream commit + subset that was copied, so
   drift can be audited and re-sync can be planned.

2. **No float money math inside the vendored code** — non-custodial red line
   0.4 (mandatory-rules §0.4) forbids float in price/amount/notional/equity
   paths. Bulk-imported code from another repo has to clear the same gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_TOOLKIT_ROOT = (
    Path(__file__).resolve().parents[2].parent
    / "src"
    / "custos"
    / "engines"
    / "nautilus"
    / "toolkit"
)
_PROVENANCE_FILE = _TOOLKIT_ROOT / "TOOLKIT_PROVENANCE.md"


def test_toolkit_provenance_records_upstream_commit() -> None:
    """Provenance file exists, records upstream commit shas for both vendored
    trees (ps shared/ and pandas_ta), and lists the subset of packages that
    were vendored so drift can be audited later."""
    assert _PROVENANCE_FILE.exists(), (
        f"vendored toolkit must ship a provenance manifest at {_PROVENANCE_FILE}"
    )
    text = _PROVENANCE_FILE.read_text(encoding="utf-8")

    # At least two upstream commit shas: one for ps shared/, one for pandas_ta.
    shas = re.findall(r"\b[0-9a-f]{7,40}\b", text)
    assert len(shas) >= 2, (
        "provenance manifest must record upstream shas for both vendored trees "
        "(philosophers-stone + pandas_ta)"
    )

    # Upstream repo URL pins.
    assert "philosophers-stone" in text, "provenance manifest must identify the ps upstream"
    assert "pandas_ta" in text.lower() or "pandas-ta" in text.lower(), (
        "provenance manifest must identify the pandas_ta upstream"
    )

    # Vendored subset must be enumerated so re-sync knows what to copy.
    for expected_package in ("config", "nautilus", "risk", "signals"):
        assert expected_package in text, (
            f"provenance manifest must list the '{expected_package}' subset that was vendored"
        )


def test_toolkit_ships_pandas_ta_license_for_attribution() -> None:
    """MIT vendoring requires the LICENSE to travel with the code so an auditor
    who reads the vendored tree can see the attribution."""
    license_path = _TOOLKIT_ROOT / "vendor" / "pandas_ta" / "LICENSE"
    assert license_path.exists(), (
        "pandas_ta LICENSE must be vendored alongside the code (MIT attribution invariant)"
    )
    body = license_path.read_text(encoding="utf-8")
    assert "MIT" in body, "pandas_ta LICENSE must be the MIT text"
    assert "pandas-ta" in body.lower() or "pandas_ta" in body.lower(), (
        "pandas_ta LICENSE must credit the pandas-ta project"
    )


def test_vendored_toolkit_no_new_float_money_math() -> None:
    """Red-line 0.4 watchdog on the vendored toolkit.

    The non-custodial red line forbids ``float()`` in money-computation paths
    (price/amount/notional/equity/balance/pnl/drawdown/profit/loss/margin).
    The vendored trees are byte-identical snapshots of their upstreams and
    cannot be patched without violating the sync invariant — so this test
    records the known-safe hits with justifications and fails if any new
    hits are introduced.

    Two categories of exempted hits:

    - **Indicator / OHLCV data** — pandas_ta and its callers work in float
      natively; the vendored ``PriceSnapshot`` dataclass exists to compare
      warmup checkpoints against historical bar data, never to place orders.
    - **Startup validation thresholds** — the ``startup_validator`` compares
      the operator-configured ``initial_capital`` against actual account
      balance to catch config drift before any order goes out. The float
      multiplication is a fail-fast threshold, not a fund-flow computation;
      the money that actually leaves the account is sized by NT's
      Decimal-typed ``Money`` / ``Quantity`` further down the pipeline.

    Anything else is a red-line breach and must be resolved (either by
    filing an upstream fix and re-syncing, or by escalating to CEO if the
    upstream can't be moved). See plan
    §DEV-06-06A-PANDAS-TA-FLOAT-EXCEPTIONS for the tracking record.
    """
    import subprocess

    toolkit_root = _TOOLKIT_ROOT
    money_words = (
        "price",
        "amount",
        "notional",
        "equity",
        "balance",
        "pnl",
        "drawdown",
        "profit",
        "loss",
        "margin",
    )
    pattern = rf"float\([^)]*({'|'.join(money_words)})"
    result = subprocess.run(
        ["grep", "-rnE", pattern, str(toolkit_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line]

    # Known-safe exemptions — each entry is (relative_path_suffix, count).
    # If the vendored code drifts and a new hit appears anywhere else, the
    # difference against this set is what fails the test.
    expected_exemptions = {
        # PriceSnapshot dataclass construction: OHLCV bar data for indicator
        # warmup checkpoints. Not a fund-flow path.
        "toolkit/shared/warmup/snapshot.py": 5,
        # startup_validator initial_capital vs actual balance sanity check.
        # Fail-fast threshold at startup, does not size orders.
        "toolkit/shared/nautilus/coordinators/startup_validator.py": 5,
    }

    counts: dict[str, int] = {}
    for line in lines:
        # grep -rn output: "<path>:<lineno>:<code>". Split at first two ":".
        path_part = line.split(":", 2)[0]
        rel = str(Path(path_part).resolve().relative_to(toolkit_root.parent))
        # Match against the suffix — vendored paths are stable, worktree
        # prefix is not.
        for suffix, _ in expected_exemptions.items():
            if rel.endswith(suffix) or suffix in rel:
                counts[suffix] = counts.get(suffix, 0) + 1
                break
        else:
            pytest.fail(
                f"red-line 0.4 breach — unexpected float() money-math hit in vendored "
                f"toolkit at {rel}: {line}. Either patch the upstream and re-sync, "
                f"or add an exemption with a written justification."
            )

    for suffix, expected in expected_exemptions.items():
        actual = counts.get(suffix, 0)
        assert actual == expected, (
            f"exemption count drift for {suffix}: expected {expected}, "
            f"grep now finds {actual}. Adjust the exemption to match the "
            f"new upstream, or investigate whether the new hits are truly non-fund-flow."
        )


def test_toolkit_import_bootstrap_resolves_shared() -> None:
    """The base install must expose the vendored shared toolkit imports."""
    # Fresh import via a per-test module name so we don't rely on prior state.
    import importlib

    importlib.import_module("custos.engines.nautilus.toolkit")

    shared_nautilus = importlib.import_module("shared.nautilus")
    assert Path(shared_nautilus.__file__).is_relative_to(_TOOLKIT_ROOT / "shared" / "nautilus"), (
        "bare `shared.nautilus` import must resolve into the vendored toolkit tree"
    )


def test_toolkit_import_bootstrap_resolves_pandas_ta_with_nautilus_extra() -> None:
    """The Nautilus install must expose the vendored pandas_ta import."""
    import importlib

    pytest.importorskip("nautilus_trader")
    importlib.import_module("custos.engines.nautilus.toolkit")

    pandas_ta = importlib.import_module("pandas_ta")
    assert Path(pandas_ta.__file__).is_relative_to(_TOOLKIT_ROOT / "vendor" / "pandas_ta"), (
        "bare `pandas_ta` import must resolve into the vendored toolkit tree"
    )
