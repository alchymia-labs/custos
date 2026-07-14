"""Crucible-signed DeploymentSpec consumer contract.

ARX authorizes human intent but never signs or relays runner commands. Crucible
publishes an exact-instance command as a signed domain event. Custos verifies the
original event bytes and subject before translating the canonical payload into
the local execution-engine shape.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

DEPLOYMENT_SPEC_SCHEMA_ID = (
    "https://custos.the-alephain-guild/runner-contract/v1/deployment_spec.schema.json"
)
DOMAIN_EVENT_SIGNATURE_CONTEXT = b"CRUCIBLE-DOMAIN-EVENT-V2\0"
DOMAIN_EVENT_SIGNATURE_PROFILE = "crucible-domain-event-v2-exact-bytes"
DOMAIN_EVENT_ENCODING = "application/json;base64url"
DEPLOYMENT_SPEC_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
_CANONICAL_DEPLOYMENT_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "deployment_spec_id",
        "tenant_id",
        "trading_mode",
        "strategy_id",
        "strategy_release_id",
        "strategy_release_version",
        "strategy_artifact_digest",
        "strategy_manifest_digest",
        "strategy_release_snapshot_digest",
        "parameters",
        "code_provenance",
        "strategy_product_id",
        "risk_policy_id",
        "risk_policy_version",
        "risk_policy_digest",
        "target_runner_id",
        "engine_binding_id",
        "execution_channel",
        "credential_scope",
        "runner_contract_requirements",
        "venue_source_policy",
        "source_policy_digest",
        "scheduling_policy",
        "scheduling_policy_digest",
        "promotion_id",
        "promotion_evidence_digest",
    }
)
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
SafeId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]


class TradingMode(StrEnum):
    SANDBOX = "sandbox"
    TESTNET = "testnet"
    LIVE = "live"


class LifecycleState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: SafeId


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_balances: list[str] = Field(min_length=1)


class DeploymentSpec(BaseModel):
    """Validated local execution view of a canonical Crucible DeploymentSpec."""

    model_config = ConfigDict(extra="forbid", title="DeploymentSpecPayload v1")

    spec_id: UUID
    deployment_instance_id: UUID
    deployment_spec_digest: Sha256Hex
    strategy_id: UUID
    generation: StrictInt = Field(ge=1)
    trading_mode: TradingMode
    lifecycle_state: LifecycleState
    strategy_path: str = Field(min_length=1)
    provenance_ref: ProvenanceRef
    connector: str = Field(min_length=1)
    pairs: list[str] = Field(min_length=1)
    leverage: StrictInt = Field(ge=1)
    strategy_config: dict[str, Any] = Field(default_factory=dict)
    strategy_registry_name: str | None = None
    code_hash: Sha256Hex
    log_level: str = "INFO"
    sandbox: SandboxConfig | None = None
    risk_config: dict[str, Any] = Field(default_factory=dict)
    nautilus_config: dict[str, Any] = Field(default_factory=dict)
    promotion_id: UUID | None = None
    promotion_evidence_digest: Sha256Hex | None = None

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Self:
        if self.trading_mode is TradingMode.LIVE:
            if self.promotion_id is None or self.promotion_evidence_digest is None:
                raise ValueError("live deployment requires Crucible-signed promotion evidence")
        if self.trading_mode is TradingMode.SANDBOX and self.sandbox is None:
            raise ValueError("sandbox deployment requires sandbox.starting_balances")
        return self


class _SignedDomainEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Annotated[StrictInt, Field(ge=2, le=2)]
    signature_profile: str
    event_encoding: str
    event_bytes: str
    signature_key_id: str
    signature: str


class _ModeEventPlane(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    trading_mode: TradingMode


class _DomainEventDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Annotated[StrictInt, Field(ge=2, le=2)]
    event_id: UUID
    tenant_id: SafeId
    event_plane: _ModeEventPlane
    bounded_context: str
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: StrictInt = Field(ge=1)
    event_type: str
    payload: dict[str, Any]
    correlation_id: str
    actor_assertion_jti: str | None
    occurred_at: str


@dataclass(frozen=True, slots=True)
class CrucibleDomainEventVerifier:
    key_id: str
    public_key: Ed25519PublicKey

    @classmethod
    def from_file(cls, path: str | Path, *, key_id: str) -> CrucibleDomainEventVerifier:
        if not key_id.strip():
            raise ValueError("Crucible domain-event key id is required")
        encoded = Path(path).expanduser().read_text(encoding="utf-8").strip()
        try:
            raw = bytes.fromhex(encoded) if len(encoded) == 64 else _decode_base64url(encoded)
            public_key = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Crucible domain-event public key must encode 32 Ed25519 bytes"
            ) from exc
        return cls(key_id=key_id, public_key=public_key)

    def verify(self, *, subject: str, data: bytes) -> _DomainEventDocument:
        envelope = _SignedDomainEventEnvelope.model_validate_json(data)
        if envelope.signature_profile != DOMAIN_EVENT_SIGNATURE_PROFILE:
            raise ValueError("unsupported Crucible domain-event signature profile")
        if envelope.event_encoding != DOMAIN_EVENT_ENCODING:
            raise ValueError("unsupported Crucible domain-event encoding")
        if envelope.signature_key_id != self.key_id:
            raise ValueError("Crucible domain-event signing key id does not match authority")
        event_bytes = _decode_base64url(envelope.event_bytes)
        signature = _decode_base64url(envelope.signature)
        if len(signature) != 64:
            raise ValueError("Crucible domain-event signature must be 64 bytes")
        subject_bytes = subject.encode("utf-8")
        framed = b"".join(
            (
                DOMAIN_EVENT_SIGNATURE_CONTEXT,
                len(subject_bytes).to_bytes(4, "big"),
                subject_bytes,
                len(event_bytes).to_bytes(8, "big"),
                event_bytes,
            )
        )
        try:
            self.public_key.verify(signature, framed)
        except InvalidSignature as exc:
            raise ValueError("Crucible domain-event signature verification failed") from exc
        return _DomainEventDocument.model_validate_json(event_bytes)


@dataclass(frozen=True, slots=True)
class DeploymentMessage:
    subject: str
    event_id: UUID
    occurred_at: str
    spec: DeploymentSpec

    @classmethod
    def parse(
        cls,
        data: bytes,
        *,
        subject: str,
        expected_tenant_id: str,
        expected_runner_id: str,
        verifier: CrucibleDomainEventVerifier,
    ) -> DeploymentMessage:
        event = verifier.verify(subject=subject, data=data)
        if event.tenant_id != expected_tenant_id:
            raise ValueError("DeploymentSpec tenant does not match runner authority")
        if event.event_plane.kind != "mode":
            raise ValueError("DeploymentSpec command must come from a mode event plane")
        if event.bounded_context != "deployment" or event.aggregate_type != "deployment_instance":
            raise ValueError("domain event is not a DeploymentInstance command")

        event_type = event.event_type.split(".")
        accepted_types = {
            "DeploymentSpecReadyForRunner",
            "DeploymentInstanceDesiredStateChanged",
        }
        if len(event_type) != 3 or event_type[0] not in accepted_types:
            raise ValueError("domain event is not a runner DeploymentSpec command")
        runner_id = str(UUID(event_type[1]))
        instance_id = UUID(event_type[2])
        if runner_id != str(UUID(expected_runner_id)) or event.aggregate_id != instance_id:
            raise ValueError("DeploymentSpec subject is not bound to this runner and instance")

        expected_subject = (
            f"crucible_rust.domain.{event.tenant_id}.{event.event_plane.trading_mode.value}."
            f"deployment.{event.event_type}"
        )
        if subject != expected_subject:
            raise ValueError("DeploymentSpec subject differs from its signed document")

        payload = event.payload
        if payload.get("schema_version") != 1:
            raise ValueError("DeploymentSpec command payload schema_version must be 1")
        if payload.get("tenant_id") != event.tenant_id:
            raise ValueError("DeploymentSpec payload tenant differs from signed event")
        if payload.get("mode") != event.event_plane.trading_mode.value:
            raise ValueError("DeploymentSpec payload mode differs from signed event plane")
        canonical = payload.get("deployment_spec")
        if not isinstance(canonical, dict):
            raise ValueError("DeploymentSpec command lacks canonical deployment_spec")
        if str(payload.get("runner_id")) != runner_id:
            raise ValueError("DeploymentSpec payload runner differs from signed subject")
        if UUID(str(payload.get("deployment_instance_id"))) != instance_id:
            raise ValueError("DeploymentSpec payload instance differs from signed subject")
        spec_id = UUID(str(payload.get("deployment_spec_id")))
        digest = str(payload.get("deployment_spec_digest") or "")
        if UUID(str(canonical.get("deployment_spec_id"))) != spec_id:
            raise ValueError("canonical DeploymentSpec id differs from command provenance")
        if canonical.get("tenant_id") != event.tenant_id:
            raise ValueError("canonical DeploymentSpec tenant differs from command authority")
        if canonical.get("trading_mode") != event.event_plane.trading_mode.value:
            raise ValueError("canonical DeploymentSpec mode differs from command event plane")
        if str(canonical.get("target_runner_id")) != runner_id:
            raise ValueError("canonical DeploymentSpec target runner differs from command")
        if canonical.get("schema_version") != 1:
            raise ValueError("canonical DeploymentSpec schema_version must be 1")
        canonical_digest = canonical_deployment_spec_digest(canonical)
        if not hmac.compare_digest(canonical_digest, digest):
            raise ValueError("canonical DeploymentSpec digest differs from signed provenance")
        generation = payload.get("generation")
        lifecycle_state = payload.get("lifecycle_state")
        if type(generation) is not int or generation < 1:
            raise ValueError("DeploymentSpec command requires a positive generation")
        if lifecycle_state not in {state.value for state in LifecycleState}:
            raise ValueError("DeploymentSpec command requires an explicit lifecycle_state")

        spec = _runtime_spec(
            canonical=canonical,
            deployment_instance_id=instance_id,
            deployment_spec_id=spec_id,
            deployment_spec_digest=digest,
            generation=generation,
            lifecycle_state=lifecycle_state,
        )
        return cls(
            subject=subject, event_id=event.event_id, occurred_at=event.occurred_at, spec=spec
        )


def _runtime_spec(
    *,
    canonical: dict[str, Any],
    deployment_instance_id: UUID,
    deployment_spec_id: UUID,
    deployment_spec_digest: str,
    generation: int,
    lifecycle_state: str,
) -> DeploymentSpec:
    parameters = canonical.get("parameters")
    code_provenance = canonical.get("code_provenance")
    credential_scope = canonical.get("credential_scope")
    if not isinstance(parameters, dict) or not isinstance(code_provenance, dict):
        raise ValueError("canonical DeploymentSpec runtime maps are invalid")
    if not isinstance(credential_scope, dict):
        raise ValueError("canonical DeploymentSpec credential scope is invalid")
    runtime = parameters.get("runner_runtime", parameters)
    if not isinstance(runtime, dict):
        raise ValueError("parameters.runner_runtime must be an object")
    venue_policy = canonical.get("venue_source_policy") or []
    connector = runtime.get("connector")
    if not connector and venue_policy and isinstance(venue_policy[0], dict):
        connector = venue_policy[0].get("venue")
    strategy_path = code_provenance.get("strategy_path") or code_provenance.get("artifact_path")
    risk_config = dict(runtime.get("risk_config") or {})
    risk_config.update(
        {
            "policy_id": canonical.get("risk_policy_id"),
            "policy_version": canonical.get("risk_policy_version"),
            "policy_digest": canonical.get("risk_policy_digest"),
        }
    )
    return DeploymentSpec.model_validate(
        {
            "spec_id": deployment_spec_id,
            "deployment_instance_id": deployment_instance_id,
            "deployment_spec_digest": deployment_spec_digest,
            "strategy_id": canonical.get("strategy_id"),
            "generation": generation,
            "trading_mode": canonical.get("trading_mode"),
            "lifecycle_state": lifecycle_state,
            "strategy_path": strategy_path,
            "provenance_ref": {"credential_id": str(credential_scope.get("scope_id") or "")},
            "connector": connector,
            "pairs": runtime.get("pairs"),
            "leverage": runtime.get("leverage", 1),
            "strategy_config": runtime.get("strategy_config", parameters),
            "strategy_registry_name": code_provenance.get("strategy_registry_name"),
            "code_hash": canonical.get("strategy_artifact_digest"),
            "log_level": runtime.get("log_level", "INFO"),
            "sandbox": runtime.get("sandbox"),
            "risk_config": risk_config,
            "nautilus_config": runtime.get("nautilus_config", {}),
            "promotion_id": canonical.get("promotion_id"),
            "promotion_evidence_digest": canonical.get("promotion_evidence_digest"),
        }
    )


def _decode_base64url(value: str) -> bytes:
    if not value or any(character.isspace() for character in value):
        raise ValueError("base64url value is empty or contains whitespace")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url value") from exc


def canonical_deployment_spec_digest(canonical: dict[str, Any]) -> str:
    """Match Crucible `sha256-canonical-json-v1` over the canonical spec only.

    The digest field and command envelope are intentionally excluded. Exact
    field-set validation prevents an additive producer change from silently
    changing the cross-language hash contract.
    """
    fields = frozenset(canonical)
    if fields != _CANONICAL_DEPLOYMENT_SPEC_FIELDS:
        missing = sorted(_CANONICAL_DEPLOYMENT_SPEC_FIELDS - fields)
        extra = sorted(fields - _CANONICAL_DEPLOYMENT_SPEC_FIELDS)
        raise ValueError(
            f"canonical DeploymentSpec field set differs: missing={missing}, extra={extra}"
        )
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_strategy_code_hash(strategy_dir: str | Path) -> str:
    path = Path(strategy_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"strategy directory not found: {path}")
    return compute_strategy_dir_hash(path)
