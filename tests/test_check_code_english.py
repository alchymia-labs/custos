from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "scripts/check-code-english.py"
TARGET_PATH = (
    "packages/custos-strategy-toolkit-nautilus/src/"
    "custos_toolkit_nautilus/adapter/trading_strategy.py"
)
LEGACY_PATH = "src/custos/engines/nautilus/toolkit/shared/nautilus/trading_strategy.py"
SOURCE_COMMIT = "a" * 40
CJK_LINE = "# " + "\u65e2\u5b58\u5168\u89d2\u6807\u70b9\uff0c"
SOURCE_BYTES = ("from shared import dependency\n" + CJK_LINE + "\n").encode()
TARGET_BYTES = ("from custos_toolkit import dependency\n" + CJK_LINE + "\n").encode()


@pytest.fixture
def checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_code_english", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _manifest(*, legacy_sha: str | None = None, target_sha: str | None = None) -> dict:
    return {
        "source_commit": SOURCE_COMMIT,
        "files": [
            {
                "legacy_path": LEGACY_PATH,
                "legacy_sha256": legacy_sha or _sha256(SOURCE_BYTES),
                "target_path": "custos_toolkit_nautilus/adapter/trading_strategy.py",
                "target_sha256": target_sha or _sha256(TARGET_BYTES),
            }
        ],
    }


def _install_exact_blobs(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    source: bytes = SOURCE_BYTES,
    staged: bytes = TARGET_BYTES,
    current: bytes = TARGET_BYTES,
) -> None:
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)
    target = tmp_path / TARGET_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(current)
    blobs = {
        f"{SOURCE_COMMIT}:{LEGACY_PATH}": source,
        f":{TARGET_PATH}": staged,
    }
    monkeypatch.setattr(checker, "_git_blob", blobs.__getitem__)


def test_main_prints_note_for_exact_manifest_relocation(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_exact_blobs(checker, monkeypatch, tmp_path)
    monkeypatch.setattr(checker, "_staged_target_files", lambda: [TARGET_PATH])
    monkeypatch.setattr(checker, "_staged_added_lines", lambda _path: [(2, CJK_LINE)])
    monkeypatch.setattr(checker, "_load_extraction_manifest", _manifest)

    assert checker.main() == 0
    output = capsys.readouterr().out
    assert "EXEMPT exact relocated file" in output
    assert TARGET_PATH in output
    assert "pre-existing CJK line(s)" in output


@pytest.mark.parametrize(
    ("source", "staged", "current"),
    [
        (SOURCE_BYTES + b"# drift\n", TARGET_BYTES, TARGET_BYTES),
        (SOURCE_BYTES, TARGET_BYTES + b"# drift\n", TARGET_BYTES),
        (SOURCE_BYTES, TARGET_BYTES, TARGET_BYTES + b"# drift\n"),
    ],
)
def test_digest_drift_denies_relocation_exemption(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: bytes,
    staged: bytes,
    current: bytes,
) -> None:
    _install_exact_blobs(
        checker,
        monkeypatch,
        tmp_path,
        source=source,
        staged=staged,
        current=current,
    )

    exempt, note = checker._exact_relocation_exemption(TARGET_PATH, [(2, CJK_LINE)], _manifest())

    assert exempt is False
    assert note is None


def test_unlisted_target_denies_without_reading_git(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        checker,
        "_git_blob",
        lambda _name: pytest.fail("unlisted paths must not read Git blobs"),
    )

    exempt, note = checker._exact_relocation_exemption(
        TARGET_PATH, [(2, CJK_LINE)], {"source_commit": SOURCE_COMMIT, "files": []}
    )

    assert exempt is False
    assert note is None


def test_new_cjk_line_not_present_in_source_blob_is_denied(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_exact_blobs(checker, monkeypatch, tmp_path)

    exempt, note = checker._exact_relocation_exemption(
        TARGET_PATH,
        [(2, "# " + "\u65b0\u589e\u4e2d\u6587\uff01")],
        _manifest(),
    )

    assert exempt is False
    assert note is None
