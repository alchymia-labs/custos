# Plan 11 Round 2 Review (Claude, opus-4-7[1m])

**Reviewed at**: 2026-07-10
**Plan file**: `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md`
**Round 1 review anchors**:
- `.forge/reviews/2026-07/11-plan-review-claude.md` (3 C / 4 H / 8 M / 7 L)
- `.forge/reviews/2026-07/cross-plan-11-12-review-claude.md` (2 C / 5 H / 5 M / 2 L)
**Round 1 fix commit**: `5287486`
**Round 1 baseline**: `d3a7948`
**Verdict**: `APPROVED_WITH_FOLLOW_UPS`

**R1 fix completeness**: **~95%** — all 3 CRITICAL + 3.5/4 HIGH + 8/8 selected MEDIUM landed. One HIGH (H4) is partially fixed (impl side flipped to stdlib logging, but test-side assertion still references structlog — dead-branch). Cross-plan H5 hard-dep gate landed. Two new documentation-level drift findings (numeric counts + test-vs-impl-source consistency) surfaced during R2 grep verification. No new Critical. Executor can proceed with a small, cheap forward-fix at close-out.

- **R1 fully-fixed**: 3 C + 3 H + 8 M + cross-plan hard-dep gate + cross-plan `token_hash` single source of truth
- **R1 partially-fixed**: H4 (test-side residue)
- **R2 new findings**: 1 MEDIUM + 3 LOW (all documentation drift, no functional bug)

---

## R1 finding verification table

### Plan 11 R1 (3 Critical + 4 High + 8 Medium + 7 Low)

| R1 Finding | Severity | Fix status | Evidence (file:line or grep) |
|---|---|---|---|
| **C1** clean-break residues | Critical | ✅ Fixed | `grep -nE 'DeprecationWarning\|coexistence' 11-*.md` — 7 hits, **all negations** ("no DeprecationWarning" / "no coexistence"). No stale seed remains. Deviations table 3 rows (namespace L562 / enroll transport L563 / vault storage model L564) all flipped to ✅ CEO directive 2026-07-10. `test_deprecated_warning_on_old_entry.py` File Inventory row deleted (grep `test_deprecated_warning_on_old_entry` = 0 hits). Verification checklist L529 rewritten to "exits code 2 … **no `DeprecationWarning`** bridge". Progress T8 Notes L551 rewritten to "sys.exit(2) + one-line pointer … no DeprecationWarning bridge". File Inventory L127 credential_vault.md row: "sole supported runtime model … no coexistence" (clean-break rewrite). |
| **C2** `run_daemon` vanish (Option A vs B) | Critical | ✅ Fixed (Option A adopted) | File Inventory L110: new row `src/custos/cli/_daemon.py` "Create" hosting `run_daemon` + `_build_vault` + `_build_host` + `_build_reconciler` + `_heartbeat_loop`. Task 7 Step 3 (L413): "Extract to `src/custos/cli/_daemon.py` (not `cli/main.py`, per C2 Option A)". Task 7 Step 3.3 (L418): "`from custos.cli._daemon import run_daemon; asyncio.run(run_daemon(ns))`". T8 (L114) delete list explicitly says "relocated to `cli/_daemon.py`" for all 5 helpers. `_daemon.py` survives T8's `cli/main.py` rewrite. |
| **C3** PerKeyVault runtime reader gap | Critical | ✅ Fixed | File Inventory L113: `src/custos/core/per_key_vault.py` "Create" with `class PerKeyVault(_BaseVault)` — inherits `_verify_permission_scope` + `_emit_decrypt_audit`. Failure-mode contract adds 3 rows L154-156 (`test_per_key_vault_missing_enc_file_clear_error` / `test_per_key_vault_scope_violation` / `test_per_key_vault_sops_fail_no_silent_return`). Task 7 Step 3.2 (L417) stale sops_file/age_key_file DELETED + `vault_dir=DEFAULT_VAULT_DIR` added. Task 7 Step 3 (L413) rebuilds `_build_vault` to construct `PerKeyVault(vault_dir=args.vault_dir, tenant_id=args.tenant_id, initiator=args.runner_id)`. T8 preservation range L115 + L477 spelled out ("Delete lines 121-206" preserves `_BaseVault` + `AuditEvent` + adds `CREDENTIAL_ENCRYPTED = "CredentialEncrypted"`). |
| **H1** URL scheme allowlist | High | ✅ Fixed | Task 2 File Inventory L111: `validate_backend_url` in `validators.py`. Task 2 Step 1 (L214-220) has 7 test cases (accepts http/https, rejects file / gopher / bare hostname / empty netloc / userinfo / fragment). Task 2 Step 3 (L238-256) full implementation via `urllib.parse.urlparse`. Task 4 Step 3 (L315): `--backend type=validators.validate_backend_url`. Failure-mode L152: `test_enroll_rejects_non_http_backend`. |
| **H2** Task 9 duplicated bullets | High | ✅ Fixed | T9 Files section (L488-498) now 8 unique items; former near-duplicate 3-item block deleted. Actions steps 3-4 (L503-504) rewritten with clean-break language (no "coexistence"). |
| **H3** T7 Step 3.2 stale sops fields | High | ✅ Fixed | Subsumed by BLK-3. Line 417: "Stale `sops_file` / `age_key_file` fields DELETED — the multi-cred sops-file model no longer exists post-T8 (H3 residue removal)". Only remaining `sops_file` / `age_key_file` grep hits are historical context (Evidence L40, Goal L69, Architecture L77, KDT L88, Deviations L564) describing what's being deleted. |
| **H4** T5 audit event via stdlib logging | High | ⚠️ **Partial** | ✅ **Impl side**: L355 T5 Step 3 rewritten to use `_log = logging.getLogger("custos.credential_vault")` with `extra={"audit_event": AuditEvent.CREDENTIAL_ENCRYPTED.value, ...}`. AuditEvent enum extension added at T8 File Inventory L115 + L477. ❌ **Test side residue**: L342 test spec still says "`test_vault_put_never_logs_secret`: capture **structlog** output, assert raw `--api-secret` value never appears in any log record". Verification checklist L533 also says "structlog output". Since impl uses stdlib logging (not structlog), the structlog-only capture would trivially pass without exercising the invariant. See **N1** below. |
| M1 payload contract note | Medium | ✅ Fixed | L310 + L319: "backend resolves tenant from `token_hash` server-side; runner does not send `tenant_id` in the payload". |
| M2 `--capabilities action='append'` | Medium | ✅ Fixed | L315: "`--capabilities` (**M2**: `action="append"`, `default=[]`)". |
| M3 三形式 secret 输入 | Medium | ✅ Fixed | L348-351: three mutually exclusive `--api-secret-*` flags (stdin primary / env secondary / cmdline demo warn-loud). Failure-mode L153: `test_vault_put_prefers_stdin_and_warns_on_cmdline_secret`. |
| M4 redirect handler 重验 scheme | Medium | ✅ Fixed | L320: "install a `urllib.request.HTTPRedirectHandler` subclass that re-runs `validate_backend_url` on the Location header before following any 3xx redirect". |
| M5 timeout=30 invariant 注释 | Medium | ✅ Fixed | L320: "`timeout=30` matches the sops-decrypt `subprocess.run(..., timeout=30)` invariant at `credential_vault.py:162` — hard invariant across all zero-dep external I/O boundaries". |
| M6 Deviations "numbering" 行删 | Medium | ✅ Fixed | `grep -n 'numbering\|pending review-time\|⏳'` = 0 hits. |
| M7 T8 `credential_vault.py` preservation | Medium | ✅ Fixed | Subsumed by BLK-3. L115 File Inventory row for `credential_vault.py`: "**Delete lines 121-206** — Delete `SopsAgeVault` class only. **Preserve** `_BaseVault._verify_permission_scope` (lines 83-98) + `_BaseVault._emit_decrypt_audit` (lines 64-81) + `AuditEvent` enum (lines 39-46)". |
| M8 T9 close-out 红线 gate 表 | Medium | ✅ Fixed | L508-514 T9 Action 8: full "红线 gate 满足度" table template with 4 rows (0.1 / 0.2 / 0.3 / 0.4), columns `red_line \| code_coverage \| runtime_wire \| defer_status \| follow_up_plan_ref`. Explicit lesson #40 reference. |
| L1 sops encrypt via /dev/stdin | Low | ✅ Fixed | L353 T5 Step 3: "**L1 note**: payload bytes are passed via `subprocess.run(..., input=...)`, NOT via a `sh -c` intermediary — no shell buffer holds plaintext". |
| L2 grep positive baseline | Low | ✅ Positive obs, no action | — |
| L3 `--vault-dir` `~/.arx/vault` cross-cutting | Low | ✅ Fixed | L420 T7 Step 4: added `test_vault_put_reuses_arx_dir_0700` cross-cutting test. |
| L4 README brace expansion POSIX | Low | ✅ Fixed | L505 T9 Actions step 5: "**L4 note**: … POSIX-safe fallback (`mv ~/.custos/enrollment.json ~/.arx/enrollment.json && mv ~/.custos/state ~/.arx/state`) with a … note". |
| L5 ADR-014 cross-repo scope | Low | ✅ Fixed | L495 T9 Files ADR-014 row: "workspace-only edit … Independent-repo executors … skip this step; record the skip in the plan close-out follow-up list. Workspace executors commit the ADR edit in a **separate commit outside the custos-repo**, `git add <specific-file>` per `mandatory-rules.md` §6". Cross M2 also covered here. |
| L6 test naming stale | Low | ✅ Fixed | `test_deprecated_warning_on_old_entry` deleted from File Inventory; `test_legacy_cli_removed.py` retained at T8. |
| L7 version bump dedup | Low | ✅ Fixed | L498 T9 Files: "**Note (L7)**: T8 does the actual bump; T9 only verifies via `grep '^version = "0.2.0"' pyproject.toml` = 1 hit. Do NOT bump again in T9". Reinforced at Actions step 6 (L506). |

### Cross-plan R1 (2 Critical + 5 High + 5 Medium + 2 Low)

| Cross R1 Finding | Severity | Fix status | Evidence |
|---|---|---|---|
| Cross C1 Plan 12 Dockerfile ENTRYPOINT | Critical | ✅ Fixed (Plan 12 side, out of Plan 11 R2 scope) | Plan 12 L246 shows `ENTRYPOINT ["arx-runner", "start"]` matches File Inventory L149; Plan 12 fix commit `2bae32b` covered this. |
| Cross C2 Plan 11 3-way DeprecationWarning drift | Critical | ✅ Fixed | Same as C1 above — clean-break residues fully removed. |
| Cross H1 CHANGELOG breaking scope | High | ✅ Fixed (Plan 12 side) | Plan 12 L333-336 T5 Step 3 CHANGELOG scaffold enumerates Plan 11 items under `### Removed` + `### Changed` (BREAKING) + Plan 12 items under `### Added`. Plan 11 T9 does NOT touch CHANGELOG.md (confirmed by grep). |
| Cross H2 verify-release.sh docker run smoke | High | ✅ Fixed (Plan 12 side) | Plan 12 has `tests/test_docker_entrypoint_help.py` (L169). |
| Cross H3 WAL default retargeting owner | High | ✅ Fixed | File Inventory L109 `subcommands/start.py`: defines `DEFAULT_WAL_PATH = Path.home() / ".arx" / "state" / "telemetry-wal.db"` + `DEFAULT_ENROLLMENT_PATH`. Task 7 Step 3 also declares `DEFAULT_VAULT_DIR` (L415). Cross-ref to H3 explicit in the row. |
| Cross H4 Dockerfile HOME + VOLUME | High | ✅ Fixed (Plan 12 side) | Plan 12 L151 File Inventory `Dockerfile`: "`useradd -u 1000 -m -d /home/custos custos` + `ENV HOME=/home/custos` + `VOLUME ["/home/custos/.arx"]` (Cross H4 fix …)". |
| Cross H5 strict serial merge protocol | High | ✅ Fixed | Plan 11 L27 "下游耦合与执行顺序 (cross-plan hard gate)" — "Plan 11 全部 T1..T9 squash 落 `main` 后, Plan 12 execute-team 才能启动 … Do not parallel-execute". Plan 12 L10 mirrors. |
| Cross M1 README 3-way | Medium | ✅ Deferred to Plan 12 T5/T9 | Plan 11 T9 owns Quick Start + Breaking Change; Plan 12 T5 owns Not Included Yet trim. Ownership boundary clear. |
| Cross M2 ADR-014 cross-repo | Medium | ✅ Fixed (L495 workspace-only annotation) | Same as L5 above. |
| Cross M3 DP5 wording drift | Medium | ✅ Fixed (Plan 12 side) | Plan 12 L103 DP5 marked **RESOLVED**. |
| Cross M4 SemVer 0.x breaking clarity | Medium | ✅ Fixed (Plan 12 side) | Plan 12 CHANGELOG scaffold marks `**BREAKING — Plan 11**`. |
| Cross M5 boundary fanout list | Medium | ✅ Fixed (Plan 12 side) | Not directly in Plan 11 scope. |
| Cross L1 test_changelog optional | Low | Deferred to Plan 12 | Not in Plan 11 scope. |
| Cross L2 T9 near-duplicate | Low | ✅ Fixed (subsumed by H2). | Same evidence as H2. |
| Cross-plan `token_hash` single source | (bonus) | ✅ Fixed | L28 "**Wire field name single source of truth (lesson #35)**: … `token_hash` (verified: `src/custos/core/enrollment.py:59`). Plan 12 gateway-contract v1 JSON Schema aligns to this name". Plan 12 L452 mirrors. |

**R1 tally**: 5 Critical (all fixed) + 9 High (8 fixed + 1 partial-H4) + 13 Medium (all fixed or scoped to Plan 12) + 9 Low (all fixed or scoped) = **95%+ landed**.

---

## New findings (R2, introduced or surfaced by R1 fix)

### N1 — H4 fix incomplete: test-side still targets structlog while impl is stdlib logging (dead-branch, lesson #22/#28 vein)

- **Severity**: MEDIUM
- **Location**: Plan L342 (T5 Step 1 test spec) + L533 (Verification checklist)
- **Evidence**:
  - L355 (impl side, correct): "**H4 audit event via stdlib logging** (not structlog): `_log = logging.getLogger("custos.credential_vault")` … emit `_log.info("credential_encrypted", extra={…})`"
  - L342 (test side, residue): "`test_vault_put_never_logs_secret`: **capture structlog output**, assert raw `--api-secret` value never appears in any log record"
  - L533 (checklist, residue): "No `--api-secret` value appears in any **structlog** output (verified by `test_vault_put_never_logs_secret`)"
- **Impact**: Post-fix, the T5 audit event is emitted via stdlib `logging`. A test that captures only structlog will find the log stream empty — the assertion "raw `--api-secret` value never appears" trivially passes without exercising the invariant. This is a dead-branch test (lesson #22/#28) that also tips into lesson #17 (test doesn't cover the actual failure mode). The R1 review's H4 fix flipped the impl but forgot to sweep the test-side language. If the executor takes L342 verbatim, they'll write a test that never runs against the audit log.
- **Suggested fix**:
  - L342 rewrite: "`test_vault_put_never_logs_secret`: **capture both stdlib `caplog` and structlog output**, assert raw `--api-secret` value never appears in any log record. **H4-aligned**: T5 audit event uses stdlib `logging.getLogger("custos.credential_vault")` (see Step 3 L355), so the stdlib `caplog` fixture is the primary check; structlog capture is the defense-in-depth secondary."
  - L533 rewrite: "No `--api-secret` value appears in any log record (both stdlib `caplog` and structlog output verified by `test_vault_put_never_logs_secret`)".

### N2 — Failure-mode contract table numeric drift (lesson #25 vein)

- **Severity**: MEDIUM (documentation drift; blocks close-out red-line-gate sanity check if executor greps the count literally)
- **Location**: Plan L158 (Contract closing sentence) + L507 (T9 Action 7) + L530 (Verification checklist)
- **Evidence**:
  - Actual failure-mode table row count: **22** (verified: `awk` on the table extract). Rows 1-17 are original pre-R1; rows 18-22 are review-driven (H1 + M3 + BLK-3 × 3).
  - L158: "All **21** failure modes are code-level tests …"
  - L507: "any failure modes uncovered during implementation added beyond the **21 contracted (14 original + 7 review-driven)**"
  - L530: "All **21** failure-mode contract tests present and green"
- **Impact**: R1 review's Positive P3 saw 16 pre-fix rows; after the fix added 5 rows the drafter typed "21 contracted (14 + 7)". Actual is 22 (17 + 5). The 14/7 breakdown is also wrong (5 review-driven, not 7). If an executor takes the checklist literally and greps "21 tests present", they'll miss 1 test or add a spurious one. Not a functional bug but violates lesson #25 (fabricated numbers — even off-by-one drift counts).
- **Suggested fix**: Replace three occurrences:
  - L158 → "All **22** failure modes …"
  - L507 → "beyond the **22 contracted (17 original + 5 review-driven)**"
  - L530 → "All **22** failure-mode contract tests present and green"

### N3 — Test name near-collision + failure-mode table coverage gap

- **Severity**: LOW
- **Location**: Plan L148 (Failure-mode row 14, T8 test) + L407 (T7 Step 1 test)
- **Evidence**:
  - L148: `test_default_paths_target_arx_namespace` (T8, module-level introspection of argparse default constants)
  - L407: `test_start_default_paths_target_arx_namespace` (T7, runtime test that `start` builds a namespace with `.arx` paths)
  - L440 (T8 Step 1): `test_default_paths_target_arx_namespace` re-declared for T8 impl
  - L551 (Progress T8 Notes): lists `test_default_paths_target_arx_namespace`
- **Impact**: T7 and T8 declare two distinct tests differing only by the `_start_` prefix — likely intentional (T7 tests runtime; T8 tests module constants), but the failure-mode contract table only lists the T8 version. If T7's test is contract-worthy (per L157 lesson #17 discipline), it should also appear in the table. If T7 test is redundant with T8, one should be dropped.
- **Suggested fix**: Either add a new row to failure-mode contract for T7's runtime test, or fold T7's test description into the T8 row's Purpose column ("… asserted at both module-const level (T8) and start-runtime level (T7 `test_start_default_paths_target_arx_namespace`)").

### N4 — Progress row test-count drift (T7)

- **Severity**: LOW
- **Location**: Plan L550 (Progress row T7)
- **Evidence**:
  - L550: "T7 start subcommand | 🔲 | | reads runner.toml, delegates to refactored `run_daemon`; preserves engine/wal flags; **5 tests**"
  - Actual T7 Step 1 (L402-408) lists **9 tests**: 6 `test_start_*` + 3 `test_per_key_vault_*` (moved into T7 per BLK-3 fix).
- **Impact**: Progress notes carry a stale count from pre-BLK-3 draft. Purely informational; does not affect executor behavior since Step 1 test list is authoritative.
- **Suggested fix**: L550 update to "9 tests (6 start + 3 per_key_vault)".

### N5 — MockVault dev/paper fallback silently dropped by rebuilt `_build_vault`

- **Severity**: LOW (potential; needs CEO confirmation)
- **Location**: Plan L413 (T7 Step 3 rebuilt `_build_vault`)
- **Evidence**:
  - Pre-fix `_build_vault` (src/custos/cli/main.py:132-146): three-way branch — `CredentialVault` (mock) if both sops/age None; `SopsAgeVault` if both set; fail-fast if partial config.
  - Post-fix L413: "Rebuild `_build_vault` to construct `PerKeyVault(vault_dir=args.vault_dir, tenant_id=args.tenant_id, initiator=args.runner_id)`" — no MockVault branch mentioned.
  - L158: "the runtime wire is already covered by Plan 04's reconciler tests and this plan does not modify reconciler code beyond swapping the `_build_vault` return type from `SopsAgeVault` to `PerKeyVault` in `_daemon.py`."
- **Impact**: After the fix, paper/dev-mode users without any `~/.arx/vault/*.enc` files would still get a `PerKeyVault` that fails at first `.decrypt()` with `FileNotFoundError`. If Plan 04 reconciler tests injected `MockVault` at a higher layer (fixture-level `credential_vault` argument), they'd still pass. But real paper-mode CLI users would hit a runtime error unless they'd run `arx-runner vault put` for every credential the reconciler tries to decrypt. Whether this is intentional CEO clean-break policy (force real vault put even in paper) or an accidental drop is not spelled out in the plan.
- **Suggested fix**: Add one sentence to L413 clarifying either "`_build_vault` always returns `PerKeyVault` — paper-mode users must still run `arx-runner vault put` per credential; MockVault is retired along with legacy CLI" (if intentional) or "`_build_vault` returns `MockVault` (`CredentialVault`) when no `--vault-dir` credentials exist; `PerKeyVault` otherwise" (if MockVault dev/paper fallback is preserved). CEO clean-break directive at L71+L89 suggests the former, but not explicit.

---

## R2 verdict rationale

**APPROVED_WITH_FOLLOW_UPS** because:

1. **All 3 R1 Critical fixed** (BLK-1 clean-break residues + BLK-2 `run_daemon` relocation + BLK-3 PerKeyVault runtime reader). Cross-plan Critical (Cross-C2 3-way DeprecationWarning) also swept as part of BLK-1.
2. **All 4 R1 High fixed except H4 partial** — H4 impl side flipped correctly to stdlib logging (L355 + AuditEvent enum extension), but test-side language (L342 + L533) still references structlog, creating a dead-branch test. Not blocking (impl works; test just isn't exercising the invariant). Fix is a single-line rewrite of two locations.
3. **All 8 selected Medium fixed** (M1-M8 all landed with grep-verified evidence).
4. **Cross-plan hard-dep gate landed** (L27 explicit "全部 T1..T9 squash 落 main" + `token_hash` single source of truth at L28).
5. **New R2 findings** are 1 Medium (N1 test-vs-impl inconsistency) + 3 Low (N2 numeric drift / N3 test-name near-collision / N4 progress row count) + 1 Low (N5 MockVault dev/paper drop needs CEO confirmation). None are Critical. None block landing.

**Cheapest close-out fix**: single Edit pass over L342, L533 (H4 test alignment) + L158, L507, L530 (numeric drift 21 → 22, 14+7 → 17+5) + L550 (T7 count 5 → 9). Ideally also L413 clarification about MockVault disposition (N5). All 6 edits are 1-line replacements; total < 15 minutes of executor time. Recommend absorbing into T9 close-out actions rather than a separate fix cycle.

**No REQUEST_CHANGES** because none of the new findings are Critical or would cause executor thrash. The plan is executable as-is; the follow-ups are polish + numeric hygiene.

---

## Suggested close-out follow-up list (for Plan 11 T9 to absorb)

1. Sweep H4 test-side language (L342 + L533): replace "structlog output" with "both stdlib `caplog` and structlog output" and cross-ref L355 for the impl-side stdlib logger rationale.
2. Numeric drift sweep (N2): update L158 / L507 / L530 to 22 / 17+5.
3. Test-name near-collision (N3): either add T7 runtime-namespace test as a new failure-mode row or fold into T8 row's Purpose column.
4. Progress row count (N4): L550 update T7 to "9 tests (6 start + 3 per_key_vault)".
5. `_build_vault` MockVault disposition (N5): add one sentence to L413 clarifying whether paper mode requires a real vault or whether MockVault fallback is preserved.

---

*Reviewer: Claude (opus-4-7[1m]) @ 2026-07-10*
*Method: R1 finding grep verification × R2 fix-side new-finding sweep (dead-branch / numeric-drift / test-vs-impl consistency)*
*Lesson enforcement: #9/#11/#37 grep-verified all fix landings; #17/#22/#28 dead-branch probe (N1); #25 numeric drift (N2); #34 self-check via git show 5287486; positive dogfood: R1 fix commit message names all 3 Critical + 4 High + 8 Medium explicitly, easing R2 verification.*
