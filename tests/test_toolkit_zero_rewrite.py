from __future__ import annotations

import ast
import json
import subprocess
import sys
import warnings
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs/authority/strategy-toolkit-inventory-v1.json"
EXTRACTION_PATH = ROOT / "docs/authority/strategy-toolkit-extraction-v1.json"
PARITY_GOLDEN_PATH = ROOT / "docs/authority/strategy-toolkit-parity-golden-v1.json"
BASE_SOURCE_ROOT = ROOT / "packages/custos-strategy-toolkit/src"
NAUTILUS_SOURCE_ROOT = ROOT / "packages/custos-strategy-toolkit-nautilus/src"
LEGACY_SOURCE_ROOT = ROOT / "src/custos/engines/nautilus/toolkit"


def _inventory_entries() -> list[dict[str, Any]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return payload["files"]


def _parity_golden() -> dict[str, Any]:
    payload = json.loads(PARITY_GOLDEN_PATH.read_text(encoding="utf-8"))
    extraction = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    assert payload["oracle_source_commit"] == extraction["source_commit"]
    return payload


def _target_path(entry: dict[str, Any]) -> Path:
    target = Path(entry["target_path"])
    if target.parts[0] == "custos_toolkit":
        return BASE_SOURCE_ROOT / target
    if target.parts[0] == "custos_toolkit_nautilus":
        return NAUTILUS_SOURCE_ROOT / target
    raise AssertionError(f"unsupported toolkit target namespace: {target}")


def _legacy_path(entry: dict[str, Any]) -> Path:
    return ROOT / entry["legacy_path"]


def test_frozen_inventory_is_extracted_one_to_one() -> None:
    entries = _inventory_entries()
    targets = [_target_path(entry) for entry in entries]

    assert len(entries) == 241
    assert len(set(targets)) == 241
    assert all(target.is_file() for target in targets)
    assert all(not _legacy_path(entry).exists() for entry in entries)


def test_extracted_sources_have_no_legacy_top_level_imports() -> None:
    violations: list[str] = []

    for entry in _inventory_entries():
        target = _target_path(entry)
        if target.suffix != ".py" or not target.exists():
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.partition(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.partition(".")[0]}
            else:
                continue
            forbidden = roots & {"shared", "pandas_ta", "pkg_resources"}
            if forbidden:
                violations.append(
                    f"{target.relative_to(ROOT)}:{node.lineno}:{','.join(sorted(forbidden))}"
                )

    assert violations == []


def test_legacy_namespace_shim_has_no_import_path_side_effects() -> None:
    probe = """
import json
import sys

before = tuple(sys.path)
import custos.engines.nautilus.toolkit
after = tuple(sys.path)
print(json.dumps({
    "path_unchanged": before == after,
    "shared_loaded": "shared" in sys.modules,
    "pandas_ta_loaded": "pandas_ta" in sys.modules,
    "pkg_resources_loaded": "pkg_resources" in sys.modules,
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "path_unchanged": True,
        "shared_loaded": False,
        "pandas_ta_loaded": False,
        "pkg_resources_loaded": False,
    }


def test_signal_order_intent_projection_matches_pre_extraction_baseline() -> None:
    from custos_toolkit.signals.resolver import SignalResolver
    from custos_toolkit.signals.types import Signal, SignalDirection

    golden = _parity_golden()["signal_order_intent"]
    fixed_input = golden["input"]
    signal = Signal(
        direction=SignalDirection(fixed_input["direction"]),
        price=Decimal(fixed_input["price"]),
        strength=fixed_input["strength"],
        timestamp=fixed_input["timestamp_ns"],
        pair=fixed_input["pair"],
        amount=Decimal(fixed_input["amount"]),
        order_type=fixed_input["order_type"],
        order_price_offset=Decimal(fixed_input["order_price_offset"]),
    )

    resolved = SignalResolver().resolve(signal)

    assert SignalResolver().to_okx_format(resolved) == golden["expected"]


def test_private_vendor_supertrend_matches_pre_extraction_baseline() -> None:
    pandas = pytest.importorskip("pandas")
    from custos_toolkit_nautilus._vendor import pandas_ta

    golden = _parity_golden()["private_vendor_supertrend"]
    fixed_input = golden["input"]
    result = pandas_ta.supertrend(
        pandas.Series(fixed_input["high"], dtype="float64"),
        pandas.Series(fixed_input["low"], dtype="float64"),
        pandas.Series(fixed_input["close"], dtype="float64"),
        length=fixed_input["length"],
        multiplier=fixed_input["multiplier"],
    )

    normalized_trend = [
        None if pandas.isna(value) else round(float(value), 8) for value in result["SUPERT_3_2.0"]
    ]
    assert normalized_trend == golden["expected"]["SUPERT_3_2.0"]
    assert result["SUPERTd_3_2.0"].tolist() == golden["expected"]["SUPERTd_3_2.0"]
