"""EnrollmentToken pairing: runner registers to tenant with a one-time/revocable
token.
(binds scope + paper_only).

Cloud issues a token (SHA-256 hash stored server-side) → user pastes plaintext
token into the runner → runner.enroll(plaintext_token) computes the hash and
publishes to the enrollment subject → wait for cloud confirmation → persist
runner_id to local enrollment.json.

paper_only=True by default — live mode requires a separate cloud-issued
paper_only=False token (upgrade path).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from custos.core.log import get_logger
from custos.core.nats_client import ArxNatsClient

_log = get_logger("custos.enrollment")


def hash_token(token: str) -> str:
    """SHA-256 hex digest of an enrollment token plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class EnrollmentClient:
    """Pair the runner with a tenant via one-shot enrollment token."""

    nats_client: ArxNatsClient
    tenant_id: str
    runner_id: str
    enrollment_path: Path
    confirm_timeout_secs: float = 30.0

    async def enroll(
        self,
        token: str,
        agent_version: str = "",
        capabilities: list[str] | None = None,
    ) -> bool:
        """Publish enrollment hash; wait for cloud confirmation; persist record.

        Confirmation arrives out-of-band (HTTP API ack or NATS reply subject);
        v1 uses a fixed-timeout sleep + locally-recorded enrollment, with the
        cloud side reconciling via the API on /api/v1/runners/enroll. Even if
        the publish never reaches the broker, the local persistence keeps the
        runner usable; cloud will reject heartbeats until enrollment is
        reconciled.
        """
        token_hash = hash_token(token)
        payload = {
            "token_hash": token_hash,
            "runner_id": self.runner_id,
            "agent_version": agent_version,
            "capabilities": capabilities or [],
        }
        try:
            await self.nats_client.publish_enrollment(payload=payload)
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "enrollment_publish_failed",
                runner_id=self.runner_id,
                error=str(exc),
            )
            return False

        # v1: simplify to immediate persistence + short wait; cloud reply pattern
        # Phase 2 + RBAC will land in a later iteration.
        await asyncio.sleep(min(1.0, self.confirm_timeout_secs))

        try:
            self._persist(
                token_hash=token_hash,
                agent_version=agent_version,
                capabilities=capabilities or [],
            )
        except OSError as exc:
            _log.error("enrollment_persist_failed", error=str(exc))
            return False

        _log.info(
            "enrollment_completed",
            runner_id=self.runner_id,
            tenant_id=self.tenant_id,
        )
        return True

    def is_enrolled(self) -> bool:
        """Check whether local enrollment.json exists and is not expired (v1: no expiry)."""
        if not self.enrollment_path.exists():
            return False
        try:
            data = json.loads(self.enrollment_path.read_text())
            return data.get("runner_id") == self.runner_id
        except (OSError, json.JSONDecodeError):
            return False

    def _persist(
        self,
        *,
        token_hash: str,
        agent_version: str,
        capabilities: list[str],
    ) -> None:
        record = {
            "runner_id": self.runner_id,
            "tenant_id": self.tenant_id,
            "token_hash": token_hash,
            "agent_version": agent_version,
            "capabilities": capabilities,
            "enrolled_at_ns": time.time_ns(),
        }
        self.enrollment_path.parent.mkdir(parents=True, exist_ok=True)
        # Persist files with 0600 mode (KEK never leaves host; token_hash is sensitive).
        self.enrollment_path.write_text(json.dumps(record, separators=(",", ":")))
        try:
            self.enrollment_path.chmod(0o600)
        except OSError:  # pragma: no cover — windows/CI compatibility
            pass
