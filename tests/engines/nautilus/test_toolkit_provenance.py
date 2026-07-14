from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROVENANCE = ROOT / "docs/authority/strategy-toolkit-provenance.md"
INVENTORY = ROOT / "docs/authority/strategy-toolkit-inventory-v1.json"
EXTRACTION = ROOT / "docs/authority/strategy-toolkit-extraction-v1.json"
BASE_ROOT = ROOT / "packages/custos-strategy-toolkit/src/custos_toolkit"
NAUTILUS_ROOT = ROOT / "packages/custos-strategy-toolkit-nautilus/src/custos_toolkit_nautilus"


def test_private_vendor_license_is_packaged_under_the_private_namespace() -> None:
    license_path = NAUTILUS_ROOT / "_vendor/pandas_ta/LICENSE"

    assert license_path.is_file()
    assert "MIT License" in license_path.read_text(encoding="utf-8")


def test_provenance_names_all_authority_inputs_and_retired_aliases() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")

    assert INVENTORY.name in text
    assert EXTRACTION.name in text
    assert "scripts/check-toolkit-extraction.py" in text
    assert "sys.path" in text
    assert "pkg_resources" in text
    assert "top-level `pandas_ta`" in text


def test_inventory_money_paths_remain_decimal_based() -> None:
    money_paths = [BASE_ROOT / "risk/orders.py", BASE_ROOT / "position/sizer.py"]

    for path in money_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "Decimal" in imported_names, path.relative_to(ROOT)


def test_legacy_implementation_roots_are_absent() -> None:
    toolkit = ROOT / "src/custos/engines/nautilus/toolkit"

    assert not (toolkit / "shared").exists()
    assert not (toolkit / "vendor").exists()
    assert (toolkit / "__init__.py").is_file()


def test_extraction_records_only_declared_transformation_profiles() -> None:
    extraction = json.loads(EXTRACTION.read_text(encoding="utf-8"))

    assert {record["transformation_profile"] for record in extraction["files"]} <= {
        "byte_identical",
        "namespace_or_private_vendor_packaging",
    }
