"""Plan 12 T2 contract: Docker image runs as non-root (FM2 Layer 2).

The daemon must not run as `root` inside the container. The
``USER 1000:1000`` line in the Dockerfile is Layer 1; the CI job's
``docker inspect`` gate is Layer 3; this test is Layer 2 (build the image
locally, ``docker inspect`` its ``Config.User``).

Gated behind ``@pytest.mark.docker`` so contributors without a Docker
daemon skip cleanly. The docker image is expected to already have been
built via ``make docker-build`` (or the CI job); the test is intentionally
side-effect-free — it does not build the image itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

IMAGE = os.environ.get("CUSTOS_TEST_IMAGE", "custos-runner:test")


@pytest.mark.docker
def test_docker_image_runs_as_non_root_user():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not on PATH")
    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{.Config.User}}", IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        pytest.skip(
            f"image {IMAGE} not present; run `make docker-build` first "
            f"(stderr={inspect.stderr.strip()!r})"
        )
    user = inspect.stdout.strip()
    assert user, f"Config.User must be set; got empty string ({inspect.stdout!r})"
    assert user != "root", f"expected non-root USER, got {user!r}"
    assert user != "0", f"expected non-root UID, got {user!r}"
    # Plan 12 T2 pins `USER 1000:1000` (non-privileged system user).
    assert user.startswith("1000"), f"expected `1000:1000` USER, got {user!r}"
