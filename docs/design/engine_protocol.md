# engine_protocol — ExecutionEngineProtocol authority doc

> Source: `src/custos/core/engine_protocol.py`.

## Tier-1 contract (frozen)

All engine hosts must implement `ExecutionEngineProtocol`.  The G6 gate and
the deployment reconciler operate exclusively through this interface.

```python
@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    async def deploy(self, spec: dict, credential: dict) -> str: ...
    async def reconfigure(self, spec: dict) -> None: ...
    async def stop(self, spec_id: str) -> None: ...
    def supports_live(self) -> bool: ...
    def supports_venue(self, venue: str) -> bool: ...
```

### Method semantics

| Method | Sync/Async | Purpose |
|--------|-----------|---------|
| `deploy` | async | Start a strategy from a `DeploymentSpec` + decrypted credential. Returns a container/session id. |
| `reconfigure` | async | Hot-update a running deployment (e.g. parameter tweak). |
| `stop` | async | Stop a deployment by `spec_id`. |
| `supports_live` | sync | Capability query: can this host execute against a live venue? G6 gate layer 1 calls this. |
| `supports_venue` | sync | Capability query: does this host wire the given venue connector? G6 gate layer 2 calls this. |

`supports_live` and `supports_venue` are synchronous because the G6 gate
needs an immediate answer before any async work.

### Existing implementations

| Host | Module | `supports_live` | `supports_venue` |
|------|--------|-----------------|-------------------|
| `NoopHost` | `custos.engines.nautilus.host` | `False` | `False` |
| `NtTradingNodeHost` | `custos.engines.nautilus.host` | `True` | `True` for `BINANCE` |

## Tier-2 extensions (planned, owned by downstream plans)

The following methods are documented as the recommended extension surface.
They are **not** part of the Tier-1 runtime Protocol and will be added by
Plan 04 together with their implementations (paired landing keeps
`isinstance` checks stable).

| Method (recommended signature) | Owner | Purpose |
|-------------------------------|-------|---------|
| `check_engine_connected(spec_id) -> ...` | Plan 04 | Zombie watchdog |
| `get_status(spec_id) -> ...` | Plan 04 | Status snapshot |
| `get_positions(spec_id) -> ...` | Plan 04 | Position snapshot |
| `get_orders(spec_id) -> ...` | Plan 04 | Order snapshot |
| `get_open_notional(spec_id) -> Decimal` | Plan 04 | Runner notional cap (Decimal, red-line 0.4) |
| `flatten_positions(spec_id, reason) -> None` | Plan 04 | Breaker flatten |

## Engine onboarding template (5 steps)

To add a new engine (e.g. hummingbot):

1. `mkdir src/custos/engines/<name>/` + `tests/engines/<name>/` + `docs/engines/<name>.md`
2. Implement `ExecutionEngineProtocol` in `<name>/host.py` (Tier-1 required; Tier-2 as needed)
3. Fill the `<name>` optional-dependency in `pyproject.toml` (empty slot already exists)
4. Add venue adapter(s) if needed (`venue_<exchange>.py`)
5. Register in CLI dispatch: `custos deploy --engine <name>` routes to the new host
