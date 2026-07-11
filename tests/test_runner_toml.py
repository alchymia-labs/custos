"""Failing-first tests for the ``~/.arx/runner.toml`` persistence module.

Contract:
- 0600 file mode invariant on write and refuse on read when world-readable.
- Atomic write (tmpfile + fsync + rename); a mid-rename crash must leave the
  prior file (or nothing) intact rather than a partial write.
- ``~/.arx/`` directory auto-create at 0700.
- Missing file on read raises a clear ``FileNotFoundError`` with an actionable
  ``arx-runner enroll`` hint (never a silent ``None``).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from custos.core.runner_toml import RunnerToml


def _sample_record() -> RunnerToml:
    return RunnerToml(
        tenant_id="acme",
        runner_id="runner-7",
        backend_url="https://team-server.example",
        long_term_credential="lt-credential-value",
        enrolled_at_ns=1_700_000_000_000_000_000,
    )


def test_write_creates_file_at_0600(tmp_path: Path) -> None:
    target = tmp_path / "arx" / "runner.toml"
    RunnerToml.write(target, _sample_record())
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_write_creates_arx_dir_at_0700(tmp_path: Path) -> None:
    target = tmp_path / "arx" / "runner.toml"
    RunnerToml.write(target, _sample_record())
    dir_mode = stat.S_IMODE(os.stat(target.parent).st_mode)
    assert dir_mode == 0o700, f"expected parent dir 0o700, got {oct(dir_mode)}"


def test_read_round_trips_written_record(tmp_path: Path) -> None:
    target = tmp_path / "arx" / "runner.toml"
    original = _sample_record()
    RunnerToml.write(target, original)
    loaded = RunnerToml.read(target)
    assert loaded == original


def test_read_rejects_world_readable_mode(tmp_path: Path) -> None:
    target = tmp_path / "runner.toml"
    target.write_text(
        'tenant_id = "acme"\n'
        'runner_id = "runner-7"\n'
        'backend_url = "https://team-server.example"\n'
        'long_term_credential = "lt-value"\n'
        "enrolled_at_ns = 1700000000000000000\n",
        encoding="utf-8",
    )
    os.chmod(target, 0o644)
    with pytest.raises(PermissionError, match="0600"):
        RunnerToml.read(target)


def test_read_missing_file_raises_clear_error(tmp_path: Path) -> None:
    target = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError, match="arx-runner enroll"):
        RunnerToml.read(target)


def test_atomic_write_survives_interrupt(tmp_path: Path) -> None:
    target = tmp_path / "arx" / "runner.toml"
    original = _sample_record()
    RunnerToml.write(target, original)
    pre_snapshot = target.read_bytes()

    updated = RunnerToml(
        tenant_id="acme",
        runner_id="runner-7",
        backend_url="https://team-server.example",
        long_term_credential="rotated-value",
        enrolled_at_ns=1_700_000_000_000_000_001,
    )

    with mock.patch("os.rename", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError, match="simulated crash"):
            RunnerToml.write(target, updated)

    assert target.read_bytes() == pre_snapshot, "old file must be untouched on rename failure"
    tmp_files = list(target.parent.glob(".runner.toml.tmp*"))
    assert not tmp_files, f"tmpfile leak after failed rename: {tmp_files}"


def test_read_rejects_missing_required_field(tmp_path: Path) -> None:
    target = tmp_path / "runner.toml"
    target.write_text(
        'tenant_id = "acme"\n'
        'runner_id = "runner-7"\n'
        'backend_url = "https://team-server.example"\n'
        "enrolled_at_ns = 1700000000000000000\n",  # missing long_term_credential
        encoding="utf-8",
    )
    os.chmod(target, 0o600)
    with pytest.raises(ValueError, match="long_term_credential"):
        RunnerToml.read(target)
