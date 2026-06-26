"""Local exchange-credential vault (sops+age / Vault).

Hard rules (architecture §1 trust boundary):
- KEK (age private key) never leaves the runner host.
- `permission_scope` forbids withdrawal (must be `trade_no_withdraw`).
- Every decrypt MUST emit a `CredentialDecrypted` audit event so the audit
  writer can build the immutable chain. The cloud product surface schema
  never persists keys.

V1 implementations:
- `MockVault`: returns a placeholder credential dict (test / dev).
- `SopsAgeVault`: shells out to `sops --decrypt --age <recipient> <file>`
  with the age key file pointed at by `SOPS_AGE_KEY_FILE` env override.
  Reads the decrypted secret + emits the audit event; never logs the
  plaintext.

Future: Hashicorp Vault provider for team tier (CLAUDE.md 红线
'Key/策略逻辑只在 runner 本地' 仍适用 — Vault token 也只在 runner)。
"""

from __future__ import annotations

import enum
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

# Use stdlib logging so existing test_credential_vault.py caplog assertions
# on extra={...} attributes (audit_event / credential_id / tenant_id) still
# work. Other runner modules use structlog; this one keeps stdlib to avoid
# breaking Plan 01 audit signal contract test.
_log = logging.getLogger("arx_runner.credential_vault")


class AuditEvent(enum.Enum):
    """Audit event names consumed by the downstream audit log writer.

    Pinned as a closed enum so a rename can't silently break the writer's
    pattern match.
    """

    CREDENTIAL_DECRYPTED = "CredentialDecrypted"


class CredentialVaultProtocol(Protocol):
    """Vault interface. Implementations must guarantee the audit event emit
    on every successful decrypt and must verify permission_scope is non-
    withdrawal before returning."""

    def decrypt(self, credential_id: str) -> dict: ...


class _BaseVault:
    """Shared audit-emit + permission-scope verification logic."""

    def __init__(self, *, tenant_id: str, initiator: str) -> None:
        self._tenant_id = tenant_id
        self._initiator = initiator

    def _emit_decrypt_audit(self, credential_id: str) -> None:
        """Emit canonical CredentialDecrypted audit event.

        Plaintext credentials NEVER appear in audit logs — only the
        credential_id reference. Audit writer downstream consumes the
        structured log event and chains it (Plan 07 audit三件套)。
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        _log.info(
            "credential_decrypted",
            extra={
                "audit_event": AuditEvent.CREDENTIAL_DECRYPTED.value,
                "credential_id": credential_id,
                "tenant_id": self._tenant_id,
                "initiator": self._initiator,
                "timestamp": timestamp,
            },
        )

    @staticmethod
    def _verify_permission_scope(cred: dict, credential_id: str) -> None:
        """Reject creds that allow withdrawal (CLAUDE.md 红线 + security.md)。"""
        scope = cred.get("permission_scope")
        if scope != "trade_no_withdraw":
            _log.error(
                "credential_scope_violation",
                extra={
                    "credential_id": credential_id,
                    "got_scope": scope,
                },
            )
            raise ValueError(
                f"credential {credential_id!r} has unsafe permission_scope "
                f"(expected 'trade_no_withdraw', got {scope!r})"
            )


class CredentialVault(_BaseVault):
    """Mock vault: returns a placeholder credential dict and emits the
    canonical `CredentialDecrypted` audit signal. Used by tests + dev.

    Kept name `CredentialVault` for backward compat with existing call
    sites (`from arx_runner.credential_vault import CredentialVault`).
    """

    def decrypt(self, credential_id: str) -> dict:
        cred = {
            "credential_id": credential_id,
            "tenant_id": self._tenant_id,
            "permission_scope": "trade_no_withdraw",
            "secret": "<mock>",
        }
        self._verify_permission_scope(cred, credential_id)
        self._emit_decrypt_audit(credential_id)
        return cred


class SopsAgeVault(_BaseVault):
    """V1 vault — sops + age CLI integration.

    Decrypts a sops-encrypted credentials file (JSON or YAML) using an age
    private key located via the `SOPS_AGE_KEY_FILE` env or explicit
    `age_key_file` arg。

    KEK 永不出本地 (CLAUDE.md 红线):
    - 不日志 plaintext (只 emit credential_id 引用 + audit event)
    - 不写 NATS 任何 plaintext
    - 不写 HTTP API 任何 plaintext
    - age_key_file 默认 0600，从环境读
    """

    def __init__(
        self,
        *,
        sops_file: Path,
        age_key_file: Path,
        tenant_id: str,
        initiator: str,
    ) -> None:
        super().__init__(tenant_id=tenant_id, initiator=initiator)
        self._sops_file = sops_file
        self._age_key_file = age_key_file

    def decrypt(self, credential_id: str) -> dict:
        if not self._sops_file.exists():
            raise FileNotFoundError(f"sops file not found: {self._sops_file}")
        if not self._age_key_file.exists():
            raise FileNotFoundError(
                f"age key file not found: {self._age_key_file}"
            )

        env = dict(os.environ)
        env["SOPS_AGE_KEY_FILE"] = str(self._age_key_file)

        try:
            result = subprocess.run(
                ["sops", "--decrypt", str(self._sops_file)],
                env=env,
                capture_output=True,
                check=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            _log.error("sops_binary_not_found", extra={"error": str(exc)})
            raise RuntimeError("sops CLI not installed on runner host") from exc
        except subprocess.CalledProcessError as exc:
            # stderr 可能含 sops 错误信息，但不会含 plaintext (sops 设计如此)。
            _log.error(
                "sops_decrypt_failed",
                extra={
                    "credential_id": credential_id,
                    "returncode": exc.returncode,
                    "stderr_len": len(exc.stderr or b""),
                },
            )
            raise RuntimeError("sops decryption failed") from exc
        except subprocess.TimeoutExpired:
            _log.error("sops_decrypt_timeout", extra={"credential_id": credential_id})
            raise RuntimeError("sops decryption timed out") from None

        # sops 输出 plaintext — 仅在内存解析, 立即用立即释放。
        try:
            cred_raw = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            _log.error(
                "sops_output_parse_failed",
                extra={"credential_id": credential_id, "error": str(exc)},
            )
            raise RuntimeError("sops output is not valid JSON") from exc

        # 找到 credential_id 对应条目 (sops 文件可能含多 credential)。
        cred = cred_raw.get(credential_id)
        if cred is None:
            _log.error(
                "credential_not_in_sops_file",
                extra={
                    "credential_id": credential_id,
                    "available_ids_count": len(cred_raw) if isinstance(cred_raw, dict) else 0,
                },
            )
            raise KeyError(
                f"credential {credential_id!r} not present in sops file"
            )

        self._verify_permission_scope(cred, credential_id)
        self._emit_decrypt_audit(credential_id)
        return cred
