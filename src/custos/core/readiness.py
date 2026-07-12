"""Atomic file-based runner readiness state."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

_FILE_MODE = 0o600
_DIR_MODE = 0o700


@dataclass(frozen=True)
class ReadinessFile:
    path: Path
    tenant_id: str
    runner_id: str

    def mark_ready(
        self,
        *,
        strategy_id: str | None,
        nats_connected: bool,
        deployment_subscription: bool,
    ) -> None:
        state = {
            "ready": True,
            "tenant_id": self.tenant_id,
            "runner_id": self.runner_id,
            "strategy_id": strategy_id,
            "nats_connected": nats_connected,
            "deployment_subscription": deployment_subscription,
        }
        self._atomic_write(json.dumps(state, separators=(",", ":")).encode("utf-8"))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def _atomic_write(self, payload: bytes) -> None:
        parent_created = not self.path.parent.exists()
        self.path.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        if parent_created:
            os.chmod(self.path.parent, _DIR_MODE)
        temp_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temp_path, self.path)
            os.chmod(self.path, _FILE_MODE)
        finally:
            temp_path.unlink(missing_ok=True)


def is_ready_file(path: Path) -> bool:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(state, dict):
        return False
    if not isinstance(state.get("tenant_id"), str) or not state["tenant_id"]:
        return False
    if not isinstance(state.get("runner_id"), str) or not state["runner_id"]:
        return False
    if state.get("ready") is not True or state.get("nats_connected") is not True:
        return False
    strategy_id = state.get("strategy_id")
    if strategy_id is not None and (not isinstance(strategy_id, str) or not strategy_id):
        return False
    subscription = state.get("deployment_subscription")
    if strategy_id is not None and subscription is not True:
        return False
    return isinstance(subscription, bool)
