# Plan 08 manual peer review (codex L1 fallback)

- **Reviewer**: Execution Lead (main session) — manual fallback per lesson #19 fallback chain
- **Branch**: `custos/08-plan/runner` @ `5c6e655` (base `6373f50`, 4 commits)
- **Review timestamp**: 2026-07-10 SGT afternoon
- **Verdict**: **APPROVED_WITH_FOLLOW_UPS** (1 LOW-priority observation, non-blocking)
- **Fallback trigger**: codex CLI L1 attempted with the same defensive template that succeeded on other projects, but exited 0 with no lastmsg written and no assistant response in the log — same pattern as Plan 07's two codex attempts (see `DEV-07-CODEX-FALLBACK-CHAIN-EXHAUSTED`). gemini CLI not installed. Per lesson #19 fallback chain (codex×2 → gemini → manual peer review by main session), fell back to manual review.

---

## Summary

Plan 08 delivers real-strategy end-to-end acceptance for the ps SuperTrendStrategy, closes the Plan 06 remainder (Tracks 5-6), and lands a robust independent-clone-reproducible fixture mirror. Six focused spot-checks were run against the branch head; five pass unconditionally and one carries a LOW-priority docstring-wording observation.

The core red-line-0.1 credential leak-negative test is a **modeling case** for the wider codebase: it correctly uses `capfd` (not `caplog`) to catch structlog's `PrintLoggerFactory` file-descriptor writes, asserts sentinel values are absent after a real deploy path executes, and comments the intent inline referencing red-line 0.1 explicitly. The T5.2 testnet split (unconditional routing-wire assertion + opt-in real deploy assertion) is a clean partial+manual verification pattern per Plan 06 T5.2 precedent, with three-way `_skip_unless_provisioned` (enable env + vault root + credential id) that each name the manual-verification path.

Plan 06 close-out is signed at the top-level Status line 3 (✅ Completed) with a full close-out section at line 509 (`### Plan 06 整 close-out (2026-07-10, Plan 08 承接)`); the historical 06a partial-close-out subsection at line 487 is preserved as a historical record, correctly distinct from the full close-out. No internal inconsistency in the parent-child close-out order.

The runner-executor-08-2 respawn (after runner-executor-08 died from ECONNRESET at 2026-07-10T07:28 UTC before producing any commit) landed 4 clean commits with `make verify` and `make verify-nt` both green (299 pass + 2 skip on each). The two skipped tests are `test_real_supertrend_testnet_deploy` (DP1 partial+manual per DEV-08-T5.2-MANUAL-VERIFICATION) and the pre-existing `test_wire_shapes.py` (Plan 01 deferred item, not introduced by Plan 08).

## Spot-check results

### A: 3 CEO ratifications faithful — **PASS**

Grep `.forge/plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md`:

| Plan line | DEV entry | Ratified option | Match CEO decision? |
|-----------|-----------|-----------------|---------------------|
| 400 | `DEV-08-TESTNET-CREDENTIAL-SOURCE` (DP1) | `Decision (CEO 2026-07-10): A — real Binance testnet credential via credential_vault sops+age` | ✅ Match |
| 425 | `DEV-08-ARX-WEB-SIDECAR-FOLLOWUP` (DP2) | `Decision (CEO 2026-07-10): A — independent arx-side follow-up plan (Plan 08 T6.1 documents debt only)` | ✅ Match |
| 441 | `DEV-08-SANDBOX-FAULT-INJECTION` (DP3) | `Decision (CEO 2026-07-10): A — golden path only` | ✅ Match |

All three carry rationale text that references the drafter's argument or CEO's independent judgment (T5.1 already substantial e2e; cross-repo coordination overhead too high; etc.).

### B: T5.1 credential leak-negative (`test_credential_not_in_telemetry_payload_supertrend`) — **PASS — modeling case**

`tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py:246-288`:

- Uses `capfd` (file-descriptor level capture) not `caplog` — necessary because structlog's `PrintLoggerFactory` writes through fd, not stdlib logging. Docstring lines 262-264 explicitly explain this.
- Deploys through `NtTradingNodeHost().deploy(_spec(), _credential())` — real deploy path, not a mock.
- Reads captured output AFTER deploy completes: `captured = capfd.readouterr(); combined = captured.out + captured.err`.
- Asserts `_SENTINEL_API_KEY not in combined` AND `_SENTINEL_API_SECRET not in combined` — two independent assertions, each with a red-line-0.1 breach message referencing `code_hash_skipped_sandbox`, `nt_deploy_started`, `nt_observability_attached` as the observable sinks that must not leak.
- Failure-mode wording is honest: "a new sink was added without hooking through the shared desensitisation processor" — the test is designed to catch future sink additions that bypass the shared processor.

This is one of the strongest failure-mode tests I've seen in this codebase.

### C: DEV-08-RISK-CONTROLLER-ACTIVATION-PROXY decision — **PASS (legitimate proxy)**

Executor changed the plan's original assertion `strategy._risk_controller is not None` to a config-layer proxy because the runtime activation happens in `on_start` (not `__init__`), and the monkey-patched `run_async` parked scenario doesn't execute `on_start`. The proxy asserts the production-tier risk config values landed (max_daily_loss=0.05 / max_drawdown=0.15 / consecutive_loss_pause=5).

This is a **legitimate proxy**, not a downgrade:

- Runtime activation coverage is provided by ps-side `test_supertrend_risk_controller_enabled.py` per Plan 06 06a Track 2, which the executor correctly cites.
- The custos-side test now covers a different-but-related invariant: the production-tier risk config values reach the strategy via the config plumb path. Missing this proxy in custos would have left the config plumb path untested.
- The DEV entry is honest about the trade-off: it names the specific NT lifecycle constraint that made the runtime assertion infeasible, and it names the successor test that does cover runtime activation.

Judgment: better than blindly executing the original plan assertion and getting a false green.

### D: T5.2 testnet routing wire (unconditional) + opt-in deploy (skip-if-not-provisioned) — **PASS with LOW-priority observation**

`tests/engines/nautilus/test_real_supertrend_e2e_testnet.py`:

- **Routing wire** (`test_real_supertrend_testnet_routing_wire`, line 179): unconditional — no network, no vault. Asserts (1) `isinstance(exec_cfg, BinanceExecClientConfig)`, (2) `exec_cfg.environment is BinanceEnvironment.TESTNET` (with a red-line-0.2 breach comment naming the failure mode as testnet-intent-routed-to-live), (3) `exec_cfg.account_type == BinanceAccountType.USDT_FUTURES`, (4) `exec_cfg.us is False` (rejects Binance US routing). Four substantive assertions. This is the wire-level guardrail that catches config-builder drift without needing a real credential.

- **Opt-in deploy** (`test_real_supertrend_testnet_deploy`, line 220): `_skip_unless_provisioned` at line 157 with three checks — `CUSTOS_T52_TESTNET_ENABLE == "1"` + `_ENV_VAULT_ROOT` set + `_ENV_CREDENTIAL_ID` set. Each skip message references `DEV-08-T5.2-MANUAL-VERIFICATION` for the operator handoff. When provisioned, the test asserts container_id round-trip + real testnet credential values absent from captured output (cross-mode desensitisation).

**LOW-priority observation FU-08-1** (record as future-plan-drafting note; non-blocking for landing): the T5.2 test docstrings do not use the exact wording "testnet only — mainnet key would violate red-line 0.1" as suggested in the packet dispatch. The equivalent intent is expressed via:
- Env var name `CUSTOS_T52_TESTNET_ENABLE` (testnet-only opt-in flag)
- Line 158 docstring "the operator hasn't opted into the testnet infrastructure"
- Line 202-207 unconditional assertion `exec_cfg.environment is BinanceEnvironment.TESTNET`
- DEV entry text referencing sandbox key non-real per mandatory-rules §5

The semantic is fully covered; the docstring wording is looser than the packet spec but not misleading. Suggested follow-up: on next docstring pass, add one sentence to `_skip_unless_provisioned` docstring or `test_real_supertrend_testnet_deploy` docstring explicitly stating "operators must provision a Binance TESTNET credential; a mainnet credential in this vault path violates red-line 0.1 and is a runtime user-error, not a test infrastructure concern."

### E: Fixture mirror provenance (`tests/fixtures/real_supertrend/PROVENANCE.md`) — **PASS (excellent), 1 UNVERIFIED**

PROVENANCE.md is comprehensive (60 lines):

- **Purpose**: names option iii as the drafter's recommendation + explains Apache-2.0 independent-clone reproducibility as the driver
- **Source pin**: `philosophers-stone develop` @ `3443e969bec5988276e96694806d1602b61e75fc` with upstream commit subject
- **File mapping**: 3 fixture files → 3 upstream paths (strategy.py + __init__.py + config.yaml)
- **Runtime resolution**: via `custos.engines.nautilus.strategy_loader.load_strategy_class`, imports resolve through vendored toolkit `sys.path` bootstrap (no ps sibling checkout at test time)
- **Drift discipline**: intentionally NOT auto-synced; bump is a deliberate maintenance step (copy 3 files + update commit field + re-run assertions); assertions surface material change as red — intended failure mode
- **Not a runtime import**: nothing under `src/custos/` imports from `tests/fixtures/real_supertrend/` (loaded via filesystem path, not Python import system)

**UNVERIFIED**: the claim that ps commit `3443e969bec5988276e96694806d1602b61e75fc` exists cannot be verified from this worktree (would require philosophers-stone repo access). If a workspace operator with ps access spot-checks this later, that closes the loop; not a blocker for landing.

### F: Plan 06 close-out parent-child order — **PASS (structurally clean)**

`.forge/plans/2026-07/06-ps-supertrend-migration.md`:

- **Line 3 top-level Status**: `✅ Completed (2026-07-10; 06a slice landed 306b9e5 for Tracks 1-4, Plan 08 landed remainder Tracks 5-6 and this close-out)` — full Plan 06 completion signed at Plan 08 T6.2
- **Line 482** `## 完成报告 (Close-out Report)` — top-level close-out section header
- **Line 487** `### 06a partial close-out (2026-07-09)` — historical partial subsection, preserved intact from 06a landing (retains its ⚠️ Partial wording as a historical record of the state at 2026-07-09)
- **Line 502** `### Plan 06 完整 close-out 待办 (Plan 08 承接)` — the "outstanding items to be closed by Plan 08" list (referenced from 06a)
- **Line 509** `### Plan 06 整 close-out (2026-07-10, Plan 08 承接)` — the actual full Plan 06 close-out signed by Plan 08 T6.2

The parent-child order is preserved: Plan 06 close-out is signed BEFORE Plan 08 close-out inside the same T6.2 commit `5c6e655`. The historical partial-06a subsection uses a subsection heading level (`###`) and clear date suffix, so it reads as a historical record rather than a contradicting current status.

## Cross-cutting observations

- **runner-executor-08-2 was a respawn** after `runner-executor-08` (opus) died from ECONNRESET at 2026-07-10T07:28 UTC before producing any commit. The respawn used the same opus config + same worktree base `6373f50`; zero orphan state, zero rework. Recorded as an operational note; no scope drift.
- **Language Policy compliance**: pre-commit hook `5c01cdb` accepted all 4 commits. New Python test files, PROVENANCE.md, and T6.1 docs section are English. Chinese verbatim quotes from Plan 06 headings preserved as verbatim (Plan 06 pre-dates Language Policy per project convention).
- **Lesson #C2 self-review discipline**: the close-out marker's `constraints_honored` array attaches an evidence anchor per lesson honored. Lesson #25 anti-fabrication holds: 4 contract test names in the marker exactly match the 4 `def test_*` / `async def test_*` lines in the 2 test files (grep-verified 2+2 = 4).
- **Lesson #40 red-line gate 3-column**: the marker's red-line gate table correctly distinguishes `code_coverage` per red line with `runtime_wire` acknowledgement of what the parked-monkeypatched deploy path can + cannot verify (T5.1 credential leak-negative is a real assertion; T5.2 real-session testnet order emission is partial+manual per DEV-08-T5.2-MANUAL-VERIFICATION).
- **Failure-mode independence**: sandbox credential leak-negative test uses `capfd` at fd level; sandbox risk-controller proxy asserts config-plumb values; T5.2 wire routing asserts config-builder never returns live-endpoint for testnet intent. Three independent guards for three different failure modes.
- **Red-line 0.4 preservation**: 4 red-line grep gates on branch head — 0.1 = 0 hits, 0.2 = 0 hits, 0.3 = 0 hits, 0.4 = 5 hits (all in vendored toolkit `shared/warmup/snapshot.py` — pre-existing 06a legacy, Plan 08 diff introduces 0 new hits per `git diff 6373f50..5c6e655 -- '*.py' | grep -cE '^\+.*float\(.*(price|amount|notional)' = 0`).

## Verdict rationale

Verdict: **APPROVED_WITH_FOLLOW_UPS** (1 LOW-priority docstring-wording observation, non-blocking).

All 3 CEO ratifications are faithfully recorded with correct option letters + rationale text at correct plan lines (400 / 425 / 441). The T5.1 credential leak-negative test is a modeling case for the codebase — correctly using `capfd` for structlog's `PrintLoggerFactory` fd writes, asserting sentinel values absent AFTER real deploy path executes. The T5.2 split (unconditional routing wire + opt-in real deploy) is a clean partial+manual verification pattern per Plan 06 T5.2 precedent. The `DEV-08-RISK-CONTROLLER-ACTIVATION-PROXY` decision is a legitimate proxy of the runtime activation invariant, honestly documented, with the runtime coverage correctly cited to ps-side `test_supertrend_risk_controller_enabled.py` per 06a Track 2. Plan 06 close-out order (parent-child) is structurally clean at plan file lines 3 (top-level) + 487 (historical partial) + 509 (full close-out).

The one LOW-priority observation is that T5.2 docstrings do not use the exact wording "mainnet key would violate red-line 0.1" as suggested in the packet spec; the semantic is fully covered via env var naming + unconditional assertion `environment is BinanceEnvironment.TESTNET` + DEV entry reference, but the docstring literal wording is looser than the packet spec. This is non-blocking for landing; can be tightened on next docstring pass.

Manual peer independence caveat: this review is by the same party as the Slot 2 executor spawn (Execution Lead). Independence signal is weaker than a genuine second-opinion codex report would provide. The `DEV-08-CODEX-FALLBACK-CHAIN-EXHAUSTED` deviation records this trade-off explicitly (mirroring the Plan 07 pattern). Plan 08's substantive scope — real e2e integration tests + docs + close-out cascade — was largely verifiable by grep + Read (test names + assertion structure + fixture provenance + CEO rulings + status flip), and the two independent grep gates (language pre-commit hook + red-line 0.4 float-money-math no-new-hits) already caught 0 violations.

Safe to squash-merge.

---

*Manual peer report by Execution Lead, custos /forge:execute-team Batch 1 Slot 2 codex L1 fallback, 2026-07-10 SGT.*
