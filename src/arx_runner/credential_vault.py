"""Local exchange-credential vault (sops+age / Vault).

Hard rules (architecture §1 trust boundary):
- KEK never leaves the runner host.
- `permission_scope` forbids withdrawal.
- Every decrypt MUST emit a `CredentialDecrypted` audit event so the audit
  writer can build the immutable chain. The cloud product surface schema
  never persists keys.

This module ships the audit signal contract and a mock decrypt path. The
real sops/age plumbing lands when the credential delivery flow is built;
its consumers should code against the shape contracted here.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class AuditEvent(enum.Enum):
    """Audit event names consumed by the downstream audit log writer.

    Pinned as a closed enum so a rename can't silently break the writer's
    pattern match.
    """

    CREDENTIAL_DECRYPTED = "CredentialDecrypted"


class CredentialVault:
    """Mock vault: returns a placeholder credential dict and emits the
    canonical `CredentialDecrypted` audit signal. A future iteration swaps
    the mock body for real sops/age decryption; the audit emit must stay."""

    def __init__(self, *, tenant_id: str, initiator: str) -> None:
        self._tenant_id = tenant_id
        self._initiator = initiator

    def decrypt(self, credential_id: str) -> dict:
        cred = {
            "credential_id": credential_id,
            "tenant_id": self._tenant_id,
            "permission_scope": "trade_no_withdraw",
            "secret": "<mock>",
        }
        self._emit_decrypt_audit(credential_id)
        return cred

    def _emit_decrypt_audit(self, credential_id: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        log.info(
            "credential_decrypted",
            extra={
                "audit_event": AuditEvent.CREDENTIAL_DECRYPTED.value,
                "credential_id": credential_id,
                "tenant_id": self._tenant_id,
                "initiator": self._initiator,
                "timestamp": timestamp,
            },
        )
