from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURRENT_CANONICAL_SOURCE = Path(
    "packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py"
)
RECEIPT_PATH = Path("docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json")
VENDORED_PATHS = {
    "crucible_rust_plan_88": Path(
        "docs/authority/receipts/vendor/crucible-plan-88-custos-task-2-requirements-review.json"
    ),
    "philosophers_stone_plan_54": Path(
        "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-requirements-review.json"
    ),
}


def _load_checker() -> ModuleType:
    path = ROOT / "scripts/check-authority-docs.py"
    spec = importlib.util.spec_from_file_location("check_authority_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _copy(root: Path, relative: Path) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, destination)


def _write_json(path: Path, value: object) -> bytes:
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _ready_tree(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    receipt = json.loads((ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))
    receipt["receipt_status"] = "READY"
    receipt["handoff_ready"] = True
    receipt["producer"]["candidate_commit"] = "f" * 40
    receipt["producer"]["commit"] = "f" * 40
    receipt["producer"]["worktree_clean"] = True
    receipt["verification"] = {
        "command": "make check-authority",
        "status": "PASS",
        "executed_at": "2026-07-15T12:00:00Z",
        "environment": "clean test checkout",
    }
    historical_source = tmp_path / Path(receipt["producer"]["source"])
    historical_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / CURRENT_CANONICAL_SOURCE, historical_source)
    _copy(tmp_path, Path(receipt["contract_asset_index"]["path"]))
    profiles = deepcopy(CHECKER.REVIEW_PROFILES)
    for index, (reviewer, path) in enumerate(VENDORED_PATHS.items()):
        _copy(tmp_path, path)
        vendored_path = tmp_path / path
        review = json.loads(vendored_path.read_text(encoding="utf-8"))
        if reviewer == "crucible_rust_plan_88":
            producer = review["producer_snapshot"]
        else:
            producer = review["custos_producer_pin"]
        producer["commit"] = receipt["producer"]["candidate_commit"]
        producer["source"] = {
            "path": receipt["producer"]["source"],
            "sha256": receipt["producer"]["source_sha256"],
        }
        producer["contract_asset_index"] = dict(receipt["contract_asset_index"])
        raw = _write_json(vendored_path, review)
        synthetic_review_commit = ("c" if index == 0 else "d") * 40
        slot = receipt["requirements_reviews"][reviewer]
        slot["status"] = "ACCEPTED_REQUIREMENTS_REVIEW"
        slot.pop("stale_for_current_candidate", None)
        slot.pop("stale_reason", None)
        slot["receipt"]["source_commit"] = synthetic_review_commit
        slot["receipt"]["sha256"] = hashlib.sha256(raw).hexdigest()
        profiles[reviewer]["source_commit"] = synthetic_review_commit
        profiles[reviewer]["sha256"] = slot["receipt"]["sha256"]
    _write_json(tmp_path / RECEIPT_PATH, receipt)
    return receipt, profiles


def _write_receipt(tmp_path: Path, receipt: dict[str, object]) -> None:
    _write_json(tmp_path / RECEIPT_PATH, receipt)


def _errors(tmp_path: Path, profiles: dict[str, dict[str, object]]) -> list[str]:
    errors: list[str] = []
    CHECKER.verify_plan_18_task_2_receipt(
        errors,
        root=tmp_path,
        review_profiles=profiles,
    )
    return errors


def _mutate_review(
    tmp_path: Path,
    receipt: dict[str, object],
    reviewer: str,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    vendored_path = tmp_path / VENDORED_PATHS[reviewer]
    review = json.loads(vendored_path.read_text(encoding="utf-8"))
    current: object = review
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement
    raw = _write_json(vendored_path, review)
    receipt["requirements_reviews"][reviewer]["receipt"]["sha256"] = hashlib.sha256(raw).hexdigest()
    _write_receipt(tmp_path, receipt)


def test_ready_receipt_accepts_exact_vendored_requirements_reviews(tmp_path: Path) -> None:
    _, profiles = _ready_tree(tmp_path)

    assert _errors(tmp_path, profiles) == []


def test_ready_receipt_rejects_arbitrary_nonempty_review_evidence(tmp_path: Path) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    receipt["requirements_reviews"]["crucible_rust_plan_88"]["receipt"] = "trusted"
    _write_receipt(tmp_path, receipt)

    assert any("structured receipt object" in error for error in _errors(tmp_path, profiles))


def test_ready_receipt_rejects_missing_vendored_review(tmp_path: Path) -> None:
    _, profiles = _ready_tree(tmp_path)
    (tmp_path / VENDORED_PATHS["crucible_rust_plan_88"]).unlink()

    assert any("missing crucible_rust_plan_88" in error for error in _errors(tmp_path, profiles))


def test_ready_receipt_rejects_vendored_review_path_escape(tmp_path: Path) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    evidence = receipt["requirements_reviews"]["crucible_rust_plan_88"]["receipt"]
    evidence["vendored_path"] = "../escaped-review.json"
    _write_receipt(tmp_path, receipt)

    assert any("escapes the repository root" in error for error in _errors(tmp_path, profiles))


def test_ready_receipt_rejects_review_status_mismatch(tmp_path: Path) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    receipt["requirements_reviews"]["philosophers_stone_plan_54"]["status"] = "ACCEPTED"
    _write_receipt(tmp_path, receipt)

    assert any("decision is not accepted" in error for error in _errors(tmp_path, profiles))


def test_ready_receipt_rejects_vendored_byte_digest_substitution(tmp_path: Path) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    receipt["requirements_reviews"]["crucible_rust_plan_88"]["receipt"]["sha256"] = "0" * 64
    _write_receipt(tmp_path, receipt)

    errors = _errors(tmp_path, profiles)
    assert any("evidence sha256 differs" in error for error in errors)
    assert any("byte digest differs" in error for error in errors)


@pytest.mark.parametrize(
    ("path", "replacement", "expected_error"),
    [
        (("producer_snapshot", "commit"), "0" * 40, "reviewed producer commit differs"),
        (
            ("producer_snapshot", "source", "sha256"),
            "0" * 64,
            "reviewed producer source differs",
        ),
        (
            ("producer_snapshot", "contract_asset_index", "sha256"),
            "0" * 64,
            "reviewed asset index differs",
        ),
        (
            ("contract_requirements", "canonicalization", "identifier"),
            "sha256-substituted-v1",
            "reviewed canonicalization differs",
        ),
        (
            ("contract_requirements", "execution_abi"),
            "alephain.strategy_runtime.v2",
            "reviewed execution ABI differs",
        ),
        (
            ("contract_requirements", "entry_point", "group"),
            "alephain.strategy_runtime.v2",
            "reviewed entry-point group differs",
        ),
        (
            ("reviewed_assets", 0, "sha256"),
            "0" * 64,
            "reviewed schema asset digest set differs",
        ),
    ],
)
def test_ready_receipt_rejects_semantic_review_substitution(
    tmp_path: Path,
    path: tuple[str | int, ...],
    replacement: object,
    expected_error: str,
) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    _mutate_review(tmp_path, receipt, "crucible_rust_plan_88", path, replacement)

    assert any(expected_error in error for error in _errors(tmp_path, profiles))


def test_ready_receipt_rejects_missing_reviewed_schema_asset(tmp_path: Path) -> None:
    receipt, profiles = _ready_tree(tmp_path)
    vendored_path = tmp_path / VENDORED_PATHS["crucible_rust_plan_88"]
    review = json.loads(vendored_path.read_text(encoding="utf-8"))
    review["reviewed_assets"].pop()
    raw = _write_json(vendored_path, review)
    receipt["requirements_reviews"]["crucible_rust_plan_88"]["receipt"]["sha256"] = hashlib.sha256(
        raw
    ).hexdigest()
    _write_receipt(tmp_path, receipt)

    assert any("schema asset digest set differs" in error for error in _errors(tmp_path, profiles))
