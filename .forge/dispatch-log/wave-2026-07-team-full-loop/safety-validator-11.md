# Plan 11 Safety Validator Report

**Branch**: `custos/plan-11/runner` @ `4652a47`
**Base**: `main` @ `99112b8`
**Commits**: 10 (T1..T9 + marker)
**Validator**: safety-validator (claude-opus-4-6[1m])
**Date**: 2026-07-11
**Verdict**: **APPROVED**

---

## 8-Checklist Audit

### 1. Key / plaintext never leaves custos process memory

- **Status**: PASS
- **Relevance**: HIGH -- Plan 11 introduces `PerKeyVault` (new runtime vault reader), `vault put/verify/list` subcommands, and `enroll` subcommand that handles enrollment tokens.
- **Evidence**:
  - `grep -rnE 'log\.(info|debug|warning).*(api[_-]?key|api[_-]?secret|password|token|kek)' src/` = **0 hits**. No raw key material appears in any log call.
  - `grep -rnE '(publish|send|emit).*\b(password|secret|api_key|kek)' src/` = **0 hits**.
  - `per_key_vault.py:21` uses `logging.getLogger("custos.credential_vault")` -- all `_log.error(...)` calls log only `credential_id`, `returncode`, `stderr_len` (L55-58), never plaintext.
  - `vault.py:265-270` `_emit_encrypt_audit` logs `key_id` + `tenant_id` + `timestamp` only; api_secret never in log payload.
  - `enroll.py:99` hashes token before sending: `token_hash = hashlib.sha256(args.token.encode("utf-8")).hexdigest()` -- raw token never sent to backend, only hash.
  - `enroll.py:101` HTTP payload contains `token_hash`, not raw token.
  - `grep -rn 'boto3|google.cloud|azure|aws_|gcloud' src/` = **0 hits** (no cloud SDK).
  - `vault.py:130-195` passes plaintext to sops via `subprocess.run(input=payload_bytes)` (stdin pipe, no shell buffer); sops output is encrypted ciphertext written to `.enc` file.
- **Notes**: The `print()` calls in `vault.py` and `enroll.py` are CLI user-facing messages (stderr error reporting); none contain plaintext secrets. `vault.py:229` prints path only (`"credential encrypted to {enc_path}"`).

### 2. G6 gate logic not bypassed

- **Status**: PASS (N/A -- not touched)
- **Relevance**: Plan 11 does not modify G6 gate files. `git diff main...HEAD -- src/custos/core/nautilus_host.py` = empty. `git diff main...HEAD -- src/custos/core/g6_gate.py` = empty (verified by diff stat).
- **Evidence**:
  - G6 gate code at `src/custos/core/g6_gate.py:29` (`check_g6_gate`) and `deployment_reconciler.py:231,235` both untouched by Plan 11.
  - `_daemon.py:187` preserves the comment: "Default NoopHost (paper / dev) declares supports_live()=False so the G6 gate rejects it on live."
  - No new venue client introduced outside `nautilus_host.py`.

### 3. Disconnect != stop (local fallback breaker chain preserved)

- **Status**: PASS
- **Relevance**: Plan 11 extracts the daemon runtime from `main.py` into `_daemon.py`; the fallback breaker chain must survive the extraction.
- **Evidence**:
  - `_daemon.py:30-35` imports `FallbackBreaker`, `FallbackBreakerConfig`, `RunnerNotionalCap`, `ZombieWatchdog` -- all four safety components.
  - `_daemon.py:97-104` wires them: `runner_cap = RunnerNotionalCap(...)`, `fallback_breaker = FallbackBreaker(...)`, `zombie_watchdog = ZombieWatchdog()`.
  - `_daemon.py:112-113` passes both to `DeploymentReconciler`.
  - `grep 'stop_all_strategies|force_shutdown' src/custos/core/reconcile.py` = **0 hits** (no force-stop on disconnect).
  - `nats_client.py` disconnect handling preserved: fire-and-forget noop on disconnect (L366), stash-and-replay on reconnect (L308), at-least-once WAL (L374).

### 4. Reconciliation not silent

- **Status**: PASS (N/A -- not touched)
- **Relevance**: Plan 11 does not modify `reconcile.py` or `deployment_reconciler.py` reconciliation result paths. `git diff main...HEAD -- src/custos/core/reconcile.py` = empty.
- **Evidence**:
  - `reconcile.py:34` `ReconResult` class intact.
  - `reconcile.py:127` dedicated `recon_result` subject preserved.
  - `reconcile.py:129` `upload_recon_result` method intact.

### 5. Reported events contain no key plaintext / strategy source

- **Status**: PASS (N/A -- not touched)
- **Relevance**: Plan 11 does not modify `telemetry_actor.py`. `git diff main...HEAD -- src/custos/core/telemetry_actor.py` = empty.
- **Evidence**:
  - `telemetry_actor.py` whitelist + envelope schema unchanged.
  - `host.py:78` `_sanitize_exception` redaction function intact (L88: `"<redacted: contained credential material>"`).
  - `strategy_loader.py:172` uses `sha256[:8]` for path tags, not plaintext.

### 6. EnrollmentToken one-time + paper_only semantics

- **Status**: PASS
- **Relevance**: Plan 11 introduces `subcommands/enroll.py` -- the new CLI enrollment handler.
- **Evidence**:
  - `enrollment.py:1-8` declares one-time token + paper_only=True default semantics.
  - `enroll.py:99` hashes token with SHA-256 before sending (raw token does not leave the runner process via HTTP).
  - `enroll.py:101` sends `token_hash` (not raw token) in the enrollment payload.
  - `enroll.py:120-124` handles HTTP 409 Conflict (token already consumed) as `enrollment refused` -- consistent with one-time semantics enforced server-side.
  - `enroll.py:155-177` persists the backend response via `RunnerToml.write()` which uses atomic rename + `0600` permissions (`runner_toml.py:56-76`).
  - Token validation at parse time: `enroll.py:85-88` `_validate_token` checks non-empty + reasonable length.

### 7. Python uses uv (no pip)

- **Status**: PASS
- **Relevance**: Plan 11 modifies `pyproject.toml` (new `tomli` dependency for py3.10).
- **Evidence**:
  - `grep -rn 'pip install|python -m pip' src/ scripts/ Makefile` = **0 hits** in project code. The only `pip` references are in vendored `pandas_ta` (`toolkit/vendor/pandas_ta/utils/_data.py:49,119` -- yfinance install instructions in vendored third-party code, not custos code) and `pyproject.toml:25,60` comments (documentation of pip distribution name, not pip commands).
  - `Makefile:14-18` uses `uv sync` exclusively.
  - `Makefile:21-38` uses `uv run` for all tool invocations.

### 8. Silent path must have structlog (or stdlib logging + caplog, per H4 fix)

- **Status**: PASS
- **Relevance**: Plan 11 introduces 5 new files in `src/custos/`: `_daemon.py`, `per_key_vault.py`, `runner_toml.py`, `subcommands/enroll.py`, `subcommands/vault.py`, `validators.py`.
- **Evidence**:
  - **per_key_vault.py**: Every except handler has `_log.error(...)` with structured fields: L50 (`sops_binary_not_found`), L55 (`sops_decrypt_failed`), L65 (`sops_decrypt_timeout`), L71 (`sops_output_parse_failed`), L79 (`credential_not_in_enc_file`). All re-raise after logging. No silent drops.
  - **runner_toml.py:72-80**: `except BaseException` is a best-effort tmpfile cleanup that re-raises the original error (L80 `raise`). The inner `except FileNotFoundError: pass` at L78-79 is cleaning up a temp file that may not exist -- appropriate, and the outer exception propagates. Not a silent drop.
  - **vault.py**: All except handlers either print error to stderr (CLI user-facing) or log with `_log.error(...)`. `BaseException` at L221 is same tmpfile cleanup pattern as runner_toml.py (re-raises).
  - **enroll.py**: All except handlers print to stderr + `_log.error(...)` (L137 `enrollment_connection_error`), or return non-zero exit code with user-facing error message.
  - **_daemon.py:134**: `except Exception` in heartbeat loop has `log.warning("heartbeat_publish_transient_failure", ...)` + continues -- marked `# noqa: BLE001` with reason.
  - **validators.py:51**: `except ValueError` re-raises as `argparse.ArgumentTypeError` -- not silent.
  - Existing core modules (telemetry_actor, nats_client, deployment_reconciler) all have structlog via `custos.core.log.get_logger()` -- unchanged by Plan 11.

---

## Special-Focus Items (Plan 11 R1/R2 Fixes)

### BLK-1: Legacy clean-break

- **Status**: PASS
- **Evidence**:
  - `python -m custos` entry point redirects to error message with pointer to `arx-runner start`: `main.py:17-19`.
  - `SopsAgeVault` removed from runtime: grep in `src/custos/core/credential_vault.py` confirms class body deleted; references in `per_key_vault.py:5` and `_daemon.py:12` are docstring history only, not imports.
  - `tests/test_sops_age_vault_removed.py:13-14` confirms `from custos.core.credential_vault import SopsAgeVault` raises `ImportError`.
  - `~/.custos/` grep in `src/` = **0 hits** (retired path).
  - `DeprecationWarning` grep: only in `tests/test_legacy_cli_removed.py:31-32` which **asserts** DeprecationWarning is NOT present -- confirming clean break (no bridge, no warning, just hard error).

### BLK-3 + N5: MockVault runtime full removal + PerKeyVault unconditional

- **Status**: PASS
- **Evidence**:
  - `grep -rn 'MockVault' src/custos/cli/ src/custos/core/` = **0 hits** as imports or instantiation. Only docstring references (`_daemon.py:13,46`) explain the design decision.
  - `_build_vault()` at `_daemon.py:43-56` unconditionally returns `PerKeyVault(vault_dir=..., tenant_id=..., initiator=...)`. No 3-way branch, no MockVault fallback, no conditional logic.
  - `MockVault` in `tests/` exists only in `test_main_starts_state_snapshot_publisher.py:115` as a test fixture comment -- not imported or instantiated.

### H4: Audit event (stdlib logging in credential vault)

- **Status**: PASS
- **Evidence**:
  - `per_key_vault.py:21`: `_log = logging.getLogger("custos.credential_vault")` -- stdlib logger, same namespace as `credential_vault.py:34`.
  - `per_key_vault.py` logs at every error path (L50, L55, L65, L71, L79) with structured `extra={}` dicts.
  - `vault.py:37`: `_log = logging.getLogger("custos.credential_vault")` + `_log.info("credential_encrypted", ...)` at L265 and `_log.error(...)` at L190, L197.
  - `enroll.py:29`: `_log = logging.getLogger("custos.enrollment")`.
  - stdlib logging is the documented H4 fix approach (defence-in-depth alongside structlog in other modules; caplog assertions work uniformly in tests).

### H1: URL scheme allowlist

- **Status**: PASS
- **Evidence**:
  - `validators.py:24`: `_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})` -- explicit allowlist.
  - `validators.py:42-64` `validate_backend_url()`:
    - L53: Rejects non-http(s) schemes (`file://`, `gopher://`, etc.).
    - L57: Rejects empty netloc.
    - L59-62: Rejects embedded userinfo.
    - L63: Rejects fragments.
  - `enroll.py:40-47` `_validate_redirect_url()` re-runs `validate_backend_url()` on 3xx Location headers -- preventing SSRF via redirect.
  - `tests/test_cli_validators.py` (117 lines) covers all rejection cases.

---

## Conditions

None. All 8 checklist items PASS with grep evidence.

---

## Blockers

None.

---

## Recommendation

**APPROVED for merge.** Plan 11 is a CLI restructuring plan (subcommand dispatcher + PerKeyVault + runner.toml + enrollment handler + validators). The non-custodial 4 red lines are fully preserved:

1. Key material never enters log/publish/send paths. The new PerKeyVault logs only metadata (credential_id, returncode, stderr_len). Enrollment sends token_hash, not raw token.
2. G6 gate untouched by this plan.
3. FallbackBreaker + ZombieWatchdog + RunnerNotionalCap chain faithfully extracted into `_daemon.py` with all four components wired.
4. No money math paths introduced (Plan 11 is CLI/vault, not trading).

The R1/R2 fix items (BLK-1 clean-break, BLK-3/N5 MockVault removal, H4 audit events, H1 URL allowlist) are all properly implemented with grep-verified evidence.
