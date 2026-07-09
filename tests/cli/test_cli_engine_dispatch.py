"""CLI --engine dispatch tests."""

from __future__ import annotations

import pytest

from custos.cli.main import _build_host, _parse_args
from custos.engines.nautilus.host import NoopHost


def test_cli_engine_defaults_to_nautilus() -> None:
    args = _parse_args(["--tenant-id", "t", "--runner-id", "r"])
    assert args.engine == "nautilus"
    host = _build_host(args)
    assert isinstance(host, NoopHost)


def test_cli_engine_unknown_rejected() -> None:
    args = _parse_args(["--tenant-id", "t", "--runner-id", "r", "--engine", "hummingbot"])
    with pytest.raises(SystemExit, match="not available"):
        _build_host(args)
