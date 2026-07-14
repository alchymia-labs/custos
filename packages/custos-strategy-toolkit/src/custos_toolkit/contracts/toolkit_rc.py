"""Custos-owned immutable toolkit release-candidate contract."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SourceCommit = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
RcVersion = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+rc[1-9][0-9]*$")]
DistributionName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
RegistryVersion = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+!-]*$")]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolkitRcMemberRole(StrEnum):
    BASE_CONTRACTS_WHEEL = "base_contracts_wheel"
    NAUTILUS_WHEEL = "nautilus_wheel"


class ImmutableToolkitArtifactBindingV1(_StrictFrozenModel):
    coordinate: NonEmptyString
    sha256: Sha256Hex
    size_bytes: StrictInt = Field(gt=0)

    @model_validator(mode="after")
    def validate_immutable_coordinate(self) -> Self:
        marker = "@sha256:"
        if marker not in self.coordinate:
            raise ValueError("artifact requires a digest-pinned coordinate")
        if not self.coordinate.endswith(f"{marker}{self.sha256}"):
            raise ValueError("artifact coordinate digest must match sha256")
        prefix = self.coordinate[: -len(f"{marker}{self.sha256}")]
        if not prefix or prefix.startswith((".", "/", "file:", "path:", "editable:")):
            raise ValueError("artifact coordinate must identify an immutable repository object")
        return self


class LockedToolkitDependencyV1(_StrictFrozenModel):
    name: DistributionName
    version: RegistryVersion
    requirement: NonEmptyString

    @model_validator(mode="after")
    def validate_registry_pin(self) -> Self:
        if self.requirement != f"{self.name}=={self.version}":
            raise ValueError("toolkit dependency must be an exact registry requirement")
        return self


class ToolkitRcMemberV1(_StrictFrozenModel):
    role: ToolkitRcMemberRole
    distribution_name: DistributionName
    version: RcVersion
    python_requires: NonEmptyString
    nautilus_version: NonEmptyString | None
    top_level_modules: tuple[NonEmptyString, ...] = Field(min_length=1)
    dependencies: tuple[LockedToolkitDependencyV1, ...] = Field(min_length=1)
    wheel: ImmutableToolkitArtifactBindingV1
    sbom: ImmutableToolkitArtifactBindingV1
    contract_schema: ImmutableToolkitArtifactBindingV1
    contract_asset_index: ImmutableToolkitArtifactBindingV1
    dependency_lock_evidence: ImmutableToolkitArtifactBindingV1
    slsa_provenance: ImmutableToolkitArtifactBindingV1
    sigstore_attestation: ImmutableToolkitArtifactBindingV1
    source_repository: NonEmptyString
    source_commit: SourceCommit
    t4_zero_rewrite_receipt: ImmutableToolkitArtifactBindingV1
    t4b_typing_closure_receipt: ImmutableToolkitArtifactBindingV1
    t5_pre_import_verifier_receipt: ImmutableToolkitArtifactBindingV1

    @field_validator("top_level_modules")
    @classmethod
    def validate_top_level_modules(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("top-level toolkit modules must be unique")
        for value in values:
            if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", value):
                raise ValueError("top-level toolkit module must be an importable module path")
            if value.split(".", 1)[0] in {"shared", "pandas_ta"}:
                raise ValueError("forbidden top-level toolkit module")
        return values

    @model_validator(mode="after")
    def validate_distribution_policy(self) -> Self:
        if self.source_repository != "https://github.com/alchymia-labs/custos":
            raise ValueError("toolkit RC source repository identity differs")
        if self.role is ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL:
            if (
                self.distribution_name != "custos-strategy-toolkit"
                or self.python_requires != ">=3.11"
                or self.nautilus_version is not None
            ):
                raise ValueError("base contracts member policy differs")
        elif (
            self.distribution_name != "custos-strategy-toolkit-nautilus"
            or self.python_requires != ">=3.12,<3.13"
            or self.nautilus_version != "1.230.0"
        ):
            raise ValueError("Nautilus member policy differs")
        return self


class ToolkitRcReceiptManifestV1(_StrictFrozenModel):
    """Schema-only foundation for a future immutable toolkit RC receipt."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="ToolkitRcReceiptManifestV1",
        json_schema_extra={
            "$id": (
                "https://custos.the-alephain-guild/contracts/"
                "toolkit-rc-receipt-manifest-v1.schema.json"
            )
        },
    )

    schema_version: Literal[1] = 1
    contract_version: Literal["alephain.custos.toolkit-rc-receipt-manifest.v1"] = (
        "alephain.custos.toolkit-rc-receipt-manifest.v1"
    )
    candidate_version: RcVersion
    immutable: Literal[True] = True
    overwrite_allowed: Literal[False] = False
    members: tuple[ToolkitRcMemberV1, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_member_matrix(self) -> Self:
        if {member.role for member in self.members} != set(ToolkitRcMemberRole):
            raise ValueError("toolkit RC requires exactly one base and one Nautilus member")
        if any(member.version != self.candidate_version for member in self.members):
            raise ValueError("every toolkit RC member version must match candidate_version")
        return self


class ToolkitRcCycloneDxSbomV1(_StrictFrozenModel):
    role: ToolkitRcMemberRole
    distribution_name: DistributionName
    wheel_sha256: Sha256Hex
    format: Literal["CycloneDX 1.6"] = "CycloneDX 1.6"
    artifact: ImmutableToolkitArtifactBindingV1


class ToolkitRcT6dPendingReceiptV1(_StrictFrozenModel):
    """Contract-only readiness evidence before the protected release runner executes."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="ToolkitRcT6dPendingReceiptV1",
        json_schema_extra={
            "$id": (
                "https://custos.the-alephain-guild/contracts/"
                "toolkit-rc-t6d-pending-receipt-v1.schema.json"
            )
        },
    )

    schema_version: Literal[1] = 1
    contract_version: Literal["alephain.custos.toolkit-rc-t6d-pending-receipt.v1"] = (
        "alephain.custos.toolkit-rc-t6d-pending-receipt.v1"
    )
    status: Literal["PENDING_T6D_RELEASE_RUNNER"] = "PENDING_T6D_RELEASE_RUNNER"
    ready: Literal[False] = False
    candidate_version: RcVersion
    source_repository: Literal["https://github.com/alchymia-labs/custos"] = (
        "https://github.com/alchymia-labs/custos"
    )
    source_commit: SourceCommit
    source_date_epoch: StrictInt = Field(ge=315_532_800)
    release_environment: Literal["toolkit-rc-release"] = "toolkit-rc-release"
    workflow_identity: Literal[
        "https://github.com/alchymia-labs/custos/.github/workflows/"
        "release-toolkit-rc.yml@refs/heads/main"
    ] = (
        "https://github.com/alchymia-labs/custos/.github/workflows/"
        "release-toolkit-rc.yml@refs/heads/main"
    )
    oidc_issuer: Literal["https://token.actions.githubusercontent.com"] = (
        "https://token.actions.githubusercontent.com"
    )
    build_manifest: ImmutableToolkitArtifactBindingV1
    dependency_lock_evidence: ImmutableToolkitArtifactBindingV1
    cyclonedx_sboms: tuple[ToolkitRcCycloneDxSbomV1, ...] = Field(min_length=2, max_length=2)
    provenance_statement: ImmutableToolkitArtifactBindingV1
    formal_sboms_complete: Literal[True] = True
    dependency_locks_complete: Literal[True] = True
    provenance_complete: Literal[True] = True
    production_credentials_used: Literal[False] = False
    production_signature_verified: Literal[False] = False
    remote_publication_verified: Literal[False] = False
    final_receipt_published: Literal[False] = False
    final_blockers: tuple[
        Literal[
            "execute the protected production release runner with credentials and "
            "register its verified remote receipt"
        ],
        ...,
    ] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_sbom_matrix(self) -> Self:
        if {sbom.role for sbom in self.cyclonedx_sboms} != set(ToolkitRcMemberRole):
            raise ValueError("T6d pending receipt requires one SBOM per toolkit member")
        expected = {
            ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL: "custos-strategy-toolkit",
            ToolkitRcMemberRole.NAUTILUS_WHEEL: "custos-strategy-toolkit-nautilus",
        }
        if any(sbom.distribution_name != expected[sbom.role] for sbom in self.cyclonedx_sboms):
            raise ValueError("T6d pending SBOM distribution matrix differs")
        return self


__all__ = [
    "ImmutableToolkitArtifactBindingV1",
    "LockedToolkitDependencyV1",
    "ToolkitRcMemberRole",
    "ToolkitRcMemberV1",
    "ToolkitRcReceiptManifestV1",
    "ToolkitRcCycloneDxSbomV1",
    "ToolkitRcT6dPendingReceiptV1",
]
