from __future__ import annotations

import base64
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.contracts import (
    DEPLOYMENT_SPEC_DIGEST_ALGORITHM,
    CrucibleDomainEventVerifier,
    DeploymentMessage,
    DeploymentSpec,
    canonical_deployment_spec_digest,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/gateway-contract/v1/deployment_spec.schema.json"
RUNNER_ID = "10000000-0000-4000-8000-000000000001"
INSTANCE_ID = "20000000-0000-4000-8000-000000000002"
SPEC_ID = "30000000-0000-4000-8000-000000000003"
STRATEGY_ID = "40000000-0000-4000-8000-000000000004"
SHA_A = "a" * 64
SHA_B = "b" * 64


def canonical_spec() -> dict:
    return {
        "schema_version": 1,
        "deployment_spec_id": SPEC_ID,
        "tenant_id": "acme",
        "trading_mode": "sandbox",
        "strategy_id": STRATEGY_ID,
        "strategy_release_id": "50000000-0000-4000-8000-000000000005",
        "strategy_release_version": 1,
        "strategy_artifact_digest": SHA_B,
        "strategy_manifest_digest": SHA_A,
        "strategy_release_snapshot_digest": SHA_B,
        "parameters": {
            "runner_runtime": {
                "connector": "binance",
                "pairs": ["BTC-USDT"],
                "leverage": 1,
                "strategy_config": {},
                "sandbox": {"starting_balances": ["10000 USDT"]},
            }
        },
        "code_provenance": {"strategy_path": "/tmp/strategy"},
        "strategy_product_id": "60000000-0000-4000-8000-000000000006",
        "risk_policy_id": "70000000-0000-4000-8000-000000000007",
        "risk_policy_version": 1,
        "risk_policy_digest": SHA_A,
        "target_runner_id": RUNNER_ID,
        "engine_binding_id": "80000000-0000-4000-8000-000000000008",
        "execution_channel": {"channel_type": "runner"},
        "credential_scope": {"scope_id": "sandbox-credential", "scope_digest": SHA_A},
        "runner_contract_requirements": {},
        "venue_source_policy": [],
        "source_policy_digest": SHA_A,
        "scheduling_policy": {},
        "scheduling_policy_digest": SHA_B,
        "promotion_id": None,
        "promotion_evidence_digest": None,
    }


def signed_command(
    event_name: str = "DeploymentSpecReadyForRunner",
    *,
    mutate_payload=None,
) -> tuple[bytes, str, CrucibleDomainEventVerifier]:
    private_key = Ed25519PrivateKey.generate()
    canonical = canonical_spec()
    digest = canonical_deployment_spec_digest(canonical)
    event_type = f"{event_name}.{RUNNER_ID}.{INSTANCE_ID}"
    subject = f"crucible_rust.domain.acme.sandbox.deployment.{event_type}"
    payload = {
        "schema_version": 1,
        "tenant_id": "acme",
        "mode": "sandbox",
        "runner_id": RUNNER_ID,
        "deployment_instance_id": INSTANCE_ID,
        "deployment_spec_id": SPEC_ID,
        "deployment_spec_digest": digest,
        "generation": 1,
        "lifecycle_state": "running",
        "deployment_spec": canonical,
    }
    if mutate_payload is not None:
        mutate_payload(payload)
    event = {
        "schema_version": 2,
        "event_id": "90000000-0000-4000-8000-000000000009",
        "tenant_id": "acme",
        "event_plane": {"kind": "mode", "trading_mode": "sandbox"},
        "bounded_context": "deployment",
        "aggregate_type": "deployment_instance",
        "aggregate_id": INSTANCE_ID,
        "aggregate_version": 1,
        "event_type": event_type,
        "payload": payload,
        "correlation_id": "correlation-1",
        "actor_assertion_jti": None,
        "occurred_at": "2026-07-14T00:00:00.000000000Z",
    }
    event_bytes = json.dumps(event, separators=(",", ":")).encode()
    subject_bytes = subject.encode()
    framed = b"".join(
        (
            b"CRUCIBLE-DOMAIN-EVENT-V2\0",
            len(subject_bytes).to_bytes(4, "big"),
            subject_bytes,
            len(event_bytes).to_bytes(8, "big"),
            event_bytes,
        )
    )

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    envelope = {
        "schema_version": 2,
        "signature_profile": "crucible-domain-event-v2-exact-bytes",
        "event_encoding": "application/json;base64url",
        "event_bytes": encode(event_bytes),
        "signature_key_id": "domain-key-1",
        "signature": encode(private_key.sign(framed)),
    }
    verifier = CrucibleDomainEventVerifier("domain-key-1", private_key.public_key())
    return json.dumps(envelope).encode(), subject, verifier


@pytest.mark.parametrize(
    "event_name",
    ["DeploymentSpecReadyForRunner", "DeploymentInstanceDesiredStateChanged"],
)
def test_accepts_both_signed_desired_state_event_types(event_name: str) -> None:
    data, subject, verifier = signed_command(event_name)
    message = DeploymentMessage.parse(
        data,
        subject=subject,
        expected_tenant_id="acme",
        expected_runner_id=RUNNER_ID,
        verifier=verifier,
    )
    assert message.spec.deployment_instance_id == UUID(INSTANCE_ID)


def test_rejects_signed_but_internally_inconsistent_digest() -> None:
    data, subject, verifier = signed_command(
        mutate_payload=lambda payload: payload.__setitem__("deployment_spec_digest", SHA_A)
    )
    with pytest.raises(ValueError, match="digest differs"):
        DeploymentMessage.parse(
            data,
            subject=subject,
            expected_tenant_id="acme",
            expected_runner_id=RUNNER_ID,
            verifier=verifier,
        )


@pytest.mark.parametrize("field", ["generation", "lifecycle_state"])
def test_generation_and_lifecycle_are_required(field: str) -> None:
    data, subject, verifier = signed_command(mutate_payload=lambda payload: payload.pop(field))
    with pytest.raises(ValueError, match=field):
        DeploymentMessage.parse(
            data,
            subject=subject,
            expected_tenant_id="acme",
            expected_runner_id=RUNNER_ID,
            verifier=verifier,
        )


def test_digest_contract_is_versioned_and_does_not_mutate_input() -> None:
    canonical = canonical_spec()
    before = deepcopy(canonical)
    assert DEPLOYMENT_SPEC_DIGEST_ALGORITHM == "sha256-canonical-json-v1"
    assert len(canonical_deployment_spec_digest(canonical)) == 64
    assert canonical == before


def test_checked_in_schema_matches_local_execution_model() -> None:
    assert json.loads(SCHEMA.read_text()) == DeploymentSpec.model_json_schema()
