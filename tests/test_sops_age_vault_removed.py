"""Failing-first tests for the deletion of the legacy ``SopsAgeVault`` class.

Its per-key ``.enc`` replacement (``PerKeyVault``) is contracted separately;
this file only asserts the class is gone.
"""

from __future__ import annotations

import pytest


def test_sops_age_vault_class_removed() -> None:
    with pytest.raises(ImportError, match="SopsAgeVault"):
        from custos.core.credential_vault import SopsAgeVault  # noqa: F401


def test_base_vault_and_audit_event_survive() -> None:
    """The base helpers survive the delete; PerKeyVault inherits from them."""
    from custos.core.credential_vault import (
        AuditEvent,
        CredentialVault,
        _BaseVault,
    )

    assert AuditEvent.CREDENTIAL_DECRYPTED.value == "CredentialDecrypted"
    assert AuditEvent.CREDENTIAL_ENCRYPTED.value == "CredentialEncrypted"
    assert hasattr(_BaseVault, "_verify_permission_scope")
    assert hasattr(_BaseVault, "_emit_decrypt_audit")
    assert issubclass(CredentialVault, _BaseVault)


def test_per_key_vault_inherits_base_vault() -> None:
    from custos.core.credential_vault import _BaseVault
    from custos.core.per_key_vault import PerKeyVault

    assert issubclass(PerKeyVault, _BaseVault)
