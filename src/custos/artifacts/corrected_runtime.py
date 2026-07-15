from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from custos_toolkit.contracts.strategy_execution import (
    DevelopmentSourceRefV1,
    FrozenJsonObject,
    RunnerLocalArtifactPolicyDecisionV1,
    StrategyArtifactPreImportVerificationReceiptV2,
    StrategyExecutionContextV1,
    canonical_json_bytes,
    canonical_json_digest,
    deep_freeze_json,
)

from custos.artifacts.archive import QuarantinedWheel, quarantine_wheel
from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.policy import ArchiveLimitsV1, verify_signed_release_policy
from custos.artifacts.production_pre_import import RunnerLocalArtifactVerificationConfig
from custos.artifacts.verifier import (
    DigestSubject,
    SigstoreVerificationEvidence,
    SigstoreVerificationRequest,
    SigstoreVerifierCapability,
)
from custos.contracts.crucible_runner_command import CrucibleRunnerDeploymentCommandV1

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArtifactRuntimeBlocked(RuntimeError):
    """The corrected verifier is present but external production receipts are absent."""


class ArtifactRuntimeActivationError(RuntimeError):
    """A verified artifact could not become a durable visible activation."""


@dataclass(frozen=True, slots=True)
class CorrectedRuntimeCapability:
    status: Literal["PREPARED_BLOCKED", "READY_EXTERNAL_RECEIPTS"]
    ps_bundle_receipt_digest: str | None
    crucible_c6_receipt_digest: str | None

    @classmethod
    def prepared_blocked(cls) -> CorrectedRuntimeCapability:
        return cls(
            status="PREPARED_BLOCKED",
            ps_bundle_receipt_digest=None,
            crucible_c6_receipt_digest=None,
        )

    @classmethod
    def from_external_receipts(
        cls,
        *,
        ps_bundle_receipt_digest: str,
        crucible_c6_receipt_digest: str,
    ) -> CorrectedRuntimeCapability:
        for value, label in (
            (ps_bundle_receipt_digest, "PS-specific bundle receipt"),
            (crucible_c6_receipt_digest, "Crucible C6 receipt"),
        ):
            if not _SHA256.fullmatch(value):
                raise ValueError(f"{label} digest must be lowercase SHA-256")
        return cls(
            status="READY_EXTERNAL_RECEIPTS",
            ps_bundle_receipt_digest=ps_bundle_receipt_digest,
            crucible_c6_receipt_digest=crucible_c6_receipt_digest,
        )

    @property
    def ready(self) -> bool:
        return (
            self.status == "READY_EXTERNAL_RECEIPTS"
            and self.ps_bundle_receipt_digest is not None
            and self.crucible_c6_receipt_digest is not None
        )


@dataclass(frozen=True, slots=True)
class CorrectedArtifactRuntimeConfig:
    local_verification: RunnerLocalArtifactVerificationConfig
    activation_parent: Path
    capability: CorrectedRuntimeCapability

    def __post_init__(self) -> None:
        if not self.activation_parent.is_absolute():
            raise ValueError("runner-local activation parent must be an absolute path")


@dataclass(frozen=True, slots=True)
class CorrectedVerifiedMember:
    role: str
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    path: Path


@dataclass(frozen=True, slots=True)
class PreparedStrategyArtifact:
    command: CrucibleRunnerDeploymentCommandV1
    activation_id: str
    receipt: StrategyArtifactPreImportVerificationReceiptV2
    verified_members: tuple[CorrectedVerifiedMember, ...]
    quarantine_root: Path
    verified_entry_point: str
    effective_config: FrozenJsonObject
    execution_context: StrategyExecutionContextV1


@dataclass(frozen=True, slots=True)
class ActivatedStrategyArtifact:
    prepared: PreparedStrategyArtifact
    activation_root: Path
    strategy: object


RuntimeArtifactSource: TypeAlias = PreparedStrategyArtifact | DevelopmentSourceRefV1


class DurableArtifactRuntimeState(Protocol):
    async def load_durable_desired_command(self, deployment_instance_id: UUID) -> Any: ...

    async def stage_artifact_activation(self, **kwargs: Any) -> None: ...

    async def mark_artifact_activation_active(self, **kwargs: Any) -> None: ...

    async def quarantine_artifact_activation(self, **kwargs: Any) -> None: ...


class CorrectedMemberVerifier(Protocol):
    def verify(
        self,
        release_bom: Mapping[str, object],
        member_paths: Mapping[str, Path],
    ) -> tuple[CorrectedVerifiedMember, ...]: ...


class ArtifactQuarantineCapability(Protocol):
    def quarantine(
        self,
        *,
        wheel_path: Path,
        entry_point_group: str,
        entry_point: str,
        limits: ArchiveLimitsV1,
        quarantine_parent: Path,
    ) -> QuarantinedWheel: ...


class RuntimeEntryPointLoader(Protocol):
    def load(
        self,
        *,
        activation_root: Path,
        entry_point: str,
        effective_config: FrozenJsonObject,
        execution_context: StrategyExecutionContextV1,
    ) -> object: ...


def _strict_json_object(payload: bytes, label: str) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            f"{label} is not strict UTF-8 JSON",
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != payload:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            f"{label} is not an exact canonical JSON object",
        )
    return value


def _read_stable_member(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_UNSTABLE,
            f"BOM member is not a stable regular file: {label}",
        )
    before = path.stat()
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_UNSTABLE,
            f"BOM member cannot be read: {label}",
        ) from error
    after = path.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or len(payload) != after.st_size:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_UNSTABLE,
            f"BOM member changed while being read: {label}",
        )
    return payload


def verify_full_bom_member_files(
    release_bom: Mapping[str, object],
    member_paths: Mapping[str, Path],
) -> tuple[CorrectedVerifiedMember, ...]:
    """Derive the only member table from the full PS BOM and verify every byte."""

    members = release_bom.get("members")
    if not isinstance(members, list) or not members:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_SET_MISMATCH,
            "full release BOM members must be a non-empty array",
        )
    expected_names = {
        member.get("name") for member in members if isinstance(member, Mapping)
    }
    if (
        len(expected_names) != len(members)
        or any(not isinstance(name, str) or not name for name in expected_names)
        or set(member_paths) != expected_names
    ):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_SET_MISMATCH,
            "member paths must exactly match names derived from the full release BOM",
        )
    verified: list[CorrectedVerifiedMember] = []
    for raw in members:
        if not isinstance(raw, Mapping):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_SET_MISMATCH,
                "release BOM member is not an object",
            )
        name = cast(str, raw["name"])
        role = raw.get("role")
        media_type = raw.get("media_type")
        size_bytes = raw.get("size_bytes")
        digest = raw.get("sha256")
        if (
            not isinstance(role, str)
            or not isinstance(media_type, str)
            or type(size_bytes) is not int
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_SET_MISMATCH,
                f"release BOM member metadata is invalid: {name}",
            )
        path = member_paths[name]
        payload = _read_stable_member(path, label=name)
        if len(payload) != size_bytes or hashlib.sha256(payload).hexdigest() != digest:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_SET_MISMATCH,
                f"release BOM member bytes differ: {name}",
            )
        verified.append(
            CorrectedVerifiedMember(
                role=role,
                name=name,
                media_type=media_type,
                size_bytes=size_bytes,
                sha256=digest,
                path=path,
            )
        )
    return tuple(verified)


class FullBomMemberVerifier:
    def verify(
        self,
        release_bom: Mapping[str, object],
        member_paths: Mapping[str, Path],
    ) -> tuple[CorrectedVerifiedMember, ...]:
        return verify_full_bom_member_files(release_bom, member_paths)


class ProductionArtifactQuarantiner:
    def quarantine(
        self,
        *,
        wheel_path: Path,
        entry_point_group: str,
        entry_point: str,
        limits: ArchiveLimitsV1,
        quarantine_parent: Path,
    ) -> QuarantinedWheel:
        return quarantine_wheel(
            wheel_path,
            entry_point_group=entry_point_group,
            entry_point=entry_point,
            limits=limits,
            quarantine_parent=quarantine_parent,
        )


def _statement_subjects(statement: Mapping[str, object]) -> tuple[DigestSubject, ...]:
    raw_subjects = statement.get("subject")
    if not isinstance(raw_subjects, list) or not raw_subjects:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            "release statement has no signed subjects",
        )
    subjects: list[DigestSubject] = []
    for raw in raw_subjects:
        if not isinstance(raw, Mapping):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
                "release statement subject is not an object",
            )
        name = raw.get("name")
        digest = raw.get("digest")
        sha256 = digest.get("sha256") if isinstance(digest, Mapping) else None
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
        ):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
                "release statement subject lacks exact SHA-256",
            )
        subjects.append(DigestSubject(name=name, sha256=sha256))
    if len({item.name for item in subjects}) != len(subjects):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            "release statement subject names are duplicated",
        )
    return tuple(subjects)


def _validate_sigstore_against_crucible(
    evidence: SigstoreVerificationEvidence,
    request: SigstoreVerificationRequest,
    command: CrucibleRunnerDeploymentCommandV1,
) -> None:
    claims = command.artifact_evidence.get("signed_producer_claims")
    proof = command.artifact_evidence.get("sigstore_proof")
    if not isinstance(claims, Mapping) or not isinstance(proof, Mapping):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            "Crucible evidence lacks signed producer claims or Sigstore proof",
        )
    expected_identity = (
        proof.get("issuer"),
        claims.get("workflow_identity"),
        claims.get("producer_repository"),
    )
    actual_identity = (
        evidence.issuer,
        evidence.workflow_identity,
        evidence.source_repository,
    )
    expected_subjects = {(item.name, item.sha256) for item in request.required_subjects}
    actual_subjects = {(item.name, item.sha256) for item in evidence.verified_subjects}
    if (
        evidence.verifier_capability_id == ""
        or evidence.bundle_sha256 != command.artifact_attestation_ref.get("bundle_sha256")
        or evidence.bundle_sha256 != proof.get("bundle_sha256")
        or evidence.trusted_root_sha256
        != hashlib.sha256(request.trusted_root_bytes).hexdigest()
        or actual_identity != expected_identity
        or actual_identity
        not in {
            (item.issuer, item.workflow_identity, item.source_repository)
            for item in request.accepted_identities
        }
        or actual_subjects != expected_subjects
        or not evidence.transparency_log_verified
    ):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            "detached bundle verification differs from local policy or Crucible evidence",
        )


class CorrectedArtifactRuntime:
    def __init__(
        self,
        *,
        state: DurableArtifactRuntimeState,
        config: CorrectedArtifactRuntimeConfig,
        sigstore_verifier: SigstoreVerifierCapability,
        member_verifier: CorrectedMemberVerifier | None = None,
        quarantiner: ArtifactQuarantineCapability | None = None,
    ) -> None:
        self._state = state
        self._config = config
        self._sigstore_verifier = sigstore_verifier
        self._member_verifier = member_verifier or FullBomMemberVerifier()
        self._quarantiner = quarantiner or ProductionArtifactQuarantiner()

    @property
    def capability_ready(self) -> bool:
        return self._config.capability.ready

    async def prepare(
        self,
        *,
        deployment_instance_id: UUID,
        release_statement_bytes: bytes,
        detached_bundle_path: Path,
        member_paths: Mapping[str, Path],
        verified_at: datetime,
    ) -> PreparedStrategyArtifact:
        durable = await self._state.load_durable_desired_command(deployment_instance_id)
        command = durable.command
        if not isinstance(command, CrucibleRunnerDeploymentCommandV1):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.COMMAND_BINDING_INVALID,
                "T5e requires the T4 durable CR89 command model",
            )
        if command.deployment_instance_id != deployment_instance_id:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.COMMAND_BINDING_INVALID,
                "durable desired command differs from requested deployment instance",
            )

        local = self._config.local_verification
        verified_policy = verify_signed_release_policy(
            local.signed_policy_envelope_bytes,
            authority_key_id=local.policy_authority_key_id,
            authority_public_key=local.policy_authority_public_key,
            sigstore_trusted_root_bytes=local.sigstore_trusted_root_bytes,
            now=verified_at,
        )
        crucible_policy = command.artifact_evidence.get("local_policy_evaluation")
        if isinstance(crucible_policy, Mapping) and (
            crucible_policy.get("policy_digest") == verified_policy.policy_digest
        ):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.POLICY_BINDING_MISMATCH,
                "runner-local release policy must remain independent from Crucible policy",
            )

        statement = _strict_json_object(release_statement_bytes, "release statement")
        statement_digest = hashlib.sha256(release_statement_bytes).hexdigest()
        if statement_digest != command.artifact_attestation_ref.get("statement_sha256"):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
                "release statement bytes differ from detached attestation reference",
            )
        bundle_bytes = _read_stable_member(detached_bundle_path, label="detached bundle")
        if (
            hashlib.sha256(bundle_bytes).hexdigest()
            != command.artifact_attestation_ref.get("bundle_sha256")
        ):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
                "detached bundle bytes differ from detached attestation reference",
            )

        verified_members = self._member_verifier.verify(command.release_bom, member_paths)
        strategy_wheels = [item for item in verified_members if item.role == "strategy_wheel"]
        if len(strategy_wheels) != 1:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_SET_MISMATCH,
                "full release BOM must resolve one verified strategy wheel",
            )
        subjects = _statement_subjects(statement)
        sigstore_request = SigstoreVerificationRequest(
            bundle_path=detached_bundle_path,
            trusted_root_bytes=local.sigstore_trusted_root_bytes,
            accepted_identities=verified_policy.policy.accepted_identities,
            required_subjects=subjects,
            quarantine_parent=local.quarantine_parent,
        )
        try:
            sigstore_evidence = self._sigstore_verifier.verify(sigstore_request)
        except ArtifactVerificationError:
            raise
        except Exception as error:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_VERIFICATION_FAILED,
                "detached bundle verifier failed",
            ) from error
        _validate_sigstore_against_crucible(sigstore_evidence, sigstore_request, command)

        entry_point_group = command.release_bom.get("entry_point_group")
        entry_point = command.release_bom.get("entry_point_name")
        if not isinstance(entry_point_group, str) or not isinstance(entry_point, str):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MANIFEST_INVALID,
                "full release BOM lacks the typed strategy entry point",
            )
        quarantined = self._quarantiner.quarantine(
            wheel_path=strategy_wheels[0].path,
            entry_point_group=entry_point_group,
            entry_point=entry_point,
            limits=verified_policy.policy.archive_limits,
            quarantine_parent=local.quarantine_parent,
        )

        artifact_ref_digest = command.artifact_ref_digest
        acceptance_digest = command.artifact_acceptance_receipt.get("receipt_digest")
        if not isinstance(acceptance_digest, str) or not _SHA256.fullmatch(acceptance_digest):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.COMMAND_BINDING_INVALID,
                "Crucible acceptance receipt digest is absent",
            )
        policy_decision = RunnerLocalArtifactPolicyDecisionV1(
            authority="custos-runner-local",
            policy_id=verified_policy.policy.policy_id,
            policy_version=verified_policy.policy.version,
            policy_digest=verified_policy.policy_digest,
            evaluated_at=verified_at,
            decision="accepted",
            release_bom_digest=command.release_bom_digest,
            artifact_ref_digest=artifact_ref_digest,
            artifact_evidence_digest=command.artifact_evidence_digest,
            artifact_acceptance_receipt_digest=acceptance_digest,
        )
        receipt = StrategyArtifactPreImportVerificationReceiptV2(
            verification_profile="custos-artifact-pre-import-verification-v2",
            verified_at=verified_at,
            release_bom=command.release_bom,
            release_bom_digest=command.release_bom_digest,
            release_statement=statement,
            release_statement_digest=statement_digest,
            artifact_ref=command.artifact_ref,
            artifact_ref_digest=artifact_ref_digest,
            detached_attestation_ref=command.artifact_attestation_ref,
            detached_attestation_ref_digest=canonical_json_digest(
                command.artifact_attestation_ref
            ),
            crucible_artifact_evidence=command.artifact_evidence,
            crucible_artifact_evidence_digest=command.artifact_evidence_digest,
            crucible_artifact_acceptance=command.artifact_acceptance_receipt,
            crucible_artifact_acceptance_receipt_digest=acceptance_digest,
            runner_local_policy_decision=policy_decision,
        )
        frozen = deep_freeze_json(command.effective_config)
        if not isinstance(frozen, Mapping):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.COMMAND_BINDING_INVALID,
                "effective configuration is not a JSON object",
            )
        execution_context = StrategyExecutionContextV1(
            engine="nautilus",
            trading_mode=command.trading_mode,
            deployment_instance_id=command.deployment_instance_id,
            deployment_spec_id=command.deployment_spec_id,
            deployment_spec_digest=command.deployment_spec_digest,
            effective_config_digest=command.effective_config_digest,
            generation=command.generation,
        )
        activation_id = str(
            uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        "custos-corrected-artifact-activation-v1",
                        str(command.deployment_instance_id),
                        str(command.deployment_spec_id),
                        str(command.generation),
                        command.artifact_ref.artifact_sha256,
                    )
                ),
            )
        )
        return PreparedStrategyArtifact(
            command=command,
            activation_id=activation_id,
            receipt=receipt,
            verified_members=verified_members,
            quarantine_root=quarantined.root,
            verified_entry_point=quarantined.verified_entry_point,
            effective_config=cast(FrozenJsonObject, frozen),
            execution_context=execution_context,
        )

    async def activate(
        self,
        prepared: PreparedStrategyArtifact,
        *,
        loader: RuntimeEntryPointLoader,
    ) -> ActivatedStrategyArtifact:
        if not self._config.capability.ready:
            raise ArtifactRuntimeBlocked(
                "PS-specific bundle and Crucible C6 receipts are absent; "
                "corrected production runtime remains PREPARED_BLOCKED"
            )
        command = prepared.command
        parent = self._config.activation_parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        activation_root = parent / prepared.activation_id
        if activation_root.exists():
            raise ArtifactRuntimeActivationError("immutable activation path already exists")
        await self._state.stage_artifact_activation(
            command=command,
            activation_id=prepared.activation_id,
            artifact_ref_digest=command.artifact_ref_digest,
            artifact_evidence_digest=command.artifact_evidence_digest,
        )
        try:
            os.replace(prepared.quarantine_root, activation_root)
            await self._state.mark_artifact_activation_active(
                command=command,
                activation_id=prepared.activation_id,
            )
        except Exception as error:
            recovery_root = (
                self._config.local_verification.quarantine_parent
                / f"activation-failed-{prepared.activation_id}"
            )
            try:
                if activation_root.exists() and not recovery_root.exists():
                    os.replace(activation_root, recovery_root)
            finally:
                await self._state.quarantine_artifact_activation(
                    command=command,
                    activation_id=prepared.activation_id,
                    reason="durable_activation_commit_failed",
                )
            raise ArtifactRuntimeActivationError(
                "durable activation failed before Python import"
            ) from error

        try:
            strategy = loader.load(
                activation_root=activation_root,
                entry_point=prepared.verified_entry_point,
                effective_config=prepared.effective_config,
                execution_context=prepared.execution_context,
            )
        except Exception as error:
            await self._state.quarantine_artifact_activation(
                command=command,
                activation_id=prepared.activation_id,
                reason="verified_entry_point_load_failed",
            )
            raise ArtifactRuntimeActivationError(
                "verified entry point failed after durable activation"
            ) from error
        return ActivatedStrategyArtifact(
            prepared=prepared,
            activation_root=activation_root,
            strategy=strategy,
        )


__all__ = [
    "ActivatedStrategyArtifact",
    "ArtifactRuntimeActivationError",
    "ArtifactRuntimeBlocked",
    "CorrectedArtifactRuntime",
    "CorrectedArtifactRuntimeConfig",
    "CorrectedRuntimeCapability",
    "CorrectedVerifiedMember",
    "PreparedStrategyArtifact",
    "RuntimeArtifactSource",
    "verify_full_bom_member_files",
]
