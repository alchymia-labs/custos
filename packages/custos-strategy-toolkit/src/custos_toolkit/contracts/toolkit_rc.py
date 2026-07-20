"""Custos-owned immutable toolkit release-candidate contract."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
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


class ToolkitRcPublicationObjectV1(_StrictFrozenModel):
    coordinate: NonEmptyString
    object_id: Sha256Hex
    sha256: Sha256Hex
    size_bytes: StrictInt = Field(gt=0)

    @model_validator(mode="after")
    def validate_object_identity(self) -> Self:
        if hashlib.sha256(self.coordinate.encode()).hexdigest() != self.object_id:
            raise ValueError("publication object_id must be the coordinate SHA-256")
        return self


class ToolkitRcPublicationReceiptV1(_StrictFrozenModel):
    """Immutable artifact-service receipt, before Custos authority registration."""

    schema_version: Literal["alephain.custos.toolkit-rc-publication-receipt.v1"]
    status: Literal[
        "PENDING_T6C_PUBLICATION_VERIFIED",
        "PENDING_T6E_AUTHORITY_REGISTRATION",
    ]
    ready: Literal[False]
    handoff_ready: Literal[False]
    candidate_version: RcVersion
    source_repository: Literal["https://github.com/alchymia-labs/custos"]
    source_commit: SourceCommit
    source_date_epoch: StrictInt = Field(ge=315_532_800)
    publication_id: NonEmptyString
    transaction_id: NonEmptyString
    publication_atomic: Literal[True]
    puback_verified: Literal[True]
    readback_verified: Literal[True]
    production_credentials_used: StrictBool
    production_signature_verified: StrictBool
    workflow_ref: (
        Literal["alchymia-labs/custos/.github/workflows/release-toolkit-rc.yml@refs/heads/main"]
        | None
    )
    workflow_identity: (
        Literal[
            "https://github.com/alchymia-labs/custos/.github/workflows/"
            "release-toolkit-rc.yml@refs/heads/main"
        ]
        | None
    )
    oidc_issuer: Literal["https://token.actions.githubusercontent.com"] | None
    release_environment: Literal["toolkit-rc-release"] | None
    workflow_run_id: StrictInt | None = Field(default=None, gt=0)
    workflow_run_attempt: StrictInt | None = Field(default=None, gt=0)
    objects: tuple[ToolkitRcPublicationObjectV1, ...] = Field(min_length=1)
    authority_registered: Literal[False]

    @model_validator(mode="after")
    def validate_publication_state(self) -> Self:
        identities = (
            self.workflow_ref,
            self.workflow_identity,
            self.oidc_issuer,
            self.release_environment,
            self.workflow_run_id,
            self.workflow_run_attempt,
        )
        if self.production_credentials_used:
            if (
                self.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
                or not self.production_signature_verified
                or any(value is None for value in identities)
            ):
                raise ValueError("production publication receipt lacks exact workflow evidence")
        elif (
            self.status != "PENDING_T6C_PUBLICATION_VERIFIED"
            or self.production_signature_verified
            or any(value is not None for value in identities)
        ):
            raise ValueError("local publication receipt must not claim production evidence")
        coordinates = [item.coordinate for item in self.objects]
        object_ids = [item.object_id for item in self.objects]
        if len(coordinates) != len(set(coordinates)) or len(object_ids) != len(set(object_ids)):
            raise ValueError("publication receipt objects must be unique")
        if any(self.candidate_version not in item.coordinate for item in self.objects):
            raise ValueError("publication receipt object coordinate lacks candidate version")
        return self


class ToolkitRcAuthorityPendingReceiptV1(_StrictFrozenModel):
    receipt_schema_version: Literal[1]
    contract_version: Literal["alephain.custos.toolkit-rc-authority-receipt.v1"]
    status: Literal["PENDING_T6E_AUTHORITY_REGISTRATION"]
    ready: Literal[False]
    handoff_ready: Literal[False]
    publication_receipt_url: NonEmptyString
    publication_receipt_sha256: Sha256Hex
    publication_receipt_size_bytes: StrictInt = Field(gt=0)
    publication_receipt: ToolkitRcPublicationReceiptV1
    stable_ready_receipt_path: Literal[
        "docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json"
    ]
    production_credentials_used: Literal[True]
    production_signature_verified: Literal[True]
    remote_publication_verified: Literal[True]
    authority_registered: Literal[False]
    runtime_ready: Literal[False]
    production_ready: Literal[False]
    strategy_release_bom_created: Literal[False]
    final_blockers: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=1)
    scope_ceiling: Literal[
        "Custos base and Nautilus toolkit RC only; no strategy artifact, "
        "StrategyRelease, engine, or runtime readiness"
    ]

    @model_validator(mode="after")
    def validate_pending_blockers(self) -> Self:
        if self.final_blockers != (
            "verified READY candidate is registered by an independent authority commit",
        ) or (
            self.publication_receipt.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
            or not self.publication_receipt.production_credentials_used
            or not self.publication_receipt.production_signature_verified
        ):
            raise ValueError("pending toolkit authority blockers differ")
        return self


class ToolkitRcAuthorityReadyReceiptV1(_StrictFrozenModel):
    receipt_schema_version: Literal[1]
    contract_version: Literal["alephain.custos.toolkit-rc-authority-receipt.v1"]
    status: Literal["READY_TOOLKIT_RC"]
    ready: Literal[True]
    handoff_ready: Literal[True]
    candidate_version: RcVersion
    source_repository: Literal["https://github.com/alchymia-labs/custos"]
    source_commit: SourceCommit
    source_date_epoch: StrictInt = Field(ge=315_532_800)
    publication_receipt_url: NonEmptyString
    publication_receipt_sha256: Sha256Hex
    publication_receipt_size_bytes: StrictInt = Field(gt=0)
    publication_receipt: ToolkitRcPublicationReceiptV1
    toolkit_manifest: ToolkitRcReceiptManifestV1
    toolkit_manifest_sha256: Sha256Hex
    build_manifest_sha256: Sha256Hex
    predecessor_pending_receipt: ImmutableToolkitArtifactBindingV1
    production_credentials_used: Literal[True]
    production_signature_verified: Literal[True]
    remote_publication_verified: Literal[True]
    authority_registered: Literal[True]
    final_blockers: tuple[NonEmptyString, ...] = Field(max_length=0)
    handoff_scope: Literal["Custos base and Nautilus toolkit RC only"]
    loaded: Literal[False]
    engine_ready: Literal[False]
    runtime_ready: Literal[False]
    production_ready: Literal[False]
    strategy_release_bom_created: Literal[False]

    @model_validator(mode="after")
    def validate_ready_cross_bindings(self) -> Self:
        publication = self.publication_receipt
        if (
            publication.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
            or not publication.production_credentials_used
            or not publication.production_signature_verified
            or publication.candidate_version != self.candidate_version
            or publication.source_commit != self.source_commit
            or publication.source_date_epoch != self.source_date_epoch
            or self.toolkit_manifest.candidate_version != self.candidate_version
        ):
            raise ValueError("READY toolkit receipt production evidence differs")
        if any(
            member.source_repository != self.source_repository
            or member.source_commit != self.source_commit
            for member in self.toolkit_manifest.members
        ):
            raise ValueError("READY toolkit manifest source authority differs")
        published_coordinates = {item.coordinate for item in publication.objects}
        required_coordinates = {
            binding.coordinate
            for member in self.toolkit_manifest.members
            for binding in (
                member.wheel,
                member.sbom,
                member.contract_schema,
                member.contract_asset_index,
                member.dependency_lock_evidence,
                member.slsa_provenance,
                member.sigstore_attestation,
                member.t4_zero_rewrite_receipt,
                member.t4b_typing_closure_receipt,
                member.t5_pre_import_verifier_receipt,
            )
        }
        if not required_coordinates.issubset(published_coordinates):
            raise ValueError("READY toolkit receipt omits manifest-bound remote objects")
        return self


class ToolkitRcAuthorityReceiptV1(
    RootModel[
        Annotated[
            ToolkitRcAuthorityPendingReceiptV1 | ToolkitRcAuthorityReadyReceiptV1,
            Field(discriminator="status"),
        ]
    ]
):
    model_config = ConfigDict(frozen=True, title="ToolkitRcAuthorityReceiptV1")


class ToolkitRcOciDescriptorV1(_StrictFrozenModel):
    media_type: NonEmptyString
    digest: Sha256Digest
    size_bytes: StrictInt = Field(gt=0)
    title: NonEmptyString
    role: NonEmptyString
    source_coordinate: NonEmptyString | None = None


class ToolkitRcOciPublicationReceiptV1(_StrictFrozenModel):
    """Digest-authoritative OCI publication evidence before authority registration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="ToolkitRcOciPublicationReceiptV1",
        json_schema_extra={
            "$id": (
                "https://custos.the-alephain-guild/contracts/"
                "toolkit-rc-oci-publication-receipt-v1.schema.json"
            )
        },
    )

    schema_version: Literal[1] = 1
    contract_version: Literal["alephain.custos.toolkit-rc-oci-publication-receipt.v1"] = (
        "alephain.custos.toolkit-rc-oci-publication-receipt.v1"
    )
    status: Literal[
        "PENDING_T6D_RELEASE_RUNNER",
        "PENDING_T6E_AUTHORITY_REGISTRATION",
    ]
    ready: Literal[False] = False
    handoff_ready: Literal[False] = False
    candidate_version: RcVersion
    source_repository: Literal["https://github.com/alchymia-labs/custos"] = (
        "https://github.com/alchymia-labs/custos"
    )
    source_commit: SourceCommit
    source_date_epoch: StrictInt = Field(ge=315_532_800)
    artifact_type: Literal["application/vnd.alephain.custos.strategy-toolkit.rc.v1"] = (
        "application/vnd.alephain.custos.strategy-toolkit.rc.v1"
    )
    manifest_media_type: Literal["application/vnd.oci.image.manifest.v1+json"] = (
        "application/vnd.oci.image.manifest.v1+json"
    )
    registry: NonEmptyString
    repository: NonEmptyString
    tag: RcVersion
    oci_coordinate: NonEmptyString
    manifest_digest: Sha256Digest
    manifest_size_bytes: StrictInt = Field(gt=0)
    config: ToolkitRcOciDescriptorV1
    layers: tuple[ToolkitRcOciDescriptorV1, ...] = Field(min_length=1)
    publication_atomic: Literal[True] = True
    manifest_commit_verified: Literal[True] = True
    descriptor_readback_verified: Literal[True] = True
    tag_readback_verified: Literal[True] = True
    production_credentials_used: StrictBool
    production_signature_verified: StrictBool
    workflow_ref: (
        Literal["alchymia-labs/custos/.github/workflows/release-toolkit-rc.yml@refs/heads/main"]
        | None
    )
    workflow_identity: (
        Literal[
            "https://github.com/alchymia-labs/custos/.github/workflows/"
            "release-toolkit-rc.yml@refs/heads/main"
        ]
        | None
    )
    oidc_issuer: Literal["https://token.actions.githubusercontent.com"] | None
    release_environment: Literal["toolkit-rc-release"] | None
    workflow_run_id: StrictInt | None = Field(default=None, gt=0)
    workflow_run_attempt: StrictInt | None = Field(default=None, gt=0)
    authority_registered: Literal[False] = False

    @model_validator(mode="after")
    def validate_oci_publication(self) -> Self:
        if (
            "://" in self.registry
            or "/" in self.registry
            or self.repository.startswith(("/", "."))
            or self.repository.endswith("/")
            or self.tag != self.candidate_version
            or self.oci_coordinate != f"{self.registry}/{self.repository}@{self.manifest_digest}"
        ):
            raise ValueError("OCI publication coordinate differs")
        if (
            self.config.role != "release_config"
            or self.config.source_coordinate is not None
            or self.config.media_type
            != "application/vnd.alephain.custos.strategy-toolkit.rc.config.v1+json"
        ):
            raise ValueError("OCI publication config descriptor differs")
        roles = [layer.role for layer in self.layers]
        if len(roles) != len(set(roles)) or any(
            layer.source_coordinate is None for layer in self.layers
        ):
            raise ValueError("OCI publication layer matrix differs")
        identities = (
            self.workflow_ref,
            self.workflow_identity,
            self.oidc_issuer,
            self.release_environment,
            self.workflow_run_id,
            self.workflow_run_attempt,
        )
        if self.production_credentials_used:
            if (
                self.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
                or not self.production_signature_verified
                or any(value is None for value in identities)
            ):
                raise ValueError("production OCI publication lacks workflow evidence")
        elif (
            self.status != "PENDING_T6D_RELEASE_RUNNER"
            or self.production_signature_verified
            or any(value is not None for value in identities)
        ):
            raise ValueError("local OCI publication claims production evidence")
        return self


class ToolkitRcAuthorityReadyReceiptV2(_StrictFrozenModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        title="ToolkitRcAuthorityReadyReceiptV2",
        json_schema_extra={
            "$id": (
                "https://custos.the-alephain-guild/contracts/"
                "toolkit-rc-authority-receipt-v2.schema.json"
            )
        },
    )

    receipt_schema_version: Literal[2] = 2
    contract_version: Literal["alephain.custos.toolkit-rc-authority-receipt.v2"] = (
        "alephain.custos.toolkit-rc-authority-receipt.v2"
    )
    status: Literal["READY_TOOLKIT_RC"] = "READY_TOOLKIT_RC"
    ready: Literal[True] = True
    handoff_ready: Literal[True] = True
    candidate_version: RcVersion
    source_repository: Literal["https://github.com/alchymia-labs/custos"] = (
        "https://github.com/alchymia-labs/custos"
    )
    source_commit: SourceCommit
    source_date_epoch: StrictInt = Field(ge=315_532_800)
    publication_receipt: ToolkitRcOciPublicationReceiptV1
    toolkit_manifest: ToolkitRcReceiptManifestV1
    toolkit_manifest_sha256: Sha256Hex
    build_manifest_sha256: Sha256Hex
    predecessor_oci_manifest: ImmutableToolkitArtifactBindingV1
    production_credentials_used: Literal[True] = True
    production_signature_verified: Literal[True] = True
    remote_publication_verified: Literal[True] = True
    authority_registered: Literal[True] = True
    final_blockers: tuple[NonEmptyString, ...] = Field(max_length=0)
    handoff_scope: Literal["Custos base and Nautilus toolkit RC only"] = (
        "Custos base and Nautilus toolkit RC only"
    )
    loaded: Literal[False] = False
    engine_ready: Literal[False] = False
    runtime_ready: Literal[False] = False
    production_ready: Literal[False] = False
    strategy_release_bom_created: Literal[False] = False

    @model_validator(mode="after")
    def validate_ready_cross_bindings(self) -> Self:
        publication = self.publication_receipt
        manifest_digest = publication.manifest_digest.removeprefix("sha256:")
        if (
            publication.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
            or not publication.production_credentials_used
            or not publication.production_signature_verified
            or publication.candidate_version != self.candidate_version
            or publication.source_commit != self.source_commit
            or publication.source_date_epoch != self.source_date_epoch
            or self.toolkit_manifest.candidate_version != self.candidate_version
            or self.predecessor_oci_manifest.coordinate != publication.oci_coordinate
            or self.predecessor_oci_manifest.sha256 != manifest_digest
            or self.predecessor_oci_manifest.size_bytes != publication.manifest_size_bytes
        ):
            raise ValueError("READY OCI toolkit authority bindings differ")
        if any(
            member.source_repository != self.source_repository
            or member.source_commit != self.source_commit
            for member in self.toolkit_manifest.members
        ):
            raise ValueError("READY toolkit manifest source authority differs")
        published_coordinates = {
            layer.source_coordinate
            for layer in publication.layers
            if layer.source_coordinate is not None
        }
        required_coordinates = {
            binding.coordinate
            for member in self.toolkit_manifest.members
            for binding in (
                member.wheel,
                member.sbom,
                member.contract_schema,
                member.contract_asset_index,
                member.dependency_lock_evidence,
                member.slsa_provenance,
                member.sigstore_attestation,
                member.t4_zero_rewrite_receipt,
                member.t4b_typing_closure_receipt,
                member.t5_pre_import_verifier_receipt,
            )
        }
        if not required_coordinates.issubset(published_coordinates):
            raise ValueError("READY OCI toolkit receipt omits manifest-bound layers")
        return self


class ToolkitRcAuthorityReceiptV2(RootModel[ToolkitRcAuthorityReadyReceiptV2]):
    model_config = ConfigDict(frozen=True, title="ToolkitRcAuthorityReceiptV2")


__all__ = [
    "ImmutableToolkitArtifactBindingV1",
    "LockedToolkitDependencyV1",
    "ToolkitRcMemberRole",
    "ToolkitRcMemberV1",
    "ToolkitRcReceiptManifestV1",
    "ToolkitRcCycloneDxSbomV1",
    "ToolkitRcT6dPendingReceiptV1",
    "ToolkitRcPublicationObjectV1",
    "ToolkitRcPublicationReceiptV1",
    "ToolkitRcAuthorityPendingReceiptV1",
    "ToolkitRcAuthorityReadyReceiptV1",
    "ToolkitRcAuthorityReceiptV1",
    "ToolkitRcOciDescriptorV1",
    "ToolkitRcOciPublicationReceiptV1",
    "ToolkitRcAuthorityReadyReceiptV2",
    "ToolkitRcAuthorityReceiptV2",
]
