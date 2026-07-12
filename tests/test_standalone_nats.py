from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nats.js.api import StorageType, StreamConfig
from nats.js.errors import NotFoundError

from custos.cli.subcommands import main
from custos.core.standalone_nats import (
    bootstrap_standalone_nats,
    ensure_standalone_streams,
    standalone_stream_configs,
)


class _FakeJetStream:
    def __init__(self) -> None:
        self.streams: dict[str, StreamConfig] = {}
        self.added: list[str] = []
        self.updated: list[str] = []
        self.deleted: list[str] = []

    async def stream_info(self, name: str):
        try:
            config = self.streams[name]
        except KeyError as exc:
            raise NotFoundError from exc
        return SimpleNamespace(config=deepcopy(config))

    async def add_stream(self, config: StreamConfig):
        assert config.name is not None
        self.streams[config.name] = deepcopy(config)
        self.added.append(config.name)
        return SimpleNamespace(config=deepcopy(config))

    async def update_stream(self, config: StreamConfig):
        assert config.name is not None
        self.streams[config.name] = deepcopy(config)
        self.updated.append(config.name)
        return SimpleNamespace(config=deepcopy(config))

    async def delete_stream(self, name: str) -> None:
        self.deleted.append(name)
        self.streams.pop(name, None)


def _configs_by_suffix(tenant_id: str = "acme") -> dict[str, StreamConfig]:
    return {
        config.name.rsplit("_", 1)[-1]: config
        for config in standalone_stream_configs(tenant_id)
        if config.name is not None
    }


async def test_bootstrap_creates_desired_state_stream() -> None:
    jetstream = _FakeJetStream()

    await ensure_standalone_streams(jetstream, "acme")

    config = _configs_by_suffix()["DEPLOYMENT"]
    assert jetstream.streams[config.name].subjects == ["arx.acme.deployment_spec.>"]
    assert jetstream.streams[config.name].storage is StorageType.FILE
    assert jetstream.streams[config.name].max_msgs_per_subject == 1


async def test_bootstrap_creates_observed_state_stream() -> None:
    jetstream = _FakeJetStream()

    await ensure_standalone_streams(jetstream, "acme")

    config = _configs_by_suffix()["OBSERVED"]
    assert jetstream.streams[config.name].subjects == [
        "arx.acme.deployment_status.>",
        "arx.acme.heartbeat.>",
        "arx.acme.telemetry.>",
        "arx.acme.snapshot.>",
        "arx.acme.pre_trade_reject.>",
        "arx.acme.enrollment.>",
    ]
    assert jetstream.streams[config.name].storage is StorageType.FILE


async def test_bootstrap_is_idempotent() -> None:
    jetstream = _FakeJetStream()
    await ensure_standalone_streams(jetstream, "acme")
    jetstream.added.clear()

    await ensure_standalone_streams(jetstream, "acme")

    assert jetstream.added == []
    assert jetstream.updated == []


async def test_bootstrap_updates_owned_stream_drift() -> None:
    jetstream = _FakeJetStream()
    await ensure_standalone_streams(jetstream, "acme")
    deployment = _configs_by_suffix()["DEPLOYMENT"]
    jetstream.streams[deployment.name].subjects = ["arx.acme.wrong.>"]

    await ensure_standalone_streams(jetstream, "acme")

    assert jetstream.updated == [deployment.name]
    assert jetstream.streams[deployment.name].subjects == ["arx.acme.deployment_spec.>"]


async def test_bootstrap_never_deletes_unknown_stream() -> None:
    jetstream = _FakeJetStream()
    jetstream.streams["USER_EVENTS"] = StreamConfig(
        name="USER_EVENTS",
        subjects=["user.>"],
        storage=StorageType.FILE,
    )

    await ensure_standalone_streams(jetstream, "acme")

    assert "USER_EVENTS" in jetstream.streams
    assert jetstream.deleted == []


async def test_bootstrap_refuses_to_take_over_unowned_name_collision() -> None:
    jetstream = _FakeJetStream()
    deployment = _configs_by_suffix()["DEPLOYMENT"]
    jetstream.streams[deployment.name] = StreamConfig(
        name=deployment.name,
        subjects=["user.>"],
        storage=StorageType.FILE,
    )

    with pytest.raises(RuntimeError, match="not owned"):
        await ensure_standalone_streams(jetstream, "acme")

    assert jetstream.updated == []


@pytest.mark.parametrize("tenant_id", ["", "acme.prod", "*", "../acme"])
def test_bootstrap_rejects_invalid_tenant(tenant_id: str) -> None:
    with pytest.raises(ValueError):
        standalone_stream_configs(tenant_id)


async def test_bootstrap_times_out_when_nats_unreachable() -> None:
    async def connect(_url: str):
        raise ConnectionError("unreachable")

    with pytest.raises(TimeoutError, match="within"):
        await bootstrap_standalone_nats(
            nats_url="nats://unreachable:4222",
            tenant_id="acme",
            timeout_secs=0.01,
            connect_factory=connect,
        )


def test_cli_bootstrap_wires_explicit_standalone_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap = AsyncMock()
    monkeypatch.setattr("custos.cli.subcommands.nats.bootstrap_standalone_nats", bootstrap)

    exit_code = main(
        [
            "nats",
            "bootstrap",
            "--profile",
            "standalone",
            "--nats-url",
            "nats://nats:4222",
            "--tenant-id",
            "acme",
            "--timeout-secs",
            "12",
        ]
    )

    assert exit_code == 0
    bootstrap.assert_awaited_once_with(
        nats_url="nats://nats:4222",
        tenant_id="acme",
        timeout_secs=12.0,
    )


def test_cli_bootstrap_rejects_unknown_profile() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "nats",
                "bootstrap",
                "--profile",
                "managed",
                "--tenant-id",
                "acme",
            ]
        )
