# Cross-Plan Round 2 Review (Claude, opus-4-7[1m])

**Reviewed at**: 2026-07-10
**Baseline**: Plan 11 fix `5287486` + Plan 12 fix `2bae32b`（on top of R1 review `.forge/reviews/2026-07/cross-plan-11-12-review-claude.md`）
**Reviewer scope**: R1 cross-plan finding verification + fresh cross-plan drift scan after both fixes.

## Verdict

**APPROVED_WITH_FOLLOW_UPS** — All 14 R1 cross-plan findings (2 C / 5 H / 5 M / 2 L) have visible textual resolutions with cross-plan evidence. Zero blocking new finding surfaced in R2. Three non-blocking follow-ups (all serialization / handoff-artifact / housekeeping) recorded below.

- Blocker (C): 0
- New High: 0
- New Medium: 2 (handoff staleness + `test_vault_put_never_logs_secret` capture scope after H4 flip)
- New Low: 2 (failure-mode count off-by-one 22 vs "21"; CHANGELOG "single-file" wording precision)
- Execute-team dispatch: green with the checklist in §"Final execute-team dispatch recommendation" below.

---

## R1 cross-plan finding verification table

| R1 Finding | Fix status | Cross-plan evidence |
|------------|------------|---------------------|
| **Cross C1** — Plan 12 Dockerfile ENTRYPOINT contradicts DP5 + violates Plan 11 clean-break | ✅ | Plan 12 line 246 `ENTRYPOINT ["arx-runner", "start"]` (Task 2 impl) + line 149 File Inventory + `tests/test_docker_entrypoint_help.py` added (line 169); verify-release.sh line 312 `docker run --rm ... --help` + line 314 non-root probe (FM2 Layer 3 alive). Cross-refs Plan 11 T8 `[project.scripts].arx-runner = "custos.cli.subcommands:main"` line 448 — same entry name, no drift. |
| **Cross C2** — Plan 11 three-way DeprecationWarning contradiction | ✅ | `grep DeprecationWarning` in Plan 11 = 4 hits, all **negative statements** (`no DeprecationWarning bridge`) at lines 69 / 89 / 145 / 529 / 551. Zero positive assertions. `grep coexistence` = 3 hits, all negations (`no coexistence`). Line 116 File Inventory: `tests/test_credential_vault_sops.py` deleted (legacy). Line 117 not present as pre-fix `test_deprecated_warning_on_old_entry.py` row. Progress row line 551 T8 Notes: `sys.exit(2) + one-line pointer` — no DeprecationWarning. Verification checklist line 529: `exits code 2 with arx-runner start pointer + no DeprecationWarning bridge`. |
| **Cross H1** — Plan 12 T5 CHANGELOG omits Plan 11 breaking items; T9 stale claim | ✅ | Plan 12 T5 Step 3 (lines 331-337) explicitly expands 0.2.0 entry: `### Removed (BREAKING — Plan 11)` + `### Changed (BREAKING — Plan 11)` + `### Added (Plan 12 additive)`. Line 336: "T5 责任 = 整合 Plan 11 (breaking) + Plan 12 (additive)". Plan 11 T9 File Inventory does NOT list `CHANGELOG.md` (only in header discussion at line 27 as gate content, and at lines 502/531 as inspection reference). `grep 'CHANGELOG\.md' 11-*.md` = 0 hits in File Inventory / Actions section. |
| **Cross H2** — verify-release.sh dead FM2 Layer 3 | ✅ | Plan 12 T4 Step 3 verify-release.sh (lines 300-315): appended `docker run --rm --help` (line 312) + non-root inspect probe (line 314). Aligned with Plan 12 line 155 File Inventory description and FM2 Layer 3 claim (line 185). |
| **Cross H3** — Plan 11 WAL default retargeting has no owning Task; DEVIATION stale coexistence | ✅ | Plan 11 T7 File Inventory row for `subcommands/start.py` line 109: explicit `DEFAULT_WAL_PATH = Path.home() / ".arx" / "state" / "telemetry-wal.db"` and `DEFAULT_ENROLLMENT_PATH = Path.home() / ".arx" / "enrollment.json"`. T7 Step 3 line 415 restates module-level defaults + `DEFAULT_VAULT_DIR`. Stale coexistence DEVIATION row rewritten line 562: "**`~/.arx/` is the sole namespace.** `~/.custos/` retired entirely per CEO clean-break directive (2026-07-10)". Test at line 407: `test_start_default_paths_target_arx_namespace` C1/H3. |
| **Cross H4** — Plan 12 Dockerfile missing VOLUME/HOME/passwd | ✅ | Plan 12 Dockerfile T2 Step 3 (lines 237-247): `RUN useradd -u 1000 -m -d /home/custos custos` + `ENV HOME=/home/custos` + `VOLUME ["/home/custos/.arx"]` + `USER 1000:1000` (order preserved: user create → HOME → COPY → VOLUME → USER). Plan 11 T9 owns `docs/ops/05-deployment.md` (T9 File Inventory line 493). Plan 12 T9 §3 references docker mount pattern via inspection-only cross-reference (line 530). No overlap. |
| **Cross H5** — pyproject.toml merge coordination, SHA gate, no-parallel | ✅ | Plan 12 header line 10 adds full **Cross H5 Strict serial merge protocol** block: HARD PRECONDITION + SHA gate `git log --oneline | grep 'plan 11 t8'` + `grep '"arx-runner"' pyproject.toml` + explicit "Plan 12 does NOT run in worktree parallel with Plan 11". Plan 12 header line 12 keeps `multi_session_scope: false` consistent. Plan 11 line 27 also carries this from its side. |
| **Cross M1** — README.md three-way modification risk | ✅ | Plan 12 T9 §3 bullet 3 (line 530): "T5 已处理; T9 只做 inspection-only 复检, 无追加 edit; 避免 lesson #16 三方修改冲突". Plan 11 T9 owns Quick Start + Upgrade section (line 118). |
| **Cross M2** — Plan 11 T9 ADR-014 cross-repo write | ✅ | Plan 11 T9 line 495 rewritten: "**workspace-only edit**... this file lives in `the-alephain-guild/codex/`, OUTSIDE the custos repo. Independent-repo executors (fresh `git clone custos`) do NOT see this path and MUST skip this step; record the skip in the plan close-out follow-up list. Workspace executors commit the ADR edit in a **separate commit outside the custos-repo**, `git add <specific-file>` per `mandatory-rules.md` §6". Explicit boundary + `git add <specific-file>` cite. |
| **Cross M3** — DP5 wording drift | ✅ | Plan 12 line 629 lesson #35 row updated to "**resolved** (Cross M3 fix — 与 line 101 DP5 header 'RESOLVED' 一致)". Line 103 DP5 header also **RESOLVED**. Deviation log entry at line 594 confirms wording sync. |
| **Cross M4** — Version tag semantics + BREAKING prefix | ✅ | Plan 12 T5 Step 3 (lines 333-334) explicitly uses `### Removed (**BREAKING — Plan 11**)` + `### Changed (**BREAKING — Plan 11**)` markers. arx-side pin at line 117 changed to `~=0.2.0` (H4 landed) with explicit "pip resolve 自动升 minor 静默破坏 client" rationale. |
| **Cross M5** — fanout list incomplete | ✅ | Plan 12 line 629 lesson #35 row fanout list expanded to: `pyproject.toml + Dockerfile + verify-release.sh + release.yml + docs/lts-commitment.md + docs/ops/05-deployment.md + docs/design/03-implementation.md + README.md + CHANGELOG.md`. All 9 files enumerated. Matches R1 request. |
| **Cross L1** — T5 test_changelog_exists.py optional | ⚠️ Partial | Plan 12 T5 Step 2 line 329 still keeps "**可选** `tests/test_changelog_exists.py`". Fix commit `2bae32b` did not flip to required; Plan 12 T9 verification checklist line 553 (`## [0.2.0] entry 完整`) offers indirect check via manual grep. Non-blocking but under-fixed. |
| **Cross L2** — Plan 11 T9 file inventory near-duplicates lines 441-446 | ✅ | Lines 441-446 in current Plan 11 are inside T8 Step 3 (pyproject.toml rewrite code block + main.py rewrite code block) — no duplicated 3-item block. Fix commit message (`5287486`) confirms "H2: Task 9 body deduped (deleted 3 near-duplicate bullets in Files section)". |

**Round 1 net**: 12 ✅ green + 1 ⚠️ partial (L1, non-blocking) + 1 stale artifact concern (see M-R2-1 below).

---

## New cross-plan findings (R2)

### M-R2-1 — Handoff packet stale post-fix; merge-conflict prevention checklist not landed

**Where**:
- `.forge/handoff/2026-07-team-full-loop/custos-handoff-packet.md`:
  - Line 12 `Base commit (custos): 45c62e7` — pre-Plan 11/12 fixes (fix commits are `5287486` + `2bae32b`).
  - §17 Parallel Execution Guide (line 291): describes G1 "script name 决定（`arx-runner` 主 + `custos` deprecated）供 G2 消费（DP5 soft dep）" — **stale**: DP5 is now **RESOLVED** (Plan 12 line 103), no `custos` deprecated entry exists (Plan 11 clean-break).
  - §18 Acceptance Criteria (line 306): "`python -m custos ...` 仍可运行 + `DeprecationWarning` 到 stderr" + "14 个失败模式契约测试" — **stale**: Plan 11 now says clean-break (`sys.exit(2)`, no DeprecationWarning) and failure-mode table has 22 rows (or 21 per Plan 11 own count, see L-R2-1).
- R1 review `.forge/reviews/2026-07/cross-plan-11-12-review-claude.md` lines 278-296 defines a 15-item **Merge conflict prevention checklist** intended as a hand-off to execute-team. This checklist is **not** in the handoff packet §17 nor elsewhere in the `.forge/handoff/` tree.

**Problem**: Execute-team dispatch that reads only the handoff packet (per Trust Layer H8 in packet §0) will consume the **pre-fix** narrative — expecting DeprecationWarning + 14 tests + script name TBD — and diverge from the actual post-fix plan text. The 15-item merge-conflict checklist that R1 explicitly framed as "hand-off to execute-team" would be silently omitted.

**Fix (before execute-team dispatch)**:
- Option A (preferred): main session issues a **handoff-packet supplement** (`.forge/handoff/2026-07-team-full-loop/custos-handoff-packet-supplement-r1-fix.md`) with (1) updated base commit `5287486` + `2bae32b`, (2) reference to the two fix commits, (3) verbatim copy of the 15-item merge-conflict checklist, (4) revised §17 Parallel Execution Guide reflecting DP5 RESOLVED + clean-break wording, (5) revised §18 Acceptance Criteria reflecting 22 failure modes + `sys.exit(2)` behavior.
- Option B (heavier): rebuild the full handoff packet with new baseline commit.

**Non-blocking** because both fix commits are on `main` and the plan files themselves are the ultimate source of truth per Trust Layer H8 §2 signed artifacts; execute-team can read Plan 11/12 directly. But without the supplement, executor onboarding via handoff packet requires manual cross-check.

---

### M-R2-2 — Plan 11 T5 `test_vault_put_never_logs_secret` capture scope inconsistent with H4 stdlib-logging flip

**Where**:
- Plan 11 T5 Step 1 line 342: `test_vault_put_never_logs_secret: capture structlog output, assert raw --api-secret value never appears in any log record`.
- Plan 11 T5 Step 3 line 355 (H4 fix): `**H4 audit event via stdlib logging** (not structlog): _log = logging.getLogger("custos.credential_vault")...` — the audit path is now stdlib logging, not structlog.
- Plan 11 Verification checklist line 533: "No `--api-secret` value appears in any structlog output (verified by `test_vault_put_never_logs_secret`)" — still says structlog.

**Problem**: After H4 fix flipped the audit event from structlog to stdlib logging, the test description in Step 1 + verification checklist still restricts capture to structlog. If executor takes Step 1 literally, the test would use `structlog.testing.capture_logs` (or similar) and **miss** any accidental leak in the stdlib logger. The stdlib audit-event path is where the credential is passed through — the test should capture **both** structlog and stdlib (via `caplog`) to be truly "any log record".

**Fix**: Plan 11 T5 Step 1 line 342 — rewrite the test description to: "capture **both** `structlog.testing.capture_logs` and pytest `caplog` (stdlib `logging`), assert raw `--api-secret` value never appears in any record from either sink". Verification checklist line 533 — rewrite: "No `--api-secret` value appears in any log output (structlog + stdlib caplog)".

**Non-blocking** because the intent is clear from Step 3 line 355 (H4 fix landed) and executor can reconcile at TDD time, but the letter of the test description is now stale.

---

### L-R2-1 — Failure-mode count off-by-one (22 rows vs "21 failure modes")

**Where**:
- Plan 11 Failure Mode Coverage Contract table (lines 133-156) — I counted 22 test-name rows via `awk /^## 失败模式覆盖契约/,/^## 实现任务/ | grep -c '| \`?test_'` = **22**.
- Plan 11 line 158 narrative: "All **21** failure modes are code-level tests".
- Plan 11 Verification checklist line 530: "All **21** failure-mode contract tests present and green".

**Problem**: Count-off-by-one. The C3 remediation added 3 `PerKeyVault` rows (lines 154-156) but the narrative summary at lines 158 + 530 still says 21. The fix commit message (`5287486`) says "21 failure modes are code-level tests" narrative was updated from 14 → 21, but likely miscounted (14 original + 7 review-driven = 21 in the commit message, but the actual added-in-table count is 8, giving 22).

**Fix**: Plan 11 line 158 + line 530 — change "21" to "22". Plus additional cross-cutting `test_vault_put_reuses_arx_dir_0700` (L3 fix, line 420) which is a 23rd test but is a shared-state invariant test not in the failure-mode contract table (separate category).

**Non-blocking** because executor greps by test-name, not by count. Housekeeping only.

---

### L-R2-2 — Plan 12 T5 CHANGELOG "single-file → per-key .enc" wording under-precise

**Where**: Plan 12 T5 Step 3 line 334: "`### Changed` (**BREAKING — Plan 11**): state namespace `~/.custos/` → `~/.arx/`; **vault storage model single-file → per-key `.enc`**".

**Problem**: "single-file" is technically ambiguous — the legacy `SopsAgeVault` was a **single sops file containing multiple credentials in one JSON**. External readers of the CHANGELOG may read "single-file" as "single-per-key" (the new state) since the new model is also "one file per key". A clearer phrasing is "multi-credential-in-one-JSON sops file → per-key `.enc` files".

**Fix**: Plan 12 T5 Step 3 line 334 — rewrite "single-file → per-key `.enc`" to "multi-credential-in-one-JSON sops file → per-key `.enc` files" (matches Plan 11 line 88 wording).

**Non-blocking** — semantic content is correct; wording precision only.

---

## Cross-plan consistency spot checks

| Check | Method | Result |
|-------|--------|--------|
| `token_hash` field name single source | `grep 'token_hash\|token_sha256' 11-*.md 12-*.md` | Plan 11: 5 hits `token_hash`, 0 `token_sha256`. Plan 12: 5 hits `token_hash`, 1 `token_sha256` inside the deviation log entry (documenting fix). ✅ Wire name aligned. |
| Script entry name single source | `grep 'custos.cli.subcommands:main\|"arx-runner"' 11-*.md 12-*.md` | Plan 11 T8 line 448 = `arx-runner = "custos.cli.subcommands:main"`; Plan 12 T1 line 206 asserts same. ✅ Aligned. |
| Container `~/.arx/` path resolution | Plan 12 Dockerfile: `HOME=/home/custos` + `VOLUME ["/home/custos/.arx"]`; Plan 11 T1 uses `Path.home() / ".arx"` | In container UID 1000, `Path.home()` resolves to `/home/custos` (from passwd entry `useradd -u 1000 -m -d /home/custos custos`). So `Path.home() / ".arx"` = `/home/custos/.arx` = VOLUME target. ✅ Consistent. |
| CHANGELOG.md ownership single | `grep 'CHANGELOG\.md' 11-*.md` | Plan 11 File Inventory + Actions section: **0 hits** (Plan 11 does not modify CHANGELOG.md). Plan 12 T5 sole owner (line 156, 336). ✅ Aligned with R1 H1 fix. |
| Plan 11 T8 stub `def main` vs Plan 12 T1 test | Plan 11 line 465 `def main(argv: list[str] | None = None) -> int:` in `cli/main.py` stub; Plan 12 T1 asserts entry `custos.cli.subcommands:main` (different module) | Both defined `main` symbols — one in `cli/main.py` (stub) and one in `cli/subcommands/__init__.py` (real dispatcher). Test at Plan 12 T1 targets the `subcommands:main`. No collision. ✅ Consistent. |
| `_daemon.py` importer | Plan 11 line 418: `from custos.cli._daemon import run_daemon`; Plan 12 doesn't reference `_daemon` | Zero cross-plan interference. ✅ |
| `SopsAgeVault` deletion + `PerKeyVault` add | Plan 11 T7 File Inventory line 113 + T8 line 431 delete + line 115 preserve enum/base | `test_sops_age_vault_class_removed` at T8 verifies deletion (line 439); `PerKeyVault` 3 failure-mode tests at T7 (lines 154-156) verify production runtime read path. ✅ Consistent within Plan 11; no Plan 12 touchpoint. |
| Plan 11 CHANGELOG "Removed" items vs Plan 11 clean-break directive wording | Plan 12 line 333: 5 removed items — legacy `python -m custos` entry point; legacy `custos` console script; `SopsAgeVault` multi-credential-JSON model; `~/.custos/` state namespace; `--sops-file` / `--age-key-file` CLI flags | Cross-referenced against Plan 11 line 69 + line 89 + line 116 + line 92 + line 114. All 5 removed items present in Plan 11 clean-break scope. ✅ CHANGELOG scaffold enumerates exactly Plan 11 breaking scope. |

---

## Final execute-team dispatch recommendation

**Verdict**: READY (with M-R2-1 handoff supplement recommended before dispatch)

### Strict serial gate landed
- ✅ Plan 12 header line 10 `Cross H5 — Strict serial merge protocol` block landed with HARD PRECONDITION + SHA gate + no-parallel declaration.
- ✅ Plan 11 line 27 also carries the "Do not parallel-execute" mirror from its side.

### SHA gate commands (verbatim from Plan 12 header line 10 + line 557)
Execute-team spawn prompt for Plan 12 MUST include these three assertions before Task 1 Step 1:

```bash
# Gate 1 — Plan 11 T8 landed on main
git log --oneline | grep -q 'plan 11 t8' || { echo "FAIL: Plan 11 T8 not landed"; exit 1; }
# Gate 2 — arx-runner console script registered
grep -q '"arx-runner"' pyproject.toml || { echo "FAIL: arx-runner script not in pyproject.toml"; exit 1; }
# Gate 3 — SopsAgeVault fully removed
[ "$(grep -c 'SopsAgeVault' src/custos/core/credential_vault.py)" = "0" ] || { echo "FAIL: SopsAgeVault residue in credential_vault.py"; exit 1; }
```

### Merge conflict prevention checklist (from R1 review §"Merge conflict prevention checklist")

**This checklist is not yet in `.forge/handoff/2026-07-team-full-loop/`**. Options:
- (A) Copy verbatim into the recommended handoff supplement (M-R2-1 fix Option A).
- (B) Reference by path in the execute-team spawn prompt with instruction to read `.forge/reviews/2026-07/cross-plan-11-12-review-claude.md` lines 278-296.

Verbatim (for convenience, so execute-team spawn prompt writer does not need to re-fetch):

- [ ] Plan 12 execute-team worktree branches from `main` HEAD containing Plan 11 T8 squash commit — NOT any earlier commit.
- [ ] `pyproject.toml` — Plan 11 T8 owns `[project.scripts]` + `version`; Plan 12 T1 owns `[project.optional-dependencies].lts` + `[tool.hatch.build.hooks.custom]`. Ownership never crosses.
- [ ] `README.md` — Plan 11 T9 owns §Quick Start + §Upgrade from 0.1.x; Plan 12 T5 owns §Not Included Yet trim. Plan 12 T9 does NOT further edit README.md.
- [ ] `CHANGELOG.md` — Plan 12 T5 sole owner. Plan 11 T9 must NOT create or edit `CHANGELOG.md`.
- [ ] `Dockerfile` — Plan 12 T2 sole owner. ENTRYPOINT `["arx-runner", "start"]` (verified R2 line 246).
- [ ] `.github/workflows/release.yml` — Plan 12 T4 sole owner.
- [ ] `docs/lts-commitment.md` + `docs/upgrade-path.md` — Plan 12 T6 sole owner.
- [ ] `docs/gateway-contract/v1/*` — Plan 12 T7 sole owner.
- [ ] `docs/reproducible-build.md` — Plan 12 T8 sole owner.
- [ ] `CONTRIBUTING.md` + `SECURITY.md` — Plan 12 T9 sole owner.
- [ ] `docs/design/enrollment.md` + `docs/design/credential_vault.md` + `docs/design/03-implementation.md` + `docs/ops/05-deployment.md` — Plan 11 T9 sole owner.
- [ ] ADR-014 workspace-level edit (Plan 11 T9 line 495) — separate commit outside custos-repo; `git add <specific-file>` per lesson #3. Independent-repo executor SKIP + record follow-up.
- [ ] `src/custos/cli/main.py` — Plan 11 T8 sole owner (5-line stub). Plan 12 does not touch.
- [ ] `src/custos/core/credential_vault.py` — Plan 11 T8 sole owner (delete lines 121-206 + extend `AuditEvent` enum). Plan 12 does not touch.
- [ ] `src/custos/cli/_daemon.py` — Plan 11 T7 sole owner (new file). Plan 12 does not touch.
- [ ] `src/custos/core/per_key_vault.py` — Plan 11 T7 sole owner (new file). Plan 12 does not touch.
- [ ] Version tag `v0.2.0` — created only after Plan 12 T9 close-out at HEAD containing both plans' commits. `git tag -s v0.2.0 <commit-sha>`.
- [ ] Post-publish CI `verify-release.sh` includes `docker run --rm --help` + non-root probe (H2 fix landed, R2 verified line 312-314).

### Suggested pre-dispatch actions (main session)

1. **[Recommended]** Write M-R2-1 handoff supplement (`.forge/handoff/2026-07-team-full-loop/custos-handoff-packet-supplement-r1-fix.md`) — either verbatim checklist + updated §17/§18 or point to fix commits + R2 report.
2. **[Optional low-priority housekeeping]** Fix L-R2-1 (22 vs "21") + L-R2-2 (CHANGELOG wording) + M-R2-2 (structlog+caplog capture scope) as a single amend commit, or defer to close-out cycle.
3. **[Gate]** Verify Plan 11 fix `5287486` and Plan 12 fix `2bae32b` are on `main` (they are, per `git log --oneline`); handoff packet base commit `45c62e7` is now 2 commits behind — supplement or refresh required if strict provenance is desired.

### Post-Plan-11-landing gate (execute-team spawns Plan 12 only after these pass)

- `git log --oneline | grep 'plan 11 t8'` — hits (Plan 11 T8 squash commit).
- `grep '"arx-runner"' pyproject.toml` — hits 1.
- `grep 'SopsAgeVault' src/custos/core/credential_vault.py` — hits 0.
- `python -m custos --tenant-id t --runner-id r 2>&1 >/dev/null; echo $?` — 2 (per T8 stub) + stderr contains `arx-runner start`.
- `shutil.which("arx-runner")` — resolves in Python after `uv sync`.
- `shutil.which("custos")` — None (legacy console script gone).

Once all 6 assertions pass, Plan 12 execute-team dispatch is authorized. Track A / B / C parallelization inside Plan 12 (per R1 review §"Suggested execution ordering" step 3) remains valid.

---

## Positive observations (retained from R1 + reinforced)

- **DP5 RESOLVED** with clean-break directive → boundary constant single-source (lesson #35) is truly single-source; Plan 12 consumer references never diverge.
- **Serial merge protocol** explicitly landed at Plan 12 header + Plan 11 line 27 mirror + verification checklist line 557 triple-cite.
- **Cross-plan wire alignment**: `token_hash` (Plan 11 T4 wire = Plan 12 T7 JSON Schema) + `arx-runner` (Plan 11 T8 script = Plan 12 T1 test = Plan 12 T2 Dockerfile ENTRYPOINT) — both single-source.
- **Non-Custodial red line coverage** (Plan 11 §M8 red-line gate satisfaction table lines 508-514) explicitly maps 4 red lines to code-level tests + runtime wire, following lesson #40 pattern.
- **C1 boundary-string validators** (Plan 11 T2 `validate_backend_url` — 7 new tests) close H1 explicitly with cross-plan test surface at Plan 11 line 152 (`test_enroll_rejects_non_http_backend`).
- **Multi-layer failure-mode independence** (Plan 12 FM1/FM2 + Plan 11 21/22 rows) preserved through both fixes with no dead-branch regression.
