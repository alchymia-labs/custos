"""Runner runtime host selection.

The reconciler binds a single host from the clean-break ``--engine`` enum.
``nautilus`` selects the real ``NtTradingNodeHost`` and ``noop`` selects the
explicit contract-test stub. The G6 gate still guards every live deploy.

Post-Plan-11: ``_build_host`` lives in ``custos.cli._daemon`` (the flat
``custos.cli.main`` module was retired). Tests build the ``Namespace``
directly rather than routing through a legacy parser.
"""

from __future__ import annotations

import argparse

import pytest

from custos.cli._daemon import _build_host
from custos.engines.nautilus import host as nautilus_host


def _host_args(*, engine: str = "nautilus") -> argparse.Namespace:
    return argparse.Namespace(
        tenant_id="acme",
        runner_id="r-1",
        engine=engine,
    )


def test_build_host_defaults_to_nautilus() -> None:
    assert type(_build_host(_host_args())).__name__ == "NtTradingNodeHost"


def test_build_host_noop_when_explicit() -> None:
    assert type(_build_host(_host_args(engine="noop"))).__name__ == "NoopHost"


@pytest.mark.asyncio
async def test_build_host_nt_without_runtime_fails_fast(monkeypatch) -> None:
    # The nautilus engine selects the real host; if the runtime is absent it must fail
    # fast on deploy rather than silently doing nothing (no stub fallback).
    monkeypatch.setattr(nautilus_host, "TradingNode", None)
    host = _build_host(_host_args())
    with pytest.raises(RuntimeError, match="nautilus"):
        await host.deploy({"spec_id": "x"}, {})
