from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from custos_toolkit.contracts.strategy_execution import (
    ArtifactMemberRole,
    StrategyExecutionCommandBindingV1,
    StrategyManifestV1,
    canonical_model_digest,
)
from pydantic import ValidationError

from custos.artifacts.archive import quarantine_wheel
from custos.artifacts.bom import VerifiedArtifactMember, verify_release_bom_and_members
from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.policy import (
    SigstoreIdentityV1,
    verify_signed_release_policy,
)


@dataclass(frozen=True, slots=True)
class DigestSubject:
    name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class SigstoreVerificationRequest:
    bundle_path: Path
    trusted_root_bytes: bytes
    accepted_identities: tuple[SigstoreIdentityV1, ...]
    required_subjects: tuple[DigestSubject, ...]
    quarantine_parent: Path


@dataclass(frozen=True, slots=True)
class SigstoreVerificationEvidence:
    verifier_capability_id: str
    bundle_sha256: str
    trusted_root_sha256: str
    issuer: str
    workflow_identity: str
    source_repository: str
    verified_subjects: tuple[DigestSubject, ...]
    transparency_log_verified: bool


class SigstoreVerifierCapability(Protocol):
    """Injected cryptographic capability; production composition must provide it."""

    capability_id: str

    def verify(self, request: SigstoreVerificationRequest) -> SigstoreVerificationEvidence: ...


@dataclass(frozen=True, slots=True)
class PreImportVerificationRequest:
    command_binding: StrategyExecutionCommandBindingV1
    release_bom_bytes: bytes
    member_paths: Mapping[str, Path]
    signed_policy_envelope_bytes: bytes
    policy_authority_key_id: str
    policy_authority_public_key: Ed25519PublicKey
    sigstore_trusted_root_bytes: bytes
    quarantine_parent: Path
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class PreImportVerificationResult:
    verification_profile: str
    verified_at: datetime
    command_binding_digest: str
    artifact_ref_digest: str
    release_bom_digest: str
    verified_members: tuple[VerifiedArtifactMember, ...]
    local_trust_policy_id: str
    local_trust_policy_version: int
    local_trust_policy_digest: str
    trusted_root_digest: str
    sigstore: SigstoreVerificationEvidence
    verified_entry_point: str
    quarantine_root: Path


def _only_member(
    members: tuple[VerifiedArtifactMember, ...], role: ArtifactMemberRole
) -> VerifiedArtifactMember:
    matches = [member for member in members if member.role is role]
    if len(matches) != 1:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_SET_MISMATCH,
            f"release member set must contain exactly one {role.value}",
        )
    return matches[0]


def _read_verified_member(member: VerifiedArtifactMember) -> bytes:
    try:
        payload = member.path.read_bytes()
    except OSError as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_UNSTABLE,
            f"verified member cannot be reread: {member.name}",
        ) from error
    if len(payload) != member.size_bytes or hashlib.sha256(payload).hexdigest() != member.sha256:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_UNSTABLE,
            f"verified member changed after BOM verification: {member.name}",
        )
    return payload


def _validate_sigstore_evidence(
    evidence: SigstoreVerificationEvidence,
    request: SigstoreVerificationRequest,
    *,
    expected_bundle_digest: str,
    expected_identity: tuple[str, str, str],
    require_transparency_log: bool,
) -> None:
    actual_identity = (
        evidence.issuer,
        evidence.workflow_identity,
        evidence.source_repository,
    )
    accepted = {
        (identity.issuer, identity.workflow_identity, identity.source_repository)
        for identity in request.accepted_identities
    }
    expected_subjects = {(subject.name, subject.sha256) for subject in request.required_subjects}
    actual_subjects = {(subject.name, subject.sha256) for subject in evidence.verified_subjects}
    mismatched = (
        not evidence.verifier_capability_id
        or evidence.bundle_sha256 != expected_bundle_digest
        or evidence.trusted_root_sha256 != hashlib.sha256(request.trusted_root_bytes).hexdigest()
        or actual_identity != expected_identity
        or actual_identity not in accepted
        or actual_subjects != expected_subjects
        or (require_transparency_log and not evidence.transparency_log_verified)
    )
    if mismatched:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_EVIDENCE_MISMATCH,
            "Sigstore verifier evidence does not match policy and command-bound subjects",
        )


class ArtifactVerifierKernel:
    def __init__(self, *, sigstore_verifier: SigstoreVerifierCapability | None) -> None:
        self._sigstore_verifier = sigstore_verifier

    def verify(self, request: PreImportVerificationRequest) -> PreImportVerificationResult:
        if self._sigstore_verifier is None:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_VERIFIER_UNAVAILABLE,
                "production Sigstore verifier capability is not configured",
            )
        verified_policy = verify_signed_release_policy(
            request.signed_policy_envelope_bytes,
            authority_key_id=request.policy_authority_key_id,
            authority_public_key=request.policy_authority_public_key,
            sigstore_trusted_root_bytes=request.sigstore_trusted_root_bytes,
            now=request.verified_at,
        )
        attestation = request.command_binding.artifact_ref.attestation
        expected_policy = (
            attestation.trust_policy_id,
            attestation.trust_policy_version,
            attestation.trust_policy_digest,
        )
        local_policy = (
            verified_policy.policy.policy_id,
            verified_policy.policy.version,
            verified_policy.policy_digest,
        )
        if local_policy != expected_policy:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.POLICY_BINDING_MISMATCH,
                "artifact attestation policy binding differs from signed local policy",
            )

        verified_bom = verify_release_bom_and_members(
            bom_bytes=request.release_bom_bytes,
            command_binding=request.command_binding,
            member_paths=request.member_paths,
        )
        strategy_wheel = _only_member(verified_bom.members, ArtifactMemberRole.STRATEGY_WHEEL)
        manifest_member = _only_member(
            verified_bom.members, ArtifactMemberRole.STRATEGY_MANIFEST
        )
        bundle_member = _only_member(
            verified_bom.members, ArtifactMemberRole.ATTESTATION_BUNDLE
        )
        manifest_bytes = _read_verified_member(manifest_member)
        try:
            manifest = StrategyManifestV1.model_validate_json(manifest_bytes)
        except (ValidationError, ValueError) as error:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MANIFEST_INVALID,
                "strategy manifest does not match the coordinated strict contract",
            ) from error

        required_subjects = (
            DigestSubject("strategy_release_bom", verified_bom.release_bom_digest),
            DigestSubject(strategy_wheel.name, strategy_wheel.sha256),
            DigestSubject(manifest_member.name, manifest_member.sha256),
        )
        sigstore_request = SigstoreVerificationRequest(
            bundle_path=bundle_member.path,
            trusted_root_bytes=request.sigstore_trusted_root_bytes,
            accepted_identities=verified_policy.policy.accepted_identities,
            required_subjects=required_subjects,
            quarantine_parent=request.quarantine_parent,
        )
        try:
            sigstore_evidence = self._sigstore_verifier.verify(sigstore_request)
        except ArtifactVerificationError:
            raise
        except Exception as error:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.SIGSTORE_VERIFICATION_FAILED,
                "Sigstore cryptographic verification capability failed",
            ) from error
        expected_identity = (
            attestation.issuer,
            attestation.workflow_identity,
            attestation.source_repository,
        )
        _validate_sigstore_evidence(
            sigstore_evidence,
            sigstore_request,
            expected_bundle_digest=bundle_member.sha256,
            expected_identity=expected_identity,
            require_transparency_log=verified_policy.policy.require_transparency_log,
        )

        quarantined = quarantine_wheel(
            strategy_wheel.path,
            entry_point_group=manifest.entry_point_group,
            entry_point=manifest.entry_point,
            limits=verified_policy.policy.archive_limits,
            quarantine_parent=request.quarantine_parent,
        )
        return PreImportVerificationResult(
            verification_profile="custos-artifact-pre-import-internal-v1",
            verified_at=request.verified_at,
            command_binding_digest=canonical_model_digest(request.command_binding),
            artifact_ref_digest=canonical_model_digest(request.command_binding.artifact_ref),
            release_bom_digest=verified_bom.release_bom_digest,
            verified_members=verified_bom.members,
            local_trust_policy_id=verified_policy.policy.policy_id,
            local_trust_policy_version=verified_policy.policy.version,
            local_trust_policy_digest=verified_policy.policy_digest,
            trusted_root_digest=hashlib.sha256(request.sigstore_trusted_root_bytes).hexdigest(),
            sigstore=sigstore_evidence,
            verified_entry_point=quarantined.verified_entry_point,
            quarantine_root=quarantined.root,
        )
