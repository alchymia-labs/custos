"""Generate wire-shape fixtures for cross-language pinning (WR-NATS-3).

Each fixture is a real producer-side byte string emitted by the runner
code path that the Rust consumer eventually parses. Fixtures land in
``backend/crates/telemetry/tests/wire_shapes/`` so the Rust integration
test can decode them with ``serde_json::from_slice``.

Stable inputs (fixed event_id / session_id / occurred_at) make the
fixtures git-stable; only producer-side schema drift will move them.
"""

from __future__ import annotations

from pathlib import Path

from arx_runner.nats_client import NatsEnvelope, OrderingMeta

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "backend" / "crates" / "telemetry" / "tests" / "wire_shapes"


def _stable_envelope(payload: dict, *, with_ordering: bool) -> bytes:
    """Build a stable envelope — event_id / occurred_at / session_id
    are pinned so fixture bytes don't drift commit-to-commit."""
    ordering = (
        OrderingMeta(
            session_id="01900000-0000-7000-8000-000000000001",
            seq=42,
        )
        if with_ordering
        else None
    )
    env = NatsEnvelope(
        event_id="01900000-0000-7000-8000-000000000abc",
        tenant_id="acme",
        occurred_at="2026-06-26T10:00:00.000000000Z",
        payload=payload,
        ordering=ordering,
    )
    return env.to_bytes()


def write_fixture(name: str, payload: dict, *, with_ordering: bool) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = FIXTURE_DIR / f"{name}.json"
    target.write_bytes(_stable_envelope(payload, with_ordering=with_ordering))


def main() -> None:
    write_fixture(
        "heartbeat",
        payload={
            "runner_id": "r-001",
            "uptime_secs": 3600,
            "active_deployments": 2,
            "health": "online",
        },
        with_ordering=True,
    )
    write_fixture(
        "telemetry_snapshot",
        payload={
            "runner_id": "r-001",
            "session_id": "01900000-0000-7000-8000-000000000001",
            "seq": 42,
            "equity": "12345.67891234",
            "equity_currency": "Usd",
            "health": "online",
            "positions": [
                {
                    "symbol": "BTC-USDT",
                    "side": "long",
                    "qty": "0.5",
                    "unrealized_pnl": "-12.34",
                }
            ],
            "orders": [
                {
                    "client_order_id": "c-001",
                    "status": "filled",
                    "filled_qty": "0.25",
                }
            ],
            "original_precision": "Nanosecond",
        },
        with_ordering=True,
    )
    write_fixture(
        "recon_result",
        payload={
            "dimension": "balance",
            "domain": "cex",
            "source_amount": "100.00000000",
            "source_currency": "USD",
            "source_as_of": "2026-06-26T10:00:00.000000Z",
            "target_amount": "110.00000000",
            "target_currency": "USD",
            "target_as_of": "2026-06-26T10:00:00.000000Z",
            "tolerance": "0.05",
            "in_flight_count": 0,
            "deployment_spec_id": "00000000-0000-0000-0000-000000000000",
            "scope": "account-1",
        },
        with_ordering=True,
    )
    print(f"Wrote fixtures to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
