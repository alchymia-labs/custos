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

## Tier-2 contract (frozen)

Six `required` methods that back the disconnect-resilient guards
(`local_cap` / `fallback_breaker` / `zombie_watchdog`) and the state
snapshot publisher. Every host adds each Tier-2 method in lockstep with
the Protocol so the `@runtime_checkable` `isinstance` check stays green
(`test_engine_protocol_tier2.py` covers this end-to-end, plus a
relaxed-double proving a fake missing a Tier-2 method fails the check).

```python
    # -- Tier-2: runner-level risk / connectivity state --------------------
    async def get_open_notional(self, spec_id: str) -> Decimal: ...
    async def check_engine_connected(self, spec_id: str) -> ConnectivityState: ...
    async def flatten_positions(self, spec_id: str, reason: str) -> None: ...

    # -- Tier-2: observability snapshot ------------------------------------
    async def get_positions(self, spec_id: str) -> list[PositionSnapshot]: ...
    async def get_orders(self, spec_id: str) -> list[OrderSnapshot]: ...
    async def get_engine_status(self, spec_id: str) -> EngineStatus: ...
```

| Method | Purpose | Consumer |
|--------|---------|---------|
| `get_open_notional` | Sum of gross open notional across the spec's positions (Decimal, red-line 0.4). | `RunnerNotionalCap` (soft cap) + `FallbackBreaker` (hard limit) |
| `check_engine_connected` | Engine data / exec connectivity + `checked_at_epoch_s` wall clock. | `ZombieWatchdog` — persistent disconnect > grace = degraded |
| `flatten_positions` | Close every open position for the spec by reason. NT hosts map this to `Strategy.close_all_positions` per instrument (DEV-04-FLATTEN-NT-MAPPING). | `FallbackBreaker` on trip |
| `get_positions` | List of `PositionSnapshot` (Decimal money) for observability. | `StateSnapshotPublisher` |
| `get_orders` | List of `OrderSnapshot` (Decimal money) for observability. | `StateSnapshotPublisher` |
| `get_engine_status` | Aggregate `EngineStatus`: counters + `open_notional` + `peak_equity` + `current_equity` + `drawdown_pct` (all money Decimal). | `StateSnapshotPublisher` + `FallbackBreaker.evaluate(current_equity=…)` drawdown feed |

### Money-safe snapshot dataclasses

Every snapshot type is a frozen dataclass whose money fields are enforced
Decimal at construction — `_reject_float_money` in `engine_protocol.py`
raises `TypeError` on any float slipping through the boundary
(runtime invariant, since dataclass annotations alone cannot enforce
types).

```python
@dataclass(frozen=True)
class ConnectivityState:
    data_connected: bool
    exec_connected: bool
    checked_at_epoch_s: float

@dataclass(frozen=True)
class PositionSnapshot:
    instrument_id: str
    quantity: Decimal
    avg_px: Decimal
    unrealized_pnl: Decimal
    notional: Decimal

@dataclass(frozen=True)
class OrderSnapshot:
    client_order_id: str
    instrument_id: str
    side: str
    quantity: Decimal
    price: Decimal
    status: str

@dataclass(frozen=True)
class EngineStatus:
    phase: str            # running / degraded / unknown
    position_count: int
    order_count: int
    open_notional: Decimal
    peak_equity: Decimal
    current_equity: Decimal
    drawdown_pct: Decimal   # percentage (Decimal("20") = 20%)
```

### NoopHost semantics

`NoopHost` returns empty lists + a zero-valued `EngineStatus`
(`phase="running"`, every Decimal `= 0`). This keeps the notional cap /
fallback breaker / zombie watchdog structurally no-op against a paper /
sim runner — the guards still evaluate every tick but never trip.

### NtTradingNodeHost semantics

- `get_open_notional`: sums `abs(position.quantity) * position.avg_px_open` over
  `kernel.cache.positions_open()`.
- `get_positions` / `get_orders`: iterate the same cache, Decimal-recompute
  every money field.
- `get_engine_status`: `open_notional` + `Σ unrealized_pnl` as
  `current_equity`; per-spec `peak_equity` is tracked as Decimal on the
  host (no float high-water mark — DEV-04-PEAK-EQUITY-DECIMAL);
  `drawdown_pct = (peak - current) / peak * 100`.
- `check_engine_connected`: `kernel.data_engine.check_connected()` +
  `kernel.exec_engine.check_connected()`, `checked_at_epoch_s = time.time()`.
- `flatten_positions`: per-instrument `Strategy.close_all_positions` for
  every strategy on the trader.

## Engine onboarding template (5 steps)

To add a new engine (e.g. hummingbot):

1. `mkdir src/custos/engines/<name>/` + `tests/engines/<name>/` + `docs/engines/<name>.md`
2. Implement `ExecutionEngineProtocol` in `<name>/host.py` (Tier-1 required; Tier-2 as needed)
3. Fill the `<name>` optional-dependency in `pyproject.toml` (empty slot already exists)
4. Add venue adapter(s) if needed (`venue_<exchange>.py`)
5. Register in CLI dispatch: `custos deploy --engine <name>` routes to the new host
