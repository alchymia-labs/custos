# Plan 00c — L1 codex high-effort peer review (rule 10)

**Reviewer**: codex-cli 0.142.0, model_reasoning_effort=high, sandbox=read-only
**Reviewed at commit**: `3375af3` (branch `custos/00c/runner`, base `eed6a4e`, 8 commits)
**Reviewed on**: 2026-07-07
**Fallback chain level**: L1 (primary; no fallback needed)
**Artifact size**: 4649 bytes (> 500 bytes gate, rule 10 pass)

---

**Verdict**: APPROVE_WITH_FOLLOW_UPS

**Blockers**: None.

**Follow-ups**:
- `tests/test_main_host_selection.py:20`: add a base-install test for `--nt-host` + deploy fail-fast when NT is absent. The code does fail via `src/arx_runner/nautilus_host.py:126`, but the existing test is under `tests/test_nt_trading_node_host.py:24` `pytest.importorskip("nautilus_trader")`, so `tests/test_nt_trading_node_host.py:112` may skip exactly in the missing-NT environment it claims to cover.
- `src/arx_runner/deployment_reconciler.py:65`: consider making undeclared host capabilities explicitly fail with `g6_gate_live_capability_denied` via `getattr(..., lambda: False)`, plus a test. The current direct `host.supports_live()` is fail-closed by `AttributeError`, but not with the structured G6 reason promised by the contract.
- `src/arx_runner/_nt_binance_venue.py:69`: `data_environment_for_mode()` defaults unknown modes to `LIVE`. `src/arx_runner/nautilus_host.py:226` later rejects unknown `trading_mode`, so this is not a sandbox fallback, but a strict unknown-mode test would protect this boundary.

**Confirmations**:
- G6 layer ordering and independence are sound. `_check_g6_gate()` only gates live at `src/arx_runner/deployment_reconciler.py:54`, then checks host live, venue, code hash, and credential scope at `:57-61`. The relaxed-double tests keep prior layers valid: layer 2 uses a live-capable host and only flips connector at `tests/test_g6_gate_capability_e2e.py:99-106`; layer 3 keeps host/venue/scope valid and flips hash at `:109-116`; layer 4 keeps host/venue/hash valid and flips scope at `:141-149`. No dead-branch shadow found.
- Host capability contract is fail-safe for shipped hosts: `NoopHost.supports_live()` and `supports_venue()` return `False` at `src/arx_runner/nautilus_host.py:99-105`; `NtTradingNodeHost.supports_live()` returns `True` and venue support is limited to `_SUPPORTED_VENUES` at `:50-53` and `:133-137`.
- Binance testnet/live branches are present: testnet config pins `BinanceEnvironment.TESTNET` at `src/arx_runner/_nt_binance_venue.py:228-230`; live pins `LIVE` after approval at `:233-236`; live approval rejects `<2` distinct approvers with `sod_approval_missing` at `:81-86`. Host dispatch rejects unknown modes instead of falling back at `src/arx_runner/nautilus_host.py:208-228`.
- CLI default remains `NoopHost`: `--nt-host` is opt-in at `src/arx_runner/__main__.py:73-77`, `_build_host()` returns `NtTradingNodeHost` only when flagged and otherwise `NoopHost` at `:133-139`, and the reconciler still receives that host before every deploy at `:175-180`.
- CEO override four-piece record is present: handoff §0 at `.forge/handoff/2026-07/00c-execute-team-packet.md:10-26`, plan DEV log at `.forge/plans/2026-07/00c-g6-gate-live-release.md:164-169`, `.forge/README.md` footnote at `.forge/README.md:36-43`, and C1 lesson at `.claude/rules/historical-lessons.md:9-21`.
- Commit `7513d97` adds a real guard: live with `code_hash` but no `strategy_path` now refuses before hashing CWD at `src/arx_runner/deployment_reconciler.py:101-113`, with a regression test at `tests/test_g6_gate_capability_e2e.py:130-138`. Sandbox/testnet optional hash behavior is preserved because `_check_g6_gate()` returns for non-live at `src/arx_runner/deployment_reconciler.py:54-56`, and loader skip remains at `src/arx_runner/_strategy_loader.py:70-71`.
- Red-line greps are clean in code: no `log/publish` path mentioning raw `api_key`/`api_secret`, no `SKIP_G6|BYPASS_G6|G6_BYPASS` in executable code, no `stop_all_strategies`, and no `float(` in `deployment_reconciler.py`, `nautilus_host.py`, or `_nt_binance_venue.py`.
- Docker example safety is correct: `.env.example` is non-secret and warns not to overwrite at `examples/supertrend-testnet/.env.example:1-8`; README uses `[ -f .env ] || cp ...` at `examples/supertrend-testnet/README.md:47-50`; vault fixture is placeholder shaped at `examples/supertrend-testnet/vault-fixture/credentials.example.json:1-7`; observability limitation is explicit at `examples/supertrend-testnet/README.md:9-14`.

**Rationale**:
The critical G6 concern passes: each live guard is implemented as a separate check and the relaxed-double tests genuinely exercise the intended layer rather than relying on an earlier failure. The code path for `--nt-host` selects a real host without bypassing the live gate.

I could not execute pytest in this read-only review shell: `python`/`pytest` were not on PATH, `python3` lacked `pytest` and `nautilus_trader`, and `uv run` would require environment writes. This review is therefore source-and-grep based, anchored to target commit `3375af3`.