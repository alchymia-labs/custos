from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from custos_toolkit.contracts.strategy_execution import (
    StrategyArtifactPreImportVerificationReceiptV1,
    StrategyExecutionCommandBindingV1,
)

from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from custos.artifacts.sigstore_verifier import ProductionSigstoreVerifier
from custos.artifacts.verifier import ArtifactVerifierKernel, PreImportVerificationRequest


@dataclass(frozen=True, slots=True)
class RunnerLocalArtifactVerificationConfig:
    """Immutable trust material loaded from runner-local configuration.

    Callers, not artifacts or deployment commands, select these values. The signed
    policy binds the trusted-root digest before any BOM, Sigstore, or archive work.
    """

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


class ProductionArtifactPreImportVerifier:
    """Production signed-wheel verification before Python import or entry-point load.

    Runtime activation is deliberately absent. Plan 19 may call this seam only after
    the producer command gate is satisfied; this module never imports strategy code.
    """

    def __init__(self, config: RunnerLocalArtifactVerificationConfig) -> None:
        self._config = config
        self._kernel = ArtifactVerifierKernel(sigstore_verifier=ProductionSigstoreVerifier())

    def verify(
        self,
        *,
        command_binding: StrategyExecutionCommandBindingV1,
        release_bom_bytes: bytes,
        member_paths: Mapping[str, Path],
        verified_at: datetime,
    ) -> StrategyArtifactPreImportVerificationReceiptV1:
        if not isinstance(command_binding, StrategyExecutionCommandBindingV1):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.COMMAND_BINDING_INVALID,
                "production pre-import verification requires a typed signed-wheel command binding",
            )
        result = self._kernel.verify(
            PreImportVerificationRequest(
                command_binding=command_binding,
                release_bom_bytes=release_bom_bytes,
                member_paths=member_paths,
                signed_policy_envelope_bytes=self._config.signed_policy_envelope_bytes,
                policy_authority_key_id=self._config.policy_authority_key_id,
                policy_authority_public_key=self._config.policy_authority_public_key,
                sigstore_trusted_root_bytes=self._config.sigstore_trusted_root_bytes,
                quarantine_parent=self._config.quarantine_parent,
                verified_at=verified_at,
            )
        )
        return result.receipt


__all__ = [
    "ProductionArtifactPreImportVerifier",
    "RunnerLocalArtifactVerificationConfig",
]
