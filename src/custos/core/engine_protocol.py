"""Engine-agnostic execution protocol.

All engine hosts (nautilus / hummingbot / freqtrade / athanor / nt-rust) must
implement ``ExecutionEngineProtocol``.  The G6 gate and the deployment
reconciler operate exclusively through this interface so they remain
engine-agnostic.

``supports_live`` / ``supports_venue`` are synchronous capability queries the
G6 gate calls before any async work; a host declares up-front whether it can
handle live execution and which venues it wires.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    """Tier-1 engine contract.  Required methods that every host must provide.

    Tier-2 extensions (status snapshots, risk queries, position flattening)
    are documented in ``docs/design/engine_protocol.md`` and owned by
    downstream plans that add them together with their implementations.
    """

    async def deploy(self, spec: dict, credential: dict) -> str: ...

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool: ...

    def supports_venue(self, venue: str) -> bool: ...
