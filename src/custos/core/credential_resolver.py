"""Resolve a signed Crucible credential scope through the local Custos vault."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from custos.core.runner_command_intake import VerifiedRunnerCommand
from custos.core.runner_command_runtime import (
    RunnerCredentialResolutionRejected,
    RunnerCredentialResolutionUnavailable,
)


class CredentialVaultV1(Protocol):
    def decrypt(self, credential_ref: str) -> dict[str, Any]: ...


class VaultRunnerCredentialResolverV1:
    """Bind a signed scope UUID/digest to one local non-custodial vault record."""

    def __init__(self, vault: CredentialVaultV1) -> None:
        self._vault = vault

    async def resolve(
        self,
        verified: VerifiedRunnerCommand,
        credential_scope: object,
    ) -> dict[str, Any]:
        scope_id = str(getattr(credential_scope, "scope_id", ""))
        scope_digest = str(getattr(credential_scope, "scope_digest", ""))
        if not scope_id or len(scope_digest) != 64:
            raise RunnerCredentialResolutionRejected("signed credential scope identity is invalid")
        try:
            credential = await asyncio.to_thread(self._vault.decrypt, scope_id)
        except Exception as error:
            raise RunnerCredentialResolutionUnavailable(
                "local credential vault is unavailable"
            ) from error
        if not isinstance(credential, dict):
            raise RunnerCredentialResolutionRejected("vault credential is not an object")
        if credential.get("scope_digest") != scope_digest:
            raise RunnerCredentialResolutionRejected(
                "vault credential differs from the signed scope digest"
            )
        if (
            verified.command.trading_mode in {"testnet", "live"}
            and credential.get("permission_scope") != "trade_no_withdraw"
        ):
            raise RunnerCredentialResolutionRejected(
                "real-venue credential is not trade_no_withdraw"
            )
        return credential


__all__ = ["CredentialVaultV1", "VaultRunnerCredentialResolverV1"]
