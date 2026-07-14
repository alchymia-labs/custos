from __future__ import annotations

import base64
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
    verify_signed_release_policy,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _signed_policy(
    *,
    now: datetime,
    root_bytes: bytes,
    private_key: Ed25519PrivateKey,
    mutate_payload: bool = False,
) -> tuple[bytes, ReleaseTrustPolicyV1]:
    policy = ReleaseTrustPolicyV1(
        policy_id="custos-strategy-release",
        version=7,
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        sigstore_trusted_root_sha256=__import__("hashlib").sha256(root_bytes).hexdigest(),
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
    payload = canonical_policy_bytes(policy)
    signature = private_key.sign(release_policy_signature_message(payload))
    if mutate_payload:
        payload = payload.replace(b'"version":7', b'"version":8')
    envelope = SignedReleaseTrustPolicyEnvelopeV1(
        policy_bytes=_b64(payload),
        signature_key_id="release-policy-root-1",
        signature=_b64(signature),
    )
    return canonical_json_bytes(envelope.model_dump(mode="json")), policy


def test_exact_policy_bytes_are_verified_before_policy_parse() -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    root = b"offline-sigstore-trusted-root"
    private_key = Ed25519PrivateKey.generate()
    envelope, expected = _signed_policy(now=now, root_bytes=root, private_key=private_key)

    verified = verify_signed_release_policy(
        envelope,
        authority_key_id="release-policy-root-1",
        authority_public_key=private_key.public_key(),
        sigstore_trusted_root_bytes=root,
        now=now,
    )

    assert verified.policy == expected
    assert len(verified.policy_digest) == 64
    assert verified.authority_key_id == "release-policy-root-1"


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("mutated_payload", ArtifactVerificationCode.POLICY_SIGNATURE_INVALID),
        ("wrong_key_id", ArtifactVerificationCode.POLICY_AUTHORITY_MISMATCH),
        ("wrong_trusted_root", ArtifactVerificationCode.TRUST_ROOT_DIGEST_MISMATCH),
        ("expired", ArtifactVerificationCode.POLICY_EXPIRED),
    ],
)
def test_policy_verification_fails_closed(case: str, expected_code: ArtifactVerificationCode) -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    root = b"offline-sigstore-trusted-root"
    private_key = Ed25519PrivateKey.generate()
    envelope, _ = _signed_policy(
        now=now - timedelta(days=2) if case == "expired" else now,
        root_bytes=root,
        private_key=private_key,
        mutate_payload=case == "mutated_payload",
    )

    with pytest.raises(ArtifactVerificationError) as error:
        verify_signed_release_policy(
            envelope,
            authority_key_id=("wrong-root" if case == "wrong_key_id" else "release-policy-root-1"),
            authority_public_key=private_key.public_key(),
            sigstore_trusted_root_bytes=(b"wrong-root" if case == "wrong_trusted_root" else root),
            now=now,
        )

    assert error.value.code is expected_code


def test_policy_payload_rejects_embedded_authority_key() -> None:
    now = datetime(2026, 7, 15, tzinfo=UTC)
    root = b"offline-sigstore-trusted-root"
    private_key = Ed25519PrivateKey.generate()
    envelope, _ = _signed_policy(now=now, root_bytes=root, private_key=private_key)
    envelope_model = SignedReleaseTrustPolicyEnvelopeV1.model_validate_json(envelope)
    payload = base64.urlsafe_b64decode(envelope_model.policy_bytes + "==")
    payload = payload[:-1] + b',"authority_public_key":"artifact-controlled"}'
    signature = private_key.sign(release_policy_signature_message(payload))
    forged = envelope_model.model_copy(
        update={"policy_bytes": _b64(payload), "signature": _b64(signature)}
    )

    with pytest.raises(ArtifactVerificationError) as error:
        verify_signed_release_policy(
            canonical_json_bytes(forged.model_dump(mode="json")),
            authority_key_id="release-policy-root-1",
            authority_public_key=private_key.public_key(),
            sigstore_trusted_root_bytes=root,
            now=now,
        )

    assert error.value.code is ArtifactVerificationCode.POLICY_INVALID
