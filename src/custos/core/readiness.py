"""Atomic readiness state tied to an active machine credential authority."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_FILE_MODE = 0o600
_DIR_MODE = 0o700


@dataclass(frozen=True, slots=True)
class ReadinessFile:
    path: Path
    tenant_id: str
    runner_id: str
    credential_id: str
    credential_version: int
    credential_valid_until: str
    machine_key_id: str

    def mark_ready(
        self,
        *,
        strategy_id: str | None,
        nats_connected: bool,
        deployment_subscription: bool,
    ) -> None:
        if _expired(self.credential_valid_until):
            self.clear()
            raise RuntimeError("refusing readiness for an expired machine credential")
        state = {
            "ready": True,
            "tenant_id": self.tenant_id,
            "runner_id": self.runner_id,
            "credential_id": self.credential_id,
            "credential_version": self.credential_version,
            "credential_valid_until": self.credential_valid_until,
            "machine_key_id": self.machine_key_id,
            "credential_state": "active",
            "credential_binding_valid": True,
            "strategy_id": strategy_id,
            "nats_connected": nats_connected,
            "deployment_subscription": deployment_subscription,
        }
        self._atomic_write(json.dumps(state, separators=(",", ":")).encode("utf-8"))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def _atomic_write(self, payload: bytes) -> None:
        self.path.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        os.chmod(self.path.parent, _DIR_MODE)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, self.path)
            os.chmod(self.path, _FILE_MODE)
        finally:
            temporary.unlink(missing_ok=True)


def is_ready_file(path: Path) -> bool:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(state, dict) or set(state) != set(_FIELDS):
        return False
    if state.get("ready") is not True or state.get("nats_connected") is not True:
        return False
    if state.get("credential_state") != "active":
        return False
    if state.get("credential_binding_valid") is not True:
        return False
    if not isinstance(state.get("credential_version"), int) or state["credential_version"] < 1:
        return False
    for field in ("tenant_id", "runner_id", "credential_id", "machine_key_id"):
        if not isinstance(state.get(field), str) or not state[field]:
            return False
    if not isinstance(state.get("credential_valid_until"), str) or _expired(
        state["credential_valid_until"]
    ):
        return False
    strategy_id = state.get("strategy_id")
    if strategy_id is not None and (not isinstance(strategy_id, str) or not strategy_id):
        return False
    subscription = state.get("deployment_subscription")
    if strategy_id is not None and subscription is not True:
        return False
    return isinstance(subscription, bool)


_FIELDS = (
    "ready",
    "tenant_id",
    "runner_id",
    "credential_id",
    "credential_version",
    "credential_valid_until",
    "machine_key_id",
    "credential_state",
    "credential_binding_valid",
    "strategy_id",
    "nats_connected",
    "deployment_subscription",
)


def _expired(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return parsed.tzinfo is None or parsed.astimezone(UTC) <= datetime.now(UTC)
