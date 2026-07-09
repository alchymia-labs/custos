"""Strategy source loader + code_hash verification.

code_hash pinning is a non-custodial red line: the runner must refuse to start
a strategy whose on-disk bytes don't match the spec's expected hash. Covers:
- the hash is deterministic and content-sensitive
- a mismatched hash is rejected (CodeHashMismatch) before any import happens
- a matching hash loads the class
- expected_code_hash=None (sandbox) skips the check but emits an audit event
- a missing strategy path fails fast (FileNotFoundError)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from custos.engines.nautilus.strategy_loader import (
    CodeHashMismatch,
    compute_strategy_dir_hash,
    load_strategy_class,
)

_STRATEGY_SRC = """
from __future__ import annotations


class DemoStrategy:
    def __init__(self, marker: str = "v1") -> None:
        self.marker = marker
"""


def _write_strategy(tmp_path: Path, body: str = _STRATEGY_SRC) -> Path:
    strat_dir = tmp_path / "demo"
    strat_dir.mkdir(parents=True)
    strategy_file = strat_dir / "strategy.py"
    strategy_file.write_text(body)
    return strategy_file


def test_compute_dir_hash_is_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    path_a = _write_strategy(tmp_path / "a")
    path_b = _write_strategy(tmp_path / "b")
    assert compute_strategy_dir_hash(path_a.parent) == compute_strategy_dir_hash(path_b.parent)

    tampered = _write_strategy(tmp_path / "c", body=_STRATEGY_SRC + "\n# tampered\n")
    assert compute_strategy_dir_hash(tampered.parent) != compute_strategy_dir_hash(path_a.parent)


def test_hash_mismatch_rejected(tmp_path: Path) -> None:
    # Failure-mode contract: expected != actual -> CodeHashMismatch, no import.
    strategy_file = _write_strategy(tmp_path)
    with pytest.raises(CodeHashMismatch):
        load_strategy_class(strategy_file, expected_code_hash="deadbeef" * 8)


def test_matching_hash_loads_class(tmp_path: Path) -> None:
    strategy_file = _write_strategy(tmp_path)
    good_hash = compute_strategy_dir_hash(strategy_file.parent)
    cls = load_strategy_class(strategy_file, expected_code_hash=good_hash)
    assert cls.__name__ == "DemoStrategy"
    assert cls(marker="x").marker == "x"


def test_sandbox_hash_none_skips_check_but_audits(tmp_path: Path) -> None:
    strategy_file = _write_strategy(tmp_path)
    with structlog.testing.capture_logs() as logs:
        cls = load_strategy_class(strategy_file, expected_code_hash=None)
    assert cls.__name__ == "DemoStrategy"
    assert "code_hash_skipped_sandbox" in [entry.get("event") for entry in logs]


def test_strategy_path_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_strategy_class(tmp_path / "missing" / "strategy.py", expected_code_hash=None)


def test_explicit_strategy_class_attribute_wins(tmp_path: Path) -> None:
    body = (
        "class HelperStrategy:\n    pass\n\n"
        "class RealStrategy:\n    pass\n\n"
        "STRATEGY_CLASS = RealStrategy\n"
    )
    strategy_file = _write_strategy(tmp_path, body=body)
    cls = load_strategy_class(strategy_file, expected_code_hash=None)
    assert cls.__name__ == "RealStrategy"
