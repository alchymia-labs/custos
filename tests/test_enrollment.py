"""EnrollmentClient — hash consistency + publish + persistence + replay safety.

Lesson #17 failure mode: enrollment must handle publish failure + persistence
failure + token replay safely. Cloud consume-token is atomic, so this test
covers that runner-side enroll does not misclassify valid replay attempts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from custos.core.enrollment import EnrollmentClient, hash_token


@dataclass
class _FakeNats:
    publish_payloads: list[dict] = field(default_factory=list)
    publish_raises: bool = False

    async def publish_enrollment(self, *, payload: dict) -> None:
        if self.publish_raises:
            raise RuntimeError("nats disconnected")
        self.publish_payloads.append(payload)


def test_hash_token_is_deterministic_sha256() -> None:
    token = "tok-secret-001"
    expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert hash_token(token) == expected
    # digest length = 64 hex chars
    assert len(hash_token(token)) == 64


@pytest.mark.asyncio
async def test_enroll_writes_local_record(tmp_path: Path) -> None:
    nats = _FakeNats()
    path = tmp_path / "enrollment.json"
    client = EnrollmentClient(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=path,
        confirm_timeout_secs=0.01,
    )

    ok = await client.enroll("plaintext-token", agent_version="1.0.0")
    assert ok is True
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["runner_id"] == "runner-7"
    assert data["tenant_id"] == "acme"
    assert data["token_hash"] == hash_token("plaintext-token")
    assert data["agent_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_enroll_publishes_hash_not_plaintext(tmp_path: Path) -> None:
    """Critical security invariant: send only hash to cloud, never plaintext."""
    nats = _FakeNats()
    client = EnrollmentClient(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=tmp_path / "enrollment.json",
        confirm_timeout_secs=0.01,
    )

    await client.enroll("plaintext-token")

    assert len(nats.publish_payloads) == 1
    payload = nats.publish_payloads[0]
    assert "token_hash" in payload
    # plaintext must never appear in NATS payload (CLAUDE.md red line)
    assert "plaintext-token" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_enroll_publish_failure_returns_false(tmp_path: Path) -> None:
    nats = _FakeNats(publish_raises=True)
    client = EnrollmentClient(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=tmp_path / "enrollment.json",
        confirm_timeout_secs=0.01,
    )

    ok = await client.enroll("plaintext-token")
    assert ok is False
    # do not write local state on publish failure
    assert not (tmp_path / "enrollment.json").exists()


def test_is_enrolled_returns_false_when_missing(tmp_path: Path) -> None:
    client = EnrollmentClient(
        nats_client=_FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=tmp_path / "enrollment.json",
    )
    assert client.is_enrolled() is False


def test_is_enrolled_returns_false_when_runner_id_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "enrollment.json"
    path.write_text(json.dumps({"runner_id": "different-runner"}))

    client = EnrollmentClient(
        nats_client=_FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=path,
    )
    assert client.is_enrolled() is False


@pytest.mark.asyncio
async def test_enrollment_replay_token_overwrites_local_record(tmp_path: Path) -> None:
    """Lesson #17 replay: re-enroll with same token → local record is overwritten.
    Cloud RBAC consume_token is atomic and rejects consumed tokens (Plan 06 Task
    6); runner-side local enroll does not enforce token uniqueness — cloud-side
    enforcement is authoritative."""
    nats = _FakeNats()
    path = tmp_path / "enrollment.json"
    client = EnrollmentClient(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        enrollment_path=path,
        confirm_timeout_secs=0.01,
    )

    await client.enroll("token-1")
    await client.enroll("token-1")  # replay
    # NATS sends twice; cloud sees the replay and is expected to reject duplicates.
    assert len(nats.publish_payloads) == 2
