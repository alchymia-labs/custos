from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/authority/strategy-toolkit-inventory-v1.json"
TOOLKIT = ROOT / "src/custos/engines/nautilus/toolkit"


def _source_paths() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in TOOLKIT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix in {".py", ".yaml"} or path.name == "LICENSE")
        and ("shared" in path.relative_to(TOOLKIT).parts or "vendor" in path.relative_to(TOOLKIT).parts)
    }


def test_inventory_covers_each_deterministic_source_once() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    recorded = [entry["legacy_path"] for entry in inventory["files"]]
    assert len(recorded) == len(set(recorded))
    assert set(recorded) == _source_paths()
    assert inventory["file_count"] == len(recorded)


def test_inventory_has_one_explicit_disposition_per_file() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    allowed = {
        "platform_neutral",
        "nautilus_specific",
        "private_vendor",
        "ps_owned_strategy",
        "ps_owned_hummingbot",
        "delete",
    }
    assert set(inventory["category_counts"]) == allowed
    assert sum(inventory["category_counts"].values()) == inventory["file_count"]
    assert inventory["legacy_aliases_must_retire"] == ["shared", "pandas_ta"]
