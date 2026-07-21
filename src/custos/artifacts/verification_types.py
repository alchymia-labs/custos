"""Internal verification capabilities used by the canonical V1 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from custos.artifacts.policy import SigstoreIdentityV1


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
class RunnerLocalArtifactVerificationConfig:
    """Immutable runner-local policy and trust material."""

    signed_policy_envelope_bytes: bytes
    policy_authority_key_id: str
    policy_authority_public_key: Ed25519PublicKey
    sigstore_trusted_root_bytes: bytes
    quarantine_parent: Path

    def __post_init__(self) -> None:
        if not self.signed_policy_envelope_bytes:
            raise ValueError("runner-local signed release policy is required")
        if not self.policy_authority_key_id.strip():
            raise ValueError("runner-local release-policy authority key id is required")
        if not isinstance(self.policy_authority_public_key, Ed25519PublicKey):
            raise TypeError("runner-local release-policy authority must be an Ed25519 public key")
        if not self.sigstore_trusted_root_bytes:
            raise ValueError("runner-local Sigstore trusted root is required")
        if not self.quarantine_parent.is_absolute():
            raise ValueError("runner-local quarantine parent must be an absolute path")


__all__ = [
    "DigestSubject",
    "RunnerLocalArtifactVerificationConfig",
    "SigstoreVerificationEvidence",
    "SigstoreVerificationRequest",
    "SigstoreVerifierCapability",
]
