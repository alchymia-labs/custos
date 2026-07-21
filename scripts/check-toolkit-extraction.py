#!/usr/bin/env python3
"""Verify the inventory-backed strategy-toolkit extraction is zero-rewrite."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs/authority/strategy-toolkit-inventory-v1.json"
EXTRACTION_PATH = ROOT / "docs/authority/strategy-toolkit-extraction-v1.json"
EXTRACTION_RECEIPT_PATH = (
    ROOT / "docs/authority/receipts/custos-plan-18-task-4-extraction-receipt.json"
)
BASE_SOURCE_ROOT = ROOT / "packages/custos-strategy-toolkit/src"
NAUTILUS_SOURCE_ROOT = ROOT / "packages/custos-strategy-toolkit-nautilus/src"

_PANDAS_TA_DISTRIBUTION_BLOCK = """from pkg_resources import get_distribution, DistributionNotFound
import os.path


_dist = get_distribution("pandas_ta")
try:
    # Normalize case for Windows systems
    dist_loc = os.path.normcase(_dist.location)
    here = os.path.normcase(__file__)
    if not here.startswith(os.path.join(dist_loc, "pandas_ta")):
        # not installed, but there is another version that *is*
        raise DistributionNotFound
except DistributionNotFound:
    __version__ = "Please install this project with setup.py"

version = __version__ = _dist.version
"""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def target_path(entry: dict[str, Any]) -> Path:
    target = Path(entry["target_path"])
    if target.parts[0] == "custos_toolkit":
        return BASE_SOURCE_ROOT / target
    if target.parts[0] == "custos_toolkit_nautilus":
        return NAUTILUS_SOURCE_ROOT / target
    raise ValueError(f"unsupported toolkit namespace: {target}")


def transform_source(legacy_path: str, source: bytes) -> bytes:
    """Apply only import-namespace and private-vendor packaging adaptations."""
    if not legacy_path.endswith(".py"):
        return source

    text = source.decode("utf-8")
    text = text.replace("shared.nautilus", "custos_toolkit_nautilus.adapter")
    text = re.sub(r"(?<![\w.])shared\.", "custos_toolkit.", text)
    text = re.sub(
        r"(?m)^(\s*from\s+)shared(\s+import\s+)",
        r"\1custos_toolkit\2",
        text,
    )
    text = text.replace("from pandas_ta", "from custos_toolkit_nautilus._vendor.pandas_ta")
    text = re.sub(
        r"(?m)^(\s*)import pandas_ta as ([A-Za-z_][A-Za-z0-9_]*)(\s*(?:#.*)?)$",
        r"\1from custos_toolkit_nautilus._vendor import pandas_ta as \2\3",
        text,
    )
    text = re.sub(
        r"(?m)^(\s*)import pandas_ta(\s*(?:#.*)?)$",
        r"\1from custos_toolkit_nautilus._vendor import pandas_ta\2",
        text,
    )

    if legacy_path.endswith("vendor/pandas_ta/__init__.py"):
        if _PANDAS_TA_DISTRIBUTION_BLOCK not in text:
            raise ValueError("pandas_ta distribution metadata block drifted")
        text = text.replace(
            _PANDAS_TA_DISTRIBUTION_BLOCK,
            '__version__ = version = "0.0.0+vendored"\n',
        )

    return text.encode("utf-8")


def _git_blob(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _forbidden_imports(path: Path, content: bytes) -> list[str]:
    if path.suffix != ".py":
        return []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(content.decode("utf-8"), filename=str(path))
    violations: list[str] = []
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
                f"{path.relative_to(ROOT)}:{node.lineno}:{','.join(sorted(forbidden))}"
            )
    return violations


def check() -> list[str]:
    errors: list[str] = []
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    extraction = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    receipt = json.loads(EXTRACTION_RECEIPT_PATH.read_text(encoding="utf-8"))
    entries = inventory["files"]
    records = extraction["files"]
    source_commit = extraction["source_commit"]
    implementation_commit = receipt["implementation"]["implementation_commit"]

    if inventory["file_count"] != 241 or len(entries) != 241:
        errors.append("frozen inventory must contain exactly 241 files")
    if len(records) != len(entries):
        errors.append("extraction manifest cardinality differs from inventory")
        return errors

    records_by_legacy = {record["legacy_path"]: record for record in records}
    if len(records_by_legacy) != len(records):
        errors.append("extraction manifest contains duplicate legacy paths")
        return errors

    for entry in entries:
        legacy_path = entry["legacy_path"]
        target = target_path(entry)
        record = records_by_legacy.get(legacy_path)
        if record is None:
            errors.append(f"missing extraction record: {legacy_path}")
            continue
        if record["target_path"] != entry["target_path"]:
            errors.append(f"target mapping drift: {legacy_path}")
        if (ROOT / legacy_path).exists():
            errors.append(f"legacy implementation still exists: {legacy_path}")
        source = _git_blob(source_commit, legacy_path)
        target_content = _git_blob(implementation_commit, str(target.relative_to(ROOT)))
        expected = transform_source(legacy_path, source)
        if _sha256(source) != record["legacy_sha256"]:
            errors.append(f"legacy digest drift: {legacy_path}")
        if _sha256(target_content) != record["target_sha256"]:
            errors.append(f"target digest drift: {entry['target_path']}")
        if target_content != expected:
            errors.append(f"non-zero-rewrite extraction: {entry['target_path']}")
        errors.extend(_forbidden_imports(target, target_content))

    return errors


def main() -> int:
    try:
        errors = check()
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"toolkit extraction check failed: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("strategy toolkit extraction: verified historical T4 snapshot (241/241, zero-rewrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
