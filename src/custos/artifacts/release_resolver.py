"""Authenticated Crucible StrategyRelease material boundary for Custos V1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from custos.artifacts.runtime import StrategyReleaseArtifactAuthorityV1
from custos.core.runner_command_intake import VerifiedRunnerCommand


class StrategyReleaseResolutionError(RuntimeError):
    """Base error for the authenticated owner-material lookup."""


class StrategyReleaseResolutionUnavailable(StrategyReleaseResolutionError):
    """The owner endpoint or authenticated transport is temporarily unavailable."""


class StrategyReleaseResolutionRejected(StrategyReleaseResolutionError):
    """Crucible rejected the requested release or returned conflicting authority."""


@dataclass(frozen=True, slots=True)
class ResolvedStrategyReleaseArtifactV1:
    release_authority: StrategyReleaseArtifactAuthorityV1
    release_statement_bytes: bytes
    detached_bundle_path: Path
    member_paths: Mapping[str, Path]
    verified_at: datetime

    def __post_init__(self) -> None:
        if not self.release_statement_bytes:
            raise ValueError("resolved StrategyRelease statement bytes are required")
        if self.verified_at.tzinfo is None:
            raise ValueError("StrategyRelease verification time must be timezone-aware")
        paths = (self.detached_bundle_path, *self.member_paths.values())
        if not self.member_paths or any(not path.is_absolute() for path in paths):
            raise ValueError("resolved StrategyRelease member paths must be absolute")


class StrategyReleaseArtifactResolverV1(Protocol):
    async def resolve(
        self,
        verified: VerifiedRunnerCommand,
    ) -> ResolvedStrategyReleaseArtifactV1: ...


class UnavailableStrategyReleaseArtifactResolverV1:
    """Production-safe composition default until Crucible publishes its receipt."""

    async def resolve(
        self,
        verified: VerifiedRunnerCommand,
    ) -> ResolvedStrategyReleaseArtifactV1:
        raise StrategyReleaseResolutionUnavailable(
            "authenticated Crucible StrategyRelease resolver is not composed"
        )


__all__ = [
    "ResolvedStrategyReleaseArtifactV1",
    "StrategyReleaseArtifactResolverV1",
    "StrategyReleaseResolutionError",
    "StrategyReleaseResolutionRejected",
    "StrategyReleaseResolutionUnavailable",
    "UnavailableStrategyReleaseArtifactResolverV1",
]
