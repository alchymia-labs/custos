# Cross-Plan Coherence Review: Plan 11 <-> Plan 12 (Claude, opus-4-7[1m])

**Reviewed at**: 2026-07-10
**Plans**:
- Plan 11 `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md` (CLI clean-break)
- Plan 12 `.forge/plans/2026-07/12-custos-distribution-signed-wheel-docker-lts.md` (distribution + LTS)
**Reviewer lens**: version 0.2.0 same-tag release; `arx-runner` script name single-source; `~/.arx/` namespace unification; hard-dep gate enforcement; CHANGELOG integration duty; Task ownership overlap; merge-conflict prevention (lesson #16 / #24 / #32 / #33 / #35 / #37).

## Verdict

`REQUEST_CHANGES` — 2 Critical (blocking) + 5 High + 5 Medium + 2 Low. Plans are structurally aligned and the hard-dep sequencing intent is correct, but Plan 12 has two internal contradictions that also violate the Plan 11 clean-break contract, and Plan 11 has three internal contradictions about the DeprecationWarning path that would derail Plan 12 T1's gate assertions. Both are single-file `sed`-level fixes — no re-planning needed.

- Critical: 2
- High: 5
- Medium: 5
- Low: 2

---

## Critical findings (block landing)

### C1 — Plan 12 Dockerfile ENTRYPOINT internal contradiction directly violates Plan 11 clean-break

**Where**:
- Plan 12 line 149 (File Inventory Dockerfile row): declares `ENTRYPOINT ["arx-runner", "start"]`
- Plan 12 line 225 (Task 2 Step 3 implementation): specifies `ENTRYPOINT ["python", "-m", "custos"]`

**Problem**: Line 149 (spec) and line 225 (impl instruction) are directly contradictory *inside Plan 12*. Line 225 is worse because Plan 11 Task 8 (line 84 + line 138 + File Inventory line 107 + Failure mode `test_python_m_custos_exits_nonzero_with_pointer` at line 138) deletes `python -m custos` and rewrites `cli/main.py` to a 5-line `sys.exit(2)` stub. A Docker image with `ENTRYPOINT ["python", "-m", "custos"]` will `exit 2` on every `docker run` — the image is broken on landing. Yet Plan 12 T4 `verify-release.sh` (lines 274-286) contains no `docker run --rm ...` smoke; only signature verify. The broken ENTRYPOINT would not surface until first real deployment.

**Compounding**: Plan 12 line 153 File Inventory description of `verify-release.sh` claims it will include `docker run --rm --help (health probe)`, but the actual T4 Step 3 implementation (lines 274-286) shows only sigstore verify + cosign verify — no `docker run`. So the CI path also fails to catch the ENTRYPOINT bug (that would have been Layer 3 of FM2 per line 182).

**Fix**:
- Plan 12 line 225: rewrite `ENTRYPOINT ["python", "-m", "custos"]` -> `ENTRYPOINT ["arx-runner", "start"]` (matches line 149).
- Plan 12 T4 Step 3 (line 274-286): append `docker run --rm ghcr.io/the-alephain-guild/custos:v${VERSION} --help` and assert exit 0, so FM2 Layer 3 (line 182) truly becomes independent — otherwise it's a dead layer per lesson #22/#28.

---

### C2 — Plan 11 internal three-way DeprecationWarning contradiction; if executor follows the wrong branch, Plan 12 T1 gate assertions cannot pass

**Where**: Plan 11 self-contradicts on whether `python -m custos` still runs post-landing.

- **Clean-break branch** (Goal line 64: "hard clean break — no DeprecationWarning bridge"; Decision line 84: "DELETED... `sys.exit(2)`... no DeprecationWarning bridge"; Failure mode row line 138: `test_python_m_custos_exits_nonzero_with_pointer` requires "no `DeprecationWarning`, no partial delegation"; File Inventory line 107: `cli/main.py` rewritten to 5-line stub returning 2; Task 8 impl line 399-421 rewrites `cli/main.py` fully; Task 8 test line 382 asserts `returncode == 2`).
- **DeprecationWarning-bridge branch** (File Inventory line 117: `tests/test_deprecated_warning_on_old_entry.py` — "still runs + stderr contains `DeprecationWarning`"; Verification checklist line 470: "`python -m custos ... still runs + emits `DeprecationWarning` to stderr`"; Progress row line 492: T8 notes "`DeprecationWarning to stderr + warnings module`").

**Problem**: The plan carries both stances. If the executor reads the failing-test seed from line 117 (File Inventory) or the checklist gate line 470, they build a soft-deprecation bridge (`python -m custos` still runs). Plan 12 T1 Step 2 test assertion (`data["project"]["version"] == "0.2.0"` + `"custos" not in data["project"]["scripts"]`) may still pass superficially, but Plan 12 T9 verification checklist line 464 (hard-dep gate) says team-lead must independently `grep 'SopsAgeVault' src/custos/core/credential_vault.py` — which is fine — but the ENTRYPOINT + user-facing surface would still be split-brain.

More severely, the sabotaged Plan 12 T1 test asserts `"custos" not in data["project"]["scripts"]` — if the DeprecationWarning branch also registers a `custos` script entry (to trigger the warning code path), the assertion fails and Plan 12 T1 cannot land.

**Fix**: Plan 11 must delete the three contradictory items in one edit:
- Line 117 File Inventory row: replace with `tests/test_legacy_cli_removed.py` (already listed at line 378 in T8 impl — consolidate).
- Line 470 verification checklist bullet: rewrite to `python -m custos ... exits nonzero + stderr contains 'arx-runner start' pointer + no DeprecationWarning bridge`.
- Line 492 Progress row T8 notes: change `DeprecationWarning to stderr + warnings module` to `sys.exit(2) + one-line pointer to arx-runner start`.

Cross-ref: lesson #37 (spawn prompt / spec editing before grep implication) — these three lines are exactly the drift lesson #37 protects against; Plan 11 drafter mixed pre-CEO-directive text with post-directive rewrites.

---

## High findings

### H1 — Plan 12 T5 CHANGELOG scaffold content omits Plan 11 breaking items; T9 claim of prior inclusion is false

**Where**:
- Plan 12 line 303 (T5 Step 3): `## [0.2.0] - 2026-07-10` first entry only lists Plan 12 items — "sigstore wheel signing, non-root Dockerfile, LTS commitment, gateway contract v1".
- Plan 12 line 438 (T9 §3 bullet 3): claims "`CHANGELOG.md` §0.2.0 breaking note 已在 T5 landing 时包含 Plan 11 clean-break 项 (legacy `python -m custos` 删除 + SopsAgeVault 删除 + `~/.custos/` 退休)".

**Problem**: T5's own Step 3 description does not mention Plan 11 items. T5 sits between Plan 11 T9 (which does not modify `CHANGELOG.md`, per Plan 11 line 434-456) and Plan 12 T9. Since 0.2.0 is a single tag covering both breaking (Plan 11 `feat!`) and additive (Plan 12 `feat`) changes, `CHANGELOG.md` v0.2.0 entry MUST include Plan 11 items under `### Removed` / `### Changed` / `### Deprecated` and Plan 12 items under `### Added`. T5's description does not carry this instruction, so an executor following T5 verbatim would write a CHANGELOG missing all Plan 11 breaking items — leaving downstream `~=0.2` client pinners (arx) blind to the actual breaking scope.

**Fix**: Plan 12 T5 Step 3 (line 303) — expand the `## [0.2.0]` scaffold instruction to explicitly enumerate:
- `### Removed`: legacy `python -m custos` entry point; legacy `custos` console script; `SopsAgeVault` multi-credential-JSON model; `~/.custos/` state namespace; `--sops-file` / `--age-key-file` CLI flags.
- `### Changed`: state namespace `~/.custos/` -> `~/.arx/`; vault storage model single-file -> per-key `.enc`.
- `### Added`: `[project.scripts].arx-runner`; new subcommands `enroll` / `vault put` / `vault verify` / `vault list` / `start`; sigstore keyless wheel signing; multi-stage non-root Dockerfile; `docs/lts-commitment.md`; `docs/gateway-contract/v1/` JSON Schema.

---

### H2 — Plan 12 T4 `verify-release.sh` implementation misses the `docker run` smoke declared in File Inventory (dead FM2 Layer 3)

**Where**:
- Plan 12 line 153 (File Inventory verify-release.sh): "post-publish smoke test: pull wheel + verify sig, pull image + verify sig + `docker run --rm --help` (health probe)".
- Plan 12 line 182 (FM2): claims Layer 3 (smoke) is one of three independent layers guarding docker root user leakage.
- Plan 12 line 274-286 (T4 Step 3 impl): actual script contains only `pip download` + `sigstore verify` + `docker pull` + `cosign verify`. No `docker run`.

**Problem**: Same dead-branch pattern as lesson #22/#28 — FM2 Layer 3 (smoke) does not exist in the implementation, only in the design intent. Plan 12 claims multi-layer fail-fast is testable independently but Layer 3 is not present. Also, without `docker run` the ENTRYPOINT bug (C1) has no CI-side detection.

**Fix**: Plan 12 T4 Step 3 (line 274-286) — append after `cosign verify`:
```bash
# Health probe: image starts and CLI responds
docker run --rm ghcr.io/the-alephain-guild/custos:v${VERSION} --help
# Non-root probe: independent from test_docker_non_root.py (Layer 3 of FM2)
[ "$(docker inspect --format '{{.Config.User}}' ghcr.io/the-alephain-guild/custos:v${VERSION})" != "root" ] || exit 1
```

---

### H3 — Plan 11 `~/.custos/state/telemetry-wal.db` default retargeting has no owning Task; DEVIATION log still describes pre-CEO-directive coexistence

**Where**:
- Plan 11 line 87 (Decision, Runner state namespace row): "Plan 04 WAL path default (`args.wal_path` at `cli/main.py:92`) is retargeted from `Path.home() / ".custos" / "state" / "telemetry-wal.db"` to `Path.home() / ".arx" / "state" / "telemetry-wal.db"` — a Plan 04 config surface change coordinated in this plan".
- Plan 11 T8 (line 371-428): rewrites `cli/main.py` fully to a 5-line `sys.exit(2)` stub, so the default at `cli/main.py:92` disappears entirely.
- Plan 11 T7 (line 342-368): `start` subcommand implementation does not explicitly instruct where the new default lives.
- Plan 11 line 385 (T8 Step 1 test): `test_default_paths_target_arx_namespace` asserts "default `--wal-path` / `--enrollment-path` all contain `.arx`, none contain `.custos`".
- Plan 11 line 504 (DEVIATION namespace row): still says "Two-namespace persistence... `~/.arx/runner.toml` + `~/.arx/vault/*.enc` (new, this plan) vs `~/.custos/enrollment.json` + `~/.custos/state/telemetry-wal.db` (existing, Plan 04/05). Chose coexistence over rename..." — contradicts the clean-break decision at line 87.

**Problem**:
1. No Task explicitly owns the WAL default retargeting. After T8 rewrites `cli/main.py`, the default must migrate to `subcommands/start.py` (T7) or a shared constants module — but neither T7 nor T8 File Inventory lists this migration.
2. T8 test `test_default_paths_target_arx_namespace` (line 385) will fail if executor didn't add the new default anywhere.
3. Line 504 DEVIATION row is stale text from the pre-CEO-directive draft — still says "chose coexistence" while the actual decision (line 87) is clean-break. If executor treats DEVIATION as authoritative, the test fails.

**Fix**:
- Plan 11 Task 7 File Inventory + Step 3: explicitly instruct "`subcommands/start.py` defines module-level `DEFAULT_WAL_PATH = Path.home() / '.arx' / 'state' / 'telemetry-wal.db'` and `DEFAULT_ENROLLMENT_PATH = Path.home() / '.arx' / 'enrollment.json'`".
- Plan 11 line 504 DEVIATION: rewrite from "coexistence" to reflect the actual CEO clean-break decision (line 87). Or delete this row entirely since the decision table already carries the record.

---

### H4 — Plan 12 Dockerfile does not declare a `VOLUME`/mount for `~/.arx/`; container restart loses vault + runner.toml

**Where**:
- Plan 12 line 149 (File Inventory Dockerfile): `USER 1000:1000` + `WORKDIR /opt/custos`.
- Plan 12 line 225 (T2 Step 3 impl): same USER/WORKDIR; no `VOLUME` declaration.
- Plan 11 clean-break decision: `~/.arx/runner.toml` + `~/.arx/vault/*.enc` + `~/.arx/enrollment.json` + `~/.arx/state/telemetry-wal.db` are the sole state paths.

**Problem**: Container user is UID 1000; the runner reads/writes `~/.arx/` = `/home/uid-1000/.arx/` (or wherever HOME resolves for UID 1000 — likely `/nonexistent` for a bare `USER 1000:1000` without a matching passwd entry). Without an explicit `VOLUME ["/home/custos/.arx"]` declaration + HOME env + passwd entry, three things break:
1. `arx-runner enroll` fails because HOME resolves to `/nonexistent` — runner.toml write fails with permission error.
2. Even if HOME is set, container restart wipes the vault (no volume => ephemeral).
3. `docs/ops/05-deployment.md` (modified by Plan 11 T9) needs to describe `docker run -v ~/.arx:/home/custos/.arx custos-runner:latest ...` but Plan 12 T9 doesn't touch deployment docs.

**Fix**:
- Plan 12 T2 Step 3 (line 225): add
  - `RUN useradd -u 1000 -m -d /home/custos custos` (or equivalent)
  - `ENV HOME=/home/custos`
  - `VOLUME ["/home/custos/.arx"]`
- Plan 12 T9 (or coordinate with Plan 11 T9): add a section in `docs/ops/05-deployment.md` describing the container mount pattern.

---

### H5 — `pyproject.toml` merge coordination: Plan 11 T8 + Plan 12 T1 both edit; if parallel-executed will merge-conflict (lesson #16)

**Where**:
- Plan 11 T8 (line 371-428): adds `[project.scripts].arx-runner`, deletes any `custos = ...`, bumps `version = "0.2.0"`.
- Plan 12 T1 (line 197-213): adds `[project.optional-dependencies].lts` + `[tool.hatch.build.hooks.custom]` block; explicitly claims "Plan 12 不改 script 表本身" (line 206).

**Problem**: Both plans modify `pyproject.toml`. Plan 12 T1 Step 3 line 205-206 relies on Plan 11 being already landed. But nothing in either plan's spawn-time text prevents parallel execute-team worktrees from both branching off pre-Plan-11 main and diverging. If parallel:
- Plan 11 worktree writes `[project.scripts]` + version bump.
- Plan 12 worktree writes `[project.optional-dependencies]` + hatch hook, still on version 0.1.0.
- Merge conflict on the version line + both blocks landing in different order per lesson #16.

Plan 12 verification checklist line 464 has a manual hard-dep gate ("team-lead independently `git log --oneline | grep 'plan 11'` hit ..."), but a manual gate is not enforced by execute-team dispatch.

**Fix**:
- Add explicit strict-serial statement to Plan 12 `Depends on:` header (line 8): "Plan 11 T8 commit landed on `main` is a HARD PRECONDITION. Plan 12 T1 execute-team worktree MUST branch from a `main` HEAD containing Plan 11 T8 squash commit; execute-team spawn prompt must include SHA gate check `git rev-parse HEAD^{tree} | git grep -q '\"arx-runner\"'` before proceeding to Task 1 Step 1".
- Add to Plan 12 pre-execute checklist: "Plan 12 does NOT run in a worktree parallel with Plan 11" (contradicts the false 'parallel possible' vibe from `multi_session_scope: false`).

---

## Medium findings

### M1 — README.md three-way modification risk (Plan 11 T9 + Plan 12 T5 + Plan 12 T9)

**Where**:
- Plan 11 T9 (line 439, 453): rewrites Quick Start (`README.md:76-79`) + adds Breaking Change (0.2.0) section.
- Plan 12 T5 (line 304): trims `## Not Included Yet` (delivered items removed).
- Plan 12 T9 (line 437): "README.md § "Not Included Yet" 剩余项精简（已在 T5 处理）" — a self-redundant clean-up already done by T5.

**Problem**: If parallel worktrees (lesson #16), Plan 11 T9 rewrites §Quick Start and Plan 12 T5 edits §Not Included Yet — these are different sections but on the same file. Git merges usually succeed, but the third-party diff (Plan 12 T9 line 437 claiming further edit) is redundant with T5.

**Fix**:
- Enforce serial: Plan 11 first, then Plan 12 T5, then Plan 12 T9.
- Delete Plan 12 T9 §3 bullet 3 "已在 T5 处理" as a no-op (or make it an inspection-only check).

### M2 — Plan 11 T9 modifies `the-alephain-guild/codex/decisions/ADR-014-...` — cross-repo write outside custos-independent-repo boundary

**Where**: Plan 11 line 440 — modifies `the-alephain-guild/codex/decisions/ADR-014-ecosystem-open-source-boundary.md`.

**Problem**: Custos is an independent Apache-2.0 repo (per its CLAUDE.md §8 "独立开源仓库自足纪律"). Modifying an ADR in the workspace-level `codex/` tree from a custos plan is a cross-boundary write. External auditors cloning custos alone will not see the ADR update. Plan 12 does not cross this boundary.

**Fix**: Two options:
- Plan 11 keeps the ADR update in its Task 9 but explicitly marks it as workspace-scoped, out-of-repo commit (separate from the custos-repo commit).
- Move the ADR update to a workspace-level follow-up plan; Plan 11 close-out records the follow-up but does not touch the ADR itself.

Also cross-ref lesson #3 mandatory-rule §6 — cross-subsystem commit must be `git add <specific-file>` with `scope` tagging. Plan 11 T9 needs to spell this out.

### M3 — DP5 wording drift: "RESOLVED" vs "partial resolve"

**Where**:
- Plan 12 line 101 (DP5 header): "**RESOLVED**".
- Plan 12 line 515 (Applicable lessons, lesson #35 row): "script name (DP5, **partial resolve** — ...)".

**Problem**: Same DP5, two different resolution states in the same plan. Minor drafting drift.

**Fix**: Plan 12 line 515: change "partial resolve" to "resolved" for consistency with line 101.

### M4 — Version tag semantics: 0.2.0 covers both `feat!` (Plan 11) and `feat` (Plan 12); needs explicit CHANGELOG structure to disambiguate downstream `~=0.2` pinners

**Where**:
- Plan 11 T8 commit msg line 428: `feat(custos)!: ...` (breaking).
- Plan 12 line 111 SEMVER MINOR row: "additive-only" — but this refers to future minor lines, not the 0.2.0 landing.
- Plan 12 line 115: arx uses `~=0.2` PEP 440 pin.

**Problem**: SemVer §4 pre-1.0 explicitly allows breaking in `0.Y` minor bumps — technically fine. But the `~=0.2` pin will silently accept the breaking Plan 11 changes on next `pip install --upgrade`. arx-side client integrations that consumed `python -m custos` invocations or `SopsAgeVault` API will break silently unless the arx client pin was explicit.

**Fix**:
- Plan 12 T5 CHANGELOG scaffold: add BOLD `**BREAKING**` prefix on every Plan 11 removal entry (Keep-a-Changelog convention allows this).
- Plan 12 line 115: add sentence "arx client crates that consume runner internals must review the 0.2.0 removals before `pip install --upgrade`; the `~=0.2` pin is intentionally permissive because 0.x pre-1.0 accepts breaking in minor".

### M5 — Boundary constant fanout list incomplete; verify-release.sh + .github/workflows/release.yml usage not enumerated

**Where**: Plan 12 line 515 (lesson #35 fanout row): "T9 联动检 `pyproject.toml + Dockerfile + docs + README`".

**Problem**: Missing from fanout list:
- `.github/workflows/scripts/verify-release.sh` — if C1 fix adds `docker run --rm ... --help`, that invocation calls the script name.
- `.github/workflows/release.yml` — build/publish jobs use wheel filename (`custos_runner-*.whl`) rather than script name; but if release.yml has a post-publish `docker run` step it would use script name.
- `docs/ops/05-deployment.md` (modified by Plan 11 T9) — Docker deployment command examples.
- `docs/design/03-implementation.md` (modified by Plan 11 T9) — CLI invocation examples.
- `README.md:76-79` (Quick Start, rewritten by Plan 11 T9).

**Fix**: Plan 12 T9 line 515 fanout list — expand to: `pyproject.toml + Dockerfile + verify-release.sh + release.yml + docs/lts-commitment.md + docs/ops/05-deployment.md + docs/design/03-implementation.md + README.md + CHANGELOG.md`.

---

## Low / follow-up

### L1 — Plan 12 T5 test file `tests/test_changelog_exists.py` marked "optional"

**Where**: Plan 12 line 300: "可选 `tests/test_changelog_exists.py`".

**Problem**: T5's only independent test is optional. T5's close-out relies on T6 to indirectly verify CHANGELOG presence (T6 test file `test_lts_commitment_doc.py` doesn't assert CHANGELOG existence). This is a mild lesson #17 dead-branch — no independent T5 gate.

**Fix**: Promote `tests/test_changelog_exists.py` from optional to required. Add assertions:
- `## [0.2.0]` section present
- section contains `### Removed` (Plan 11 breaking items)
- section contains `### Added` (Plan 12 additive items)

### L2 — Plan 11 T9 file inventory near-duplicated (lines 441-443 + lines 444-446)

**Where**: Plan 11 lines 441-446: three items listed twice ("Modify `.forge/plans/2026-07/11-...` — status to `✅ Completed`" appears at 441 AND 444; ".forge/README.md — add Plan 11 row" at 442 AND 445; version bump discussion at 443 AND 446).

**Problem**: Housekeeping — appears to be a copy-paste artifact from an earlier plan draft.

**Fix**: Delete the second copy (lines 444-446).

---

## Positive observations

- **Hard-dep sequencing intent is correct**: Plan 12 line 8 header + line 72 plan-to-plan row + line 464 verification gate + line 470 progress row all describe the same "Plan 11 lands first, then Plan 12" story. The gate `grep 'SopsAgeVault' ...` + `grep '"arx-runner"' pyproject.toml` is well-designed for manual verification.
- **DP5 resolution logic is sound**: single source of truth in Plan 11 `pyproject.toml`, Plan 12 consumes downstream. Once C1 is fixed the boundary constant single-source rule (lesson #35) holds.
- **Failure-mode coverage** (Plan 11: 14 code-level tests, all `def test_*` names present in the failure-mode table; Plan 12: 11 FM items with multi-layer independence design) meets lesson #17 discipline.
- **`~/.arx/` namespace unification** (Plan 11 decision) is the correct clean-break call — avoids long-term dual-namespace drift.
- **Foundation Scan iteration log** (Plan 12 lines 503-506) documents the 4-dim methodology (lesson #14/#30/#33/#33b) explicitly.
- **CEO clean-break directive traceability**: both plans cite the 2026-07-10 CEO directive at the same points, giving the review a stable reference axis.
- **Applicable-lessons self-audit** (Plan 12 lines 508-518) is comprehensive and cites the correct rule numbers.
- **Contract v1 semantic separation** (Plan 12 line 64 clarifying that CustosGateway is NATS payload + Rust trait, not REST HTTP) prevents future confusion with `openapi`-style specs.

---

## Suggested execution ordering

**Strict serial required** (do NOT parallelize):

1. **Plan 11 first, full landing on `main`** (T1..T9 all squashed). Rationale:
   - `pyproject.toml` script table + version 0.2.0 must exist for Plan 12 T1 gate to pass.
   - `~/.arx/` namespace must be the sole namespace before Plan 12 Dockerfile references `~/.arx/` mount.
   - `arx-runner` script name single-source (Plan 11 pyproject.toml) must be committed before Plan 12 Dockerfile ENTRYPOINT + docs references consume it.

2. **Plan 12 execute-team may start only when** all three team-lead gates from Plan 12 line 464 pass:
   - `git log --oneline | grep 'plan 11'` hits (Plan 11 T8 squash)
   - `grep '"arx-runner"' pyproject.toml` hits 1
   - `grep 'SopsAgeVault' src/custos/core/credential_vault.py` hits 0

3. **Within Plan 12**, three tracks can parallelize IF SHA-gate is checked:
   - Track A (T1 + T5 + T9 documentation): pyproject.toml + CHANGELOG + README + close-out — must be strictly serial (all touch pyproject.toml OR README).
   - Track B (T2 + T3 + T4 CI/Docker): Dockerfile + wheel signing + release.yml — independent from Track A.
   - Track C (T6 + T7 + T8 contracts/reproducible): LTS docs + gateway schemas + reproducible-build — independent from A and B.

4. **Do not tag `v0.2.0`** until Plan 12 T9 close-out passes and Plan 11 close-out already committed. The v0.2.0 tag must point at a commit where BOTH plans' invariants hold; premature tagging on Plan 11 close-out will create a release without CI + docs.

---

## Merge conflict prevention checklist (hand-off to execute-team)

- [ ] Plan 12 execute-team spawn prompt includes SHA gate: `git log --oneline | grep 'plan 11 t8'` must hit before Plan 12 T1 starts.
- [ ] Plan 12 execute-team worktree branches from a `main` HEAD that contains Plan 11 T8 squash commit — NOT from any earlier commit.
- [ ] `pyproject.toml` — only Plan 11 T8 owns `[project.scripts]` + `version`; only Plan 12 T1 owns `[project.optional-dependencies].lts` + `[tool.hatch.build.hooks.custom]`. Do not cross ownership.
- [ ] `README.md` — Plan 11 T9 owns §Quick Start + §Upgrade from 0.1.x; Plan 12 T5 owns §Not Included Yet trim. Plan 12 T9 does NOT further edit README.md.
- [ ] `CHANGELOG.md` — Plan 12 T5 is sole owner. Plan 11 T9 must NOT create or edit `CHANGELOG.md`. If Plan 11 accidentally lands a `CHANGELOG.md`, execute-team `git restore --staged CHANGELOG.md` before Plan 11 commit.
- [ ] `Dockerfile` — Plan 12 T2 sole owner. ENTRYPOINT MUST be `["arx-runner", "start"]` per Plan 12 line 149 (fix line 225 per C1).
- [ ] `.github/workflows/release.yml` — Plan 12 T4 sole owner.
- [ ] `docs/lts-commitment.md` + `docs/upgrade-path.md` — Plan 12 T6 sole owner.
- [ ] `docs/gateway-contract/v1/*` — Plan 12 T7 sole owner.
- [ ] `docs/reproducible-build.md` — Plan 12 T8 sole owner.
- [ ] `CONTRIBUTING.md` + `SECURITY.md` — Plan 12 T9 sole owner.
- [ ] `docs/design/enrollment.md` + `docs/design/credential_vault.md` + `docs/design/03-implementation.md` + `docs/ops/05-deployment.md` — Plan 11 T9 sole owner.
- [ ] ADR-014 workspace-level edit (Plan 11 T9 line 440) — separate commit outside custos-repo; team-lead confirms cross-boundary edit is explicit + `git add <specific-file>` per lesson #3.
- [ ] `src/custos/cli/main.py` — Plan 11 T8 sole owner (5-line stub rewrite). No Plan 12 Task touches it.
- [ ] `src/custos/core/credential_vault.py` — Plan 11 T8 sole owner (delete lines 121-206). No Plan 12 Task touches it.
- [ ] Version tag `v0.2.0` — only after Plan 12 T9 close-out. Team-lead runs `git tag -s v0.2.0` at Plan 12 T9 close-out commit HEAD.
- [ ] Post-publish CI verify-release.sh must include `docker run --rm --help` (C1/H2 fix) so the ENTRYPOINT surface is smoke-tested independently.
