"""Contract tests for the `make toolkit-sync-check` real diff implementation.

The target diffs the vendored ps `shared/` subset against a local upstream
checkout (`PS_ROOT`, required). The pinned commit to diff from normally comes
from `docs/authority/strategy-toolkit-provenance.md`, but can be overridden via `PINNED_PS_SHA` for
tests — that seam keeps these tests hermetic (a synthetic local git fixture,
not a dependency on any real philosophers-stone checkout being present on
the machine running the tests, matching independent-repo self-sufficiency).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2].parent

_FIXTURE_GIT_ENV = {
    "GIT_AUTHOR_NAME": "toolkit-sync-check-fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "toolkit-sync-check-fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def _base_env() -> dict[str, str]:
    return dict(os.environ)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = _base_env()
    env.update(_FIXTURE_GIT_ENV)
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )


def _run_sync_check(*, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "toolkit-sync-check"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_shared_file(repo: Path, contents: str) -> None:
    config_dir = repo / "shared" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "loader.py").write_text(contents, encoding="utf-8")


@pytest.fixture
def ps_fixture(tmp_path: Path) -> tuple[Path, str]:
    """A minimal local git repo mimicking ps: one commit with a `shared/`
    tree. Returns (repo_path, pinned_sha) — pinned_sha is that first
    commit's real SHA, usable as a `PINNED_PS_SHA` override."""
    repo = tmp_path / "ps_fixture"
    repo.mkdir()
    _write_shared_file(repo, "# fixture loader v1\n")
    (repo / "README.md").write_text("# fixture ps repo\n", encoding="utf-8")

    _git("init", "-q", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "initial fixture commit", cwd=repo)
    pinned = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    return repo, pinned


def test_toolkit_sync_check_zero_drift_current(ps_fixture: tuple[Path, str]) -> None:
    """PS_ROOT HEAD equals the pinned SHA — sync-check must exit 0, report no
    drift, and gracefully note pandas_ta as a manual check when
    PANDAS_TA_ROOT is unset."""
    repo, pinned = ps_fixture
    env = _base_env()
    env["PS_ROOT"] = str(repo)
    env["PINNED_PS_SHA"] = pinned
    env.pop("PANDAS_TA_ROOT", None)

    result = _run_sync_check(env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "drift: no" in result.stdout.lower()
    assert "manual check required" in result.stdout.lower()


def test_toolkit_sync_check_detects_upstream_drift(ps_fixture: tuple[Path, str]) -> None:
    """A synthetic commit landing after the pinned SHA under `shared/` must
    be detected as drift — non-zero exit + structured drift report.

    The recipe itself exits 1 on drift, but `make` wraps any non-zero recipe
    exit as its own "Error N" and returns a make-level exit code (commonly 2)
    rather than passing the recipe's literal code through — so the
    CI-meaningful assertion here is "non-zero", matching what a CI pipeline
    actually branches on.
    """
    repo, pinned = ps_fixture
    _write_shared_file(repo, "# fixture loader v2 (drift)\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "drift: touch shared/config/loader.py", cwd=repo)

    env = _base_env()
    env["PS_ROOT"] = str(repo)
    env["PINNED_PS_SHA"] = pinned

    result = _run_sync_check(env=env)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "drift: yes" in result.stdout.lower()


def test_toolkit_sync_check_reports_new_ps_commits(ps_fixture: tuple[Path, str]) -> None:
    """Output must name the new commit(s) under `shared/` plus a diff-stat,
    not just a yes/no verdict."""
    repo, pinned = ps_fixture
    _write_shared_file(repo, "# fixture loader v2 (drift)\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "drift: touch shared/config/loader.py", cwd=repo)

    env = _base_env()
    env["PS_ROOT"] = str(repo)
    env["PINNED_PS_SHA"] = pinned

    result = _run_sync_check(env=env)

    assert "drift: touch shared/config/loader.py" in result.stdout
    assert "1 file" in result.stdout, (
        f"expected a diff-stat line naming '1 file changed', got:\n{result.stdout}"
    )


def test_toolkit_sync_check_requires_ps_root() -> None:
    """PS_ROOT unset must fail fast with a clear error referencing PS_ROOT,
    never a silent success."""
    env = _base_env()
    env.pop("PS_ROOT", None)

    result = _run_sync_check(env=env)

    assert result.returncode != 0
    assert "PS_ROOT" in result.stderr or "PS_ROOT" in result.stdout
