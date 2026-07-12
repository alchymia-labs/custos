"""Failing-first tests for ``PerKeyVault`` — the reconciler's runtime read path.

Mirrors the ``vault verify`` contract at the reconciler read site:
- missing ``.enc`` file → clear error
- ``permission_scope`` violation → raise before returning
- sops subprocess failure → propagate up (no silent return)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest


def test_per_key_vault_missing_enc_file_clear_error(tmp_path: Path) -> None:
    from custos.core.per_key_vault import PerKeyVault

    vault = PerKeyVault(vault_dir=tmp_path / "vault", tenant_id="acme", initiator="runner-7")
    with pytest.raises(FileNotFoundError, match="arx-runner vault put"):
        vault.decrypt("not-there")


def test_per_key_vault_scope_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from custos.core.per_key_vault import PerKeyVault

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(mode=0o700)
    enc = vault_dir / "binance-paper.enc"
    enc.write_bytes(b"CIPHER")
    import os

    os.chmod(enc, 0o600)

    payload = {
        "binance-paper": {
            "api_key": "pub",
            "api_secret": "sec",
            "permission_scope": "trade_full",
        }
    }
    run_mock = mock.MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["sops"],
            returncode=0,
            stdout=json.dumps(payload).encode("utf-8"),
            stderr=b"",
        )
    )
    monkeypatch.setattr("custos.core.per_key_vault.subprocess.run", run_mock)
    vault = PerKeyVault(vault_dir=vault_dir, tenant_id="acme", initiator="runner-7")
    with pytest.raises(ValueError, match="permission_scope"):
        vault.decrypt("binance-paper")


def test_per_key_vault_sops_fail_no_silent_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from custos.core.per_key_vault import PerKeyVault

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(mode=0o700)
    enc = vault_dir / "binance-paper.enc"
    enc.write_bytes(b"CIPHER")
    import os

    os.chmod(enc, 0o600)

    run_mock = mock.MagicMock(
        side_effect=subprocess.CalledProcessError(1, ["sops"], stderr=b"boom")
    )
    monkeypatch.setattr("custos.core.per_key_vault.subprocess.run", run_mock)
    vault = PerKeyVault(vault_dir=vault_dir, tenant_id="acme", initiator="runner-7")
    with pytest.raises(RuntimeError, match="sops"):
        vault.decrypt("binance-paper")


def test_per_key_vault_happy_path_emits_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Happy path returns credential dict + emits CredentialDecrypted audit."""
    import logging

    from custos.core.credential_vault import AuditEvent
    from custos.core.per_key_vault import PerKeyVault

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(mode=0o700)
    enc = vault_dir / "binance-paper.enc"
    enc.write_bytes(b"CIPHER")
    import os

    os.chmod(enc, 0o600)

    payload = {
        "binance-paper": {
            "api_key": "pub",
            "api_secret": "sec",
            "permission_scope": "trade_no_withdraw",
        }
    }
    run_mock = mock.MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["sops"],
            returncode=0,
            stdout=json.dumps(payload).encode("utf-8"),
            stderr=b"",
        )
    )
    monkeypatch.setattr("custos.core.per_key_vault.subprocess.run", run_mock)
    vault = PerKeyVault(vault_dir=vault_dir, tenant_id="acme", initiator="runner-7")
    with caplog.at_level(logging.INFO, logger="custos.credential_vault"):
        cred = vault.decrypt("binance-paper")
    assert cred["permission_scope"] == "trade_no_withdraw"
    assert run_mock.call_args.args[0] == [
        "sops",
        "--decrypt",
        "--input-type",
        "json",
        "--output-type",
        "json",
        str(enc),
    ]
    audit_records = [
        r
        for r in caplog.records
        if getattr(r, "audit_event", None) == AuditEvent.CREDENTIAL_DECRYPTED.value
    ]
    assert len(audit_records) == 1
    assert audit_records[0].credential_id == "binance-paper"


def test_per_key_vault_missing_sops_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from custos.core.per_key_vault import PerKeyVault

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(mode=0o700)
    enc = vault_dir / "binance-paper.enc"
    enc.write_bytes(b"CIPHER")
    import os

    os.chmod(enc, 0o600)

    run_mock = mock.MagicMock(side_effect=FileNotFoundError("sops missing"))
    monkeypatch.setattr("custos.core.per_key_vault.subprocess.run", run_mock)
    vault = PerKeyVault(vault_dir=vault_dir, tenant_id="acme", initiator="runner-7")
    with pytest.raises(RuntimeError, match="sops CLI"):
        vault.decrypt("binance-paper")
