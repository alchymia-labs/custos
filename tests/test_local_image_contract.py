from __future__ import annotations

from pathlib import Path

MAKEFILE = Path(__file__).resolve().parents[1] / "Makefile"


def test_makefile_defines_local_v030_image_contract() -> None:
    text = MAKEFILE.read_text()

    assert "LOCAL_IMAGE ?= custos-runner:v0.3.0" in text
    assert "docker-build-local-v030:" in text
    assert "verify-local-v030:" in text
    assert "org.opencontainers.image.revision" in text
    assert "CUSTOS_TEST_IMAGE=$(LOCAL_IMAGE)" in text
    assert "verify-runtime-existing" in text


def test_generic_docker_build_injects_source_revision() -> None:
    text = MAKEFILE.read_text()
    start = text.index("docker-build: dist")
    end = text.index("docker-build-local-v030:", start)
    block = text[start:end]

    assert "--label org.opencontainers.image.revision=$(SOURCE_REVISION)" in block
