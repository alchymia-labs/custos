"""EnrollmentClient — hash consistency + publish + persist + replay safety。

教训 #17 失败模式: enrollment 必须处理 publish 失败 + 持久化失败 + token
重放 (上游云端 consume_token 原子保证, 这里测 runner 侧 enroll 不会做出
误判)。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from arx_runner.enrollment import EnrollmentClient, hash_token


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
    # 长度 = 64 hex chars
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
    """关键 安全契约: 只发 hash 给云端, 不发明文。"""
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
    # 明文不出现在 NATS payload (CLAUDE.md 红线)
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
    # 失败时本地不写
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
    """教训 #17 replay: 同 token 重新 enroll → 本地记录会被覆盖。云端 RBAC
    consume_token 原子保证已消费 token 拒绝 (Plan 06 Task 6); runner 侧
    本地 enroll 不验证 token 唯一性 — 防御靠云端。"""
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
    await client.enroll("token-1")  # 重放
    # NATS 上发了 2 次 → 云端可见重放, 由云端拒
    assert len(nats.publish_payloads) == 2
