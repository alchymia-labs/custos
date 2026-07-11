"""Plan 12 T7 contract: gateway-contract v1 additive-only backward-compat.

The four JSON Schemas under ``docs/gateway-contract/v1/`` freeze the wire
shape of the CustosGateway payloads. Additive-only rule (Plan 12 DP8 +
C1 fix) has two precise conditions:

1. ``current.required ⊆ golden.required`` — adding a new required field is
   a MAJOR breaking change (an old producer wouldn't emit it).
2. Every property that existed in ``golden.properties`` still exists in
   ``current.properties`` — removing a property is a MAJOR breaking
   change.

Three negative tests (Plan 12 BLK-5) exercise the assertion form itself:
adding an optional field must pass; adding a new required field must
fail; removing a property must fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "docs" / "gateway-contract" / "v1"
GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "gateway_contract_v1_golden"
SCHEMAS = ("enrollment", "deployment_status", "telemetry_snapshot", "heartbeat")


def _load(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def test_schemas_present():
    for name in SCHEMAS:
        assert (CONTRACT_DIR / f"{name}.schema.json").exists(), (
            f"missing docs/gateway-contract/v1/{name}.schema.json"
        )


def test_goldens_present():
    for name in SCHEMAS:
        assert (GOLDEN_DIR / f"{name}.schema.json").exists(), (
            f"missing golden fixture for {name}; freeze the current schema"
            f" into tests/fixtures/gateway_contract_v1_golden/{name}.schema.json"
        )


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_backward_compat_vs_golden(name: str):
    current = _load(CONTRACT_DIR / f"{name}.schema.json")
    golden = _load(GOLDEN_DIR / f"{name}.schema.json")
    cur_req = set(current.get("required", []))
    gold_req = set(golden.get("required", []))
    added_required = cur_req - gold_req
    assert not added_required, (
        f"{name}: new required field(s) {sorted(added_required)}; adding a "
        f"required field is a MAJOR breaking change (a producer on the older"
        f" version wouldn't emit it). Route this via docs/gateway-contract/v2/"
        f" or refresh the golden after a MAJOR bump."
    )
    cur_props = set(current.get("properties", {}))
    gold_props = set(golden.get("properties", {}))
    removed_props = gold_props - cur_props
    assert not removed_props, (
        f"{name}: removed property/ies {sorted(removed_props)}; removing a "
        f"property is a MAJOR breaking change. Deprecate first (see LTS "
        f"deprecation grace), then remove after ≥ 1 minor line."
    )


# --- BLK-5 negative tests: the assertion form itself must catch these ---------


def test_additive_optional_field_passes():
    golden = {"required": ["a"], "properties": {"a": {"type": "string"}}}
    current = {
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
    }
    assert set(current["required"]) <= set(golden["required"])
    for key in golden["properties"]:
        assert key in current["properties"]


def test_new_required_field_blocked():
    golden = {"required": ["a"], "properties": {"a": {"type": "string"}}}
    current = {
        "required": ["a", "b"],
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
    }
    with pytest.raises(AssertionError):
        assert set(current["required"]) <= set(golden["required"])


def test_removed_property_blocked():
    golden = {
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "foo": {"type": "string"}},
    }
    current = {"required": ["a"], "properties": {"a": {"type": "string"}}}
    with pytest.raises(AssertionError):
        for key in golden["properties"]:
            assert key in current["properties"], f"removed property: {key}"
