from __future__ import annotations

import json
from pathlib import Path

import pytest

from custos.cli.subcommands import main
from custos.contracts import compute_strategy_code_hash

SHA = "a" * 64


def _spec_file(
    tmp_path: Path,
    *,
    mode: str = "sandbox",
    code_hash: str = SHA,
) -> Path:
    raw = {
        "spec_id": "11111111-1111-4111-8111-111111111111",
        "deployment_instance_id": "22222222-2222-4222-8222-222222222222",
        "deployment_spec_digest": SHA,
        "strategy_id": "33333333-3333-4333-8333-333333333333",
        "generation": 1,
        "trading_mode": mode,
        "lifecycle_state": "running",
        "strategy_path": "/opt/strategies/supertrend/strategy.py",
        "provenance_ref": {"credential_id": "binance-sandbox"},
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_config": {},
        "code_hash": code_hash,
    }
    if mode == "sandbox":
        raw["sandbox"] = {"starting_balances": ["10_000 USDT"]}
    if mode == "live":
        raw["promotion_id"] = "44444444-4444-4444-8444-444444444444"
        raw["promotion_evidence_digest"] = "b" * 64
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw))
    return path


def test_validate_is_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["deployment", "validate", "--spec-file", str(_spec_file(tmp_path))])

    assert exit_code == 0
    assert "DeploymentSpec valid" in capsys.readouterr().out


def test_validate_rejects_invalid_spec(tmp_path: Path) -> None:
    spec_file = _spec_file(tmp_path)
    raw = json.loads(spec_file.read_text())
    raw["generation"] = 0
    spec_file.write_text(json.dumps(raw))

    assert main(["deployment", "validate", "--spec-file", str(spec_file)]) == 1


def test_validate_live_spec_accepts_matching_strategy_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("VALUE = 1\n")
    spec_file = _spec_file(
        tmp_path,
        mode="live",
        code_hash=compute_strategy_code_hash(strategy_dir),
    )
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
    assert "DeploymentSpec valid" in capsys.readouterr().out
    assert spec_file.read_text() == original


def test_validate_rejects_strategy_digest_mismatch(tmp_path: Path) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("VALUE = 1\n")

    result = main(
        [
            "deployment",
            "validate",
            "--spec-file",
            str(_spec_file(tmp_path, mode="live")),
            "--strategy-dir",
            str(strategy_dir),
        ]
    )

    assert result == 1


def test_validate_rejects_unknown_field(tmp_path: Path) -> None:
    spec_file = _spec_file(tmp_path)
    raw = json.loads(spec_file.read_text())
    raw["strategy_confg"] = {}
    spec_file.write_text(json.dumps(raw))

    assert main(["deployment", "validate", "--spec-file", str(spec_file)]) == 1


def test_deployment_publish_action_is_not_available(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["deployment", "publish", "--spec-file", str(_spec_file(tmp_path))])
