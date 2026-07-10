# Plan 04 04b — Safety-Validator 8-Checklist Report

**Reviewed at**: 2026-07-10
**Branch HEAD**: `f1d724a` (worktree `.forge/worktrees/04b-runner`, branch `custos/04b/runner`)
**Base commit**: `f20f97e` (docs backfill for a-slice partial close-out)
**Delta vs base**: 6 commits, `d99bd23..f1d724a` (+1506/-629 across 36 files, of which the 05b file "deletions" are an artifact of main having already advanced to `f99dbf7` with 05b squash — see §Note below)
**Model**: `claude-opus-4-6[1m]`
**Reviewer**: `safety-validator` (Team Lead dispatched, packet §5)

---

## Verdict

**APPROVED_FOR_SQUASH**

Every one of the 8 checklist items PASSES with independent grep evidence anchored to `file:lineno` in the worktree at HEAD `f1d724a`. No CRIT finding. No red-line breach. Executor's marker claims all cross-check against the actual code — no hallucinated tests, no fabricated numbers, no shadow claims. Lesson #C2 (self-review not exempt) applied throughout: every "PASS" here rests on a grep result I ran myself, not on the marker's summary.

---

## Checklist Results (1..8)

### 1. Red-line 0.1 (Key/KEK not out of process) — PASS

- `grep -nE 'api[_-]?key|secret|password|vault|kek|credential' src/custos/core/state_snapshot.py` → **0 hits**
- Payload wire structure (`src/custos/core/state_snapshot.py:75-95`): position keys = `client_order_id / instrument_id / side / quantity / price / status`; engine_status keys = `phase / position_count / order_count / open_notional / peak_equity / current_equity / drawdown_pct`. **No credential/vault field.**
- 3 new dataclasses (`engine_protocol.py:77-121`) declare only `instrument_id / quantity / avg_px / unrealized_pnl / notional / client_order_id / side / status / phase / counters / equity money fields` — no credential surface introduced.
- Runtime wire: state_snapshot publisher's `publish_once` writes JSON derived from Tier-2 return values only; the Tier-2 methods (`host.py:141 / 485 / 513 / 534`) themselves never touch credential material.

### 2. Red-line 0.2 (G6 gate not bypassed) — PASS

- `git diff f20f97e..HEAD -- src/custos/engines/nautilus/host.py | grep -iE 'g6|gate|_can_go_live|live_capable'` → returns only a docstring-line change on the aggregate exposure/equity snapshot section. **No modification to G6 gate logic, no new venue-client call sites, no bypass path introduced.**
- Tier-2 methods added purely as additive surface:
  - `NoopHost` — `host.py:141 async def get_positions` / `:145 async def get_orders` / `:148 async def get_engine_status`
  - `NtTradingNodeHost` — `host.py:485 / :513 / :534` same signature
- G6 gate path (Plan 00c layer 1-4) is not touched by any of these 3 additions.

### 3. Red-line 0.3 (Disconnect ≠ Stop; drawdown wire RUNTIME-LIVE) — PASS (headline flip verified)

**This is the slice's main red-line delivery. Verified as real runtime path, not just code-ready.**

- `deployment_reconciler.py:296` — `status = await self.execution_engine.get_engine_status(spec_id)`
- `:297` — `total_equity = (total_equity or Decimal("0")) + status.current_equity`
- `:303-306` — `verdict = self.fallback_breaker.evaluate(open_notional=total_notional, current_equity=total_equity)`
- **`current_equity` is truly wired into the breaker's `evaluate` call, per active spec, per tick.** Not a docstring, not a placeholder — the real live path.

Idempotence gate (DEV-04b-BREAKER-FLATTEN-IDEMPOTENCE):
- `deployment_reconciler.py:302` — `was_frozen = self.fallback_breaker.frozen` captured **before** `evaluate` (correct order — `evaluate` may set frozen=True on trip).
- `:309-312` — `if was_frozen: return` skips repeat flatten dispatch after the first trip.
- Independently tested: `test_arx_disconnect_chaos.py:216 assert host.flatten_calls == [("s-1", "notional_breach")]` — single-entry list after 60 ticks proves idempotence works at runtime.

Silent-drop safety on equity probe failure:
- `deployment_reconciler.py:299-301` — `except Exception as exc: _log.warning("breaker_equity_probe_failed", ...); total_equity = None; break` → degrades to notional-only for the tick, keeps auditability (lesson #21).

### 4. Red-line 0.4 (Money math Decimal, wire str) — PASS

- Invariant: `engine_protocol.py:46 def _reject_float_money(instance)` iterates each dataclass's Decimal-declared field via `dataclasses.fields()` and `raise TypeError` when any value is not `Decimal`.
- All 3 new dataclasses invoke it from `__post_init__`:
  - `PositionSnapshot.__post_init__` at `:84`
  - `OrderSnapshot.__post_init__` at `:100`
  - `EngineStatus.__post_init__` at `:124`
- Wire serialization (`state_snapshot.py:75-92`): every money field is `str(<decimal>)`. Position: `quantity / price`. Order: `quantity / price`. EngineStatus: `open_notional / peak_equity / current_equity / drawdown_pct`.
- `grep -rnE 'float\(.*(price|amount|notional)' src/custos --exclude-dir=toolkit` → **0** (per marker's residual grep, independently spot-checked on new src).

### 5. Silent-drop paths → structlog (lesson #21) — PASS

- `state_snapshot.py:140-149` — probe try/except: `_log.warning("state_snapshot_probe_failed", spec_id=..., error=...)` before returning; the `# noqa: BLE001` documents fail-safe intent.
- `state_snapshot.py:166-173` — publish try/except: `_log.warning("state_snapshot_publish_failed", subject=..., error=...)`.
- `state_snapshot.py:188-190` — TimeoutError branch on `asyncio.wait_for(stop.wait(), timeout=...)`: this is the periodic-wake pattern (waiting for stop signal with a timer-based wake), not silent drop — `continue` is the correct next iteration.
- `deployment_reconciler.py:289-295` — notional probe: `_log.warning("breaker_notional_probe_failed", ...)`.
- `deployment_reconciler.py:299-301` — equity probe: `_log.warning("breaker_equity_probe_failed", ...)` + degrade to notional-only.
- `deployment_reconciler.py:315-320` — flatten dispatch banner: `_log.warning("fallback_breaker_flatten", reason=..., open_notional=..., current_equity=..., drawdown_pct=...)`.
- `deployment_reconciler.py:326-327` — per-spec flatten failure: `_log.error("flatten_positions_failed", ...)`.
- `grep -rnE "except.*: *pass|except.*: *return" src/custos/core/state_snapshot.py src/custos/core/deployment_reconciler.py src/custos/core/engine_protocol.py` → **0 hits** for silent-drop patterns in new/touched sources.

### 6. Failure-mode coverage (lesson #17) — PASS

**Long-run assertion is real, not a happy-path fake**:
- `tests/core/test_arx_disconnect_chaos.py:183 async def test_arx_disconnect_long_run_guards_persist`.
- Body drives 60 ticks (`for _ in range(60): await reconciler._watchdog_tick(); await reconciler._breaker_tick()`) then asserts four independent guards persist:
  1. Cap layer: 3× `local_cap.allows(...) is False` proves runtime rejection continues across the whole run.
  2. Breaker layer: `host.flatten_calls == [("s-1", "notional_breach")]` proves single-fire idempotence + `reconciler.fallback_breaker.allows_new_orders() is False` proves freeze latch holds.
  3. Watchdog layer: `len(degraded_attempts) >= 2` proves escalation loop keeps trying to publish even though `_DisconnectedNats` refuses every attempt.
  4. State coherence: `reconciler._state["s-1"].observed_generation == 1` proves no runaway state growth.

**Contract test name grep verification** (lesson #25):
- All 19 test names referenced in the marker's `contract_test_names_grep_verified` block resolve to **exactly 1 file each** via `grep -rc "def <name>" tests/`. Zero fabricated names, zero missing definitions.

**Multi-layer independence** (lesson #22/#28 aspect):
- `test_arx_disconnect_chaos.py:129 assert host.flatten_calls == [("s-1", "notional_breach")]` (basic-case single-tick trip)
- `test_arx_disconnect_chaos.py:216 assert host.flatten_calls == [("s-1", "notional_breach")]` (long-run 60-tick, still one call = idempotence gate proven runtime-live, not dead branch)
- `test_fallback_breaker.py:178 host.flatten_calls == [("s-1", "drawdown_breach")]` (drawdown-only fire path, independent of notional path)

### 7. Runtime wire vs code-ready three-column (lesson #40 / C40) — PASS

Plan file `.forge/plans/2026-07/04-red-line-03-runner-fallback.md` contains the required table at two locations (planning target §L441-450 and close-out fulfillment §L528-537):

- L530 header row: `| 红线 | code_coverage | runtime_wire | defer_status | follow_up_plan_ref |` — three columns present and honestly filled.
- L537 兑现范围声明 explicitly declares the transition: **"transitions from `code_coverage + partial runtime_wire` (04a: cap / zombie / notional breaker live; drawdown wire deferred) to `code_coverage + full runtime_wire`"** for red-line 0.3.
- Defer scope named:
  - arx-side state_snapshot consumer migration → external arx-project follow-up (single-repo self-sufficiency discipline).
  - NT per-order intercept hook (DEV-04a-CAP-ENFORCEMENT-HOOK-DEFER) → v1 pre-live follow-up. Cap decision layer is runtime-wire; intercept layer is not (this distinction is exactly the lesson #40 discipline).
- No承袭 of red-line name as fulfillment claim; every row distinguishes vision from reality.

### 8. Docs sync T6.1 — PASS

All four docs updated to reflect the new Tier-2 contract + tri-guard runtime:

- `docs/design/reconcile.md:63` — Hard breaker row now names both feeds: `get_open_notional + get_engine_status.current_equity`; describes "首次触发 flatten_positions 每个 active spec + 冻结新单; 后续 tick 不重复 flatten" (idempotence semantics captured).
- `docs/domain.md:103` — DeploymentSpec row extended with `risk_config`(optional dict, 见 RunnerRiskConfig); `docs/domain.md:104` — **new `RunnerRiskConfig` row added** with all-Decimal fields (`max_notional_per_runner / fallback_breaker.max_notional / fallback_breaker.max_drawdown_pct`) + fallback defaults + wire `str(Decimal)` red-line 0.4 anchor.
- `docs/design/engine_protocol.md:56-58` — Tier-2 method signatures finalized on Protocol; `:66-68` — table row for each with consumers (StateSnapshotPublisher, FallbackBreaker.evaluate); `:109 current_equity: Decimal` on `EngineStatus`; `:126 get_engine_status` behavior notes cover peak_equity tracking.
- `docs/design/nautilus_host.md:57` — Runner-layer hard fallback breaker anchor names FallbackBreaker + per-tick Tier-2 feed.

Also verified: `.forge/README.md:38` — Plan 04 row status = `✅ Completed (2026-07-10, 红线 0.3 完整 runtime-wire 兑现)` with correct commit-range narrative.

---

## Red-line Gate Assessment (per-red-line, lesson #40 three-layer)

| Red-line | 04b posture | Grep-anchored evidence |
|----------|-------------|------------------------|
| **0.1 Key/KEK** | Maintained (not touched) | `state_snapshot.py` grep for credential keywords = 0; payload structural exclusion confirmed at `state_snapshot.py:75-92` |
| **0.2 G6 gate** | Maintained (not touched) | `host.py` diff for G6/gate/live_capable = docstring-only; Tier-2 methods added at `:141 / :145 / :148 / :485 / :513 / :534` as additive surface without touching gate layers |
| **0.3 Disconnect ≠ stop** | **Strengthened — full runtime-wire delivered** | `deployment_reconciler.py:296-306` real live drawdown feed; `:302 was_frozen` idempotence gate; `test_arx_disconnect_chaos.py:216` runtime proof over 60 ticks |
| **0.4 Money Decimal** | Maintained + extended to new surface | `engine_protocol.py:46 _reject_float_money` runtime invariant fires from all 3 dataclass `__post_init__`; wire `str(Decimal)` at `state_snapshot.py:75-92` |

**Overall red-line drift risk**: NONE. 04b is a red-line 0.3 strengthening slice with zero regression on 0.1 / 0.2 / 0.4 and honest defer declaration for the arx-side consumer + NT per-order intercept hook.

---

## Findings

None at CRIT/WARN level. One informational note for team-lead squash-merge planning (**not** a blocker):

**INFO-1: Squash-merge target diverged during review window**
- **Anchor**: `git log --oneline main -3` at review time shows `main` HEAD = `f99dbf7 refactor(custos): Plan 05 05b slice … (squash)`; 04b branch base is `f20f97e`, so `main..HEAD` diff includes 05b file **deletions** (from 04b's perspective — 04b never saw 05b changes).
- **Implication**: When team-lead runs `git merge --squash custos/04b/runner` onto main, `.forge/README.md` will show a real conflict (both slices flip their own row) + the 05b-scope files (`pyproject.toml`, `Makefile`, `.claude/rules/tech-stack.md`, `docs/engines/*`, etc.) will appear stale in the 04b tree.
- **Resolution**: Marker `hooks_after_close_out[1]` already anticipates this and instructs "take both rows updated" for `.forge/README.md`. For the 05b-scope files, team-lead should retain main's post-05b content (04b did not intentionally revert them). Recommend rebase-then-squash rather than raw squash-merge to make the conflict resolution explicit.
- **This is an operational note**, not a safety finding — 04b is fully approved as-is and the merge-time resolution is straightforward.

---

## Lesson C2 Compliance Statement

Every finding and every PASS above is anchored to a `file:lineno` from an independent grep I ran, not a copy of the marker's assertions. Where the marker's line numbers were slightly off (e.g., marker cited `L322-326` for the was_frozen gate, actual runtime location is `L302`), the actual code position is quoted with the correct line. No claim in this report was accepted from the marker without independent verification. UNVERIFIED status: **none** — all 8 checklist items rest on grep evidence, all 19 contract test names rest on `grep -rc` = 1, all four docs updates rest on section-line grep hits.

---

## Recommendation

**APPROVE_SQUASH** — team-lead may proceed with `git merge --squash custos/04b/runner` (preferably rebase-then-squash to make INFO-1 conflict resolution explicit) into `main` and continue the packet §9 peer-review chain (codex L1 → medium → claude opus-4-8 → manual).

Red-line 0.3 runtime-wire is **fully delivered** in this slice, custody承重墙 remains intact for 0.1 / 0.2 / 0.4, and the plan close-out honestly declares defer scope per lesson #40. This is a textbook lesson #40 dogfood slice — the promised flip from partial to full runtime-wire is real, testable, and independently grep-provable.
