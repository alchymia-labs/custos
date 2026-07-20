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
from custos.core.machine_credential_vault import (
    MachineCredentialError,
    MachineCredentialHttpClient,
    MachineCredentialRejectedError,
    MachineCredentialTransportError,
    MachineCredentialVault,
)
from custos.core.nats_client import CrucibleNatsClient
from custos.core.nats_transport import (
    RunnerNatsTransportConnectionProfile,
    RunnerNatsTransportError,
    RunnerNatsTransportVault,
)
from custos.core.per_key_vault import PerKeyVault
from custos.core.readiness import ReadinessFile
from custos.core.runner_deployment_lifecycle_fact import RunnerDeploymentLifecycleFactEmitter
from custos.core.runner_fact import (
    RunnerCapabilityReceipt,
    RunnerFactEmitter,
    RunnerFactIdentity,
    RunnerFactJetStreamPublisher,
    RunnerFactOutbox,
    RunnerStateAuthorityError,
    RunnerStateStore,
)
from custos.core.runner_fact_producer import RunnerFactProductionLoop
from custos.core.runner_safety_policy import (
    DurableRunnerSafetyPolicyResolver,
    RunnerSafetyPolicyResolver,
)
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


async def _watch_nats_transport_authority(
    stop: asyncio.Event,
    profile: RunnerNatsTransportConnectionProfile,
    *,
    check_secs: float = 1.0,
) -> None:
    """Stop execution on local expiry or broker authorization denial."""

    while not stop.is_set():
        try:
            profile.assert_active()
        except RunnerNatsTransportError as exc:
            log.error(
                "nats_transport_authority_invalidated",
                extra={"error_type": type(exc).__name__},
            )
            stop.set()
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=check_secs)
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
    runner_safety_boundary_factory=None,
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
            runner_safety_boundary_factory=runner_safety_boundary_factory,
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
    safety_policy_resolver: RunnerSafetyPolicyResolver | None = None,
    readiness: ReadinessFile | None = None,
) -> DeploymentReconciler:
    """Compose durable policy guards without claiming CR99 runtime readiness.

    The resolver has no live capability until a real CR99 publication receipt
    exists, so live reconciliation remains fail closed.
    """
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
        safety_policy_resolver=safety_policy_resolver,
        zombie_watchdog=zombie_watchdog,
        readiness=readiness,
    )


def _command_authority_unavailable(_verified_command):
    raise RunnerStateAuthorityError(
        "CR89 command authority resolver is not composed; "
        "strategy_release_id must not be substituted for strategy_id"
    )


def _build_runner_safety_boundary_factory(
    *,
    state_store,
    safety_policy_resolver: RunnerSafetyPolicyResolver,
):
    async def build(spec: dict):
        limits = await safety_policy_resolver.resolve(str(spec["trading_mode"]))
        if not limits.owner_policy or limits.policy_id is None:
            raise RuntimeError("runner safety execution requires a durable verified owner policy")
        from custos.engines.nautilus.runner_safety import RunnerReservationBoundary

        return RunnerReservationBoundary(
            store=state_store,
            deployment_instance_id=UUID(str(spec["deployment_instance_id"])),
            policy_id=limits.policy_id,
        )

    return build


async def _supervise_long_running_tasks(tasks: list[asyncio.Task], stop: asyncio.Event) -> None:
    """Fail the daemon when a long-running task exits before an intentional stop."""

    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    failure: BaseException | None = None
    failed_name = "unnamed"
    for task in done:
        failed_name = task.get_name()
        if task.cancelled():
            if not stop.is_set():
                failure = RuntimeError("long-running task was unexpectedly cancelled")
            continue
        task_error = task.exception()
        if task_error is not None:
            failure = task_error
            break
        if not stop.is_set():
            failure = RuntimeError("long-running task exited unexpectedly")
            break
    stop.set()
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if failure is not None:
        raise RuntimeError(f"long-running task {failed_name!r} failed: {failure}") from failure


async def _shutdown_in_order(
    *,
    stop: asyncio.Event,
    tasks: list[asyncio.Task],
    host: object | None,
    fact_outbox: object,
    fact_publisher: object,
    client: object,
) -> None:
    """Stop intake/tasks, stop deployments, flush facts, then close transports."""

    stop.set()
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    try:
        close_host = getattr(host, "close", None)
        if callable(close_host):
            await close_host()
        try:
            await fact_publisher.drain_once()  # type: ignore[attr-defined]
            for _ in range(7):
                if not await fact_outbox.pending():  # type: ignore[attr-defined]
                    break
                if await fact_publisher.drain_once() == 0:  # type: ignore[attr-defined]
                    break
            if await fact_outbox.pending():  # type: ignore[attr-defined]
                log.warning("runner_fact_shutdown_flush_incomplete")
        except Exception as exc:  # noqa: BLE001 - durable rows remain for restart
            log.warning(
                "runner_fact_shutdown_flush_failed",
                extra={"error_type": type(exc).__name__},
            )
    finally:
        try:
            await fact_publisher.close()  # type: ignore[attr-defined]
        finally:
            await client.close()  # type: ignore[attr-defined]


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
    transport_bundle = RunnerNatsTransportVault(args.nats_transport_vault).load()
    if transport_bundle.active is None:
        raise RunnerNatsTransportError(
            "NATS transport has no active generation; run nats-transport activate"
        )
    if transport_bundle.retiring is not None:
        raise RunnerNatsTransportError(
            "NATS transport has unresolved retiring-generation evidence; "
            "run nats-transport activate to resume fail-closed retirement"
        )
    transport_profile = RunnerNatsTransportConnectionProfile(
        credential=transport_bundle.active,
        nats_url=args.nats_url,
        ca_path=args.nats_ca,
        server_name=args.nats_server_name,
        pinned_issuer_account_public_nkey=args.nats_issuer_account_public_nkey,
    )
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
        redactor=RuntimeLogRedactor(
            known_secrets=(
                machine_credential.machine_credential,
                transport_bundle.active.nats_user_jwt,
            )
        ),
    )
    lifecycle_fact_emitter = RunnerDeploymentLifecycleFactEmitter(fact_emitter, capability)
    fact_publisher = RunnerFactJetStreamPublisher(
        connection_profile=transport_profile,
        outbox=fact_outbox,
        runner_id=runner_id,
        authority_guard=machine_credential.assert_active,
    )
    client = CrucibleNatsClient(
        connection_profile=transport_profile,
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
                _watch_nats_transport_authority(stop, transport_profile),
                name="runner-nats-transport-authority-watch",
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
            state_store = RunnerStateStore(
                outbox=fact_outbox,
                identity=identity,
                tenant_id=args.tenant_id,
                runner_id=runner_id,
                authority_resolver=_command_authority_unavailable,
            )
            safety_policy_resolver = DurableRunnerSafetyPolicyResolver(state_store)
            runner_safety_boundary_factory = _build_runner_safety_boundary_factory(
                state_store=state_store,
                safety_policy_resolver=safety_policy_resolver,
            )
            # ``--engine noop`` declares supports_live()=False so the G6 gate
            # refuses it on live; the default nautilus engine selects the real
            # NtTradingNodeHost. The host wires only signed RunnerFact bridges
            # to each deployment's MessageBus inside deploy().
            host = _build_host(
                args,
                fact_emitter=fact_emitter,
                capability_receipt=capability,
                runner_safety_boundary_factory=runner_safety_boundary_factory,
            )
            reconciler = _build_reconciler(
                args,
                client,
                host,
                vault,
                runtime_log_emitter,
                lifecycle_fact_emitter,
                deployment_verifier,
                safety_policy_resolver,
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

        await _supervise_long_running_tasks(tasks, stop)
    finally:
        readiness.clear()
        await _shutdown_in_order(
            stop=stop,
            tasks=tasks,
            host=host,
            fact_outbox=fact_outbox,
            fact_publisher=fact_publisher,
            client=client,
        )
        log.info("runner_stopped")
    return 0
