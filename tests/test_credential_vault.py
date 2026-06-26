"""CredentialVault decrypt path emits the CredentialDecrypted audit signal.

The vault stub does not implement real sops/age decryption — that lands
when the full credential flow plan is built. What we contract today is the
audit signal shape: every successful decrypt MUST log a structured
CredentialDecrypted event so the downstream audit writer can pick it up.
"""

from __future__ import annotations

import logging

import pytest

from arx_runner.credential_vault import CredentialVault, AuditEvent


def test_decrypt_returns_mock_credential() -> None:
    vault = CredentialVault(tenant_id="acme", initiator="runner-7")
    cred = vault.decrypt("cred-123")
    assert isinstance(cred, dict)
    assert "credential_id" in cred


def test_decrypt_emits_credential_decrypted_audit_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vault = CredentialVault(tenant_id="acme", initiator="runner-7")
    with caplog.at_level(logging.INFO, logger="arx_runner.credential_vault"):
        vault.decrypt("cred-123")

    audit_records = [
        r
        for r in caplog.records
        if getattr(r, "audit_event", None) == AuditEvent.CREDENTIAL_DECRYPTED.value
    ]
    assert len(audit_records) == 1, "expected exactly one CredentialDecrypted audit log"

    rec = audit_records[0]
    assert rec.credential_id == "cred-123"
    assert rec.tenant_id == "acme"
    assert rec.initiator == "runner-7"
    assert rec.timestamp  # truthy ISO-8601 string


def test_audit_event_enum_pins_credential_decrypted_name() -> None:
    # Pinning the event name guards against accidental rename — the downstream
    # audit writer matches on this exact string.
    assert AuditEvent.CREDENTIAL_DECRYPTED.value == "CredentialDecrypted"
