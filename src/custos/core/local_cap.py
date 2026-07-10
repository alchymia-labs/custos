"""Runner-level notional cap — the disconnect-resilient soft limit.

A structural ceiling on the total open notional a single runner may hold. It
rejects *new* orders that would push the runner past the cap; it never touches
existing positions (that is the fallback breaker's job). The decision is made
locally from the runner's own open-notional view, so it keeps enforcing while
the cloud control plane is unreachable (the disconnect-resilient red line): a
cloud reject notification is best-effort, but the local reject holds regardless.

Money is ``Decimal`` end to end (red line 0.4). The cap value comes from the
cloud ``DeploymentSpec.risk_config`` when present; absent that, a conservative
per-mode floor applies so a missing config can never mean "no cap".
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from custos.core.log import get_logger

_log = get_logger("custos.local_cap")

# Conservative structural floors used when the cloud spec carries no explicit
# per-runner cap (first boot before a spec pull, or a spec that omits the
# field). Paper stays tiny; live is capped low until an operator raises it via
# risk_config. These are fail-safe defaults, not recommended live limits.
PAPER_CAP_FLOOR_USD = Decimal("200")
LIVE_CAP_FLOOR_USD = Decimal("1000")

# Called on a cap breach to notify the cloud (symbol, current_open, requested,
# cap). Best-effort — a failure is logged and swallowed so the local reject
# still stands during a disconnect.
RejectPublisher = Callable[[str, Decimal, Decimal, Decimal], Awaitable[None]]


@dataclass(frozen=True)
class LocalCapConfig:
    """Resolved per-runner notional cap. ``max_notional_per_runner`` is the
    total open-notional ceiling in the runner's quote currency."""

    max_notional_per_runner: Decimal

    @classmethod
    def from_spec(cls, spec: dict, *, live: bool) -> LocalCapConfig:
        """Resolve the cap from a ``DeploymentSpec`` dict. Uses
        ``risk_config.max_notional_per_runner`` when present (cloud authority),
        else the conservative per-mode floor. Parsed via ``Decimal(str(...))``
        so no float ever reaches the value (red line 0.4)."""
        raw = spec.get("risk_config", {}).get("max_notional_per_runner")
        if raw is not None:
            return cls(max_notional_per_runner=Decimal(str(raw)))
        return cls(max_notional_per_runner=LIVE_CAP_FLOOR_USD if live else PAPER_CAP_FLOOR_USD)


def check_cap(
    current_open: Decimal,
    new_order_notional: Decimal,
    config: LocalCapConfig,
) -> bool:
    """True if adding ``new_order_notional`` keeps total open notional within
    the cap; False if it would breach."""
    return current_open + new_order_notional <= config.max_notional_per_runner


class RunnerNotionalCap:
    """Pre-trade guard enforcing the runner notional cap.

    ``allows`` is the enforcement point: it returns whether a proposed order may
    proceed. On a breach it emits a structured ``runner_cap_exceeded`` event and
    best-effort notifies the cloud via ``reject_publisher``; the local reject is
    returned regardless of whether that notification succeeds, so the cap keeps
    protecting the runner while disconnected.
    """

    def __init__(
        self,
        config: LocalCapConfig,
        *,
        reject_publisher: RejectPublisher | None = None,
    ) -> None:
        self._config = config
        self._reject_publisher = reject_publisher

    @property
    def config(self) -> LocalCapConfig:
        return self._config

    def apply_config(self, new_config: LocalCapConfig) -> bool:
        """Swap the enforced config. Returns True when the value actually
        changed so callers can emit a single structured event per change.

        The reconciler calls this on each accepted spec so cloud-side
        ``risk_config`` edits take effect on the next loop (docs/domain.md
        L104), without silently drifting from what the operator set."""
        if new_config == self._config:
            return False
        self._config = new_config
        return True

    async def allows(
        self,
        *,
        symbol: str,
        current_open: Decimal,
        new_order_notional: Decimal,
    ) -> bool:
        if check_cap(current_open, new_order_notional, self._config):
            return True
        _log.warning(
            "runner_cap_exceeded",
            symbol=symbol,
            current_open=str(current_open),
            requested_notional=str(new_order_notional),
            cap=str(self._config.max_notional_per_runner),
        )
        if self._reject_publisher is not None:
            try:
                await self._reject_publisher(
                    symbol,
                    current_open,
                    new_order_notional,
                    self._config.max_notional_per_runner,
                )
            except Exception as exc:  # noqa: BLE001 — cloud notify best-effort; local reject holds (red line 0.3)
                _log.warning("runner_cap_reject_publish_failed", symbol=symbol, error=str(exc))
        return False
