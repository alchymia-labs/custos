"""Plan 19 T7A: exact CR99 runner-policy contract consumption."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.contracts.crucible_runner_safety_policy import (
    CrucibleRunnerSafetyPolicyAuthenticator,
    RunnerSafetyPolicyVerificationError,
)

ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "docs/authority/vendor/crucible-plan-99"
GOLDEN_PATH = (
    VENDOR_ROOT / "docs/authority/golden/crucible-runner-safety-policy-v1.json"
)

EXPECTED_ASSETS = {
    "docs/authority/schemas/crucible-runner-safety-policy-v1.schema.json": (
        "8aeb5442542a1e26581264f7f1acf7a498099a096eb246d9785d4b7fc828637a"
    ),
    "docs/authority/schemas/crucible-runner-safety-policy-v1.schema.json.sha256": (
        "f638984bb38a8f41f0d1922a4d40f8b0c1143842a6b66cb683ccb918aa40f7c7"
    ),
    "docs/authority/golden/crucible-runner-safety-policy-v1.json": (
        "290698580bf2ef31e4babe2b9c621e5f74064f7cee4bff5e143823e7bedc5b8e"
    ),
    "docs/authority/golden/crucible-runner-safety-policy-v1.json.sha256": (
        "c5145b8f7ae467bf34da2bc70f1a79443266e906a66e51fb217ab5b438229c9e"
    ),
    "docs/authority/receipts/crucible-plan-99-runner-policy-producer-v3.json": (
        "48f5ab98e9f62c1747949d42cccbdb324d9011da61d067a3d88dfbf25565da92"
    ),
}


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _signed_golden(
    private_key: Ed25519PrivateKey,
    *,
    envelope_mutator=None,
) -> bytes:
    envelope = dict(_golden()["signed_envelope"])
    envelope["signature_key_id"] = "cr99-test-key"
    if envelope_mutator is not None:
        envelope_mutator(envelope)
    signature_input = base64.urlsafe_b64decode(
        envelope["signature_input_base64url"] + "=="
    )
    envelope["signature_base64url"] = _b64url(private_key.sign(signature_input))
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


def _authenticator(
    private_key: Ed25519PrivateKey,
) -> CrucibleRunnerSafetyPolicyAuthenticator:
    return CrucibleRunnerSafetyPolicyAuthenticator(
        expected_tenant_id="tenant-team-alpha",
        expected_runner_id=UUID("0198a596-cab5-7a00-8000-000000000002"),
        allowed_trading_modes=frozenset({"live", "sandbox", "testnet"}),
        signature_keys={"cr99-test-key": private_key.public_key()},
    )


def test_exact_vendor_assets_match_current_cr99_receipt() -> None:
    for relative_path, expected_digest in EXPECTED_ASSETS.items():
        payload = (VENDOR_ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_digest

    receipt = json.loads(
        (
            VENDOR_ROOT
            / "docs/authority/receipts/crucible-plan-99-runner-policy-producer-v3.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["producer_commit"] == "0f8c9afbeccf2435785354ad734c16f18aa339ab"
    assert receipt["status"] == "READY_CONTRACT_PRODUCER_ONLY"
    assert receipt["truth"]["runtime_publication_enabled"] is False
    assert receipt["truth"]["live_capability"] is False


def test_authenticator_verifies_exact_event_signature_and_scope() -> None:
    private_key = Ed25519PrivateKey.generate()
    verified = _authenticator(private_key).verify(
        signed_envelope_bytes=_signed_golden(private_key)
    )

    policy = verified.policy
    assert policy.tenant_id == "tenant-team-alpha"
    assert policy.trading_mode == "live"
    assert policy.runner_id == UUID("0198a596-cab5-7a00-8000-000000000002")
    assert policy.policy_version == 1
    assert policy.generation == 1
    assert str(policy.max_order_notional) == "25000"
    assert str(policy.max_total_notional) == "100000"
    assert verified.exact_subject.endswith(".live.risk.runner_safety_policy.v1")
    assert verified.signature_key_id == "cr99-test-key"


def test_wrong_signature_or_scope_fails_closed() -> None:
    private_key = Ed25519PrivateKey.generate()
    envelope = json.loads(_signed_golden(private_key))
    envelope["signature_base64url"] = _b64url(b"x" * 64)
    tampered = json.dumps(envelope, separators=(",", ":")).encode()

    with pytest.raises(RunnerSafetyPolicyVerificationError, match="signature"):
        _authenticator(private_key).verify(signed_envelope_bytes=tampered)

    wrong_scope = CrucibleRunnerSafetyPolicyAuthenticator(
        expected_tenant_id="another-tenant",
        expected_runner_id=UUID("0198a596-cab5-7a00-8000-000000000002"),
        allowed_trading_modes=frozenset({"live"}),
        signature_keys={"cr99-test-key": private_key.public_key()},
    )
    with pytest.raises(RunnerSafetyPolicyVerificationError, match="tenant"):
        wrong_scope.verify(signed_envelope_bytes=_signed_golden(private_key))


def test_signed_noncanonical_or_digest_tampered_event_is_rejected() -> None:
    private_key = Ed25519PrivateKey.generate()
    golden = _golden()
    event = golden["event_document"]
    event["payload"]["max_total_notional"] = "99999"
    event_bytes = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()
    subject = golden["subject"]
    signature_input = (
        b"CRUCIBLE-DOMAIN-EVENT-V2\0"
        + len(subject.encode()).to_bytes(4, "big")
        + subject.encode()
        + len(event_bytes).to_bytes(8, "big")
        + event_bytes
    )
    fingerprint_input = (
        b"CRUCIBLE-RUNNER-SAFETY-POLICY-V1\0"
        + len(subject.encode()).to_bytes(4, "big")
        + subject.encode()
        + len(event_bytes).to_bytes(8, "big")
        + event_bytes
    )
    envelope = dict(golden["signed_envelope"])
    envelope.update(
        {
            "event_bytes_base64url": _b64url(event_bytes),
            "signature_input_base64url": _b64url(signature_input),
            "signature_key_id": "cr99-test-key",
            "signature_base64url": _b64url(private_key.sign(signature_input)),
            "fingerprint": hashlib.sha256(fingerprint_input).hexdigest(),
        }
    )

    with pytest.raises(RunnerSafetyPolicyVerificationError, match="digest"):
        _authenticator(private_key).verify(
            signed_envelope_bytes=json.dumps(envelope, separators=(",", ":")).encode()
        )


def test_synthetic_golden_signature_is_never_runtime_evidence() -> None:
    truth = _golden()["truth"]
    assert truth == {
        "contract_only": True,
        "custos_consumer_ready": False,
        "migration_0117_executed": False,
        "production_ready": False,
        "runtime_publication_enabled": False,
        "runtime_ready": False,
        "synthetic_signature_bytes": True,
    }
