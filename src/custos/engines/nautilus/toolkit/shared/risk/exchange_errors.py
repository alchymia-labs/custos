"""Exchange order-rejection classification (plan 13).

Platform-neutral pure logic: classifies an order-rejection reason string into a
backoff tier so the strategy can react differently to transient server/rate-limit
errors vs. business-logic rejections.

- ``"server"``: gateway/timeout/rate-limit errors (5xx, -1007, -1003, -1015, ...).
  These mean the venue couldn't process the request; the right reaction is a long
  backoff / circuit-break, and NOT hammering the endpoint (which burns order quota).
- ``"logic"``: business rejections (e.g. -2022 ReduceOnly rejected, -2019 margin).
  These are deterministic; a short backoff (after clearing the blocking condition)
  is appropriate.

Kept under ``shared/risk`` (no nautilus/msgspec deps) so it is unit-testable in any
environment, per the platform-neutral module rules.
"""

from __future__ import annotations

# Substrings (lower-cased) that mark a transient server-side / rate-limit error.
# Binance numeric codes are matched as substrings of the reason payload string.
_SERVER_ERROR_MARKERS: tuple[str, ...] = (
    "-1000",  # UNKNOWN — internal error
    "-1001",  # DISCONNECTED — internal disconnect
    "-1003",  # TOO_MANY_REQUESTS — rate limited
    "-1007",  # TIMEOUT — backend timeout, execution status unknown
    "-1015",  # TOO_MANY_ORDERS — order rate limited
    "-1016",  # SERVICE_SHUTTING_DOWN
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "timeout",
    "too many",
    "<!doctype",
    "<html",
)


def classify_rejection_reason(reason: str | None) -> str:
    """Classify an order-rejection reason into a backoff tier.

    Returns ``"server"`` for transient gateway/timeout/rate-limit errors that
    warrant a long backoff / circuit-break, otherwise ``"logic"`` (the safe
    default for deterministic business rejections and unrecognized reasons).
    """
    if not reason:
        return "logic"
    lowered = reason.lower()
    if any(marker in lowered for marker in _SERVER_ERROR_MARKERS):
        return "server"
    return "logic"
