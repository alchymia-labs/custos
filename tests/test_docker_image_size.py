"""Complete official runtime Docker image size ceiling.

Multi-stage builds are a common regression surface: forgetting to copy from
the `builder` stage instead of installing again in `runtime` can silently
double the image size. The complete Nautilus runtime measured 1,070,492,907
bytes on Linux arm64 during Plan 14 T5. The 1.25 GiB ceiling leaves headroom
for architecture and routine dependency differences while remaining below
the plan's hard 1.5 GiB maximum. The goal is to catch a builder-stage leak,
not to police normal dependency growth.

Gated behind ``@pytest.mark.docker``.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

IMAGE = os.environ.get("CUSTOS_TEST_IMAGE", "custos-runner:test")
CEILING_BYTES = 1280 * 1024 * 1024


@pytest.mark.docker
def test_docker_image_size_under_1280mib():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH")
    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{.Size}}", IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        pytest.skip(f"image {IMAGE} not present; run `make docker-build` first")
    size = int(inspect.stdout.strip())
    assert size < CEILING_BYTES, (
        f"image {IMAGE} size {size / 1024 / 1024:.1f} MB exceeds "
        f"{CEILING_BYTES / 1024 / 1024:.0f} MB ceiling — likely a multi-stage "
        f"builder leak; verify Dockerfile only COPIES from the builder stage "
        f"into runtime and does not re-run `pip install`."
    )
