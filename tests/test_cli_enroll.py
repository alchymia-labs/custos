"""Failing-first tests for ``arx-runner enroll``.

Mocks ``urllib.request.urlopen`` for every network call; asserts:
- happy path: 200 → runner.toml written at 0600 with expected fields
- 4xx / 5xx / connection error → no partial write
- boundary validation runs before any urlopen call
- payload shape (`token_hash` + `runner_id` + `agent_version` + `capabilities`)
  matches the backend contract; ``tenant_id`` is NOT sent (backend resolves
  it server-side via token → tenant lookup).
- non-http(s) `--backend` scheme rejected before urlopen
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import pytest

from custos.cli.subcommands import main
from custos.core.runner_toml import RunnerToml

_BACKEND = "http://team-server:8000"


def _fake_response(payload: dict, status: int = 200) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _happy_response() -> mock.MagicMock:
    return _fake_response(
        {"long_term_credential": "lt-abc", "enrolled_at_ns": 1_700_000_000_000_000_000}
    )


def _run_enroll(argv: list[str], *, monkeypatch, urlopen) -> int:
    monkeypatch.setattr("custos.cli.subcommands.enroll.urllib.request.urlopen", urlopen)
    return main(["enroll", *argv])


def _base_argv(runner_toml: Path, token: str = "one-shot-token") -> list[str]:
    return [
        "--token",
        token,
        "--backend",
        _BACKEND,
        "--tenant-id",
        "acme",
        "--runner-id",
        "runner-7",
        "--runner-toml",
        str(runner_toml),
    ]


def test_enroll_happy_path_persists_runner_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    exit_code = _run_enroll(_base_argv(runner_toml), monkeypatch=monkeypatch, urlopen=urlopen)
    assert exit_code == 0
    loaded = RunnerToml.read(runner_toml)
    assert loaded.tenant_id == "acme"
    assert loaded.runner_id == "runner-7"
    assert loaded.backend_url == _BACKEND
    assert loaded.long_term_credential == "lt-abc"
    assert loaded.enrolled_at_ns == 1_700_000_000_000_000_000
    import os
    import stat

    assert stat.S_IMODE(os.stat(runner_toml).st_mode) == 0o600


def test_enroll_backend_unreachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(side_effect=URLError("connection refused"))
    exit_code = _run_enroll(_base_argv(runner_toml), monkeypatch=monkeypatch, urlopen=urlopen)
    assert exit_code != 0
    assert not runner_toml.exists()
    assert "connection" in capsys.readouterr().err.lower()


def test_enroll_backend_500_no_partial_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    err = HTTPError(_BACKEND, 500, "Internal Server Error", hdrs=None, fp=io.BytesIO(b""))
    urlopen = mock.MagicMock(side_effect=err)
    exit_code = _run_enroll(_base_argv(runner_toml), monkeypatch=monkeypatch, urlopen=urlopen)
    assert exit_code != 0
    assert not runner_toml.exists()


def test_enroll_double_use_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    err = HTTPError(_BACKEND, 409, "Conflict", hdrs=None, fp=io.BytesIO(b"token already used"))
    urlopen = mock.MagicMock(side_effect=err)
    exit_code = _run_enroll(_base_argv(runner_toml), monkeypatch=monkeypatch, urlopen=urlopen)
    assert exit_code != 0
    assert not runner_toml.exists()
    assert "token already used" in capsys.readouterr().err


def test_enroll_creates_arx_dir_at_0700(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    assert not runner_toml.parent.exists()
    urlopen = mock.MagicMock(return_value=_happy_response())
    _run_enroll(_base_argv(runner_toml), monkeypatch=monkeypatch, urlopen=urlopen)
    import os
    import stat

    assert stat.S_IMODE(os.stat(runner_toml.parent).st_mode) == 0o700


def test_enroll_rejects_token_with_null_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    argv = _base_argv(runner_toml, token="abc\x00def")
    with pytest.raises(SystemExit):
        _run_enroll(argv, monkeypatch=monkeypatch, urlopen=urlopen)
    assert not runner_toml.exists()
    urlopen.assert_not_called()


def test_enroll_rejects_tenant_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    argv = [
        "--token",
        "abc",
        "--backend",
        _BACKEND,
        "--tenant-id",
        "../evil",
        "--runner-id",
        "runner-7",
        "--runner-toml",
        str(runner_toml),
    ]
    with pytest.raises(SystemExit):
        _run_enroll(argv, monkeypatch=monkeypatch, urlopen=urlopen)
    urlopen.assert_not_called()


@pytest.mark.parametrize(
    "bad_backend",
    ["file:///etc/passwd", "gopher://x", "foo"],
)
def test_enroll_rejects_non_http_backend(
    bad_backend: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    argv = [
        "--token",
        "abc",
        "--backend",
        bad_backend,
        "--tenant-id",
        "acme",
        "--runner-id",
        "runner-7",
        "--runner-toml",
        str(runner_toml),
    ]
    with pytest.raises(SystemExit):
        _run_enroll(argv, monkeypatch=monkeypatch, urlopen=urlopen)
    urlopen.assert_not_called()
    assert not runner_toml.exists()


def test_enroll_payload_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    argv = _base_argv(runner_toml)
    argv.extend(["--agent-version", "0.2.0"])
    argv.extend(["--capabilities", "nautilus"])
    argv.extend(["--capabilities", "noop-host"])
    exit_code = _run_enroll(argv, monkeypatch=monkeypatch, urlopen=urlopen)
    assert exit_code == 0
    call = urlopen.call_args
    request = call.args[0]
    payload = json.loads(request.data)
    expected_hash = hashlib.sha256(b"one-shot-token").hexdigest()
    assert payload == {
        "token_hash": expected_hash,
        "runner_id": "runner-7",
        "agent_version": "0.2.0",
        "capabilities": ["nautilus", "noop-host"],
    }
    assert "tenant_id" not in payload, "backend resolves tenant server-side via token_hash"
    assert request.get_header("Content-type") == "application/json"
    assert request.full_url == f"{_BACKEND}/api/v1/enrollments"


def test_enroll_never_logs_raw_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner_toml = tmp_path / "arx" / "runner.toml"
    urlopen = mock.MagicMock(return_value=_happy_response())
    with caplog.at_level("DEBUG"):
        _run_enroll(
            _base_argv(runner_toml, token="super-secret-token"),
            monkeypatch=monkeypatch,
            urlopen=urlopen,
        )
    for record in caplog.records:
        assert "super-secret-token" not in record.getMessage()
