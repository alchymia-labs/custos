"""Custos-owned strategy execution and artifact verification contracts.

These models define the runner's execution ABI and the exact artifact evidence
it accepts. They deliberately do not define StrategyRelease lifecycle or the
canonical StrategyRelease BOM, which remain Crucible and Philosophers-Stone
responsibilities respectively.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Annotated, Literal, Protocol, Self, TypeAlias, TypeVar, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

STRATEGY_EXECUTION_ABI_V1 = "alephain.strategy_runtime.v1"
STRATEGY_CONTRACT_SCHEMA_VERSION = 1
STRATEGY_CONTRACT_CANONICALIZATION = "sha256-canonical-json-v1"

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
SafeName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")]
SourceCommit = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]

JsonScalar: TypeAlias = None | bool | int | Decimal | str
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
FrozenJsonObject: TypeAlias = Mapping[str, JsonValue]

ConfigT = TypeVar("ConfigT")
StrategyT_co = TypeVar("StrategyT_co", covariant=True)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StrategyExecutionContextV1(_StrictFrozenModel):
    """Identity and provenance presented to a strategy runtime adapter."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="StrategyExecutionContextV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/strategy-execution-context-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    engine: Literal["nautilus"]
    trading_mode: Literal["sandbox", "testnet", "live"]
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: Sha256Hex
    effective_config_digest: Sha256Hex
    generation: StrictInt = Field(ge=1)


class StrategyRuntimeAdapterV1(Protocol[ConfigT, StrategyT_co]):
    """Typed adapter implemented by an engine-specific strategy wheel."""

    def build_config(
        self,
        effective_config: FrozenJsonObject,
        execution_context: StrategyExecutionContextV1,
    ) -> ConfigT: ...

    def build_strategy(self, config: ConfigT) -> StrategyT_co: ...


class ArtifactMemberRole(StrEnum):
    BASE_CONTRACTS_WHEEL = "base_contracts_wheel"
    NAUTILUS_WHEEL = "nautilus_wheel"
    STRATEGY_WHEEL = "strategy_wheel"
    STRATEGY_MANIFEST = "strategy_manifest"
    RUNTIME_ARTIFACT = "runtime_artifact"
    ATTESTATION_BUNDLE = "attestation_bundle"
    SBOM = "sbom"
    CONTRACT_SCHEMA = "contract_schema"
    SOURCE_TREE = "source_tree"


class DigestBindingV1(_StrictFrozenModel):
    name: SafeName
    sha256: Sha256Hex

    @field_validator("name")
    @classmethod
    def validate_relative_name(cls, value: str) -> str:
        return _validate_relative_artifact_name(value)


class ArtifactMemberV1(_StrictFrozenModel):
    role: ArtifactMemberRole
    name: SafeName
    media_type: NonEmptyString
    size_bytes: StrictInt = Field(ge=0)
    sha256: Sha256Hex

    @field_validator("name")
    @classmethod
    def validate_relative_name(cls, value: str) -> str:
        return _validate_relative_artifact_name(value)


class AttestationEvidenceV1(_StrictFrozenModel):
    bundle_sha256: Sha256Hex
    source_repository: NonEmptyString
    source_commit: SourceCommit
    normalized_source_tree_sha256: Sha256Hex
    issuer: NonEmptyString
    workflow_identity: NonEmptyString
    trust_policy_id: NonEmptyString
    trust_policy_version: StrictInt = Field(ge=1)
    trust_policy_digest: Sha256Hex
    python_version: Annotated[str, StringConstraints(pattern=r"^3\.12\.[0-9]+$")]
    engine: Literal["nautilus"]
    engine_version: Literal["1.230.0"]
    base_contracts_version: NonEmptyString
    engine_toolkit_version: NonEmptyString
    build_inputs: tuple[DigestBindingV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_build_inputs(self) -> Self:
        _require_unique_names(self.build_inputs, label="attestation build input")
        return self


class StrategyManifestV1(_StrictFrozenModel):
    """Artifact-local compatibility metadata, never release authority."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="StrategyManifestV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/strategy-manifest-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    execution_abi: Literal["alephain.strategy_runtime.v1"]
    entry_point_group: Literal["alephain.strategy_runtime.v1"]
    entry_point: NonEmptyString
    engine: Literal["nautilus"]
    engine_version: Literal["1.230.0"]
    requires_python: Literal[">=3.12,<3.13"]
    base_contracts_version: NonEmptyString
    engine_toolkit_version: NonEmptyString
    config_schema_sha256: Sha256Hex
    catalog_alias: NonEmptyString | None = None
    runtime_artifacts: tuple[ArtifactMemberV1, ...] = ()

    @field_validator("entry_point")
    @classmethod
    def validate_entry_point(cls, value: str) -> str:
        module, separator, attribute = value.partition(":")
        valid_module = re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module)
        if not separator or not attribute or not valid_module:
            raise ValueError("entry_point must be a module path and attribute separated by ':'")
        if module.split(".", 1)[0] in {"shared", "pandas_ta"}:
            raise ValueError("legacy top-level toolkit aliases are not valid entry points")
        return value

    @model_validator(mode="after")
    def validate_runtime_artifacts(self) -> Self:
        if any(
            member.role is not ArtifactMemberRole.RUNTIME_ARTIFACT
            for member in self.runtime_artifacts
        ):
            raise ValueError("manifest runtime_artifacts may contain only runtime_artifact members")
        _require_unique_members(self.runtime_artifacts)
        return self


class StrategyArtifactRefV1(_StrictFrozenModel):
    """Exact executable bytes and evidence, without business lifecycle state."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="StrategyArtifactRefV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/strategy-artifact-ref-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    artifact_kind: Literal["wheel"]
    artifact_coordinate: NonEmptyString
    artifact_sha256: Sha256Hex
    artifact_size_bytes: StrictInt = Field(gt=0)
    manifest_sha256: Sha256Hex
    manifest_size_bytes: StrictInt = Field(gt=0)
    required_runtime_artifacts: tuple[ArtifactMemberV1, ...] = ()
    attestation: AttestationEvidenceV1
    sbom_sha256: Sha256Hex
    contract_schema_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_runtime_artifacts(self) -> Self:
        if any(
            member.role is not ArtifactMemberRole.RUNTIME_ARTIFACT
            for member in self.required_runtime_artifacts
        ):
            raise ValueError("required_runtime_artifacts may contain only runtime_artifact members")
        _require_unique_members(self.required_runtime_artifacts)
        return self


class DevelopmentSourceRefV1(_StrictFrozenModel):
    """Explicit non-promotable source reference for sandbox development only."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="DevelopmentSourceRefV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/development-source-ref-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    source_path: NonEmptyString
    source_sha256: Sha256Hex
    trading_mode: Literal["sandbox"]
    promotable: Literal[False] = False


class StrategyExecutionCommandBindingV1(_StrictFrozenModel):
    """Artifact fields that a signed Crucible command must bind exactly."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="StrategyExecutionCommandBindingV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/strategy-execution-command-binding-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: Sha256Hex
    generation: StrictInt = Field(ge=1)
    strategy_release_id: UUID
    release_bom_digest: Sha256Hex
    release_bom_members: tuple[ArtifactMemberV1, ...] = Field(min_length=1)
    artifact_ref: StrategyArtifactRefV1
    effective_config_digest: Sha256Hex

    @model_validator(mode="after")
    def validate_release_member_projection(self) -> Self:
        _validate_release_members(self.release_bom_members, self.artifact_ref)
        return self


class StrategyArtifactVerificationReceiptV1(_StrictFrozenModel):
    """Custos proof that exact command-bound bytes passed local verification."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="StrategyArtifactVerificationReceiptV1",
        json_schema_extra={
            "$id": "https://custos.the-alephain-guild/contracts/strategy-artifact-verification-receipt-v1.schema.json"
        },
    )

    schema_version: Literal[1] = 1
    verification_profile: Literal["custos-artifact-verification-v1"]
    verified_at: datetime
    command_binding: StrategyExecutionCommandBindingV1
    artifact_ref_digest: Sha256Hex
    verified_members: tuple[ArtifactMemberV1, ...] = Field(min_length=1)
    local_trust_policy_id: NonEmptyString
    local_trust_policy_version: StrictInt = Field(ge=1)
    local_trust_policy_digest: Sha256Hex
    loaded_entry_point: NonEmptyString

    @model_validator(mode="after")
    def validate_lossless_evidence(self) -> Self:
        if self.verified_members != self.command_binding.release_bom_members:
            raise ValueError(
                "verified_members must losslessly echo the command release member table"
            )
        if self.artifact_ref_digest != canonical_model_digest(self.command_binding.artifact_ref):
            raise ValueError("artifact_ref_digest does not match the command artifact_ref")
        attestation = self.command_binding.artifact_ref.attestation
        expected_policy = (
            attestation.trust_policy_id,
            attestation.trust_policy_version,
            attestation.trust_policy_digest,
        )
        local_policy = (
            self.local_trust_policy_id,
            self.local_trust_policy_version,
            self.local_trust_policy_digest,
        )
        if local_policy != expected_policy:
            raise ValueError("receipt trust policy does not match verified attestation evidence")
        return self


def parse_and_freeze_json_object(raw: str | bytes) -> FrozenJsonObject:
    """Parse JSON with Decimal numbers, reject duplicates, and deep-freeze it."""

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    value = json.loads(
        raw,
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_reject_non_finite_json_number,
        object_pairs_hook=_object_without_duplicate_keys,
    )
    frozen = deep_freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise ValueError("effective config must be a JSON object")
    return cast(FrozenJsonObject, frozen)


def deep_freeze_json(value: object) -> JsonValue:
    """Convert a JSON-compatible value into immutable recursive containers."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, float):
        raise TypeError("float is forbidden; parse JSON numbers as Decimal")
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            frozen[key] = deep_freeze_json(value[key])
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze_json(item) for item in value)
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def canonical_json_bytes(value: JsonValue | list[object] | dict[str, object]) -> bytes:
    """Encode the repository's deterministic canonical JSON subset."""

    return _encode_canonical_json(value).encode("utf-8")


def canonical_json_digest(value: JsonValue | list[object] | dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_model_digest(model: BaseModel) -> str:
    value = model.model_dump(mode="json", exclude_none=False)
    return canonical_json_digest(value)


def verify_effective_config_digest(raw: str | bytes, expected_digest: str) -> FrozenJsonObject:
    frozen = parse_and_freeze_json_object(raw)
    actual_digest = canonical_json_digest(frozen)
    if actual_digest != expected_digest:
        raise ValueError("effective config digest does not match signed command")
    return frozen


def _validate_relative_artifact_name(value: str) -> str:
    if "\\" in value:
        raise ValueError("artifact member names must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.endswith("/"):
        raise ValueError("artifact member names must be safe relative paths")
    return value


def _require_unique_names(values: tuple[DigestBindingV1, ...], *, label: str) -> None:
    names = [value.name for value in values]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate {label} name")


def _require_unique_members(members: tuple[ArtifactMemberV1, ...]) -> None:
    keys = [(member.role, member.name) for member in members]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate artifact member role/name")


def _validate_release_members(
    members: tuple[ArtifactMemberV1, ...], artifact_ref: StrategyArtifactRefV1
) -> None:
    _require_unique_members(members)
    by_role: dict[ArtifactMemberRole, list[ArtifactMemberV1]] = {}
    for member in members:
        by_role.setdefault(member.role, []).append(member)
    required_singletons = {
        ArtifactMemberRole.BASE_CONTRACTS_WHEEL,
        ArtifactMemberRole.NAUTILUS_WHEEL,
        ArtifactMemberRole.STRATEGY_WHEEL,
        ArtifactMemberRole.STRATEGY_MANIFEST,
        ArtifactMemberRole.ATTESTATION_BUNDLE,
        ArtifactMemberRole.SBOM,
        ArtifactMemberRole.CONTRACT_SCHEMA,
        ArtifactMemberRole.SOURCE_TREE,
    }
    invalid = sorted(role.value for role in required_singletons if len(by_role.get(role, ())) != 1)
    if invalid:
        raise ValueError(f"release member projection requires exactly one of each role: {invalid}")

    expected_digests = {
        ArtifactMemberRole.STRATEGY_WHEEL: artifact_ref.artifact_sha256,
        ArtifactMemberRole.STRATEGY_MANIFEST: artifact_ref.manifest_sha256,
        ArtifactMemberRole.ATTESTATION_BUNDLE: artifact_ref.attestation.bundle_sha256,
        ArtifactMemberRole.SBOM: artifact_ref.sbom_sha256,
        ArtifactMemberRole.CONTRACT_SCHEMA: artifact_ref.contract_schema_sha256,
        ArtifactMemberRole.SOURCE_TREE: artifact_ref.attestation.normalized_source_tree_sha256,
    }
    for role, expected_digest in expected_digests.items():
        if by_role[role][0].sha256 != expected_digest:
            raise ValueError(f"{role.value} digest differs from ArtifactRef")

    member_keys = {(member.role, member.name, member.sha256) for member in members}
    for runtime_artifact in artifact_ref.required_runtime_artifacts:
        key = (runtime_artifact.role, runtime_artifact.name, runtime_artifact.sha256)
        if key not in member_keys:
            raise ValueError(
                "ArtifactRef runtime artifact is absent from release member projection"
            )


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_non_finite_json_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _encode_canonical_json(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical JSON numbers must be finite")
        if value == 0:
            return "0"
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    if isinstance(value, float):
        raise TypeError("float is forbidden in canonical JSON")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        entries = (
            f"{json.dumps(key, ensure_ascii=False)}:{_encode_canonical_json(value[key])}"
            for key in sorted(value)
        )
        return "{" + ",".join(entries) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode_canonical_json(item) for item in value) + "]"
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


__all__ = [
    "ArtifactMemberRole",
    "ArtifactMemberV1",
    "AttestationEvidenceV1",
    "DevelopmentSourceRefV1",
    "DigestBindingV1",
    "FrozenJsonObject",
    "JsonScalar",
    "JsonValue",
    "STRATEGY_CONTRACT_CANONICALIZATION",
    "STRATEGY_CONTRACT_SCHEMA_VERSION",
    "STRATEGY_EXECUTION_ABI_V1",
    "StrategyArtifactRefV1",
    "StrategyArtifactVerificationReceiptV1",
    "StrategyExecutionCommandBindingV1",
    "StrategyExecutionContextV1",
    "StrategyManifestV1",
    "StrategyRuntimeAdapterV1",
    "canonical_json_bytes",
    "canonical_json_digest",
    "canonical_model_digest",
    "deep_freeze_json",
    "parse_and_freeze_json_object",
    "verify_effective_config_digest",
]
