"""Post-parse daemon runtime — reconciler + snapshot publisher + heartbeat.

Extracted from the legacy flat CLI ``_run`` coroutine so both the
``arx-runner start`` subcommand and any future embedding call site can
enter the runtime by handing in a compatible ``argparse.Namespace``.

The composition is verbatim from the pre-Plan-11 loop: NATS connect,
optional enrollment publish, optional reconciler + snapshot publisher +
runtime vault, and a heartbeat task; cancels tasks on stop and closes
the client cleanly. The only substantive change vs. the legacy body is
that ``_build_vault`` now returns a ``PerKeyVault`` unconditionally —
the deleted ``SopsAgeVault`` (multi-credential JSON) has no replacement
runtime read path, and ``MockVault`` is intentionally kept out of the
runtime graph (dev/paper users must run ``arx-runner vault put`` before
``arx-runner start``).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time

import uuid6

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.enrollment import EnrollmentClient
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.nats_client import ArxNatsClient
from custos.core.per_key_vault import PerKeyVault
from custos.core.state_snapshot import StateSnapshotPublisher
from custos.core.zombie_watchdog import ZombieWatchdog
from custos.engines.nautilus.risk import make_runner_cap_reject_publisher

log = logging.getLogger("custos")

_AVAILABLE_ENGINES = {"nautilus"}


def _build_vault(args: argparse.Namespace) -> PerKeyVault:
    """Build the runtime vault reader.

    Always ``PerKeyVault``; no ``MockVault`` runtime fallback. Dev/paper
    users must provision at least one credential via ``arx-runner vault
    put`` before ``arx-runner start`` — the reconciler only ever calls
    ``decrypt`` for a spec that actually references a credential_id, so
    a runner that never runs a live spec never opens the vault.
    """
    return PerKeyVault(
        vault_dir=args.vault_dir,
        tenant_id=args.tenant_id,
        initiator=args.runner_id,
    )


def _build_host(args: argparse.Namespace, client: ArxNatsClient | None = None):
    """Pick the execution engine host based on ``--engine`` / ``--use-nt-host``.

    Default ``NoopHost`` (paper / dev); ``--use-nt-host`` or ``--engine
    nautilus`` selects the real ``NtTradingNodeHost``. Unknown engine
    names are rejected with a clear error rather than a crash. The G6
    gate still guards every live deploy regardless of engine choice.
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
    vault: PerKeyVault,
) -> DeploymentReconciler:
    """Compose the reconciler with the three local guards wired in (non-custodial
    red line 0.3 runtime wire — cap + breaker + watchdog keep guarding when
    the cloud is unreachable). Cap / breaker configs start at conservative
    floors; per-spec risk_config refresh is a follow-up."""
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


async def _heartbeat_loop(client: ArxNatsClient, interval: float, stop: asyncio.Event) -> None:
    # Time-ordered UUIDv7 so the session boundary is comparable on the
    # consumer side (matches the wire contract's session_id timeordering).
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
                # The fallback heartbeat loop has no NT binding; the
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


async def run_daemon(args: argparse.Namespace) -> int:
    """Start the reconcile / telemetry / heartbeat runtime loop.

    Body is verbatim from the pre-Plan-11 flat CLI ``_run`` coroutine
    aside from the vault selection (see ``_build_vault``).
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # WAL path enables at-least-once state snapshot + reconcile status:
    # messages published while NATS is disconnected are stashed and replayed
    # on the next connect. Ensure the parent directory exists so a fresh
    # runner install doesn't fail on first boot.
    args.wal_path.parent.mkdir(parents=True, exist_ok=True)
    client = ArxNatsClient(
        nats_url=args.nats_url,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        wal_path=args.wal_path,
    )
    await client.connect()
    log.info(
        "runner_started",
        extra={"tenant_id": args.tenant_id, "runner_id": args.runner_id},
    )

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
            # Default NoopHost (paper / dev) declares supports_live()=False so
            # the G6 gate refuses it on live; --use-nt-host selects the real
            # NtTradingNodeHost. The real NT host wires the telemetry + pre-
            # trade reject bridges to each deployment's MessageBus inside
            # deploy() — that is where the bus exists.
            host = _build_host(args, client)
            reconciler = _build_reconciler(args, client, host, vault)
            tasks.append(
                asyncio.create_task(
                    reconciler.reconcile_loop(stop, args.reconcile_strategy_id),
                    name="arx-deployment-reconciler",
                )
            )
            # State snapshot publisher: polls the engine's Tier-2 methods
            # on ``interval_secs`` and publishes one envelope per active
            # spec via the JetStream WAL-backed path. Scheduled once and
            # dynamically iterates the spec ids the reconciler currently
            # holds — no re-spawn needed when specs come and go.
            publisher = StateSnapshotPublisher(
                engine=host,
                nats_client=client,
                tenant_id=args.tenant_id,
                runner_id=args.runner_id,
                interval_secs=args.snapshot_interval_secs,
            )
            tasks.append(
                asyncio.create_task(
                    publisher.run(stop, reconciler.active_spec_ids),
                    name="arx-state-snapshot-publisher",
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
