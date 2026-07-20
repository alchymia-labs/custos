"""Authenticated runner NATS transport authority.

Custos owns only the runner User NKey seed. Crucible owns issuance, permission,
durable-consumer and revocation authority. The local seed and issued JWT live in
a dedicated sops+age vault; venue credentials never share this document.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import inspect
import json
import os
import re
import ssl
import stat
import subprocess
import tempfile
import urllib.parse
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import nats
import nkeys  # type: ignore[import-untyped]
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from nats import errors as nats_errors

from custos.core.machine_credential_vault import (
    MachineCredential,
    MachineCredentialHttpClient,
)

RUNNER_NATS_TRANSPORT_PROFILE = "runner-v1"
RUNNER_COMMAND_STREAM = "CRUCIBLE_DOMAIN_AUDIT"
_ISSUE_PATH = "/internal/v1/runner-nats-transport/enroll"
_ROTATE_PATH = "/internal/v1/runner-nats-transport/rotate"
_ACTIVATE_PATH = "/internal/v1/runner-nats-transport/activate"
_REVOKE_SUPERSEDED_PATH = "/internal/v1/runner-nats-transport/revoke-superseded"
_REVOCATION_CHALLENGE_PATH = "/internal/v1/runner-nats-transport/revocation-challenge"
_REVOCATION_EVIDENCE_PATH = "/internal/v1/runner-nats-transport/revocation-evidence"
_CANONICAL_ISSUE_PATH = "/api/v1/runner-nats-transport/enroll"
_CANONICAL_ROTATE_PATH = "/api/v1/runner-nats-transport/rotate"
_CANONICAL_ACTIVATE_PATH = "/api/v1/runner-nats-transport/activate"
_CANONICAL_REVOKE_SUPERSEDED_PATH = "/api/v1/runner-nats-transport/revoke-superseded"
_CANONICAL_REVOCATION_CHALLENGE_PATH = "/api/v1/runner-nats-transport/revocation-challenge"
_CANONICAL_REVOCATION_EVIDENCE_PATH = "/api/v1/runner-nats-transport/revocation-evidence"
_REVOCATION_CHALLENGE_PROFILE = "crucible.runner.nats-revocation-challenge.v1"
_REVOCATION_EVIDENCE_PROFILE = "custos.runner.nats-revocation-evidence.v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNT_NKEY = re.compile(r"^A[A-Z2-7]{55}$")
_USER_NKEY = re.compile(r"^U[A-Z2-7]{55}$")
_FILE_MODE = 0o600
_DIR_MODE = 0o700
_WORLD_GROUP_BITS = 0o077


class RunnerNatsTransportError(RuntimeError):
    """Transport authority, custody or binding validation failed."""


class RunnerNatsTransportRevokedError(RunnerNatsTransportError):
    """The broker rejected the current User JWT generation."""


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _required_uuid(value: object, field_name: str) -> UUID:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise RunnerNatsTransportError(f"{field_name} must be a UUID") from exc
    if parsed.int == 0:
        raise RunnerNatsTransportError(f"{field_name} must not be nil")
    return parsed


def _required_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise RunnerNatsTransportError(f"{field_name} must be RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunnerNatsTransportError(f"{field_name} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise RunnerNatsTransportError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp_nanos(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond:06d}000Z"


def _required_mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunnerNatsTransportError(f"{field_name} must be an object")
    return dict(value)


def _decode_base64url(value: str, field_name: str) -> bytes:
    if not value or "=" in value or any(character.isspace() for character in value):
        raise RunnerNatsTransportError(f"{field_name} is not canonical base64url")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise RunnerNatsTransportError(f"{field_name} is invalid base64url") from exc


def _decode_public_nkey(value: str, expected_prefix: int) -> bytes:
    try:
        encoded = value.encode("ascii")
        raw = base64.b32decode(encoded + b"=" * (-len(encoded) % 8))
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise RunnerNatsTransportError("issuer Account NKey is invalid") from exc
    if len(raw) != 35 or raw[0] != expected_prefix:
        raise RunnerNatsTransportError("issuer Account NKey has the wrong type")
    expected_crc = int.from_bytes(raw[-2:], byteorder="little")
    if nkeys.crc16(bytearray(raw[:-2])) != expected_crc:
        raise RunnerNatsTransportError("issuer Account NKey checksum is invalid")
    return raw[1:33]


def _validate_jwt(
    token: str,
    *,
    expected_issuer: str,
    expected_user: str,
    expected_expiry: datetime,
    permission_profile: Mapping[str, Any],
) -> None:
    segments = token.split(".")
    if len(segments) != 3:
        raise RunnerNatsTransportError("NATS User JWT must have three segments")
    try:
        header = json.loads(_decode_base64url(segments[0], "JWT header"))
        claims = json.loads(_decode_base64url(segments[1], "JWT claims"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RunnerNatsTransportError("NATS User JWT is not valid JSON") from exc
    if not isinstance(header, dict) or header.get("alg") != "ed25519-nkey":
        raise RunnerNatsTransportError("NATS User JWT algorithm is not ed25519-nkey")
    if not isinstance(claims, dict):
        raise RunnerNatsTransportError("NATS User JWT claims must be an object")
    if claims.get("iss") != expected_issuer or claims.get("sub") != expected_user:
        raise RunnerNatsTransportError("NATS User JWT issuer or subject binding mismatch")
    exp = claims.get("exp")
    iat = claims.get("iat")
    if type(exp) is not int or type(iat) is not int or exp <= iat:
        raise RunnerNatsTransportError("NATS User JWT validity window is invalid")
    if datetime.fromtimestamp(exp, UTC) != expected_expiry.replace(microsecond=0):
        raise RunnerNatsTransportError("NATS User JWT expiry binding mismatch")
    signature = _decode_base64url(segments[2], "JWT signature")
    if len(signature) != 64:
        raise RunnerNatsTransportError("NATS User JWT signature length is invalid")
    public_key = _decode_public_nkey(expected_issuer, nkeys.PREFIX_BYTE_ACCOUNT)
    try:
        VerifyKey(public_key).verify(f"{segments[0]}.{segments[1]}".encode("ascii"), signature)
    except BadSignatureError as exc:
        raise RunnerNatsTransportError("NATS User JWT signature is invalid") from exc
    nats_claims = claims.get("nats")
    if not isinstance(nats_claims, dict) or nats_claims.get("type") != "user":
        raise RunnerNatsTransportError("NATS User JWT has no user permission claims")
    publish = nats_claims.get("pub")
    subscribe = nats_claims.get("sub")
    if not isinstance(publish, dict) or not isinstance(subscribe, dict):
        raise RunnerNatsTransportError("NATS User JWT permission claims are incomplete")
    expected = (
        (publish, "allow", permission_profile["publish_allow"]),
        (publish, "deny", permission_profile["publish_deny"]),
        (subscribe, "allow", permission_profile["subscribe_allow"]),
        (subscribe, "deny", permission_profile["subscribe_deny"]),
    )
    if any(claim.get(key) != value for claim, key, value in expected):
        raise RunnerNatsTransportError("NATS User JWT permissions diverge from CR100 profile")


def _expected_permission_profile(
    tenant_id: str,
    runner_id: UUID,
    authorized_modes: Sequence[str],
) -> dict[str, Any]:
    runner = str(runner_id)
    durable = f"custos-v4-{tenant_id}-{runner}"
    publish_allow = [
        f"crucible.runner_fact.{mode}.{tenant_id}.{runner}.>" for mode in authorized_modes
    ]
    publish_allow.extend(
        (
            f"$JS.ACK.{RUNNER_COMMAND_STREAM}.{durable}.>",
            f"$JS.API.CONSUMER.INFO.{RUNNER_COMMAND_STREAM}.{durable}",
        )
    )
    return {
        "schema_version": 1,
        "profile": RUNNER_NATS_TRANSPORT_PROFILE,
        "tenant_id": tenant_id,
        "runner_id": runner,
        "authorized_modes": list(authorized_modes),
        "publish_allow": publish_allow,
        "subscribe_allow": [
            f"custos.runner_command_v4_delivery.{tenant_id}.{runner}",
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


def _expected_durable_config(
    tenant_id: str,
    runner_id: UUID,
    authorized_modes: Sequence[str],
) -> dict[str, Any]:
    runner = str(runner_id)
    return {
        "schema_version": 1,
        "stream_name": RUNNER_COMMAND_STREAM,
        "durable_name": f"custos-v4-{tenant_id}-{runner}",
        "delivery_subject": f"custos.runner_command_v4_delivery.{tenant_id}.{runner}",
        "filter_subjects": [
            (
                f"crucible_rust.domain.{tenant_id}.{mode}.deployment."
                f"RunnerDeploymentCommandV4.{runner}.*"
            )
            for mode in authorized_modes
        ],
        "deliver_policy": "all",
        "ack_policy": "explicit",
        "replay_policy": "instant",
        "max_ack_pending": 1,
        "consumer_mode": "push_existing_only",
    }


def generate_runner_user_nkey() -> tuple[bytes, str]:
    """Generate a local User seed; only the public NKey may leave Custos."""

    seed = nkeys.encode_seed(os.urandom(32), nkeys.PREFIX_BYTE_USER)
    seed_buffer = bytearray(seed)
    pair = nkeys.from_seed(seed_buffer)
    try:
        public_key = pair.public_key.decode("ascii")
    finally:
        pair.wipe()
        for index in range(len(seed_buffer)):
            seed_buffer[index] = 0
    return seed, public_key


def runner_nats_user_pop_payload(
    *,
    tenant_id: str,
    runner_id: UUID,
    machine_credential_id: UUID,
    machine_credential_version: int,
    correlation_id: UUID,
    idempotency_key: UUID,
    nats_user_public_key: str,
    requested_at: datetime,
) -> bytes:
    return "\n".join(
        (
            "crucible.runner.nats-key.pop.v1",
            f"tenant_id={tenant_id}",
            f"runner_id={runner_id}",
            f"credential_id={machine_credential_id}",
            f"credential_version={machine_credential_version}",
            f"correlation_id={correlation_id}",
            f"idempotency_key={idempotency_key}",
            f"nats_transport_profile={RUNNER_NATS_TRANSPORT_PROFILE}",
            f"nats_user_public_key={nats_user_public_key}",
            f"requested_at={_timestamp_nanos(requested_at)}",
        )
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class RunnerNatsTransportCredential:
    tenant_id: str
    runner_id: UUID
    transport_credential_id: UUID
    transport_credential_version: int
    transport_generation: int
    nats_user_public_key: str
    nats_user_seed: bytes = field(repr=False)
    nats_user_jwt: str = field(repr=False)
    nats_user_jwt_sha256: str
    issuer_account_public_nkey: str
    permission_profile: dict[str, Any]
    permission_profile_sha256: str
    durable_config: dict[str, Any]
    durable_config_sha256: str
    issued_at: datetime
    expires_at: datetime
    source_path: Path | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.tenant_id):
            raise RunnerNatsTransportError("tenant_id is not a safe authority identifier")
        object.__setattr__(self, "runner_id", _required_uuid(self.runner_id, "runner_id"))
        object.__setattr__(
            self,
            "transport_credential_id",
            _required_uuid(self.transport_credential_id, "transport_credential_id"),
        )
        if (
            type(self.transport_credential_version) is not int
            or self.transport_credential_version < 1
            or type(self.transport_generation) is not int
            or self.transport_generation < 1
        ):
            raise RunnerNatsTransportError("transport version and generation must be positive")
        if not _USER_NKEY.fullmatch(self.nats_user_public_key):
            raise RunnerNatsTransportError("NATS User public key is invalid")
        if not _ACCOUNT_NKEY.fullmatch(self.issuer_account_public_nkey):
            raise RunnerNatsTransportError("NATS issuer Account public key is invalid")
        if not _LOWER_SHA256.fullmatch(self.nats_user_jwt_sha256):
            raise RunnerNatsTransportError("NATS User JWT digest is invalid")
        if not _LOWER_SHA256.fullmatch(self.permission_profile_sha256):
            raise RunnerNatsTransportError("permission profile digest is invalid")
        if not _LOWER_SHA256.fullmatch(self.durable_config_sha256):
            raise RunnerNatsTransportError("durable config digest is invalid")
        object.__setattr__(self, "issued_at", self.issued_at.astimezone(UTC))
        object.__setattr__(self, "expires_at", self.expires_at.astimezone(UTC))
        if self.expires_at <= self.issued_at:
            raise RunnerNatsTransportError("NATS transport validity window is invalid")
        seed_buffer = bytearray(self.nats_user_seed)
        try:
            pair = nkeys.from_seed(seed_buffer)
            public_key = pair.public_key.decode("ascii")
        except Exception as exc:  # noqa: BLE001 - normalize nkeys implementation errors
            raise RunnerNatsTransportError("NATS User seed is invalid") from exc
        finally:
            if "pair" in locals():
                pair.wipe()
            for index in range(len(seed_buffer)):
                seed_buffer[index] = 0
        if public_key != self.nats_user_public_key:
            raise RunnerNatsTransportError("NATS User seed does not match public key")
        self._validate_authority()

    def _validate_authority(self) -> None:
        if _sha256(self.nats_user_jwt.encode("ascii")) != self.nats_user_jwt_sha256:
            raise RunnerNatsTransportError("NATS User JWT digest mismatch")
        if _sha256(_canonical_json_bytes(self.permission_profile)) != (
            self.permission_profile_sha256
        ):
            raise RunnerNatsTransportError("permission profile digest mismatch")
        if _sha256(_canonical_json_bytes(self.durable_config)) != self.durable_config_sha256:
            raise RunnerNatsTransportError("durable config digest mismatch")
        modes = self.permission_profile.get("authorized_modes")
        if (
            not isinstance(modes, list)
            or not modes
            or len(modes) != len(set(modes))
            or any(mode not in {"sandbox", "testnet", "live"} for mode in modes)
        ):
            raise RunnerNatsTransportError("authorized_modes is invalid")
        expected_permission = _expected_permission_profile(self.tenant_id, self.runner_id, modes)
        if self.permission_profile != expected_permission:
            raise RunnerNatsTransportError("permission profile is not exact CR100 authority")
        expected_durable = _expected_durable_config(self.tenant_id, self.runner_id, modes)
        if self.durable_config != expected_durable:
            raise RunnerNatsTransportError("durable config is not exact CR100 authority")
        _validate_jwt(
            self.nats_user_jwt,
            expected_issuer=self.issuer_account_public_nkey,
            expected_user=self.nats_user_public_key,
            expected_expiry=self.expires_at,
            permission_profile=self.permission_profile,
        )

    def assert_active(self, *, now: datetime | None = None) -> None:
        if self.source_path is not None and not self.source_path.exists():
            raise RunnerNatsTransportError("NATS transport vault was invalidated locally")
        if self.expires_at <= (now or datetime.now(UTC)).astimezone(UTC):
            raise RunnerNatsTransportError("NATS User JWT is expired")

    def to_document(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "runner_id": str(self.runner_id),
            "transport_credential_id": str(self.transport_credential_id),
            "transport_credential_version": self.transport_credential_version,
            "transport_generation": self.transport_generation,
            "nats_user_public_key": self.nats_user_public_key,
            "nats_user_seed_base64": base64.b64encode(self.nats_user_seed).decode("ascii"),
            "nats_user_jwt": self.nats_user_jwt,
            "nats_user_jwt_sha256": self.nats_user_jwt_sha256,
            "issuer_account_public_nkey": self.issuer_account_public_nkey,
            "permission_profile": self.permission_profile,
            "permission_profile_sha256": self.permission_profile_sha256,
            "durable_config": self.durable_config,
            "durable_config_sha256": self.durable_config_sha256,
            "issued_at": _timestamp_text(self.issued_at),
            "expires_at": _timestamp_text(self.expires_at),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> RunnerNatsTransportCredential:
        expected_fields = {
            "tenant_id",
            "runner_id",
            "transport_credential_id",
            "transport_credential_version",
            "transport_generation",
            "nats_user_public_key",
            "nats_user_seed_base64",
            "nats_user_jwt",
            "nats_user_jwt_sha256",
            "issuer_account_public_nkey",
            "permission_profile",
            "permission_profile_sha256",
            "durable_config",
            "durable_config_sha256",
            "issued_at",
            "expires_at",
        }
        if set(value) != expected_fields:
            raise RunnerNatsTransportError("NATS transport vault credential shape is invalid")
        try:
            seed = base64.b64decode(value["nats_user_seed_base64"], validate=True)
        except (TypeError, ValueError) as exc:
            raise RunnerNatsTransportError("NATS User seed encoding is invalid") from exc
        return cls(
            tenant_id=str(value["tenant_id"]),
            runner_id=_required_uuid(value["runner_id"], "runner_id"),
            transport_credential_id=_required_uuid(
                value["transport_credential_id"], "transport_credential_id"
            ),
            transport_credential_version=value["transport_credential_version"],
            transport_generation=value["transport_generation"],
            nats_user_public_key=str(value["nats_user_public_key"]),
            nats_user_seed=seed,
            nats_user_jwt=str(value["nats_user_jwt"]),
            nats_user_jwt_sha256=str(value["nats_user_jwt_sha256"]),
            issuer_account_public_nkey=str(value["issuer_account_public_nkey"]),
            permission_profile=_required_mapping(value["permission_profile"], "permission_profile"),
            permission_profile_sha256=str(value["permission_profile_sha256"]),
            durable_config=_required_mapping(value["durable_config"], "durable_config"),
            durable_config_sha256=str(value["durable_config_sha256"]),
            issued_at=_required_timestamp(value["issued_at"], "issued_at"),
            expires_at=_required_timestamp(value["expires_at"], "expires_at"),
        )

    @classmethod
    def from_issued_response(
        cls,
        response: Mapping[str, Any],
        *,
        tenant_id: str,
        runner_id: UUID,
        nats_user_seed: bytes,
        expected_issuer_account_public_nkey: str,
    ) -> RunnerNatsTransportCredential:
        expected_fields = {
            "transport_credential_id",
            "transport_credential_version",
            "transport_generation",
            "nats_transport_profile",
            "nats_user_public_key",
            "nats_user_jwt",
            "nats_user_jwt_sha256",
            "issuer_account_public_nkey",
            "permission_profile",
            "permission_profile_sha256",
            "durable_config",
            "durable_config_sha256",
            "issued_at",
            "expires_at",
        }
        if set(response) != expected_fields:
            raise RunnerNatsTransportError("CR100 issuance response shape is invalid")
        if response["nats_transport_profile"] != RUNNER_NATS_TRANSPORT_PROFILE:
            raise RunnerNatsTransportError("CR100 transport profile is unsupported")
        if response["issuer_account_public_nkey"] != expected_issuer_account_public_nkey:
            raise RunnerNatsTransportError("CR100 issuer Account pin mismatch")
        return cls(
            tenant_id=tenant_id,
            runner_id=runner_id,
            transport_credential_id=_required_uuid(
                response["transport_credential_id"], "transport_credential_id"
            ),
            transport_credential_version=response["transport_credential_version"],
            transport_generation=response["transport_generation"],
            nats_user_public_key=str(response["nats_user_public_key"]),
            nats_user_seed=nats_user_seed,
            nats_user_jwt=str(response["nats_user_jwt"]),
            nats_user_jwt_sha256=str(response["nats_user_jwt_sha256"]),
            issuer_account_public_nkey=str(response["issuer_account_public_nkey"]),
            permission_profile=_required_mapping(
                response["permission_profile"], "permission_profile"
            ),
            permission_profile_sha256=str(response["permission_profile_sha256"]),
            durable_config=_required_mapping(response["durable_config"], "durable_config"),
            durable_config_sha256=str(response["durable_config_sha256"]),
            issued_at=_required_timestamp(response["issued_at"], "issued_at"),
            expires_at=_required_timestamp(response["expires_at"], "expires_at"),
        )


@dataclass(frozen=True, slots=True)
class RunnerNatsRevocationChallenge:
    profile: str
    tenant_id: str
    runner_id: UUID
    transport_credential_id: UUID
    generation: int
    user_public_nkey: str
    resolver_account_jwt_sha256: str
    revoke_before: datetime
    challenge_nonce: UUID
    expected_binding_revision: int
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.profile != _REVOCATION_CHALLENGE_PROFILE:
            raise RunnerNatsTransportError("CR100 revocation challenge profile is invalid")
        if not _SAFE_ID.fullmatch(self.tenant_id):
            raise RunnerNatsTransportError("revocation challenge tenant_id is invalid")
        object.__setattr__(self, "runner_id", _required_uuid(self.runner_id, "runner_id"))
        object.__setattr__(
            self,
            "transport_credential_id",
            _required_uuid(self.transport_credential_id, "transport_credential_id"),
        )
        object.__setattr__(
            self,
            "challenge_nonce",
            _required_uuid(self.challenge_nonce, "challenge_nonce"),
        )
        if type(self.generation) is not int or self.generation < 1:
            raise RunnerNatsTransportError("revocation challenge generation is invalid")
        if type(self.expected_binding_revision) is not int or self.expected_binding_revision < 1:
            raise RunnerNatsTransportError("revocation challenge binding revision is invalid")
        if not _USER_NKEY.fullmatch(self.user_public_nkey):
            raise RunnerNatsTransportError("revocation challenge User NKey is invalid")
        if not _LOWER_SHA256.fullmatch(self.resolver_account_jwt_sha256):
            raise RunnerNatsTransportError("revocation challenge resolver digest is invalid")
        for field_name in ("revoke_before", "issued_at", "expires_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None:
                raise RunnerNatsTransportError(
                    f"revocation challenge {field_name} must include a timezone"
                )
            object.__setattr__(self, field_name, value.astimezone(UTC))
        if self.expires_at <= self.issued_at or self.revoke_before > self.expires_at:
            raise RunnerNatsTransportError("revocation challenge time window is invalid")

    def assert_fresh(self, *, now: datetime | None = None) -> None:
        if self.expires_at <= (now or datetime.now(UTC)).astimezone(UTC):
            raise RunnerNatsTransportError("CR100 revocation challenge is expired")

    def assert_credential_binding(self, credential: RunnerNatsTransportCredential) -> None:
        expected = (
            self.tenant_id == credential.tenant_id
            and self.runner_id == credential.runner_id
            and self.transport_credential_id == credential.transport_credential_id
            and self.generation == credential.transport_generation
            and self.user_public_nkey == credential.nats_user_public_key
        )
        if not expected:
            raise RunnerNatsTransportError("CR100 revocation challenge credential binding mismatch")

    def to_document(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "tenant_id": self.tenant_id,
            "runner_id": str(self.runner_id),
            "transport_credential_id": str(self.transport_credential_id),
            "generation": self.generation,
            "user_public_nkey": self.user_public_nkey,
            "resolver_account_jwt_sha256": self.resolver_account_jwt_sha256,
            "revoke_before": _timestamp_text(self.revoke_before),
            "challenge_nonce": str(self.challenge_nonce),
            "expected_binding_revision": self.expected_binding_revision,
            "issued_at": _timestamp_text(self.issued_at),
            "expires_at": _timestamp_text(self.expires_at),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> RunnerNatsRevocationChallenge:
        expected_fields = {
            "profile",
            "tenant_id",
            "runner_id",
            "transport_credential_id",
            "generation",
            "user_public_nkey",
            "resolver_account_jwt_sha256",
            "revoke_before",
            "challenge_nonce",
            "expected_binding_revision",
            "issued_at",
            "expires_at",
        }
        if set(value) != expected_fields:
            raise RunnerNatsTransportError("CR100 revocation challenge shape is invalid")
        return cls(
            profile=str(value["profile"]),
            tenant_id=str(value["tenant_id"]),
            runner_id=_required_uuid(value["runner_id"], "runner_id"),
            transport_credential_id=_required_uuid(
                value["transport_credential_id"], "transport_credential_id"
            ),
            generation=value["generation"],
            user_public_nkey=str(value["user_public_nkey"]),
            resolver_account_jwt_sha256=str(value["resolver_account_jwt_sha256"]),
            revoke_before=_required_timestamp(value["revoke_before"], "revoke_before"),
            challenge_nonce=_required_uuid(value["challenge_nonce"], "challenge_nonce"),
            expected_binding_revision=value["expected_binding_revision"],
            issued_at=_required_timestamp(value["issued_at"], "issued_at"),
            expires_at=_required_timestamp(value["expires_at"], "expires_at"),
        )

    @classmethod
    def from_response(
        cls,
        value: Mapping[str, Any],
        credential: RunnerNatsTransportCredential,
    ) -> RunnerNatsRevocationChallenge:
        challenge = cls.from_document(value)
        challenge.assert_credential_binding(credential)
        challenge.assert_fresh()
        return challenge


@dataclass(frozen=True, slots=True)
class RunnerNatsRevocationObservation:
    challenge: RunnerNatsRevocationChallenge
    replacement_transport_credential_id: UUID
    replacement_generation: int
    replacement_connected_at: datetime
    challenge_validated_at: datetime
    challenge_expiry_outcome: str = "fresh"
    forced_disconnect_observed_at: datetime | None = None
    old_generation_reconnect_denied_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "replacement_transport_credential_id",
            _required_uuid(
                self.replacement_transport_credential_id,
                "replacement_transport_credential_id",
            ),
        )
        if (
            type(self.replacement_generation) is not int
            or self.replacement_generation <= self.challenge.generation
        ):
            raise RunnerNatsTransportError(
                "replacement generation must supersede the revoked generation"
            )
        if self.challenge_expiry_outcome != "fresh":
            raise RunnerNatsTransportError("only a fresh revocation challenge may produce evidence")
        for field_name in (
            "replacement_connected_at",
            "challenge_validated_at",
            "forced_disconnect_observed_at",
            "old_generation_reconnect_denied_at",
            "completed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if value.tzinfo is None:
                    raise RunnerNatsTransportError(
                        f"revocation observation {field_name} must include a timezone"
                    )
                object.__setattr__(self, field_name, value.astimezone(UTC))
        if (
            self.old_generation_reconnect_denied_at is not None
            and self.forced_disconnect_observed_at is None
        ):
            raise RunnerNatsTransportError(
                "old-generation denial cannot precede forced-disconnect evidence"
            )
        if self.completed_at is not None and not self.evidence_ready:
            raise RunnerNatsTransportError(
                "revocation completion requires both Custos observations"
            )

    @property
    def evidence_ready(self) -> bool:
        return (
            self.forced_disconnect_observed_at is not None
            and self.old_generation_reconnect_denied_at is not None
        )

    def mark_forced_disconnect(self, observed_at: datetime) -> RunnerNatsRevocationObservation:
        return replace(
            self,
            forced_disconnect_observed_at=(
                self.forced_disconnect_observed_at or observed_at.astimezone(UTC)
            ),
        )

    def mark_reconnect_denied(self, observed_at: datetime) -> RunnerNatsRevocationObservation:
        if self.forced_disconnect_observed_at is None:
            raise RunnerNatsTransportError(
                "forced disconnect must be durable before reconnect denial"
            )
        return replace(
            self,
            old_generation_reconnect_denied_at=(
                self.old_generation_reconnect_denied_at or observed_at.astimezone(UTC)
            ),
        )

    def mark_completed(self, completed_at: datetime) -> RunnerNatsRevocationObservation:
        if not self.evidence_ready:
            raise RunnerNatsTransportError("incomplete revocation evidence cannot complete")
        return replace(self, completed_at=completed_at.astimezone(UTC))

    def to_document(self) -> dict[str, Any]:
        return {
            "challenge": self.challenge.to_document(),
            "replacement_transport_credential_id": str(self.replacement_transport_credential_id),
            "replacement_generation": self.replacement_generation,
            "replacement_connected_at": _timestamp_text(self.replacement_connected_at),
            "challenge_validated_at": _timestamp_text(self.challenge_validated_at),
            "challenge_expiry_outcome": self.challenge_expiry_outcome,
            "forced_disconnect_observed_at": (
                _timestamp_text(self.forced_disconnect_observed_at)
                if self.forced_disconnect_observed_at is not None
                else None
            ),
            "old_generation_reconnect_denied_at": (
                _timestamp_text(self.old_generation_reconnect_denied_at)
                if self.old_generation_reconnect_denied_at is not None
                else None
            ),
            "completed_at": (
                _timestamp_text(self.completed_at) if self.completed_at is not None else None
            ),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> RunnerNatsRevocationObservation:
        if set(value) != {
            "challenge",
            "replacement_transport_credential_id",
            "replacement_generation",
            "replacement_connected_at",
            "challenge_validated_at",
            "challenge_expiry_outcome",
            "forced_disconnect_observed_at",
            "old_generation_reconnect_denied_at",
            "completed_at",
        }:
            raise RunnerNatsTransportError("revocation observation shape is invalid")

        def optional_timestamp(field_name: str) -> datetime | None:
            field_value = value[field_name]
            return _required_timestamp(field_value, field_name) if field_value is not None else None

        return cls(
            challenge=RunnerNatsRevocationChallenge.from_document(
                _required_mapping(value["challenge"], "challenge")
            ),
            replacement_transport_credential_id=_required_uuid(
                value["replacement_transport_credential_id"],
                "replacement_transport_credential_id",
            ),
            replacement_generation=value["replacement_generation"],
            replacement_connected_at=_required_timestamp(
                value["replacement_connected_at"], "replacement_connected_at"
            ),
            challenge_validated_at=_required_timestamp(
                value["challenge_validated_at"], "challenge_validated_at"
            ),
            challenge_expiry_outcome=str(value["challenge_expiry_outcome"]),
            forced_disconnect_observed_at=optional_timestamp("forced_disconnect_observed_at"),
            old_generation_reconnect_denied_at=optional_timestamp(
                "old_generation_reconnect_denied_at"
            ),
            completed_at=optional_timestamp("completed_at"),
        )


@dataclass(frozen=True, slots=True)
class RunnerNatsTransportBundle:
    active: RunnerNatsTransportCredential | None
    pending: RunnerNatsTransportCredential | None
    retiring: RunnerNatsTransportCredential | None = None
    revocation: RunnerNatsRevocationObservation | None = None

    def __post_init__(self) -> None:
        if self.active is None and self.pending is None and self.retiring is None:
            raise RunnerNatsTransportError("NATS transport vault has no credential")
        if self.active is not None and self.pending is not None:
            if (
                self.active.tenant_id != self.pending.tenant_id
                or self.active.runner_id != self.pending.runner_id
                or self.active.issuer_account_public_nkey != self.pending.issuer_account_public_nkey
                or self.pending.transport_generation <= self.active.transport_generation
            ):
                raise RunnerNatsTransportError("pending NATS generation is not a valid rotation")
        if self.pending is not None and self.retiring is not None:
            raise RunnerNatsTransportError("pending and retiring NATS generations cannot coexist")
        if self.retiring is not None:
            if self.active is None or (
                self.retiring.tenant_id != self.active.tenant_id
                or self.retiring.runner_id != self.active.runner_id
                or self.retiring.issuer_account_public_nkey
                != self.active.issuer_account_public_nkey
                or self.retiring.transport_generation >= self.active.transport_generation
            ):
                raise RunnerNatsTransportError(
                    "retiring NATS generation is not superseded by active authority"
                )
        if self.revocation is not None:
            if self.active is None or (
                self.revocation.replacement_transport_credential_id
                != self.active.transport_credential_id
                or self.revocation.replacement_generation != self.active.transport_generation
            ):
                raise RunnerNatsTransportError(
                    "revocation observation replacement binding mismatch"
                )
            if self.retiring is None:
                if self.revocation.completed_at is None:
                    raise RunnerNatsTransportError(
                        "incomplete revocation requires the retiring credential"
                    )
            else:
                self.revocation.challenge.assert_credential_binding(self.retiring)

    def promote_pending(self) -> RunnerNatsTransportBundle:
        if self.pending is None:
            raise RunnerNatsTransportError("NATS transport vault has no pending generation")
        return RunnerNatsTransportBundle(
            active=self.pending,
            pending=None,
            retiring=self.active,
            revocation=None,
        )

    def with_revocation(
        self, observation: RunnerNatsRevocationObservation
    ) -> RunnerNatsTransportBundle:
        if self.retiring is None:
            raise RunnerNatsTransportError("NATS transport vault has no retiring generation")
        observation.challenge.assert_credential_binding(self.retiring)
        return replace(self, revocation=observation)

    def complete_retirement(self, completed_at: datetime) -> RunnerNatsTransportBundle:
        if self.retiring is None or self.revocation is None:
            raise RunnerNatsTransportError("NATS transport retirement is not in progress")
        return replace(
            self,
            retiring=None,
            revocation=self.revocation.mark_completed(completed_at),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "active": self.active.to_document() if self.active is not None else None,
            "pending": self.pending.to_document() if self.pending is not None else None,
            "retiring": (self.retiring.to_document() if self.retiring is not None else None),
            "revocation": (self.revocation.to_document() if self.revocation is not None else None),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> RunnerNatsTransportBundle:
        version = value.get("schema_version")
        expected = (
            {"schema_version", "active", "pending"}
            if version == 1
            else {"schema_version", "active", "pending", "retiring", "revocation"}
        )
        if set(value) != expected:
            raise RunnerNatsTransportError("NATS transport vault shape is invalid")
        if version not in {1, 2}:
            raise RunnerNatsTransportError("NATS transport vault version is unsupported")
        active_value = value.get("active")
        pending_value = value.get("pending")
        retiring_value = value.get("retiring")
        revocation_value = value.get("revocation")
        if active_value is not None and not isinstance(active_value, dict):
            raise RunnerNatsTransportError("active NATS transport credential is invalid")
        if pending_value is not None and not isinstance(pending_value, dict):
            raise RunnerNatsTransportError("pending NATS transport credential is invalid")
        if retiring_value is not None and not isinstance(retiring_value, dict):
            raise RunnerNatsTransportError("retiring NATS transport credential is invalid")
        if revocation_value is not None and not isinstance(revocation_value, dict):
            raise RunnerNatsTransportError("NATS revocation observation is invalid")
        return cls(
            active=(
                RunnerNatsTransportCredential.from_document(active_value)
                if active_value is not None
                else None
            ),
            pending=(
                RunnerNatsTransportCredential.from_document(pending_value)
                if pending_value is not None
                else None
            ),
            retiring=(
                RunnerNatsTransportCredential.from_document(retiring_value)
                if retiring_value is not None
                else None
            ),
            revocation=(
                RunnerNatsRevocationObservation.from_document(revocation_value)
                if revocation_value is not None
                else None
            ),
        )


class RunnerNatsTransportVault:
    """Dedicated sops+age vault with active/pending rotation semantics."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def load(self) -> RunnerNatsTransportBundle:
        if not self.path.exists():
            raise RunnerNatsTransportError(
                f"NATS transport vault {self.path} is missing; "
                "run `arx-runner nats-transport enroll`"
            )
        if stat.S_IMODE(self.path.stat().st_mode) & _WORLD_GROUP_BITS:
            raise RunnerNatsTransportError("NATS transport vault must have mode 0600")
        _require_age_key_file()
        try:
            result = subprocess.run(
                (
                    "sops",
                    "--decrypt",
                    "--input-type",
                    "json",
                    "--output-type",
                    "json",
                    str(self.path),
                ),
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            raise RunnerNatsTransportError("cannot execute sops for NATS transport vault") from exc
        if result.returncode != 0:
            raise RunnerNatsTransportError("cannot decrypt NATS transport vault")
        try:
            document = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RunnerNatsTransportError("NATS transport vault is not valid JSON") from exc
        if not isinstance(document, dict):
            raise RunnerNatsTransportError("NATS transport vault root must be an object")
        bundle = RunnerNatsTransportBundle.from_document(document)
        return RunnerNatsTransportBundle(
            active=(
                replace(bundle.active, source_path=self.path) if bundle.active is not None else None
            ),
            pending=(
                replace(bundle.pending, source_path=self.path)
                if bundle.pending is not None
                else None
            ),
            retiring=(
                replace(bundle.retiring, source_path=self.path)
                if bundle.retiring is not None
                else None
            ),
            revocation=bundle.revocation,
        )

    def persist(self, bundle: RunnerNatsTransportBundle, *, age_recipient: str) -> None:
        recipient = age_recipient.strip()
        if not recipient.startswith("age1"):
            raise RunnerNatsTransportError("age recipient must be an age1 public recipient")
        self.path.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        os.chmod(self.path.parent, _DIR_MODE)
        plaintext = _canonical_json_bytes(bundle.to_document()) + b"\n"
        try:
            result = subprocess.run(
                (
                    "sops",
                    "--encrypt",
                    "--age",
                    recipient,
                    "--input-type",
                    "json",
                    "--output-type",
                    "json",
                    "/dev/stdin",
                ),
                input=plaintext,
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            raise RunnerNatsTransportError("cannot execute sops for NATS transport vault") from exc
        finally:
            plaintext = b""
        if result.returncode != 0 or not result.stdout:
            raise RunnerNatsTransportError("cannot encrypt NATS transport vault")
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temp_path = Path(temp_name)
        try:
            os.fchmod(descriptor, _FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(result.stdout)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            os.chmod(self.path, _FILE_MODE)
            _fsync_directory(self.path.parent)
        finally:
            temp_path.unlink(missing_ok=True)


class RunnerNatsTransportAuthorityClient:
    """Machine-authenticated direct Crucible transport lifecycle client."""

    def __init__(self, crucible_url: str, machine_credential: MachineCredential) -> None:
        self.machine_credential = machine_credential
        self.http = MachineCredentialHttpClient(crucible_url, machine_credential)

    def issue_initial(
        self,
        *,
        expected_issuer_account_public_nkey: str,
        now: datetime | None = None,
    ) -> RunnerNatsTransportCredential:
        return self._issue(
            path=_ISSUE_PATH,
            canonical_path=_CANONICAL_ISSUE_PATH,
            expected_issuer_account_public_nkey=expected_issuer_account_public_nkey,
            expected_generation=None,
            now=now,
        )

    def issue_rotation(
        self,
        active: RunnerNatsTransportCredential,
        *,
        now: datetime | None = None,
    ) -> RunnerNatsTransportCredential:
        if (
            active.tenant_id != self.machine_credential.tenant_id
            or active.runner_id != self.machine_credential.runner_id
        ):
            raise RunnerNatsTransportError("active NATS credential has wrong machine binding")
        return self._issue(
            path=_ROTATE_PATH,
            canonical_path=_CANONICAL_ROTATE_PATH,
            expected_issuer_account_public_nkey=active.issuer_account_public_nkey,
            expected_generation=active.transport_generation,
            now=now,
        )

    def _issue(
        self,
        *,
        path: str,
        canonical_path: str,
        expected_issuer_account_public_nkey: str,
        expected_generation: int | None,
        now: datetime | None,
    ) -> RunnerNatsTransportCredential:
        requested_at = (now or datetime.now(UTC)).astimezone(UTC)
        correlation_id = uuid4()
        idempotency_key = uuid4()
        seed, public_key = generate_runner_user_nkey()
        proof = runner_nats_user_pop_payload(
            tenant_id=self.machine_credential.tenant_id,
            runner_id=self.machine_credential.runner_id,
            machine_credential_id=self.machine_credential.credential_id,
            machine_credential_version=self.machine_credential.credential_version,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            nats_user_public_key=public_key,
            requested_at=requested_at,
        )
        seed_buffer = bytearray(seed)
        pair = nkeys.from_seed(seed_buffer)
        try:
            proof_signature = base64.b64encode(pair.sign(proof)).decode("ascii")
        finally:
            pair.wipe()
            for index in range(len(seed_buffer)):
                seed_buffer[index] = 0
        body: dict[str, Any] = {
            "tenant_id": self.machine_credential.tenant_id,
            "runner_id": str(self.machine_credential.runner_id),
            "credential_id": str(self.machine_credential.credential_id),
            "credential_version": self.machine_credential.credential_version,
            "correlation_id": str(correlation_id),
            "idempotency_key": str(idempotency_key),
            "nats_transport_profile": RUNNER_NATS_TRANSPORT_PROFILE,
            "nats_user_public_key": public_key,
            "nats_user_proof_signature_base64": proof_signature,
            "requested_at": _timestamp_nanos(requested_at),
        }
        if expected_generation is not None:
            body["expected_generation"] = expected_generation
        response = self.http.post(
            path,
            body,
            canonical_path=canonical_path,
            correlation_id=correlation_id,
        )
        return RunnerNatsTransportCredential.from_issued_response(
            response,
            tenant_id=self.machine_credential.tenant_id,
            runner_id=self.machine_credential.runner_id,
            nats_user_seed=seed,
            expected_issuer_account_public_nkey=expected_issuer_account_public_nkey,
        )

    def activate(self, credential: RunnerNatsTransportCredential) -> dict[str, Any]:
        correlation_id = uuid4()
        body = {
            "tenant_id": self.machine_credential.tenant_id,
            "runner_id": str(self.machine_credential.runner_id),
            "credential_id": str(self.machine_credential.credential_id),
            "credential_version": self.machine_credential.credential_version,
            "correlation_id": str(correlation_id),
            "transport_credential_id": str(credential.transport_credential_id),
            "transport_generation": credential.transport_generation,
            "expected_revision": None,
            "reason": "custos-local-generation-ready",
        }
        response = self.http.post(
            _ACTIVATE_PATH,
            body,
            canonical_path=_CANONICAL_ACTIVATE_PATH,
            correlation_id=correlation_id,
        )
        expected = {
            "tenant_id": credential.tenant_id,
            "runner_id": str(credential.runner_id),
            "transport_credential_id": str(credential.transport_credential_id),
            "generation": credential.transport_generation,
            "status": "active",
        }
        if any(response.get(key) != value for key, value in expected.items()):
            raise RunnerNatsTransportError("CR100 activation response binding mismatch")
        if type(response.get("revision")) is not int or response["revision"] < 1:
            raise RunnerNatsTransportError("CR100 activation revision is invalid")
        return response

    def revoke_superseded(
        self,
        credential: RunnerNatsTransportCredential,
        *,
        expected_active_revision: int,
        reason: str,
    ) -> RunnerNatsRevocationChallenge:
        self._assert_credential_binding(credential)
        if type(expected_active_revision) is not int or expected_active_revision < 1:
            raise RunnerNatsTransportError("active NATS binding revision is invalid")
        if not reason.strip():
            raise RunnerNatsTransportError("NATS revocation reason is required")
        correlation_id = uuid4()
        body = {
            "tenant_id": self.machine_credential.tenant_id,
            "runner_id": str(self.machine_credential.runner_id),
            "credential_id": str(self.machine_credential.credential_id),
            "credential_version": self.machine_credential.credential_version,
            "correlation_id": str(correlation_id),
            "transport_credential_id": str(credential.transport_credential_id),
            "transport_generation": credential.transport_generation,
            "expected_active_revision": expected_active_revision,
            "reason": reason,
        }
        response = self.http.post(
            _REVOKE_SUPERSEDED_PATH,
            body,
            canonical_path=_CANONICAL_REVOKE_SUPERSEDED_PATH,
            correlation_id=correlation_id,
        )
        return RunnerNatsRevocationChallenge.from_response(response, credential)

    def read_revocation_challenge(
        self, credential: RunnerNatsTransportCredential
    ) -> RunnerNatsRevocationChallenge:
        self._assert_credential_binding(credential)
        correlation_id = uuid4()
        body = {
            "tenant_id": self.machine_credential.tenant_id,
            "runner_id": str(self.machine_credential.runner_id),
            "credential_id": str(self.machine_credential.credential_id),
            "credential_version": self.machine_credential.credential_version,
            "correlation_id": str(correlation_id),
            "transport_credential_id": str(credential.transport_credential_id),
            "transport_generation": credential.transport_generation,
        }
        response = self.http.post(
            _REVOCATION_CHALLENGE_PATH,
            body,
            canonical_path=_CANONICAL_REVOCATION_CHALLENGE_PATH,
            correlation_id=correlation_id,
        )
        return RunnerNatsRevocationChallenge.from_response(response, credential)

    def submit_revocation_evidence(
        self,
        observation: RunnerNatsRevocationObservation,
        *,
        reason: str,
    ) -> datetime:
        if not observation.evidence_ready:
            raise RunnerNatsTransportError("Custos revocation evidence is incomplete")
        observation.challenge.assert_fresh()
        if not reason.strip():
            raise RunnerNatsTransportError("NATS revocation evidence reason is required")
        correlation_id = uuid4()
        challenge = observation.challenge
        assert observation.old_generation_reconnect_denied_at is not None
        body = {
            "profile": _REVOCATION_EVIDENCE_PROFILE,
            "tenant_id": self.machine_credential.tenant_id,
            "runner_id": str(self.machine_credential.runner_id),
            "credential_id": str(self.machine_credential.credential_id),
            "credential_version": self.machine_credential.credential_version,
            "correlation_id": str(correlation_id),
            "transport_credential_id": str(challenge.transport_credential_id),
            "transport_generation": challenge.generation,
            "user_public_nkey": challenge.user_public_nkey,
            "resolver_account_jwt_sha256": challenge.resolver_account_jwt_sha256,
            "revoke_before": _timestamp_text(challenge.revoke_before),
            "challenge_nonce": str(challenge.challenge_nonce),
            "expected_binding_revision": challenge.expected_binding_revision,
            "forced_disconnect_observed": True,
            "old_generation_reconnect_denied": True,
            "observed_at": _timestamp_text(observation.old_generation_reconnect_denied_at),
            "reason": reason,
        }
        response = self.http.post(
            _REVOCATION_EVIDENCE_PATH,
            body,
            canonical_path=_CANONICAL_REVOCATION_EVIDENCE_PATH,
            correlation_id=correlation_id,
        )
        expected_fields = {
            "tenant_id",
            "runner_id",
            "transport_credential_id",
            "generation",
            "resolver_account_jwt_sha256",
            "completed_at",
        }
        expected_values = {
            "tenant_id": challenge.tenant_id,
            "runner_id": str(challenge.runner_id),
            "transport_credential_id": str(challenge.transport_credential_id),
            "generation": challenge.generation,
            "resolver_account_jwt_sha256": challenge.resolver_account_jwt_sha256,
        }
        if set(response) != expected_fields or any(
            response.get(key) != value for key, value in expected_values.items()
        ):
            raise RunnerNatsTransportError("CR100 revocation completion binding mismatch")
        return _required_timestamp(response["completed_at"], "completed_at")

    def _assert_credential_binding(self, credential: RunnerNatsTransportCredential) -> None:
        if (
            credential.tenant_id != self.machine_credential.tenant_id
            or credential.runner_id != self.machine_credential.runner_id
        ):
            raise RunnerNatsTransportError("NATS credential has wrong machine authority binding")


@dataclass(slots=True)
class RunnerNatsTransportConnectionProfile:
    credential: RunnerNatsTransportCredential
    nats_url: str
    ca_path: Path
    server_name: str
    pinned_issuer_account_public_nkey: str
    _authorization_denied: asyncio.Event = field(
        default_factory=asyncio.Event,
        init=False,
        repr=False,
    )
    _disconnected: asyncio.Event = field(
        default_factory=asyncio.Event,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.nats_url)
        if (
            parsed.scheme != "tls"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise RunnerNatsTransportError("NATS transport requires a credential-free tls:// URL")
        if parsed.hostname != self.server_name:
            raise RunnerNatsTransportError("NATS TLS server name must equal the configured host")
        self.ca_path = self.ca_path.expanduser().resolve()
        if not self.ca_path.is_file():
            raise RunnerNatsTransportError("NATS TLS CA file is missing")
        if self.pinned_issuer_account_public_nkey != (self.credential.issuer_account_public_nkey):
            raise RunnerNatsTransportError("NATS issuer Account pin mismatch")
        self.credential.assert_active()

    @property
    def tenant_id(self) -> str:
        return self.credential.tenant_id

    @property
    def runner_id(self) -> UUID:
        return self.credential.runner_id

    @property
    def durable_config(self) -> Mapping[str, Any]:
        return self.credential.durable_config

    def assert_active(self) -> None:
        self.credential.assert_active()
        if self._authorization_denied.is_set():
            raise RunnerNatsTransportRevokedError(
                "NATS broker rejected the active User JWT generation"
            )

    async def wait_authorization_denied(self) -> None:
        await self._authorization_denied.wait()

    @property
    def authorization_denied(self) -> bool:
        return self._authorization_denied.is_set()

    def mark_authorization_denied(self) -> None:
        self._authorization_denied.set()

    async def wait_disconnected(self) -> None:
        await self._disconnected.wait()

    def assert_publish_subject(self, subject: str) -> None:
        self.assert_active()
        allowed = self.credential.permission_profile["publish_allow"]
        if not any(_subject_matches(pattern, subject) for pattern in allowed):
            raise RunnerNatsTransportError("RunnerFact subject is outside CR100 authority")

    async def connect(
        self,
        *,
        name: str,
        error_cb: Callable[[Exception], Awaitable[None] | None] | None = None,
        disconnected_cb: Callable[[], Awaitable[None] | None] | None = None,
        allow_reconnect: bool = True,
        max_reconnect_attempts: int = -1,
    ) -> Any:
        self.assert_active()
        context = ssl.create_default_context(cafile=str(self.ca_path))
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        def user_jwt_cb() -> bytearray:
            self.assert_active()
            return bytearray(self.credential.nats_user_jwt.encode("ascii"))

        def signature_cb(nonce: str) -> bytes:
            self.assert_active()
            seed = bytearray(self.credential.nats_user_seed)
            pair = nkeys.from_seed(seed)
            try:
                return base64.b64encode(pair.sign(nonce.encode("utf-8")))
            finally:
                pair.wipe()
                for index in range(len(seed)):
                    seed[index] = 0

        async def guarded_error_cb(error: Exception) -> None:
            if isinstance(error, nats_errors.AuthorizationError):
                self.mark_authorization_denied()
            if error_cb is not None:
                result = error_cb(error)
                if inspect.isawaitable(result):
                    await result

        async def guarded_disconnected_cb() -> None:
            self._disconnected.set()
            if disconnected_cb is not None:
                result = disconnected_cb()
                if inspect.isawaitable(result):
                    await result

        return await nats.connect(
            servers=[self.nats_url],
            name=name,
            tls=context,
            tls_hostname=self.server_name,
            user_jwt_cb=user_jwt_cb,
            signature_cb=signature_cb,
            error_cb=guarded_error_cb,
            disconnected_cb=guarded_disconnected_cb,
            allow_reconnect=allow_reconnect,
            max_reconnect_attempts=max_reconnect_attempts,
        )


async def assert_old_generation_reconnect_denied(
    profile: RunnerNatsTransportConnectionProfile,
    *,
    name: str,
    timeout_seconds: float,
) -> None:
    """Accept only an explicit broker authorization denial for the exact old JWT."""

    if timeout_seconds <= 0:
        raise RunnerNatsTransportError("old-generation reconnect timeout must be positive")

    async def attempt() -> None:
        connection: Any | None = None
        try:
            connection = await profile.connect(
                name=name,
                allow_reconnect=False,
                max_reconnect_attempts=0,
            )
        except Exception as exc:  # noqa: BLE001 - typed callback is the evidence boundary
            if profile.authorization_denied:
                return
            raise RunnerNatsTransportError(
                "old-generation reconnect failed without explicit authorization denial"
            ) from exc
        finally:
            if connection is not None and not connection.is_closed:
                await connection.close()
        raise RunnerNatsTransportError("revoked old NATS generation reconnected")

    try:
        await asyncio.wait_for(attempt(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise RunnerNatsTransportError(
            "old-generation reconnect timed out without authorization denial"
        ) from exc


def _subject_matches(pattern: str, subject: str) -> bool:
    if pattern.endswith(".>"):
        prefix = pattern[:-1]
        return subject.startswith(prefix) and len(subject) > len(prefix)
    return pattern == subject


def _require_age_key_file() -> Path:
    configured = os.environ.get("SOPS_AGE_KEY_FILE", "").strip()
    if not configured:
        raise RunnerNatsTransportError("SOPS_AGE_KEY_FILE is required")
    path = Path(configured).expanduser().resolve()
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise RunnerNatsTransportError("SOPS_AGE_KEY_FILE is not readable") from exc
    if mode & _WORLD_GROUP_BITS:
        raise RunnerNatsTransportError(
            "SOPS_AGE_KEY_FILE must not be accessible by group or others"
        )
    return path


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
