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
import time
from pathlib import Path

import uuid6

from arx_runner.credential_vault import CredentialVault, SopsAgeVault
from arx_runner.deployment_reconciler import DeploymentReconciler
from arx_runner.enrollment import EnrollmentClient
from arx_runner.nats_client import ArxNatsClient
from arx_runner.nt_risk_engine import NtRiskEngineBridge

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
    # Plan 06 — enrollment / reconciler integration (opt-in):
    parser.add_argument(
        "--enrollment-token",
        default=None,
        help="One-shot pairing token (plaintext). Sent as sha256 hash to cloud.",
    )
    parser.add_argument(
        "--enrollment-path",
        type=Path,
        default=Path.home() / ".arx-runner" / "enrollment.json",
        help="Local enrollment record path (0600).",
    )
    parser.add_argument(
        "--sops-file",
        type=Path,
        default=None,
        help="sops-encrypted credentials file path. Required for live mode.",
    )
    parser.add_argument(
        "--age-key-file",
        type=Path,
        default=None,
        help="age private key file path (KEK; never leaves the runner host).",
    )
    parser.add_argument(
        "--reconcile-strategy-id",
        default=None,
        help="Enable deployment reconciler bound to this strategy_id.",
    )
    return parser.parse_args(argv)


async def _heartbeat_loop(
    client: ArxNatsClient, interval: float, stop: asyncio.Event
) -> None:
    # Time-ordered UUIDv7 so the session boundary is comparable on the
    # consumer side (plan-index §6 + lesson on session_id timeordering).
    session_id = str(uuid6.uuid7())
    started_at = time.monotonic()
    seq = 0
    while not stop.is_set():
        try:
            await client.publish_heartbeat(
                health="ok",
                seq=seq,
                session_id=session_id,
                uptime_secs=int(time.monotonic() - started_at),
                # v1 fallback heartbeat loop has no NT binding; the
                # production telemetry actor reports the real count.
                active_deployments=0,
            )
        except Exception as exc:  # noqa: BLE001 — heartbeat loop must survive transient publish errors
            log.warning("heartbeat_publish_failed", extra={"error": str(exc), "seq": seq})
        seq += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


def _build_vault(args: argparse.Namespace) -> CredentialVault:
    """Pick a vault implementation based on CLI args. sops/age 双参数齐全
    → SopsAgeVault; 否则 MockVault (dev/paper) — fail-fast 不静默降级:
    若只指定 sops_file 或只指定 age_key_file, 必报错 (CLAUDE.md 红线:
    'Key/策略逻辑只在 runner 本地' + 半配置 → 拒)。"""
    if args.sops_file is None and args.age_key_file is None:
        return CredentialVault(tenant_id=args.tenant_id, initiator=args.runner_id)
    if args.sops_file is None or args.age_key_file is None:
        raise SystemExit(
            "sops/age 必须同时指定 --sops-file + --age-key-file (半配置拒绝)"
        )
    return SopsAgeVault(
        sops_file=args.sops_file,
        age_key_file=args.age_key_file,
        tenant_id=args.tenant_id,
        initiator=args.runner_id,
    )


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

    tasks: list[asyncio.Task] = []
    try:
        # Enrollment (first run): publish hash + persist locally.
        if args.enrollment_token:
            enroll_client = EnrollmentClient(
                nats_client=client,
                tenant_id=args.tenant_id,
                runner_id=args.runner_id,
                enrollment_path=args.enrollment_path,
            )
            await enroll_client.enroll(args.enrollment_token)

        # Deployment reconciler (opt-in via --reconcile-strategy-id).
        if args.reconcile_strategy_id:
            vault = _build_vault(args)
            # nautilus_host stub — paper/dev 用 NoopHost 让 reconciler 跑通流程而不
            # 真起 NT 进程; live mode 由 deployment_reconciler 的 G6 gate 拒绝。真实
            # NT host 由后续 adapter plan 落地后替换。
            from arx_runner.nautilus_host import NoopHost as _NoopHost  # G6 gate uses isinstance

            reconciler = DeploymentReconciler(
                nats_client=client,
                tenant_id=args.tenant_id,
                runner_id=args.runner_id,
                nautilus_host=_NoopHost(),
                credential_vault=vault,
            )
            tasks.append(
                asyncio.create_task(
                    reconciler.reconcile_loop(stop, args.reconcile_strategy_id),
                    name="arx-deployment-reconciler",
                )
            )

            # Single-order pre-trade reject bridge. Constructed alongside the
            # NT host path; it begins forwarding NT `OrderDenied` events once a
            # live NT MessageBus is available. The stub host has no MessageBus,
            # so we record that the bridge is staged and awaiting NT rather than
            # fail-fast on a `None` bus.
            pre_trade_bridge = NtRiskEngineBridge(
                client=client,
                tenant_id=args.tenant_id,
                runner_id=args.runner_id,
            )
            log.info(
                "pre_trade_bridge_pending_nt_messagebus",
                extra={"subject": pre_trade_bridge.subject()},
            )

        tasks.append(
            asyncio.create_task(
                _heartbeat_loop(client, args.heartbeat_interval, stop),
                name="arx-heartbeat",
            )
        )
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await client.close()
        log.info("runner_stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
