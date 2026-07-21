from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from custos_toolkit.contracts.strategy_execution import (
    StrategyArtifactPreImportVerificationReceiptV1,
)
from pydantic import ValidationError as PydanticValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "docs/gateway-contract/v1/strategy_artifact_pre_import_verification_receipt_v1.schema.json"
)
GOLDEN = ROOT / "docs/authority/strategy-artifact-pre-import-verification-v1.golden.json"
NEGATIVE = ROOT / "docs/authority/strategy-artifact-pre-import-verification-v1.negative.json"
INDEX = ROOT / "docs/authority/strategy-contract-assets-v1.json"
RECEIPT = ROOT / "docs/authority/receipts/custos-plan-18-strategy-contract-v1-receipt.json"
CRUCIBLE_RECEIPT = (
    ROOT
    / "docs/authority/receipts/vendor/"
    "crucible-plan-88-v1-contract-consumer-receipt.json"
)


def _validate(document: dict[str, object]) -> None:
    StrategyArtifactPreImportVerificationReceiptV1.model_validate(document)


def _apply_mutation(document: dict[str, object], mutation: dict[str, object]) -> None:
    path = mutation["path"]
    assert isinstance(path, list) and path
    target: object = document
    for segment in path[:-1]:
        assert isinstance(target, dict)
        target = target[segment]
    assert isinstance(target, dict)
    key = path[-1]
    assert isinstance(key, str)
    if mutation["operation"] == "remove":
        del target[key]
    else:
        target[key] = mutation["value"]


def test_schema_golden_and_index_are_the_same_v1_contract() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    assert schema["title"] == "StrategyArtifactPreImportVerificationReceiptV1"
    assert schema["properties"]["schema_version"]["const"] == 1
    _validate(golden["receipt"])
    receipt_contract = index["current_contracts"]["pre_import_verification_receipt"]
    artifact_ref_contract = index["current_contracts"]["strategy_artifact_ref"]
    assert receipt_contract["type"] == "StrategyArtifactPreImportVerificationReceiptV1"
    assert receipt_contract["schema_path"] == str(SCHEMA.relative_to(ROOT))
    assert artifact_ref_contract["type"] == "StrategyArtifactRefV1"
    assert index["status"] == "CANONICAL_V1_CONTRACT_ASSETS_PUBLISHED"
    assert "consumer_receipts" not in index
    assert "runtime_ready" not in index
    crucible_receipt = json.loads(CRUCIBLE_RECEIPT.read_text(encoding="utf-8"))
    assert crucible_receipt["producers"]["custos"]["commit"] == (
        "8c4454f35c5189063bad1516d77e260f034d3da7"
    )
    assert crucible_receipt["runtime_ready"] is False
    assert crucible_receipt["production_ready"] is False


def test_all_published_negative_cases_fail_closed() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["receipt"]
    negatives = json.loads(NEGATIVE.read_text(encoding="utf-8"))

    assert negatives["cases"]
    for case in negatives["cases"]:
        invalid = copy.deepcopy(golden)
        _apply_mutation(invalid, case["mutation"])
        with pytest.raises((PydanticValidationError, TypeError, ValueError)):
            _validate(invalid)


def test_contract_receipt_stays_pending_until_both_consumers_pin_v1() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    assert receipt["status"] == "CANONICAL_V1_PENDING_CONSUMER_RECEIPTS"
    assert receipt["contract_consumer_ready"] is False
    assert receipt["command_consumer_ready"] is False
    assert receipt["runtime_ready"] is False
    assert receipt["production_ready"] is False
    assert receipt["consumers"]["philosophers_stone"]["receipt"] is None
    crucible_pin = receipt["consumers"]["crucible_rust"]["receipt"]
    assert crucible_pin["commit"] == (
        "43c9f14bf9fb9b66fd65b368db95ff8cd7083be5"
    )
    assert crucible_pin["sha256"] == hashlib.sha256(CRUCIBLE_RECEIPT.read_bytes()).hexdigest()
