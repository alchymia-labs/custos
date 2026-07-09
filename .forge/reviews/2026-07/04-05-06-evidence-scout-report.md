# Evidence Scout Report — Plan 04 + 05 + 06 Foundation Scan

> **Role**: evidence-scout (custos plan-team). Facts only, no plan drafting, no file edits.
> **Scope**: Plan 04 (红线 0.3), Plan 05 (结构重构 + rename), Plan 06 (ps supertrend 迁移).
> **Method**: 4-dimensional Foundation Scan (historical-lessons.md #14 空间维 / #30 命名空间维 / #33 时间维 / #33b 层次维). Every fact below is `file:line` anchored or a literal grep/read result; anything not anchorable is marked **UNVERIFIED**.
> **as-of**: main HEAD `db75846` (Plan 05 skeleton commit), 2026-07-09.

---

## Coverage Checklist

- [x] Sanity-check grep (`import structlog` in `src/`) before trusting any "0 hits" result — see Plan 04 §1.
- [x] Plan 05 axis 1–7 (rename fanout / src+tests tree / `NautilusHostProtocol` / G6 gate / pyproject.toml / NATS subject / CLI entry)
- [x] Plan 04 axis 1–8 (`max_notional_per_runner` / `flatten` / `drawdown` / reconcile disconnect handling / snapshot API / chaos test infra / zombie-orphan / structlog landscape)
- [x] Plan 06 axis 1–8 (`_strategy_loader.py` / ps `register_strategy` / ps `registry.py` / ps `shared/` tree / supertrend `config.yaml` / sidecar consumer / `TradingNodeConfig` construction / supertrend tests)
- [x] Cross-plan: Plan 05 path renumbering effect on 04/06; sidecar arx-side confirmation
- [x] Bonus finds surfaced during scan (design-doc drift, `DeploymentSpec` is a dict not a class, NT SDK API names) — flagged inline where they change a plan's assumption

---

# Plan 05 Foundation Scan (结构重构 + rename + ExecutionEngineProtocol)

## 1. `arx_runner` rename fanout (lesson #35)

Sanity check passed: `grep "import structlog" src/` hits `src/arx_runner/log.py:20` — pattern matching works.

**Total occurrences**: `grep -rn "arx_runner" src/ tests/ docs/ .claude/ .forge/ Makefile pyproject.toml CLAUDE.md README.md` → **352 lines**, across **60 files**. Full distinct-file list (sorted):

```
.claude/rules/historical-lessons.md
.claude/rules/mandatory-rules.md
.claude/rules/verification.md
.forge/dispatch-log/03/plan-drafter.complete.json
.forge/handoff/2026-07/{00a,00b,00c,03}-execute-team-packet.md
.forge/handoff/2026-07/03-plan-team-packet.md
.forge/marker/{00b-runner,03-runner}.complete.json
.forge/plans/2026-07/{00a,00b,00c,01,03,04,05,06}-*.md
.forge/README.md
.forge/reviews/2026-07/{00a-peer-codex,00b-peer-codex,00b-peer-manual,00b-safety-validator-report,00b-tdd-enforcer-report,00c-peer-codex,03-authority-reviewer-report,03-evidence-scout-report,03-impl-peer-codex,03-intra-plan-reviewer-report,03-peer-codex,03-tdd-enforcer-report}.md
.forge/teams.yaml
.forge/triage/03-DEVIATION-triage.md
CLAUDE.md
docs/design/03-implementation.md
docs/design/{credential_vault,enrollment,nats_client,nautilus_host,reconcile,telemetry_actor}.md
docs/domain.md
docs/guides/04-testing.md
docs/guides/dev-guide.md
docs/ops/05-deployment.md
pyproject.toml
README.md
src/arx_runner/{__main__,_strategy_loader,credential_vault,deployment_reconciler,enrollment,nats_client,nautilus_host,nt_risk_engine,telemetry_actor}.py
tests/test_{credential_lifecycle,credential_vault_sops,credential_vault,deployment_reconciler,enrollment,g6_gate_capability_e2e,g6_gate_capability_integration,g6_gate,gc_safety_invariant,heartbeat,host_mode_matrix,log,main_host_selection,nats_client_telemetry,nats_envelope,nats_wal_resilience,nats_wire_contract,nautilus_host_capability,nt_binance_venue,nt_risk_engine,nt_telemetry_e2e,nt_trading_node_host_integration,nt_trading_node_host,reconcile,smoke,strategy_loader,subject_builder_contract,telemetry_actor_failure_modes,telemetry_actor,telemetry_money_contract,telemetry_nt_bridge}.py
```

**Test-file import fanout precisely** (`grep -rc "from arx_runner\|import arx_runner" tests/*.py`, non-zero only): **31 test files**, total **62 import lines** (sum of per-file counts below):

```
test_credential_vault.py:1  test_credential_lifecycle.py:1  test_g6_gate_capability_integration.py:2
test_credential_vault_sops.py:1  test_deployment_reconciler.py:1  test_g6_gate.py:3
test_enrollment.py:1  test_g6_gate_capability_e2e.py:3  test_gc_safety_invariant.py:4
test_heartbeat.py:1  test_log.py:1  test_main_host_selection.py:2
test_nats_client_telemetry.py:1  test_nats_wal_resilience.py:1  test_host_mode_matrix.py:4
test_nautilus_host_capability.py:1  test_nt_binance_venue.py:2  test_nt_telemetry_e2e.py:3
test_nt_trading_node_host_integration.py:3  test_nats_envelope.py:1  test_nt_trading_node_host.py:3
test_smoke.py:1  test_strategy_loader.py:1  test_subject_builder_contract.py:2
test_nats_wire_contract.py:1  test_telemetry_nt_bridge.py:1  test_telemetry_actor.py:2
test_nt_risk_engine.py:2  test_reconcile.py:2  test_telemetry_actor_failure_modes.py:3
test_telemetry_money_contract.py:2
```

**Makefile**: `grep -n "arx_runner" Makefile` → **0 hits** (contra plan's Track 1 assumption that Makefile needs a rename pass — verify no other module-path reference exists there before drafting a Makefile task).

**pyproject.toml** rename touchpoints (see full dump in §5 below): `name="custos-runner"` already renamed (pip-side, no change needed); `[tool.hatch.build.targets.wheel] packages = ["src/arx_runner"]` at line 39 is the **one** line that must change to `["src/custos"]`.

## 2. Current `src/` + `tests/` inventory

`find src/ tests/ -type f -name '*.py'`:

**`src/arx_runner/`** — 14 files: `__init__.py` `__main__.py` `_nt_binance_venue.py` `_strategy_loader.py` `config.py` `credential_vault.py` `deployment_reconciler.py` `enrollment.py` `log.py` `nats_client.py` `nautilus_host.py` `nt_risk_engine.py` `reconcile.py` `telemetry_actor.py`

Classification (matches Plan 05's own §Context table with one addition):
- **Engine-agnostic core** (→ `custos/core/`): `config.py` `credential_vault.py` `deployment_reconciler.py` (minus G6-gate Protocol coupling — see §3) `enrollment.py` `log.py` `nats_client.py` `reconcile.py` `telemetry_actor.py`
- **NT-specific** (→ `custos/engines/nautilus/`): `_nt_binance_venue.py` `_strategy_loader.py` `nautilus_host.py` `nt_risk_engine.py`
- **Entry point** (→ `custos/cli/` or `custos/__main__.py`): `__main__.py`

**`tests/`** — 32 files + `tests/fixtures/minimal_supertrend_strategy.py` (listed verbatim in §1's fanout list above). No existing `tests/core/` or `tests/engines/` subdirectory — Plan 05's proposed `tests/core/` + `tests/engines/nautilus/` split is **net-new directory structure**, not a rename of existing subdirs.

## 3. `NautilusHostProtocol` current definition (ancestor of `ExecutionEngineProtocol`)

- **Definition**: `src/arx_runner/deployment_reconciler.py:156` `class NautilusHostProtocol(Protocol):`
  - `:166` `async def deploy(self, spec: dict, credential: dict) -> str: ...`
  - `:168` `async def reconfigure(self, spec: dict) -> None: ...`
  - `:170` `async def stop(self, spec_id: str) -> None: ...`
  - `:172` `def supports_live(self) -> bool: ...`
  - `:174` `def supports_venue(self, venue: str) -> bool: ...`
  - Note: **no `runtime_checkable` decorator currently** on `NautilusHostProtocol` (plain structural `Protocol`, duck-typed via `_host_capability()` helper at `:64`, not `isinstance()`). Plan 05's proposed `@runtime_checkable` on `ExecutionEngineProtocol` (skeleton line 122) is a **new** capability, not a straight rename.
  - Also **no** `get_status` / `check_engine_connected` / `get_positions` / `get_orders` / `get_open_notional` / `flatten_positions` methods exist on the current protocol — all 6 of Plan 05's proposed Track 3 state/risk methods are 100% new surface (see Plan 04 §5 below — corroborates 0 hits for a snapshot API anywhere).
- **Implementations**:
  - `NoopHost` — `src/arx_runner/nautilus_host.py:85` (methods `:97` `deploy`, `:102` `reconfigure`, `:105` `stop`, `:108` `supports_live` → always `False`, `:113` `supports_venue` → always `False`)
  - `NtTradingNodeHost` — `src/arx_runner/nautilus_host.py:117` (methods `:166` `deploy`, `:307` `stop`, `:333` `reconfigure`, `:160` `supports_live` → always `True`, `:163` `supports_venue` → checks `_SUPPORTED_VENUES` frozenset at `:62`)
- **Consumer**: `DeploymentReconciler` dataclass field `nautilus_host: NautilusHostProtocol` at `deployment_reconciler.py:199`.
- **Docs referencing the protocol name** (rename fanout for Track 4): `docs/design/reconcile.md:33`, `docs/design/nautilus_host.md:14,39,129`, `src/arx_runner/nautilus_host.py:3,93` (docstrings).

## 4. G6 gate current implementation (call sites for Track 4 refactor)

All in `src/arx_runner/deployment_reconciler.py`:
- `:35` `def _check_g6_gate(host: object, spec: dict, credential: dict | None) -> None:` — top-level orchestrator, docstring `:36` "a live deployment must clear every layer or it is refused"
- `:64` `def _host_capability(host: object, method: str, *args: object) -> bool:` — duck-typed capability query (fail-safe: undeclared method → `False`)
- `:77` `def _g6_require_live_capable_host(host, spec)` — layer 1, calls `_host_capability(host, "supports_live")` at `:78`
- `:91` `def _g6_require_supported_venue(host, spec)` — layer 2, calls `_host_capability(host, "supports_venue", str(venue))` at `:93`
- `:106` `def _g6_require_code_hash_match(spec)` — layer 3, code_hash pin check
- `:142` `def _g6_require_safe_credential_scope(credential, spec)` — layer 4, credential scope check
- **Call sites**: `_apply_spec` at `:349` (new deployment path) and `:353` (idempotent re-check path)
- **Structured log events emitted**: `g6_gate_code_hash_mismatch` (`:109,119,130`), `g6_gate_live_capability_denied` (`:80`), `g6_gate_venue_unsupported` (`:95`), `g6_gate_credential_scope_violation` (`:146`)

This is the exact 4-layer structure Plan 05 Track 4 needs to extract into `core/g6_gate.py` and repoint from `NautilusHostProtocol` → `ExecutionEngineProtocol`. No behavior change is implied by the current code — purely a Protocol name swap + module move.

## 5. `pyproject.toml` current structure (full file, 66 lines)

```toml
[project]
name = "custos-runner"
version = "0.0.0"
description = "Custos: non-custodial self-hosted runner ..."
requires-python = ">=3.11"
dependencies = ["nats-py>=2.9", "pydantic>=2.5", "structlog>=24", "uuid6>=2024.1.12"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.6"]
nt-runtime = ["nautilus-trader>=1.227; python_version >= '3.12'", "pyyaml>=6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/arx_runner"]        # ← line 39, ONLY line needing the rename

[tool.uv]
package = true

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E","W","F","I","B","UP"]
ignore = ["E501","B008"]
```

**Delta for Plan 05 Track 5**: current extras are `dev` + `nt-runtime` only (**not** `nautilus` — Plan 05 skeleton's example TOML renames `nt-runtime` → `nautilus`, which is itself a **boundary constant rename** consumers may reference — grep found no other file referencing the string `nt-runtime` as an install instruction besides `pyproject.toml` comments `:19-25` and `.claude/rules/tech-stack.md`/`common-errors.md`/`README.md` in the earlier full-repo `arx_runner` grep scope — those files were not in this grep's scope; a dedicated `grep -rn "nt-runtime"` pass is recommended before Track 5 executes). No `hummingbot` / `freqtrade` / `athanor` / `nt-rust` slots exist yet — confirmed net-new.

## 6. NATS subject naming current scheme

- **Central builder**: `src/arx_runner/nats_client.py:141` `def build_subject(tenant: str, kind: str, *path_parts: str) -> str:` → `:151` `return "arx." + ".".join(parts)`. Raises `ValueError` on empty path parts (`:150`).
- **Convenience wrapper**: `nats_client.py:134` `def heartbeat_subject(tenant_id, runner_id) -> str:` → delegates to `build_subject(tenant_id, "heartbeat", runner_id)`.
- **Subjects built via `build_subject`** (current scheme = `arx.{tenant}.{kind}.{...parts}`, **no engine segment**):
  - `nats_client.py:400` → `arx.{tenant}.deployment_spec.{strategy_id}`
  - `nats_client.py:427` → (subject via `build_subject`, kind not fully shown in this grep — confirm exact kind string at Phase 2)
  - `nats_client.py:446` → `arx.{tenant}.enrollment.{runner_id}`
  - `telemetry_actor.py:548` → telemetry envelope subject (routed through `build_subject`, comment at `:545-547` explicitly calls out this is deliberate to avoid malformed `"arx.acme.telemetry.."` subjects)
  - `telemetry_actor.py:559` → `heartbeat_subject(...)`
  - `nt_risk_engine.py:185` → `arx.{tenant}.pre_trade_reject.{runner_id}` (via `build_subject`)
- **⚠️ One subject bypasses the builder entirely** — `src/arx_runner/reconcile.py:127`: `return f"arx.{self._tenant_id}.recon_result.{self._runner_id}.{self._session_id}"` is a raw f-string, **not** routed through `build_subject()`. This is a pre-existing inconsistency Plan 05 Track 6 should account for: if an `{engine}` segment is inserted into the subject scheme, this hand-rolled subject in `reconcile.py` will silently NOT get the new segment unless it's explicitly migrated too (it won't be caught by grepping `build_subject(` call sites alone).

## 7. CLI entry point

- **No `[project.scripts]` entry in `pyproject.toml`** (`grep -n "\[project.scripts\]" pyproject.toml` → 0 hits / exit 1). There is currently **no installed console script** — the CLI is invoked as `python -m arx_runner` per `__main__.py:8` docstring ("Run with ``python -m arx_runner --tenant-id acme --runner-id runner-7``").
- **Dispatch**: `src/arx_runner/__main__.py:31` `_parse_args()` — `argparse.ArgumentParser(prog="arx-runner")`. Current flags: `--nats-url` `--tenant-id` `--runner-id` `--heartbeat-interval` `--enrollment-token` `--enrollment-path` `--sops-file` `--age-key-file` `--reconcile-strategy-id` `--use-nt-host` (boolean flag, `:72-77`).
- **Host selection**: `__main__.py:124` `_build_host(args, client)` — `if args.use_nt_host:` → `NtTradingNodeHost` (`:139`), else `NoopHost` (`:146`). This is a **binary** switch today (NT vs Noop) — Plan 05 Track 10's proposed `--engine <name>` multi-way dispatch is net-new, not a rename of an existing `--engine` flag (none exists).
- **No `cli/` package exists** — Plan 05 Track 2's proposed `src/custos/cli/main.py` is a new module, and `__main__.py`'s current logic (~220 lines, `_parse_args` + `_build_vault` + `_build_host` + `_run` + `main`) is what would move there.

---

# Plan 04 Foundation Scan (红线 0.3 兑现)

## 1. `max_notional_per_runner` — grep confirms plan's 0-code-hits claim, but design docs reference it in 7 places

`grep -rn "max_notional_per_runner" .` (repo-wide) → **0 hits in `src/` or `tests/`**, confirming Plan 04's origin claim exactly. Non-code hits (design intent only, no implementation):
```
README.md:37
CLAUDE.md:77
.claude/rules/mandatory-rules.md:30
.forge/README.md:38 (plan index entry itself)
.forge/plans/2026-07/04-red-line-03-runner-fallback.md:17,18,26,60,112 (this plan's own text)
docs/design/00-overview.md:33
docs/design/01-architecture.md:74
docs/design/nautilus_host.md:50
docs/ops/runbook.md:143
```

## 2. `flatten` / `flatten_positions` — 0 hits in custos; NT SDK method name differs from plan's assumed name

`grep -rn "flatten" src/ tests/ docs/` → **0 hits anywhere in custos**. Confirmed net-new for Track 4.

**NT SDK check** (`uv run python3 -c "import nautilus_trader.trading.strategy"` succeeded once `PATH=$HOME/.local/bin:$PATH` was set — confirms `nt-runtime` extra IS installed in this dev venv): `nautilus_trader.trading.strategy.Strategy` exposes `close_all_positions` and `close_position` (plus `handle_instrument_close` / `on_instrument_close` / `on_position_closed` / `subscribe_instrument_close` / `unsubscribe_instrument_close`) — **there is no method literally named `flatten_position` or `flatten_positions` on NT's `Strategy` class**. Plan 04's `ExecutionEngineProtocol.flatten_positions()` (per Plan 05 skeleton) and Plan 06's Track 4 breaker will need to map onto `Strategy.close_all_positions(instrument_id)` at the NT-engine-impl layer, not a same-named passthrough.

## 3. `drawdown` — 1 code hit (a telemetry field, not a computed breaker); design docs claim otherwise for `nt_risk_engine.py`

`grep -rn "drawdown" src/ tests/ docs/` → **1 hit in code**: `src/arx_runner/telemetry_actor.py:67` — the string `"drawdown_pct"` appears in a list (context needed at Phase 2, but per Plan 04's own citation this is a telemetry field name, not a computation).

**⚠️ Design-doc drift finding** (lesson #14/#33 territory): `docs/design/03-implementation.md:51` documents the project structure as:
```
├── nt_risk_engine.py      ← 本地 fallback breaker (drawdown + max_notional)
```
I read `src/arx_runner/nt_risk_engine.py` in full (379 lines). **It contains no drawdown computation, no fallback breaker, and no per-runner notional accumulation.** Its actual, sole responsibility (confirmed by its own module docstring `:1-19`) is: (1) mapping cloud-pulled per-order pre-trade rules (`max_qty` / `max_notional` / `price_collar_bps` — all **per-order**, not per-runner) into an NT `RiskEngineConfig`-shaped dict via `build_nt_risk_engine_config()` (`:87-119`), and (2) bridging NT's native `OrderDenied` MessageBus event to a `PreTradeRejected` NATS envelope via `NtRiskEngineBridge` (`:159-314`). This is the **per-order** layer that Plan 04's own §Context already correctly marks "✅ per-order (NT RiskEngine, existing)" — the design doc's line 51 label is stale/aspirational and should not be read as evidence that any part of Track 4's fallback breaker already exists. **Drafters: do not assume `nt_risk_engine.py` is a starting point for Track 4 — it's the per-order layer, unrelated in code to per-runner cap/breaker.**

Also: `PreTradeRuleConfig` dataclass (`nt_risk_engine.py:56-84`) is a good pattern reference for Track 1's `LocalCapConfig` — it demonstrates the project's established "parse Decimal from `str(raw[...])`, never from float" convention (`:79-80`) that Track 1/4 must follow (red line 0.4).

## 4. Reconcile loop's NATS-disconnect handling — lives in `deployment_reconciler.py`, NOT `reconcile.py`

**⚠️ Naming trap for drafters**: `src/arx_runner/reconcile.py` (152 lines) is actually `ReconcileUploader` — a **reconciliation-*result*-uploader** (balance/position/order/fill comparison → NATS), unrelated to the DeploymentSpec pull loop. Its only structlog call is `reconcile.py:143` `log.info("recon_cycle_stub", ...)` inside `run_reconciliation_cycle()` which is an explicit stub returning `[]` (`:136-151`, docstring: "a stub that lies is worse than a stub that does nothing").

The actual **DeploymentSpec pull loop with NATS-disconnect handling** is `DeploymentReconciler.reconcile_loop()` in `src/arx_runner/deployment_reconciler.py:206-265`:
- `:224-232` — subscribe failure: `_log.error("deployment_reconciler_subscribe_failed", ...)` then **`return`** (the whole loop exits, never starts — no retry-with-backoff on the initial subscribe).
- `:234-249` — per-iteration receive loop: `TimeoutError` → `continue` (`:240-241`, normal poll timeout, not a failure); any other exception → `_log.warning("deployment_reconciler_recv_failed", ...)` (`:243-247`) then `asyncio.sleep(poll_interval_secs)` + `continue` (`:248-249`) — **loop never stops, but also performs zero cap/breaker/drawdown check on this path**. This confirms Plan 04's premise precisely: disconnect is already handled gracefully (never crashes, never stops), but there is no structural notional/drawdown guard anywhere in this path — it is pure log-and-retry.
- Full structlog event landscape in `deployment_reconciler.py` (18 call sites; useful for Track 1-4 to know what naming convention to match and avoid duplicating): `:79,94,109,118,129,145` (G6 gate `_log.error`), `:217` `deployment_reconciler_started`, `:227` subscribe failed, `:243` recv failed (warning), `:254` decode failed, `:262` `deployment_reconciler_stopped`, `:271` missing spec_id, `:276` invalid generation, `:287` no-op (debug), `:295` stale (warning), `:318,333,389` (further down in `_apply_spec`/`_report_status`, not read in this pass — Phase 2 should read `:267-393` in full before drafting Track 1-4 hooks).

## 5. State snapshot API — 0 hits, confirmed net-new

`grep -n "snapshot\|def positions\|def orders\|open_notional" src/arx_runner/nautilus_host.py` → **0 hits**. Neither `NautilusHostProtocol` nor either implementation (`NoopHost`, `NtTradingNodeHost`) exposes any state-query method today — corroborates §3 of the Plan 05 scan above (protocol has zero of the 6 proposed state/risk methods).

## 6. Chaos test infrastructure — disconnect-simulation patterns already exist, but none combine with cap/breaker

Existing NATS-disconnect test patterns (none of these test a cap/breaker/drawdown path — all are pure connectivity/WAL tests):
- `tests/test_deployment_reconciler.py:68` — `raise RuntimeError("nats disconnected")` (mock fixture)
- `tests/test_enrollment.py:27` — same pattern
- `tests/test_nats_wal_resilience.py:64` — "Stash 10 messages while disconnected"
- `tests/test_nats_client_telemetry.py:97` `test_publish_fire_and_forget_silently_noops_when_disconnected`; `:105` `test_wal_stashes_telemetry_while_disconnected_and_drains_on_connect`; `:145` stash-with-distinct-subjects variant
- `tests/test_telemetry_nt_bridge.py:316` `test_nt_messagebus_disconnected_logs_and_degrades` → asserts `:323` `"nt_messagebus_disconnected"` appears in structured logs
- `tests/test_heartbeat.py:30-31` — comment references `nats_fire_and_forget_noop_disconnected` event (lesson #21 zero-silent pattern already in place for heartbeat)

Track 5's proposed `test_arx_disconnect_chaos.py` is genuinely new territory — no existing test combines disconnect injection with a runner-level cap/breaker/zombie assertion.

## 7. `zombie` / `orphan` / `_active_nodes` — no zombie-detection concept exists; `_active_nodes` is pure lifecycle bookkeeping

`grep -rniE "zombie|orphan|_active_nodes" src/ tests/` → **0 hits for "zombie" or "orphan"** (literal strings, case-insensitive). `_active_nodes` (10 hits) is a plain `dict[str, tuple]` on `NtTradingNodeHost` (`nautilus_host.py:141`) mapping `spec_id -> (TradingNode, background_task)`, used purely for idempotency-guard / stop / self-termination bookkeeping (`:169,218,308,379,381`) — it has no liveness-check semantics (no `check_connected()` polling, no timestamp of last-seen-healthy). Track 3's zombie watchdog is fully new logic; it can piggyback on this dict's keys as the enumeration source but must add the connectivity-check + timer state itself.

## 8. ps-side reference implementation for Track 2/3 (borrow candidates) — confirmed present at cited lines

`philosophers-stone/deploy/nautilus/runner.py` (grep confirms plan's citations are accurate):
- `:101` `self._peak_equity: float = 0.0` (⚠️ **float**, not Decimal — if Track 2 borrows this pattern, it must be re-derived in Decimal per custos red line 0.4, not copy-pasted)
- `:216` `_collect_metrics()`, `:323-328` peak-equity/drawdown_pct computation (`drawdown = self._peak_equity - equity`; `drawdown_pct = drawdown / self._peak_equity * 100`)
- `:344` `_collect_orders()`, `:383` `_collect_positions()`, `:453` `_collect_engine_status()` (`:472` docstring warns "risk than the cache/portfolio reads in `_collect_metrics`" — implies a cross-thread-safety caveat Track 2 must re-verify for NT's async engine thread, not assume safe)
- `:812` + `:1196` `_create_node_config()` (two occurrences — likely two host-flavor classes in this file; Phase 2 should read both before Track 4 designs custos's own `_create_node_config` equivalent)

`philosophers-stone/deploy/sidecar/app.py` Rule 2 (persistent-degradation / zombie) — confirmed at cited line, full logic read:
- `:298` docstring block describing Rule 1 (never-connected zombie, ready-timeout-based) and Rule 2 (running-disconnected zombie, persistent `engine`/`ipc` degradation-based)
- `:321` `persistent_degraded_since: dict[str, float] = {}` — per-source monotonic timer state
- `:359-368` the actual Rule 2 loop body: for each of `("engine", "ipc")`, if degraded, track since-when in the dict; if `now - since >= unhealthy_after`, add to `escalate_reasons`
- Escalation is unified with Rule 1 at one decision point (`:359` region continues below what was read) — `mark_healthy(False)` — and is **exempt while `state.paused`** (manual-intervention flag). Track 3's "本地自主降级" design should note this pause-exemption pattern as a good practice to replicate (avoid escalating during intentional maintenance).

---

# Plan 06 Foundation Scan (ps supertrend 迁移)

## 1. `_strategy_loader.py` current state — path→class only, but `NtTradingNodeHost` ALREADY probes for a module-level `create_strategy` factory

`src/arx_runner/_strategy_loader.py` (130 lines) — confirmed path→class only:
- `:59` `def load_strategy_class(strategy_path: Path, expected_code_hash: str | None) -> type:` — verifies code_hash (`:70-84`) then imports (`:86` `_import_module_from_path`) and locates the class (`:87` `_find_strategy_class`)
- `:106` `def _find_strategy_class(module, strategy_path) -> type:` — explicit `STRATEGY_CLASS` module attribute wins (`:109-111`), else the single class whose name ends in `"Strategy"` (`:113-118`), else raises (ambiguous or none found, `:121-128`)
- No `strategy_registry_name` concept, no import of `shared.nautilus.registry` anywhere — confirmed net-new for Track 1.

**⚠️ Important correction to plan's premise**: `NtTradingNodeHost._instantiate_strategy()` (`nautilus_host.py:356-367`) **already** has factory-probing logic:
```python
module = sys.modules.get(strategy_cls.__module__)
factory = getattr(module, "create_strategy", None) if module is not None else None
if callable(factory):
    return factory(spec.get("strategy_config", {}))
return strategy_cls()
```
docstring `:357-358` explicitly calls this "ps-style entry point". This is a **per-module** `create_strategy(config: dict)` factory probe (matches ps supertrend's own `strategy.py:394 def create_strategy(config: dict) -> SuperTrendStrategy:` — see §2 below), **distinct from** the registry-global `shared.nautilus.registry.create_strategy(name, config_wrapper=...)` the plan's Track 1 pseudocode proposes calling directly. Two viable integration paths exist for Track 1:
  - **(a)** Rely on the *existing* `_instantiate_strategy` factory probe — since ps supertrend's `strategy.py:394` module-level `create_strategy(config: dict)` already delegates to the registry internally (see §2), simply loading `strategy.py` via the existing path→class loader and letting `_instantiate_strategy` call its `create_strategy` may already work with **zero changes to `_strategy_loader.py`**, only a `sys.path` fix for `shared/` (Track 3).
  - **(b)** Add the plan's proposed `strategy_registry_name` field + explicit `shared.nautilus.registry.create_strategy(name, ...)` call, bypassing per-module `create_strategy` probing entirely.
  Phase 2 should explicitly decide between (a) and (b) — (a) is a much smaller diff if it works, but needs a spike/experiment to confirm `_find_strategy_class`'s "class name ends in `Strategy`" heuristic correctly locates `SuperTrendStrategy` in `strategy.py` (it should, since `register_strategy(...)` at module scope doesn't interfere with `inspect.getmembers`).

## 2. ps supertrend `register_strategy` + `create_strategy` — confirmed exactly as plan claims, plus a second Crucible-facing wrapper

`philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py`:
- `:18-24` imports `from shared.nautilus import (..., register_strategy)`
- `:386-391` module-scope self-registration: `register_strategy(name="supertrend", strategy_class=SuperTrendStrategy, config_class=SuperTrendStrategyConfig, parameters_builder=build_parameters_config)`
- `:394-411` **also** defines a module-level `def create_strategy(config: dict) -> SuperTrendStrategy:` — this is explicitly documented (`:395`) as the **"Crucible entry-point factory (alephain.strategies group)"**, implementing "the Crucible StrategyFactory protocol". Its body (`:402-411`) loads `base_config.yaml`, deep-merges with the passed `config` dict, wraps in `ConfigWrapper`, then calls `shared.nautilus.create_strategy("supertrend", config_wrapper=wrapper)` (the registry-global factory, aliased `_create_registered_strategy` at import time, `:406`). **This is exactly the per-module factory `NtTradingNodeHost._instantiate_strategy` already knows how to call** — confirming integration path (a) in §1 above is plausible with zero custos code change beyond `shared/` path resolution (Track 3).

## 3. ps `shared/nautilus/registry.py` — full read, confirms plan's API citations exactly

`philosophers-stone/shared/nautilus/registry.py` (339 lines):
- `:32-39` `_STRATEGY_REGISTRY: dict[str, tuple[StrategyClass, ConfigClass, parameters_builder]] = {}`
- `:173-204` `register_strategy(name, strategy_class, config_class, parameters_builder)` — idempotent re-registration from the *same* class is allowed (`:198-201`), re-registration from a *different* class raises `ValueError` (`:202`)
- `:148-165` `discover_strategies()` — lazy, called once (`_DISCOVERY_DONE` guard `:154-157`), scans 4 path patterns (`:91-145`: flat Docker, nested legacy Docker, scripts, and **category structure** — the local-dev pattern `{base}/{category}/{name}/refinement/nautilus/strategy.py` at `:131-144`, which is exactly where supertrend's `strategy.py` lives)
- `:222-288` `create_strategy(name, *, config=None, config_path=None, config_wrapper=None)` — 3 mutually-exclusive construction modes; raises `ValueError` for unregistered names (`:265-267`) listing available strategies — this is a clean, already-safe "明确错误 (非 crash)" for Plan 06's failure-mode contract row 1.
- `:53-56` env-var hook `STRATEGY_INJECT_PATH` (Crucible-specific extraction path) — **not directly relevant** to custos but shows the discovery mechanism is already env-var-extensible if custos needs its own discovery root.

## 4. ps `shared/` directory tree — full listing (for Track 3 packaging decision)

`find shared -type f -name '*.py'` → **~90 files** across 9 top-level subpackages:
```
shared/config/          (2 files: loader.py, validator.py)
shared/filters/         (8 files: adx/base/cooldown/momentum/mtf/regime/registry/time_filter/volatility/volume)
shared/hummingbot/      (10 files — Hummingbot-specific, NOT needed for custos/NT path)
shared/indicators/      (1 file: __init__.py — top-level, distinct from shared/nautilus/indicators/)
shared/nautilus/        (~35 files — the NT-relevant subtree, see below)
shared/position/        (2 files: sizer.py, tracker.py)
shared/protocols/       (3 files: bar.py, filter.py, __init__.py)
shared/risk/            (6 files: controller.py, equity.py, exchange_errors.py, manager.py, orders.py, __init__.py)
shared/signals/         (3 files: resolver.py, types.py, __init__.py)
shared/warmup/          (5 files: exceptions.py, protocol.py, snapshot.py, warmer.py, __init__.py)
```
`shared/nautilus/` itself breaks down into: `config/` (9 files: allocation/backtesting/filters/platforms/position/risk/signal/snapshot/trading), `coordinators/` (14 files: config_summary_logger/equity_provider/execution/filter/order_reconciler/pair_context/risk_control/signal_execution/sizing/sltp/snapshot/startup_validator/trade_event_handler/warmup), `filters/` (5 files), `indicators/` (5 files: adx/atr/macd/rsi/supertrend), plus top-level `capital_allocator.py` `event_publisher.py` `execution.py` `filter_manager.py` `orders.py` `pair_context.py` `registry.py` `signal_processor.py` `sizing.py` `sltp_mode.py` `state_persistence.py` `strategy_core.py` `tick_monitor.py` `trading_config.py` `trading_strategy.py` `utils.py` `warmup_manager.py`.

**For supertrend specifically**, the minimal dependency closure (per `strategy.py:16-26` imports) is: `shared/config/` (`ConfigWrapper`), `shared/nautilus/` (`NautilusTradingStrategy`, `NautilusTradingStrategyConfig`, `PairContext`, `register_strategy`, `indicators/supertrend.py`), `shared/signals/` (`Signal`) — but `shared/nautilus/trading_strategy.py` (the `NautilusTradingStrategy` base class) transitively pulls in most of `shared/nautilus/coordinators/*` and `shared/risk/*` (confirmed by `trading_strategy.py:73` `from shared.risk import OrderPriceCalculator, RiskController, RiskManager` — see §5 below). `shared/hummingbot/` is **not** in supertrend's NT import chain and can be excluded from any Track 3 packaging option that only needs the NT path.

## 5. supertrend `config.yaml` — confirmed 0 `risk:` section; `RiskController` wiring confirmed present but dormant

`philosophers-stone/trend/supertrend/config.yaml` (340 lines, read in full) — `grep -n "^risk:\|max_daily_loss\|max_drawdown\|consecutive_loss" trend/supertrend/config.yaml` → **0 hits**. No top-level `risk:` key exists at all in this file (sections present: `strategy`, `parameters`, `warmup`, `trading`, `position`, `platforms`, `snapshot` — confirmed exhaustively by reading the whole file). This exactly matches the plan's claim.

`shared/nautilus/trading_strategy.py`:
- `:73` `from shared.risk import OrderPriceCalculator, RiskController, RiskManager`
- `:177` `self._risk_controller: RiskController | None = None` — starts `None`, only populated if config supplies a risk section (mechanism for populating it was **not** read in this pass — Phase 2 should grep `_risk_controller =` assignment sites beyond `:177` to find where/if a config-driven risk section would activate it)
- `:730-732` `risk_controller` property getter (read-only accessor)

`shared/risk/controller.py` — `class RiskController` at `:33`; **confirmed Decimal-only money math** (red line 0.4 compliant): `:10` `from decimal import Decimal`; `:22,26` dataclass fields `session_pnl: Decimal`, `peak_equity: Decimal`; `:43` `initial_capital: Decimal` constructor param; `:107-178` `check_limits(current_equity: Decimal, ...)` / `_calculate_drawdown(...)  -> Decimal`, all internal comparisons use `Decimal(str(max_loss))` etc. (`:142,149,156`) — **no float anywhere in this file's signatures**, satisfying Plan 06's red-line-gate-table row 0.4 concern without further verification needed at the `RiskController` level itself (Track 2's job is only to populate the **config** that activates it, not touch this file).

## 6. `shared/` packaging challenge — no existing precedent in custos for cross-repo Python dependency

Not directly answerable by grep (this is a Track 3 design decision, not a fact-finding target) — but confirmed: custos's `pyproject.toml` (Plan 05 §5 above) has **zero** reference to `philosophers-stone` or any path/git dependency today. Whatever Track 3 chooses (A: bundle `shared/` into strategy dir; B: pip-package `shared/`; C: env-var `PS_SHARED_PATH` + sys.path), it is **greenfield** — no existing sys.path-injection or vendoring code exists in custos to build on top of. `_strategy_loader.py`'s `_import_module_from_path` (§1 above) does its own `sys.modules` registration but does **not** touch `sys.path` at all — so Track 3's chosen option must add path-manipulation logic somewhere (likely in `_strategy_loader.py` or the deploy-time bootstrap), it doesn't exist implicitly today.

## 7. ps sidecar / runner.py retirement — sidecar's actual primary consumer confirmed as Crucible; arx web dependency confirmed narrow

`grep -rln "sidecar" tesseract-trading/the-crucible/` → **19 files**, including core-looking hits: `crucible_engine/sidecar_models.py`, `crucible_engine/supervisor.py`, `crucible_engine/risk_monitor.py` (plan's cited `risk_monitor.py:568 sidecar_url` — not independently re-verified at that exact line in this pass, but the file is confirmed to reference sidecar), `crucible_engine/metrics_persister.py`, `docker/sidecar.Dockerfile`. This corroborates the plan's claim that Crucible is sidecar's primary/structural consumer (Dockerfile + engine core modules, not just docs).

`grep -rln "sidecar" tesseract-trading/arx/` → **9 files**, all in the **web/** frontend layer or planning docs — no Rust backend crate references sidecar:
```
docker/server.Dockerfile
web/package-lock.json
web/app/(dashboard)/dashboard/strategies/[id]/page.tsx
web/lib/hooks/useApi.ts        ← plan's cited file
web/lib/api/strategies.ts
web/lib/events/adapter.ts
web/lib/events/use-event-stream.ts
web/e2e/events.spec.ts
web/e2e/ui-migrate-smoke.spec.ts
```
`grep -n "sidecar" tesseract-trading/arx/web/lib/hooks/useApi.ts` → `:208` — confirmed exact comment: `// 当前持仓（sidecar 实时代理 GET /strategies/{id}/positions → { positions, count, stale }）`. This confirms the plan's claim precisely: arx's sidecar coupling is web-frontend-only (a comment + presumably a fetch call near it — the actual fetch implementation was not read in this pass) and is tech debt independent of custos/ps, not a hard backend dependency. Two `.forge/` planning artifacts in arx (`58-crucible-rust-maturity-assessment.md`, `2026-07-06-arx-pivot/evidence-part2.md`) also reference "sidecar" — likely discussing this same tech debt from arx's side; not read in this pass.

## 8. `TradingNodeConfig` construction comparison — ps vs custos

**ps** `philosophers-stone/deploy/nautilus/runner.py:812` `def _create_node_config(self) -> TradingNodeConfig:` (also `:1196`, a second occurrence — likely a second host-flavor class in the same file, unread in this pass). Read `:811-865`: builds `trader_id` from strategy name + environment (`:820-821`); pulls `platforms.nautilus.trading_node.*` config keys — `timeout_connection` (`:826`, default 30.0), `timeout_reconciliation` (`:827`, default 10.0), `timeout_portfolio` (`:828`, default 10.0), `timeout_disconnection` (`:829`, default 10.0), `reconciliation_lookback_mins` (`:830`, default 1440); conditionally builds `DatabaseConfig` + `CacheConfig` + `MessageBusConfig` if `database.enabled` (`:839-864`), gated by a `validate_event_publishing_config()` fail-fast check (`:836-838`, "D2 fix 18 (peer HIGH-1): fail-fast if event publishing is on but database is off" — a useful pattern reference for Track 4's own config validation).

**custos** `src/arx_runner/nautilus_host.py:192-199` — current `TradingNodeConfig` construction is **minimal**: only `trader_id`, `logging` (log_level from spec), `data_clients`/`exec_clients` (venue-keyed), and `exec_engine=LiveExecEngineConfig(reconciliation=reconciliation)`. **Zero** Redis cache/MessageBus config, **zero** custom timeout tuning — all currently rely on NT's internal defaults. This confirms Plan 06 Track 4's "custos TradingNodeConfig 是 minimal" claim exactly, and confirms ps's `config.yaml:213-228` (`platforms.nautilus.trading_node.{timeout_connection,timeout_reconciliation,timeout_portfolio,timeout_disconnection,reconciliation_lookback_mins}` — all present in the config file read in §5 above) is the config shape Track 4 would need to plumb into custos's `DeploymentSpec` (as `nautilus_config`, per the plan's own proposal) to reach parity.

## 9. Existing supertrend tests

`find alchymia-labs/philosophers-stone -name 'test_*supertrend*.py'` (excluding `.worktrees/` clutter — 14 hits total, only 4 are on the main tree):
```
tests/test_supertrend_hummingbot_refactored.py   (Hummingbot-side, not NT-relevant to Plan 06)
tests/test_supertrend_snapshot.py                (Redis snapshot persistence — relevant to config.yaml's `snapshot.*` section)
tests/strategies/test_supertrend.py
tests/strategies/test_supertrend_logic.py
```
(Contents not read in this pass — Phase 2 should read `tests/strategies/test_supertrend.py` + `test_supertrend_logic.py` before drafting Track 5's e2e test, to avoid duplicating existing coverage of `calculate_signal` logic.) The remaining 10 hits are stale copies under `.worktrees/feature-*/` branches — **not** live test files on the main tree, should be ignored.

## 10. `DeploymentSpec` is a plain `dict` everywhere — no Pydantic/dataclass model exists (affects both Plan 04 Track 1 and Plan 06 Track 2)

**⚠️ Cross-cutting finding, affects both Plan 04 and Plan 06**: `grep -rn "class DeploymentSpec" src/ tests/ docs/domain.md` → **0 hits**. `grep -rln "DeploymentSpec" src/` shows the identifier appears only inside type-hint comments / docstrings in `nats_client.py`, `_nt_binance_venue.py`, `_strategy_loader.py`, `deployment_reconciler.py` — every actual function signature in the codebase types it as plain `dict` (e.g. `deployment_reconciler.py:267 async def handle_spec(self, spec: dict) -> None:`, `nautilus_host.py:166 async def deploy(self, spec: dict, credential: dict) -> str:`).

Additionally, `docs/design/03-implementation.md`'s dependency table claims `pydantic` is used for "Envelope schema + DeploymentSpec 数据模型" and its project-structure comment labels `config.py` as `← DeploymentSpec / TransportEnvelope Pydantic 模型` — **both false**: `src/arx_runner/config.py` (28 lines, read in full) contains only one dataclass, `TelemetryQueueConfig` (queue-size / batch-size knobs), with **no** `DeploymentSpec` or `TransportEnvelope` class anywhere in it or in the rest of `src/`.

The only formal (non-code) schema for `DeploymentSpec`'s fields is prose in `docs/domain.md:103`:
```
spec_id · tenant_id · strategy_id · version · parameters(JSON) · execution_engine_binding_id
· trading_mode(testnet/sandbox/live) · target_runner_id · generation · code_hash · pulled_at
```
**No `risk_config` field and no `strategy_registry_name` field exist in this documented shape today.** Consequence for drafting: Plan 04 Track 1's "Cap 从 `DeploymentSpec.risk_config.max_notional_per_runner` 读入" and Plan 06 Track 2's "`DeploymentSpec` 数据模型加 `strategy_registry_name` optional 字段" both need to be re-scoped as **"add a new key to the `docs/domain.md:103` field list + consume it via `spec.get("risk_config", {}).get(...)` / `spec.get("strategy_registry_name")` dict access"** — there is no Python class to add a typed field to. If Plan 05 or a future plan formalizes `DeploymentSpec` as a real Pydantic model, that would change this, but as of this scan (Plan 05 skeleton stage) it has not happened and Plan 05's own skeleton does not propose it either.

---

# Cross-Plan Considerations

## Plan 05 → Plan 04/06 path dependency

Confirmed: Plan 04 and Plan 06 skeletons already correctly hedge their File Inventory sections with "⚠️ 路径基于 Plan 05 结构重构后的新目录 ... 若 Plan 05 未先落地则本 plan 路径需回退到 `src/arx_runner/*` 老路径". No further action needed here beyond drafters re-confirming Plan 05's actual final directory names (`custos/core/*` vs `custos/engines/nautilus/*`) match Plan 05's close-out reality before finalizing 04/06's own File Inventory — the skeleton names are currently only proposals, not yet built.

Specific renamed files each downstream plan should track once Plan 05 lands:
- Plan 04 needs: `custos/core/deployment_reconciler.py` (was `src/arx_runner/deployment_reconciler.py`), `custos/engines/nautilus/host.py` (was `nautilus_host.py`), `custos/core/telemetry_actor.py` (was `telemetry_actor.py`).
- Plan 06 needs: `custos/engines/nautilus/strategy_loader.py` (was `_strategy_loader.py` — **note the leading underscore is dropped** per Plan 05's own Track 2 table, `_strategy_loader.py` → `strategy_loader.py`; same for `nt_risk_engine.py` → `risk.py` and `_nt_binance_venue.py` → `venue_binance.py`), `custos/engines/nautilus/host.py`.

## Sidecar consumer confirmation (resolves prior uncertainty cited in Plan 06 origin)

Both plans' claim "sidecar 主消费者是 Crucible, arx 只是 web 前端 tech debt" is **confirmed** by this scan (§7 above) — Crucible has 19 sidecar references spanning Dockerfile + core engine modules (`supervisor.py`, `risk_monitor.py`, `metrics_persister.py`, `sidecar_models.py`), while arx's 9 references are entirely in `web/` (frontend hooks/pages/e2e specs) with zero Rust backend crate involvement.

## Design-doc drift flagged for authority-docs follow-up (not this scan's job to fix)

Two docs are stale relative to code and should be flagged to whoever runs `/forge:audit-authority` next, independent of Plans 04/05/06 landing:
1. `docs/design/03-implementation.md:51` mislabels `nt_risk_engine.py` as "本地 fallback breaker (drawdown + max_notional)" — it is actually the per-order NT RiskEngine bridge (see Plan 04 §3 above).
2. `docs/design/03-implementation.md`'s dependency table + project-structure comment claims `config.py` holds "DeploymentSpec / TransportEnvelope Pydantic 模型" — neither class exists anywhere in `src/` (see Plan 06 §10 above).

---

## Dispatch marker

Written to `.forge/dispatch-log/plan-team-04-05-06/evidence-scout.json`.
