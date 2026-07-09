"""SopsAgeVault — sops CLI integration with mocked subprocess。

教训 #17 失败模式:
- sops binary 不存在 → SystemExit/RuntimeError
- sops decrypt 失败 (returncode != 0) → RuntimeError
- sops 输出非 JSON → RuntimeError
- credential_id 不在 sops 文件 → KeyError
- permission_scope != trade_no_withdraw → ValueError

KEK 不泄漏 (CLAUDE.md 红线):
- 明文 secret 不出现在 caplog
- sops_decrypt_failed 日志不含 plaintext
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from custos.core.credential_vault import AuditEvent, SopsAgeVault


@pytest.fixture
def sops_file(tmp_path: Path) -> Path:
    p = tmp_path / "secrets.enc.json"
    p.write_text('{"encrypted": "irrelevant — sops will mock decrypt"}')
    return p


@pytest.fixture
def age_key_file(tmp_path: Path) -> Path:
    p = tmp_path / "age.key"
    p.write_text("AGE-SECRET-KEY-1...mock")
    p.chmod(0o600)
    return p


def _fake_run(stdout: bytes, returncode: int = 0):
    def runner(cmd, **kwargs):
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=returncode,
                cmd=cmd,
                stderr=b"sops: error decrypting (no plaintext here)",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr=b"")

    return runner


def test_decrypt_returns_credential_dict(
    sops_file: Path,
    age_key_file: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext = json.dumps(
        {
            "cred-123": {
                "credential_id": "cred-123",
                "tenant_id": "acme",
                "permission_scope": "trade_no_withdraw",
                "secret": "TOP-SECRET-API-KEY-DO-NOT-LEAK",
            }
        }
    ).encode("utf-8")

    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(plaintext)):
        with caplog.at_level(logging.INFO, logger="custos.credential_vault"):
            cred = vault.decrypt("cred-123")

    assert cred["credential_id"] == "cred-123"
    assert cred["permission_scope"] == "trade_no_withdraw"

    # KEK 不泄漏: caplog 不含 plaintext API key
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    log_text_extras = "\n".join(
        json.dumps({k: getattr(rec, k, None) for k in ("secret",)}) for rec in caplog.records
    )
    assert "TOP-SECRET-API-KEY-DO-NOT-LEAK" not in log_text
    assert "TOP-SECRET-API-KEY-DO-NOT-LEAK" not in log_text_extras


def test_decrypt_emits_audit_event(
    sops_file: Path,
    age_key_file: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext = json.dumps(
        {
            "cred-123": {
                "credential_id": "cred-123",
                "tenant_id": "acme",
                "permission_scope": "trade_no_withdraw",
                "secret": "<doesnt matter>",
            }
        }
    ).encode("utf-8")

    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(plaintext)):
        with caplog.at_level(logging.INFO, logger="custos.credential_vault"):
            vault.decrypt("cred-123")

    audit = [
        r
        for r in caplog.records
        if getattr(r, "audit_event", None) == AuditEvent.CREDENTIAL_DECRYPTED.value
    ]
    assert len(audit) == 1
    assert audit[0].credential_id == "cred-123"


def test_rejects_unsafe_permission_scope(sops_file: Path, age_key_file: Path) -> None:
    plaintext = json.dumps(
        {
            "cred-bad": {
                "credential_id": "cred-bad",
                "tenant_id": "acme",
                "permission_scope": "withdraw",  # 危险!
                "secret": "<x>",
            }
        }
    ).encode("utf-8")

    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(plaintext)):
        with pytest.raises(ValueError, match="unsafe permission_scope"):
            vault.decrypt("cred-bad")


def test_credential_id_not_in_file_raises_key_error(sops_file: Path, age_key_file: Path) -> None:
    plaintext = json.dumps({"other-cred": {}}).encode("utf-8")
    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(plaintext)):
        with pytest.raises(KeyError):
            vault.decrypt("missing-cred")


def test_sops_binary_missing_raises_runtime_error(sops_file: Path, age_key_file: Path) -> None:
    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )

    def boom(*args, **kwargs):
        raise FileNotFoundError("sops")

    with patch("subprocess.run", side_effect=boom):
        with pytest.raises(RuntimeError, match="sops CLI not installed"):
            vault.decrypt("any-cred")


def test_sops_decrypt_failure_raises_runtime_error(
    sops_file: Path, age_key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(b"", returncode=2)):
        with caplog.at_level(logging.ERROR, logger="custos.credential_vault"):
            with pytest.raises(RuntimeError, match="sops decryption failed"):
                vault.decrypt("cred-123")

    # silent path 必接 log (lesson #21)
    failures = [r for r in caplog.records if r.levelname == "ERROR"]
    assert any("sops_decrypt_failed" in r.getMessage() for r in failures)


def test_sops_output_non_json_raises(sops_file: Path, age_key_file: Path) -> None:
    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with patch("subprocess.run", side_effect=_fake_run(b"not json")):
        with pytest.raises(RuntimeError, match="sops output is not valid JSON"):
            vault.decrypt("cred-123")


def test_missing_sops_file_raises_file_not_found(tmp_path: Path, age_key_file: Path) -> None:
    vault = SopsAgeVault(
        sops_file=tmp_path / "missing.json",
        age_key_file=age_key_file,
        tenant_id="acme",
        initiator="runner-7",
    )
    with pytest.raises(FileNotFoundError):
        vault.decrypt("cred-123")


def test_missing_age_key_file_raises(sops_file: Path, tmp_path: Path) -> None:
    vault = SopsAgeVault(
        sops_file=sops_file,
        age_key_file=tmp_path / "missing-age.key",
        tenant_id="acme",
        initiator="runner-7",
    )
    with pytest.raises(FileNotFoundError):
        vault.decrypt("cred-123")
