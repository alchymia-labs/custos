from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from custos.artifacts.release_resolver import (
    StrategyReleaseResolutionUnavailable,
    UnavailableStrategyReleaseArtifactResolverV1,
)
from custos.cli._daemon import _build_runner_safety_boundary_factory
from custos.core.fallback_breaker import FallbackBreakerConfig

POLICY_ID = UUID("22222222-2222-4222-8222-222222222222")
DEPLOYMENT_INSTANCE_ID = UUID("11111111-1111-4111-8111-111111111111")


class _Resolver:
    def __init__(self, *, policy_id=POLICY_ID, owner_policy: bool = True) -> None:
        self.policy_id = policy_id
        self.owner_policy = owner_policy
        self.modes: list[str] = []

    async def resolve(self, trading_mode: str):
        self.modes.append(trading_mode)
        return SimpleNamespace(
            policy_id=self.policy_id,
            owner_policy=self.owner_policy,
            breaker=FallbackBreakerConfig(
                max_notional=Decimal("100"),
                max_drawdown_pct=Decimal("10"),
            ),
        )


@pytest.mark.asyncio
async def test_boundary_factory_uses_durable_owner_policy_identity() -> None:
    store = object()
    resolver = _Resolver()
    factory = _build_runner_safety_boundary_factory(
        state_store=store,
        safety_policy_resolver=resolver,
    )

    boundary = await factory(
        {
            "deployment_instance_id": str(DEPLOYMENT_INSTANCE_ID),
            "trading_mode": "testnet",
        }
    )

    assert resolver.modes == ["testnet"]
    assert boundary._store is store
    assert boundary._deployment_instance_id == DEPLOYMENT_INSTANCE_ID
    assert boundary._policy_id == POLICY_ID
    assert boundary._fallback_breaker.config.max_notional == Decimal("100")


@pytest.mark.asyncio
async def test_boundary_factory_fails_closed_without_owner_policy() -> None:
    factory = _build_runner_safety_boundary_factory(
        state_store=object(),
        safety_policy_resolver=_Resolver(policy_id=None, owner_policy=False),
    )

    with pytest.raises(RuntimeError, match="verified owner policy"):
        await factory(
            {
                "deployment_instance_id": str(DEPLOYMENT_INSTANCE_ID),
                "trading_mode": "sandbox",
            }
        )


@pytest.mark.asyncio
async def test_uncomposed_strategy_release_authority_fails_closed() -> None:
    resolver = UnavailableStrategyReleaseArtifactResolverV1()

    with pytest.raises(StrategyReleaseResolutionUnavailable, match="not composed"):
        await resolver.resolve(object())
