"""Strict consumer for the Crucible-owned runner deployment command."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from custos_toolkit.contracts.strategy_execution import (
    StrategyArtifactRefV2,
    canonical_json_bytes,
    canonical_json_digest,
    canonical_model_digest,
)
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StringConstraints, model_validator

__all__ = ["CrucibleRunnerDeploymentCommandV1"]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MEMBER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_ENTRY_POINT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

_SIGNATURE_PROFILE = "crucible-domain-event-v2-exact-bytes"
_EVENT_ENCODING = "application/json;base64url"
_SUBJECT_PREFIX = "crucible_rust.domain"
_EVENT_TYPE_PREFIX = "RunnerDeploymentCommandV1"
_FINGERPRINT_DOMAIN = b"CRUCIBLE-RUNNER-DEPLOYMENT-COMMAND-FINGERPRINT-V1\0"

_COMMAND_FIELDS = (
    "schema_version",
    "tenant_id",
    "trading_mode",
    "runner_id",
    "deployment_instance_id",
    "deployment_spec_id",
    "deployment_spec_digest",
    "generation",
    "lifecycle_state",
    "strategy_release_id",
    "effective_config",
    "effective_config_digest",
    "artifact_ref",
    "artifact_ref_canonical_json",
    "artifact_ref_digest",
    "release_bom",
    "release_bom_canonical_json",
    "release_bom_digest",
    "artifact_attestation_ref",
    "artifact_evidence",
    "artifact_acceptance_receipt",
    "artifact_evidence_digest",
)
_EVENT_FIELDS = (
    "schema_version",
    "event_id",
    "tenant_id",
    "event_plane",
    "bounded_context",
    "aggregate_type",
    "aggregate_id",
    "aggregate_version",
    "event_type",
    "payload",
    "correlation_id",
    "actor_assertion_jti",
    "occurred_at",
)
_ENVELOPE_FIELDS = (
    "schema_version",
    "signature_profile",
    "event_encoding",
    "event_bytes",
    "signature_key_id",
    "signature",
)
_BOM_FIELDS = (
    "schema_version",
    "canonicalization",
    "producer_repository",
    "producer_commit",
    "strategy_coordinate",
    "engine",
    "engine_version",
    "python_requires",
    "entry_point_group",
    "entry_point_name",
    "execution_abi_schema_coordinate",
    "execution_abi_schema_sha256",
    "execution_abi_golden_coordinate",
    "execution_abi_golden_sha256",
    "contract_asset_index_coordinate",
    "contract_asset_index_sha256",
    "toolkit_coordinate",
    "toolkit_wheel_sha256",
    "toolkit_sbom_sha256",
    "strategy_source_commit",
    "strategy_source_tree_sha256",
    "strategy_artifact_coordinate",
    "strategy_artifact_sha256",
    "strategy_manifest_sha256",
    "build_lock_sha256",
    "zero_rewrite_semantic_diff_sha256",
    "zero_rewrite_characterization_sha256",
    "members",
)
_BOM_MEMBER_FIELDS = ("role", "coordinate", "name", "media_type", "size_bytes", "sha256")
_BOM_ROLES = {
    "base_contracts_wheel",
    "nautilus_wheel",
    "strategy_wheel",
    "strategy_manifest",
    "runtime_artifact",
    "attestation_bundle",
    "sbom",
    "contract_schema",
    "source_tree",
}
_REQUIRED_SINGLETON_ROLES = {
    "base_contracts_wheel",
    "nautilus_wheel",
    "strategy_wheel",
    "strategy_manifest",
    "sbom",
    "contract_schema",
    "source_tree",
}
_ATTESTATION_REF_FIELDS = (
    "schema_version",
    "statement_coordinate",
    "statement_sha256",
    "bundle_coordinate",
    "bundle_sha256",
    "payload_type",
    "predicate_type",
)
_SIGNED_CLAIMS_FIELDS = (
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
_SIGSTORE_FIELDS = (
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
_POLICY_FIELDS = (
    "schema_version",
    "policy_id",
    "policy_version",
    "policy_digest",
    "evaluated_at",
    "decision",
)
_EVIDENCE_FIELDS = (
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
_ACCEPTANCE_FIELDS = (
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

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
TenantId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class CrucibleRunnerDeploymentCommandV1(BaseModel):
    """The sole Custos consumer model for the CR89 command contract.

    ``from_verified_signed_envelope`` validates the closed envelope and exact
    event bytes after the caller has established cryptographic trust. This
    contract-only slice does not select roots or verify signatures itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    tenant_id: TenantId
    trading_mode: Literal["sandbox", "testnet", "live"]
    runner_id: Annotated[UUID, Field(strict=False)]
    deployment_instance_id: Annotated[UUID, Field(strict=False)]
    deployment_spec_id: Annotated[UUID, Field(strict=False)]
    deployment_spec_digest: Sha256Hex
    generation: int = Field(strict=True, ge=1)
    lifecycle_state: Literal["running", "paused", "stopped", "archived"]
    strategy_release_id: Annotated[UUID, Field(strict=False)]
    effective_config: dict[str, object]
    effective_config_digest: Sha256Hex
    artifact_ref: StrategyArtifactRefV2
    artifact_ref_canonical_json: str = Field(min_length=2)
    artifact_ref_digest: Sha256Hex
    release_bom: dict[str, object]
    release_bom_canonical_json: str = Field(min_length=2)
    release_bom_digest: Sha256Hex
    artifact_attestation_ref: dict[str, object]
    artifact_evidence: dict[str, object]
    artifact_acceptance_receipt: dict[str, object]
    artifact_evidence_digest: Sha256Hex

    _exact_signed_event_bytes: bytes = PrivateAttr(default=b"")
    _verified_subject: str = PrivateAttr(default="")
    _producer_fingerprint: str = PrivateAttr(default="")

    @property
    def exact_signed_event_bytes(self) -> bytes:
        """Return the immutable bytes signed by Crucible, excluding signature bytes."""

        return self._exact_signed_event_bytes

    @property
    def verified_subject(self) -> str:
        return self._verified_subject

    @property
    def producer_fingerprint(self) -> str:
        return self._producer_fingerprint

    @classmethod
    def from_verified_signed_envelope(
        cls,
        *,
        subject: str,
        signed_envelope_bytes: bytes,
    ) -> Self:
        """Parse CR89 bytes whose Ed25519 signature was verified by the caller."""

        envelope = _strict_json_object(signed_envelope_bytes, "signed_envelope")
        _require_exact_keys(envelope, _ENVELOPE_FIELDS, "signed_envelope")
        if envelope["schema_version"] != 2:
            raise ValueError("signed envelope schema_version must be exactly 2")
        if envelope["signature_profile"] != _SIGNATURE_PROFILE:
            raise ValueError("signed envelope signature_profile differs")
        if envelope["event_encoding"] != _EVENT_ENCODING:
            raise ValueError("signed envelope event_encoding differs")
        key_id = envelope["signature_key_id"]
        if not isinstance(key_id, str) or not _KEY_ID_PATTERN.fullmatch(key_id):
            raise ValueError("signed envelope signature_key_id is invalid")
        event_bytes = _decode_base64url(envelope["event_bytes"], "signed_envelope.event_bytes")
        signature = _decode_base64url(envelope["signature"], "signed_envelope.signature")
        if len(signature) != 64:
            raise ValueError("signed envelope signature must be exactly 64 bytes")

        event = _strict_json_object(event_bytes, "event_document")
        _require_exact_keys(event, _EVENT_FIELDS, "event_document", ordered=True)
        if _json_bytes_preserving_order(event) != event_bytes:
            raise ValueError("event document is not exact compact JSON")
        if event["schema_version"] != 2:
            raise ValueError("event schema_version must be exactly 2")
        for field in ("event_id", "correlation_id", "actor_assertion_jti"):
            _require_canonical_uuid(event[field], f"event.{field}")
        _require_timestamp(event["occurred_at"], "event.occurred_at")

        event_plane = event["event_plane"]
        if not isinstance(event_plane, dict):
            raise ValueError("event_plane must be an object")
        _require_exact_keys(event_plane, ("kind", "trading_mode"), "event_plane", ordered=True)
        if event_plane["kind"] != "mode":
            raise ValueError("event_plane.kind must be mode")

        payload = event["payload"]
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        _require_exact_keys(payload, _COMMAND_FIELDS, "command", ordered=True)
        for field in (
            "runner_id",
            "deployment_instance_id",
            "deployment_spec_id",
            "strategy_release_id",
        ):
            _require_canonical_uuid(payload[field], f"command.{field}")
        command = cls.model_validate(payload)

        expected_event_type = (
            f"{_EVENT_TYPE_PREFIX}.{command.runner_id}.{command.deployment_instance_id}"
        )
        expected_subject = (
            f"{_SUBJECT_PREFIX}.{command.tenant_id}.{command.trading_mode}.deployment."
            f"{expected_event_type}"
        )
        expected_plane = {"kind": "mode", "trading_mode": command.trading_mode}
        if (
            event["tenant_id"] != command.tenant_id
            or event_plane != expected_plane
            or event["bounded_context"] != "deployment"
            or event["aggregate_type"] != "deployment_instance"
            or event["aggregate_id"] != str(command.deployment_instance_id)
            or event["aggregate_version"] != command.generation
            or event["event_type"] != expected_event_type
        ):
            raise ValueError("event target differs from command tenant/mode/instance/generation")
        if subject != expected_subject:
            raise ValueError("NATS subject differs from the derived CR89 subject")

        fingerprint = hashlib.sha256(_framed(_FINGERPRINT_DOMAIN, subject, event_bytes)).hexdigest()
        object.__setattr__(command, "_exact_signed_event_bytes", event_bytes)
        object.__setattr__(command, "_verified_subject", subject)
        object.__setattr__(command, "_producer_fingerprint", fingerprint)
        return command

    @model_validator(mode="after")
    def validate_command_bindings(self) -> Self:
        for field in (
            "runner_id",
            "deployment_instance_id",
            "deployment_spec_id",
            "strategy_release_id",
        ):
            if getattr(self, field).int == 0:
                raise ValueError(f"{field} must not be nil")
        if self.effective_config_digest != canonical_json_digest(self.effective_config):
            raise ValueError("effective_config_digest differs from effective_config")

        artifact_ref_raw = _parse_exact_canonical_object(
            self.artifact_ref_canonical_json,
            "artifact_ref_canonical_json",
        )
        artifact_ref = StrategyArtifactRefV2.model_validate(artifact_ref_raw)
        if artifact_ref != self.artifact_ref:
            raise ValueError("artifact_ref differs from its retained canonical bytes")
        if (
            self.artifact_ref_digest
            != hashlib.sha256(self.artifact_ref_canonical_json.encode()).hexdigest()
        ):
            raise ValueError("artifact_ref_digest differs from retained bytes")
        if self.artifact_ref_digest != canonical_model_digest(self.artifact_ref):
            raise ValueError("artifact_ref_digest differs from ArtifactRefV2")

        release_bom = _parse_exact_canonical_object(
            self.release_bom_canonical_json,
            "release_bom_canonical_json",
        )
        if release_bom != self.release_bom:
            raise ValueError("release_bom differs from its retained canonical bytes")
        if (
            self.release_bom_digest
            != hashlib.sha256(self.release_bom_canonical_json.encode()).hexdigest()
        ):
            raise ValueError("release_bom_digest differs from retained bytes")
        _validate_release_bom(self.release_bom, self.artifact_ref)

        _validate_attestation_ref(self.artifact_attestation_ref)
        _validate_artifact_evidence(self.artifact_evidence, self.release_bom)
        _validate_acceptance_receipt(self.artifact_acceptance_receipt)
        attestation_ref_digest = canonical_json_digest(self.artifact_attestation_ref)
        evidence_bindings = {
            "strategy_release_id": str(self.strategy_release_id),
            "artifact_ref_digest": self.artifact_ref_digest,
            "manifest_digest": self.artifact_ref.manifest_sha256,
            "release_bom_digest": self.release_bom_digest,
            "statement_digest": self.artifact_attestation_ref["statement_sha256"],
            "attestation_ref_digest": attestation_ref_digest,
            "bundle_sha256": self.artifact_attestation_ref["bundle_sha256"],
            "artifact_evidence_digest": self.artifact_evidence_digest,
        }
        for field, expected in evidence_bindings.items():
            if self.artifact_evidence.get(field) != expected:
                raise ValueError(f"artifact_evidence.{field} cross-binding differs")
        acceptance_bindings = {
            "tenant_id": self.tenant_id,
            "strategy_release_id": str(self.strategy_release_id),
            "artifact_evidence_digest": self.artifact_evidence_digest,
        }
        for field, expected in acceptance_bindings.items():
            if self.artifact_acceptance_receipt.get(field) != expected:
                raise ValueError(f"artifact_acceptance_receipt.{field} cross-binding differs")
        return self


def _validate_release_bom(bom: dict[str, object], artifact_ref: StrategyArtifactRefV2) -> None:
    _require_exact_keys(bom, _BOM_FIELDS, "release_bom")
    constants = {
        "schema_version": "alephain.strategy-release-bom.v1",
        "canonicalization": "sha256-canonical-json-v1",
        "engine": "nautilus",
        "engine_version": "1.230.0",
        "python_requires": ">=3.12,<3.13",
        "entry_point_group": "alephain.strategy_runtime.v1",
    }
    for field, expected in constants.items():
        if bom[field] != expected:
            raise ValueError(f"release_bom.{field} differs")
    if not isinstance(bom["entry_point_name"], str) or not _ENTRY_POINT_PATTERN.fullmatch(
        bom["entry_point_name"]
    ):
        raise ValueError("release_bom.entry_point_name is invalid")
    for field in (
        "producer_repository",
        "strategy_coordinate",
        "execution_abi_schema_coordinate",
        "execution_abi_golden_coordinate",
        "contract_asset_index_coordinate",
        "toolkit_coordinate",
        "strategy_artifact_coordinate",
    ):
        _require_nonempty_string(bom[field], f"release_bom.{field}")
    for field in ("producer_commit", "strategy_source_commit"):
        value = bom[field]
        if not isinstance(value, str) or not _SOURCE_COMMIT_PATTERN.fullmatch(value):
            raise ValueError(f"release_bom.{field} is invalid")
    for field in (
        "execution_abi_schema_sha256",
        "execution_abi_golden_sha256",
        "contract_asset_index_sha256",
        "toolkit_wheel_sha256",
        "toolkit_sbom_sha256",
        "strategy_source_tree_sha256",
        "strategy_artifact_sha256",
        "strategy_manifest_sha256",
        "build_lock_sha256",
        "zero_rewrite_semantic_diff_sha256",
        "zero_rewrite_characterization_sha256",
    ):
        _require_digest(bom[field], f"release_bom.{field}")

    members = bom["members"]
    if not isinstance(members, list) or len(members) < 7:
        raise ValueError("release_bom.members must be the full BOM array")
    by_role: dict[str, list[dict[str, object]]] = {}
    identities: set[tuple[object, object]] = set()
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("release_bom member must be an object")
        _require_exact_keys(member, _BOM_MEMBER_FIELDS, "release_bom member")
        role = member["role"]
        if role not in _BOM_ROLES:
            raise ValueError("release_bom member role is invalid")
        for field in ("coordinate", "media_type"):
            _require_nonempty_string(member[field], f"release_bom member {field}")
        if not isinstance(member["name"], str) or not _MEMBER_NAME_PATTERN.fullmatch(
            member["name"]
        ):
            raise ValueError("release_bom member name is invalid")
        if type(member["size_bytes"]) is not int or member["size_bytes"] < 0:
            raise ValueError("release_bom member size_bytes is invalid")
        _require_digest(member["sha256"], "release_bom member sha256")
        identity = (role, member["name"])
        if identity in identities:
            raise ValueError("release_bom contains a duplicate role/name")
        identities.add(identity)
        by_role.setdefault(str(role), []).append(member)
    for role in _REQUIRED_SINGLETON_ROLES:
        if len(by_role.get(role, [])) != 1:
            raise ValueError(f"release_bom must contain exactly one {role}")
    if not by_role.get("runtime_artifact"):
        raise ValueError("release_bom must contain runtime_artifact members")

    bindings = {
        "producer_repository": artifact_ref.source_repository,
        "strategy_source_commit": artifact_ref.source_commit,
        "strategy_source_tree_sha256": artifact_ref.normalized_source_tree_sha256,
        "strategy_artifact_coordinate": artifact_ref.artifact_coordinate,
        "strategy_artifact_sha256": artifact_ref.artifact_sha256,
        "strategy_manifest_sha256": artifact_ref.manifest_sha256,
        "contract_asset_index_sha256": artifact_ref.contract_schema_sha256,
        "engine": artifact_ref.engine,
        "engine_version": artifact_ref.engine_version,
    }
    for field, expected in bindings.items():
        if bom[field] != expected:
            raise ValueError(f"release_bom.{field} differs from ArtifactRefV2")
    strategy_wheel = by_role["strategy_wheel"][0]
    if (
        strategy_wheel["coordinate"] != artifact_ref.artifact_coordinate
        or strategy_wheel["sha256"] != artifact_ref.artifact_sha256
        or strategy_wheel["size_bytes"] != artifact_ref.artifact_size_bytes
    ):
        raise ValueError("release_bom strategy wheel differs from ArtifactRefV2")
    strategy_manifest = by_role["strategy_manifest"][0]
    if (
        strategy_manifest["sha256"] != artifact_ref.manifest_sha256
        or strategy_manifest["size_bytes"] != artifact_ref.manifest_size_bytes
    ):
        raise ValueError("release_bom strategy manifest differs from ArtifactRefV2")
    runtime_members = {
        (item["name"], item["sha256"], item["size_bytes"], item["media_type"])
        for item in by_role["runtime_artifact"]
    }
    artifact_runtime_members = {
        (item.name, item.sha256, item.size_bytes, item.media_type)
        for item in artifact_ref.required_runtime_artifacts
    }
    if runtime_members != artifact_runtime_members:
        raise ValueError("release_bom runtime artifacts differ from ArtifactRefV2")
    if by_role["source_tree"][0]["sha256"] != artifact_ref.normalized_source_tree_sha256:
        raise ValueError("release_bom source tree differs from ArtifactRefV2")
    if by_role["contract_schema"][0]["sha256"] != artifact_ref.contract_schema_sha256:
        raise ValueError("release_bom contract schema differs from ArtifactRefV2")
    if by_role["sbom"][0]["sha256"] != bom["toolkit_sbom_sha256"]:
        raise ValueError("release_bom SBOM binding differs")
    if by_role["nautilus_wheel"][0]["sha256"] != bom["toolkit_wheel_sha256"]:
        raise ValueError("release_bom toolkit wheel binding differs")
    if bom["build_lock_sha256"] not in {item.sha256 for item in artifact_ref.build_inputs}:
        raise ValueError("release_bom build lock differs from ArtifactRefV2")


def _validate_attestation_ref(value: dict[str, object]) -> None:
    _require_exact_keys(value, _ATTESTATION_REF_FIELDS, "artifact_attestation_ref")
    constants = {
        "schema_version": "alephain.artifact-attestation-ref.v1",
        "payload_type": "application/vnd.in-toto+json",
        "predicate_type": "https://the-alephain-guild.dev/attestation/strategy-release/v1",
    }
    for field, expected in constants.items():
        if value[field] != expected:
            raise ValueError(f"artifact_attestation_ref.{field} differs")
    for coordinate, digest in (
        ("statement_coordinate", "statement_sha256"),
        ("bundle_coordinate", "bundle_sha256"),
    ):
        _require_nonempty_string(value[coordinate], f"artifact_attestation_ref.{coordinate}")
        _require_digest(value[digest], f"artifact_attestation_ref.{digest}")
        if not str(value[coordinate]).endswith(f"@sha256:{value[digest]}"):
            raise ValueError(f"artifact_attestation_ref.{coordinate} is not digest pinned")


def _validate_artifact_evidence(
    evidence: dict[str, object], release_bom: dict[str, object]
) -> None:
    _require_exact_keys(evidence, _EVIDENCE_FIELDS, "artifact_evidence")
    if evidence["schema_version"] != 1:
        raise ValueError("artifact_evidence.schema_version must be exactly 1")
    _require_canonical_uuid(
        evidence["strategy_release_id"], "artifact_evidence.strategy_release_id"
    )
    for field in (
        "artifact_ref_digest",
        "manifest_digest",
        "release_bom_digest",
        "statement_digest",
        "attestation_ref_digest",
        "bundle_sha256",
        "artifact_evidence_digest",
    ):
        _require_digest(evidence[field], f"artifact_evidence.{field}")
    _require_timestamp(evidence["verified_at"], "artifact_evidence.verified_at")

    claims = _require_object(evidence["signed_producer_claims"], "signed_producer_claims")
    proof = _require_object(evidence["sigstore_proof"], "sigstore_proof")
    policy = _require_object(evidence["local_policy_evaluation"], "local_policy_evaluation")
    _require_exact_keys(claims, _SIGNED_CLAIMS_FIELDS, "signed_producer_claims")
    _require_exact_keys(proof, _SIGSTORE_FIELDS, "sigstore_proof")
    _require_exact_keys(policy, _POLICY_FIELDS, "local_policy_evaluation")

    for field in (
        "producer_repository",
        "producer_commit",
        "workflow_identity",
        "engine",
        "engine_version",
        "python_requires",
        "entry_point_group",
        "entry_point_name",
    ):
        _require_nonempty_string(claims[field], f"signed_producer_claims.{field}")
    if type(claims["source_date_epoch"]) is not int or claims["source_date_epoch"] < 0:
        raise ValueError("signed_producer_claims.source_date_epoch is invalid")
    for field in (
        "strategy_source_tree_sha256",
        "execution_abi_schema_sha256",
        "contract_asset_index_sha256",
        "toolkit_wheel_sha256",
        "toolkit_sbom_sha256",
        "build_lock_sha256",
        "zero_rewrite_semantic_diff_sha256",
        "zero_rewrite_characterization_sha256",
    ):
        _require_digest(claims[field], f"signed_producer_claims.{field}")
    claim_bindings = {
        "producer_repository": release_bom["producer_repository"],
        "producer_commit": release_bom["producer_commit"],
        "strategy_source_tree_sha256": release_bom["strategy_source_tree_sha256"],
        "execution_abi_schema_sha256": release_bom["execution_abi_schema_sha256"],
        "contract_asset_index_sha256": release_bom["contract_asset_index_sha256"],
        "toolkit_wheel_sha256": release_bom["toolkit_wheel_sha256"],
        "toolkit_sbom_sha256": release_bom["toolkit_sbom_sha256"],
        "build_lock_sha256": release_bom["build_lock_sha256"],
        "zero_rewrite_semantic_diff_sha256": release_bom["zero_rewrite_semantic_diff_sha256"],
        "zero_rewrite_characterization_sha256": release_bom["zero_rewrite_characterization_sha256"],
        "engine": release_bom["engine"],
        "engine_version": release_bom["engine_version"],
        "python_requires": release_bom["python_requires"],
        "entry_point_group": release_bom["entry_point_group"],
        "entry_point_name": release_bom["entry_point_name"],
    }
    for field, expected in claim_bindings.items():
        if claims[field] != expected:
            raise ValueError(f"signed_producer_claims.{field} differs from release BOM")

    if proof["schema_version"] != 1:
        raise ValueError("sigstore_proof.schema_version must be exactly 1")
    for field in ("bundle_sha256", "statement_sha256", "certificate_sha256", "checkpoint_sha256"):
        _require_digest(proof[field], f"sigstore_proof.{field}")
    for field in ("issuer", "workflow_identity", "rekor_log_id"):
        _require_nonempty_string(proof[field], f"sigstore_proof.{field}")
    for field in ("rekor_log_index", "rekor_integrated_time"):
        if type(proof[field]) is not int or proof[field] < 0:
            raise ValueError(f"sigstore_proof.{field} is invalid")
    for field in (
        "certificate_chain_verified",
        "sct_verified",
        "dsse_signature_verified",
        "rekor_body_verified",
        "set_verified",
        "inclusion_proof_verified",
        "checkpoint_verified",
    ):
        if proof[field] is not True:
            raise ValueError(f"sigstore_proof.{field} must be true")
    if (
        proof["bundle_sha256"] != evidence["bundle_sha256"]
        or proof["statement_sha256"] != evidence["statement_digest"]
        or proof["workflow_identity"] != claims["workflow_identity"]
    ):
        raise ValueError("sigstore proof differs from evidence or producer claims")

    if policy["schema_version"] != 1 or policy["decision"] != "accepted":
        raise ValueError("local policy decision must be accepted schema v1")
    _require_nonempty_string(policy["policy_id"], "local_policy_evaluation.policy_id")
    if type(policy["policy_version"]) is not int or policy["policy_version"] < 1:
        raise ValueError("local_policy_evaluation.policy_version is invalid")
    _require_digest(policy["policy_digest"], "local_policy_evaluation.policy_digest")
    _require_timestamp(policy["evaluated_at"], "local_policy_evaluation.evaluated_at")

    digest_input = _ordered_copy(evidence, _EVIDENCE_FIELDS)
    digest_input["signed_producer_claims"] = _ordered_copy(claims, _SIGNED_CLAIMS_FIELDS)
    digest_input["sigstore_proof"] = _ordered_copy(proof, _SIGSTORE_FIELDS)
    digest_input["local_policy_evaluation"] = _ordered_copy(policy, _POLICY_FIELDS)
    digest_input["artifact_evidence_digest"] = ""
    expected_digest = hashlib.sha256(_json_bytes_preserving_order(digest_input)).hexdigest()
    if evidence["artifact_evidence_digest"] != expected_digest:
        raise ValueError("artifact_evidence self digest differs")


def _validate_acceptance_receipt(receipt: dict[str, object]) -> None:
    _require_exact_keys(receipt, _ACCEPTANCE_FIELDS, "artifact_acceptance_receipt")
    if receipt["schema_version"] != 1:
        raise ValueError("artifact acceptance schema_version must be exactly 1")
    _require_nonempty_string(receipt["tenant_id"], "artifact_acceptance_receipt.tenant_id")
    if type(receipt["released_lifecycle_version"]) is not int or (
        receipt["released_lifecycle_version"] < 1
    ):
        raise ValueError("artifact acceptance lifecycle version must be positive")
    for field in (
        "strategy_release_id",
        "outbox_event_id",
        "actor_id",
        "actor_assertion_jti",
        "correlation_id",
    ):
        _require_canonical_uuid(receipt[field], f"artifact_acceptance_receipt.{field}")
    for field in (
        "artifact_evidence_digest",
        "snapshot_digest",
        "request_fingerprint",
        "receipt_digest",
    ):
        _require_digest(receipt[field], f"artifact_acceptance_receipt.{field}")
    _require_timestamp(receipt["accepted_at"], "artifact_acceptance_receipt.accepted_at")
    digest_input = _ordered_copy(receipt, _ACCEPTANCE_FIELDS)
    digest_input["receipt_digest"] = ""
    expected_digest = hashlib.sha256(_json_bytes_preserving_order(digest_input)).hexdigest()
    if receipt["receipt_digest"] != expected_digest:
        raise ValueError("artifact acceptance receipt self digest differs")


def _parse_exact_canonical_object(raw: str, label: str) -> dict[str, object]:
    value = _strict_json_object(raw.encode(), label)
    if canonical_json_bytes(value) != raw.encode():
        raise ValueError(f"{label} is not exact canonical JSON")
    return value


def _strict_json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_float=Decimal,
            parse_int=int,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {token}")
            ),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid JSON for {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: tuple[str, ...],
    label: str,
    *,
    ordered: bool = False,
) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} field set differs")
    if ordered and tuple(value) != expected:
        raise ValueError(f"{label} field order differs from exact producer bytes")


def _require_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_nonempty_string(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")


def _require_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_canonical_uuid(value: object, label: str) -> UUID:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a UUID string")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError(f"{label} must be a UUID") from error
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError(f"{label} must be a canonical non-nil UUID")
    return parsed


def _require_timestamp(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be a UTC RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must have a timezone")


def _decode_base64url(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be unpadded base64url")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{label} must be unpadded base64url") from error


def _ordered_copy(value: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    return {field: value[field] for field in fields}


def _json_bytes_preserving_order(value: object) -> bytes:
    return _encode_json_preserving_order(value).encode("utf-8")


def _encode_json_preserving_order(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if type(value) is int:
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON numbers must be finite")
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return "0" if rendered in {"-0", ""} else rendered
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{_encode_json_preserving_order(item)}"
                for key, item in value.items()
            )
            + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode_json_preserving_order(item) for item in value) + "]"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _framed(domain: bytes, subject: str, event_bytes: bytes) -> bytes:
    subject_bytes = subject.encode("utf-8")
    return (
        domain
        + len(subject_bytes).to_bytes(4, "big")
        + subject_bytes
        + len(event_bytes).to_bytes(8, "big")
        + event_bytes
    )
