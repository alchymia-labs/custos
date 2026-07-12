from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custos.cli.subcommands import main
from custos.contracts import compute_strategy_code_hash


def _spec_file(tmp_path: Path, *, mode: str = "sandbox") -> Path:
    raw = {
        "spec_id": "supertrend-sandbox",
        "generation": 1,
        "trading_mode": mode,
        "lifecycle_state": "running",
        "strategy_path": "/opt/strategies/supertrend/strategy.py",
        "provenance_ref": {"credential_id": "binance-sandbox"},
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
    }
    if mode == "sandbox":
        raw["sandbox"] = {"starting_balances": ["10_000 USDT"]}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw))
    return path


def test_validate_is_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connect = AsyncMock(side_effect=AssertionError("validate must not connect"))
    monkeypatch.setattr("custos.cli.subcommands.deployment.nats.connect", connect)

    exit_code = main(["deployment", "validate", "--spec-file", str(_spec_file(tmp_path))])

    assert exit_code == 0
    connect.assert_not_awaited()
    assert "valid" in capsys.readouterr().out.lower()


def test_validate_rejects_invalid_spec(tmp_path: Path) -> None:
    spec_file = _spec_file(tmp_path)
    raw = json.loads(spec_file.read_text())
    raw["generation"] = 0
    spec_file.write_text(json.dumps(raw))

    assert main(["deployment", "validate", "--spec-file", str(spec_file)]) != 0


def test_validate_live_spec_accepts_strategy_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("VALUE = 1\n")
    spec_file = _spec_file(tmp_path, mode="live")
    original = spec_file.read_text()

    result = main(
        [
            "deployment",
            "validate",
            "--spec-file",
            str(spec_file),
            "--strategy-dir",
            str(strategy_dir),
        ]
    )

    assert result == 0
    assert "valid DeploymentSpec" in capsys.readouterr().out
    assert spec_file.read_text() == original


def test_validate_live_spec_rejects_missing_strategy_dir(tmp_path: Path) -> None:
    result = main(
        [
            "deployment",
            "validate",
            "--spec-file",
            str(_spec_file(tmp_path, mode="live")),
            "--strategy-dir",
            str(tmp_path / "missing"),
        ]
    )

    assert result == 1


def test_validate_live_spec_rejects_unknown_field_after_hash(tmp_path: Path) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("VALUE = 1\n")
    spec_file = _spec_file(tmp_path, mode="live")
    raw = json.loads(spec_file.read_text())
    raw["strategy_confg"] = {}
    spec_file.write_text(json.dumps(raw))

    result = main(
        [
            "deployment",
            "validate",
            "--spec-file",
            str(spec_file),
            "--strategy-dir",
            str(strategy_dir),
        ]
    )

    assert result == 1


def test_publish_waits_for_jetstream_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jetstream = AsyncMock()
    jetstream.publish.return_value = object()
    connection = MagicMock()
    connection.drain = AsyncMock()
    connection.jetstream.return_value = jetstream
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("custos.cli.subcommands.deployment.nats.connect", connect)

    exit_code = main(
        [
            "deployment",
            "publish",
            "--spec-file",
            str(_spec_file(tmp_path)),
            "--tenant-id",
            "acme",
            "--strategy-id",
            "supertrend-sandbox",
            "--nats-url",
            "nats://nats:4222",
        ]
    )

    assert exit_code == 0
    connect.assert_awaited_once_with("nats://nats:4222")
    jetstream.publish.assert_awaited_once()
    subject, payload = jetstream.publish.await_args.args
    assert subject == "arx.acme.deployment_spec.supertrend-sandbox"
    assert json.loads(payload)["payload"]["spec"]["generation"] == 1
    connection.drain.assert_awaited_once()


def test_publish_strategy_dir_overrides_code_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("class Strategy:\n    pass\n")
    spec_file = _spec_file(tmp_path, mode="live")
    jetstream = AsyncMock()
    jetstream.publish.return_value = object()
    connection = MagicMock()
    connection.drain = AsyncMock()
    connection.jetstream.return_value = jetstream
    monkeypatch.setattr(
        "custos.cli.subcommands.deployment.nats.connect",
        AsyncMock(return_value=connection),
    )

    exit_code = main(
        [
            "deployment",
            "publish",
            "--spec-file",
            str(spec_file),
            "--tenant-id",
            "acme",
            "--strategy-id",
            "supertrend-live",
            "--strategy-dir",
            str(strategy_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads(jetstream.publish.await_args.args[1])
    assert payload["payload"]["spec"]["code_hash"] == compute_strategy_code_hash(strategy_dir)


def test_publish_live_without_hash_fails_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = AsyncMock()
    monkeypatch.setattr("custos.cli.subcommands.deployment.nats.connect", connect)

    exit_code = main(
        [
            "deployment",
            "publish",
            "--spec-file",
            str(_spec_file(tmp_path, mode="live")),
            "--tenant-id",
            "acme",
            "--strategy-id",
            "supertrend-live",
        ]
    )

    assert exit_code != 0
    connect.assert_not_awaited()
