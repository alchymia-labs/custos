# Plan 11 Deep Review (Claude, opus-4-7[1m])

**Reviewed at**: 2026-07-10
**Plan file**: `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md`
**Reviewer lens**: safety + failure modes + clean-break coherence + Task ordering
**Evidence baseline**: HEAD = `d3a7948` (Plan 12 draft commit)

## Verdict

`REQUEST_CHANGES`

- **Critical**: 3 (internal `clean-break ↔ deprecation/coexistence` contradiction; Task 7 → Task 8 ordering bug that breaks `subcommands/start.py` after `cli/main.py` is stubbed; runtime vault reader gap after `SopsAgeVault` deletion)
- **High**: 4
- **Medium**: 8
- **Low / follow-up**: 7
- **Positive**: 6

The plan's core direction (subcommand restructure + `arx-runner` single entry + clean-break) is sound and evidence-anchored, but the file carries **substantial residue from an earlier soft-deprecation draft** that directly contradicts the CEO clean-break directive stated at lines 64-66 / 84. Landing without reconciliation will cause executor thrash and downstream Plan 12 assumption breakage.

---

## Critical findings (block landing)

### C1 — Clean-break directive contradicts multiple `DeprecationWarning` / `coexistence` residues throughout the plan

- **Location**:
  - Plan line 64 (Goal), 66 (CEO directive), 84 (Key Design Decision `custos` legacy entry point) — **clean-break: no DeprecationWarning bridge, no partial delegation**
  - Plan line 117 (File Inventory) — `tests/test_deprecated_warning_on_old_entry.py` "still runs + emits `DeprecationWarning` + `arx-runner start` guidance"
  - Plan line 138 (Failure-Mode Contract) — `test_python_m_custos_exits_nonzero_with_pointer` correctly enforces clean-break, but conflicts with line 117 test naming
  - Plan line 470 (Verification checklist) — "`python -m custos ... still runs + emits DeprecationWarning to stderr`" (**pure contradiction**)
  - Plan line 492 (Progress table T8) — Notes column "`DeprecationWarning to stderr + warnings module`" (**pure contradiction**)
  - Plan line 119-120 (File Inventory docs) — enrollment.md "**Add** ... coexistence with existing NATS enrollment" + credential_vault.md "**Add** ... coexistence with the multi-credential sops JSON"
  - Plan lines 449-455 (Task 9 Actions) — steps 3 + 4 explicitly say "coexistence with existing NATS `enrollment.json` (paragraph)" and "coexistence with existing single-file `SopsAgeVault` (paragraph)"
  - Plan lines 504-506 (Deviations table) — three `⏳ pending review-time` rows still describe **coexistence** for namespace / enroll transport / vault storage model
- **Evidence**:
  ```
  $ grep -nE 'DeprecationWarning|coexistence' .forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md
  117:| tests/test_deprecated_warning_on_old_entry.py | Create | `python -m custos ...` still runs + emits `DeprecationWarning`
  138:| legacy entry point clean break | ... no `DeprecationWarning`, no partial delegation
  451: `docs/design/enrollment.md` — ... + coexistence with existing NATS `enrollment.json` (paragraph, not a rewrite).
  452: `docs/design/credential_vault.md` — ... + coexistence with existing single-file `SopsAgeVault` (paragraph).
  470:- [ ] `python -m custos ...` still runs + emits `DeprecationWarning` to stderr
  492: | T8 [project.scripts] + deprecated | 🔲 | | DeprecationWarning to stderr + warnings module ...
  504: DEVIATION | namespace | Two-namespace persistence ... Chose coexistence over rename ...
  506: DEVIATION | vault storage model | Per-key ... coexists with single-file multi-credential sops JSON model at credential_vault.py:121-206 (Plan 05, unchanged) ...
  ```
- **Impact**: TDD executor at T8 will encounter mutually exclusive test contracts (Verification checklist + `test_deprecated_warning_on_old_entry.py` demand `DeprecationWarning`; T8's `test_python_m_custos_exits_nonzero_with_pointer` + KDT line 84 forbid it). Whichever the executor picks, the reviewer will bounce it back. Same for Task 9 Actions: an executor following steps 3-5 verbatim would write "coexistence" paragraphs contradicting the "Rewrite ... Do NOT preserve the old section" wording in the same task's Files section (line 435). Downstream Plan 12 DP5 relies on `SopsAgeVault` fully removed + `~/.custos/` retired + `arx-runner` single entry (see Plan 12 line 8, line 464 hard gate: `grep 'SopsAgeVault' src/custos/core/credential_vault.py` must hit 0). Any deprecation-bridge landing violates that gate.
- **Suggested fix**:
  1. Delete plan line 117 entirely (rename or delete `test_deprecated_warning_on_old_entry.py`); T8 already provides `test_python_m_custos_exits_nonzero_with_pointer` + `test_no_custos_console_script_registered` covering the clean-break contract.
  2. Rewrite line 470 verification checkbox to: `` `python -m custos ...` exits code 2 with `arx-runner start` pointer + no `DeprecationWarning` in stderr``.
  3. Rewrite line 492 T8 Notes: `clean-break: exit 2 with pointer; test_python_m_custos_exits_nonzero_with_pointer + test_no_custos_console_script_registered + test_sops_age_vault_class_removed + test_default_paths_target_arx_namespace`.
  4. Delete stale File Inventory phrasings at lines 119-120 (drop "Add ... coexistence" — Task 9 Files at 435-436 already frames these as rewrites, not additive).
  5. Rewrite Task 9 Actions steps 3-4 (lines 451-452) to remove "coexistence" language; align with Task 9 Files section wording ("replace" / "rewrite" / "single supported production vault").
  6. Update Deviations table lines 504-506:
     - "namespace": change from "coexistence" to "`~/.arx/` sole namespace; `~/.custos/` retired outright with manual `mv` migration in README Upgrade section"
     - "enroll transport": change from "NATS kept for backward compat" to "NATS `EnrollmentClient` retained as low-level building block; CLI-facing surface is HTTP-only per lifecycle.md §0.2.2" (matches Task 9 Files line 436).
     - "vault storage model": remove the "coexists ... Plan 05, unchanged" clause; replace with "Per-key `.enc` is the sole runtime vault; `SopsAgeVault` deleted (T8)". Flip `⏳ pending review-time` → `✅ CEO directive 2026-07-10`.

### C2 — Task 7 places `run_daemon` in `cli/main.py`, Task 8 deletes it → `subcommands/start.py` imports vanish

- **Location**: Plan lines 342-367 (Task 7) + lines 371-428 (Task 8) + line 107 (File Inventory `cli/main.py`)
- **Evidence**:
  - Task 7 Step 3 (line 359): "Refactor `cli/main.py`: extract the post-`_parse_args` half of `_run` into a new `async def run_daemon(args)` that expects a filled `argparse.Namespace`. **Legacy `_run` becomes `run_daemon(_parse_args(...))`**." — i.e., `run_daemon` lives in `cli/main.py`.
  - Task 7 Step 3.3 (line 363): "`asyncio.run(main.run_daemon(ns))`" — `subcommands/start.py` imports `main.run_daemon`.
  - Task 8 line 107: `cli/main.py` **"Delete majority"** — Delete `_parse_args` + `_build_vault` + `_build_host` + `_build_reconciler` + `_heartbeat_loop` + `_run` (**relocated to `cli/subcommands/start.py`**). Only 5-line stub `main()` remains.
  - Task 8 Step 3 (lines 399-421): The concrete stub rewrite of `cli/main.py` **removes `run_daemon` entirely** — the new file contents only expose `def main(argv) -> int` that prints an error and returns 2.
- **Impact**: After T7 lands, `subcommands/start.py` calls `main.run_daemon(ns)`. After T8 lands (which rewrites `cli/main.py` to the 5-line stub), `main.run_daemon` no longer exists. `arx-runner start` will raise `AttributeError: module 'custos.cli.main' has no attribute 'run_daemon'` at first invocation. `test_start_reads_runner_toml_and_wires_reconciler` (T7 Step 1) will start green after T7 but turn red after T8. All Plan 04 reconciler regression tests referenced at T7 Step 4 will also fail.
- **Suggested fix**:
  - Option A (preferred): Move `run_daemon` into a new dedicated module `src/custos/cli/_daemon.py` at Task 7 time. `subcommands/start.py` imports `from custos.cli._daemon import run_daemon`. Task 8 then deletes `cli/main.py` internals without collateral. Extend File Inventory row for `_daemon.py` (Create) accordingly.
  - Option B: Move `run_daemon` (+ the reconciler / host / vault / heartbeat builders it depends on — see also C3) into `subcommands/start.py` directly at Task 7 time; Task 7 Step 3.1 already extracts the coroutine, so let it land at its final home. Task 8's line 107 language ("relocated to `cli/subcommands/start.py`") already hints at this intent; the plan just needs Task 7's Step 3 rewritten to match ("extract to `subcommands/start.py`, not `cli/main.py`") so the two Tasks are consistent.
  - Whichever option chosen, adjust File Inventory rows for `cli/main.py` and `subcommands/start.py` accordingly; also add `_build_vault` / `_build_host` / `_build_reconciler` / `_heartbeat_loop` to the relocation list (T8 currently only names `_run` as "relocated").

### C3 — Runtime vault reader gap: `SopsAgeVault` deleted (T8) but no replacement class reads `~/.arx/vault/<key-id>.enc` at reconciler runtime

- **Location**:
  - Plan lines 72-73, 108, 372, 376 (T8 deletes `SopsAgeVault` class outright)
  - Plan line 362 (T7 Step 3.2): "Build a compatible `argparse.Namespace` with ... `sops_file=optional`, `age_key_file=optional`" — stale from soft-deprecation draft; these fields are meaningless after SopsAgeVault deletion.
  - `src/custos/core/deployment_reconciler.py:35` + `:59` — Reconciler holds `credential_vault: CredentialVaultProtocol` and calls `.decrypt(credential_id)` at deploy time.
  - Grep evidence: only two vault classes exist today — `CredentialVault` (mock, `credential_vault.py:101-118`) + `SopsAgeVault` (production, `:121-206`). Delete SopsAgeVault → only mock remains for live paths.
- **Impact**: After T8 the reconciler cannot read real exchange credentials in production. `vault put` writes `~/.arx/vault/<key-id>.enc` files (T5), and `vault verify` reads them one-shot (T6), but the running daemon has no path from `credential_vault.decrypt("binance-paper")` → `~/.arx/vault/binance-paper.enc`. Live mode is silently broken: the reconciler will either fall back to `MockVault` (returning `<mock>` secret) or crash with `KeyError`. The plan claims to align with lifecycle.md §0.3 verbatim, but §0.3.2 requires the runtime to actually decrypt per-key files at deploy time.
- **Suggested fix**:
  - Add a new module `src/custos/core/per_key_vault.py` (or extend `credential_vault.py`) to the File Inventory: `class PerKeyVault(_BaseVault)` reads `<vault-dir>/<credential_id>.enc` via `sops --decrypt` (mirrors the T6 `vault verify` decrypt path but returns the parsed cred dict for reconciler consumption). Preserve `_verify_permission_scope` + `_emit_decrypt_audit` invariants.
  - Add failure-mode tests: `test_per_key_vault_missing_enc_file_clear_error`, `test_per_key_vault_scope_violation`, `test_per_key_vault_sops_fail_no_silent_return` (mirrors T6 verify contracts but for the runtime call site).
  - Extend Task 7 Step 3.2 to name `PerKeyVault(vault_dir=~/.arx/vault, tenant_id=..., initiator=...)` as the reconciler's `credential_vault` argument, replacing `_build_vault` entirely. Delete stale `sops_file` / `age_key_file` Namespace fields at Step 3.2.
  - This closes the loop between T5 (write) / T6 (verify) / T7 (runtime read), and cleanly retires `_build_vault` — currently the plan is silent on how `_build_vault` is dispositioned after T8.

---

## High findings

### H1 — `--backend` URL has no scheme allowlist / boundary validation (lesson #26 fanout)

- **Location**: Plan lines 251-281 (Task 4 `enroll` implementation) + line 274 `urllib.request.Request(f"{backend}/api/v1/enrollments", ...)`.
- **Evidence**:
  - Task 2 validators (lines 195-215) only cover `tenant_id` / `runner_id` / `key-id` — no URL validator.
  - Task 4 tests (lines 258-265) do not include a `--backend file://...` / `--backend gopher://...` rejection case.
  - `urllib.request.urlopen` accepts `file://`, `ftp://`, `data://` — a malicious enrollment token bearer script setting `--backend file:///dev/urandom` would happily read local files instead of POSTing.
- **Impact**: Runner host command-line injection via `--backend` reaches `urlopen` unfiltered. Not a red-line breach (KEK stays local), but violates lesson #26 boundary-string invariant on the first HTTP surface in custos. A malicious operator (or compromised deployment script) could make the runner read arbitrary local files as if they were HTTP responses.
- **Suggested fix**:
  - Extend `validators.py` (Task 2) with `validate_backend_url(value: str) -> str`: parse via `urllib.parse.urlparse`, require `scheme in {"http", "https"}`, require non-empty netloc, reject fragment / userinfo. Reject at parse-time in the enroll subparser (`type=validators.validate_backend_url`).
  - Add a new failure-mode row to the contract table + a new test `test_enroll_rejects_non_http_backend` covering `file://` / `gopher://` / bare `foo`.
  - Consider `--insecure` opt-in for `http://` in prod; default warn-loud when scheme is `http`.

### H2 — Task 9 has two conflicting sub-sections + duplicated bullets

- **Location**: Plan lines 432-458 (Task 9 body).
- **Evidence**:
  - Files section (lines 434-446) says clean-break rewrite ("Rewrite `docs/design/credential_vault.md` — **replace** the entire `SopsAgeVault` section ... Do NOT preserve the old section").
  - Actions section (lines 448-456) contradicts with "coexistence with existing NATS `enrollment.json` (paragraph, not a rewrite)" and "coexistence with existing single-file `SopsAgeVault` (paragraph)".
  - Lines 441-443 (Files) list plan status flip + `.forge/README.md` update + version bump; then lines 444-446 (still Files) **repeat verbatim** the same three items with slightly different wording ("adds new console-script surface + new subcommands + new `~/.arx/` filesystem contract"). This is dead residue from an earlier redraft that was never garbage-collected.
- **Impact**: Executor confusion at T9 close-out. If they follow Files verbatim they get clean-break rewrite; if they follow Actions they get additive paragraph. Duplicated bullets amplify risk of double-editing (e.g., double-bumping version, double-appending .forge/README.md rows).
- **Suggested fix**:
  - Delete lines 444-446 entirely (duplicate).
  - Rewrite Actions steps 3-4 (lines 451-452) to remove "coexistence" language and align with Files section (clean-break rewrite of both docs).
  - Consider merging Actions + Files into a single unified list (Actions currently mirrors Files with different wording, adding no signal).

### H3 — Task 7 Step 3.2 keeps stale `sops_file` / `age_key_file` Namespace fields (soft-deprecation residue)

- **Location**: Plan line 362.
- **Evidence**: "Build a compatible `argparse.Namespace` with tenant_id / runner_id from record + CLI overrides for nats_url / wal_path / snapshot_interval_secs / engine / use_nt_host / reconcile_strategy_id / heartbeat_interval / enrollment_token=None / enrollment_path=default / **sops_file=optional / age_key_file=optional**."
- **Impact**: T8 deletes `SopsAgeVault` and `_build_vault` should also lose its `sops_file` / `age_key_file` code path (per KDT line 84). T7 code that passes these fields wires nothing — but if left as-is, an executor might preserve the old `_build_vault` scaffolding, which reads `args.sops_file` and either raises the "半配置拒绝" `SystemExit` or falls into `MockVault`. This is exactly the C3 gap surfaced in T7's language.
- **Suggested fix**: Remove `sops_file` / `age_key_file` from the T7 Step 3.2 Namespace. Add `vault_dir` (default `~/.arx/vault`) so `PerKeyVault` (see C3) has its config. Update T7 test `test_start_preserves_engine_and_wal_flags` to also assert `--vault-dir` override.

### H4 — Language Policy: T5 audit-event source uses stdlib logging, not structlog

- **Location**: Plan line 306 ("Emit structlog `credential_encrypted` audit event ... mirrors the decrypt audit event at `credential_vault.py:64-81`") + `src/custos/core/credential_vault.py:32-36` + `:64-81`.
- **Evidence**:
  ```
  src/custos/core/credential_vault.py:32: # Use stdlib logging so existing test_credential_vault.py caplog assertions
  src/custos/core/credential_vault.py:36: _log = logging.getLogger("custos.credential_vault")
  src/custos/core/credential_vault.py:72:         _log.info("credential_decrypted", extra={...})
  ```
- **Impact**: T5 says the new `credential_encrypted` audit event uses **structlog** but the pattern it mirrors is **stdlib logging with `extra={}`**. If T5 implementation writes `structlog.get_logger().info(...)`, `test_vault_put_never_logs_secret` (which relies on stdlib caplog) will not observe it, and downstream audit-chain writers that pattern-match on `custos.credential_vault` stdlib logger will miss the new event. Non-red-line but breaks audit-chain integration.
- **Suggested fix**: Rewrite T5 Step 3 last bullet to: "Emit **stdlib logging** `credential_encrypted` audit event via `_log.info(..., extra={"audit_event": AuditEvent.CREDENTIAL_ENCRYPTED.value, "key_id": ..., "tenant_id": ...})` — mirrors the decrypt audit event at `credential_vault.py:64-81`, keeping the audit writer's stdlib-caplog pattern-match discipline (`credential_vault.py:32-35` intentional-choice comment)." Also add `CREDENTIAL_ENCRYPTED = "CredentialEncrypted"` to the `AuditEvent` enum at `credential_vault.py:39-46`, since T8 keeps the base class.

---

## Medium findings

### M1 — T4 payload lacks `tenant_id` — server-side tenant resolution mechanism unstated

- **Location**: Plan line 265 (test assertion) + line 275 (payload construction).
- **Evidence**: `test_enroll_payload_shape` asserts `{"token_hash": <sha256 hex>, "runner_id": <id>, "agent_version": <str>, "capabilities": <list>}` — no `tenant_id`. Existing NATS `enrollment.py:57-63` also omits `tenant_id`.
- **Impact**: How does the backend map `token_hash` → tenant? If via server-side pre-issued token DB lookup, that must be explicit in the arx-78 contract cross-ref. If the CLI needs to send `tenant_id`, T4 must add it. Otherwise multi-tenant enrollments could silently misroute.
- **Suggested fix**: Add a one-line note in T4 "**payload contract with arx-78**": "backend resolves tenant from `token_hash` via server-side lookup (issued token → tenant mapping); runner does not send `tenant_id`. `--tenant-id` CLI flag is captured only for local `runner.toml` persistence + subsequent `start` invocation." Cross-ref `arx-78` §payload spec.

### M2 — T4 `--capabilities` list flag underspecified (argparse nargs semantics)

- **Location**: Plan line 270 (`--capabilities`).
- **Evidence**: argparse cannot produce a list from a single `--capabilities x` flag without either `nargs='+'` (space-separated), `nargs='*'` + repeat, or `action='append'` (repeat flag). Plan doesn't say.
- **Impact**: Two implementers will produce two incompatible surfaces. Also the plan's `test_enroll_payload_shape` asserts `capabilities: list` without saying how the CLI accepts it.
- **Suggested fix**: Explicit in T4 Step 3: "`--capabilities` uses `action='append'` (repeat flag: `--capabilities nautilus --capabilities noop-host`) so each value is validated individually and a caller with zero `--capabilities` invocations sends `[]`."

### M3 — T5 `--api-secret` on command line — process listings expose the secret

- **Location**: Plan line 302 (Task 5 Step 3 arg list).
- **Evidence**: `--api-secret` presented as a normal argparse flag. On multi-user hosts / auditable process lists (`ps aux`, `/proc/<pid>/cmdline`), the secret is readable by any user in the pid namespace during the `sops --encrypt` subprocess window.
- **Impact**: Red line 0.1 says "Key/KEK 永不出进程" but doesn't specifically forbid a short cmdline exposure. Still a defense-in-depth gap — a lifecycle.md §0.3 audit-tier operator would rightly flag it.
- **Suggested fix**: T5 Step 3 must offer:
  - `--api-secret-stdin` (read from `sys.stdin.readline().rstrip("\n")`, primary)
  - `--api-secret-env ENV_NAME` (read from `os.environ[ENV_NAME]`, secondary)
  - `--api-secret <value>` (deprecated / demo only, print red warning to stderr)
  - Add failure-mode test `test_vault_put_prefers_stdin_and_warns_on_cmdline_secret`.

### M4 — T4 lacks `HTTP 301/302` redirect handling contract

- **Location**: Plan lines 258-278 (Task 4).
- **Evidence**: `urllib.request.urlopen` by default follows redirects. If backend responds 301 → `file:///etc/passwd`, urlopen follows. (Related to H1.)
- **Impact**: Redirect-to-file scheme escalation.
- **Suggested fix**: T4 Step 3.4: build `urllib.request.Request(...)` with `HTTPRedirectHandler` disabled or with a custom handler that re-validates the scheme (defense-in-depth complement to H1's parse-time check).

### M5 — T4 `timeout=30` is not aligned with credential_vault decrypt subprocess timeout

- **Location**: Plan line 275 (`urlopen(req, timeout=30)`) + `src/custos/core/credential_vault.py:162` (`subprocess.run(..., timeout=30)`).
- **Evidence**: Consistent — both are 30s. Documentation nit only: plan doesn't explicitly say "30s matches sops decrypt subprocess timeout invariant."
- **Impact**: Consistency should be an explicit invariant so future timeouts don't drift.
- **Suggested fix**: T4 Step 3.4 comment: "`timeout=30` matches `credential_vault.py:162` sops-decrypt subprocess timeout — hard invariant across all zero-dep external I/O boundaries."

### M6 — Deviations table row "numbering" (line 503) is not a deviation

- **Location**: Line 503.
- **Evidence**: "Plan 11 chosen (not 09 or 10) because `.forge/README.md:65,67` reserves 09 for hook infra formalization and 10+ for future engine backends."
- **Impact**: Confuses genuine deviations (namespace, transport, vault storage model) with an allocation choice.
- **Suggested fix**: Delete the row. Numbering rationale belongs in the Context section, not the Deviations table.

### M7 — T6 `_verify_permission_scope` reuse depends on file layout post-deletion

- **Location**: Plan line 332 ("`_verify_permission_scope` (reuse from `credential_vault.py` — import + call)").
- **Evidence**: `_verify_permission_scope` is a staticmethod on `_BaseVault` (`credential_vault.py:83-98`). T8 only deletes `SopsAgeVault` at `:121-206`, keeping the base class intact. So the import path is stable, but plan doesn't spell this out.
- **Impact**: Executor might delete more than intended (e.g., "delete lines 84-206" instead of "delete lines 121-206"). Failing to preserve `_verify_permission_scope` breaks T6 verify.
- **Suggested fix**: T8 File Inventory line 108: "**Delete lines 121-206** — `SopsAgeVault` class only. **Preserve** `_BaseVault._verify_permission_scope` (lines 83-98) and `_BaseVault._emit_decrypt_audit` (lines 64-81); T6 `vault verify` reuses them via `from custos.core.credential_vault import _BaseVault` (or expose them as module-level functions if the underscore prefix bothers linters)."

### M8 — Task 9 close-out lacks lesson #40 red-line gate satisfaction table

- **Location**: Task 9 lines 448-458 (Actions).
- **Evidence**: Close-out Report template mentioned at Action 7 says "(a) actual file inventory delta vs planned, (b) any failure modes uncovered ..., (c) any deviations logged." No mention of the "红线 gate 满足度" table required by lesson #40 (custos rule alias) for red-line-touching plans.
- **Impact**: Plan 11 touches red line 0.1 (Key never out of process — via new vault put path + audit event) + red line 0.4 tangentially (payload wire format). Close-out without lesson #40 table risks partial-scope silent claims.
- **Suggested fix**: Add Action 8 template: "**红线 gate 满足度 table** — one row per red line (0.1 / 0.2 / 0.3 / 0.4). Columns: `red_line | code_coverage (test_* names) | runtime_wire (composition root file:line) | defer_status (in-scope? defer_to_plan?) | follow_up_plan_ref`." Explicitly claim red line 0.2 (G6 host gate) is preserved unchanged (start subcommand delegates to existing reconciler + host wire unchanged); red line 0.3 preserved (start reuses full reconciler + FallbackBreaker + ZombieWatchdog chain unchanged).

---

## Low / follow-up

### L1 — T5 sops encrypt via `/dev/stdin` may leave payload in `sh` process memory buffers
- Mitigation: pass `input=...` bytes directly to `subprocess.run` (not through `sh`). Plan text at line 304 already does this correctly (`subprocess.run(["sops", ...], input=payload.encode())`) — just note in code comment.

### L2 — Plan says "grep -c 'add_subparsers' src/custos/cli/main.py = 0" (line 28) — verified accurate as of HEAD 2026-07-10
- No action; positive baseline evidence.

### L3 — `--vault-dir` default `~/.arx/vault` conflicts with T7 Step 3.2 unstated default
- If T7 keeps `runner.toml` in `~/.arx/` and vault in `~/.arx/vault/`, `~/.arx/` dir mode invariant (0o700) must be honored by both. T1 tests only cover `runner.toml.parent.mkdir(mode=0o700)`. Add cross-cutting test: `test_vault_put_reuses_arx_dir_0700` in T5.

### L4 — README.md Upgrade section (line 439) mixes CLI syntax and shell `mv` commands
- The `mv ~/.custos/{enrollment.json,state} ~/.arx/` uses brace expansion, which is bash-specific. Users on `dash` / `sh` will get errors. Note in README: "assumes bash / zsh; on POSIX sh use two separate `mv` commands."

### L5 — ADR-014 edit at line 440 crosses `custos/` → workspace `the-alephain-guild/codex/`
- This is a cross-repo change. Per custos independent-repo discipline (`CLAUDE.md` §8 "独立开源仓库自足纪律"), plan should note this Task 9 action is workspace-only (invisible in independent `git clone custos`). If executor runs independent-repo, this action is silently skipped. Add explicit note: "workspace-only action; independent-repo executors log a follow-up note in the plan close-out instead."

### L6 — `test_deprecated_warning_on_old_entry.py` name is stale even after C1 fix
- Under clean-break, rename to `test_legacy_cli_removed.py` (already used at T8 Step 1 line 383). Delete the stale row at line 117 File Inventory; T8's `test_legacy_cli_removed.py` covers it.

### L7 — `pyproject.toml` version bump duplicated in T8 Step 3 (line 397) and T9 Action 6 (line 454)
- If T8 already bumps to `0.2.0`, T9 Action 6 is a no-op that risks accidentally bumping to `0.3.0`. Clarify: "T8 does the actual bump; T9 verifies via `grep '^version = "0.2.0"' pyproject.toml` = 1 hit."

---

## Positive observations

- **P1**: Plan 1.5 evidence anchors (lines 25-47) are grep-verified against HEAD 2026-07-10; independent verification confirms `_parse_args:36`, `_build_vault:132`, `_build_reconciler:181`, `_run:212`, `SopsAgeVault:121`, `_verify_permission_scope:84`, `hash_token:27` all resolve — solid Foundation Scan.
- **P2**: Zero-dep policy consistently applied (stdlib `argparse.add_subparsers`, `urllib.request`, `tomllib`, `subprocess`). Chosen as red-line-adjacent audit-simplicity discipline (KDT line 80). Correct call for custos non-custodial positioning.
- **P3**: Failure-mode contract table (lines 128-144) covers 16 failure modes across 3 wire tiers with named tests — exceeds lesson #17 minimum bar.
- **P4**: Lesson #26 boundary validation applied to `tenant_id` / `runner_id` / `key-id` — with `argparse.ArgumentTypeError` at parse time (before filesystem join). This is the correct pattern (see H1 for the missed URL case).
- **P5**: Task 9 line 440's ADR-014 amendment cross-references custos Plans 11 + 12 close-outs — establishes traceability chain per lesson #38 (CEO override four-piece) even though this plan is not itself a CEO override.
- **P6**: Verification checklist line 475 explicitly reminds executor about lesson #15 (no `Plan NN` markers in `.py` source comments) — good preemptive guard.

---

## Cross-plan handoff notes (to Plan 12 reviewer)

- **Plan 12 hard-dep gate integrity**: Plan 12 line 464 requires `grep 'SopsAgeVault' src/custos/core/credential_vault.py` = 0. Plan 11's C1 contradictions could leak a soft-deprecation window where `SopsAgeVault` survives + `arx-runner` entry lands simultaneously → Plan 12 T5 landing test `data["project"]["scripts"]["arx-runner"] == "custos.cli.subcommands:main"` still passes, but `SopsAgeVault` grep gate fails. Plan 12 would then block on Plan 11 rework. Recommend Plan 11 reworks C1 first, lands clean-break, before Plan 12 START gate opens.
- **`~/.arx/` namespace commitment**: Plan 12 DP5 assumes Plan 11 fully retires `~/.custos/`. Plan 11's C3 vault-reader gap could ship a runtime that still reads `~/.custos/vault/*` fallback if executor patches it in ad-hoc. Plan 12 T4 `Dockerfile ENTRYPOINT ["arx-runner", "start"]` would then behave differently at runtime vs. audit surface. Reviewers should flag any `~/.custos` residue in Plan 11's fix cycle.
- **`arx-runner` entry name single-source**: both plans point at `custos.cli.subcommands:main` as the entry. Confirm C2 fix (Option A/B) keeps `subcommands/__init__.py:main` as the entry (Task 8 line 393). If C2 fix moves `run_daemon` to `_daemon.py` or `subcommands/start.py`, the entry point remains `custos.cli.subcommands:main` (unchanged), so Plan 12 pyproject scripts assertion is safe.
- **Version bump coordination**: Plan 11 T8 bumps to `0.2.0`. Plan 12 T1 says "`[project.scripts]` + version bump 已由 Plan 11 落地" — assumes Plan 11 already bumped. If Plan 11 lands without T8 (partial split), Plan 12 T1 tests fail. Reviewers should tag Plan 11 T8 as "**must not split from T1-T7**" — bump must ride with the clean-break.

---

*Reviewer: Claude (opus-4-7[1m]) @ 2026-07-10*
*Method: 11 review dimensions × grep-verified anchors + cross-plan handoff check*
*Lesson enforcement: #9/#11/#37 grep-verified all evidence claims; #14/#30/#33/#33b Foundation Scan re-run against HEAD `d3a7948`; C2 explicit uncertainty note*
