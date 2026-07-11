"""Failing-first tests for the ``arx-runner`` subcommand dispatcher.

Contract:
- No subcommand or an unknown subcommand exits non-zero with a usage
  message listing the registered subcommands (``enroll`` / ``start`` /
  ``vault``).
- Each subcommand's ``--help`` lists its own flags without needing a
  full runtime wiring (the handler bodies are still stubs at T3 — T4-T7
  fill them in).
"""

from __future__ import annotations

import pytest

from custos.cli.subcommands import main


def test_no_subcommand_shows_help_nonzero_exit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    for cmd in ("enroll", "start", "vault"):
        assert cmd in err


def test_unknown_subcommand_shows_help_nonzero_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["foo"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    # argparse prints "invalid choice" for unknown subcommand plus the list.
    assert "invalid choice" in err or "unknown" in err.lower()
    for cmd in ("enroll", "start", "vault"):
        assert cmd in err


def test_enroll_help_lists_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["enroll", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--token", "--backend", "--tenant-id", "--runner-id"):
        assert flag in out


def test_start_help_lists_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["start", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--runner-toml" in out


def test_vault_help_lists_subactions(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["vault", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for action in ("put", "verify", "list"):
        assert action in out


def test_vault_no_action_shows_help_nonzero_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["vault"])
    assert excinfo.value.code != 0
