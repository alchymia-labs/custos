"""Runner runtime host selection.

The reconciler binds a single NautilusHost at construction. The default
is the ``NoopHost`` stub (paper / dev); passing ``--use-nt-host`` selects
the real ``NtTradingNodeHost`` so sandbox / testnet / live execution can
actually run. The G6 gate still guards every live deploy regardless of
which host is selected — ``--use-nt-host`` enables the real execution
path, it does not bypass the gate. When the nautilus extra is absent,
the real host fails fast on deploy.

Post-Plan-11: ``_build_host`` lives in ``custos.cli._daemon`` (the flat
``custos.cli.main`` module was retired). Tests build the ``Namespace``
directly rather than routing through a legacy parser.
"""

from __future__ import annotations

import argparse

import pytest

from custos.cli._daemon import _build_host
from custos.engines.nautilus import host as nautilus_host


def _host_args(*, use_nt_host: bool = False, engine: str = "nautilus") -> argparse.Namespace:
    return argparse.Namespace(
        tenant_id="acme",
        runner_id="r-1",
        use_nt_host=use_nt_host,
        engine=engine,
    )


def test_build_host_defaults_to_noop() -> None:
    assert type(_build_host(_host_args())).__name__ == "NoopHost"


def test_build_host_nt_when_flagged() -> None:
    assert type(_build_host(_host_args(use_nt_host=True))).__name__ == "NtTradingNodeHost"


@pytest.mark.asyncio
async def test_build_host_nt_without_runtime_fails_fast(monkeypatch) -> None:
    # --use-nt-host selects the real host; if nautilus is absent it must fail
    # fast on deploy rather than silently doing nothing (no stub fallback).
    monkeypatch.setattr(nautilus_host, "TradingNode", None)
    host = _build_host(_host_args(use_nt_host=True))
    with pytest.raises(RuntimeError, match="nautilus"):
        await host.deploy({"spec_id": "x"}, {})
