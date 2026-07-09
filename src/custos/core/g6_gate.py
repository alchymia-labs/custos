"""G6 host gate — four-layer live deployment guard.

A live deployment must clear every layer or it is refused.  Non-live modes
(paper / sandbox / testnet) pass through without checks.

Layers:
  1. Host declares ``supports_live()``  (NoopHost → False → refuse)
  2. Host declares ``supports_venue(connector)``
  3. Spec pins ``code_hash`` matching the local strategy directory
  4. Credential ``permission_scope`` is ``trade_no_withdraw``

Each layer has a relaxed-double test proving it is a live guard, not a
dead branch.  Case-insensitive ``trading_mode`` comparison handles both
Python ``"live"`` and Rust serde PascalCase ``"Live"`` wire values.
"""

from __future__ import annotations

from pathlib import Path

from custos.core.log import get_logger
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

_log = get_logger("custos.g6_gate")

_LIVE_SAFE_SCOPE = "trade_no_withdraw"


def check_g6_gate(host: object, spec: dict, credential: dict | None) -> None:
    """Run all four G6 gate layers for a deployment spec.

    Only ``live`` mode triggers the checks.  Layer 4 (credential scope) is
    skipped when ``credential`` is None (reconfigure path — scope was
    verified at deploy time).
    """
    mode = str(spec.get("trading_mode") or "").lower()
    if mode != "live":
        return
    _g6_require_live_capable_host(host, spec)
    _g6_require_supported_venue(host, spec)
    _g6_require_code_hash_match(spec)
    if credential is not None:
        _g6_require_safe_credential_scope(credential, spec)


def _host_capability(host: object, method: str, *args: object) -> bool:
    """Query a host capability method, treating an undeclared one as False.

    Shipped hosts implement the capability contract explicitly; this fallback
    converts a missing method into a fail-safe structured rejection instead of
    an ``AttributeError``.
    """
    fn = getattr(host, method, None)
    return bool(fn(*args)) if callable(fn) else False


def _g6_require_live_capable_host(host: object, spec: dict) -> None:
    if not _host_capability(host, "supports_live"):
        _log.error(
            "g6_gate_live_capability_denied",
            spec_id=spec.get("spec_id"),
            trading_mode=spec.get("trading_mode"),
            host=type(host).__name__,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} requests live but host "
            f"{type(host).__name__} does not declare live capability"
        )


def _g6_require_supported_venue(host: object, spec: dict) -> None:
    venue = spec.get("connector")
    if not _host_capability(host, "supports_venue", str(venue)):
        _log.error(
            "g6_gate_venue_unsupported",
            spec_id=spec.get("spec_id"),
            venue=venue,
            host=type(host).__name__,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} venue {venue!r} not supported "
            f"by host {type(host).__name__}"
        )


def _g6_require_code_hash_match(spec: dict) -> None:
    code_hash = spec.get("code_hash")
    if not code_hash:
        _log.error("g6_gate_code_hash_mismatch", spec_id=spec.get("spec_id"), reason="missing")
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} live deploy requires a pinned "
            "code_hash (none provided)"
        )
    strategy_path = spec.get("strategy_path")
    if not strategy_path:
        _log.error(
            "g6_gate_code_hash_mismatch",
            spec_id=spec.get("spec_id"),
            reason="missing_strategy_path",
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} live deploy has a code_hash but no "
            "strategy_path to verify it against"
        )
    actual = compute_strategy_dir_hash(Path(strategy_path).parent)
    if actual != code_hash:
        _log.error(
            "g6_gate_code_hash_mismatch",
            spec_id=spec.get("spec_id"),
            reason="mismatch",
            expected_prefix=str(code_hash)[:12],
            actual_prefix=actual[:12],
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} code_hash mismatch "
            f"(expected {str(code_hash)[:12]}…, got {actual[:12]}…)"
        )


def _g6_require_safe_credential_scope(credential: dict, spec: dict) -> None:
    scope = credential.get("permission_scope")
    if scope != _LIVE_SAFE_SCOPE:
        _log.error(
            "g6_gate_credential_scope_violation",
            spec_id=spec.get("spec_id"),
            got_scope=scope,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} credential scope {scope!r} is not "
            f"{_LIVE_SAFE_SCOPE!r}"
        )
