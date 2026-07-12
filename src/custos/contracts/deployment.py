"""Strict DeploymentSpec consumer contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self
from uuid import UUID

import uuid6
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from custos.core.nats_client import NatsEnvelope, _now_rfc3339_nanos, build_subject
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

DEPLOYMENT_SPEC_SCHEMA_ID = (
    "https://custos.the-alephain-guild/gateway-contract/v1/deployment_spec.schema.json"
)
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
SubjectId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
Rfc3339Nanos = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z$",
    ),
]


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

    credential_id: str = Field(min_length=1)


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_balances: list[str] = Field(min_length=1)


class DeploymentSpec(BaseModel):
    """Validated desired state accepted by the Custos runtime."""

    model_config = ConfigDict(
        extra="forbid",
        title="DeploymentSpecPayload v1",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": DEPLOYMENT_SPEC_SCHEMA_ID,
            "allOf": [
                {
                    "if": {
                        "properties": {"trading_mode": {"const": TradingMode.LIVE.value}},
                        "required": ["trading_mode"],
                    },
                    "then": {
                        "properties": {
                            "code_hash": {
                                "type": "string",
                                "pattern": r"^[a-f0-9]{64}$",
                            }
                        },
                        "required": ["code_hash"],
                    },
                },
                {
                    "if": {
                        "properties": {"trading_mode": {"const": TradingMode.SANDBOX.value}},
                        "required": ["trading_mode"],
                    },
                    "then": {
                        "properties": {
                            "sandbox": {
                                "type": "object",
                                "properties": {
                                    "starting_balances": {
                                        "type": "array",
                                        "minItems": 1,
                                    }
                                },
                                "required": ["starting_balances"],
                            }
                        },
                        "required": ["sandbox"],
                    },
                },
            ],
        },
    )

    spec_id: str = Field(min_length=1)
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
    code_hash: Sha256Hex | None = None
    log_level: str = "INFO"
    sandbox: SandboxConfig | None = None
    approved_by: list[str] = Field(default_factory=list)
    risk_config: dict[str, Any] = Field(default_factory=dict)
    nautilus_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Self:
        if self.trading_mode is TradingMode.LIVE and self.code_hash is None:
            raise ValueError("live deployment requires a 64-character lowercase code_hash")
        if self.trading_mode is TradingMode.SANDBOX and self.sandbox is None:
            raise ValueError("sandbox deployment requires sandbox.starting_balances")
        return self


class _DeploymentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: SubjectId
    spec: DeploymentSpec


class _DeploymentWireEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_version: Annotated[StrictInt, Field(ge=1, le=1)]
    event_id: UUID
    tenant_id: SubjectId
    occurred_at: Rfc3339Nanos
    payload_schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    payload: _DeploymentPayload

    @field_validator("event_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("deployment event_id must be UUIDv7")
        return value


@dataclass(frozen=True)
class DeploymentMessage:
    """Canonical DeploymentSpec subject plus its validated v1 envelope."""

    subject: str
    envelope: NatsEnvelope
    spec: DeploymentSpec

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        strategy_id: str,
        spec: DeploymentSpec,
    ) -> DeploymentMessage:
        payload = _DeploymentPayload.model_validate(
            {
                "strategy_id": strategy_id,
                "spec": spec,
            }
        )
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload.model_dump(mode="json"),
        )
        wire = _DeploymentWireEnvelope.model_validate(envelope.to_dict())
        return cls(
            subject=build_subject(wire.tenant_id, "deployment_spec", payload.strategy_id),
            envelope=envelope,
            spec=payload.spec,
        )

    @classmethod
    def parse(
        cls,
        data: bytes,
        *,
        expected_tenant_id: str,
    ) -> DeploymentMessage:
        wire = _DeploymentWireEnvelope.model_validate_json(data)
        if wire.tenant_id != expected_tenant_id:
            raise ValueError(
                f"deployment message tenant {wire.tenant_id!r} does not match "
                f"expected tenant {expected_tenant_id!r}"
            )
        payload = wire.payload
        envelope = NatsEnvelope(
            event_id=str(wire.event_id),
            tenant_id=wire.tenant_id,
            occurred_at=wire.occurred_at,
            payload=payload.model_dump(mode="json"),
            envelope_version=wire.envelope_version,
            payload_schema_version=wire.payload_schema_version,
        )
        return cls(
            subject=build_subject(wire.tenant_id, "deployment_spec", payload.strategy_id),
            envelope=envelope,
            spec=payload.spec,
        )

    def to_bytes(self) -> bytes:
        return self.envelope.to_bytes()


def compute_strategy_code_hash(strategy_dir: str | Path) -> str:
    """Return the canonical Custos strategy-directory SHA-256."""

    path = Path(strategy_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"strategy directory not found: {path}")
    return compute_strategy_dir_hash(path)
