# Plan 08 codex L1 peer review — in-place fix log

- **Plan file**: `.forge/plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md`
- **Peer review verdict**: `REQUEST_CHANGES` (codex L1, 9 findings: 3 HIGH + 5 MED + 1 LOW)
- **Peer review artifact**: `/private/tmp/claude-501/-Users-wukai-data-repos-github-the-alephain-guild-tesseract-trading-custos/5107788a-8761-4294-9d1d-9c4515183572/scratchpad/codex-peer/lastmsg-08.txt`
- **Fix cycle date**: 2026-07-09 (plan-drafter-08, in-place directed fix)
- **Plan file post-fix line count**: 511 (up from 484 pre-fix)

---

## Fix table

| ID | Severity | Location (pre-fix line) | Finding | Fix action | Verification |
|----|----------|-------------------------|---------|------------|--------------|
| CR-1 | HIGH | line 29 (§1.5 anchor table) | Anchors claimed verbatim but were paraphrases | Restructured table: added distinct "Verbatim scout / Plan 06 quote" column carrying exact quoted text; kept "Summary" column as drafter paraphrase relabelled non-authoritative. Every row's source anchor cites either `evidence-scout-07-08.md:<line>` or `06-ps-supertrend-migration.md:<line>` | `grep -c "Verbatim scout / Plan 06 quote"` → 2 (table header + column reference). Every quote grep-verifiable against the cited scout line range or Plan 06 file:line |
| CR-2 | HIGH | line 346 (§red-line 0.1) | Declared defer_status=none even though DP1 = C could defer T5.2 | Made defer_status conditional on DP1 outcome: `DP1 = A|B → none`; `DP1 = C → testnet-mode credential-path coverage deferred to <successor plan>`. Also added DP1-conditional wording for the code_coverage cell and a two-variant "satisfaction declaration" at close-out | `grep -c "conditional on DP1 outcome"` → 1; satisfaction declaration has explicit A/B and C variants |
| CR-3 | HIGH | line 55 (START gate paragraph) | START gate treated Plan 07 expansion/trim as a "re-verify toolkit path" branch, ignoring handoff packet's explicit statement that Plan 07 curation can change T5 e2e coverage policy | Replaced paragraph with an explicit **post-Plan-07 coverage matrix** (3 rows: keep 06a subset / expand vendoring / trim to strict closure) — each row states resulting T5 coverage, additional e2e tests, and executor action. Documented default scope decision = row (a) supertrend-only | `grep -c "Post-Plan-07 coverage matrix"` → 1; matrix has 3 rows a/b/c matching Plan 07 DP1 options |
| CR-4 | MED | line 392 (DP3) | DP3 had only options A/B, packet requires a/b/c for all CEO DPs | Added **DP3 option C**: "Defer fault injection to Plan 04 chaos infrastructure or a dedicated pre-live chaos plan" with explicit follow-up DEV entry and named successor plan. Added Impact section listing all three options + preserved drafter recommendation = A with rationale contrasting A vs C | `grep -c "Option C"` → 4 (multiple DPs); DP3 body now contains option A/B/C + Impact + Decision |
| CR-5 | MED | line 330 (failure-mode table) | Existing test rows lacked file:line anchors despite scout §6 providing them | Added `tests/test_nt_trading_node_host_integration.py:60` (`test_full_lifecycle_sandbox_supertrend`), `:91` (`test_deploy_missing_nt_extra_fails_fast`), `:99` (`test_deploy_code_hash_mismatch_rejected`) anchors inline in the ✓existing rows | `grep -c "test_nt_trading_node_host_integration.py:60\|:91\|:99"` → 3 (all three existing-test anchors present) |
| CR-6 | MED | line 183 (T5.1 strategy source) | tmp_path option (i) claimed self-contained but copied from external ps checkout | Reordered options: (iii) permanent in-repo fixture mirror at `tests/fixtures/real_supertrend/` promoted to drafter recommendation (with explicit "all companion config files" requirement); (i) and (ii) explicitly flagged as NOT independent-clone reproducible + require `pytest.skip("ps repo checkout absent...")` if chosen + explicit self-contained-gap declaration in close-out + T6.1 docs | Option (iii) text starts with "**drafter recommendation for independent-clone reproducibility**"; options (i)(ii) start with "NOT independent-clone reproducible" |
| CR-7 | MED | line 216 (testnet reachability) | Hard-coded `testnet.binancefuture.com/ping` without source anchor + no spot connector consideration | Replaced hard-coded URL with **connector-aware probe** derived from installed NT Binance adapter (`nautilus_trader.adapters.binance` `BinanceEnvironment.TESTNET` constants; futures uses `futures.testnet_url`, spot uses `spot.testnet_url` in NT ≥1.227). Added explicit futures-vs-spot branching rule: Plan 08 targets futures by default per Plan 06 conventions; spot out of scope | `grep -c "connector-aware probe"` → 1; text names both futures/spot adapter attributes |
| CR-8 | MED | line 297 (tracking-number gate) | Repo-wide `Plan 06\|Task N\|lesson #` grep would fail — existing pollution already present in `src/custos/cli/main.py:46`, `toolkit/TOOLKIT_PROVENANCE.md`, `tests/test_deployment_reconciler.py:3`, `tests/test_enrollment.py:126`, etc. | Scoped the check to files created or modified by Plan 08 only: `git diff --name-only <plan-08-base>..HEAD -- 'tests/**/*.py' 'src/**/*.py' 'docs/**/*.md' \| xargs grep -nE "..." → 0 hits`. Named the pre-existing pollution list explicitly + registered a follow-up cleanup plan candidate | `grep -c "scoped to files created or modified by Plan 08"` → 1; pre-existing pollution files enumerated |
| CR-9 | LOW | line 461 (close-out template) | Close-out template + several plan body phrases still Chinese | Translated: (a) close-out template labels to bilingual `English (Chinese)` pairs — Chinese preserved in parens because `.claude/rules/progress-management.md` §"完成报告模板" heading is authoritative Chinese; (b) T6.2 §"完成报告" fill instructions bilingual for the same reason; (c) `paper→testnet e2e打通` → `paper→testnet e2e landed` in Goal + Next sections; (d) T6.2 references to Plan 06's own Chinese section headings preserved because the executor must write them verbatim into the Plan 06 file. Test names, DEV IDs, task labels remain English throughout | Chinese in plan body is now limited to: verbatim scout quotes, verbatim Plan 06 quotes, authority-doc Chinese section anchors (`.claude/rules/*.md §XXX`), Plan 06 file's own Chinese section headings (`§"完成报告"`), and the bilingual parenthetical glosses that pair English labels with the authoritative Chinese |

---

## Post-fix invariants

- **§1.5 all anchors trace to scout or Plan 06 file:line** — every row's source anchor column names either `evidence-scout-07-08.md §N line M` or `.forge/plans/2026-07/06-ps-supertrend-migration.md:L` explicitly; verbatim column carries the exact quoted text
- **DP3 has a/b/c per packet** — DP3 section body has Option A/B/C + Impact section listing all three + Drafter recommendation still A with rationale contrasting A vs C
- **Red-line 0.1 conditional to DP1 outcome** — code_coverage cell has DP1 = A|B vs C branching; defer_status cell has "conditional on DP1 outcome" wording with DP1 = A|B → none, DP1 = C → deferred; two-variant satisfaction declaration below the table
- **Existing test rows have file:line anchors** — T5 (no-regression) rows in failure-mode table now cite `tests/test_nt_trading_node_host_integration.py:60`, `:91`, `:99`
- **Close-out template English-primary** — English labels lead every bullet; Chinese in parens as authoritative section anchor (paired with the `.claude/rules/progress-management.md` template heading which itself is Chinese by rule)
- **Post-Plan-07 coverage matrix explicit** — 3-row matrix (a/b/c per Plan 07 DP1) with executor action per row; default scope decision documented = row (a) supertrend-only
- **CR-6 tmp_path fix: option (iii) permanent mirror is now drafter recommendation** — options (i)(ii) explicitly flagged as NOT independent-clone reproducible with `pytest.skip` fallback + self-contained-gap declaration
- **CR-7 connector-aware probe replaces hard-coded URL** — reachability check now derives endpoint from `nautilus_trader.adapters.binance` at Foundation Scan time; futures/spot branching documented
- **CR-8 tracking-number grep scoped to Plan 08 diff** — no longer claims false invariant against pre-existing pollution; pre-existing pollution named for a follow-up hygiene plan

## Files touched

- `.forge/plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md` — in-place edit for all 9 findings; header `Fix cycle` line added; total 511 lines (up from 484)
- `.forge/fixes/2026-07/08-plan-fix.md` — this fix log (new)

## Newly-surfaced ambiguity

None. The 9 findings were self-contained; no dependency escalations to Planning Lead / CEO discovered during the fix cycle. DP1/DP2/DP3 remain CEO decision points as designed. The DP1-conditional wording of red-line 0.1 does not change the CEO decision surface — it makes the plan honestly declare partial coverage under the DP1 = C branch instead of overstating.

## Discipline honoured

- **Language Policy** — plan body English-primary; Chinese preserved only where it is a verbatim source quote (scout / Plan 06), an authoritative rule-file section anchor, or a Plan 06 file heading the executor must write verbatim
- **lesson C2 (output-pollution defense)** — every §1.5 anchor grep-verifiable against evidence-scout-07-08.md line ranges or Plan 06 file:line
- **lesson #25 (fabricated-test-name gate)** — no new test names introduced; anchors added to existing test names verified against `tests/test_nt_trading_node_host_integration.py` (lines 60/91/99 confirmed by `grep -n "async def test_"`)
- **lesson #40 / C40 (red-line gate)** — defer_status DP1-conditional; three-layer separation preserved (code_coverage / runtime_wire / defer_status per red line)
- **lesson #17 (happy-path vs failure-mode)** — failure-mode contract table structure preserved + strengthened with file:line anchors
- **No new source code changes** — plan file + fix log only; no `src/` / `tests/` edits
- **No teammate spawns** — single drafter in-place fix as instructed
