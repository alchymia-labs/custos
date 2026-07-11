"""Strict DeploymentSpec consumer contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

DEPLOYMENT_SPEC_SCHEMA_ID = (
    "https://custos.the-alephain-guild/gateway-contract/v1/deployment_spec.schema.json"
)
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


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
