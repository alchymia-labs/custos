"""G6 rejection propagated through instance-keyed reconciliation."""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
import structlog
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from custos.contracts.crucible_runner_safety_policy import (
    CrucibleRunnerSafetyPolicyAuthenticator,
    VerifiedRunnerSafetyPolicy,
)
from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.runner_fact import RunnerFactAuthority
from custos.core.runner_safety_policy import RunnerSafetyLimits
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

SHA = "a" * 64
RUNNER_ID = UUID("10000000-0000-4000-8000-000000000001")
INSTANCE_ID = UUID("20000000-0000-4000-8000-000000000002")
SPEC_ID = UUID("30000000-0000-4000-8000-000000000003")
STRATEGY_ID = UUID("40000000-0000-4000-8000-000000000004")
POLICY_ID = UUID("70000000-0000-4000-8000-000000000007")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _frame(context: bytes, subject: str, event_bytes: bytes) -> bytes:
    subject_bytes = subject.encode("utf-8")
    return (
        context
        + len(subject_bytes).to_bytes(4, "big")
        + subject_bytes
        + len(event_bytes).to_bytes(8, "big")
        + event_bytes
    )


def _verified_live_policy(
    private_key: Ed25519PrivateKey,
) -> VerifiedRunnerSafetyPolicy:
    body = {
        "schema_version": 1,
        "policy_id": str(POLICY_ID),
        "runner_id": str(RUNNER_ID),
        "tenant_id": "acme",
        "trading_mode": "live",
        "policy_version": 1,
        "generation": 1,
        "settlement_currency": "USDT",
        "max_order_notional": "100",
        "max_total_notional": "500",
        "exposure_model": "filled_plus_active_reservations",
        "breach_action": "freeze_risk_increasing",
        "risk_reducing_orders": "always_permitted",
        "effective_at": "2026-07-15T00:00:00Z",
        "expires_at": "2026-08-15T00:00:00Z",
        "status": "active",
        "previous_policy": None,
    }
    compact_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    payload = {**body, "policy_digest": hashlib.sha256(compact_body).hexdigest()}
    event = {
        "schema_version": 2,
        "event_id": "71000000-0000-4000-8000-000000000001",
        "tenant_id": "acme",
        "event_plane": {"kind": "mode", "trading_mode": "live"},
        "bounded_context": "risk",
        "aggregate_type": "runner_aggregate_cap_policy",
        "aggregate_id": str(POLICY_ID),
        "aggregate_version": 1,
        "event_type": "RunnerAggregateCapPolicyV1",
        "payload": payload,
        "correlation_id": "71000000-0000-4000-8000-000000000002",
        "actor_assertion_jti": "71000000-0000-4000-8000-000000000003",
        "occurred_at": "2026-07-15T00:00:01Z",
    }
    event_bytes = json.dumps(event, separators=(",", ":")).encode("utf-8")
    subject = "crucible_rust.domain.acme.live.risk.runner_safety_policy.v1"
    signature_input = _frame(b"CRUCIBLE-DOMAIN-EVENT-V2\0", subject, event_bytes)
    fingerprint = hashlib.sha256(
        _frame(b"CRUCIBLE-RUNNER-SAFETY-POLICY-V1\0", subject, event_bytes)
    ).hexdigest()
    envelope = {
        "envelope_schema_version": 1,
        "subject": subject,
        "event_bytes_base64url": _b64url(event_bytes),
        "signature_profile": "crucible-domain-event-v2-exact-bytes",
        "signature_encoding": "application/json;base64url",
        "signature_input_base64url": _b64url(signature_input),
        "signature_key_id": "g6-policy-test",
        "signature_base64url": _b64url(private_key.sign(signature_input)),
        "fingerprint": fingerprint,
    }
    return CrucibleRunnerSafetyPolicyAuthenticator(
        expected_tenant_id="acme",
        expected_runner_id=RUNNER_ID,
        allowed_trading_modes=frozenset({"live"}),
        signature_keys={"g6-policy-test": private_key.public_key()},
    ).verify(signed_envelope_bytes=json.dumps(envelope, separators=(",", ":")).encode("utf-8"))


class _SignedLivePolicyResolver:
    def __init__(
        self,
        verified: VerifiedRunnerSafetyPolicy,
        receipt: dict[str, object],
        public_key: Ed25519PublicKey,
    ) -> None:
        signature = receipt.get("signature_base64url")
        if not isinstance(signature, str):
            raise ValueError("test publication receipt lacks a signature")
        signed_body = {key: value for key, value in receipt.items() if key != "signature_base64url"}
        public_key.verify(
            _b64url_decode(signature),
            json.dumps(signed_body, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        )
        policy = verified.policy
        if signed_body != {
            "receipt_schema_version": 1,
            "status": "VALIDATED_TEST_RUNTIME_PUBLICATION_ONLY",
            "tenant_id": policy.tenant_id,
            "trading_mode": policy.trading_mode,
            "runner_id": str(policy.runner_id),
            "policy_digest": policy.policy_digest,
            "fingerprint": verified.fingerprint,
            "signature_key_id": "g6-policy-test",
            "runtime_publication_enabled": True,
            "live_capability": True,
        }:
            raise ValueError("test publication receipt does not bind the verified policy")
        self._verified = verified
        self.calls: list[str] = []

    async def resolve(self, trading_mode: str) -> RunnerSafetyLimits:
        self.calls.append(trading_mode)
        if trading_mode != self._verified.policy.trading_mode:
            raise RuntimeError("signed policy does not cover requested mode")
        return RunnerSafetyLimits.from_verified_policy(self._verified.policy)


def _signed_live_policy_resolver() -> _SignedLivePolicyResolver:
    private_key = Ed25519PrivateKey.generate()
    verified = _verified_live_policy(private_key)
    policy = verified.policy
    receipt_body: dict[str, object] = {
        "receipt_schema_version": 1,
        "status": "VALIDATED_TEST_RUNTIME_PUBLICATION_ONLY",
        "tenant_id": policy.tenant_id,
        "trading_mode": policy.trading_mode,
        "runner_id": str(policy.runner_id),
        "policy_digest": policy.policy_digest,
        "fingerprint": verified.fingerprint,
        "signature_key_id": "g6-policy-test",
        "runtime_publication_enabled": True,
        "live_capability": True,
    }
    receipt_bytes = json.dumps(receipt_body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    receipt = {
        **receipt_body,
        "signature_base64url": _b64url(private_key.sign(receipt_bytes)),
    }
    return _SignedLivePolicyResolver(verified, receipt, private_key.public_key())


class _CapabilityLessHost:
    async def deploy(self, spec: dict, credential: dict) -> str:
        return str(spec["deployment_instance_id"])

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, deployment_instance_id: str) -> None:
        return None


@pytest.fixture
def strategy_dir(tmp_path):
    directory = tmp_path / "supertrend"
    directory.mkdir()
    (directory / "strategy.py").write_text("class SupertrendStrategy:\n    pass\n")
    return directory


def _live_spec(strategy_dir) -> dict:
    return {
        "spec_id": str(SPEC_ID),
        "deployment_instance_id": str(INSTANCE_ID),
        "deployment_spec_digest": SHA,
        "strategy_id": str(STRATEGY_ID),
        "generation": 1,
        "trading_mode": "live",
        "lifecycle_state": "running",
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_path": str(strategy_dir / "strategy.py"),
        "strategy_config": {},
        "code_hash": compute_strategy_dir_hash(strategy_dir),
        "provenance_ref": {"credential_id": "cred-live"},
        "promotion_id": "50000000-0000-4000-8000-000000000005",
        "promotion_evidence_digest": "b" * 64,
    }


def _authority(value: dict, *, strategy_id: str) -> RunnerFactAuthority:
    return RunnerFactAuthority(
        tenant_id="acme",
        trading_mode=value["trading_mode"],
        runner_id=RUNNER_ID,
        deployment_instance_id=UUID(value["deployment_instance_id"]),
        deployment_spec_id=UUID(value["spec_id"]),
        deployment_spec_digest=value["deployment_spec_digest"],
        generation=int(value["generation"]),
        strategy_id=UUID(strategy_id),
        capability_version_id=UUID("60000000-0000-4000-8000-000000000006"),
        capability_version=1,
        capability_manifest_digest=SHA,
    )


def _reconciler(
    host: object,
    safety_policy_resolver: _SignedLivePolicyResolver,
) -> tuple[DeploymentReconciler, MagicMock, MagicMock]:
    vault = MagicMock()
    vault.decrypt.return_value = {
        "api_key": "k",
        "api_secret": "s",
        "permission_scope": "trade_no_withdraw",
    }
    runtime_log = MagicMock()
    runtime_log.authority_for_spec.side_effect = _authority
    runtime_log.emit = AsyncMock()
    lifecycle = MagicMock()
    lifecycle.authority_for_spec.side_effect = _authority
    lifecycle.emit_fact = AsyncMock()
    subject = DeploymentReconciler(
        nats_client=object(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id=str(RUNNER_ID),
        execution_engine=host,
        credential_vault=vault,
        runtime_log_emitter=runtime_log,
        lifecycle_fact_emitter=lifecycle,
        deployment_verifier=object(),  # type: ignore[arg-type]
        safety_policy_resolver=safety_policy_resolver,
    )
    return subject, runtime_log, lifecycle


@pytest.mark.asyncio
async def test_undeclared_host_degrades_without_emitting_applied_fact(strategy_dir) -> None:
    resolver = _signed_live_policy_resolver()
    reconciler, runtime_log, lifecycle = _reconciler(_CapabilityLessHost(), resolver)

    with structlog.testing.capture_logs() as logs:
        applied = await reconciler.handle_spec(_live_spec(strategy_dir))

    assert applied is False
    events = [entry.get("event") for entry in logs]
    assert "g6_gate_live_capability_denied" in events
    assert "deployment_reconcile_failed" in events
    assert resolver.calls == ["live"]
    runtime_log.emit.assert_awaited_once()
    lifecycle.emit_fact.assert_not_awaited()
