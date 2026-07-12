"""Failing-first tests for ``arx-runner start``.

The start subcommand reads ``~/.arx/runner.toml``, builds a runtime
namespace (with per-key vault + WAL + reconciler defaults), and delegates
to ``custos.cli._daemon.run_daemon``. Tests mock ``run_daemon`` so no
real NATS / NT connect happens.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from custos.cli.subcommands import main
from custos.core.runner_toml import RunnerToml


def _seed_runner_toml(target: Path) -> None:
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    RunnerToml.write(
        target,
        RunnerToml(
            tenant_id="acme",
            runner_id="runner-7",
            backend_url="https://team-server.example",
            long_term_credential="lt-abc",
            enrolled_at_ns=1_700_000_000_000_000_000,
        ),
    )


def _run_start(argv: list[str], *, monkeypatch: pytest.MonkeyPatch) -> tuple[int, mock.MagicMock]:
    run_daemon = mock.MagicMock()

    async def _fake(*args, **kwargs):
        run_daemon(*args, **kwargs)
        return 0

    monkeypatch.setattr("custos.cli._daemon.run_daemon", _fake)
    return main(["start", *argv]), run_daemon


def test_start_reads_runner_toml_and_wires_reconciler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    _seed_runner_toml(runner_toml)
    exit_code, run_daemon = _run_start(["--runner-toml", str(runner_toml)], monkeypatch=monkeypatch)
    assert exit_code == 0
    ns = run_daemon.call_args.args[0]
    assert ns.tenant_id == "acme"
    assert ns.runner_id == "runner-7"


def test_start_missing_runner_toml_fails_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    exit_code, run_daemon = _run_start(["--runner-toml", str(runner_toml)], monkeypatch=monkeypatch)
    assert exit_code != 0
    err = capsys.readouterr().err
    assert "arx-runner enroll" in err
    run_daemon.assert_not_called()


def test_start_partial_runner_toml_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "runner.toml"
    runner_toml.write_text('tenant_id = "acme"\nrunner_id = "r"\n', encoding="utf-8")
    os.chmod(runner_toml, 0o600)
    exit_code, run_daemon = _run_start(["--runner-toml", str(runner_toml)], monkeypatch=monkeypatch)
    assert exit_code != 0
    err = capsys.readouterr().err
    assert "backend_url" in err or "missing" in err.lower()
    run_daemon.assert_not_called()


def test_start_rejects_world_readable_runner_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "runner.toml"
    runner_toml.write_text(
        'tenant_id = "acme"\n'
        'runner_id = "runner-7"\n'
        'backend_url = "https://x"\n'
        'long_term_credential = "abc"\n'
        "enrolled_at_ns = 1\n",
        encoding="utf-8",
    )
    os.chmod(runner_toml, 0o644)
    exit_code, run_daemon = _run_start(["--runner-toml", str(runner_toml)], monkeypatch=monkeypatch)
    assert exit_code != 0
    err = capsys.readouterr().err
    assert "0600" in err
    run_daemon.assert_not_called()


def test_start_preserves_engine_and_wal_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    _seed_runner_toml(runner_toml)
    wal = tmp_path / "custom-wal.db"
    vault_dir = tmp_path / "custom-vault"
    exit_code, run_daemon = _run_start(
        [
            "--runner-toml",
            str(runner_toml),
            "--engine",
            "nautilus",
            "--wal-path",
            str(wal),
            "--vault-dir",
            str(vault_dir),
        ],
        monkeypatch=monkeypatch,
    )
    assert exit_code == 0
    ns = run_daemon.call_args.args[0]
    assert ns.engine == "nautilus"
    assert ns.wal_path == wal
    assert ns.vault_dir == vault_dir


def test_engine_nautilus_selects_real_host() -> None:
    from argparse import Namespace

    from custos.cli._daemon import _build_host
    from custos.engines.nautilus.host import NtTradingNodeHost

    host = _build_host(Namespace(engine="nautilus", tenant_id="acme", runner_id="runner-1"))

    assert isinstance(host, NtTradingNodeHost)


def test_engine_noop_selects_noop_host() -> None:
    from argparse import Namespace

    from custos.cli._daemon import _build_host
    from custos.engines.nautilus.host import NoopHost

    host = _build_host(Namespace(engine="noop", tenant_id="acme", runner_id="runner-1"))

    assert isinstance(host, NoopHost)


def test_use_nt_host_flag_is_removed() -> None:
    with pytest.raises(SystemExit):
        main(["start", "--use-nt-host"])


def test_start_preserves_ready_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    _seed_runner_toml(runner_toml)
    ready_file = tmp_path / "runner-ready.json"

    exit_code, run_daemon = _run_start(
        ["--runner-toml", str(runner_toml), "--ready-file", str(ready_file)],
        monkeypatch=monkeypatch,
    )

    assert exit_code == 0
    assert run_daemon.call_args.args[0].ready_file == ready_file


def test_start_default_paths_target_arx_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No CLI overrides → every default path begins with ~/.arx (no .custos)."""
    runner_toml = tmp_path / "arx" / "runner.toml"
    _seed_runner_toml(runner_toml)
    exit_code, run_daemon = _run_start(["--runner-toml", str(runner_toml)], monkeypatch=monkeypatch)
    assert exit_code == 0
    ns = run_daemon.call_args.args[0]
    for path in (ns.wal_path, ns.enrollment_path, ns.vault_dir):
        assert ".custos" not in str(path)
        assert ".arx" in str(path)
