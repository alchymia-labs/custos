from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from custos_toolkit.contracts.strategy_execution import canonical_json_bytes

from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.policy import (
    ArchiveLimitsV1,
    ReleaseTrustPolicyV1,
    SignedReleaseTrustPolicyEnvelopeV1,
    SigstoreIdentityV1,
    canonical_policy_bytes,
    release_policy_signature_message,
)
from custos.artifacts.verifier import (
    ArtifactVerifierKernel,
    PreImportVerificationRequest,
    SigstoreVerificationEvidence,
)
from tests._artifact_verifier_fixtures import build_artifact_fixture


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _policy_material(now: datetime, root: bytes):
    key = Ed25519PrivateKey.generate()
    policy = ReleaseTrustPolicyV1(
        policy_id="custos-strategy-release",
        version=1,
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        sigstore_trusted_root_sha256=hashlib.sha256(root).hexdigest(),
        accepted_identities=(
            SigstoreIdentityV1(
                issuer="https://token.actions.githubusercontent.com",
                workflow_identity=(
                    "alchymia-labs/philosophers-stone/"
                    ".github/workflows/release-strategy.yml@refs/heads/main"
                ),
                source_repository="https://github.com/alchymia-labs/philosophers-stone",
            ),
        ),
        require_transparency_log=True,
        archive_limits=ArchiveLimitsV1(),
    )
    policy_bytes = canonical_policy_bytes(policy)
    envelope = SignedReleaseTrustPolicyEnvelopeV1(
        policy_bytes=_b64(policy_bytes),
        signature_key_id="release-policy-root-1",
        signature=_b64(key.sign(release_policy_signature_message(policy_bytes))),
    )
    return key, policy, policy_bytes, canonical_json_bytes(envelope.model_dump(mode="json"))


class _TestOnlySigstoreCapability:
    """Orchestration double only; this is not production cryptographic evidence."""

    capability_id = "tests-only-non-production-sigstore-double"

    def __init__(self) -> None:
        self.called_before_quarantine = False

    def verify(self, request):
        self.called_before_quarantine = not request.quarantine_parent.exists()
        identity = request.accepted_identities[0]
        return SigstoreVerificationEvidence(
            verifier_capability_id=self.capability_id,
            bundle_sha256=hashlib.sha256(request.bundle_path.read_bytes()).hexdigest(),
            trusted_root_sha256=hashlib.sha256(request.trusted_root_bytes).hexdigest(),
            issuer=identity.issuer,
            workflow_identity=identity.workflow_identity,
            source_repository=identity.source_repository,
            verified_subjects=request.required_subjects,
            transparency_log_verified=True,
        )


def test_kernel_verifies_before_unpack_and_returns_internal_pre_import_result(tmp_path) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    trusted_root = b"offline-sigstore-trusted-root"
    key, policy, policy_bytes, envelope = _policy_material(now, trusted_root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )
    capability = _TestOnlySigstoreCapability()
    kernel = ArtifactVerifierKernel(sigstore_verifier=capability)

    result = kernel.verify(
        PreImportVerificationRequest(
            command_binding=fixture.command,
            release_bom_bytes=fixture.bom_bytes,
            member_paths=fixture.member_paths,
            signed_policy_envelope_bytes=envelope,
            policy_authority_key_id="release-policy-root-1",
            policy_authority_public_key=key.public_key(),
            sigstore_trusted_root_bytes=trusted_root,
            quarantine_parent=tmp_path / "quarantine",
            verified_at=now,
        )
    )

    assert capability.called_before_quarantine is True
    assert result.verification_profile == "custos-artifact-pre-import-internal-v1"
    assert result.verified_entry_point == "strategies.supertrend:RuntimeAdapter"
    assert result.quarantine_root.is_dir()
    assert not hasattr(result, "loaded_entry_point")
    assert not hasattr(result, "engine_ready")
    assert result.sigstore.verifier_capability_id.startswith("tests-only-")


def test_missing_sigstore_capability_fails_closed_without_unpacking(tmp_path) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    root = b"offline-sigstore-trusted-root"
    key, policy, policy_bytes, envelope = _policy_material(now, root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )
    quarantine = tmp_path / "quarantine"

    with pytest.raises(ArtifactVerificationError) as error:
        ArtifactVerifierKernel(sigstore_verifier=None).verify(
            PreImportVerificationRequest(
                command_binding=fixture.command,
                release_bom_bytes=fixture.bom_bytes,
                member_paths=fixture.member_paths,
                signed_policy_envelope_bytes=envelope,
                policy_authority_key_id="release-policy-root-1",
                policy_authority_public_key=key.public_key(),
                sigstore_trusted_root_bytes=root,
                quarantine_parent=quarantine,
                verified_at=now,
            )
        )

    assert error.value.code is ArtifactVerificationCode.SIGSTORE_VERIFIER_UNAVAILABLE
    assert not quarantine.exists()


def test_artifact_cannot_select_a_different_local_policy(tmp_path) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    root = b"offline-sigstore-trusted-root"
    key, _, _, envelope = _policy_material(now, root)
    fixture = build_artifact_fixture(tmp_path, trust_policy_digest="f" * 64)

    with pytest.raises(ArtifactVerificationError) as error:
        ArtifactVerifierKernel(sigstore_verifier=_TestOnlySigstoreCapability()).verify(
            PreImportVerificationRequest(
                command_binding=fixture.command,
                release_bom_bytes=fixture.bom_bytes,
                member_paths=fixture.member_paths,
                signed_policy_envelope_bytes=envelope,
                policy_authority_key_id="release-policy-root-1",
                policy_authority_public_key=key.public_key(),
                sigstore_trusted_root_bytes=root,
                quarantine_parent=tmp_path / "quarantine",
                verified_at=now,
            )
        )

    assert error.value.code is ArtifactVerificationCode.POLICY_BINDING_MISMATCH
