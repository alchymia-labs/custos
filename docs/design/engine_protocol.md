# Engine protocol

The engine adapter is a local deep module. It hides process and framework
details from reconciliation while preserving exact deployment identity.

## Identity rule

Every lifecycle, risk, snapshot, watchdog and breaker operation is keyed by
deployment_instance_id. deployment_spec_id is immutable configuration
provenance and must not address a running process.

## Conceptual interface

    class EngineProtocol(Protocol):
        async def deploy(
            self,
            spec: RuntimeSpec,  # contains deployment_instance_id
            credential: LocalCredential,
        ) -> EngineHandle: ...

        async def reconfigure(
            self,
            spec: RuntimeSpec,  # contains deployment_instance_id
        ) -> None: ...

        async def stop(self, deployment_instance_id: UUID) -> None: ...
        async def flatten(self, deployment_instance_id: UUID) -> None: ...
        async def snapshot(self, deployment_instance_id: UUID) -> EngineSnapshot: ...
        async def wait_ready(
            self,
            authority: EngineLifecycleAuthority,
            *,
            timeout_secs: float,
        ) -> EngineReadyReceipt: ...
        async def wait_terminal(
            self,
            authority: EngineLifecycleAuthority,
        ) -> EngineTerminalEvent: ...

The concrete Nautilus adapter may use framework-specific trader or node ids,
but those ids must be deterministically derived from and mapped back to the
deployment instance. It must never collapse two instances of one spec into a
single handle.

`EngineReadyReceipt` binds the exact instance, spec, spec digest and generation.
It is valid only after the node task, data and execution connectivity, portfolio,
reconciliation, strategy lifecycle and mandatory mode capabilities are all ready.
Creating an asyncio task is not readiness. `EngineTerminalEvent` binds the same
instance/spec/generation and carries a typed reason plus retryability.

## Failure contract

Adapter errors are local execution outcomes. The reconciler decides ACK or NAK
and emits a signed RunnerFact; the adapter cannot mutate Crucible business
state or ask ARX to authorize a recovery action.

The Plan 19 lifecycle supervisor persists its bounded restart counter in the
existing RunnerFact SQLite `command_in_progress_lease`. It probes a matching
durably applied engine before deploying on redelivery, uses exponential backoff,
and commits ready or retry-exhausted/quarantine through the T4 atomic lifecycle
transaction. It creates no database, journal or outbox.

Current authority status is `PREPARED_BLOCKED_ARTIFACT_RUNTIME_CAPABILITY`.
The adapter contract is implemented, but the v1.team daemon remains disabled
while the real Plan 18 T5e artifact capability is false. Live readiness is false.
