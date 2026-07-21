from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.core.machine_credential_vault import (
    MachineCredential,
    canonical_enrollment_proof,
    canonical_revocation_proof,
    canonical_rotation_proof,
)

AUTHORITY_DIR = Path(__file__).parents[1] / "docs" / "authority" / "vendor"
GOLDEN_PATH = AUTHORITY_DIR / "crucible-runner-machine-request-golden-v1.json"
GOLDEN_SHA_PATH = Path(f"{GOLDEN_PATH}.sha256")
FIXTURE_CREDENTIAL = "rkc1.fixture-only-not-a-production-secret"


def _golden() -> dict[str, object]:
    value = json.loads(GOLDEN_PATH.read_text())
    assert isinstance(value, dict)
    return value


def test_custos_machine_headers_match_crucible_exact_golden() -> None:
    golden = _golden()
    body = json.loads(str(golden["canonical_body"]))
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    expected_headers = golden["headers"]
    assert isinstance(expected_headers, dict)
    credential = MachineCredential(
        tenant_id=str(expected_headers["X-Crucible-Tenant-Id"]),
        runner_id=UUID(str(expected_headers["X-Crucible-Runner-Id"])),
        credential_id=UUID(str(expected_headers["X-Crucible-Credential-Id"])),
        credential_version=int(str(expected_headers["X-Crucible-Credential-Version"])),
        credential_valid_until=datetime(2027, 7, 21, tzinfo=UTC),
        machine_key_id=str(expected_headers["X-Crucible-Machine-Key-Id"]),
        machine_credential=FIXTURE_CREDENTIAL,
        private_key_bytes=private_bytes,
    )
    headers = credential.authenticated_headers(
        method=str(golden["method"]),
        path=str(golden["path"]),
        body=body,
        correlation_id=UUID(str(expected_headers["X-Crucible-Request-Id"])),
        issued_at=datetime(2026, 7, 21, tzinfo=UTC),
    )

    secret_contract = golden["credential_header"]
    assert isinstance(secret_contract, dict)
    secret_name = str(secret_contract["name"])
    assert headers.pop(secret_name) == FIXTURE_CREDENTIAL
    assert hashlib.sha256(FIXTURE_CREDENTIAL.encode()).hexdigest() == str(
        secret_contract["fixture_value_sha256"]
    )
    assert headers == expected_headers

    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    assert base64.b64encode(public_key).decode() == golden["machine_public_key_base64"]
    private_key.public_key().verify(
        base64.b64decode(str(expected_headers["X-Crucible-Machine-Signature"])),
        str(golden["signing_frame"]).encode(),
    )


def test_machine_request_authority_pin_and_legacy_cutover_are_exact() -> None:
    expected_sha = GOLDEN_SHA_PATH.read_text().split()[0]
    assert hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest() == expected_sha
    source = (
        Path(__file__).parents[1] / "src" / "custos" / "core" / "machine_credential_vault.py"
    ).read_text()
    assert "crucible.runner.machine.request.v1" in source
    assert "X-Crucible-Credential" in source
    assert "X-Arx-" not in source
    assert "arx.runner.machine.request" not in source


def test_credential_pop_domains_are_crucible_owned_v1() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    credential = MachineCredential(
        tenant_id="acme",
        runner_id=UUID("11111111-1111-4111-8111-111111111111"),
        credential_id=UUID("22222222-2222-4222-8222-222222222222"),
        credential_version=1,
        credential_valid_until=datetime(2027, 7, 21, tzinfo=UTC),
        machine_key_id=f"ed25519-{hashlib.sha256(public_key).hexdigest()[:32]}",
        machine_credential=FIXTURE_CREDENTIAL,
        private_key_bytes=private_bytes,
    )
    nonce = UUID("33333333-3333-4333-8333-333333333333")
    request_id = UUID("44444444-4444-4444-8444-444444444444")
    assert canonical_enrollment_proof(
        enrollment_token="one-time-fixture",
        tenant_id="acme",
        runner_id=credential.runner_id,
        challenge_nonce=nonce,
        machine_key_id=credential.machine_key_id,
        public_key=public_key,
    ).startswith(b"crucible.runner.enrollment.pop.v1\n")
    assert canonical_rotation_proof(
        credential=credential,
        challenge_nonce=nonce,
        correlation_id=request_id,
        new_machine_key_id=credential.machine_key_id,
        new_public_key=public_key,
        reason="fixture rotation",
    ).startswith(b"crucible.runner.credential.rotation.pop.v1\n")
    assert canonical_revocation_proof(
        credential=credential,
        challenge_nonce=nonce,
        correlation_id=request_id,
        reason="fixture revocation",
    ).startswith(b"crucible.runner.credential.revocation.pop.v1\n")
