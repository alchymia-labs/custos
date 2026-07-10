"""Runner entry point — minimal heartbeat loop.

Designed as a fallback heartbeat publisher: a standalone process driver that
publishes heartbeats on a fixed interval until SIGINT / SIGTERM. Once the
telemetry actor lands, heartbeats ride the telemetry channel and this loop
is retired in favour of the actor's lifecycle.

Run with ``python -m custos --tenant-id acme --runner-id runner-7``.
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

from custos.core.credential_vault import CredentialVault, SopsAgeVault
from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.enrollment import EnrollmentClient
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.nats_client import ArxNatsClient
from custos.core.zombie_watchdog import ZombieWatchdog
from custos.engines.nautilus.risk import make_runner_cap_reject_publisher

log = logging.getLogger("custos")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="custos")
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
        default=Path.home() / ".custos" / "enrollment.json",
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
    parser.add_argument(
        "--use-nt-host",
        action="store_true",
        help="Use the real NautilusTrader host (needs the nautilus extra) "
        "instead of the NoopHost stub. Required to run sandbox / testnet / live "
        "execution; the G6 gate still guards every live deploy.",
    )
    parser.add_argument(
        "--engine",
        default="nautilus",
        help="Execution engine to use (default: nautilus). "
        "Unknown engines are rejected with a clear error.",
    )
    return parser.parse_args(argv)


async def _heartbeat_loop(client: ArxNatsClient, interval: float, stop: asyncio.Event) -> None:
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
        except TimeoutError:
            continue


def _build_vault(args: argparse.Namespace) -> CredentialVault:
    """Pick a vault implementation based on CLI args. sops/age 双参数齐全
    → SopsAgeVault; 否则 MockVault (dev/paper) — fail-fast 不静默降级:
    若只指定 sops_file 或只指定 age_key_file, 必报错 (CLAUDE.md 红线:
    'Key/策略逻辑只在 runner 本地' + 半配置 → 拒)。"""
    if args.sops_file is None and args.age_key_file is None:
        return CredentialVault(tenant_id=args.tenant_id, initiator=args.runner_id)
    if args.sops_file is None or args.age_key_file is None:
        raise SystemExit("sops/age 必须同时指定 --sops-file + --age-key-file (半配置拒绝)")
    return SopsAgeVault(
        sops_file=args.sops_file,
        age_key_file=args.age_key_file,
        tenant_id=args.tenant_id,
        initiator=args.runner_id,
    )


_AVAILABLE_ENGINES = {"nautilus"}


def _build_host(args: argparse.Namespace, client: ArxNatsClient | None = None):
    """Pick the execution engine host based on ``--engine`` (and legacy ``--use-nt-host``).

    Default ``NoopHost`` (paper / dev); ``--use-nt-host`` or ``--engine nautilus``
    selects the real ``NtTradingNodeHost``.  Unknown engine names are rejected
    with a clear error rather than a crash.

    The G6 gate still guards every live deploy regardless of engine choice.
    """
    engine = getattr(args, "engine", "nautilus")
    if engine not in _AVAILABLE_ENGINES:
        raise SystemExit(
            f"engine {engine!r} is not available "
            f"(available: {', '.join(sorted(_AVAILABLE_ENGINES))})"
        )
    if args.use_nt_host or engine == "nautilus":
        if args.use_nt_host:
            from custos.engines.nautilus.host import NtTradingNodeHost

            return NtTradingNodeHost(
                telemetry_client=client,
                tenant_id=args.tenant_id,
                runner_id=args.runner_id,
            )
    from custos.engines.nautilus.host import NoopHost

    return NoopHost()


def _build_reconciler(
    args: argparse.Namespace,
    client: ArxNatsClient,
    host: object,
    vault: CredentialVault,
) -> DeploymentReconciler:
    """Compose the reconciler with the three local guards wired in (red line 0.3
    runtime wire). The cap / breaker configs start at their conservative floors;
    a per-spec refresh from each spec's risk_config is a follow-up. The cap's
    per-order enforcement lives at the trade path; the breaker + watchdog run on
    the reconcile loop tick."""
    runner_cap = RunnerNotionalCap(
        LocalCapConfig.from_spec({}, live=False),
        reject_publisher=make_runner_cap_reject_publisher(
            client=client, tenant_id=args.tenant_id, runner_id=args.runner_id
        ),
    )
    fallback_breaker = FallbackBreaker(FallbackBreakerConfig.from_spec({}))
    zombie_watchdog = ZombieWatchdog()
    return DeploymentReconciler(
        nats_client=client,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        execution_engine=host,  # type: ignore[arg-type]
        credential_vault=vault,
        local_cap=runner_cap,
        fallback_breaker=fallback_breaker,
        zombie_watchdog=zombie_watchdog,
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
            # Default NoopHost (paper / dev) declares supports_live()=False, so the
            # G6 gate refuses it on live; --use-nt-host selects the real
            # NtTradingNodeHost to actually run sandbox / testnet / live execution.
            # The real NT host wires the telemetry + pre-trade reject bridges to
            # each deployment's MessageBus inside deploy() (that is where the bus
            # exists); the NoopHost path has no MessageBus and no bridges.
            reconciler = _build_reconciler(args, client, _build_host(args, client), vault)
            tasks.append(
                asyncio.create_task(
                    reconciler.reconcile_loop(stop, args.reconcile_strategy_id),
                    name="arx-deployment-reconciler",
                )
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
