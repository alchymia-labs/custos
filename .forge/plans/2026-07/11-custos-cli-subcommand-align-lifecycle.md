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
| `src/custos/cli/subcommands/start.py` | Create | `arx-runner start` — read `runner.toml`, delegate to shared `_run()` coroutine extracted from `cli/main.py` |
| `src/custos/cli/validators.py` | Create | `validate_id(name, value)` — regex `^[a-zA-Z0-9_-]{1,64}$` for tenant_id / runner_id / key-id (raises `argparse.ArgumentTypeError`) |
| `src/custos/core/runner_toml.py` | Create | `RunnerToml.read(path)` / `RunnerToml.write(path, record)` — TOML I/O + atomic tmpfile+fsync+rename + 0600 mode invariant; `~/.arx/` dir auto-create at 0700 |
| `src/custos/cli/main.py` | **Delete majority** | Delete `_parse_args()` flat 13 flags + `_build_vault()` + `_build_host()` + `_build_reconciler()` + `_heartbeat_loop()` + `_run()` (relocated to `cli/subcommands/start.py`). Only remaining content: 5-line stub `main()` that prints `"custos: this entry point has been removed; use \`arx-runner start\` (see arx docs/team-self-hosted-lifecycle.md Phase 0.2)"` to stderr and `sys.exit(2)`. Path stays for `python -m custos` invocation to give a clear error instead of `ModuleNotFoundError`. |
| `src/custos/core/credential_vault.py` | **Delete lines 121-206** | Delete `SopsAgeVault` class outright. Keep only `CredentialVault` mock/base class (dev/paper) at `credential_vault.py:1-120`. |
| `tests/test_credential_vault_sops.py` | **Delete file** | Legacy `SopsAgeVault` tests — no longer applicable. |
| `pyproject.toml` | Modify | Add `[project.scripts]` block with **single entry**: `arx-runner = "custos.cli.subcommands:main"`. **No `custos = ...` entry.** Version bump `0.1.0` → `0.2.0` (semver `feat` breaking change; documented in `README.md` upgrade section). |
| `README.md` | Modify | Rewrite Quick Start (`README.md:76-79`) to `arx-runner enroll` / `arx-runner vault put` / `arx-runner start` flow. Add explicit **Upgrade from 0.1.x** section: (1) `pip install --upgrade custos-runner` (2) `mv ~/.custos/enrollment.json ~/.arx/enrollment.json` (3) `mv ~/.custos/state ~/.arx/state` (4) manually rerun `arx-runner enroll` (long-term credential) + `arx-runner vault put` per old sops-file credential. No auto-migration script provided. |
| `tests/test_cli_enroll.py` | Create | happy path (mocked backend 200) + failure modes: `token_double_use`, `backend_unreachable`, `backend_500_no_partial_persist`, `arx_dir_missing`, `token_traversal` |
| `tests/test_cli_vault_put_verify.py` | Create | put/verify/list happy path (mocked `subprocess.run(sops)`) + failure modes: `sops_decrypt_fail_no_silent_return`, `keyid_traversal`, `vault_file_0644_rejected` |
| `tests/test_cli_start.py` | Create | read runner.toml → wire reconciler + snapshot publisher (mocked NATS) + missing runner.toml fail-fast + partial runner.toml (missing tenant_id) rejected |
| `tests/test_runner_toml.py` | Create | atomic write (crash mid-write → old file intact) + 0600 preserved on rename + `~/.arx/` created at 0700 |
| `tests/test_cli_validators.py` | Create | reject `..`, `\0`, control chars 0x00-0x1F, oversized > 64 chars, empty, non-ASCII |
| `tests/test_deprecated_warning_on_old_entry.py` | Create | `python -m custos --tenant-id t --runner-id r ...` still runs + stderr contains `DeprecationWarning` + `arx-runner start` guidance |
| `tests/test_cli_unknown_subcommand.py` | Create | `arx-runner foo` → non-zero exit + `--help`-style listing |
| `docs/design/enrollment.md` | Modify | Add "HTTP enroll path (Plan 11)" section documenting the runner-side POST + runner.toml persistence contract |
| `docs/design/credential_vault.md` | Modify | Add "Per-key vault (Plan 11)" section documenting `~/.arx/vault/<key-id>.enc` and its coexistence with the multi-credential sops JSON |

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

All 14 failure modes are code-level tests (Python `pytest` + `unittest.mock`). No runtime-wire integration test is scoped in this plan; the runtime wire is already covered by Plan 04's reconciler tests and this plan does not modify reconciler code.

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

**Step 2**: `uv run pytest tests/test_cli_validators.py -v` — all fail.

**Step 3**: Minimal implementation
```python
_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def validate_id(name: str, value: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{name!r} must match ^[a-zA-Z0-9_-]{{1,64}}$ (got {value!r})"
        )
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
- `test_enroll_payload_shape`: assert mocked call payload = `{"token_hash": <sha256 hex>, "runner_id": <id>, "agent_version": <str>, "capabilities": <list>}` (mirrors `enrollment.py:57-63`)

**Step 2**: `uv run pytest tests/test_cli_enroll.py -v` — all fail (handler is `NotImplementedError` stub).

**Step 3**: Minimal implementation
- Parse `--token`, `--backend`, `--tenant-id` (validated), `--runner-id` (validated), `--runner-toml` (default `~/.arx/runner.toml`), optional `--agent-version`, `--capabilities`.
- `run(args)`:
  1. Validate ids via `validators.validate_id`.
  2. Compute `token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()` (reuse `enrollment.hash_token`).
  3. Build payload dict matching arx-78 shape.
  4. `urllib.request.Request(f"{backend}/api/v1/enrollments", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})`, POST via `urlopen(req, timeout=30)`.
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
- Parse `--key-id` (validated), `--api-key`, `--api-secret`, `--age-recipient` (or env `SOPS_AGE_RECIPIENT`), `--vault-dir` (default `~/.arx/vault`).
- Build plaintext payload dict `{key_id: {api_key, api_secret, permission_scope: "trade_no_withdraw"}}` (matching the multi-cred sops JSON shape at `credential_vault.py:193-202`, but with just one credential per file).
- `subprocess.run(["sops", "--encrypt", "--age", recipient, "--input-type", "json", "--output-type", "json", "/dev/stdin"], input=json.dumps(payload).encode(), capture_output=True, check=True, timeout=30)`.
- Write result.stdout to tmpfile → `os.chmod(tmp, 0o600)` → `os.rename(tmp, vault_dir / f"{key_id}.enc")`.
- Emit structlog `credential_encrypted` audit event (key_id + tenant only, no plaintext) — mirrors the decrypt audit event at `credential_vault.py:64-81`.

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

### Task 7: `start` subcommand — read runner.toml + reuse `_run`

**Files**:
- Modify `src/custos/cli/subcommands/start.py`
- Modify `src/custos/cli/main.py` (extract `_run_from_config` from `_run`, keep both callable)
- Create `tests/test_cli_start.py`

**Step 1**: Write failing tests
- `test_start_reads_runner_toml_and_wires_reconciler`: pre-write valid runner.toml → `start` calls `_run` with tenant/runner from toml + mocked NATS connect (via `unittest.mock.patch("custos.core.nats_client.ArxNatsClient")`)
- `test_start_missing_runner_toml_fails_fast`: no `~/.arx/runner.toml` → non-zero exit + stderr "run `arx-runner enroll` first"
- `test_start_partial_runner_toml_rejected`: runner.toml missing `tenant_id` field → non-zero exit + clear parse error
- `test_start_preserves_engine_and_wal_flags`: `--engine nautilus --wal-path /tmp/wal.db` still work + override runner.toml defaults
- `test_start_rejects_world_readable_runner_toml`: runner.toml at 0o644 → non-zero exit via `runner_toml.read()` mode check (Task 1 invariant)

**Step 2**: `uv run pytest tests/test_cli_start.py -v` — all fail.

**Step 3**: Minimal implementation
- Refactor `cli/main.py`: extract the post-`_parse_args` half of `_run` into a new `async def run_daemon(args)` that expects a filled `argparse.Namespace`. Legacy `_run` becomes `run_daemon(_parse_args(...))`.
- `subcommands/start.py:run(args)`:
  1. `record = runner_toml.read(args.runner_toml_path)` — fail-fast if missing / bad mode / partial.
  2. Build a compatible `argparse.Namespace` with tenant_id / runner_id from record + CLI overrides for nats_url / wal_path / snapshot_interval_secs / engine / use_nt_host / reconcile_strategy_id / heartbeat_interval / enrollment_token=None / enrollment_path=default / sops_file=optional / age_key_file=optional.
  3. `asyncio.run(main.run_daemon(ns))`.

**Step 4**: `uv run pytest tests/test_cli_start.py -v` — all pass. Also `uv run pytest tests/ -k "test_cli_main or test_reconciler_" -v` — Plan 04/05 tests remain green (regression sanity).

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
- Delete `SopsAgeVault` from `src/custos/core/credential_vault.py` (lines 121-206 in current file). Verify remaining `CredentialVault` mock/base class at lines 1-120 still passes `tests/test_credential_vault.py`.
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
- Modify `the-alephain-guild/codex/decisions/ADR-014-ecosystem-open-source-boundary.md` — **append a short "Custos v0.2.0 clean-break release (2026-Q3)" note under Consequences (or a new "Evolution" subsection at the end)** recording: (a) `SopsAgeVault` JSON multi-credential layout removed; (b) legacy `python -m custos` CLI entry + `[project.scripts].custos` removed; (c) `~/.custos/` namespace retired to `~/.arx/` (single-namespace policy); (d) reason chain: alignment with arx `docs/team-self-hosted-lifecycle.md` §0.2 + §0.3 verbatim command surface + lesson #35 dual-source-elimination + CEO clean-break directive (2026-07-10). Cross-ref: `custos/.forge/plans/2026-07/11-*.md` + `custos/.forge/plans/2026-07/12-*.md` close-out reports. **No `codex/projects/custos/` subdir is created in this plan** (CEO decision 2026-07-10) — the ecosystem-catalog + ADR-014 entries continue to serve as custos's workspace-level anchor; a dedicated custos codex project subdir is a future-plan candidate if/when custos codex-level architecture spec is warranted (currently the `custos/docs/design/*.md` in-repo design specs are the source of truth for single-repo audit).
- Modify `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md` — status to `✅ Completed`.
- Modify `.forge/README.md` — add Plan 11 row to plan index table with prominent "breaking change" annotation.
- **Version bump decision**: this plan is a breaking change (removed CLI + removed vault class + retired namespace). Semver `feat!` (breaking) → bump minor version in `pyproject.toml` (`0.1.0` → `0.2.0`) since we are pre-1.0 (SemVer §4 allows breaking changes in 0.x minor bumps).
- Modify `.forge/plans/2026-07/11-custos-cli-subcommand-align-lifecycle.md` — status to `✅ Completed`
- Modify `.forge/README.md` — add Plan 11 row to plan index table
- **Version bump decision**: this plan adds new console-script surface + new subcommands + new `~/.arx/` filesystem contract → semver `feat` → bump minor version in `pyproject.toml` (`0.1.0` → `0.2.0`)

**Actions**:
1. Flip `Status: 🔲 Not started` → `Status: ✅ Completed` + add `Completed: YYYY-MM-DD`.
2. `.forge/README.md` — append Plan 11 row with slug + status + depends + blocks + notes.
3. `docs/design/enrollment.md` — document `<backend>/api/v1/enrollments` request payload shape + response shape (`long_term_credential` + `enrolled_at_ns`) + `~/.arx/runner.toml` persistence contract + coexistence with existing NATS `enrollment.json` (paragraph, not a rewrite).
4. `docs/design/credential_vault.md` — document `~/.arx/vault/<key-id>.enc` per-key model + read/write API for `vault put/verify/list` + coexistence with existing single-file `SopsAgeVault` (paragraph).
5. `README.md:76-96` (Quick Start) — replace `python -m custos ...` example with the three-command lifecycle: enroll → vault put → start.
6. `pyproject.toml` version `0.1.0` → `0.2.0`.
7. Add "完成报告 (Close-out Report)" section at the end of this plan file, summarizing: (a) actual file inventory delta vs planned, (b) any failure modes uncovered during implementation added beyond the 14 contracted, (c) any deviations logged.
8. Commit: `docs(custos): plan 11 close-out — CLI subcommand align lifecycle.md`.

**Step 1-5**: This task is documentation + version + status — no test/impl cycle. Direct edit + commit.

---

## 验证清单 (Verification)

- [ ] `uv run pytest tests/ -v` — full test suite green (existing Plan 04/05 tests preserved + all new Plan 11 tests pass)
- [ ] `uv run ruff check src/custos/cli/subcommands/ src/custos/cli/validators.py src/custos/core/runner_toml.py` — no lint errors
- [ ] `uv run ruff format --check src/custos/` — formatted
- [ ] `make verify` — full release gate green (equivalent to `check + test-baseline`)
- [ ] `arx-runner --help` prints top-level subcommand list (enroll / start / vault) after `uv sync`
- [ ] `arx-runner vault --help` prints put / verify / list actions
- [ ] `python -m custos --tenant-id t --runner-id r ...` still runs + emits `DeprecationWarning` to stderr
- [ ] All 14 failure-mode contract tests present and green (grep `test_enroll_double_use_rejected`, `test_vault_verify_sops_fail_no_silent_return`, etc.)
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
| T8 [project.scripts] + deprecated | 🔲 | | DeprecationWarning to stderr + warnings module; 3 tests (2 skip if not installed) |
| T9 docs + version bump + close-out | 🔲 | | version 0.1.0 → 0.2.0 (feat minor); docs/design + README + .forge/README index |

> **Notes column convention**: qualitative info (commit hash, key decision, dependency) only. Do not add LOC / estimation values (lesson #4).

---

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|------|------|------|--------|
| DEVIATION | numbering | Plan 11 chosen (not 09 or 10) because `.forge/README.md:65,67` reserves 09 for hook infra formalization and 10+ for future engine backends. Team-lead brief §L2 confirms 11 is next free integer. Recorded to protect against silent renumbering. | ✅ (team-lead brief) |
| DEVIATION | namespace | Two-namespace persistence: `~/.arx/runner.toml` + `~/.arx/vault/*.enc` (new, this plan) vs `~/.custos/enrollment.json` + `~/.custos/state/telemetry-wal.db` (existing, Plan 04/05). Chose coexistence over rename to avoid lesson #35 fanout cascade in Plan 04 fallback tests. Documented in Task 9 docs. | ⏳ pending review-time |
| DEVIATION | enroll transport | Added HTTP path (`urllib.request` POST to `<backend>/api/v1/enrollments`) alongside existing NATS `EnrollmentClient.enroll()`. lifecycle.md §0.2.2 mandates HTTP; NATS kept for backward compat during Plan 05→11 transition. | ⏳ pending review-time |
| DEVIATION | vault storage model | Per-key `~/.arx/vault/<key-id>.enc` (new) coexists with single-file multi-credential sops JSON model at `credential_vault.py:121-206` (Plan 05, unchanged). Two models express two lifecycle intents: per-key rotation (lifecycle.md) vs bundled (Plan 05 test fixtures). | ⏳ pending review-time |
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
