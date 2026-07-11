# Plan 11 runner-executor progress

Worktree: `.worktree/plan-11-runner`
Branch: `custos/plan-11/runner`
Base SHA: `99112b8`

## T1 — runner_toml.py foundation
- SHA: `42c7bff`
- Files: 2 new (src/custos/core/runner_toml.py, tests/test_runner_toml.py)
- Tests: 7 passed, 0 failed (test_write_creates_file_at_0600 / test_write_creates_arx_dir_at_0700 / test_read_round_trips_written_record / test_read_rejects_world_readable_mode / test_read_missing_file_raises_clear_error / test_atomic_write_survives_interrupt / test_read_rejects_missing_required_field)
- Notes: Round trip test added beyond plan's 5 explicit tests (defensive; catches serialiser/deserialiser drift). Missing-required-field added for read-side defence (surfaces partial toml corruption cleanly).

## T2 — validators.py boundary regex
- SHA: `72c8b63`
- Files: 2 new (src/custos/cli/validators.py, tests/test_cli_validators.py)
- Tests: 63 passed (parametrised); 14 logical assertions covering accepts valid, path traversal, null byte, control chars 0x00-0x1F + 0x7F, oversize, empty, non-ASCII, url http/https accept, file/gopher/bare/empty-netloc/userinfo/fragment reject
- Notes: Non-ASCII parametrise row required `noqa: language` on the CJK sample line — this is canonical enforcement of the reject contract, not a violation. Ruff auto-fixed an isort ordering after inserting the parametrise block.

## T3 — subcommand dispatcher skeleton
- SHA: `8ad4590`
- Files: 5 new (subcommands/__init__.py + enroll.py + start.py + vault.py + tests/test_cli_unknown_subcommand.py)
- Tests: 6 passed (no subcommand / unknown subcommand / enroll --help / start --help / vault --help / vault without action)
- Notes: Every subcommand's argparse `type=` runs the t2 validators so id/backend rejection happens at parse time. Handler bodies raise NotImplementedError with semantic (non plan-numbered) messages per lesson #15. Full make verify: 311 passed, 1 pre-existing pandas_ta failure (pkg_resources / setuptools 70+, documented in pyproject.toml). No regressions.

## T4 — enroll subcommand
- SHA: `186992d`
- Files: 1 modified (subcommands/enroll.py), 1 new (tests/test_cli_enroll.py)
- Tests: 12 passed (happy / connection error / 500 / 409 / arx dir 0700 / null-byte token / traversal tenant / file/gopher/bare backend x3 / payload shape (verifies no `tenant_id` in wire, `token_hash` present) / never logs raw token)
- Notes: MonkeyPatch mocks `urllib.request.urlopen`, so impl calls that (not build_opener().open()). Redirect re-validation implemented via response.url check (isinstance str guard prevents MagicMock false-positive). Token validator moved to argparse `type=` so control-char rejection happens at parse time (SystemExit path) matching backend/id pattern.

## T5 — vault put (sops encrypt per-key)
- SHA: `ddec7c4`
- Files: 2 modified (subcommands/vault.py, core/credential_vault.py [AuditEvent enum extended]), 1 new (tests/test_cli_vault_put_verify.py)
- Tests: 10 passed (happy / rejects existing enc / missing sops binary / keyid traversal / permission_scope invariant / never logs secret dual sink caplog+structlog / audit event / stdin secret / env secret / argv warns ps aux)
- Notes: subprocess.run(input=...) direct stdin, no shell intermediary. AuditEvent enum gains CREDENTIAL_ENCRYPTED = "CredentialEncrypted"; audit event via stdlib logging.getLogger("custos.credential_vault") mirrors decrypt path for uniform caplog. Refuses overwrite (no --force in v1) — force flag can land as follow-up when rotation cadence needs it.

## T6 — vault verify + list
- SHA: `c826fb8`
- Files: 1 modified (subcommands/vault.py), 1 modified (tests/test_cli_vault_put_verify.py)
- Tests: 9 new passed (verify happy / verify sops fail / verify scope violation / verify missing / verify world-readable / list shows / list empty prints hint / list warns world-readable / put reuses arx dir 0700 L3 crosscut)
- Notes: `_BaseVault._verify_permission_scope` reused via import from custos.core.credential_vault. list is diagnostic (exit 0 even on mode warning to stderr). Full make verify checkpoint: 342 passed, same 1 pre-existing pandas_ta failure. No regressions.

## T7 — start subcommand + _daemon.py + PerKeyVault
- SHA: `04ebb5c`
- Files: 1 modified (subcommands/start.py), 4 new (cli/_daemon.py, core/per_key_vault.py, tests/test_cli_start.py, tests/test_per_key_vault.py)
- Tests: 11 passed (6 start: reads runner.toml / missing / partial / world-readable / preserves flags / default paths ~/.arx | 5 per_key_vault: missing enc / scope violation / sops fail / happy audit / sops binary missing)
- Notes: `_run` body extracted verbatim to `_daemon.run_daemon` — vault selection changed to unconditional PerKeyVault (MockVault runtime fallback removed per N5 CEO decision option (a) 2026-07-10). Legacy `cli/main.py` still present, T8 will rewrite it to the 5-line stub. Full pytest: 353 passed, same 1 pre-existing pandas_ta failure. No regressions across Plan 04/05 reconciler / heartbeat / snapshot tests.

## T8 — pyproject scripts + legacy CLI clean break + SopsAgeVault deletion
- SHA: `6eabe9b`
- Files: 6 modified (pyproject.toml [+ single arx-runner entry + 0.1.0→0.2.0], uv.lock, cli/main.py [rewrite to stub], core/credential_vault.py [delete SopsAgeVault, extend AuditEvent], 3 legacy test files migrated to _daemon imports), 2 new tests (test_legacy_cli_removed, test_sops_age_vault_removed), 1 deleted test (test_credential_vault_sops.py)
- Tests: 7 new passed (python -m custos exits 2 + arx-runner pointer + no DeprecationWarning / no custos console script / DEFAULT_* paths .arx-only / arx-runner registered / SopsAgeVault ImportError / base helpers survive / PerKeyVault inherits _BaseVault)
- Notes: Also fixed 3 pre-existing tests that imported `_build_host` / `_build_reconciler` from `cli.main` to point at `_daemon`. Full make verify: 351 passed, same 1 pre-existing pandas_ta failure. Console script re-registered via uv sync. `arx-runner --help` now the front door.

## T9 — docs update + close-out
- Files: 5 modified (README.md, docs/design/enrollment.md, docs/design/credential_vault.md, .forge/README.md [plan index row + exec order], .forge/plans/2026-07/11-*.md [status flip + progress table updated + Verification checklist flipped + Close-out Report + red-line gate table appended + R2 follow-ups N2/N3/N4 resolved inline])
- Tests: none new (docs + close-out only)
- Notes: Red-line gate table (lesson #40) filled per spec — 0.1 fully wired via PerKeyVault + audit event; 0.2 preserved via _daemon._build_host; 0.3 preserved via _daemon._build_reconciler composing FallbackBreaker + RunnerNotionalCap + ZombieWatchdog; 0.4 out of scope. L-R2-2 CHANGELOG wording handed to Plan 12 T5 owner (this plan does not touch CHANGELOG.md per merge conflict prevention checklist). ADR-014 workspace edit skipped for independent-repo executor per spec.








