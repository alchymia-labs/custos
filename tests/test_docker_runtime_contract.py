"""Plan 14 T5 contract for the complete official Docker runtime."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

IMAGE = os.environ.get("CUSTOS_TEST_IMAGE", "custos-runner:test")


def _require_image() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH")
    inspect = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        pytest.skip(f"image {IMAGE} not present; run `make docker-build` first")


def _run_image(*args: str, entrypoint: str | None = None) -> subprocess.CompletedProcess[str]:
    command = ["docker", "run", "--rm"]
    if entrypoint is not None:
        command.extend(["--entrypoint", entrypoint])
    command.extend([IMAGE, *args])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.docker
@pytest.mark.parametrize(
    "command",
    [
        ("--help",),
        ("start", "--help"),
        ("vault", "put", "--help"),
        ("nats", "bootstrap", "--help"),
        ("deployment", "publish", "--help"),
        ("health", "--help"),
    ],
)
def test_official_image_exposes_command_matrix(command: tuple[str, ...]) -> None:
    _require_image()

    proc = _run_image(*command)

    assert proc.returncode == 0, (
        f"expected `docker run --rm {IMAGE} {' '.join(command)}` exit 0; "
        f"got rc={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )


@pytest.mark.docker
def test_official_image_has_clean_entrypoint_cmd_and_healthcheck() -> None:
    _require_image()
    inspect = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .Config.Entrypoint}}|{{json .Config.Cmd}}|{{json .Config.Healthcheck.Test}}",
            IMAGE,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    entrypoint, command, healthcheck = inspect.stdout.strip().split("|")

    assert json.loads(entrypoint) == ["arx-runner"]
    assert json.loads(command) == ["start"]
    assert json.loads(healthcheck) == ["CMD", "arx-runner", "health"]


@pytest.mark.docker
def test_official_image_contains_nautilus_and_yaml() -> None:
    _require_image()

    proc = _run_image(
        "-c",
        "import nautilus_trader, yaml",
        entrypoint="python",
    )

    assert proc.returncode == 0, (
        f"official image must import NautilusTrader and PyYAML; "
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )


@pytest.mark.docker
def test_official_image_contains_v030_distribution() -> None:
    _require_image()

    proc = _run_image(
        "-c",
        "from importlib.metadata import version; print(version('custos-runner'))",
        entrypoint="python",
    )

    assert proc.returncode == 0, (
        "official image must contain the custos-runner distribution; "
        f"stdout={proc.stdout!r}; stderr={proc.stderr!r}"
    )
    assert proc.stdout.strip() == "0.3.0"


@pytest.mark.docker
def test_official_image_has_source_revision_label() -> None:
    _require_image()
    inspect = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "org.opencontainers.image.revision"}}',
            IMAGE,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert re.fullmatch(r"[0-9a-f]{40}", inspect.stdout.strip())


@pytest.mark.docker
@pytest.mark.parametrize("binary", ["sops", "age"])
def test_official_image_contains_vault_toolchain(binary: str) -> None:
    _require_image()

    proc = _run_image("--version", entrypoint=binary)

    assert proc.returncode == 0, (
        f"official image must provide `{binary} --version`; "
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
