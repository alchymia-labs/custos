"""Plan 12 T2 / FM11: Docker image size ceiling.

Multi-stage builds are a common regression surface: forgetting to copy from
the `builder` stage instead of installing again in `runtime` can silently
double the image size. This test caps the image at 800 MB (Plan 12 M5 fix
— relaxed from the original 500 MB after review to avoid flaky failures on
routine pandas/numpy minor bumps). The goal is to catch a builder-stage
leak, not to police normal dependency growth.

Gated behind ``@pytest.mark.docker``.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

IMAGE = "custos-runner:test"
CEILING_BYTES = 800 * 1024 * 1024  # 800 MB — Plan 12 FM11 (M5 fix)


@pytest.mark.docker
def test_docker_image_size_under_800mb():
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
