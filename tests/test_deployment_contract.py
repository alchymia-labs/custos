from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from custos.contracts import DeploymentSpec, LifecycleState, TradingMode
from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.local_cap import LIVE_CAP_FLOOR_USD, LocalCapConfig, RunnerNotionalCap
from custos.engines.nautilus.host import NtTradingNodeHost

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/gateway-contract/v1/deployment_spec.schema.json"


def _sandbox_spec() -> dict:
    return {
        "spec_id": "supertrend-sandbox",
        "generation": 1,
        "trading_mode": "sandbox",
        "lifecycle_state": "running",
        "strategy_path": "/opt/strategies/supertrend/strategy.py",
        "provenance_ref": {"credential_id": "binance-sandbox"},
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
        "strategy_config": {"period": 10, "filters": {"adx": True}},
        "strategy_registry_name": "supertrend",
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }


def _live_spec() -> dict:
    spec = _sandbox_spec()
    spec.update(
        trading_mode="live",
        sandbox=None,
        code_hash="a" * 64,
        approved_by=["alice", "bob"],
    )
    return spec


def test_generation_starts_at_one() -> None:
    raw = _sandbox_spec()
    raw["generation"] = 0

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)


@pytest.mark.parametrize("value", ["paper", "live", "degraded", "RUNNING"])
def test_lifecycle_vocab_is_closed(value: str) -> None:
    raw = _sandbox_spec()
    raw["lifecycle_state"] = value

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)


@pytest.mark.parametrize("code_hash", [None, "", "not-a-sha256", "A" * 64])
def test_live_requires_code_hash(code_hash: str | None) -> None:
    raw = _live_spec()
    raw["code_hash"] = code_hash

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)


def test_sandbox_requires_starting_balances() -> None:
    raw = _sandbox_spec()
    raw["sandbox"] = None

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)


def test_unknown_top_level_field_is_rejected() -> None:
    raw = _sandbox_spec()
    raw["strategy_confg"] = {}

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)


def test_strategy_config_reaches_factory_unchanged() -> None:
    spec = DeploymentSpec.model_validate(_sandbox_spec())
    module_name = "_deployment_contract_strategy"
    module = ModuleType(module_name)
    received: list[dict] = []

    class Strategy:
        pass

    Strategy.__module__ = module_name

    def create_strategy(config: dict) -> object:
        received.append(config)
        return object()

    module.create_strategy = create_strategy
    sys.modules[module_name] = module
    try:
        NtTradingNodeHost()._instantiate_strategy(Strategy, spec.model_dump(mode="json"))
    finally:
        sys.modules.pop(module_name, None)

    assert received == [_sandbox_spec()["strategy_config"]]


def test_registry_name_is_preserved() -> None:
    spec = DeploymentSpec.model_validate(_sandbox_spec())

    assert spec.strategy_registry_name == "supertrend"


def test_risk_live_flag_uses_trading_mode_not_lifecycle() -> None:
    local_cap = RunnerNotionalCap(LocalCapConfig.from_spec({}, live=False))
    reconciler = DeploymentReconciler(
        nats_client=object(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-1",
        execution_engine=object(),  # type: ignore[arg-type]
        credential_vault=object(),  # type: ignore[arg-type]
        local_cap=local_cap,
    )
    spec = DeploymentSpec.model_validate(_live_spec())

    reconciler._refresh_risk_config(spec.model_dump(mode="json"))

    assert local_cap.config.max_notional_per_runner == LIVE_CAP_FLOOR_USD


def test_static_schema_is_generated_from_model() -> None:
    static_schema = json.loads(SCHEMA_PATH.read_text())

    assert static_schema == DeploymentSpec.model_json_schema()


@pytest.mark.parametrize(
    "raw",
    [
        {**_live_spec(), "code_hash": None},
        {**_sandbox_spec(), "sandbox": None},
    ],
)
def test_static_schema_enforces_mode_requirements(raw: dict) -> None:
    validator = Draft202012Validator(DeploymentSpec.model_json_schema())

    assert list(validator.iter_errors(raw))


def test_model_validation_does_not_mutate_input() -> None:
    raw = _sandbox_spec()
    before = deepcopy(raw)

    DeploymentSpec.model_validate(raw)

    assert raw == before
    assert DeploymentSpec.model_validate(raw).trading_mode is TradingMode.SANDBOX
    assert DeploymentSpec.model_validate(raw).lifecycle_state is LifecycleState.RUNNING
