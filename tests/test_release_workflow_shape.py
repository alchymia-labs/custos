"""Plan 12 T4 contract: release workflow shape (permissions + 8-job DAG).

CI workflows only really exercise at tag push, so this test locks the
shape locally with plain-text assertions. That trades some strictness
(we can't verify structural relationships as tightly as a YAML parse)
for the property that we don't depend on `pyyaml` — which isn't in the
`dev` extra and would bloat the default test env just for this gate.

The assertions cover the four regressions Plan 12 R1 review called out:

- H2: `permissions:` (plural) with `id-token: write` + `packages: write`
  + `contents: write`.
- H5: 8-job DAG, all documented job names present.
- M6: stable-only tag pattern (`v[0-9]+.[0-9]+.[0-9]+`), no `v*` wildcard.
- H1: `build-docker` `needs:` includes both `build-wheel` and `sign-wheel`
  so the image is always built on the signed wheel, never on a PyPI
  fetch.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"

EXPECTED_JOBS = (
    "build-wheel",
    "sign-wheel",
    "build-docker",
    "sign-docker",
    "publish-pypi",
    "publish-ghcr",
    "verify-release",
    "release-notes",
)


def _read() -> str:
    return WORKFLOW.read_text()


def test_workflow_file_exists():
    assert WORKFLOW.exists(), f"missing workflow at {WORKFLOW}"


def test_permissions_plural_with_write_scopes():
    text = _read()
    # H2: plural `permissions:` at top level, exact scopes required by sigstore
    # + GHCR + release-notes.
    assert "\npermissions:\n" in text, "top-level `permissions:` block missing"
    assert "id-token: write" in text, "id-token: write required (sigstore OIDC)"
    assert "packages: write" in text, "packages: write required (GHCR push)"
    assert "contents: write" in text, "contents: write required (release notes)"


def test_workflow_has_eight_documented_jobs():
    text = _read()
    for name in EXPECTED_JOBS:
        assert f"\n  {name}:\n" in text, f"missing job `{name}` in workflow"


def test_stable_tag_pattern_only():
    """M6: stable-only tag pattern; `v*` wildcard would auto-publish RCs to
    the stable PyPI channel and pollute the tag series."""
    text = _read()
    assert "v[0-9]+.[0-9]+.[0-9]+" in text, "stable semver tag pattern missing"
    # Belt-and-braces: guard against the common regression of adding a bare
    # `v*` glob elsewhere in the trigger block.
    assert "- 'v*'" not in text and '- "v*"' not in text, (
        "wildcard tag pattern `v*` re-introduced; would auto-publish rc.* tags"
    )


def test_build_docker_needs_signed_wheel():
    """H1: docker image must build on the artifact from sign-wheel, not a
    PyPI-resolved one. `needs: [build-wheel, sign-wheel]` enforces the DAG."""
    text = _read()
    # Search for the build-docker `needs:` line + verify it references both
    # upstream jobs. Grep is intentionally permissive on formatting so we
    # don't hard-code YAML style.
    lines = text.splitlines()
    build_docker_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "build-docker:"), None
    )
    assert build_docker_idx is not None, "no `build-docker:` job block"
    # Scan the next 15 lines for the `needs:` line.
    window = "\n".join(lines[build_docker_idx : build_docker_idx + 15])
    assert "needs:" in window
    assert "build-wheel" in window
    assert "sign-wheel" in window


def test_release_verifies_clean_base_before_nautilus_runtime() -> None:
    """A preinstalled NT runtime must not mask the dev-only base gate."""
    text = _read()

    base_gate = text.index("make verify-base-clean")
    install_nt = text.index("make install-nt")
    verify_nt = text.index("make verify-nt")

    assert base_gate < install_nt < verify_nt
