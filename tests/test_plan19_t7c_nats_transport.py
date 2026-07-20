"""Plan 19 T7C CR100 transport authority consumer acceptance."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import nkeys
import pytest
from nats.errors import AuthorizationError

from custos.cli.subcommands import nats_transport as nats_transport_cli
from custos.core import nats_transport
from custos.core.machine_credential_vault import MachineCredentialTransportError
from custos.core.nats_transport import (
    RunnerNatsRevocationChallenge,
    RunnerNatsRevocationObservation,
    RunnerNatsTransportAuthorityClient,
    RunnerNatsTransportBundle,
    RunnerNatsTransportConnectionProfile,
    RunnerNatsTransportCredential,
    RunnerNatsTransportError,
    RunnerNatsTransportRevokedError,
    assert_old_generation_reconnect_denied,
)

_TENANT = "tenant-a"
_RUNNER = UUID("66666666-6666-4666-8666-666666666666")
_TRANSPORT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_MACHINE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def test_cli_registers_each_transport_action_without_option_conflicts() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    nats_transport_cli.register(subparsers)

    common = [
        "--nats-url",
        "tls://nats.example.test:4222",
        "--nats-server-name",
        "nats.example.test",
        "--issuer-account-public-nkey",
        "ACRUCIBLE",
    ]
    for action in ("enroll", "rotate", "activate"):
        parsed = parser.parse_args(
            [
                "nats-transport",
                action,
                *common,
                "--crucible-url",
                "https://crucible.example.test",
            ]
        )
        assert parsed.transport_action == action
        assert parsed.issuer_account_public_nkey == "ACRUCIBLE"

    parsed = parser.parse_args(["nats-transport", "verify", *common])
    assert parsed.transport_action == "verify"
    assert parsed.issuer_account_public_nkey == "ACRUCIBLE"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _keypair(prefix: int) -> tuple[bytes, object, str]:
    seed = nkeys.encode_seed(os.urandom(32), prefix)
    pair = nkeys.from_seed(bytearray(seed))
    return seed, pair, pair.public_key.decode("ascii")


def _permission_profile() -> dict[str, object]:
    durable = f"custos-v4-{_TENANT}-{_RUNNER}"
    return {
        "schema_version": 1,
        "profile": "runner-v1",
        "tenant_id": _TENANT,
        "runner_id": str(_RUNNER),
        "authorized_modes": ["sandbox", "testnet"],
        "publish_allow": [
            f"crucible.runner_fact.sandbox.{_TENANT}.{_RUNNER}.>",
            f"crucible.runner_fact.testnet.{_TENANT}.{_RUNNER}.>",
            f"$JS.ACK.CRUCIBLE_DOMAIN_AUDIT.{durable}.>",
            f"$JS.API.CONSUMER.INFO.CRUCIBLE_DOMAIN_AUDIT.{durable}",
        ],
        "subscribe_allow": [
            f"custos.runner_command_v4_delivery.{_TENANT}.{_RUNNER}",
            "_INBOX.>",
        ],
        "publish_deny": [
            "$JS.API.STREAM.>",
            "$JS.API.CONSUMER.CREATE.>",
            "$JS.API.CONSUMER.DURABLE.CREATE.>",
            "$JS.API.CONSUMER.DELETE.>",
            "$SYS.>",
        ],
        "subscribe_deny": ["$SYS.>"],
    }


def _durable_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "stream_name": "CRUCIBLE_DOMAIN_AUDIT",
        "durable_name": f"custos-v4-{_TENANT}-{_RUNNER}",
        "delivery_subject": f"custos.runner_command_v4_delivery.{_TENANT}.{_RUNNER}",
        "filter_subjects": [
            (
                f"crucible_rust.domain.{_TENANT}.sandbox.deployment."
                f"RunnerDeploymentCommandV4.{_RUNNER}.*"
            ),
            (
                f"crucible_rust.domain.{_TENANT}.testnet.deployment."
                f"RunnerDeploymentCommandV4.{_RUNNER}.*"
            ),
        ],
        "deliver_policy": "all",
        "ack_policy": "explicit",
        "replay_policy": "instant",
        "max_ack_pending": 1,
        "consumer_mode": "push_existing_only",
    }


def _digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _issued(
    *,
    user_seed: bytes,
    user_public_key: str,
    account_pair: object,
    account_public_key: str,
    generation: int = 1,
    now: datetime | None = None,
) -> dict[str, object]:
    issued_at = (now or datetime(2026, 7, 19, 8, 0, tzinfo=UTC)).replace(microsecond=0)
    expires_at = issued_at + timedelta(hours=1)
    permission = _permission_profile()
    durable = _durable_config()
    header = _b64url(
        json.dumps(
            {"typ": "JWT", "alg": "ed25519-nkey"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    claims = _b64url(
        json.dumps(
            {
                "iss": account_public_key,
                "sub": user_public_key,
                "iat": int(issued_at.timestamp()),
                "exp": int(expires_at.timestamp()),
                "nats": {
                    "type": "user",
                    "version": 2,
                    "pub": {
                        "allow": permission["publish_allow"],
                        "deny": permission["publish_deny"],
                    },
                    "sub": {
                        "allow": permission["subscribe_allow"],
                        "deny": permission["subscribe_deny"],
                    },
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    signature = account_pair.sign(signing_input)  # type: ignore[attr-defined]
    jwt = f"{header}.{claims}.{_b64url(signature)}"
    del user_seed
    return {
        "transport_credential_id": str(_TRANSPORT_ID),
        "transport_credential_version": generation,
        "transport_generation": generation,
        "nats_transport_profile": "runner-v1",
        "nats_user_public_key": user_public_key,
        "nats_user_jwt": jwt,
        "nats_user_jwt_sha256": hashlib.sha256(jwt.encode("ascii")).hexdigest(),
        "issuer_account_public_nkey": account_public_key,
        "permission_profile": permission,
        "permission_profile_sha256": _digest(permission),
        "durable_config": durable,
        "durable_config_sha256": _digest(durable),
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }


def _credential(
    *,
    generation: int = 1,
    now: datetime | None = None,
) -> RunnerNatsTransportCredential:
    user_seed, user_pair, user_public = _keypair(nkeys.PREFIX_BYTE_USER)
    account_seed, account_pair, account_public = _keypair(nkeys.PREFIX_BYTE_ACCOUNT)
    try:
        return RunnerNatsTransportCredential.from_issued_response(
            _issued(
                user_seed=user_seed,
                user_public_key=user_public,
                account_pair=account_pair,
                account_public_key=account_public,
                generation=generation,
                now=now,
            ),
            tenant_id=_TENANT,
            runner_id=_RUNNER,
            nats_user_seed=user_seed,
            expected_issuer_account_public_nkey=account_public,
        )
    finally:
        user_pair.wipe()
        account_pair.wipe()
        del account_seed


def _rotation_bundle(
    *,
    now: datetime | None = None,
) -> RunnerNatsTransportBundle:
    current = (now or datetime.now(UTC)).replace(microsecond=0)
    account_seed, account_pair, account_public = _keypair(nkeys.PREFIX_BYTE_ACCOUNT)
    user_seed_1, user_pair_1, user_public_1 = _keypair(nkeys.PREFIX_BYTE_USER)
    user_seed_2, user_pair_2, user_public_2 = _keypair(nkeys.PREFIX_BYTE_USER)
    try:
        active = RunnerNatsTransportCredential.from_issued_response(
            _issued(
                user_seed=user_seed_1,
                user_public_key=user_public_1,
                account_pair=account_pair,
                account_public_key=account_public,
                generation=1,
                now=current,
            ),
            tenant_id=_TENANT,
            runner_id=_RUNNER,
            nats_user_seed=user_seed_1,
            expected_issuer_account_public_nkey=account_public,
        )
        pending = RunnerNatsTransportCredential.from_issued_response(
            _issued(
                user_seed=user_seed_2,
                user_public_key=user_public_2,
                account_pair=account_pair,
                account_public_key=account_public,
                generation=2,
                now=current,
            ),
            tenant_id=_TENANT,
            runner_id=_RUNNER,
            nats_user_seed=user_seed_2,
            expected_issuer_account_public_nkey=account_public,
        )
        return RunnerNatsTransportBundle(active=active, pending=pending)
    finally:
        account_pair.wipe()
        user_pair_1.wipe()
        user_pair_2.wipe()
        del account_seed


def test_issued_credential_verifies_jwt_acl_durable_and_redacts_secrets() -> None:
    credential = _credential()

    rendered = repr(credential)

    assert credential.durable_config["stream_name"] == "CRUCIBLE_DOMAIN_AUDIT"
    assert credential.durable_config["durable_name"] == f"custos-v4-{_TENANT}-{_RUNNER}"
    assert credential.nats_user_jwt not in rendered
    assert base64.b64encode(credential.nats_user_seed).decode("ascii") not in rendered


def test_permission_or_stream_drift_is_rejected_before_socket_open() -> None:
    user_seed, user_pair, user_public = _keypair(nkeys.PREFIX_BYTE_USER)
    account_seed, account_pair, account_public = _keypair(nkeys.PREFIX_BYTE_ACCOUNT)
    try:
        response = _issued(
            user_seed=user_seed,
            user_public_key=user_public,
            account_pair=account_pair,
            account_public_key=account_public,
        )
        response["durable_config"] = {
            **response["durable_config"],  # type: ignore[dict-item]
            "stream_name": "SECOND_RUNNER_STREAM",
        }
        response["durable_config_sha256"] = _digest(
            response["durable_config"]  # type: ignore[arg-type]
        )
        with pytest.raises(RunnerNatsTransportError, match="exact CR100"):
            RunnerNatsTransportCredential.from_issued_response(
                response,
                tenant_id=_TENANT,
                runner_id=_RUNNER,
                nats_user_seed=user_seed,
                expected_issuer_account_public_nkey=account_public,
            )
    finally:
        user_pair.wipe()
        account_pair.wipe()
        del account_seed


def test_tls_profile_rejects_plaintext_host_drift_and_issuer_drift(tmp_path: Path) -> None:
    credential = _credential(now=datetime.now(UTC))
    ca = tmp_path / "ca.pem"
    ca.write_text("test-ca")

    with pytest.raises(RunnerNatsTransportError, match="tls://"):
        RunnerNatsTransportConnectionProfile(
            credential,
            "nats://nats.internal:4222",
            ca,
            "nats.internal",
            credential.issuer_account_public_nkey,
        )
    with pytest.raises(RunnerNatsTransportError, match="server name"):
        RunnerNatsTransportConnectionProfile(
            credential,
            "tls://nats.internal:4222",
            ca,
            "other.internal",
            credential.issuer_account_public_nkey,
        )
    with pytest.raises(RunnerNatsTransportError, match="issuer"):
        RunnerNatsTransportConnectionProfile(
            credential,
            "tls://nats.internal:4222",
            ca,
            "nats.internal",
            "A" + "A" * 55,
        )


@pytest.mark.asyncio
async def test_connect_uses_pinned_tls_jwt_and_local_nonce_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = _credential(now=datetime.now(UTC))
    ca = tmp_path / "ca.pem"
    ca.write_text("test-ca")
    context = MagicMock()
    connect = AsyncMock(return_value=object())
    monkeypatch.setattr(nats_transport.ssl, "create_default_context", lambda **_: context)
    monkeypatch.setattr(nats_transport.nats, "connect", connect)
    profile = RunnerNatsTransportConnectionProfile(
        credential,
        "tls://nats.internal:4222",
        ca,
        "nats.internal",
        credential.issuer_account_public_nkey,
    )

    await profile.connect(name="test-runner")

    kwargs = connect.await_args.kwargs
    assert kwargs["servers"] == ["tls://nats.internal:4222"]
    assert kwargs["tls"] is context
    assert kwargs["tls_hostname"] == "nats.internal"
    assert bytes(kwargs["user_jwt_cb"]()) == credential.nats_user_jwt.encode("ascii")
    signature = base64.b64decode(kwargs["signature_cb"]("nonce"), validate=True)
    pair = nkeys.from_seed(bytearray(credential.nats_user_seed))
    try:
        assert pair.verify(b"nonce", signature) is True
    finally:
        pair.wipe()
    await kwargs["disconnected_cb"]()
    await asyncio.wait_for(profile.wait_disconnected(), timeout=0.1)


@pytest.mark.asyncio
async def test_broker_authorization_denial_invalidates_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = _credential(now=datetime.now(UTC))
    ca = tmp_path / "ca.pem"
    ca.write_text("test-ca")
    context = MagicMock()
    connect = AsyncMock(return_value=object())
    monkeypatch.setattr(nats_transport.ssl, "create_default_context", lambda **_: context)
    monkeypatch.setattr(nats_transport.nats, "connect", connect)
    profile = RunnerNatsTransportConnectionProfile(
        credential,
        "tls://nats.internal:4222",
        ca,
        "nats.internal",
        credential.issuer_account_public_nkey,
    )
    await profile.connect(name="test-runner")

    await connect.await_args.kwargs["error_cb"](AuthorizationError())

    with pytest.raises(RunnerNatsTransportRevokedError, match="rejected"):
        profile.assert_active()


def test_rotation_keeps_old_generation_active_until_pending_promotes() -> None:
    account_seed, account_pair, account_public = _keypair(nkeys.PREFIX_BYTE_ACCOUNT)
    user_seed_1, user_pair_1, user_public_1 = _keypair(nkeys.PREFIX_BYTE_USER)
    user_seed_2, user_pair_2, user_public_2 = _keypair(nkeys.PREFIX_BYTE_USER)
    try:
        active = RunnerNatsTransportCredential.from_issued_response(
            _issued(
                user_seed=user_seed_1,
                user_public_key=user_public_1,
                account_pair=account_pair,
                account_public_key=account_public,
                generation=1,
            ),
            tenant_id=_TENANT,
            runner_id=_RUNNER,
            nats_user_seed=user_seed_1,
            expected_issuer_account_public_nkey=account_public,
        )
        pending = RunnerNatsTransportCredential.from_issued_response(
            _issued(
                user_seed=user_seed_2,
                user_public_key=user_public_2,
                account_pair=account_pair,
                account_public_key=account_public,
                generation=2,
            ),
            tenant_id=_TENANT,
            runner_id=_RUNNER,
            nats_user_seed=user_seed_2,
            expected_issuer_account_public_nkey=account_public,
        )

        staged = RunnerNatsTransportBundle(active=active, pending=pending)
        promoted = staged.promote_pending()

        assert staged.active is active
        assert staged.pending is pending
        assert promoted.active is pending
        assert promoted.pending is None
        assert promoted.retiring is active
        assert promoted.revocation is None
    finally:
        account_pair.wipe()
        user_pair_1.wipe()
        user_pair_2.wipe()
        del account_seed


def test_v1_vault_document_upgrades_to_v2_retirement_state_without_secret_loss() -> None:
    staged = _rotation_bundle()
    assert staged.active is not None
    legacy = {
        "schema_version": 1,
        "active": staged.active.to_document(),
        "pending": None,
    }

    upgraded = RunnerNatsTransportBundle.from_document(legacy)
    promoted = staged.promote_pending()
    assert promoted.retiring is not None
    challenge = RunnerNatsRevocationChallenge.from_response(
        _revocation_challenge(promoted.retiring),
        promoted.retiring,
    )
    assert promoted.active is not None
    persisted = promoted.with_revocation(_observation(challenge, replacement=promoted.active))
    restored = RunnerNatsTransportBundle.from_document(persisted.to_document())

    assert upgraded.to_document()["schema_version"] == 2
    assert restored == persisted
    assert restored.retiring.nats_user_jwt == staged.active.nats_user_jwt


def test_issue_request_exposes_only_public_nkey_and_uses_canonical_signature_path() -> None:
    account_seed, account_pair, account_public = _keypair(nkeys.PREFIX_BYTE_ACCOUNT)
    machine = SimpleNamespace(
        tenant_id=_TENANT,
        runner_id=_RUNNER,
        credential_id=_MACHINE_ID,
        credential_version=1,
    )
    captured: dict[str, object] = {}

    class _Http:
        def post(self, path, body, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(path=path, body=body, kwargs=kwargs)
            return _issued(
                user_seed=b"not-used-by-response",
                user_public_key=body["nats_user_public_key"],
                account_pair=account_pair,
                account_public_key=account_public,
                now=datetime.now(UTC),
            )

    try:
        client = RunnerNatsTransportAuthorityClient(
            "https://crucible.internal",
            machine,  # type: ignore[arg-type]
        )
        client.http = _Http()  # type: ignore[assignment]

        credential = client.issue_initial(
            expected_issuer_account_public_nkey=account_public,
            now=datetime.now(UTC),
        )

        body = captured["body"]
        assert captured["path"] == "/internal/v1/runner-nats-transport/enroll"
        assert captured["kwargs"]["canonical_path"] == (  # type: ignore[index]
            "/api/v1/runner-nats-transport/enroll"
        )
        assert "seed" not in json.dumps(body).lower()
        assert credential.nats_user_public_key == body["nats_user_public_key"]  # type: ignore[index]
    finally:
        account_pair.wipe()
        del account_seed


def _revocation_challenge(
    credential: RunnerNatsTransportCredential,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)
    return {
        "profile": "crucible.runner.nats-revocation-challenge.v1",
        "tenant_id": credential.tenant_id,
        "runner_id": str(credential.runner_id),
        "transport_credential_id": str(credential.transport_credential_id),
        "generation": credential.transport_generation,
        "user_public_nkey": credential.nats_user_public_key,
        "resolver_account_jwt_sha256": "d" * 64,
        "revoke_before": issued_at.isoformat().replace("+00:00", "Z"),
        "challenge_nonce": "33333333-3333-4333-8333-333333333333",
        "expected_binding_revision": 2,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }


def _observation(
    challenge: RunnerNatsRevocationChallenge,
    *,
    replacement: RunnerNatsTransportCredential | None = None,
) -> RunnerNatsRevocationObservation:
    return RunnerNatsRevocationObservation(
        challenge=challenge,
        replacement_transport_credential_id=(
            replacement.transport_credential_id
            if replacement is not None
            else challenge.transport_credential_id
        ),
        replacement_generation=(
            replacement.transport_generation
            if replacement is not None
            else challenge.generation + 1
        ),
        replacement_connected_at=datetime.now(UTC),
        challenge_validated_at=datetime.now(UTC),
    )


def test_revocation_challenge_and_observation_round_trip_without_secret_material() -> None:
    credential = _credential(now=datetime.now(UTC))
    challenge = RunnerNatsRevocationChallenge.from_response(
        _revocation_challenge(credential),
        credential,
    )
    forced_at = datetime.now(UTC)
    observation = _observation(challenge).mark_forced_disconnect(forced_at)
    observation = observation.mark_reconnect_denied(forced_at + timedelta(seconds=1))

    restored = RunnerNatsRevocationObservation.from_document(observation.to_document())
    rendered = json.dumps(restored.to_document(), sort_keys=True)

    assert restored == observation
    assert credential.nats_user_jwt not in rendered
    assert "seed" not in rendered.lower()


def test_revocation_challenge_rejects_cross_generation_substitution() -> None:
    credential = _credential(now=datetime.now(UTC))
    response = _revocation_challenge(credential)
    response["generation"] = credential.transport_generation + 1

    with pytest.raises(RunnerNatsTransportError, match="binding mismatch"):
        RunnerNatsRevocationChallenge.from_response(response, credential)


def test_authority_client_uses_targeted_superseded_route_and_public_evidence() -> None:
    credential = _credential(now=datetime.now(UTC))
    machine = SimpleNamespace(
        tenant_id=_TENANT,
        runner_id=_RUNNER,
        credential_id=_MACHINE_ID,
        credential_version=1,
    )
    captured: list[tuple[str, dict[str, object], dict[str, object]]] = []
    completed_at = datetime.now(UTC).replace(microsecond=0)

    class _Http:
        def post(self, path, body, **kwargs):  # type: ignore[no-untyped-def]
            captured.append((path, body, kwargs))
            if path.endswith("revoke-superseded") or path.endswith("revocation-challenge"):
                return _revocation_challenge(credential)
            return {
                "tenant_id": _TENANT,
                "runner_id": str(_RUNNER),
                "transport_credential_id": str(credential.transport_credential_id),
                "generation": credential.transport_generation,
                "resolver_account_jwt_sha256": "d" * 64,
                "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
            }

    client = RunnerNatsTransportAuthorityClient(
        "https://crucible.internal",
        machine,  # type: ignore[arg-type]
    )
    client.http = _Http()  # type: ignore[assignment]

    challenge = client.revoke_superseded(
        credential,
        expected_active_revision=2,
        reason="replacement active",
    )
    observation = _observation(challenge).mark_forced_disconnect(datetime.now(UTC))
    observation = observation.mark_reconnect_denied(datetime.now(UTC))
    assert client.read_revocation_challenge(credential) == challenge
    assert client.submit_revocation_evidence(observation, reason="old JWT denied") == completed_at

    assert [call[0] for call in captured] == [
        "/internal/v1/runner-nats-transport/revoke-superseded",
        "/internal/v1/runner-nats-transport/revocation-challenge",
        "/internal/v1/runner-nats-transport/revocation-evidence",
    ]
    assert captured[0][2]["canonical_path"] == ("/api/v1/runner-nats-transport/revoke-superseded")
    serialized = json.dumps([body for _, body, _ in captured], sort_keys=True)
    assert credential.nats_user_jwt not in serialized
    assert "seed" not in serialized.lower()


@pytest.mark.asyncio
async def test_old_generation_probe_requires_typed_authorization_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = _credential(now=datetime.now(UTC))
    ca = tmp_path / "ca.pem"
    ca.write_text("test-ca")
    context = MagicMock()
    monkeypatch.setattr(nats_transport.ssl, "create_default_context", lambda **_: context)

    async def rejected(**kwargs):  # type: ignore[no-untyped-def]
        await kwargs["error_cb"](AuthorizationError())
        raise OSError("broker rejected credentials")

    monkeypatch.setattr(nats_transport.nats, "connect", rejected)
    profile = RunnerNatsTransportConnectionProfile(
        credential,
        "tls://nats.internal:4222",
        ca,
        "nats.internal",
        credential.issuer_account_public_nkey,
    )

    await assert_old_generation_reconnect_denied(
        profile,
        name="old-generation",
        timeout_seconds=1,
    )

    async def unavailable(**_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("network unavailable")

    monkeypatch.setattr(nats_transport.nats, "connect", unavailable)
    second_profile = RunnerNatsTransportConnectionProfile(
        credential,
        "tls://nats.internal:4222",
        ca,
        "nats.internal",
        credential.issuer_account_public_nkey,
    )
    with pytest.raises(RunnerNatsTransportError, match="without explicit"):
        await assert_old_generation_reconnect_denied(
            second_profile,
            name="old-generation",
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_rotation_submission_loss_keeps_retiring_state_and_restart_resubmits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = _rotation_bundle()
    assert staged.active is not None
    assert staged.pending is not None
    challenge = RunnerNatsRevocationChallenge.from_response(
        _revocation_challenge(staged.active),
        staged.active,
    )
    completed_at = datetime.now(UTC)

    class _Connection:
        is_closed = False

        async def close(self) -> None:
            self.is_closed = True

    class _Profile:
        def __init__(self, credential, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            self.credential = credential

        async def connect(self, **_kwargs):  # type: ignore[no-untyped-def]
            return _Connection()

        async def wait_disconnected(self) -> None:
            return None

    class _Vault:
        def __init__(self) -> None:
            self.persisted: list[RunnerNatsTransportBundle] = []

        def persist(self, bundle, **_kwargs):  # type: ignore[no-untyped-def]
            self.persisted.append(bundle)

    class _Authority:
        fail_submit = True

        def activate(self, credential):  # type: ignore[no-untyped-def]
            return {
                "tenant_id": credential.tenant_id,
                "runner_id": str(credential.runner_id),
                "transport_credential_id": str(credential.transport_credential_id),
                "generation": credential.transport_generation,
                "status": "active",
                "revision": 2,
            }

        def revoke_superseded(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return challenge

        def read_revocation_challenge(self, *_args):  # type: ignore[no-untyped-def]
            return challenge

        def submit_revocation_evidence(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            if self.fail_submit:
                raise MachineCredentialTransportError("response lost")
            return completed_at

    async def denial(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        nats_transport_cli,
        "RunnerNatsTransportConnectionProfile",
        _Profile,
    )
    monkeypatch.setattr(
        nats_transport_cli,
        "assert_old_generation_reconnect_denied",
        denial,
    )
    args = SimpleNamespace(
        nats_url="tls://nats.internal:4222",
        nats_ca=tmp_path / "ca.pem",
        nats_server_name="nats.internal",
        issuer_account_public_nkey=staged.active.issuer_account_public_nkey,
        revocation_timeout_secs=300.0,
    )
    vault = _Vault()
    authority = _Authority()

    with pytest.raises(MachineCredentialTransportError, match="response lost"):
        await nats_transport_cli._activate_and_complete_retirement(  # noqa: SLF001
            args=args,
            authority=authority,  # type: ignore[arg-type]
            vault=vault,  # type: ignore[arg-type]
            bundle=staged,
            age_recipient="age1test",
        )

    durable = vault.persisted[-1]
    assert durable.retiring is staged.active
    assert durable.revocation is not None
    assert durable.revocation.evidence_ready is True

    authority.fail_submit = False
    resumed = await nats_transport_cli._activate_and_complete_retirement(  # noqa: SLF001
        args=args,
        authority=authority,  # type: ignore[arg-type]
        vault=vault,  # type: ignore[arg-type]
        bundle=durable,
        age_recipient="age1test",
    )

    assert resumed.retiring is None
    assert resumed.revocation is not None
    assert resumed.revocation.completed_at == completed_at


def test_expired_revocation_challenge_fails_closed() -> None:
    credential = _credential(now=datetime.now(UTC))
    response = _revocation_challenge(
        credential,
        now=datetime.now(UTC) - timedelta(minutes=10),
    )

    with pytest.raises(RunnerNatsTransportError, match="expired"):
        RunnerNatsRevocationChallenge.from_response(response, credential)
