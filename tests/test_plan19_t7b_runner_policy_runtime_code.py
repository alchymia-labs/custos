"""Plan 19 T7B: durable verified policy state and local guard consumption."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.contracts.crucible_runner_safety_policy import (
    CrucibleRunnerSafetyPolicyAuthenticator,
    RunnerAggregateCapPolicyPriorV1,
    VerifiedRunnerSafetyPolicy,
)
from custos.core.fallback_breaker import FallbackBreakerConfig
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.runner_fact import (
    RUNNER_STATE_SCHEMA_VERSION,
    RunnerFactIdentity,
    RunnerFactOutbox,
    RunnerPolicyIdentityDecision,
    RunnerStateAuthorityError,
    RunnerStateStore,
)
from custos.core.runner_safety_policy import (
    DurableRunnerSafetyPolicyResolver,
    RunnerSafetyPolicyUnavailableError,
)

RUNNER_ID = UUID("10000000-0000-4000-8000-000000000001")
TENANT_ID = "acme"
POLICY_IDS = {
    1: UUID("20000000-0000-4000-8000-000000000001"),
    2: UUID("20000000-0000-4000-8000-000000000002"),
    3: UUID("20000000-0000-4000-8000-000000000003"),
}
NOW = datetime(2026, 7, 15, 12, tzinfo=UTC)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _frame(context: bytes, subject: str, event_bytes: bytes) -> bytes:
    subject_bytes = subject.encode()
    return (
        context
        + len(subject_bytes).to_bytes(4, "big")
        + subject_bytes
        + len(event_bytes).to_bytes(8, "big")
        + event_bytes
    )


def _verified_policy(
    private_key: Ed25519PrivateKey,
    *,
    version: int = 1,
    generation: int = 1,
    previous: RunnerAggregateCapPolicyPriorV1 | None = None,
    status: str = "active",
    trading_mode: str = "sandbox",
    tenant_id: str = TENANT_ID,
    runner_id: UUID = RUNNER_ID,
    max_order: str = "100",
    max_total: str = "500",
    effective_at: str = "2026-07-15T00:00:00Z",
    expires_at: str = "2026-08-15T00:00:00Z",
) -> VerifiedRunnerSafetyPolicy:
    body = {
        "schema_version": 1,
        "policy_id": str(POLICY_IDS[version]),
        "runner_id": str(runner_id),
        "tenant_id": tenant_id,
        "trading_mode": trading_mode,
        "policy_version": version,
        "generation": generation,
        "settlement_currency": "USDT",
        "max_order_notional": max_order,
        "max_total_notional": max_total,
        "exposure_model": "filled_plus_active_reservations",
        "breach_action": "freeze_risk_increasing",
        "risk_reducing_orders": "always_permitted",
        "effective_at": effective_at,
        "expires_at": expires_at,
        "status": status,
        "previous_policy": previous.model_dump(mode="json") if previous else None,
    }
    compact_body = json.dumps(body, separators=(",", ":")).encode()
    payload = {**body, "policy_digest": hashlib.sha256(compact_body).hexdigest()}
    event = {
        "schema_version": 1,
        "event_id": "30000000-0000-4000-8000-000000000001",
        "tenant_id": tenant_id,
        "event_plane": {"kind": "mode", "trading_mode": trading_mode},
        "bounded_context": "risk",
        "aggregate_type": "runner_aggregate_cap_policy",
        "aggregate_id": str(POLICY_IDS[version]),
        "aggregate_version": generation,
        "event_type": "RunnerAggregateCapPolicyV1",
        "payload": payload,
        "correlation_id": "30000000-0000-4000-8000-000000000002",
        "actor_assertion_jti": "30000000-0000-4000-8000-000000000003",
        "occurred_at": "2026-07-15T00:00:01Z",
    }
    event_bytes = json.dumps(event, separators=(",", ":")).encode()
    subject = f"crucible_rust.domain.{tenant_id}.{trading_mode}.risk.runner_safety_policy.v1"
    signature_input = _frame(b"CRUCIBLE-DOMAIN-EVENT-V1\0", subject, event_bytes)
    fingerprint = hashlib.sha256(
        _frame(b"CRUCIBLE-RUNNER-SAFETY-POLICY-V1\0", subject, event_bytes)
    ).hexdigest()
    envelope = {
        "envelope_schema_version": 1,
        "subject": subject,
        "event_bytes_base64url": _b64url(event_bytes),
        "signature_profile": "crucible-domain-event-v1-exact-bytes",
        "signature_encoding": "application/json;base64url",
        "signature_input_base64url": _b64url(signature_input),
        "signature_key_id": "cr99-runtime-test",
        "signature_base64url": _b64url(private_key.sign(signature_input)),
        "fingerprint": fingerprint,
    }
    envelope_bytes = json.dumps(envelope, separators=(",", ":")).encode()
    return CrucibleRunnerSafetyPolicyAuthenticator(
        expected_tenant_id=tenant_id,
        expected_runner_id=runner_id,
        allowed_trading_modes=frozenset({"live", "sandbox", "testnet"}),
        signature_keys={"cr99-runtime-test": private_key.public_key()},
    ).verify(signed_envelope_bytes=envelope_bytes)


def _store(path: Path, *, tenant_id: str = TENANT_ID) -> RunnerStateStore:
    outbox = RunnerFactOutbox(path)
    return RunnerStateStore(
        outbox=outbox,
        identity=RunnerFactIdentity(Ed25519PrivateKey.generate(), "t7b-fact-key"),
        tenant_id=tenant_id,
        runner_id=RUNNER_ID,
        authority_resolver=lambda _verified: pytest.fail("not used by policy tests"),
    )


def _prior(verified: VerifiedRunnerSafetyPolicy) -> RunnerAggregateCapPolicyPriorV1:
    policy = verified.policy
    return RunnerAggregateCapPolicyPriorV1(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        generation=policy.generation,
        policy_digest=policy.policy_digest,
    )


@pytest.mark.asyncio
async def test_verified_policy_is_durable_and_recovers_from_same_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runner-state.sqlite3"
    private_key = Ed25519PrivateKey.generate()
    verified = _verified_policy(private_key)
    store = _store(database)

    result = await store.record_verified_runner_safety_policy(verified)
    loaded = await store.load_effective_runner_safety_policy("sandbox", now=NOW)
    restarted = await _store(database).load_effective_runner_safety_policy("sandbox", now=NOW)

    assert RUNNER_STATE_SCHEMA_VERSION == 1
    assert result.decision is RunnerPolicyIdentityDecision.NEWER
    assert result.committed is True
    assert loaded.policy == verified.policy
    assert restarted.exact_signed_envelope_bytes == verified.exact_signed_envelope_bytes
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM runner_cap_policy").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM runner_cap_policy_head").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master "
                "WHERE type='table' AND name='runner_fact_outbox'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.asyncio
async def test_policy_generation_digest_and_prior_fence_fail_closed(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    store = _store(tmp_path / "runner-state.sqlite3")
    first = _verified_policy(private_key)
    await store.record_verified_runner_safety_policy(first)

    replay = await store.record_verified_runner_safety_policy(first)
    assert replay.decision is RunnerPolicyIdentityDecision.IDEMPOTENT
    assert replay.committed is False

    conflict = _verified_policy(private_key, max_total="501")
    with pytest.raises(RunnerStateAuthorityError, match="conflict"):
        await store.record_verified_runner_safety_policy(conflict)

    second = _verified_policy(
        private_key,
        version=2,
        generation=2,
        previous=_prior(first),
    )
    accepted = await store.record_verified_runner_safety_policy(second)
    assert accepted.decision is RunnerPolicyIdentityDecision.NEWER

    with pytest.raises(RunnerStateAuthorityError, match="stale"):
        await store.record_verified_runner_safety_policy(first)

    unrelated_first = _verified_policy(private_key, max_total="499")
    wrong_fence = _verified_policy(
        private_key,
        version=3,
        generation=3,
        previous=RunnerAggregateCapPolicyPriorV1(
            policy_id=unrelated_first.policy.policy_id,
            policy_version=2,
            generation=2,
            policy_digest=unrelated_first.policy.policy_digest,
        ),
    )
    with pytest.raises(RunnerStateAuthorityError, match="prior fence"):
        await store.record_verified_runner_safety_policy(wrong_fence)


@pytest.mark.asyncio
async def test_scope_status_effective_and_expiry_are_enforced_after_restart(
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    verified = _verified_policy(private_key)
    wrong_tenant_store = _store(tmp_path / "wrong.sqlite3", tenant_id="other")
    with pytest.raises(RunnerStateAuthorityError, match="tenant"):
        await wrong_tenant_store.record_verified_runner_safety_policy(verified)

    future = _verified_policy(
        private_key,
        effective_at="2026-07-16T00:00:00Z",
        expires_at="2026-08-16T00:00:00Z",
    )
    store = _store(tmp_path / "future.sqlite3")
    await store.record_verified_runner_safety_policy(future)
    with pytest.raises(RunnerStateAuthorityError, match="not effective"):
        await store.load_effective_runner_safety_policy("sandbox", now=NOW)

    expired = _verified_policy(
        private_key,
        effective_at="2026-06-01T00:00:00Z",
        expires_at="2026-07-01T00:00:00Z",
    )
    expired_store = _store(tmp_path / "expired.sqlite3")
    await expired_store.record_verified_runner_safety_policy(expired)
    with pytest.raises(RunnerStateAuthorityError, match="expired"):
        await expired_store.load_effective_runner_safety_policy("sandbox", now=NOW)

    revoked = _verified_policy(private_key, status="revoked")
    revoked_store = _store(tmp_path / "revoked.sqlite3")
    await revoked_store.record_verified_runner_safety_policy(revoked)
    with pytest.raises(RunnerStateAuthorityError, match="not active"):
        await revoked_store.load_effective_runner_safety_policy("sandbox", now=NOW)


@pytest.mark.asyncio
async def test_cap_and_breaker_only_use_verified_policy_or_non_live_fallback() -> None:
    private_key = Ed25519PrivateKey.generate()
    policy = _verified_policy(private_key).policy
    cap_config = LocalCapConfig.from_verified_policy(policy)
    breaker_config = FallbackBreakerConfig.from_verified_policy(policy)

    assert cap_config.max_order_notional == policy.max_order_notional_decimal
    assert cap_config.max_total_notional == policy.max_total_notional_decimal
    assert cap_config.owner_policy is True
    assert breaker_config.max_notional == policy.max_total_notional_decimal
    assert breaker_config.owner_policy is True
    assert not hasattr(LocalCapConfig, "from_spec")
    assert not hasattr(FallbackBreakerConfig, "from_spec")

    cap = RunnerNotionalCap(cap_config)
    assert await cap.allows(
        symbol="BTCUSDT",
        current_open=cap_config.max_total_notional,
        new_order_notional=Decimal("1"),
        risk_reducing=True,
    )
    assert not await cap.allows(
        symbol="BTCUSDT",
        current_open=Decimal("0"),
        new_order_notional=cap_config.max_order_notional + Decimal("1"),
    )

    fallback = LocalCapConfig.strictest_local_fallback("sandbox")
    assert fallback.owner_policy is False
    with pytest.raises(RunnerSafetyPolicyUnavailableError, match="live"):
        LocalCapConfig.strictest_local_fallback("live")


@pytest.mark.asyncio
async def test_durable_resolver_returns_verified_policy_but_is_not_daemon_capability(
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    store = _store(tmp_path / "runner-state.sqlite3")
    verified = _verified_policy(private_key)
    await store.record_verified_runner_safety_policy(verified)
    resolver = DurableRunnerSafetyPolicyResolver(store=store, now=lambda: NOW)

    limits = await resolver.resolve("sandbox")

    assert limits.policy_id == verified.policy.policy_id
    assert limits.owner_policy is True
    assert resolver.runtime_publication_receipt_present is False
    assert resolver.live_capability is False
