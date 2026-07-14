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

The concrete Nautilus adapter may use framework-specific trader or node ids,
but those ids must be deterministically derived from and mapped back to the
deployment instance. It must never collapse two instances of one spec into a
single handle.

## Failure contract

Adapter errors are local execution outcomes. The reconciler decides ACK or NAK
and emits a signed RunnerFact; the adapter cannot mutate Crucible business
state or ask ARX to authorize a recovery action.
