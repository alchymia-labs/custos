# NautilusTrader engine

`NtTradingNodeHost` is Custos's first production execution-engine adapter. It
implements `ExecutionEngineProtocol` for sandbox, testnet and live modes.

The host accepts exactly three inputs: the typed local execution view derived
from a verified Crucible command, a locally resolved credential, and an
`ActivatedEngineArtifactV1`. It never accepts or resolves `strategy_path`,
`code_hash`, registry aliases or a legacy factory.

The only strategy import boundary is
`src/custos/engines/nautilus/runtime_loader.py`. It loads the verified
`module:attribute` from the immutable activation root and requires the exported
object to implement `StrategyRuntimeAdapterV1.build_config` and
`build_strategy`.

Lifecycle readiness, restart budget and quarantine are owned by
`core/engine_lifecycle.py`. Command intake, artifact resolution/activation,
credential resolution and post-commit ACK are owned by
`core/runner_command_runtime.py`.

See [`docs/design/nautilus_host.md`](../design/nautilus_host.md) and
[`docs/design/engine_protocol.md`](../design/engine_protocol.md).
