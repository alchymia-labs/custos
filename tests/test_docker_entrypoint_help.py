"""Docker root-command ENTRYPOINT smoke.

Runs ``docker run --rm <image> --help`` and asserts exit 0. This proves the
image's ENTRYPOINT chain (``arx-runner`` + Python site-packages copied
from the builder stage) actually resolves at runtime — not just the
declarative table in ``docker inspect``.

Before Plan 12 R1 the ENTRYPOINT was mis-declared as ``["python", "-m",
"custos"]`` (Plan 11 removed that entry point) and this smoke test would
have surfaced the dead-image regression. It is deliberately independent
from ``test_docker_non_root.py`` so an image that "inspects clean" but
crashes on start is still caught.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

IMAGE = os.environ.get("CUSTOS_TEST_IMAGE", "custos-runner:test")


@pytest.mark.docker
def test_docker_entrypoint_help_exits_zero():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH")
    check = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        pytest.skip(f"image {IMAGE} not present; run `make docker-build` first")
    proc = subprocess.run(
        ["docker", "run", "--rm", IMAGE, "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"expected `docker run --rm {IMAGE} --help` exit 0; "
        f"got rc={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    # Root help must mention the default `start` subcommand; this distinguishes
    # the clean command dispatcher from the old baked-in `arx-runner start`.
    assert "start" in proc.stdout.lower() or "start" in proc.stderr.lower(), (
        f"help output missing `start` subcommand mention; stdout={proc.stdout!r}"
    )
