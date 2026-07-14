"""Post-parse daemon runtime — reconciler + snapshot publisher + heartbeat.

Extracted from the legacy flat CLI ``_run`` coroutine so both the
``arx-runner start`` subcommand and any future embedding call site can
enter the runtime by handing in a compatible ``argparse.Namespace``.

Startup verifies the age-encrypted machine principal against Crucible
authority before connecting NATS.  Missing, expired, revoked, or mismatched
authority therefore cannot leave a stale ready file or start execution.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import signal
from uuid import UUID

from custos.contracts import CrucibleDomainEventVerifier
from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.machine_credential_vault import (
    MachineCredentialError,
    MachineCredentialHttpClient,
    MachineCredentialRejectedError,
    MachineCredentialTransportError,
    MachineCredentialVault,
)
from custos.core.nats_client import CrucibleNatsClient
from custos.core.per_key_vault import PerKeyVault
from custos.core.readiness import ReadinessFile
from custos.core.runner_deployment_lifecycle_fact import RunnerDeploymentLifecycleFactEmitter
from custos.core.runner_fact import (
    RunnerCapabilityReceipt,
    RunnerFactEmitter,
    RunnerFactIdentity,
    RunnerFactJetStreamPublisher,
    RunnerFactOutbox,
)
from custos.core.runner_fact_producer import RunnerFactProductionLoop
from custos.core.runner_toml import RunnerToml
from custos.core.runtime_log_fact import RunnerRuntimeLogEmitter, RuntimeLogRedactor
from custos.core.zombie_watchdog import ZombieWatchdog

log = logging.getLogger("custos")

_AVAILABLE_ENGINES = {"nautilus", "noop"}


async def _watch_machine_authority(
    stop: asyncio.Event,
    *,
    backend_url: str,
    machine_credential: object,
    local_check_secs: float = 1.0,
    remote_check_secs: float = 30.0,
) -> None:
    """Stop on explicit invalidation while tolerating transport outages."""
    authority = MachineCredentialHttpClient(backend_url, machine_credential)  # type: ignore[arg-type]
    elapsed = 0.0
    while not stop.is_set():
        try:
            machine_credential.assert_active()  # type: ignore[attr-defined]
        except MachineCredentialError as exc:
            log.error(
                "machine_authority_invalidated",
                extra={"error_type": type(exc).__name__},
            )
            stop.set()
            return
        elapsed += local_check_secs
        if elapsed >= remote_check_secs:
            elapsed = 0.0
            try:
                await asyncio.to_thread(authority.verify_active)
            except MachineCredentialTransportError as exc:
                log.warning(
                    "machine_authority_check_unavailable",
                    extra={"error_type": type(exc).__name__},
                )
            except (MachineCredentialRejectedError, MachineCredentialError) as exc:
                log.error(
                    "machine_authority_rejected",
                    extra={"error_type": type(exc).__name__},
                )
                stop.set()
                return
        try:
            await asyncio.wait_for(stop.wait(), timeout=local_check_secs)
        except TimeoutError:
            pass


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


def _build_host(
    args: argparse.Namespace,
    *,
    fact_emitter: RunnerFactEmitter | None = None,
    capability_receipt: RunnerCapabilityReceipt | None = None,
):
    """Pick the execution engine host from the clean-break ``--engine`` enum.

    ``nautilus`` selects the real ``NtTradingNodeHost`` and ``noop`` selects
    the explicit contract-test stub. The G6 gate still guards every live
    deploy regardless of engine choice.
    """
    engine = getattr(args, "engine", "nautilus")
    if engine not in _AVAILABLE_ENGINES:
        raise SystemExit(
            f"engine {engine!r} is not available "
            f"(available: {', '.join(sorted(_AVAILABLE_ENGINES))})"
        )
    if engine == "nautilus":
        from custos.engines.nautilus.host import NtTradingNodeHost

        return NtTradingNodeHost(
            tenant_id=args.tenant_id,
            runner_id=args.runner_id,
            runner_fact_emitter=fact_emitter,
            capability_receipt=capability_receipt,
        )
    if engine == "noop":
        from custos.engines.nautilus.host import NoopHost

        return NoopHost()
    raise SystemExit(f"unhandled engine {engine!r}")


def _build_reconciler(
    args: argparse.Namespace,
    client: CrucibleNatsClient,
    host: object,
    vault: PerKeyVault,
    runtime_log_emitter: RunnerRuntimeLogEmitter,
    lifecycle_fact_emitter: RunnerDeploymentLifecycleFactEmitter,
    deployment_verifier: CrucibleDomainEventVerifier,
    readiness: ReadinessFile | None = None,
) -> DeploymentReconciler:
    """Compose the reconciler with the three local guards wired in (non-custodial
    red line 0.3 runtime wire — cap + breaker + watchdog keep guarding when
    the cloud is unreachable). Cap / breaker configs start at conservative
    floors; per-spec risk_config refresh is a follow-up."""
    runner_cap = RunnerNotionalCap(LocalCapConfig.from_spec({}, live=False))
    zombie_watchdog = ZombieWatchdog()
    return DeploymentReconciler(
        nats_client=client,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        execution_engine=host,  # type: ignore[arg-type]
        credential_vault=vault,
        runtime_log_emitter=runtime_log_emitter,
        lifecycle_fact_emitter=lifecycle_fact_emitter,
        deployment_verifier=deployment_verifier,
        local_cap=runner_cap,
        zombie_watchdog=zombie_watchdog,
        readiness=readiness,
    )


async def run_daemon(args: argparse.Namespace) -> int:
    """Start signed-command reconciliation and signed RunnerFact publication.

    Body is verbatim from the pre-Plan-11 flat CLI ``_run`` coroutine
    aside from the vault selection (see ``_build_vault``).
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.ready_file.expanduser().resolve().unlink(missing_ok=True)
    metadata = RunnerToml.read(args.runner_toml_path)
    machine_credential = MachineCredentialVault(args.machine_vault).load()
    machine_credential.assert_binding(metadata)
    MachineCredentialHttpClient(metadata.backend_url, machine_credential).verify_active()
    identity = RunnerFactIdentity.from_private_bytes(
        machine_credential.private_key_bytes,
        machine_credential.machine_key_id,
    )
    capability = RunnerCapabilityReceipt.load(args.runner_capability)
    runner_id = UUID(args.runner_id)
    if capability.tenant_id != args.tenant_id or capability.runner_id != runner_id:
        raise RuntimeError("Runner capability receipt identity does not match runner.toml")
    if capability.key_id != identity.key_id:
        raise RuntimeError("Runner capability receipt key_id does not match local identity")
    public_key_digest = hashlib.sha256(identity.public_key_bytes).hexdigest()
    if capability.public_key_digest != public_key_digest:
        raise RuntimeError("Runner capability receipt public key does not match local identity")
    if capability.binding_status != "validated":
        raise RuntimeError(
            "Runner capability bindings are not validated; restart after projection completes"
        )
    fact_outbox = RunnerFactOutbox(args.runner_fact_outbox)
    fact_emitter = RunnerFactEmitter(
        fact_outbox,
        identity,
        machine_credential.assert_active,
    )
    runtime_log_emitter = RunnerRuntimeLogEmitter(
        emitter=fact_emitter,
        capability=capability,
        redactor=RuntimeLogRedactor(known_secrets=(machine_credential.machine_credential,)),
    )
    lifecycle_fact_emitter = RunnerDeploymentLifecycleFactEmitter(fact_emitter, capability)
    fact_publisher = RunnerFactJetStreamPublisher(
        servers=(args.nats_url,),
        outbox=fact_outbox,
        runner_id=runner_id,
        authority_guard=machine_credential.assert_active,
    )
    client = CrucibleNatsClient(
        nats_url=args.nats_url,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        machine_credential=machine_credential,
    )
    readiness = ReadinessFile(
        args.ready_file,
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        credential_id=str(machine_credential.credential_id),
        credential_version=machine_credential.credential_version,
        credential_valid_until=metadata.credential_valid_until,
        machine_key_id=machine_credential.machine_key_id,
    )
    readiness.clear()
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
    host: object | None = None
    try:
        tasks.append(
            asyncio.create_task(
                _watch_machine_authority(
                    stop,
                    backend_url=metadata.backend_url,
                    machine_credential=machine_credential,
                ),
                name="runner-machine-authority-watch",
            )
        )
        tasks.append(
            asyncio.create_task(
                fact_publisher.run(stop),
                name="crucible-runner-fact-publisher",
            )
        )
        # Deployment reconciler consumes only Crucible-signed, runner-scoped commands.
        if args.reconcile:
            deployment_verifier = CrucibleDomainEventVerifier.from_file(
                args.crucible_domain_public_key,
                key_id=args.crucible_domain_key_id,
            )
            vault = _build_vault(args)
            # ``--engine noop`` declares supports_live()=False so the G6 gate
            # refuses it on live; the default nautilus engine selects the real
            # NtTradingNodeHost. The host wires only signed RunnerFact bridges
            # to each deployment's MessageBus inside deploy().
            host = _build_host(
                args,
                fact_emitter=fact_emitter,
                capability_receipt=capability,
            )
            reconciler = _build_reconciler(
                args,
                client,
                host,
                vault,
                runtime_log_emitter,
                lifecycle_fact_emitter,
                deployment_verifier,
                readiness,
            )
            tasks.append(
                asyncio.create_task(
                    reconciler.reconcile_loop(stop),
                    name="crucible-deployment-reconciler",
                )
            )
            if args.engine == "nautilus":
                producer = RunnerFactProductionLoop(
                    host=host,  # type: ignore[arg-type]
                    emitter=fact_emitter,
                    snapshot_interval_secs=args.runner_fact_snapshot_interval_secs,
                    period_secs=args.runner_fact_period_secs,
                    period_retry_secs=args.runner_fact_period_retry_secs,
                )
                tasks.extend(
                    (
                        asyncio.create_task(
                            producer.run_observability(stop),
                            name="crucible-runner-fact-observability",
                        ),
                        asyncio.create_task(
                            producer.run_periods(stop),
                            name="crucible-runner-fact-periods",
                        ),
                    )
                )
        else:
            readiness.mark_ready(
                strategy_id=None,
                nats_connected=True,
                deployment_subscription=False,
            )

        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        stop.set()
        readiness.clear()
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if host is not None and callable(getattr(host, "close", None)):
            await host.close()  # type: ignore[attr-defined]
        await fact_publisher.close()
        await client.close()
        log.info("runner_stopped")
    return 0
