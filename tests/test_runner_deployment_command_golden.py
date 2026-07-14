from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.contracts import CrucibleDomainEventVerifier, DeploymentMessage

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/authority/runner-deployment-command-golden-v1.json"
SIDECAR = FIXTURE.with_suffix(FIXTURE.suffix + ".sha256")
SNAPSHOT = ROOT / "docs/authority/ecosystem-authority.json"
SIBLING = ROOT.parent / "crucible-rust/docs/authority/runner-deployment-command-golden-v1.json"
KEY_ID = "fixture-domain-key-v1"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed(case: dict) -> tuple[bytes, CrucibleDomainEventVerifier]:
    subject = case["subject"]
    event_bytes = json.dumps(
        case["event_document"],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    subject_bytes = subject.encode("utf-8")
    framed = b"".join(
        (
            b"CRUCIBLE-DOMAIN-EVENT-V2\0",
            len(subject_bytes).to_bytes(4, "big"),
            subject_bytes,
            len(event_bytes).to_bytes(8, "big"),
            event_bytes,
        )
    )
    envelope = {
        "schema_version": 2,
        "signature_profile": "crucible-domain-event-v2-exact-bytes",
        "event_encoding": "application/json;base64url",
        "event_bytes": _base64url(event_bytes),
        "signature_key_id": KEY_ID,
        "signature": _base64url(PRIVATE_KEY.sign(framed)),
    }
    data = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    return data, CrucibleDomainEventVerifier(KEY_ID, PRIVATE_KEY.public_key())


@pytest.mark.parametrize(
    ("case_name", "generation", "lifecycle_state"),
    [
        ("deployment_spec_ready_for_runner", 1, "running"),
        ("deployment_instance_desired_state_changed", 2, "paused"),
    ],
)
def test_crucible_golden_commands_parse_through_real_signature_verifier(
    case_name: str,
    generation: int,
    lifecycle_state: str,
) -> None:
    case = next(value for value in _fixture()["cases"] if value["name"] == case_name)
    payload = case["event_document"]["payload"]
    assert payload["mode"] == "sandbox"
    assert "trading_mode" not in payload
    assert payload["deployment_spec"]["trading_mode"] == "sandbox"

    data, verifier = _signed(case)
    message = DeploymentMessage.parse(
        data,
        subject=case["subject"],
        expected_tenant_id="acme",
        expected_runner_id="10000000-0000-4000-8000-000000000001",
        verifier=verifier,
    )

    assert message.spec.generation == generation
    assert message.spec.lifecycle_state.value == lifecycle_state
    assert str(message.spec.deployment_instance_id) == (
        "20000000-0000-4000-8000-000000000002"
    )


def test_outer_trading_mode_alias_is_rejected_without_fallback() -> None:
    case = deepcopy(_fixture()["cases"][0])
    payload = case["event_document"]["payload"]
    payload["trading_mode"] = payload.pop("mode")
    data, verifier = _signed(case)

    with pytest.raises(ValueError, match="payload mode differs"):
        DeploymentMessage.parse(
            data,
            subject=case["subject"],
            expected_tenant_id="acme",
            expected_runner_id="10000000-0000-4000-8000-000000000001",
            verifier=verifier,
        )


def test_golden_hash_matches_snapshot_sidecar_and_optional_sibling() -> None:
    raw = FIXTURE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    authority = snapshot["runner_command_golden_fixture"]

    assert authority["sha256"] == digest
    assert SIDECAR.read_text(encoding="ascii") == f"{digest}  {FIXTURE.name}\n"
    if SIBLING.is_file():
        assert SIBLING.read_bytes() == raw
