# Plan 04 04b — codex L1 Peer Review

**Reviewed at**: 2026-07-10
**Target**: `main` @ `d0dd537` (04b squash-merge)
**Model**: codex-cli 0.142.0 with `model_reasoning_effort=high` (per lesson #10/#12 template)
**Invocation**: `codex exec -c model_reasoning_effort=high -o <file> --sandbox read-only < /dev/null > <log>`
**Runtime**: ~10 min high-effort, log 5252 lines, final message written to `-o` file, exit 0
**Codex budget**: 1 of 1 codex call for Plan 04 (teams.yaml codex_audit.max_codex_calls_per_plan=1)
**Team-lead independent grep confirmation**: all 3 findings validated file:line evidence (see below)

---

**VERDICT: REQUEST_CHANGES**

**Findings**

1. `src/custos/cli/main.py:224` HIGH — `StateSnapshotPublisher` is never wired into the runner entrypoint.  
   `main.py` only starts `reconciler.reconcile_loop(...)` at `src/custos/cli/main.py:224-239` and heartbeat at `src/custos/cli/main.py:241-245`. `StateSnapshotPublisher.run()` exists at `src/custos/core/state_snapshot.py:175-186`, but `rg` shows no production construction/call site. Failure scenario: a runner deploys successfully under `--reconcile-strategy-id`, but no periodic state snapshots are ever published. This contradicts the close-out claim that the custos-side state snapshot push path is complete.

2. `src/custos/core/state_snapshot.py:167` MED — disconnected snapshot caching is not implemented for the publisher path.  
   The publisher calls `publish_fire_and_forget`, which is at-most-once and logs/returns when disconnected at `src/custos/core/nats_client.py:357-370`. The Plan required disconnected snapshot WAL caching at `.forge/plans/2026-07/04-red-line-03-runner-fallback.md:305-306`, but the chaos WAL test bypasses `StateSnapshotPublisher` and directly calls `publish_telemetry_envelope` at `tests/core/test_arx_disconnect_chaos.py:157-170`. Failure scenario: during arx disconnect, periodic state snapshots are dropped, not cached for replay.

3. `src/custos/cli/main.py:177` MED — `RunnerRiskConfig` is documented as live from spec, but runtime still uses defaults.  
   `_build_reconciler` constructs `RunnerNotionalCap(LocalCapConfig.from_spec({}, live=False))` at `src/custos/cli/main.py:177-183`; there is no later refresh from `state.last_spec.risk_config`. `docs/domain.md:104` says the daemon reads `risk_config` from the spec and changes take effect next loop. Failure scenario: an operator raises or lowers `fallback_breaker.max_notional` / `max_drawdown_pct` in `DeploymentSpec.risk_config`, but the runner continues enforcing the default breaker config.

**Confirmed strengths**

The core 04b drawdown flip is real: `_breaker_tick` calls `get_engine_status` per active spec and feeds summed `current_equity` into `FallbackBreaker.evaluate` at `src/custos/core/deployment_reconciler.py:293-306`.

The idempotence gate is correctly placed: `was_frozen` is captured before `evaluate` at `src/custos/core/deployment_reconciler.py:302`, and repeat flatten is skipped at `src/custos/core/deployment_reconciler.py:309-312`. The 60-tick chaos test asserts a single flatten call at `tests/core/test_arx_disconnect_chaos.py:197-217`.

The Decimal dataclass invariant covers the new money fields via `_reject_float_money` at `src/custos/core/engine_protocol.py:46-58`, with all three snapshot dataclasses invoking it at `src/custos/core/engine_protocol.py:83-124`.

Credential material is structurally excluded from `state_snapshot` payloads at `src/custos/core/state_snapshot.py:149-164`, and subject construction correctly routes through `build_subject` at `src/custos/core/state_snapshot.py:125-129`.

**Verification Notes**

I could not run the focused pytest set: plain `pytest` is not installed, and `uv run pytest ...` failed because the read-only environment could not initialize `/Users/wukai/.cache/uv`.

**Recommendation**

Fix cycle. The drawdown breaker runtime wire itself is solid, but the slice overclaims state snapshot runtime/WAL behavior and `RunnerRiskConfig` live semantics. Wire `StateSnapshotPublisher` from the runner lifecycle, use the WAL-backed telemetry publish path or revise the contract/tests, and either implement per-spec risk config refresh or correct the docs/close-out scope.
---

## Team-lead Independent Verification (lesson #C2 self-review 不豁免)

All 3 findings independently grep-confirmed at `d0dd537`:

- **HIGH-1 CONFIRMED**: `grep -rn 'StateSnapshotPublisher' src/ --include='*.py'` returns 1 hit only (the class definition at `src/custos/core/state_snapshot.py:109`). Zero wire in `src/custos/cli/main.py` — no import, no construction, no `publisher.run()` call. Runtime behavior: state snapshot code exists but is never started; runner deploys and heartbeats but publishes zero snapshots.
- **MED-2 CONFIRMED**: `state_snapshot.py:42-43` docstring explicitly says client "owns disconnect handling; publisher only cares that publish_fire_and_forget is awaitable and swallows disconnected calls". `test_arx_disconnect_chaos.py:157-170` uses `publish_telemetry_envelope` (WAL-backed telemetry path), not `StateSnapshotPublisher`. Test coverage for WAL is orthogonal to the publisher path.
- **MED-3 CONFIRMED**: `cli/main.py:178` `LocalCapConfig.from_spec({}, live=False)` and `cli/main.py:183` `FallbackBreakerConfig.from_spec({})` construct with empty dict at startup only. No `state.last_spec.risk_config` refresh anywhere. `docs/domain.md:104` says "daemon reads risk_config from the spec and changes take effect next loop" — actual behavior = defaults forever.

## Impact on Plan 04 close-out status

Plan 04 close-out claimed "红线 0.3 完整 runtime-wire 兑现". This is **partially accurate**:

- ✅ **Drawdown wire flip is real**: codex confirmed, safety-04b confirmed, team-lead confirmed. `_breaker_tick` → `get_engine_status` → `FallbackBreaker.evaluate(current_equity=...)` is a live runtime path.
- ❌ **State snapshot layer overclaimed**: code exists but never runs at runtime; WAL caching path is orthogonal to publisher. lesson #40 3-column red-line gate table should downgrade snapshot row from `runtime_wire=live` to `runtime_wire=code_ready + defer to follow-up wire task`.
- ❌ **RunnerRiskConfig live-from-spec overclaimed**: docs contract says live-from-spec, code uses defaults forever. Either code needs per-loop refresh OR docs need to acknowledge startup-only semantics.

## Follow-up Options (CEO decides)

- **A (fix cycle)**: Spawn runner-04b-fix to close 3 findings — wire publisher, either WAL-back publisher or revise contract, either refresh risk_config or fix docs. May unflip Plan 04 back to ⏳ during fix.
- **B (accept + follow-up plans)**: Merge as-is (04b squash already on main), add DEV entries acknowledging state snapshot + risk_config partial scope, spawn follow-up plans (e.g. Plan 10 = state snapshot runtime wire + risk_config live refresh). Plan 04 stays ✅ but red-line gate table gets amended.
- **C (partial fix in main session)**: Main-session fix HIGH-1 only (wire the publisher — small, ~10 LOC); defer MED-2 (WAL semantics) and MED-3 (per-loop refresh) to follow-up plan.

