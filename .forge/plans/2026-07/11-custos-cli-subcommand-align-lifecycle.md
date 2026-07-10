# 11 - custos CLI subcommand alignment with lifecycle.md (`enroll` / `vault` / `start`)

> **Status**: 🔲 Not started
> **Created**: 2026-07-10
> **Project**: custos
> **Wave**: v1-team-full-loop (batch)
> **For Claude**: Use `/forge:execute` to implement this plan.

## 上下文 (Context)

**权威文档引用（含具体章节号）**

- arx `docs/team-self-hosted-lifecycle.md` Phase 0.2 (steps 0.2.1-0.2.3, lines 89-93) — the enroll + start command surface this plan must match verbatim
- arx `docs/team-self-hosted-lifecycle.md` Phase 0.3 (steps 0.3.1-0.3.4, lines 96-102) — the `vault put` / `vault verify` command surface
- arx `CLAUDE.md` § 红线 H2 — "Key/策略逻辑只在 runner 本地，云端产品面永不持有" (line 89 in arx CLAUDE.md, the four red lines paragraph)
- custos `CLAUDE.md` § 5 Non-Custodial 4 红线 — items 1 (KEK 永不出进程) + 2 (G6 host gate 不绕过) + 4 (Money math Decimal, wire str)
- custos `.forge/README.md` §"编号顺序说明" + §"执行顺序建议" — Plan 09 already earmarked for hook infra formalization (line 65), Plan 10+ reserved for future engine backends (line 67); Plan 11 is the next free integer

**依赖的前置计划**

- custos Plan 05 structural refactor (`4f0192a`+`e82825d` ✅ 2026-07-10) — established `cli/main.py` package layout + `_parse_args()` + `_run()` + `--engine` dispatch that this plan will restructure into subcommands
- custos Plan 04 red-line-03 runner fallback (`4437991` ✅ 2026-07-10) — established the reconciler + WAL + snapshot publisher runtime wire that `arx-runner start` must preserve
- arx Plan 78 backend enrollment endpoint (drafted this Wave, in flight) — provides the HTTP POST `/api/v1/enrollments` endpoint that `arx-runner enroll --backend http://...` calls; enroll subcommand tests mock this contract by shape (payload + response fields), not by live integration

**下游耦合与执行顺序 (cross-plan hard gate)**

- **Plan 11 全部 T1..T9 squash 落 `main` 后, Plan 12 execute-team 才能启动** (cross-plan reviewer Suggested Ordering). Plan 12 T1 pyproject test asserts `data["project"]["scripts"]["arx-runner"] == "custos.cli.subcommands:main"` + `data["project"]["version"] == "0.2.0"` + `"custos" not in data["project"]["scripts"]`; Plan 12 T9 hard-dep gate greps `SopsAgeVault` = 0 hits in `credential_vault.py`. Both require Plan 11 T8 landed. **Do not parallel-execute** — worktree isolation cannot save merge conflicts on shared `pyproject.toml` / `README.md` / `credential_vault.py` (lesson #16).
- **Wire field name single source of truth (lesson #35)**: the enrollment payload field name is **`token_hash`** (verified: `src/custos/core/enrollment.py:59`). Plan 12 gateway-contract v1 JSON Schema aligns to this name; Plan 11 is the canonical owner. Do not rename to `token_sha256` etc. across either plan.

**契约证据 (Step 1.5 anchors — all grep-verified 2026-07-10)**

CLI current state:
- `src/custos/cli/main.py:36-103` — `_parse_args()` returns flat `argparse.Namespace` with 13 top-level flags, zero `add_subparsers()`. `grep -c 'add_subparsers' src/custos/cli/main.py` = 0.
- `src/custos/cli/main.py:37` — `parser = argparse.ArgumentParser(prog="custos")` (post-Plan 05 rename; `arx-runner` binary name from lifecycle.md is currently orphaned).
- `src/custos/cli/main.py:132-146` — `_build_vault()` requires both `--sops-file` and `--age-key-file` or neither ("半配置拒绝" fail-fast, line 140).
- `pyproject.toml:1-89` — no `[project.scripts]` section. `grep -c '\[project\.scripts\]' pyproject.toml` = 0. Package installs but exposes no console script; `README.md:76-79` currently invokes as `python -m custos ...`.

Vault contract:
- `src/custos/core/credential_vault.py:121-206` — `SopsAgeVault` implements only `decrypt()`. `grep -nE 'def (encrypt|put|store|write)' src/custos/core/credential_vault.py` = 0 hits. The sops file is prepared out-of-band; there is no write path today.
- `src/custos/core/credential_vault.py:147-206` — `decrypt()` calls `subprocess.run(["sops", "--decrypt", str(self._sops_file)], env={"SOPS_AGE_KEY_FILE": ...}, check=True, timeout=30)`; parses whole JSON, looks up `credential_id` key inside (line 193).
- `src/custos/core/credential_vault.py:82-98` — `_verify_permission_scope()` rejects any credential whose `permission_scope != "trade_no_withdraw"`. Any new write path must preserve this invariant on read-back.

Enrollment contract:
- `src/custos/core/enrollment.py:42-92` — `EnrollmentClient.enroll(token, ...)` publishes SHA-256 hash of the token via `nats_client.publish_enrollment()` (line 65). NATS-only, no HTTP client.
- `src/custos/core/enrollment.py:48-55` — the docstring names `/api/v1/runners/enroll` as the eventual cloud-side HTTP reconciliation endpoint, but the runner side has never had an HTTP flag; this plan lands that path.
- `src/custos/core/enrollment.py:104-125` — `_persist()` writes `~/.custos/enrollment.json` (0600 mode chmod on best-effort). Namespace is `~/.custos/`, not `~/.arx/`.

Reconciler + runtime wire (to be reused unchanged from `arx-runner start`):
- `src/custos/cli/main.py:181-209` — `_build_reconciler()` composes `RunnerNotionalCap` + `FallbackBreaker` + `ZombieWatchdog` + `DeploymentReconciler`. Preserved verbatim in Task 6 `start` subcommand.
- `src/custos/cli/main.py:212-294` — `_run()` main loop wires enrollment → reconciler → snapshot publisher → heartbeat. Task 6 extracts the "post-enrollment runtime" half into a reusable coroutine.

Cross-repo staleness note (informational, out of scope for this plan): arx `docs/team-self-hosted-lifecycle.md:76` still points at the pre-extraction `runner/src/arx_runner/credential_vault.py` path. This plan aligns the *command surface* with lifecycle.md but does not update lifecycle.md itself; that is a separate follow-up on the arx side. Namespace choice `~/.arx/` follows lifecycle.md's literal text (team-lead brief) even though the package rename went to `custos`.

**plan-to-plan reference table**

| plan-id | commit-hash | 引用的文件/章节 |
|---------|-------------|-----------------|
| custos-05 | `e82825d` | `src/custos/cli/main.py:36-103` `_parse_args()` structure this plan restructures |
| custos-04 | `4437991` | `src/custos/cli/main.py:181-209` reconciler + `_run()` runtime wire preserved by `arx-runner start` |
| arx-Plan 60 | (subtree split) | `~/.custos/` namespace convention — kept as-is for `enrollment.json` back-compat, `~/.arx/runner.toml` is the new long-term-credential store |
| arx-78 | in-flight (Wave v1-team-full-loop) | `POST /api/v1/enrollments` request/response shape mocked in `enroll` subcommand tests |

All commit hashes verified against `git log --oneline` (in-repo) 2026-07-10; arx-78 is co-drafted this Wave and is not yet a landed commit — tests target the shape declared in team-lead brief, not a live endpoint.

---

## 目标 (Goal)

Restructure the custos CLI from a single flat command (`python -m custos --tenant-id X --runner-id Y ...`) into five lifecycle-aligned subcommands — `arx-runner enroll` / `arx-runner start` / `arx-runner vault put` / `arx-runner vault verify` / `arx-runner vault list` — that match arx `docs/team-self-hosted-lifecycle.md` Phase 0.2 + 0.3 verbatim; add a single `[project.scripts]` entry for `arx-runner` (**hard clean break — no legacy `custos` entry point, no `python -m custos` fallback, no `DeprecationWarning` bridge**); delete the legacy `SopsAgeVault(sops_file=..., age_key_file=...)` multi-credential-in-one-JSON model outright; persist long-term credentials to `~/.arx/runner.toml` (0600) and per-key exchange credentials to `~/.arx/vault/<key-id>.enc`; consolidate all runner state (enrollment snapshot + WAL + vault) under `~/.arx/` (retire `~/.custos/` namespace); enforce boundary-string validation on `tenant_id` / `runner_id` / `key-id` at parse time.

**CEO clean-break directive (2026-07-10)**: existing team members with `~/.custos/enrollment.json` + old sops-file credentials must manually re-enroll via `arx-runner enroll` + re-add each key via `arx-runner vault put` after upgrading. No migration command is provided (docket 1 per CEO). The `python -m custos ...` old command exits non-zero with a pointer to `arx-runner start`. This is the accepted operator cost of avoiding lesson #35 boundary-constant fanout and long-term dual-namespace drift.

---

## 架构 (Architecture)

Introduce `src/custos/cli/subcommands/` as the new dispatcher entry point using stdlib `argparse.add_subparsers` (zero new dependency; matches custos CLAUDE.md §5 audit-simplicity discipline). Each subcommand is a self-contained handler module (`enroll.py` / `vault.py` / `start.py`) with its own argparse sub-parser and coroutine body. `runner_toml.py` (new core module) owns the `~/.arx/runner.toml` read/write contract with atomic-rename + 0600 enforcement; `validators.py` (new cli module) owns tenant-id / runner-id / key-id boundary regex (lesson #26). **The old `cli/main.py` flat-parser entry is deleted along with the `custos` console-script mapping** — invoking `python -m custos ...` after upgrade exits non-zero with a one-line pointer to `arx-runner start` and the arx lifecycle.md link. `vault put` shells out to `sops --encrypt --age <recipient>` producing one `.enc` file per key-id; the legacy `SopsAgeVault(sops_file=..., age_key_file=...)` class at `credential_vault.py:121-206` is **deleted outright** — the per-key `.enc` layout is the sole runtime read path. `enroll` is the first HTTP path in custos: a small `urllib.request`-based client (still zero-dep) POSTs to `<backend>/api/v1/enrollments` with the token hash + runner metadata and persists the returned long-term credential to `runner.toml`.

---

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| Subcommand library | stdlib `argparse.add_subparsers` (no new dependency) | Non-Custodial audit-simplicity red line (custos CLAUDE.md §5): every dep is auditor-facing surface. Adding `typer`/`click` would trade zero-dep for ergonomic sugar. |
| Enroll transport | HTTP POST `<backend>/api/v1/enrollments` (new); keep NATS `EnrollmentClient.enroll()` reachable for legacy invocations | lifecycle.md §0.2.2 verbatim says `--backend http://team-server:8000`; arx-78 lands the endpoint. `stdlib urllib.request` keeps zero-dep. Existing NATS path stays for backward compat during Plan 05→11 transition. |
| Long-term credential storage | `~/.arx/runner.toml` mode 0600, atomic write (tmpfile → fsync → rename) | lifecycle.md §0.2.2 mandates this path verbatim; 0600 protects the long-term credential returned by the backend; atomic rename prevents partial writes crashing subsequent `start`. |
| Vault storage model | Per-key `~/.arx/vault/<key-id>.enc` (sops+age single-file per key). **Legacy `SopsAgeVault(sops_file=..., age_key_file=...)` multi-credential-in-one-JSON class is DELETED (`credential_vault.py:121-206` + `tests/test_credential_vault_sops.py`).** No fallback read path. | lifecycle.md §0.3.1 explicit per-key model. Per-file scoping = each key has its own recipient set + rotation cadence + audit trail. **CEO clean-break directive (2026-07-10) — operators with old sops files run `sops --decrypt` manually + rerun `arx-runner vault put` per key. No auto-migration command is provided (docket 1).** Reason: eliminate lesson #35 dual-source boundary constant + write-path race in the JSON multi-credential model. |
| `custos` legacy entry point | **DELETED**. `python -m custos` and `[project.scripts].custos` are removed. Old command exits with `sys.exit(2)` + one-line pointer to `arx-runner start` (see arx `docs/team-self-hosted-lifecycle.md` Phase 0.2). No `DeprecationWarning` bridge, no flag-forwarding delegation. | CEO clean-break directive (2026-07-10) supersedes the earlier lesson #35 concern here — the earlier draft's soft-deprecation path traded technical debt for team-member convenience. CEO judgment: one operator-facing break at Plan 11 landing is preferable to long-term dual-CLI drift. Team members re-run `arx-runner enroll` + rebuild vault via `arx-runner vault put` after upgrade. |
| `tenant_id` / `runner_id` / key-id validation | CLI-layer regex `^[a-zA-Z0-9_-]{1,64}$` fail-fast in every subcommand | lesson #26: `~/.arx/vault/<key-id>.enc` is a filesystem boundary — path traversal / null byte / control char in raw string enables key exfiltration. Reject at parse time before the path is joined. |
| sops encrypt invocation | `subprocess.run(["sops", "--encrypt", "--age", "<recipient>", "/dev/stdin"], input=payload, ...)` shell-out | Mirrors the existing decrypt shell-out pattern at `credential_vault.py:157-163`; sops CLI is a Plan 05-landed external dependency (see README + `docs/design/credential_vault.md`); reading age recipient from an env var (or `--age-recipient` flag) keeps the KEK selection auditable. |
| Runner state namespace | **`~/.arx/` is the sole namespace.** `~/.custos/` is retired entirely. Contents: `~/.arx/runner.toml` (long-term HTTP-issued credential, this plan) + `~/.arx/vault/<key-id>.enc` (per-key vault, this plan) + `~/.arx/enrollment.json` (one-shot NATS-pairing snapshot, migrated from `~/.custos/enrollment.json`) + `~/.arx/state/telemetry-wal.db` (Plan 04 WAL, migrated from `~/.custos/state/`). | CEO clean-break directive (2026-07-10) — retire `~/.custos/` completely to avoid long-term dual-namespace drift + future lesson #35 fanout risk. Operators upgrading run `mv ~/.custos/enrollment.json ~/.arx/enrollment.json && mv ~/.custos/state ~/.arx/state && rmdir ~/.custos/vault ~/.custos 2>/dev/null` (documented in `README.md` Upgrade section). Plan 04 WAL path default (`args.wal_path` at `cli/main.py:92`) is retargeted from `Path.home() / ".custos" / "state" / "telemetry-wal.db"` to `Path.home() / ".arx" / "state" / "telemetry-wal.db"` — a Plan 04 config surface change coordinated in this plan. |

---

## 承载决策 (Capability Hosting Decision)

Not applicable. Every capability in this plan is production code (new subcommand handlers + validation + HTTP client + toml persistence). No skill / hook / rule / CLAUDE.md-level ambient behavior is introduced — the plan is pure runtime code.

---

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|---------|------|------|
| `src/custos/cli/subcommands/__init__.py` | Create | subcommand dispatcher `main(argv)` — argparse `add_subparsers(dest="cmd")`, routes to enroll / vault / start handlers |
| `src/custos/cli/subcommands/enroll.py` | Create | `arx-runner enroll --token T --backend URL` — validate ids, POST `/api/v1/enrollments`, persist runner.toml (0600) |
| `src/custos/cli/subcommands/vault.py` | Create | `arx-runner vault put/verify/list` — sops+age encrypt per key-id → `~/.arx/vault/<key-id>.enc` (0600); verify runs decrypt path; list scans dir |
| `src/custos/cli/subcommands/start.py` | Create | `arx-runner start` — read `runner.toml`, build reconciler namespace, delegate to `run_daemon` in `cli/_daemon.py`. Also defines module-level defaults: `DEFAULT_WAL_PATH = Path.home() / ".arx" / "state" / "telemetry-wal.db"` and `DEFAULT_ENROLLMENT_PATH = Path.home() / ".arx" / "enrollment.json"` (retargets Plan 04 WAL default from `~/.custos/state/` in the process; see H3 in cross-plan review). |
| `src/custos/cli/_daemon.py` | Create | `async def run_daemon(args: argparse.Namespace)` — post-`_parse_args` coroutine extracted verbatim from legacy `cli/main.py:212-294` `_run()` body. Also hosts the relocated helpers `_build_vault` (rebuilt to construct `PerKeyVault`) / `_build_host` / `_build_reconciler` / `_heartbeat_loop`. Imported by `subcommands/start.py` as `from custos.cli._daemon import run_daemon`; survives the T8 rewrite of `cli/main.py`. |
| `src/custos/cli/validators.py` | Create | `validate_id(name, value)` — regex `^[a-zA-Z0-9_-]{1,64}$` for tenant_id / runner_id / key-id (raises `argparse.ArgumentTypeError`). Also `validate_backend_url(value)` — `urllib.parse.urlparse`-based check: scheme ∈ {http, https}, non-empty netloc, no fragment, no userinfo (H1). |
| `src/custos/core/runner_toml.py` | Create | `RunnerToml.read(path)` / `RunnerToml.write(path, record)` — TOML I/O + atomic tmpfile+fsync+rename + 0600 mode invariant; `~/.arx/` dir auto-create at 0700 |
| `src/custos/core/per_key_vault.py` | Create | `class PerKeyVault(_BaseVault)` — reads `<vault-dir>/<credential_id>.enc` via `sops --decrypt` at reconciler runtime (production replacement for deleted `SopsAgeVault`). Preserves `_verify_permission_scope` + `_emit_decrypt_audit` invariants inherited from `_BaseVault` (`credential_vault.py:57-98`). Consumed by `_daemon._build_vault` (T7) so live-mode reconciler has a runtime read path from `arx-runner vault put`. |
| `src/custos/cli/main.py` | **Delete majority** | Delete `_parse_args()` flat 13 flags + `_build_vault()` + `_build_host()` + `_build_reconciler()` + `_heartbeat_loop()` + `_run()` (relocated to `cli/_daemon.py`). Only remaining content: 5-line stub `main()` that prints `"custos: this entry point has been removed; use \`arx-runner start\` (see arx docs/team-self-hosted-lifecycle.md Phase 0.2)"` to stderr and `sys.exit(2)`. Path stays for `python -m custos` invocation to give a clear error instead of `ModuleNotFoundError`. |
| `src/custos/core/credential_vault.py` | **Delete lines 121-206** | Delete `SopsAgeVault` class only. **Preserve** `_BaseVault._verify_permission_scope` (lines 83-98) + `_BaseVault._emit_decrypt_audit` (lines 64-81) + `AuditEvent` enum (lines 39-46) — reused by T6 `vault verify` and by new `PerKeyVault` via base-class inheritance. Also extend `AuditEvent` enum with `CREDENTIAL_ENCRYPTED = "CredentialEncrypted"` for the T5 encrypt audit event (H4). |
| `tests/test_credential_vault_sops.py` | **Delete file** | Legacy `SopsAgeVault` tests — no longer applicable. |
| `pyproject.toml` | Modify | Add `[project.scripts]` block with **single entry**: `arx-runner = "custos.cli.subcommands:main"`. **No `custos = ...` entry.** Version bump `0.1.0` → `0.2.0` (semver `feat` breaking change; documented in `README.md` upgrade section). |
| `README.md` | Modify | Rewrite Quick Start (`README.md:76-79`) to `arx-runner enroll` / `arx-runner vault put` / `arx-runner start` flow. Add explicit **Upgrade from 0.1.x** section: (1) `pip install --upgrade custos-runner` (2) `mv ~/.custos/enrollment.json ~/.arx/enrollment.json` (3) `mv ~/.custos/state ~/.arx/state` (4) manually rerun `arx-runner enroll` (long-term credential) + `arx-runner vault put` per old sops-file credential. No auto-migration script provided. |
| `tests/test_cli_enroll.py` | Create | happy path (mocked backend 200) + failure modes: `token_double_use`, `backend_unreachable`, `backend_500_no_partial_persist`, `arx_dir_missing`, `token_traversal`, `test_enroll_rejects_non_http_backend` (H1: `file://` / `gopher://` / bare `foo`) |
| `tests/test_cli_vault_put_verify.py` | Create | put/verify/list happy path (mocked `subprocess.run(sops)`) + failure modes: `sops_decrypt_fail_no_silent_return`, `keyid_traversal`, `vault_file_0644_rejected`, `test_vault_put_prefers_stdin_and_warns_on_cmdline_secret` (M3) |
| `tests/test_cli_start.py` | Create | read runner.toml → wire reconciler + snapshot publisher (mocked NATS) + missing runner.toml fail-fast + partial runner.toml (missing tenant_id) rejected |
| `tests/test_per_key_vault.py` | Create | `test_per_key_vault_missing_enc_file_clear_error` / `test_per_key_vault_scope_violation` / `test_per_key_vault_sops_fail_no_silent_return` — runtime read path failure modes for the reconciler's new production vault reader |
| `tests/test_runner_toml.py` | Create | atomic write (crash mid-write → old file intact) + 0600 preserved on rename + `~/.arx/` created at 0700 |
| `tests/test_cli_validators.py` | Create | reject `..`, `\0`, control chars 0x00-0x1F, oversized > 64 chars, empty, non-ASCII |
| `tests/test_cli_unknown_subcommand.py` | Create | `arx-runner foo` → non-zero exit + `--help`-style listing |
| `docs/design/enrollment.md` | Modify | **Rewrite** the enroll flow section as HTTP POST `<backend>/api/v1/enrollments` primary path (CLI-facing surface HTTP-only per lifecycle.md §0.2.2); `EnrollmentClient` NATS class retained as low-level building block only. |
| `docs/design/credential_vault.md` | Modify | **Rewrite** vault section to per-key `~/.arx/vault/<key-id>.enc` as the **sole** supported runtime model (`SopsAgeVault` deleted in T8, no fallback read path, no coexistence). |

---

## 失败模式覆盖契约 (Failure Mode Coverage Contract, lesson #17)

| Failure mode | Test function | Wire tier | Purpose |
|--------------|---------------|-----------|---------|
| EnrollmentToken 一次性 double-use | `test_enroll_double_use_rejected` | code-level | Backend returns 409 on second call with same token; runner.toml from first call not overwritten |
| runner.toml world-readable (0644) leakage | `test_runner_toml_rejects_world_readable_mode` | code-level | Read path rejects a file with mode & 077 != 0 (fail-loud, not silent chmod) |
| sops decrypt failure silent return | `test_vault_verify_sops_fail_no_silent_return` | code-level | `subprocess.CalledProcessError` propagates + `verify` returns non-zero exit + no "OK" printed |
| runner.toml race (2 concurrent writers same host) | `test_runner_toml_atomic_write_survives_interrupt` | code-level | Simulated crash between tmpfile.fsync and rename → old file survives, no partial write |
| tenant_id path traversal | `test_validator_rejects_tenant_traversal` | code-level | `../evil` in tenant_id → `argparse.ArgumentTypeError` before any filesystem op |
| runner_id null byte | `test_validator_rejects_runner_null_byte` | code-level | `\x00` in runner_id → rejected pre-path-join |
| key-id path traversal | `test_validator_rejects_keyid_traversal` | code-level | `../` in key-id → rejected before `~/.arx/vault/<key-id>.enc` is joined |
| HTTP backend unreachable | `test_enroll_backend_unreachable` | code-level | Connection error → clear message, non-zero exit, runner.toml not created |
| HTTP backend returns 500 | `test_enroll_backend_500_no_partial_persist` | code-level | 5xx response → runner.toml not written (all-or-nothing) |
| `~/.arx/` dir missing (fresh install) | `test_enroll_creates_arx_dir_at_0700` | code-level | Dir auto-created with mode 0700; not 0755 |
| legacy entry point clean break | `test_python_m_custos_exits_nonzero_with_pointer` | code-level | `python -m custos` → `sys.exit(2)` + stderr contains `arx-runner start` pointer + arx lifecycle.md URL; no `DeprecationWarning`, no partial delegation |
| legacy console-script clean break | `test_no_custos_console_script_registered` | code-level | After `uv sync`, `shutil.which("custos") is None` (only `arx-runner` registered in `pyproject.toml [project.scripts]`) |
| legacy SopsAgeVault clean break | `test_sops_age_vault_class_removed` | code-level | `from custos.core.credential_vault import SopsAgeVault` raises `ImportError` (class deleted) |
| `~/.custos/` namespace retirement | `test_default_paths_target_arx_namespace` | code-level | All default paths (`runner.toml` / `vault/` / `state/telemetry-wal.db` / `enrollment.json`) resolve under `Path.home() / ".arx" / ...`; no `.custos` substring in any default path constant |
| unknown subcommand | `test_unknown_subcommand_shows_help_nonzero_exit` | code-level | `arx-runner foo` → exit != 0 + subcommand list printed |
| vault put file already exists | `test_vault_put_rejects_existing_keyid` | code-level | Second `put` of same key-id → rejected unless `--force` (prevents silent overwrite) |
| sops binary missing | `test_vault_put_missing_sops_binary_fails_fast` | code-level | `FileNotFoundError` from subprocess → clear "sops CLI not installed" message (mirrors `credential_vault.py:164-166` decrypt behavior) |
| enroll `--backend` non-http scheme (H1) | `test_enroll_rejects_non_http_backend` | code-level | `--backend file:///etc/passwd` / `gopher://x` / bare `foo` → `argparse.ArgumentTypeError` before any `urlopen` call; `runner.toml` not written |
| vault put secret via `--api-secret` cmdline (M3) | `test_vault_put_prefers_stdin_and_warns_on_cmdline_secret` | code-level | `--api-secret-stdin` primary path works; `--api-secret <value>` emits red warning to stderr about `ps aux` exposure but still runs (demo-only) |
| PerKeyVault missing `.enc` at runtime read (C3) | `test_per_key_vault_missing_enc_file_clear_error` | code-level | `PerKeyVault(vault_dir=...).decrypt("binance-paper")` when `binance-paper.enc` absent → clear error naming file + `arx-runner vault put` remediation, non-zero from caller |
| PerKeyVault scope violation at runtime read (C3) | `test_per_key_vault_scope_violation` | code-level | decrypted payload has `permission_scope: "trade_full"` → `_BaseVault._verify_permission_scope` raises before caller sees credential |
| PerKeyVault sops decrypt failure at runtime read (C3) | `test_per_key_vault_sops_fail_no_silent_return` | code-level | `subprocess.CalledProcessError` from sops → propagate up (mirrors T6 verify contract, applied at reconciler read site) |

All 21 failure modes are code-level tests (Python `pytest` + `unittest.mock`). No runtime-wire integration test is scoped in this plan; the runtime wire is already covered by Plan 04's reconciler tests and this plan does not modify reconciler code beyond swapping the `_build_vault` return type from `SopsAgeVault` to `PerKeyVault` in `_daemon.py`.

---

## 实现任务 (Tasks)

### Task 1: `runner_toml.py` foundation module + tests

**Files**:
- Create `src/custos/core/runner_toml.py`
- Create `tests/test_runner_toml.py`

**Step 1**: Write failing tests
- `test_write_creates_file_at_0600`: write a record, assert `os.stat(path).st_mode & 0o777 == 0o600`
- `test_write_creates_arx_dir_at_0700`: fresh `~/.arx/` → dir mode == 0o700
- `test_read_rejects_world_readable_mode`: pre-create file at 0o644 → `read()` raises `PermissionError`
- `test_atomic_write_survives_interrupt`: mock `os.rename` to raise mid-flight → tmpfile removed, old file intact
- `test_read_missing_file_raises_clear_error`: `FileNotFoundError` with actionable message ("run `arx-runner enroll` first")

**Step 2**: `uv run pytest tests/test_runner_toml.py -v` — all 5 fail (module does not exist).

**Step 3**: Minimal implementation
- `RunnerToml` dataclass: `tenant_id: str`, `runner_id: str`, `backend_url: str`, `long_term_credential: str`, `enrolled_at_ns: int`
- `write(path: Path, record: RunnerToml)`:
  1. `path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)` + `os.chmod(path.parent, 0o700)` (idempotent on existing dir)
  2. `tmp = path.parent / f".{path.name}.tmp"`, write TOML, `os.chmod(tmp, 0o600)`, `os.fsync(fd)`, `os.rename(tmp, path)`
- `read(path: Path) -> RunnerToml`: stat mode check first, then TOML parse (stdlib `tomllib`, Python 3.11+)
- TOML shape:
  ```toml
  tenant_id = "..."
  runner_id = "..."
  backend_url = "https://..."
  long_term_credential = "..."
  enrolled_at_ns = 1234567890000000000
  ```

**Step 4**: `uv run pytest tests/test_runner_toml.py -v` — all 5 pass.

**Step 5**: Commit `feat(custos): add ~/.arx/runner.toml persistence module (plan 11 t1)`.

---

### Task 2: `validators.py` boundary regex + tests

**Files**:
- Create `src/custos/cli/validators.py`
- Create `tests/test_cli_validators.py`

**Step 1**: Write failing tests
- `test_accepts_valid_id`: `"acme"`, `"runner-7"`, `"tenant_a_1"`, 64-char ASCII alnum
- `test_rejects_path_traversal`: `"../evil"`, `"./x"`
- `test_rejects_null_byte`: `"tenant\x00"`, `"\x00tenant"`
- `test_rejects_control_chars`: each of `\x00`-`\x1F` + `\x7F`
- `test_rejects_oversize`: 65-char id
- `test_rejects_empty`: `""`
- `test_rejects_non_ascii`: `"tenant-中"`, `"tenant​"` (zero-width space)
- `test_validate_backend_url_accepts_http_https`: `"http://team-server:8000"`, `"https://team-server.example/api"`
- `test_validate_backend_url_rejects_file_scheme`: `"file:///etc/passwd"` → `argparse.ArgumentTypeError`
- `test_validate_backend_url_rejects_gopher_scheme`: `"gopher://evil.example"` → rejected
- `test_validate_backend_url_rejects_bare_hostname`: `"team-server"` (no scheme) → rejected
- `test_validate_backend_url_rejects_empty_netloc`: `"http://"` → rejected
- `test_validate_backend_url_rejects_userinfo`: `"http://user:pass@team-server"` → rejected (userinfo would leak in HTTP proxy logs)
- `test_validate_backend_url_rejects_fragment`: `"http://team-server#frag"` → rejected

**Step 2**: `uv run pytest tests/test_cli_validators.py -v` — all fail.

**Step 3**: Minimal implementation
```python
_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def validate_id(name: str, value: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{name!r} must match ^[a-zA-Z0-9_-]{{1,64}}$ (got {value!r})"
        )
    return value


def validate_backend_url(value: str) -> str:
    """H1 defence: reject non-http(s) schemes at parse-time before `urlopen` sees them."""
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--backend {value!r} is not a valid URL: {exc}") from exc
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise argparse.ArgumentTypeError(
            f"--backend scheme must be http or https (got {parsed.scheme!r} from {value!r})"
        )
    if not parsed.netloc:
        raise argparse.ArgumentTypeError(f"--backend must have a non-empty host (got {value!r})")
    if parsed.username or parsed.password:
        raise argparse.ArgumentTypeError(
            f"--backend must not embed userinfo (got user in {value!r})"
        )
    if parsed.fragment:
        raise argparse.ArgumentTypeError(f"--backend must not carry a fragment (got {value!r})")
    return value
```

**Step 4**: `uv run pytest tests/test_cli_validators.py -v` — all pass.

**Step 5**: Commit `feat(custos): add CLI boundary-string validators (plan 11 t2)`.

---

### Task 3: subcommand dispatcher skeleton + `--help`

**Files**:
- Create `src/custos/cli/subcommands/__init__.py`
- Create `tests/test_cli_unknown_subcommand.py`

**Step 1**: Write failing tests
- `test_no_subcommand_shows_help_nonzero_exit`: `main([])` → SystemExit code != 0, stderr lists `enroll`, `start`, `vault`
- `test_unknown_subcommand_shows_help_nonzero_exit`: `main(["foo"])` → SystemExit code != 0, stderr contains `unknown subcommand`
- `test_enroll_help_lists_flags`: `main(["enroll", "--help"])` → stdout contains `--token`, `--backend`, `--tenant-id`, `--runner-id`
- `test_start_help_lists_flags`: `main(["start", "--help"])` → stdout contains `--runner-toml` flag
- `test_vault_help_lists_subactions`: `main(["vault", "--help"])` → stdout lists `put`, `verify`, `list`

**Step 2**: `uv run pytest tests/test_cli_unknown_subcommand.py -v` — all fail.

**Step 3**: Minimal implementation
- `main(argv)` builds `ArgumentParser(prog="arx-runner")`, `add_subparsers(dest="cmd", required=True)`.
- Register three top-level subparsers: `enroll`, `start`, `vault`.
- `vault` gets its own `add_subparsers(dest="action")` with `put` / `verify` / `list`.
- Each handler module exposes `register(subparsers)` (builds its own sub-parser) + `run(args) -> int` (async where needed).
- Empty stubs for `enroll.run` / `vault.run` / `start.run` returning `1` with `raise NotImplementedError` message — filled by Tasks 4-6.

**Step 4**: `uv run pytest tests/test_cli_unknown_subcommand.py -v` — all pass.

**Step 5**: Commit `feat(custos): add arx-runner subcommand dispatcher skeleton (plan 11 t3)`.

---

### Task 4: `enroll` subcommand — HTTP client + persistence

**Files**:
- Modify `src/custos/cli/subcommands/enroll.py`
- Create `tests/test_cli_enroll.py`

**Step 1**: Write failing tests (all use `unittest.mock.patch("urllib.request.urlopen")`)
- `test_enroll_happy_path_persists_runner_toml`: mocked 200 response `{"long_term_credential": "abc", "enrolled_at_ns": 1234}` → `runner.toml` written at 0o600 with expected fields
- `test_enroll_backend_unreachable`: `urlopen` raises `URLError` → non-zero exit, `runner.toml` not created
- `test_enroll_backend_500_no_partial_persist`: mocked 500 → non-zero exit, `runner.toml` not created
- `test_enroll_double_use_rejected`: mocked 409 → non-zero exit + stderr contains `token already used`
- `test_enroll_creates_arx_dir_at_0700`: fresh `HOME` with no `~/.arx/` → dir created at mode 0o700
- `test_enroll_rejects_token_with_null_byte`: `--token "abc\x00"` → validator error before HTTP call
- `test_enroll_rejects_tenant_traversal`: `--tenant-id "../evil"` → validator error before HTTP call
- `test_enroll_rejects_non_http_backend` (H1): `--backend file:///etc/passwd` / `--backend gopher://x` / `--backend foo` → validator error via `validate_backend_url` before any `urlopen` call
- `test_enroll_payload_shape`: assert mocked call payload = `{"token_hash": <sha256 hex>, "runner_id": <id>, "agent_version": <str>, "capabilities": <list>}` (mirrors `enrollment.py:57-63`).
  **Wire field name note (lesson #35 boundary constant)**: `token_hash` is the wire single source of truth — Plan 12 gateway-contract v1 schema aligns to this name (not `token_sha256`). The name matches `enrollment.py:59` and remains the canonical field across all cross-plan references.
  **Payload contract with arx-78 (M1)**: backend resolves tenant from `token_hash` via server-side lookup (issued-token → tenant mapping). Runner does not send `tenant_id` in the payload. `--tenant-id` CLI flag is captured only for local `runner.toml` persistence + subsequent `arx-runner start` invocation.

**Step 2**: `uv run pytest tests/test_cli_enroll.py -v` — all fail (handler is `NotImplementedError` stub).

**Step 3**: Minimal implementation
- Parse `--token`, `--backend` (`type=validators.validate_backend_url`, H1), `--tenant-id` (`type=lambda v: validators.validate_id("tenant_id", v)`), `--runner-id` (validated), `--runner-toml` (default `~/.arx/runner.toml`), optional `--agent-version`, `--capabilities` (**M2**: `action="append"`, `default=[]` — repeat flag: `--capabilities nautilus --capabilities noop-host`; zero repeats ⇒ empty list).
- `run(args)`:
  1. Validate ids via `validators.validate_id`; `args.backend` is already normalized by argparse `type=`.
  2. Compute `token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()` (reuse `enrollment.hash_token`).
  3. Build payload dict matching arx-78 shape — `{"token_hash": ..., "runner_id": ..., "agent_version": ..., "capabilities": args.capabilities}`. **No `tenant_id` in payload** (backend resolves via token_hash lookup, M1).
  4. `urllib.request.Request(f"{backend}/api/v1/enrollments", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})`, POST via `urlopen(req, timeout=30)`. **M4 defense-in-depth**: install a `urllib.request.HTTPRedirectHandler` subclass that re-runs `validate_backend_url` on the Location header before following any 3xx redirect; reject any redirect whose scheme falls outside `{http, https}`. **M5**: `timeout=30` matches the sops-decrypt `subprocess.run(..., timeout=30)` invariant at `credential_vault.py:162` — hard invariant across all zero-dep external I/O boundaries.
  5. On 200: parse response → `RunnerToml(tenant_id, runner_id, backend_url=backend, long_term_credential=<from response>, enrolled_at_ns=<from response>)` → `runner_toml.write(args.runner_toml, record)`.
  6. On non-2xx / connection error: print clear stderr message, return 1 without any partial write.

**Step 4**: `uv run pytest tests/test_cli_enroll.py -v` — all pass.

**Step 5**: Commit `feat(custos): arx-runner enroll subcommand (HTTP + runner.toml) (plan 11 t4)`.

---

### Task 5: `vault put` subcommand — sops encrypt per-key

**Files**:
- Modify `src/custos/cli/subcommands/vault.py` (add `put` action)
- Create `tests/test_cli_vault_put_verify.py` (put half only in this task)

**Step 1**: Write failing tests
- `test_vault_put_happy_path_writes_enc_file`: mocked `subprocess.run(sops encrypt)` returns encoded bytes → `~/.arx/vault/binance-paper.enc` written at 0o600
- `test_vault_put_rejects_existing_keyid`: pre-existing `.enc` file → non-zero exit, no overwrite (no `--force` semantics in v1)
- `test_vault_put_missing_sops_binary_fails_fast`: mock `subprocess.run` raises `FileNotFoundError` → clear message ("sops CLI not installed on runner host") + non-zero exit
- `test_vault_put_rejects_keyid_traversal`: `--key-id "../evil"` → validator error
- `test_vault_put_writes_permission_scope`: assert encoded plaintext payload contains `"permission_scope": "trade_no_withdraw"` (invariant carried over from `credential_vault.py:87`)
- `test_vault_put_never_logs_secret`: capture structlog output, assert raw `--api-secret` value never appears in any log record (extends `credential_vault.py:70-81` audit-only-reference discipline)

**Step 2**: `uv run pytest tests/test_cli_vault_put_verify.py::test_vault_put_* -v` — all fail.

**Step 3**: Minimal implementation
- Parse `--key-id` (validated), `--api-key`, `--age-recipient` (or env `SOPS_AGE_RECIPIENT`), `--vault-dir` (default `~/.arx/vault`).
- **M3 secret input paths** — three mutually exclusive `--api-secret-*` flags (mutually exclusive group required):
  1. **`--api-secret-stdin`** (primary, no arg): read via `sys.stdin.readline().rstrip("\n")`; recommended for scripts / ops runbooks.
  2. **`--api-secret-env ENV_NAME`** (secondary): read via `os.environ[ENV_NAME]`; recommended for CI / vault-injected envs.
  3. **`--api-secret <value>`** (demo / debug only): print a **red warning** to stderr about `ps aux` / `/proc/<pid>/cmdline` exposure, then proceed. This preserves demo ergonomics while making the risk loud.
- Build plaintext payload dict `{key_id: {api_key, api_secret, permission_scope: "trade_no_withdraw"}}` (matching the multi-cred sops JSON shape at `credential_vault.py:193-202`, but with just one credential per file).
- `subprocess.run(["sops", "--encrypt", "--age", recipient, "--input-type", "json", "--output-type", "json", "/dev/stdin"], input=json.dumps(payload).encode(), capture_output=True, check=True, timeout=30)`. **L1 note**: payload bytes are passed via `subprocess.run(..., input=...)`, NOT via a `sh -c` intermediary — no shell buffer holds plaintext.
- Write result.stdout to tmpfile → `os.chmod(tmp, 0o600)` → `os.rename(tmp, vault_dir / f"{key_id}.enc")`.
- **H4 audit event via stdlib logging** (not structlog): `_log = logging.getLogger("custos.credential_vault")` (module-import from `custos.core.credential_vault`) — emit `_log.info("credential_encrypted", extra={"audit_event": AuditEvent.CREDENTIAL_ENCRYPTED.value, "key_id": key_id, "tenant_id": tenant_id})`. This mirrors the decrypt audit event at `credential_vault.py:64-81` (which is deliberately stdlib per the `credential_vault.py:32-35` comment, to keep `caplog` assertions and downstream stdlib-logger pattern-matching consumers happy). **Enum extension required in T8 file**: add `CREDENTIAL_ENCRYPTED = "CredentialEncrypted"` to `AuditEvent` at `credential_vault.py:39-46` (T8 already preserves the enum, so the `+1` field slots in cleanly).

**Step 4**: `uv run pytest tests/test_cli_vault_put_verify.py::test_vault_put_* -v` — all pass.

**Step 5**: Commit `feat(custos): arx-runner vault put subcommand (per-key sops encrypt) (plan 11 t5)`.

---

### Task 6: `vault verify` + `vault list` subcommands

**Files**:
- Modify `src/custos/cli/subcommands/vault.py` (add `verify` + `list` actions)
- Extend `tests/test_cli_vault_put_verify.py` (verify + list halves)

**Step 1**: Write failing tests
- `test_vault_verify_happy_path`: pre-write a `.enc`, mock decrypt → returns valid JSON with `permission_scope: trade_no_withdraw` → exit 0 + stdout `OK`
- `test_vault_verify_sops_fail_no_silent_return`: mock decrypt raises `CalledProcessError` → non-zero exit, no "OK" printed (fail-loud, matches CLAUDE.md 红线 "对账不静默" analogue)
- `test_vault_verify_rejects_scope_violation`: mock decrypt returns `permission_scope: "trade_full"` → non-zero exit + violation message (reuses `_verify_permission_scope` from `credential_vault.py:82-98`)
- `test_vault_verify_missing_file_clear_error`: no `.enc` file for key-id → clear error "key not found" + non-zero exit
- `test_vault_list_shows_all_key_ids`: pre-write 3 `.enc` files → stdout lists all 3 key-ids, no secret material
- `test_vault_list_empty_vault_prints_hint`: empty `~/.arx/vault/` → stdout hint "no keys; run `arx-runner vault put`"
- `test_vault_list_rejects_world_readable_enc`: pre-write a `.enc` at 0o644 → warning to stderr + still list (fail-loud on mode)

**Step 2**: `uv run pytest tests/test_cli_vault_put_verify.py::test_vault_verify_* tests/test_cli_vault_put_verify.py::test_vault_list_* -v` — all fail.

**Step 3**: Minimal implementation
- `verify(args)`: read `<vault-dir>/<key-id>.enc`, mode check, `subprocess.run(["sops", "--decrypt", ...], env={"SOPS_AGE_KEY_FILE": ...})`, `json.loads`, `_verify_permission_scope` (reuse from `credential_vault.py` — import + call). Success prints `OK`; anything else prints diagnostic + returns 1.
- `list(args)`: `sorted(p.stem for p in vault_dir.glob("*.enc"))`, print one per line. Include `st_mode & 0o077 != 0` warnings to stderr.
- Do NOT log any decrypted plaintext — audit event pattern from `credential_vault.py:64-81` is preserved.

**Step 4**: `uv run pytest tests/test_cli_vault_put_verify.py::test_vault_verify_* tests/test_cli_vault_put_verify.py::test_vault_list_* -v` — all pass.

**Step 5**: Commit `feat(custos): arx-runner vault verify + list subcommands (plan 11 t6)`.

---

### Task 7: `start` subcommand — read runner.toml + extract `run_daemon` into `cli/_daemon.py`

**Files**:
- Create `src/custos/cli/subcommands/start.py`
- Create `src/custos/cli/_daemon.py` (extraction target for `run_daemon` + helpers, per C2 Option A)
- Modify `src/custos/cli/main.py` — remove the extracted body (Task 8 later rewrites `main.py` to a 5-line stub; the extracted `_daemon.py` survives).
- Create `src/custos/core/per_key_vault.py` (per C3, production runtime read path for `~/.arx/vault/<key-id>.enc`)
- Create `tests/test_cli_start.py`
- Create `tests/test_per_key_vault.py`

**Step 1**: Write failing tests
- `test_start_reads_runner_toml_and_wires_reconciler`: pre-write valid runner.toml → `start` invokes `_daemon.run_daemon` with tenant/runner from toml + mocked NATS connect (via `unittest.mock.patch("custos.core.nats_client.ArxNatsClient")`)
- `test_start_missing_runner_toml_fails_fast`: no `~/.arx/runner.toml` → non-zero exit + stderr "run `arx-runner enroll` first"
- `test_start_partial_runner_toml_rejected`: runner.toml missing `tenant_id` field → non-zero exit + clear parse error
- `test_start_preserves_engine_and_wal_flags`: `--engine nautilus --wal-path /tmp/wal.db --vault-dir /tmp/vault` still work + override runner.toml defaults
- `test_start_rejects_world_readable_runner_toml`: runner.toml at 0o644 → non-zero exit via `runner_toml.read()` mode check (Task 1 invariant)
- `test_start_default_paths_target_arx_namespace` (C1/H3): with no CLI overrides, `start` builds a namespace whose `wal_path` / `enrollment_path` / `vault_dir` all begin with `Path.home() / ".arx"`; no `.custos` substring anywhere.
- `test_per_key_vault_missing_enc_file_clear_error` / `test_per_key_vault_scope_violation` / `test_per_key_vault_sops_fail_no_silent_return` (C3): runtime read failures for `PerKeyVault` — mirrors T6 `verify` contract at the reconciler read site.

**Step 2**: `uv run pytest tests/test_cli_start.py tests/test_per_key_vault.py -v` — all fail.

**Step 3**: Minimal implementation
- **Extract to `src/custos/cli/_daemon.py`** (not `cli/main.py`, per C2 Option A): create a new module hosting `async def run_daemon(args: argparse.Namespace)` — the verbatim post-`_parse_args` half of legacy `cli/main.py:212-294` `_run()`. Move alongside it the relocated helpers `_build_vault` / `_build_host` / `_build_reconciler` / `_heartbeat_loop` (previously at `cli/main.py:132-209`). Rebuild `_build_vault` to construct **`PerKeyVault(vault_dir=args.vault_dir, tenant_id=args.tenant_id, initiator=args.runner_id)`** — the C3 production replacement for the deleted `SopsAgeVault`. Legacy `cli/main.py:_run` (still present at T7 completion) becomes a one-liner: `asyncio.run(_daemon.run_daemon(_parse_args(argv)))`; T8 then rewrites `cli/main.py` to the 5-line clean-break stub and only `_daemon.py` survives.
- **Create `src/custos/core/per_key_vault.py`**: `class PerKeyVault(_BaseVault)` inheriting `_verify_permission_scope` + `_emit_decrypt_audit` from `_BaseVault` (`credential_vault.py:57-98`); constructor takes `vault_dir: Path`, `tenant_id: str`, `initiator: str`; `decrypt(credential_id)` reads `vault_dir / f"{credential_id}.enc"`, `subprocess.run(["sops", "--decrypt", str(path)], env={"SOPS_AGE_KEY_FILE": ...}, check=True, timeout=30)`, `json.loads`, `_verify_permission_scope`, `_emit_decrypt_audit`, returns credential dict. Missing file → `FileNotFoundError` with actionable message ("run `arx-runner vault put --key-id <id>` first"). sops failure → `subprocess.CalledProcessError` propagates (no silent-return).
- **`subcommands/start.py:run(args)`** (module-level defaults `DEFAULT_WAL_PATH = Path.home() / ".arx" / "state" / "telemetry-wal.db"` and `DEFAULT_ENROLLMENT_PATH = Path.home() / ".arx" / "enrollment.json"` and `DEFAULT_VAULT_DIR = Path.home() / ".arx" / "vault"` at the top of the module — these are the retargeted Plan 04 WAL default per H3 in the cross-plan review):
  1. `record = runner_toml.read(args.runner_toml_path)` — fail-fast if missing / bad mode / partial.
  2. Build a compatible `argparse.Namespace` with tenant_id / runner_id from record + CLI overrides for nats_url / wal_path (default `DEFAULT_WAL_PATH`) / snapshot_interval_secs / engine / use_nt_host / reconcile_strategy_id / heartbeat_interval / enrollment_token=None / enrollment_path=`DEFAULT_ENROLLMENT_PATH` / **`vault_dir=DEFAULT_VAULT_DIR`** (drives `PerKeyVault`). **Stale `sops_file` / `age_key_file` fields DELETED** — the multi-cred sops-file model no longer exists post-T8 (H3 residue removal).
  3. `from custos.cli._daemon import run_daemon; asyncio.run(run_daemon(ns))`.

**Step 4**: `uv run pytest tests/test_cli_start.py tests/test_per_key_vault.py -v` — all pass. Also `uv run pytest tests/ -k "test_cli_main or test_reconciler_" -v` — Plan 04/05 tests remain green (regression sanity). Add cross-cutting `test_vault_put_reuses_arx_dir_0700` (L3) to `tests/test_cli_vault_put_verify.py`: assert that after `vault put`, `~/.arx/` mode is exactly 0o700 (both `start.py` and `vault put` share the `~/.arx/` mkdir invariant).

**Step 5**: Commit `feat(custos): arx-runner start subcommand + refactor _run (plan 11 t7)`.

---

### Task 8: `[project.scripts]` single entry + legacy CLI clean break + SopsAgeVault deletion

**Files**:
- Modify `pyproject.toml` (single `[project.scripts]` entry + version bump 0.1.0 → 0.2.0)
- Rewrite `src/custos/cli/main.py` (delete flat parser + `_run` + vault/host builders; keep only 5-line stub)
- Delete `src/custos/core/credential_vault.py:121-206` (`SopsAgeVault` class)
- Delete `tests/test_credential_vault_sops.py`
- Create `tests/test_legacy_cli_removed.py`
- Create `tests/test_sops_age_vault_removed.py`

**Step 1**: Write failing tests
- `test_python_m_custos_exits_nonzero_with_pointer`: subprocess `python -m custos --tenant-id t --runner-id r` → `returncode == 2` + stderr contains `arx-runner start` + arx `team-self-hosted-lifecycle.md` URL
- `test_no_custos_console_script_registered`: after `uv sync`, `shutil.which("custos") is None`; `shutil.which("arx-runner") is not None`
- `test_sops_age_vault_class_removed`: `pytest.raises(ImportError, match="SopsAgeVault"): from custos.core.credential_vault import SopsAgeVault`
- `test_default_paths_target_arx_namespace`: import `custos.cli.subcommands` and inspect default `--wal-path` / `--enrollment-path` — all contain `.arx`, none contain `.custos`

**Step 2**: `uv run pytest tests/test_legacy_cli_removed.py tests/test_sops_age_vault_removed.py -v` — all fail (legacy still present).

**Step 3**: Minimal implementation
- `pyproject.toml` `[project.scripts]`:
  ```toml
  [project.scripts]
  arx-runner = "custos.cli.subcommands:main"
  ```
  Version bump:
  ```toml
  version = "0.2.0"
  ```
- Rewrite `src/custos/cli/main.py` in full — replace all current content with:
  ```python
  """Legacy entry-point stub — the flat CLI has been removed in 0.2.0.

  Use `arx-runner start` (see arx docs/team-self-hosted-lifecycle.md Phase 0.2).
  """
  from __future__ import annotations

  import sys


  def main(argv: list[str] | None = None) -> int:
      print(
          "custos: the `python -m custos` / `custos` entry point has been removed in 0.2.0. "
          "Use `arx-runner start` (see arx docs/team-self-hosted-lifecycle.md Phase 0.2).",
          file=sys.stderr,
      )
      return 2


  if __name__ == "__main__":
      sys.exit(main())
  ```
- **Delete `SopsAgeVault` from `src/custos/core/credential_vault.py`, exactly lines 121-206** (`class SopsAgeVault(_BaseVault):` block through end of module). **Preserve** `AuditEvent` enum (lines 39-46) — and extend it with `CREDENTIAL_ENCRYPTED = "CredentialEncrypted"` (H4 audit event for T5) — plus `CredentialVaultProtocol` (49-55) + `_BaseVault` (57-98, including `_emit_decrypt_audit` at 64-81 and `_verify_permission_scope` at 83-98) + `CredentialVault` mock class (101-118). Both T6 `vault verify` and the new C3 `PerKeyVault` inherit from `_BaseVault`, so the base class + audit event + scope validator must remain intact. Verify surviving `tests/test_credential_vault.py` still green (mock class unaffected).
- Delete `tests/test_credential_vault_sops.py`.
- `uv sync --extra dev` to re-register console scripts.

**Step 4**: `uv run pytest tests/test_legacy_cli_removed.py tests/test_sops_age_vault_removed.py -v` — all pass. Verify `uv run pytest tests/test_credential_vault.py -v` still green (mock class unaffected).

**Step 5**: Commit `feat(custos)!: register arx-runner console script + remove legacy custos entry + delete SopsAgeVault (plan 11 t8)`. (Note the `!` — breaking change per Conventional Commits.)

---

### Task 9: docs update + close-out (clean-break rewrite, not additive)

**Files**:
- Rewrite `docs/design/credential_vault.md` — **replace** the entire `SopsAgeVault` section (JSON multi-credential model) with per-key `.enc` layout as the only supported production vault. Add explicit "Removed in 0.2.0" changelog note referencing the CEO clean-break directive. Do NOT preserve the old section as historical reference.
- Rewrite `docs/design/enrollment.md` — replace NATS-only enroll flow with HTTP POST `<backend>/api/v1/enrollments` as the primary path. Note the `EnrollmentClient` NATS class (`src/custos/core/enrollment.py`) is retained as a lower-level building block called by `subcommands/enroll.py`; the CLI-facing surface is HTTP-only.
- Modify `docs/design/03-implementation.md` — replace all `--sops-file` / `--age-key-file` references with `arx-runner vault put` command flow; replace `~/.custos/` path references with `~/.arx/` throughout.
- Modify `docs/ops/05-deployment.md` — same substitution + add Upgrade from 0.1.x section detailing the manual re-enroll + re-vault-put steps.
- Modify `README.md` — Quick Start uses `arx-runner enroll` / `arx-runner vault put` / `arx-runner start`; add explicit **Breaking Change (0.2.0)** section: (1) `python -m custos` removed → use `arx-runner start` (2) sops multi-credential JSON file removed → run `sops --decrypt <old-file>` + `arx-runner vault put` per key (3) `~/.custos/` retired → `mv ~/.custos/{enrollment.json,state} ~/.arx/` (4) `--sops-file` / `--age-key-file` flags removed.
- Modify `the-alephain-guild/codex/decisions/ADR-014-ecosystem-open-source-boundary.md` — **workspace-only edit** (Cross M2): append a short "Custos v0.2.0 clean-break release (2026-Q3)" note under Consequences (or a new "Evolution" subsection at the end) recording: (a) `SopsAgeVault` JSON multi-credential layout removed; (b) legacy `python -m custos` CLI entry + `[project.scripts].custos` removed; (c) `~/.custos/` namespace retired to `~/.arx/` (single-namespace policy); (d) reason chain: alignment with arx `docs/team-self-hosted-lifecycle.md` §0.2 + §0.3 verbatim command surface + lesson #35 dual-source-elimination + CEO clean-break directive (2026-07-10). Cross-ref: `custos/.forge/plans/2026-07/11-*.md` + `custos/.forge/plans/2026-07/12-*.md` close-out reports. **Custos independent-repo boundary**: this file lives in `the-alephain-guild/codex/`, OUTSIDE the custos repo. Independent-repo executors (fresh `git clone custos`) do NOT see this path and MUST skip this step; record the skip in the plan close-out follow-up list. Workspace executors commit the ADR edit in a **separate commit outside the custos-repo**, `git add <specific-file>` per `mandatory-rules.md` §6. **No `codex/projects/custos/` subdir is created in this plan** (CEO decision 2026-07-10) — the ecosystem-catalog + ADR-014 entries continue to serve as custos's workspace-level anchor; a dedicated custos codex project subdir is a future-plan candidate if/when custos codex-level architecture spec is warranted (currently the `custos/docs/design/*.md` in-repo design specs are the source of truth for single-repo audit).
- Modify `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md` — status to `✅ Completed`.
- Modify `.forge/README.md` — add Plan 11 row to plan index table with prominent "breaking change" annotation.
- **Version bump decision**: this plan is a breaking change (removed CLI + removed vault class + retired namespace). Semver `feat!` (breaking) → bump minor version in `pyproject.toml` (`0.1.0` → `0.2.0`) since we are pre-1.0 (SemVer §4 allows breaking changes in 0.x minor bumps). **Note (L7)**: T8 does the actual bump; T9 only verifies via `grep '^version = "0.2.0"' pyproject.toml` = 1 hit. Do NOT bump again in T9.

**Actions**:
1. Flip `Status: 🔲 Not started` → `Status: ✅ Completed` + add `Completed: YYYY-MM-DD`.
2. `.forge/README.md` — append Plan 11 row with slug + status + depends + blocks + notes (prominent "breaking change" annotation).
3. `docs/design/enrollment.md` — **rewrite** the enroll section: HTTP POST `<backend>/api/v1/enrollments` is the CLI-facing primary path; document request payload shape (`token_hash` + `runner_id` + `agent_version` + `capabilities`, **no `tenant_id`** per M1) + response shape (`long_term_credential` + `enrolled_at_ns`) + `~/.arx/runner.toml` persistence contract. Note `EnrollmentClient` NATS class (`src/custos/core/enrollment.py`) is retained only as a low-level building block that `subcommands/enroll.py` MAY call in future for non-CLI callers; the CLI surface is HTTP-only (no coexistence at the user-facing layer).
4. `docs/design/credential_vault.md` — **rewrite** the vault section: per-key `~/.arx/vault/<key-id>.enc` is the **sole** production runtime model. Document the write path (`arx-runner vault put`), the verify path (`arx-runner vault verify` + `list`), and the reconciler runtime read path via `PerKeyVault` (C3). Add explicit "Removed in 0.2.0" changelog note referencing the CEO clean-break directive. Do NOT preserve the old `SopsAgeVault` section as historical reference (`SopsAgeVault` is deleted in T8 — no fallback path exists).
5. `README.md:76-96` (Quick Start) — replace `python -m custos ...` example with the three-command lifecycle: `arx-runner enroll` → `arx-runner vault put` → `arx-runner start`. **L4 note**: the `mv ~/.custos/{enrollment.json,state} ~/.arx/` bash brace-expansion example must be paired with a POSIX-safe fallback (`mv ~/.custos/enrollment.json ~/.arx/enrollment.json && mv ~/.custos/state ~/.arx/state`) with a "assumes bash / zsh; on POSIX `sh` use the two-statement form" note.
6. `pyproject.toml` — verify only, no re-bump. `grep '^version = "0.2.0"' pyproject.toml` must hit 1 (T8 already bumped).
7. Add "完成报告 (Close-out Report)" section at the end of this plan file, summarizing: (a) actual file inventory delta vs planned, (b) any failure modes uncovered during implementation added beyond the 21 contracted (14 original + 7 review-driven), (c) any deviations logged.
8. **红线 gate 满足度 table** (M8, lesson #40): append a table with one row per Non-Custodial red line (0.1 / 0.2 / 0.3 / 0.4). Columns:
   | red_line | code_coverage (test_* names) | runtime_wire (composition root file:line) | defer_status | follow_up_plan_ref |
   Expected content:
   - 0.1 (Key/KEK 永不出进程): `test_vault_put_never_logs_secret` + `test_per_key_vault_scope_violation` + `test_enroll_payload_shape` (asserts no raw token in payload, only `token_hash`) | `_daemon._build_vault` returns `PerKeyVault` (post-C3) | in-scope, fully wired | none.
   - 0.2 (G6 host gate 不绕过): unchanged in this plan — `start` subcommand delegates to `_daemon.run_daemon` which preserves the reconciler + `NtTradingNodeHost` composition from Plan 04/05 unchanged | `_daemon._build_host` (relocated verbatim) | in-scope, preserved | Plan 03 host live gate remains authoritative.
   - 0.3 (Reconcile 失联 ≠ 停止): unchanged — `_daemon._build_reconciler` composes `RunnerNotionalCap` + `FallbackBreaker` + `ZombieWatchdog` verbatim from Plan 04 | Plan 04 wire | in-scope, preserved | none.
   - 0.4 (Money math `Decimal`): unchanged — this plan does not touch money-math paths | Plan 04 telemetry_actor wire | out-of-scope | none.
9. Commit: `docs(custos): plan 11 close-out — CLI subcommand align lifecycle.md`.

**Step 1-5**: This task is documentation + version + status — no test/impl cycle. Direct edit + commit.

---

## 验证清单 (Verification)

- [ ] `uv run pytest tests/ -v` — full test suite green (existing Plan 04/05 tests preserved + all new Plan 11 tests pass)
- [ ] `uv run ruff check src/custos/cli/subcommands/ src/custos/cli/validators.py src/custos/core/runner_toml.py` — no lint errors
- [ ] `uv run ruff format --check src/custos/` — formatted
- [ ] `make verify` — full release gate green (equivalent to `check + test-baseline`)
- [ ] `arx-runner --help` prints top-level subcommand list (enroll / start / vault) after `uv sync`
- [ ] `arx-runner vault --help` prints put / verify / list actions
- [ ] `python -m custos --tenant-id t --runner-id r ...` exits code 2 with `arx-runner start` pointer in stderr; **no `DeprecationWarning`** bridge, no partial delegation (`test_python_m_custos_exits_nonzero_with_pointer`)
- [ ] All 21 failure-mode contract tests present and green (grep `test_enroll_double_use_rejected`, `test_vault_verify_sops_fail_no_silent_return`, `test_enroll_rejects_non_http_backend`, `test_per_key_vault_missing_enc_file_clear_error`, `test_vault_put_prefers_stdin_and_warns_on_cmdline_secret`, etc.)
- [ ] `~/.arx/runner.toml` post-enroll has mode `0o600` (test asserts via `os.stat`)
- [ ] `~/.arx/vault/*.enc` post-put has mode `0o600`
- [ ] No `--api-secret` value appears in any structlog output (verified by `test_vault_put_never_logs_secret`)
- [ ] All references to `Plan 11` in source comments removed at execute-time per lesson #15 (semantic phrasing only, no `Plan NN` markers in `.py` files); OK to appear in commit messages + plan file + docs
- [ ] All Step 1.5 evidence anchors (`file:line`) resolvable — grep each anchor still points at the referenced symbol (Task 9 close-out final check)
- [ ] Language Policy: all new source code identifiers / comments / log messages / error strings in English (custos CLAUDE.md § Language Policy)

---

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|------|--------|-----------|-------|
| T1 runner_toml.py + tests | 🔲 | | 5 failure-mode tests: 0600 mode, atomic write, missing file, world-readable reject, arx-dir at 0700 |
| T2 validators.py + tests | 🔲 | | lesson #26 boundary regex; rejects traversal, null byte, control, oversize, empty, non-ASCII |
| T3 dispatcher skeleton | 🔲 | | argparse add_subparsers, no new dep; `--help` / unknown-subcommand tests |
| T4 enroll subcommand | 🔲 | | HTTP client via urllib (zero-dep); mocks arx-78 endpoint; 8 tests including happy + 7 failure modes |
| T5 vault put | 🔲 | | sops encrypt per-key; 6 tests including scope invariant + no-secret-in-logs |
| T6 vault verify + list | 🔲 | | scope re-check on decrypt; list = filesystem scan; 7 tests |
| T7 start subcommand | 🔲 | | reads runner.toml, delegates to refactored `run_daemon`; preserves engine/wal flags; 5 tests |
| T8 [project.scripts] single entry + legacy CLI clean break + SopsAgeVault deletion | 🔲 | | `sys.exit(2)` + one-line pointer to `arx-runner start` (no DeprecationWarning bridge); 4 tests: `test_python_m_custos_exits_nonzero_with_pointer` + `test_no_custos_console_script_registered` + `test_sops_age_vault_class_removed` + `test_default_paths_target_arx_namespace` |
| T9 docs + version bump + close-out | 🔲 | | version 0.1.0 → 0.2.0 (feat minor); docs/design + README + .forge/README index |

> **Notes column convention**: qualitative info (commit hash, key decision, dependency) only. Do not add LOC / estimation values (lesson #4).

---

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|------|------|------|--------|
| DEVIATION | namespace | **`~/.arx/` is the sole namespace.** `~/.custos/` retired entirely per CEO clean-break directive (2026-07-10). Operators upgrading run manual `mv ~/.custos/enrollment.json ~/.arx/enrollment.json && mv ~/.custos/state ~/.arx/state` per README Upgrade section. Documented in Task 9 docs rewrite. | ✅ CEO directive 2026-07-10 |
| DEVIATION | enroll transport | CLI-facing surface is HTTP-only (`urllib.request` POST to `<backend>/api/v1/enrollments`) per lifecycle.md §0.2.2 verbatim. NATS `EnrollmentClient` (`src/custos/core/enrollment.py`) is retained as a low-level building block only — `subcommands/enroll.py` MAY call it in future for non-CLI callers, but no CLI surface exposes it. | ✅ CEO directive 2026-07-10 |
| DEVIATION | vault storage model | Per-key `~/.arx/vault/<key-id>.enc` is the **sole** runtime vault. `SopsAgeVault(sops_file=..., age_key_file=...)` multi-credential-JSON class deleted (T8 removes `credential_vault.py:121-206`). No fallback read path. Reconciler runtime read served by new `PerKeyVault` (C3) inheriting `_BaseVault` invariants. | ✅ CEO directive 2026-07-10 |
| IMPROVEMENT | boundary validation | Explicit `validators.py` module rather than inline regex — reused by every subcommand + cleanly grep-able for lesson #26 audit. | — |
| IMPROVEMENT | HTTP client zero-dep | Chose stdlib `urllib.request` over `httpx` / `requests` — one less audit dependency in a non-custodial red-line surface. | — |

---

## 关联文档 (Related Documents)

- lifecycle.md Phase 0.2 + 0.3 — canonical command surface this plan targets (arx `docs/team-self-hosted-lifecycle.md:73-108`)
- custos CLAUDE.md §5 4 红线 — non-custodial invariants preserved
- custos `docs/design/credential_vault.md` — vault design authority, modified by Task 9
- custos `docs/design/enrollment.md` — enrollment design authority, modified by Task 9
- Plan 04 (custos) — reconciler + WAL + snapshot publisher runtime wire preserved unchanged by Task 7
- Plan 05 (custos) — cli/main.py `_run()` structure this plan refactors + `arx_runner`→`custos` rename context
- arx Plan 78 — in-flight this Wave; provides backend `POST /api/v1/enrollments` contract that Task 4 mocks

---

*Drafter: `drafter-custos-11` @ 2026-07-10 (opus-4-7[1m])*
*Wave: v1-team-full-loop batch*
*Evidence anchors: 15 file:line references, all grep-verified against 2026-07-10 HEAD*
