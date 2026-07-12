"""Hermetic official-image acceptance for the standalone deployment wire."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import nats
import pytest

IMAGE = os.environ.get("CUSTOS_TEST_IMAGE", "custos-runner:test")
TENANT_ID = "acceptance"
RUNNER_ID = "runner-acceptance"
STRATEGY_ID = "strategy-acceptance"
SPEC_ID = "spec-acceptance"
KEY_ID = "credential-acceptance"


def _docker(
    *args: str,
    check: bool = True,
    input_text: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        input=input_text,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        pytest.fail(
            f"docker {' '.join(args)} failed with rc={proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
    return proc


def _require_runtime_image() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH")
    if _docker("info", check=False, timeout=10).returncode != 0:
        pytest.skip("Docker daemon is not reachable")
    if _docker("image", "inspect", IMAGE, check=False).returncode != 0:
        pytest.skip(f"image {IMAGE} not present; run `make docker-build` first")


async def _connect_to_nats(url: str, timeout: float = 15):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return await nats.connect(
                url,
                connect_timeout=0.25,
                max_reconnect_attempts=0,
            )
        except Exception as exc:  # noqa: BLE001 - readiness polling reports final error
            last_error = exc
            await asyncio.sleep(0.1)
    raise AssertionError(f"NATS at {url} did not become ready: {last_error}")


async def _wait_for_runner_health(container: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await asyncio.to_thread(
            _docker,
            "exec",
            container,
            "arx-runner",
            "health",
            check=False,
        )
        if last.returncode == 0:
            return
        state = _docker(
            "inspect",
            "--format",
            "{{.State.Running}}",
            container,
            check=False,
        )
        if state.stdout.strip() == "false":
            break
        await asyncio.sleep(0.1)
    logs = _docker("logs", container, check=False).stdout
    raise AssertionError(
        f"runner did not become healthy; last={getattr(last, 'stderr', '')!r}\nlogs={logs}"
    )


def _write_spec(path: Path, *, generation: int, lifecycle_state: str) -> None:
    path.write_text(
        json.dumps(
            {
                "spec_id": SPEC_ID,
                "generation": generation,
                "trading_mode": "sandbox",
                "lifecycle_state": lifecycle_state,
                "strategy_path": "/opt/strategies/acceptance/strategy.py",
                "provenance_ref": {"credential_id": KEY_ID},
                "connector": "binance_perpetual",
                "pairs": ["BTC-USDT"],
                "leverage": 1,
                "strategy_config": {"acceptance": True},
                "sandbox": {"starting_balances": ["10_000 USDT"]},
            }
        ),
        encoding="utf-8",
    )


def _publish_spec(network: str, spec_dir: Path, filename: str) -> None:
    _docker(
        "run",
        "--rm",
        "--network",
        network,
        "--volume",
        f"{spec_dir}:/specs:ro",
        IMAGE,
        "deployment",
        "publish",
        "--spec-file",
        f"/specs/{filename}",
        "--tenant-id",
        TENANT_ID,
        "--strategy-id",
        STRATEGY_ID,
        "--nats-url",
        "nats://nats:4222",
    )


async def _next_status(subscription, generation: int, timeout: float = 15) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        message = await subscription.next_msg(timeout=remaining)
        payload = json.loads(message.data)["payload"]
        if payload.get("observed_generation") == generation:
            return payload
    raise AssertionError(f"status for generation {generation} was not observed")


async def _next_status_with_logs(subscription, generation: int, runner: str) -> dict:
    try:
        return await _next_status(subscription, generation)
    except Exception as exc:
        logs = await asyncio.to_thread(_docker, "logs", runner, check=False)
        raise AssertionError(
            f"status for generation {generation} was not observed: {exc}\n"
            f"runner stdout={logs.stdout!r}\nrunner stderr={logs.stderr!r}"
        ) from exc


@pytest.mark.docker
@pytest.mark.integration
async def test_standalone_runtime_reconciles_running_stopped_running(tmp_path: Path) -> None:
    _require_runtime_image()
    suffix = uuid.uuid4().hex[:10]
    network = f"custos-acceptance-{suffix}"
    volume = f"custos-acceptance-state-{suffix}"
    nats_container = f"custos-acceptance-nats-{suffix}"
    runner_container = f"custos-acceptance-runner-{suffix}"
    connection = None

    try:
        _docker("network", "create", network)
        _docker("volume", "create", volume)
        _docker(
            "run",
            "--detach",
            "--name",
            nats_container,
            "--network",
            network,
            "--network-alias",
            "nats",
            "--publish",
            "127.0.0.1::4222",
            "nats:2.10-alpine",
            "-js",
        )
        _docker(
            "run",
            "--rm",
            "--network",
            network,
            IMAGE,
            "nats",
            "bootstrap",
            "--profile",
            "standalone",
            "--nats-url",
            "nats://nats:4222",
            "--tenant-id",
            TENANT_ID,
        )

        port_output = _docker("port", nats_container, "4222/tcp").stdout.strip().splitlines()[0]
        host_port = port_output.rsplit(":", 1)[1]
        connection = await _connect_to_nats(f"nats://127.0.0.1:{host_port}")

        _docker(
            "run",
            "--rm",
            "--user",
            "0:0",
            "--entrypoint",
            "sh",
            "--volume",
            f"{volume}:/home/custos/.arx",
            IMAGE,
            "-c",
            "mkdir -p /home/custos/.arx/vault /home/custos/.arx/state && "
            "chown -R 1000:1000 /home/custos/.arx && chmod 700 /home/custos/.arx",
        )
        runner_record = (
            "from pathlib import Path; from custos.core.runner_toml import RunnerToml; "
            "RunnerToml.write(Path('/home/custos/.arx/runner.toml'), "
            "RunnerToml(tenant_id='acceptance', runner_id='runner-acceptance', "
            "backend_url='http://standalone.invalid', "
            "long_term_credential='acceptance-local-only', enrolled_at_ns=1))"
        )
        _docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "--volume",
            f"{volume}:/home/custos/.arx",
            IMAGE,
            "-c",
            runner_record,
        )
        _docker(
            "run",
            "--rm",
            "--entrypoint",
            "age-keygen",
            "--volume",
            f"{volume}:/home/custos/.arx",
            IMAGE,
            "-o",
            "/home/custos/.arx/age.key",
        )
        recipient = _docker(
            "run",
            "--rm",
            "--entrypoint",
            "age-keygen",
            "--volume",
            f"{volume}:/home/custos/.arx",
            IMAGE,
            "-y",
            "/home/custos/.arx/age.key",
        ).stdout.strip()
        _docker(
            "run",
            "--interactive",
            "--rm",
            "--volume",
            f"{volume}:/home/custos/.arx",
            IMAGE,
            "vault",
            "put",
            "--key-id",
            KEY_ID,
            "--tenant-id",
            TENANT_ID,
            "--api-key",
            "acceptance-public-key",
            "--api-secret-stdin",
            "--age-recipient",
            recipient,
            input_text="acceptance-secret\n",
        )
        _docker(
            "run",
            "--rm",
            "--entrypoint",
            "sops",
            "--volume",
            f"{volume}:/home/custos/.arx",
            "--env",
            "SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key",
            IMAGE,
            "--decrypt",
            "--input-type",
            "json",
            "--output-type",
            "json",
            f"/home/custos/.arx/vault/{KEY_ID}.enc",
        )

        _docker(
            "run",
            "--detach",
            "--name",
            runner_container,
            "--network",
            network,
            "--volume",
            f"{volume}:/home/custos/.arx",
            "--env",
            "SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key",
            IMAGE,
            "start",
            "--nats-url",
            "nats://nats:4222",
            "--reconcile-strategy-id",
            STRATEGY_ID,
            "--engine",
            "noop",
            "--heartbeat-interval",
            "0.2",
            "--snapshot-interval-secs",
            "0.2",
        )
        await _wait_for_runner_health(runner_container)

        status_subject = f"arx.{TENANT_ID}.deployment_status.{RUNNER_ID}.{SPEC_ID}"
        subscription = await connection.subscribe(status_subject)
        await connection.flush()

        running_spec = tmp_path / "running.json"
        _write_spec(running_spec, generation=1, lifecycle_state="running")
        await asyncio.to_thread(_publish_spec, network, tmp_path, running_spec.name)
        running = await _next_status_with_logs(subscription, generation=1, runner=runner_container)
        assert running["phase"] == "running"
        assert running["health"] == "healthy"
        assert running["container_id"] == f"container-{SPEC_ID}"

        stopped_spec = tmp_path / "stopped.json"
        _write_spec(stopped_spec, generation=2, lifecycle_state="stopped")
        await asyncio.to_thread(_publish_spec, network, tmp_path, stopped_spec.name)
        stopped = await _next_status_with_logs(subscription, generation=2, runner=runner_container)
        assert stopped["phase"] == "stopped"
        assert stopped["health"] == "healthy"
        assert stopped["container_id"] == ""

        restarted_spec = tmp_path / "restarted.json"
        _write_spec(restarted_spec, generation=3, lifecycle_state="running")
        await asyncio.to_thread(_publish_spec, network, tmp_path, restarted_spec.name)
        restarted = await _next_status_with_logs(
            subscription, generation=3, runner=runner_container
        )
        assert restarted["phase"] == "running"
        assert restarted["health"] == "healthy"
        assert restarted["container_id"] == f"container-{SPEC_ID}"
        await _wait_for_runner_health(runner_container)
    finally:
        if connection is not None:
            await connection.drain()
        _docker("rm", "--force", runner_container, check=False)
        _docker("rm", "--force", nats_container, check=False)
        _docker("network", "rm", network, check=False)
        _docker("volume", "rm", "--force", volume, check=False)
