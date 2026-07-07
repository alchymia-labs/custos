"""Runner entry-point host selection.

The reconciler binds a single NautilusHost at construction. The default is the
NoopHost stub (paper / dev); passing --use-nt-host selects the real
NtTradingNodeHost so sandbox / testnet / live execution can actually run. The G6
gate still guards every live deploy regardless of which host is selected —
--use-nt-host enables the real execution path, it does not bypass the gate. When
the nt-runtime extra is absent, the real host fails fast on deploy.
"""

from __future__ import annotations

import pytest

from arx_runner import nautilus_host
from arx_runner.__main__ import _build_host, _parse_args


def test_build_host_defaults_to_noop() -> None:
    args = _parse_args(["--tenant-id", "acme", "--runner-id", "r-1"])
    assert type(_build_host(args)).__name__ == "NoopHost"


def test_build_host_nt_when_flagged() -> None:
    args = _parse_args(["--tenant-id", "acme", "--runner-id", "r-1", "--use-nt-host"])
    assert type(_build_host(args)).__name__ == "NtTradingNodeHost"


@pytest.mark.asyncio
async def test_build_host_nt_without_runtime_fails_fast(monkeypatch) -> None:
    # --use-nt-host selects the real host; if nt-runtime is absent it must fail
    # fast on deploy rather than silently doing nothing (no stub fallback).
    monkeypatch.setattr(nautilus_host, "TradingNode", None)
    args = _parse_args(["--tenant-id", "acme", "--runner-id", "r-1", "--use-nt-host"])
    host = _build_host(args)
    with pytest.raises(RuntimeError, match="nt-runtime"):
        await host.deploy({"spec_id": "x"}, {})
