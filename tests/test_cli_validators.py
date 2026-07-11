"""Failing-first tests for CLI boundary-string validators.

Guards the ``tenant_id`` / ``runner_id`` / ``key-id`` filesystem-boundary
path segment (`~/.arx/vault/<key-id>.enc`) plus the ``--backend`` URL
scheme allowlist (rejects ``file://`` / ``gopher://`` etc before any
``urlopen`` call).
"""

from __future__ import annotations

import argparse

import pytest

from custos.cli.validators import validate_backend_url, validate_id

# ---- validate_id -----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["acme", "runner-7", "tenant_a_1", "a", "a" * 64, "0", "0-1_2"],
)
def test_accepts_valid_id(value: str) -> None:
    assert validate_id("tenant_id", value) == value


@pytest.mark.parametrize(
    "value",
    ["../evil", "./x", "..", ".", "a/../b"],
)
def test_rejects_path_traversal(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", value)


@pytest.mark.parametrize("value", ["tenant\x00", "\x00tenant", "a\x00b"])
def test_rejects_null_byte(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", value)


@pytest.mark.parametrize("code", list(range(0x00, 0x20)) + [0x7F])
def test_rejects_control_chars(code: int) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", f"tenant{chr(code)}")


def test_rejects_oversize() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", "a" * 65)


def test_rejects_empty() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", "")


# Non-ASCII payloads are test data — the validator's contract is to reject them,
# and this file is the canonical enforcement site. noqa: language
@pytest.mark.parametrize(
    "value",
    [
        "tenant-中",  # CJK ideograph  noqa: language
        "tenant​",  # zero-width space
        "tenanté",  # latin-1 accented
    ],
)
def test_rejects_non_ascii(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_id("tenant_id", value)


# ---- validate_backend_url --------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "http://team-server:8000",
        "https://team-server.example/api",
        "https://team-server.example",
        "http://localhost:9000/path",
    ],
)
def test_validate_backend_url_accepts_http_https(value: str) -> None:
    assert validate_backend_url(value) == value


def test_validate_backend_url_rejects_file_scheme() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="scheme"):
        validate_backend_url("file:///etc/passwd")


def test_validate_backend_url_rejects_gopher_scheme() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="scheme"):
        validate_backend_url("gopher://evil.example")


def test_validate_backend_url_rejects_bare_hostname() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_backend_url("team-server")


def test_validate_backend_url_rejects_empty_netloc() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="host"):
        validate_backend_url("http://")


def test_validate_backend_url_rejects_userinfo() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="userinfo"):
        validate_backend_url("http://user:pass@team-server")


def test_validate_backend_url_rejects_fragment() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="fragment"):
        validate_backend_url("http://team-server#frag")
