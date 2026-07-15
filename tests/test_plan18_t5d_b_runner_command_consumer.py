from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from custos.contracts import CrucibleRunnerDeploymentCommandV1
from custos.contracts import __all__ as public_contracts

ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "docs/authority/vendor/crucible-plan-89"
INDEX_PATH = ROOT / "docs/authority/crucible-runner-command-consumer-assets-v1.json"
RECEIPT_PATH = (
    ROOT / "docs/authority/receipts/custos-plan-18-task-5d-b-command-consumer-receipt.json"
)
PRODUCER_COMMIT = "51d23eba8aaefb30e936fc9fae1eac0e791164aa"
PUBLICATION_COMMIT = "06b2cbc0bafc0eda2b92fc2bc3f36ba1626abc3d"
PRODUCER_RECEIPT_SHA256 = "105ea501b83053421066b4053ec3583e4dd109560b0689bfeb856c2f8beec5d2"
NON_CURRENT_COMMITS = {
    "fe7be5119633c341f6e888a250a601d9db0d6e67",
    "56743f090ef3461f306d3937bfa8b054e6e7b2d8",
    "a20f7116fed35670264d3a0139974aa25daa2a26",
}
PRODUCER_ASSETS = {
    "docs/authority/schemas/crucible-runner-deployment-command-v1.schema.json": (
        PRODUCER_COMMIT,
        "5aecc9ca09b1b06204fd9f790ecfc56ad3bc10e72086f84168092beff69061da",
        5522,
    ),
    "docs/authority/schemas/crucible-runner-deployment-command-v1.schema.json.sha256": (
        PRODUCER_COMMIT,
        "f4bc19211678de8e01c35349c08cf0771bc5d99c4d5c6fac68d9e8b946673747",
        65,
    ),
    "docs/authority/golden/crucible-runner-deployment-command-v1.json": (
        PRODUCER_COMMIT,
        "7054351ccf625bb7696063c0deb9e15c22ed1022dbdc1ef6a7adc4e78fb8c73e",
        140382,
    ),
    "docs/authority/golden/crucible-runner-deployment-command-v1.json.sha256": (
        PRODUCER_COMMIT,
        "a9b3bb28795622fbf1a6afcd425c7f9c94f9a7accaa5945523d92a7023319b7e",
        65,
    ),
    "docs/authority/receipts/crucible-plan-89-runner-command-producer-v1.json": (
        PUBLICATION_COMMIT,
        PRODUCER_RECEIPT_SHA256,
        4059,
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compact(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _golden() -> dict[str, object]:
    return json.loads(
        (
            VENDOR_ROOT / "docs/authority/golden/crucible-runner-deployment-command-v1.json"
        ).read_text(encoding="utf-8")
    )


def _envelope_bytes(value: dict[str, object]) -> bytes:
    return _compact(value)


def _parse_fixture(fixture: dict[str, object]) -> CrucibleRunnerDeploymentCommandV1:
    return CrucibleRunnerDeploymentCommandV1.from_verified_signed_envelope(
        subject=str(fixture["subject"]),
        signed_envelope_bytes=_envelope_bytes(fixture["signed_envelope"]),
    )


def _mutated_fixture(
    mutate: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    fixture = copy.deepcopy(_golden())
    envelope = fixture["signed_envelope"]
    assert isinstance(envelope, dict)
    event = json.loads(_decode_base64url(str(envelope["event_bytes"])))
    mutate(event)
    envelope["event_bytes"] = _encode_base64url(_compact(event))
    return fixture


def _rust_struct_digest(value: dict[str, object], fields: tuple[str, ...]) -> str:
    ordered = {field: value[field] for field in fields}
    return hashlib.sha256(_compact(ordered)).hexdigest()


SIGNED_CLAIMS_FIELDS = (
    "producer_repository",
    "producer_commit",
    "workflow_identity",
    "source_date_epoch",
    "strategy_source_tree_sha256",
    "execution_abi_schema_sha256",
    "contract_asset_index_sha256",
    "toolkit_wheel_sha256",
    "toolkit_sbom_sha256",
    "build_lock_sha256",
    "zero_rewrite_semantic_diff_sha256",
    "zero_rewrite_characterization_sha256",
    "engine",
    "engine_version",
    "python_requires",
    "entry_point_group",
    "entry_point_name",
)
SIGSTORE_FIELDS = (
    "schema_version",
    "bundle_sha256",
    "statement_sha256",
    "certificate_sha256",
    "issuer",
    "workflow_identity",
    "rekor_log_id",
    "rekor_log_index",
    "rekor_integrated_time",
    "checkpoint_sha256",
    "certificate_chain_verified",
    "sct_verified",
    "dsse_signature_verified",
    "rekor_body_verified",
    "set_verified",
    "inclusion_proof_verified",
    "checkpoint_verified",
)
POLICY_FIELDS = (
    "schema_version",
    "policy_id",
    "policy_version",
    "policy_digest",
    "evaluated_at",
    "decision",
)
EVIDENCE_FIELDS = (
    "schema_version",
    "strategy_release_id",
    "artifact_ref_digest",
    "manifest_digest",
    "release_bom_digest",
    "statement_digest",
    "attestation_ref_digest",
    "bundle_sha256",
    "signed_producer_claims",
    "sigstore_proof",
    "local_policy_evaluation",
    "verified_at",
    "artifact_evidence_digest",
)
ACCEPTANCE_FIELDS = (
    "schema_version",
    "tenant_id",
    "strategy_release_id",
    "released_lifecycle_version",
    "artifact_evidence_digest",
    "snapshot_digest",
    "request_fingerprint",
    "outbox_event_id",
    "actor_id",
    "actor_assertion_jti",
    "correlation_id",
    "accepted_at",
    "receipt_digest",
)


def _reseal_evidence(command: dict[str, object]) -> None:
    evidence = command["artifact_evidence"]
    assert isinstance(evidence, dict)
    for field, fields in (
        ("signed_producer_claims", SIGNED_CLAIMS_FIELDS),
        ("sigstore_proof", SIGSTORE_FIELDS),
        ("local_policy_evaluation", POLICY_FIELDS),
    ):
        value = evidence[field]
        assert isinstance(value, dict)
        evidence[field] = {key: value[key] for key in fields}
    evidence["artifact_evidence_digest"] = ""
    evidence["artifact_evidence_digest"] = _rust_struct_digest(evidence, EVIDENCE_FIELDS)
    command["artifact_evidence_digest"] = evidence["artifact_evidence_digest"]
    acceptance = command["artifact_acceptance_receipt"]
    assert isinstance(acceptance, dict)
    acceptance["artifact_evidence_digest"] = evidence["artifact_evidence_digest"]
    _reseal_acceptance(acceptance)


def _reseal_acceptance(acceptance: dict[str, object]) -> None:
    acceptance["receipt_digest"] = ""
    acceptance["receipt_digest"] = _rust_struct_digest(acceptance, ACCEPTANCE_FIELDS)


def test_corrected_cr89_assets_are_byte_exact_and_supersede_old_slices() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    producer_receipt = json.loads(
        (
            VENDOR_ROOT / "docs/authority/receipts/crucible-plan-89-runner-command-producer-v1.json"
        ).read_text(encoding="utf-8")
    )

    expected_assets = []
    for source_path, (source_commit, digest, size_bytes) in sorted(PRODUCER_ASSETS.items()):
        vendored_path = VENDOR_ROOT / source_path
        assert vendored_path.stat().st_size == size_bytes
        assert _sha256(vendored_path) == digest
        expected_assets.append(
            {
                "source_path": source_path,
                "vendored_path": str(vendored_path.relative_to(ROOT)),
                "source_commit": source_commit,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )

    assert index["producer_authority"]["producer_assets"] == expected_assets
    assert producer_receipt["producer_commit"] == PRODUCER_COMMIT
    assert producer_receipt["supersession"]["status"] == "CURRENT"
    assert {
        entry["commit"] for entry in producer_receipt["supersession"]["supersedes"]
    } == NON_CURRENT_COMMITS
    assert all(
        entry["status"] == "NON_CURRENT" for entry in producer_receipt["supersession"]["supersedes"]
    )
    assert receipt["crucible_producer"]["contract_commit"] == PRODUCER_COMMIT
    assert receipt["crucible_producer"]["publication_commit"] == PUBLICATION_COMMIT
    assert receipt["crucible_producer"]["producer_receipt_sha256"] == PRODUCER_RECEIPT_SHA256


def test_public_consumer_accepts_golden_and_retains_exact_fingerprint_material() -> None:
    fixture = _golden()
    command = _parse_fixture(fixture)
    envelope = fixture["signed_envelope"]
    assert isinstance(envelope, dict)
    event_bytes = _decode_base64url(str(envelope["event_bytes"]))

    assert command.deployment_instance_id.hex == "80000000000040008000000000000008"
    assert command.deployment_spec_id.hex == "90000000000040008000000000000009"
    assert command.generation == 1
    assert command.artifact_ref.schema_version == 2
    assert command.release_bom["schema_version"] == "alephain.strategy-release-bom.v1"
    assert command.artifact_attestation_ref["schema_version"] == (
        "alephain.artifact-attestation-ref.v1"
    )
    assert command.artifact_evidence["artifact_evidence_digest"] == (
        command.artifact_evidence_digest
    )
    assert command.exact_signed_event_bytes == event_bytes
    assert command.producer_fingerprint == fixture["fingerprint"]
    assert command.verified_subject == fixture["subject"]
    assert public_contracts.count("CrucibleRunnerDeploymentCommandV1") == 1
    assert "RunnerDeploymentCommandV1" not in public_contracts


def test_signature_bytes_are_outside_the_frozen_fingerprint() -> None:
    fixture = _golden()
    first = _parse_fixture(fixture)
    changed = copy.deepcopy(fixture)
    envelope = changed["signed_envelope"]
    assert isinstance(envelope, dict)
    envelope["signature"] = _encode_base64url(bytes([0xA5]) * 64)
    second = _parse_fixture(changed)

    assert second.exact_signed_event_bytes == first.exact_signed_event_bytes
    assert second.producer_fingerprint == first.producer_fingerprint


@pytest.mark.parametrize(
    "field",
    [
        "release_bom_members",
        "trusted_root",
        "trust_policy",
        "issuer",
        "workflow_identity",
        "runner_cap_policy",
        "unknown_field",
    ],
)
def test_command_selected_authority_and_unknown_fields_are_rejected(field: str) -> None:
    fixture = _mutated_fixture(lambda event: event["payload"].__setitem__(field, "forbidden"))
    with pytest.raises(ValueError):
        _parse_fixture(fixture)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event["payload"].__setitem__("schema_version", 2),
        lambda event: event["payload"]["artifact_ref"].__setitem__("schema_version", 1),
        lambda event: event["payload"].__setitem__(
            "release_bom", event["payload"]["release_bom"]["members"]
        ),
        lambda event: event["payload"].pop("artifact_acceptance_receipt"),
        lambda event: event["payload"].pop("artifact_evidence"),
    ],
    ids=[
        "unknown-version",
        "v1-artifact-ref",
        "bom-array",
        "missing-acceptance",
        "missing-evidence",
    ],
)
def test_legacy_shortcuts_missing_evidence_and_unknown_versions_are_rejected(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    with pytest.raises(ValueError):
        _parse_fixture(_mutated_fixture(mutate))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("deployment_spec_digest", "F" * 64),
        ("effective_config_digest", "f" * 64),
        ("artifact_ref_digest", "f" * 64),
        ("release_bom_digest", "f" * 64),
        ("artifact_evidence_digest", "f" * 64),
    ],
)
def test_digest_mismatches_are_rejected(field: str, value: str) -> None:
    fixture = _mutated_fixture(lambda event: event["payload"].__setitem__(field, value))
    with pytest.raises(ValueError):
        _parse_fixture(fixture)


@pytest.mark.parametrize(
    "field",
    [
        "artifact_ref_digest",
        "manifest_digest",
        "release_bom_digest",
        "statement_digest",
        "attestation_ref_digest",
        "bundle_sha256",
    ],
)
def test_every_artifact_evidence_component_is_cross_bound(field: str) -> None:
    def mutate(event: dict[str, object]) -> None:
        command = event["payload"]
        command["artifact_evidence"][field] = "f" * 64
        _reseal_evidence(command)

    with pytest.raises(ValueError):
        _parse_fixture(_mutated_fixture(mutate))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence["sigstore_proof"].__setitem__("checkpoint_verified", False),
        lambda evidence: evidence["sigstore_proof"].__setitem__(
            "workflow_identity", "https://example.invalid/other-workflow"
        ),
        lambda evidence: evidence["local_policy_evaluation"].__setitem__("decision", "rejected"),
        lambda evidence: evidence["local_policy_evaluation"].__setitem__("policy_version", 0),
    ],
    ids=["proof-false", "workflow", "policy-decision", "policy-version"],
)
def test_resealed_artifact_evidence_semantics_remain_fail_closed(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    def mutate_event(event: dict[str, object]) -> None:
        command = event["payload"]
        mutate(command["artifact_evidence"])
        _reseal_evidence(command)

    with pytest.raises(ValueError):
        _parse_fixture(_mutated_fixture(mutate_event))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt.__setitem__("released_lifecycle_version", 0),
        lambda receipt: receipt.__setitem__("actor_id", "00000000-0000-0000-0000-000000000000"),
        lambda receipt: receipt.__setitem__("snapshot_digest", "not-a-digest"),
        lambda receipt: receipt.__setitem__("tenant_id", "other-tenant"),
        lambda receipt: receipt.__setitem__(
            "strategy_release_id", "c0000000-0000-4000-8000-00000000000c"
        ),
    ],
    ids=["zero-lifecycle", "nil-actor", "invalid-snapshot", "tenant", "release"],
)
def test_acceptance_receipt_semantics_are_fail_closed(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    def mutate_event(event: dict[str, object]) -> None:
        receipt = event["payload"]["artifact_acceptance_receipt"]
        mutate(receipt)
        _reseal_acceptance(receipt)

    with pytest.raises(ValueError):
        _parse_fixture(_mutated_fixture(mutate_event))


def test_acceptance_receipt_self_digest_is_required() -> None:
    fixture = _mutated_fixture(
        lambda event: event["payload"]["artifact_acceptance_receipt"].__setitem__(
            "receipt_digest", "f" * 64
        )
    )
    with pytest.raises(ValueError):
        _parse_fixture(fixture)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event.__setitem__("aggregate_id", event["payload"]["deployment_spec_id"]),
        lambda event: event.__setitem__("aggregate_version", 2),
        lambda event: event["event_plane"].__setitem__("trading_mode", "live"),
        lambda event: event.__setitem__("tenant_id", "other-tenant"),
        lambda event: event.__setitem__("event_type", "RunnerDeploymentCommandV1.invalid"),
    ],
    ids=["instance", "generation", "mode", "tenant", "event-type"],
)
def test_event_target_cross_bindings_are_rejected(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    with pytest.raises(ValueError):
        _parse_fixture(_mutated_fixture(mutate))


def test_non_exact_event_bytes_and_envelope_downgrades_are_rejected() -> None:
    fixture = _golden()
    envelope = fixture["signed_envelope"]
    assert isinstance(envelope, dict)
    event = json.loads(_decode_base64url(str(envelope["event_bytes"])))
    envelope["event_bytes"] = _encode_base64url(json.dumps(event, indent=2).encode())
    with pytest.raises(ValueError):
        _parse_fixture(fixture)

    for field, replacement in (
        ("schema_version", 1),
        ("signature_profile", "caller-selected-profile"),
        ("event_encoding", "application/json"),
        ("signature", _encode_base64url(b"short")),
    ):
        invalid = _golden()
        invalid_envelope = invalid["signed_envelope"]
        assert isinstance(invalid_envelope, dict)
        invalid_envelope[field] = replacement
        with pytest.raises(ValueError):
            _parse_fixture(invalid)


def test_authority_marks_one_contract_consumer_without_runtime_or_schema_ownership() -> None:
    manifest = json.loads((ROOT / "authority-manifest.json").read_text(encoding="utf-8"))
    ecosystem = json.loads(
        (ROOT / "docs/authority/ecosystem-authority.json").read_text(encoding="utf-8")
    )
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

    assert index["status"] == "READY_COMMAND_CONSUMER_CONTRACT_ONLY"
    assert index["custos_publishes_command_schema"] is False
    assert index["exact_signed_event_bytes_retained"] is True
    assert index["command_contract_consumer_ready"] is True
    assert index["runtime_ready"] is False
    assert index["production_ready"] is False
    assert receipt["receipt_status"] == "READY_COMMAND_CONSUMER_CONTRACT_ONLY"
    assert receipt["plan_18_task_5d_b_stop"] is True
    assert receipt["plan_19_task_2_stop"] is True
    assert receipt["runtime_ready"] is False
    assert receipt["production_ready"] is False
    assert not any(
        asset["path"].startswith("docs/gateway-contract") for asset in index["consumer_assets"]
    )

    entries = manifest["authority_documents"]
    assert any(entry["role"] == "crucible_runner_command_consumer_asset_index" for entry in entries)
    assert any(entry["role"] == "plan_18_task_5d_b_command_consumer_receipt" for entry in entries)
    authority = ecosystem["strategy_execution_contract"]
    assert authority["task_5d_b_status"] == "READY_COMMAND_CONSUMER_CONTRACT_ONLY"
    assert authority["task_5d_b_runtime_ready"] is False
    assert authority["production_ready"] is False
