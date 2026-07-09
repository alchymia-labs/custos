# 同行审查报告 — Plan 04/05/06 — Plan Review (L1 Codex)

> **Source**: L1 codex peer review (lesson #10/#12 完整模板: `timeout 1200 codex exec -c model_reasoning_effort=medium -o LASTMSG --sandbox read-only < /dev/null`)
> **Codex version**: 0.142.0
> **Run**: 2026-07-09
> **Sandbox**: read-only (codex 无法直接写 target, 由 Planning Lead 从 LASTMSG copy 到本文件)
> **Report type**: Plan Review (NOT Code Review) — 审的是 3 份 refined plan 文件本身

## Verdict (per plan)
- Plan 04: APPROVED_WITH_FOLLOW_UPS
- Plan 05: APPROVED_WITH_FOLLOW_UPS
- Plan 06: REQUEST_CHANGES

## Cross-plan verdict
- Overall readiness for execute-team: NEEDS_FIX
- Preferred grouping (§12): other — G1 Plan 05 → G2 Plan 04 → G3 Plan 06

## Net-new findings (angles internal reviewers missed)

### CRITICAL
- None.

### HIGH
- HIGH-1: Plan 06 task order is internally contradictory: T1.1's loader spike requires the vendored toolkit from T3.2, but the progress table schedules T1.1 before T3.2. The fallback "temporary sys.path 指 ps 仓" proves a different path than production vendored-toolkit loading. Evidence: `06-ps-supertrend-migration.md:198`, `:200`, `:242`, `:323`.

- HIGH-2: Plan 06 "registry-mode" error semantics are underspecified. The plan says `strategy_registry_name` is post-load validation, not the primary load path, but also expects unknown registry names to raise registry.py's `ValueError`. If custos does not call `registry.create_strategy(name=...)`, that error path is not naturally reachable. Evidence: `06-ps-supertrend-migration.md:108`, `:207`, `:209`, `:211`.

- HIGH-3: The handoff packet's default serial order runs Plan 06 before Plan 04, which is backwards for risk. Plan 04 is the explicit red-line 0.3 live hard blocker; Plan 06 only soft-depends on Plan 04 for the complete three-layer story. Prefer 05 → 04 → 06. Evidence: `04-red-line-03-runner-fallback.md:8`, `:9`; `06-ps-supertrend-migration.md:8`; `04-05-06-execute-team-packet.md:244`.

### MEDIUM
- MED-1: Plan 04 claims snapshot dataclasses reject float money values, but the specified implementation is plain frozen dataclasses with annotations only. Python dataclasses do not enforce `Decimal`; specify `__post_init__` validators or remove the rejection claim. Evidence: `04-red-line-03-runner-fallback.md:153`, `:161`, `:176`, `:392`.

- MED-2: Plan 05 T1.1 is too large for the stated task split rule: 14 source files, 31 test imports, pyproject, and whole-suite green only at the end. Split it or mark it as an explicit approved big-bang exception with `git status --short` + `make verify` before commit. Evidence: `05-structural-refactor-engine-abstraction.md:40`, `:220`, `:255`, `:256`.

- MED-3: Plan 06 `DEV-06-TOOLKIT-HASH-SCOPE` is a red-line 0.2/G6 boundary decision but is recorded as a drafter decision, not a CEO decision point with alternatives and wait state. Evidence: `06-ps-supertrend-migration.md:119`, `:120`, `:378`, `:419`.

- MED-4: Plan 05's third CEO point lacks both options. `DEV-05-TOOLKIT-LOCATION` records one drafter decision and CEO ratify, but should include the rejected alternative, recommendation, and wait state. Evidence: `05-structural-refactor-engine-abstraction.md:481`, `:499`, `:501`, `:503`.

### FOLLOW-UP (non-blocker)
- FU-1: Plan 04 should add close-out evidence for dataclass Decimal validators if MED-1 is fixed via runtime invariant checks. Evidence: `04-red-line-03-runner-fallback.md:356`, `:369`, `:370`.

- FU-2: Plan 06 should add a NEW credential-not-in-logs/telemetry/status negative test. Current coverage relies on existing regressions and e2e flow assertions. Evidence: `06-ps-supertrend-migration.md:281`, `:377`, `:351`, `:364`.

## Verification of internal reviewer findings

### intra-plan-reviewer HIGH-1 (host.py 双 modify)
- Concur, but prefer serial order 05 → 04 → 06 instead of handoff's 05 → 06 → 04.
- Evidence: `04-red-line-03-runner-fallback.md:212`; `06-ps-supertrend-migration.md:158`; `04-05-06-execute-team-packet.md:244`.

### intra-plan-reviewer HIGH-2 (domain.md:103 双 modify)
- Concur. Resolution: Plan 04 first adds `risk_config`/`RunnerRiskConfig`, then Plan 06 rebases and appends `strategy_registry_name`/`nautilus_config`.
- Evidence: `04-red-line-03-runner-fallback.md:235`; `06-ps-supertrend-migration.md:182`.

### authority-reviewer red-line drift risk = LOW
- Concur. No semantic weakening found.
- Missed drift-adjacent risk: Plan 06 toolkit hash scope is well argued, but should be elevated because it defines what sits outside per-deploy G6 hash. Evidence: `06-ps-supertrend-migration.md:378`, `:419`.

## Verdict rationale
Plan 04 and Plan 05 are close enough to proceed with follow-ups. Plan 04 needs executable Decimal invariants rather than annotation-only contracts. Plan 05 is acceptable as a controlled rename, but T1.1 needs either a split or an explicit big-bang exception gate.

Plan 06 needs changes before execute-team. The vendoring/loader order and registry-mode semantics are not tight enough for a cross-repo strategy migration on the G6 and credential boundary. Fix those, add the credential leak-negative test, and run the batch 05 → 04 → 06.
