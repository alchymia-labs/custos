from __future__ import annotations

import base64
import hashlib
import sys
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from custos_toolkit.contracts.strategy_execution import (
    DevelopmentSourceRefV1,
    StrategyArtifactPreImportVerificationReceiptV1,
    canonical_json_bytes,
)
from pydantic import ValidationError

import custos.artifacts.verifier as verifier_module
from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.policy import (
    ArchiveLimitsV1,
    ReleaseTrustPolicyV1,
    SignedReleaseTrustPolicyEnvelopeV1,
    SigstoreIdentityV1,
    canonical_policy_bytes,
    release_policy_signature_message,
)
from custos.artifacts.production_pre_import import (
    ProductionArtifactPreImportVerifier,
    RunnerLocalArtifactVerificationConfig,
)
from custos.artifacts.sigstore_verifier import ProductionSigstoreVerifier
from custos.artifacts.verifier import SigstoreVerificationEvidence
from tests._artifact_verifier_fixtures import build_artifact_fixture


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _policy_material(now: datetime, trusted_root: bytes):
    key = Ed25519PrivateKey.generate()
    policy = ReleaseTrustPolicyV1(
        policy_id="custos-strategy-release",
        version=1,
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        sigstore_trusted_root_sha256=hashlib.sha256(trusted_root).hexdigest(),
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
    envelope_bytes = canonical_json_bytes(envelope.model_dump(mode="json"))
    return key, policy, policy_bytes, envelope_bytes


def _config(tmp_path, *, key, envelope: bytes, trusted_root: bytes):
    return RunnerLocalArtifactVerificationConfig(
        signed_policy_envelope_bytes=envelope,
        policy_authority_key_id="release-policy-root-1",
        policy_authority_public_key=key.public_key(),
        sigstore_trusted_root_bytes=trusted_root,
        quarantine_parent=tmp_path / "quarantine",
    )


def _successful_sigstore(self, request):
    assert type(self) is ProductionSigstoreVerifier
    assert not request.quarantine_parent.exists()
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


def test_production_composition_verifies_in_order_without_importing_entry_point(
    tmp_path, monkeypatch
) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    trusted_root = b"runner-local-offline-sigstore-root"
    key, policy, policy_bytes, envelope = _policy_material(now, trusted_root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )
    trace: list[str] = []
    real_policy = verifier_module.verify_signed_release_policy
    real_bom = verifier_module.verify_release_bom_and_members
    real_quarantine = verifier_module.quarantine_wheel

    def traced_policy(*args, **kwargs):
        trace.append("policy")
        return real_policy(*args, **kwargs)

    def traced_bom(*args, **kwargs):
        trace.append("bom")
        return real_bom(*args, **kwargs)

    def traced_sigstore(self, request):
        trace.append("sigstore")
        return _successful_sigstore(self, request)

    def traced_quarantine(*args, **kwargs):
        trace.append("archive")
        assert trace == ["policy", "bom", "sigstore", "archive"]
        return real_quarantine(*args, **kwargs)

    monkeypatch.setattr(verifier_module, "verify_signed_release_policy", traced_policy)
    monkeypatch.setattr(verifier_module, "verify_release_bom_and_members", traced_bom)
    monkeypatch.setattr(ProductionSigstoreVerifier, "verify", traced_sigstore)
    monkeypatch.setattr(verifier_module, "quarantine_wheel", traced_quarantine)
    assert "strategies.supertrend" not in sys.modules

    receipt = ProductionArtifactPreImportVerifier(
        _config(
            tmp_path,
            key=key,
            envelope=envelope,
            trusted_root=trusted_root,
        )
    ).verify(
        command_binding=fixture.command,
        release_bom_bytes=fixture.bom_bytes,
        member_paths=fixture.member_paths,
        verified_at=now,
    )

    assert trace == ["policy", "bom", "sigstore", "archive"]
    assert isinstance(receipt, StrategyArtifactPreImportVerificationReceiptV1)
    assert receipt.verified_entry_point == "strategies.supertrend:RuntimeAdapter"
    assert not hasattr(receipt, "loaded_entry_point")
    assert not hasattr(receipt, "engine_ready")
    assert "strategies.supertrend" not in sys.modules


def test_runner_local_root_mismatch_fails_before_sigstore_or_archive(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    signed_root = b"signed-root"
    key, policy, policy_bytes, envelope = _policy_material(now, signed_root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )

    def unexpected_sigstore(self, request):
        raise AssertionError("Sigstore must not run before local policy/root verification")

    monkeypatch.setattr(ProductionSigstoreVerifier, "verify", unexpected_sigstore)
    with pytest.raises(ArtifactVerificationError) as error:
        ProductionArtifactPreImportVerifier(
            _config(
                tmp_path,
                key=key,
                envelope=envelope,
                trusted_root=b"different-runner-local-root",
            )
        ).verify(
            command_binding=fixture.command,
            release_bom_bytes=fixture.bom_bytes,
            member_paths=fixture.member_paths,
            verified_at=now,
        )

    assert error.value.code is ArtifactVerificationCode.TRUST_ROOT_DIGEST_MISMATCH
    assert not (tmp_path / "quarantine").exists()


def test_member_drift_fails_before_sigstore_or_archive(tmp_path, monkeypatch) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    trusted_root = b"runner-local-offline-sigstore-root"
    key, policy, policy_bytes, envelope = _policy_material(now, trusted_root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )
    member = next(iter(fixture.member_paths.values()))
    member.write_bytes(member.read_bytes() + b"drift")

    def unexpected_sigstore(self, request):
        raise AssertionError("Sigstore must not run after BOM/member drift")

    monkeypatch.setattr(ProductionSigstoreVerifier, "verify", unexpected_sigstore)
    with pytest.raises(ArtifactVerificationError) as error:
        ProductionArtifactPreImportVerifier(
            _config(
                tmp_path,
                key=key,
                envelope=envelope,
                trusted_root=trusted_root,
            )
        ).verify(
            command_binding=fixture.command,
            release_bom_bytes=fixture.bom_bytes,
            member_paths=fixture.member_paths,
            verified_at=now,
        )

    assert error.value.code in {
        ArtifactVerificationCode.MEMBER_SIZE_MISMATCH,
        ArtifactVerificationCode.MEMBER_DIGEST_MISMATCH,
        ArtifactVerificationCode.MEMBER_UNSTABLE,
    }
    assert not (tmp_path / "quarantine").exists()


def test_missing_production_sigstore_capability_fails_without_archive(
    tmp_path, monkeypatch
) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    trusted_root = b"runner-local-offline-sigstore-root"
    key, policy, policy_bytes, envelope = _policy_material(now, trusted_root)
    fixture = build_artifact_fixture(
        tmp_path,
        trust_policy_digest=hashlib.sha256(policy_bytes).hexdigest(),
        trust_policy_id=policy.policy_id,
        trust_policy_version=policy.version,
    )

    def unavailable(self, request):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.SIGSTORE_VERIFIER_UNAVAILABLE,
            "sigstore runtime dependency is not installed",
        )

    monkeypatch.setattr(ProductionSigstoreVerifier, "verify", unavailable)
    with pytest.raises(ArtifactVerificationError) as error:
        ProductionArtifactPreImportVerifier(
            _config(
                tmp_path,
                key=key,
                envelope=envelope,
                trusted_root=trusted_root,
            )
        ).verify(
            command_binding=fixture.command,
            release_bom_bytes=fixture.bom_bytes,
            member_paths=fixture.member_paths,
            verified_at=now,
        )

    assert error.value.code is ArtifactVerificationCode.SIGSTORE_VERIFIER_UNAVAILABLE
    assert not (tmp_path / "quarantine").exists()


@pytest.mark.parametrize("trading_mode", ["testnet", "live"])
def test_source_path_contract_rejects_non_sandbox_modes(trading_mode: str) -> None:
    with pytest.raises(ValidationError):
        DevelopmentSourceRefV1(
            source_path="/runner-local/development/strategy.py",
            source_sha256="a" * 64,
            trading_mode=trading_mode,
            promotable=False,
        )
