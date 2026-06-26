"""Runner entry point — minimal heartbeat loop.

Designed as a fallback heartbeat publisher: a standalone process driver that
publishes heartbeats on a fixed interval until SIGINT / SIGTERM. Once the
telemetry actor lands, heartbeats ride the telemetry channel and this loop
is retired in favour of the actor's lifecycle.

Run with ``python -m arx_runner --tenant-id acme --runner-id runner-7``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import uuid

from arx_runner.nats_client import ArxNatsClient

log = logging.getLogger("arx_runner")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="arx-runner")
    parser.add_argument("--nats-url", default="nats://localhost:4222")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--runner-id", required=True)
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=10.0,
        help="seconds between heartbeats",
    )
    return parser.parse_args(argv)


async def _heartbeat_loop(
    client: ArxNatsClient, interval: float, stop: asyncio.Event
) -> None:
    session_id = str(uuid.uuid4())
    seq = 0
    while not stop.is_set():
        try:
            await client.publish_heartbeat(health="ok", seq=seq, session_id=session_id)
        except Exception as exc:  # noqa: BLE001 — heartbeat loop must survive transient publish errors
            log.warning("heartbeat_publish_failed", extra={"error": str(exc), "seq": seq})
        seq += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = ArxNatsClient(
        nats_url=args.nats_url,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
    )
    await client.connect()
    log.info("runner_started", extra={"tenant_id": args.tenant_id, "runner_id": args.runner_id})

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await _heartbeat_loop(client, args.heartbeat_interval, stop)
    finally:
        await client.close()
        log.info("runner_stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
