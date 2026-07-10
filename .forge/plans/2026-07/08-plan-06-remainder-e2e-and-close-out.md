# 08 — Plan 06 remainder: real supertrend e2e (sandbox + testnet) + ps sidecar retirement docs + Plan 06 close-out

> **Status**: 🔲 Todo (Phase 2 refined 2026-07-09; codex L1 REQUEST_CHANGES fix cycle applied 2026-07-09)
> **Created**: 2026-07-09 (plan-drafter-08, opus-4-7[1m])
> **Refined**: 2026-07-09 (evidence-scout §5/§6/§7/§8 as the sole grep source for contract anchors)
> **Fix cycle**: 2026-07-09 (in-place fix of 9 codex L1 findings — see `.forge/fixes/2026-07/08-plan-fix.md`)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Phase 2 refined; use `/forge:execute` or execute-team to implement
> **Depends on**: **Plan 07 landing** (curation scope decision hardens T5 e2e coverage policy) + Plan 06 06a landed at `306b9e5` (vendored toolkit + loader integration are the substrate T5 exercises) + Plan 00a + 00b + 00c + 03 + 05 (all ✅)
> **Blocks**: Plan 06 close-out (Track 6 T6.2 flips Plan 06 status to ✅) + first paper→testnet production acceptance for ps supertrend on custos
> **multi_session_scope**: **false** (4 tasks; e2e-focused, minimal source changes; T5.2 testnet is the only session-boundary risk — degrades to partial+manual verification per DP1 fallback, does not force a session split)

---

## Origin

Plan 06 06a spawn prompt explicitly deferred Tracks 5 and 6 to a follow-up slice originally labelled `06b`:

- 06a delivered Tracks 1-4 (vendored toolkit + strategy_registry_name post-load introspection + supertrend RiskController activation + TradingNodeConfig plumb-through) and committed 10 DEV entries in the close-out marker.
- Track 5 (real supertrend e2e — sandbox and testnet) and Track 6 (ps sidecar/runner retirement docs + Plan 06 close-out) were deliberately held over because e2e depends on the vendored toolkit substrate landing first and the docs section is downstream of the toolkit decision.

After 06a squash-merge (`306b9e5`), CEO 2026-07-09 renumbered the remainder from `06b` to **Plan 08** — Plan 07 (ps `shared/` curation → custos toolkit authority + ps convergence) crosses in between, and a continuous `06b` label would misread the plan sequence. The renumber decision is registered as `DEV-08-RENUMBER-FROM-06B` below.

---

## Context

### Contract anchors (Step 1.5 Contract Verification Gate)

> **as-of evidence-scout Foundation Scan** (custos main HEAD `306b9e5` + `5c01cdb` hook infra + `55782d0` orchestration artifacts, 2026-07-09) + ps `develop` HEAD `34b73a2` (2 commits post-toolkit-pin, both outside `shared/`). All anchors trace to the scout report or Plan 06 by explicit file:line; the "Verbatim scout / Plan 06 quote" column carries the exact source text so a reviewer can grep-verify it (lesson C2 output-pollution defense). The "Summary" column is drafter paraphrase for reading flow — verbatim is the load-bearing column. Every NEW test name below was independently grep-verified by scout §5 as 0-hits across the custos repo (lesson #25 zero-fabrication discipline).

| Contract cited | Source anchor | Verbatim scout / Plan 06 quote | Summary (drafter paraphrase, non-authoritative) |
|----------------|---------------|--------------------------------|-------------------------------------------------|
| Existing sandbox lifecycle test module | `evidence-scout-07-08.md` §6 line 181-183 | *"`tests/test_nt_trading_node_host_integration.py` (104 lines total, full file read): **Module docstring** (`:1-12`): explicitly states this test builds a *real* NT `TradingNode` with real Binance sandbox venue configs and a **self-contained minimal `SuperTrend`-shaped fixture** (`fixtures/minimal_supertrend_strategy.py`) — 'there is no runtime dependency on `philosophers-stone/shared/`' by design. Only network I/O (`run_async`) is stubbed."* | T5.1 scaffolding reuse baseline |
| `_spec()` fixture builder | `evidence-scout-07-08.md` §6 line 185 | *"`_spec()` (`:33-43`, builds a minimal `DeploymentSpec`-shaped dict)"* | T5.1 reusable helper |
| `_credential()` fixture builder | `evidence-scout-07-08.md` §6 line 185 | *"`_credential()` (`:46-51`, sentinel `api_key`/`api_secret`/`permission_scope=\"trade_no_withdraw\"`)"* | T5.1 + T5.2 credential surface; sentinel is the leak-negative anchor for FU-2 |
| `_parked_run()` monkeypatch | `evidence-scout-07-08.md` §6 line 185 | *"`_parked_run()` (`:54-56`, stands in for `run_async` — parks until cancelled since CI has no exchange connectivity)"* | T5.1 reusable pattern for sandbox lifecycle without network |
| Existing sandbox lifecycle test asserts fixture strategy | `evidence-scout-07-08.md` §6 line 187 | *"`test_full_lifecycle_sandbox_supertrend(monkeypatch)` (`:59-87`) — the reusable pattern for T5.1: monkeypatches `TradingNode.run_async`, calls `host.deploy(spec, credential)`, asserts `container_id`, inspects `host._active_nodes[\"int-1\"]` for the registered strategy instance, then deterministically cancels/tears down the parked task."* | Baseline for T5.1 to **swap** fixture load for vendored-toolkit load of the **real** `SuperTrendStrategy` |
| Vendored toolkit substrate | `evidence-scout-07-08.md` §2.1 line 71-83 + §2.2 line 90 | *"§2.1 vendored subset (in `toolkit/shared/`) — 9 subpackages (config/filters/indicators/nautilus/position/protocols/risk/signals/warmup), total 90 files / 17110 LOC, all pinned to upstream SHA `fc4ab1d`. Every row's file-count and LOC is byte-for-byte identical to the corresponding ps `shared/<pkg>` row in §1.1 — the vendoring is a verified verbatim snapshot. §2.2: `toolkit/__init__.py` prepends `toolkit/` and `toolkit/vendor/` to `sys.path` (idempotent) so `from shared.<pkg>` and `import pandas_ta` resolve without rewriting any vendored import statement."* | T5.1 loads real supertrend via this substrate |
| Testnet venue routing | `evidence-scout-07-08.md` §7 line 198-200 | *"`venue_binance.py:57-60` — `_DATA_ENVIRONMENT_BY_MODE = {\"sandbox\": BinanceEnvironment.LIVE, \"testnet\": BinanceEnvironment.TESTNET, \"live\": BinanceEnvironment.LIVE}` (data feed always real/LIVE except execution env switches for testnet). `venue_binance.py:228-230` — `build_exec_client_config_testnet(spec, credential)` → `_build_binance_exec_config(spec, credential, BinanceEnvironment.TESTNET)`. `host.py:291-292` — `if trading_mode == \"testnet\": exec_cfg = venue.build_exec_client_config_testnet(spec, credential)`."* | T5.2 target — `trading_mode="testnet"` reaches `BinanceEnvironment.TESTNET` for execution |
| Credential vault mode-agnostic scope check | `evidence-scout-07-08.md` §7 line 201 | *"`src/custos/core/credential_vault.py` (grep `:1-204`) — `permission_scope` enforcement is **mode-agnostic**: `_verify_permission_scope()` (`:84-97`) unconditionally rejects any credential whose `permission_scope != \"trade_no_withdraw\"`, regardless of `sandbox`/`testnet`/`live`. There is no separate 'testnet credential' code path in the vault — a testnet API key/secret goes through the exact same vault decrypt + scope-check flow as a live key."* | T5.2 testnet credential goes through the **same** vault path as live — DP1 material |
| Sidecar retirement docs baseline | `evidence-scout-07-08.md` §8 line 208 | *"`docs/design/nautilus_host.md` — 129 lines total. `grep -n \"sidecar\|supertrend\|migration\|ps 侧\|philosophers\" docs/design/nautilus_host.md` → **0 hits**. Confirms Plan 06's own T6.1 Step-1 red-state grep baseline is accurate as of this scan — T6.1's docs-only addition has genuinely not landed yet."* | T6.1 red-state |
| Crucible sidecar consumers | `evidence-scout-07-08.md` §4.2 line 120-129 | *"Grep `grep -rln -i sidecar crucible_engine --include='*.py'` → **25 files**. Core 4 files matching the packet's naming (`sidecar_models.py`(118) + `supervisor.py`(1778) + `risk_monitor.py`(649) + `metrics_persister.py`(91)). `grep -rn -E \"(from shared\|import shared)\" crucible_engine --include='*.py'` → **0 hits**. `crucible_engine` does **not** import ps `shared.*` directly — it talks to the ps sidecar over HTTP only (`crucible_engine/supervisor.py:32` `import httpx`; `:172-173` `self._http_client = httpx.AsyncClient(...)`; `:362` `instance.sidecar_url = f\"http://{container_ip}:8080\"`)."* | T6.1 no-destructive-delete constraint |
| Crucible Docker builds ship ps `shared/` | `evidence-scout-07-08.md` §4.2 line 133-134 | *"`philosophers-stone/deploy/nautilus/Dockerfile:1-8` (header comment): 'engine — runtime base: NT + deps + **shared** + sidecar (no git/uv)'; `:35` `COPY shared/README.md /tmp/deps/shared/README.md` inside the dependency-install stage. `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29,49`: `COPY --chown=hummingbot:hummingbot shared /home/hummingbot/shared`; `ENV PYTHONPATH=/home/hummingbot:/home/hummingbot/shared`."* | T6.1 must document the **second production consumer** of ps `shared/` |
| arx web sidecar consumers | `evidence-scout-07-08.md` §4.3 line 142-152 | *"`grep -rln -i sidecar web/ --include='*.ts' --include='*.tsx' --include='*.json'` → **8 files** (packet said '9 file' — one of the 8 is `web/package-lock.json`, an npm lockfile hit unrelated to actual sidecar-consumption code, so the real source-code consumer count is **7 files**, not 9). `web/lib/hooks/useApi.ts:207-217` shows a comment documenting a `StrategyPosition` interface fetched via the sidecar's real-time position proxy endpoint. This consumer talks HTTP to crucible's API (which relays to the sidecar), not to ps `shared/` directly — no Plan 07 curation decision affects this path; it is purely a Plan 08 DP2 matter, orthogonal to Plan 07's shared/ curation scope."* | T6.1 documents arx web sidecar HTTP tech-debt as **independent follow-up** (DP2 candidate) |
| No CI infrastructure | `evidence-scout-07-08.md` §9 line 216-217 | *"`find .github -type f` → **no output, directory does not exist**. Custos has no CI integration today. `Makefile` targets: … `toolkit-sync-check` exists as a stub target only (per its one-line help text: 'Print vendored toolkit upstream commits + hint how to diff against upstreams' — no diff implementation yet)."* | T5.2 baseline `make verify` remains the sole verification entrypoint; T5.2 `@integration` marker keeps testnet out of baseline |
| Plan 06 T5.1/T5.2/T6.1/T6.2 contract | `.forge/plans/2026-07/06-ps-supertrend-migration.md:371-374` (failure-mode table T5/T6 rows) | *"T5.1 real supertrend sandbox 加载/部署失败 → `test_real_supertrend_loads_and_deploys_sandbox` (NEW). T5.1 credential 泄漏到 telemetry/status/log (红线 0.1, FU-2) → `test_credential_not_in_telemetry_payload_supertrend` (leak-negative 正控, codex FU-2 + authority-reviewer, NEW). T5.2 testnet order rejected 静默 → `test_real_supertrend_testnet_deploy` (→ OrderDenied telemetry, @integration, NEW). T5 (no-regr) 现有 sandbox lifecycle 退化 → `test_full_lifecycle_sandbox_supertrend` / `test_deploy_code_hash_mismatch_rejected` (✓existing)."* | Plan 08 inherits Plan 06's Track 5/6 test-name contract verbatim |
| Progress-management close-out template | `.claude/rules/progress-management.md` §"完成报告模板" (Chinese section heading is authoritative — do not rename) | *"## 完成报告 (Close-out Report) — 完成日期 / 总 Task 数 / 偏离数 / 验证结果 / 实施 commit 范围 / 契约影响 / 红线守护 / 失败模式覆盖 / 遗留项."* | T6.2 fills the Plan 06 close-out section from this template + adds the C40 red-line satisfaction table |

### plan-to-plan references (Step 1.5)

| plan-id | Status | Product cited | Verification |
|---------|--------|---------------|--------------|
| 06 | Track 1-4 landed (06a squash `306b9e5`); Track 5-6 = this plan | 06a marker at `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-06a-v1.complete.json` (10 DEV entries); §失败模式契约表 T5.x / T6.x rows already list all NEW test names; §red-line gate table — Plan 06's own template | This plan (Plan 08) inherits Plan 06's failure-mode contract and closes it out via T6.2 |
| 07 | Not landed yet (Batch 1 sibling of this plan) | Curation scope decision (keep 06a subset / expand / trim) determines whether T5 e2e covers only supertrend or also new strategies | **START gate**: this plan's T5 e2e coverage locks once Plan 07 curation lands; before that, T5.1 can be **drafted** against the 06a subset but not **executed** until 07 landing signals whether the vendored subset shifts |

> **START gate for Plan 08 execution** = Plan 07 T3 (curation scope) close-out. Coverage policy branches by Plan 07 DP1 outcome (packet-defined `curation scope` decision — a/b/c per `.forge/handoff/2026-07/plan-team-07-08-09-packet.md:80,118`); handoff packet §Batch-1 line 48 states explicitly that Plan 07 curation *can* change Plan 08 T5 e2e coverage strategy — so this is a scope-changing branch, not just a "re-verify toolkit path" branch.

**Post-Plan-07 coverage matrix** (executor selects the matching row at Foundation Scan time based on Plan 07 close-out):

| Plan 07 DP1 outcome | Plan 08 T5 coverage | Additional e2e tests beyond supertrend | Executor action at Foundation Scan |
|--------------------|---------------------|----------------------------------------|-------------------------------------|
| (a) keep 06a subset (no change) | supertrend-only e2e (T5.1 sandbox + T5.2 testnet — as drafted below) | none | Re-verify toolkit path unchanged; proceed with drafted T5.1/T5.2 |
| (b) expand vendoring (e.g., add `shared/hummingbot/` or other subpackages) | supertrend e2e **plus one representative e2e per newly added strategy family** covered by the expanded toolkit (drafter default: extend the failure-mode contract table for each added family; do **not** silently absorb into supertrend tests) | +1 test per added family (e.g., `test_real_hummingbot_strategy_loads_and_deploys_sandbox` if Hummingbot added) | Pause + escalate to CEO / Planning Lead if expansion adds >1 new family (workload > single-session); otherwise draft additional tests in `tests/engines/nautilus/test_real_<family>_e2e_sandbox.py` with the same discipline as T5.1 |
| (c) trim to strict supertrend closure | supertrend-only e2e (same as (a)) | none | Re-verify pruned toolkit path still resolves the vendored `SuperTrendStrategy` import chain; proceed |

If Plan 07 has **not** landed at Plan 08 execution start, START gate is not met — executor blocks at Foundation Scan and escalates. Do not proceed with T5.1 against a moving toolkit substrate.

**Documented scope decision (default = row (a))**: this plan drafts T5.1/T5.2 against the (a) row (supertrend-only). Any (b) row expansion is treated as a Plan 08 scope amendment recorded as a DEV entry before execution begins.

### Current custos state relevant to Plan 08

- 06a squash `306b9e5` landed: vendored toolkit at `src/custos/engines/nautilus/toolkit/` + `strategy_registry_name` post-load registry introspection at `src/custos/engines/nautilus/strategy_loader.py` + `sys.modules` cache idempotency (executor round-trip discovery, DEV-06-06A-STRATEGY-LOADER-SYS-MODULES-CACHE) + `TOOLKIT_PROVENANCE.md` (upstream `fc4ab1d` + subset manifest) + `RiskController` config activated in ps side at `philosophers-stone/trend/supertrend/config.yaml` (CEO DP2 middle-tier: `max_daily_loss=0.05` / `max_drawdown=0.15` / `consecutive_loss_pause=5`).
- Existing sandbox lifecycle test (`tests/test_nt_trading_node_host_integration.py`) proves the `NtTradingNodeHost.deploy(spec, credential)` path works end-to-end with a **fixture-based** strategy path (a self-contained `MinimalSupertrendStrategy`, no `shared/` runtime dependency). Its module docstring explicitly states the avoidance is by design — that avoidance is exactly what T5.1 must reverse.
- `credential_vault` is mode-agnostic on scope enforcement (scout §7 — no testnet-specific branch); T5.2 testnet credential goes through the same decrypt + `trade_no_withdraw` scope-check as live.
- No CI wiring (`.github/` absent). Baseline verification remains `make verify`; T5.2 lands as `@pytest.mark.integration` (network-gated, non-baseline) so `make verify` stays deterministic in environments without testnet connectivity.

---

## Goal

After Plan 08 close-out:

- **Real supertrend end-to-end on sandbox** — custos loads the real ps `SuperTrendStrategy` (not the `MinimalSupertrendStrategy` fixture) via the vendored toolkit substrate, drives it through `NtTradingNodeHost.deploy()` with the Binance sandbox venue config, and asserts G6 gate + `_risk_controller` non-None + telemetry uplink observability (this is the first production-shaped e2e that exercises the entire Plan 06 stack together).
- **Credential leak-negative positive control** landed in the real-strategy e2e path (FU-2 from Plan 06 codex peer review), independently asserting that sentinel `api_key`/`api_secret` values do **not** appear in telemetry payloads, DeploymentStatus fields, or structlog output. Red line 0.1 gets a real-strategy-path anchor, not just a regression on the Plan 03 desensitization processor.
- **Testnet paper→testnet e2e landed or deferred** — real supertrend on Binance testnet (per DP1 CEO decision: real credential vs mock vs defer to a pre-live plan). If testnet network / funds are unavailable, task falls back to partial+manual verification with DEV registration; baseline `make verify` remains green either way.
- **ps sidecar / runner retirement docs landed** — `docs/design/nautilus_host.md` gains a "PS supertrend migration" section that: (i) declares `deploy/nautilus/runner.py` + `deploy/sidecar/` are no longer the primary production entrypoint post-custos; (ii) explicitly does **not** delete ps or crucible code (crucible ecosystem keeps consuming ps sidecar via HTTP + ps Docker images bundle `shared/` for crucible-supervised production containers per scout §4.2); (iii) references the toolkit ↔ G6 code_hash scope decision (DEV-06-TOOLKIT-HASH-SCOPE); (iv) lists arx web sidecar HTTP tech-debt as an independent follow-up.
- **Plan 06 close-out landed** — Plan 06 status → ✅ Completed, `.forge/README.md` index synchronized, Plan 06 completion report + C40 red-line gate satisfaction table filled with real code_coverage / runtime_wire / defer_status entries.

**Red line names (vision) ≠ satisfaction declarations (reality, lesson C40)**: Plan 08 delivers the **production acceptance gate** for red lines 0.1 (credential leak-negative in real-strategy e2e) and 0.2 (G6 gate exercised against real supertrend via vendored toolkit code_hash) at code_coverage layer with matching runtime_wire; red line 0.3 remains the per-strategy layer already delivered by 06a (per-runner cap layer belongs to Plan 04); red line 0.4 remains covered by 06a's vendored-toolkit float-money-math grep gate (`test_vendored_toolkit_no_new_float_money_math`).

---

## Architecture

Plan 08 is verification-heavy and near-zero source-change: two new e2e test files under `tests/engines/nautilus/`, one docs section addition to `docs/design/nautilus_host.md`, and the close-out mechanics on Plan 06 + `.forge/README.md`.

```
T5.1 sandbox path (in-process, no network) :
    _spec()/_credential()/_parked_run() (reused from existing lifecycle test)
    → strategy_path = <resolves via vendored toolkit — real ps SuperTrendStrategy>
    → NtTradingNodeHost.deploy(spec, credential)
    → assert host._active_nodes["int-1"] → real SuperTrendStrategy instance
    → assert strategy._risk_controller non-None (Plan 06 06a Track 2 activation)
    → assert G6 gate passed (dir-hash layer 3 over strategy dir)
    → assert telemetry uplink event registered (Plan 03 desensitized path)
    → assert sentinel credential NOT in telemetry payload / DeploymentStatus / structlog (FU-2)

T5.2 testnet path (network, @integration, DP1-conditional):
    trading_mode = "testnet"
    → venue_binance.build_exec_client_config_testnet(spec, credential)
    → BinanceEnvironment.TESTNET reached
    → real Binance testnet acknowledgement or OrderDenied telemetry surfaces
    → credential_vault path identical to live (scope check mode-agnostic)

T6.1 docs update:
    → docs/design/nautilus_host.md gains "PS supertrend migration" section
    → declares ps sidecar / runner retirement (docs-only, no delete)
    → references DEV-06-TOOLKIT-HASH-SCOPE
    → lists arx web sidecar HTTP follow-up (DP2)

T6.2 close-out:
    → Plan 06 Status ⏳ → ✅ Completed
    → Plan 06 §完成报告 filled per progress-management.md template
    → C40 red-line gate satisfaction table filled (real values)
    → .forge/README.md Plan 06 row Status → ✅
    → this Plan 08 Status ⏳ → ✅ Completed as well
```

**T5.1 vs existing sandbox lifecycle test** — the existing `test_full_lifecycle_sandbox_supertrend` uses a fixture (`MinimalSupertrendStrategy`) and deliberately avoids `shared/`. T5.1 reuses the same `_spec()/_credential()/_parked_run()` scaffolding but points `spec["strategy_path"]` at the real ps `SuperTrendStrategy` file **inside the vendored toolkit** — which is only possible after 06a landed the vendored `toolkit/shared/` closure and the `sys.path` bootstrap. The existing test remains untouched and continues as no-regression baseline.

---

## Key design decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Reuse existing `_spec()/_credential()/_parked_run()` scaffolding, or write fresh helpers for T5.1? | **Reuse and adapt** — extract the shared helpers into `tests/engines/nautilus/conftest.py` if T5.1 needs them, but keep the existing lifecycle test file untouched | Duplication would violate lesson-#25-style code hygiene; extracting to a conftest keeps both test modules consuming the same fixture surface, preserves baseline regression coverage, and matches the "deep module, single source" spirit of coding-taste.md §一 |
| T5.1 target: which `SuperTrendStrategy` file does `strategy_path` point at? | The **real** ps `trend/supertrend/refinement/nautilus/strategy.py` **resolved through the vendored toolkit substrate** (i.e., the loader's `sys.path` bootstrap makes `from shared...` resolve, and the strategy file itself lives at whatever custos-side path a real deployment would use — either a temp copy of `philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py` or a pre-staged fixture that mirrors it byte-for-byte) | The scout report is explicit: T5.1 must swap the fixture-based scaffolding for vendored-toolkit loading. Whether the strategy file itself is copied into `tests/fixtures/` or referenced directly from ps needs an executor-side Foundation Scan on ps availability at test time — recorded as an intra-plan open thread (DEV-08-STRATEGY-SOURCE-PATH-TBD) |
| T5.2 credential source | **CEO decision required — DP1**; drafter recommends option (a) real testnet credential in vault | Options: (a) real Binance testnet key/secret via `credential_vault` (real network, real routing evidence, matches mandatory-rules §5 "sandbox key non-real"); (b) mock testnet (asserts wire intent only, no network — cheaper but weaker acceptance signal); (c) defer T5.2 to a pre-live plan (Plan 08 lands only T5.1 + T6.1 + T6.2, T5.2 marked deferred) |
| T5.1 fault injection scope | **CEO decision required — DP3**; drafter recommends option (a) golden path only | The `test_real_supertrend_loads_and_deploys_sandbox` is already a substantial e2e; adding chaos (NATS down + venue disconnect during supertrend running with safe-halt validation) doubles the test surface. Option (a) golden path only keeps Plan 08 tight; option (b) adds chaos leveraging Plan 04 infrastructure. If Plan 04 has not landed the chaos harness by Plan 08 execution time, (b) becomes infeasible regardless of preference |
| arx web sidecar HTTP migration scope | **CEO decision required — DP2**; drafter recommends option (a) independent arx-side follow-up | Options: (a) independent arx-side follow-up plan (Plan 08 T6.1 documents the debt, arx team schedules its own plan; drafter recommendation — cross-repo coordination overhead too high for a Plan 08 blocker); (b) upgrade to Plan 08 blocker (custos + ps + arx three-repo coordination); (c) skip entirely (crucible ecosystem auto-maintains — but the arx web hits crucible's sidecar-proxied endpoint, orthogonal to crucible's own maintenance) |
| Close-out order: Plan 06 flip before or after this Plan 08 flip? | **Plan 06 first, then Plan 08** in T6.2 | Plan 06 is the parent whose Track 5-6 this plan closes; Plan 06 close-out timestamp precedes Plan 08's own close-out timestamp for audit clarity |
| T6.1 docs: separate section or inline? | New top-level section "PS supertrend migration" in `docs/design/nautilus_host.md` | scout §8 confirms 0 mentions today — no risk of duplicate content. A dedicated section is more discoverable than inline additions scattered across existing sections |

---

## File Inventory

> Status legend: **create** / **modify** / **delete**. `Baseline (test -f)` = executor Foundation Scan pre-Task expectation. All paths anchored to post-06a-squash state (`306b9e5`).

### A. custos source (create/modify — minimal; T5 does not require source-code changes if the vendored toolkit path already resolves)

| File | Status | Baseline (test -f) | Track/Task | Notes |
|------|--------|--------------------|-----------|-------|
| `tests/engines/nautilus/conftest.py` | create (if needed) | absent | T5.1 | Optional — only if T5.1 needs to share `_spec()/_credential()/_parked_run()` helpers with the existing `test_nt_trading_node_host_integration.py` module. If executor determines duplication is cleaner given scope, skip and add a DEV note |

### B. custos tests (create — the primary deliverable)

| File | Status | Baseline (test -f) | Track/Task | Notes |
|------|--------|--------------------|-----------|-------|
| `tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py` | create | absent | T5.1 | Houses `test_real_supertrend_loads_and_deploys_sandbox` + `test_credential_not_in_telemetry_payload_supertrend` (FU-2 leak-negative positive control) |
| `tests/engines/nautilus/test_real_supertrend_e2e_testnet.py` | create (conditional on DP1) | absent | T5.2 | Houses `test_real_supertrend_testnet_deploy` marked `@pytest.mark.integration` (network-gated, out of baseline `make verify`) |

### C. Docs (modify)

| File | Status | Baseline (test -f) | Track/Task | Notes |
|------|--------|--------------------|-----------|-------|
| `docs/design/nautilus_host.md` | modify | 129 lines (scout §8) | T6.1 | Add new section "PS supertrend migration" — 5 subsections per §Architecture-T6.1: (i) integration path via vendored toolkit; (ii) ps sidecar / runner retirement declaration (docs-only, no delete); (iii) crucible + Docker-image `shared/` bundling as second production consumer (per scout §4.2 finding); (iv) toolkit ↔ G6 code_hash scope reference (DEV-06-TOOLKIT-HASH-SCOPE); (v) arx web sidecar HTTP tech-debt as arx-side follow-up (DP2) |

### D. Close-out (modify)

| File | Status | Baseline (test -f) | Track/Task | Notes |
|------|--------|--------------------|-----------|-------|
| `.forge/plans/2026-07/06-ps-supertrend-migration.md` | modify | exists | T6.2 | Header Status ⏳ → ✅ Completed + Completed date; §完成报告 filled per progress-management.md template with real Task counts / DEV counts / commit ranges (custos side + ps side); C40 red-line gate satisfaction table filled with real code_coverage / runtime_wire / defer_status |
| `.forge/README.md` | modify | exists | T6.2 | Plan 06 row Status ⏳ → ✅ + Plan 08 row (add) Status ⏳ → ✅ after both close |
| `.forge/plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md` (this file) | modify | this file | T6.2 | Own Status ⏳ → ✅ + Completed date + §完成报告 |

> **Language Policy** (`CLAUDE.md` §Language Policy + `.claude/rules/code-style.md` §语言约束): all test file identifiers, function names, docstrings, log strings, commit messages, and DEV entry IDs land **English**. Chinese permitted only in this plan's argumentative prose (if a drafter judges it clearer) and in AI ↔ user conversation. The pre-commit hook `check-code-english.py` (5c01cdb) will reject new-line CJK characters at commit time.

---

## Tasks

> **TDD rhythm**: each Task writes the failing assertion first (red) → minimal implementation → green → `make verify` green (custos-side atomicity) → commit. Source code comments must not contain plan/task/lesson tracking numbers (lesson #15); use semantic references (e.g. "post-06a real supertrend acceptance") rather than "Plan 08 T5.1". **Foundation Scan pre-Task 1** (lesson #14/#30/#33): executor confirms Plan 07 T3 curation scope landed + `test -f` sweep on File Inventory + grep `strategy_registry_name` in `src/custos/engines/nautilus/strategy_loader.py` to confirm the 06a introspection surface is stable + grep vendored toolkit `toolkit/shared/nautilus/` for the `SuperTrendStrategy` symbol path.

### Track 5 — real supertrend e2e (sandbox + testnet)

#### Task T5.1: sandbox e2e — real supertrend via vendored toolkit + credential leak-negative

**Files**: `tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py` (create) [+ optional `tests/engines/nautilus/conftest.py` (create) if fixture sharing warranted]

- **Pre-Foundation-Scan (executor)**:
  - Confirm Plan 07 T3 curation scope has closed and the vendored toolkit subset covers the supertrend closure (default: 06a subset unchanged; if Plan 07 expands or trims, executor adjusts the strategy resolution path).
  - `grep -rn "def test_real_supertrend_loads_and_deploys_sandbox\|def test_credential_not_in_telemetry_payload_supertrend" tests/` → expect 0 hits (per scout §5 verification, still 0 as of this drafting; executor re-verifies to close the timing gap between plan drafting and execution).
  - Grep `tests/test_nt_trading_node_host_integration.py:33-56` to confirm `_spec()/_credential()/_parked_run()` still exist unchanged (baseline signature).
  - Resolve the real supertrend strategy file location. Options — see DEV-08-STRATEGY-SOURCE-PATH-TBD below for full analysis:
    - **(iii) Permanent in-repo fixture mirror** at `tests/fixtures/real_supertrend/` — **drafter recommendation for independent-clone reproducibility**. Copy the ps `SuperTrendStrategy` file + every companion config file it loads (`strategy.py` + any adjacent `config.yaml` / `__init__.py` needed at import time) into custos permanently. Fully self-contained: a fresh `git clone custos` + `uv sync --extra dev --extra nt-runtime` + `make verify-nt` runs T5.1 without any ps repo checkout. Trades storage duplication (~few KB per strategy file) for offline reproducibility.
    - **(i) `tmp_path` copy sourced from ps repo checkout** — NOT independent-clone reproducible: still requires ps repo present on disk at test time (the copy source is `philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py`). If chosen, T5.1 must **skip with a clear `pytest.skip("ps repo checkout absent at $PS_ROOT")` when the source path is missing**, and this self-contained-gap is documented as an accepted limitation in the plan close-out + `docs/design/nautilus_host.md` T6.1 section.
    - **(ii) Direct ps repo path (`strategy_path` points into ps checkout)** — same reproducibility gap as (i); documented equivalently.
- **Step 1 (red)**: `test -f tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py` → absent. Write two failing tests:
  1. `test_real_supertrend_loads_and_deploys_sandbox(monkeypatch, tmp_path)` — stages the real ps `SuperTrendStrategy` file at a resolvable path, monkeypatches `TradingNode.run_async` with `_parked_run`, calls `host.deploy(spec, credential)` with `strategy_registry_name="supertrend"`, asserts:
     - `container_id == "int-1"`
     - `host._active_nodes["int-1"]` yields a `SuperTrendStrategy` instance whose class is the real ps one (not `MinimalSupertrendStrategy`)
     - `strategy._risk_controller is not None` (Plan 06 06a Track 2 activation — proves the config-driven RiskController survives the real vendored-toolkit load path)
     - G6 gate layer 3 (dir-hash) accepted the strategy_path
     - `strategy.strategy_registry_name == "supertrend"` matches the registry lookup (Plan 06 06a T1.2 post-load introspection surface)
     - Teardown: cancel the parked task + `host._active_nodes.pop("int-1", None)` cleanly (existing lifecycle test pattern)
  2. `test_credential_not_in_telemetry_payload_supertrend(monkeypatch, tmp_path, capsys)` — FU-2 leak-negative positive control:
     - Uses sentinel credential values that are impossible to occur naturally (e.g. `api_key="SENTINEL-KEY-DO-NOT-LEAK-A1B2C3"`, `api_secret="SENTINEL-SECRET-DO-NOT-LEAK-X9Y8Z7"`)
     - Drives the same deploy flow as test 1
     - Asserts sentinel strings do **not** appear in: (a) any telemetry event payload emitted during deploy (capture via monkeypatched or in-memory telemetry sink), (b) `DeploymentStatus` fields, (c) `structlog` output captured via `capsys` or a structlog processor tap
     - Reason (lesson C40): red line 0.1 code_coverage layer needs a real-strategy-path anchor, not just the Plan 03 desensitization processor regression — real-strategy telemetry paths could bypass the processor if any new sink is added without hooking through the shared processor
- **Step 2 (verify red)**: `uv run pytest tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py -v` → both tests fail (T5.1 test module absent; assertions unmet).
- **Step 3 (green)**: implement the missing pieces to turn both tests green. Expected implementation surface — **zero source-code changes required** if Plan 06 06a landed cleanly: the vendored toolkit + `sys.path` bootstrap + `_instantiate_strategy` factory-probe + `strategy_registry_name` post-load introspection are already in place. If a green requires source changes, the executor pauses and escalates (potential 06a defect surfaced by T5.1 — record as DEV-08-06A-GAP-<N>).
- **Step 4 (verify green)**: `make verify` (fmt-check + lint + `pytest`) all green.
- **Failure modes covered** (lesson #17):
  - Real supertrend load path breaks under vendored toolkit → test 1 fails immediately at deploy call
  - Vendored toolkit closure incomplete (any missing transitive `shared/` subpackage) → `ModuleNotFoundError` at strategy import → test 1 red
  - Registry post-load introspection breaks with real strategy (name mismatch or lookup missed) → test 1 explicit assert fails
  - `_risk_controller` becomes None on real strategy path (config activation regression) → test 1 explicit assert fails
  - Credential sentinel leaks into any observable path → test 2 fails at whichever sink leaked; leak-negative discipline forces future sinks to hook the desensitization processor
- **Step 5**: commit `test(custos): real supertrend sandbox e2e via vendored toolkit + credential leak-negative`.

#### Task T5.2: testnet paper→testnet e2e (production acceptance point, DP1-conditional)

**Files**: `tests/engines/nautilus/test_real_supertrend_e2e_testnet.py` (create)

- **DP1 gate**: this task is executed only if CEO selects DP1 option (a) real testnet credential or (b) mock testnet. If CEO selects (c) defer, T5.2 is skipped and recorded as DEV-08-T5.2-DEFERRED with rationale + which future plan picks it up.
- **Pre-Foundation-Scan (executor, DP1 option a specifically)**:
  - Confirm Binance testnet credential is provisioned in the local `credential_vault` under the same sops+age scheme as live (mandatory-rules §5 — sandbox testnet credential, not a real-money key).
  - Confirm `nt-runtime` extra installed and Python interpreter is 3.12+ (tech-stack.md §可选依赖 marker).
  - Confirm testnet network reachability from the execution environment using a **connector-aware probe** — do not hard-code a URL, because the correct testnet endpoint depends on which NT `BinanceExecClientConfig` product family the deploy targets (futures vs spot; only futures currently uses `testnet.binancefuture.com`, spot testnet uses a different host). The executor derives the probe endpoint at Foundation-Scan time from the NT Binance adapter itself: (a) inspect `nautilus_trader.adapters.binance` for the `BinanceEnvironment.TESTNET` base-URL constant (or the equivalent per-account-type endpoint attribute — futures uses `futures.testnet_url`, spot uses `spot.testnet_url` in NT ≥1.227); (b) hit that adapter-derived URL's `/ping` (or the connector's own idempotent health endpoint) via `httpx` before the test runs. If the endpoint cannot be derived from the installed NT version or if the network probe fails, DP1 option (a) auto-degrades to option (b) mock or option (c) defer — recorded as DEV. Document futures-vs-spot behaviour in the executor's Foundation-Scan output so future readers can retrace the reachability decision. Spot/futures branching rule: Plan 08 targets futures by default (supertrend on Binance USD-M futures per Plan 06 06a `refinement/nautilus` conventions); spot support is out of scope for this plan.
- **Step 1 (red)**: `test -f tests/engines/nautilus/test_real_supertrend_e2e_testnet.py` → absent. Write `test_real_supertrend_testnet_deploy` marked `@pytest.mark.integration` (per `pyproject.toml` marker registry; already excluded from baseline `make verify`). Test drives `host.deploy(spec_with_trading_mode_testnet, testnet_credential)`, asserts:
  - Real BinanceEnvironment.TESTNET routing (via `venue_binance.build_exec_client_config_testnet`)
  - Non-empty acknowledgement telemetry (order submission acknowledged by testnet) OR structured `OrderDenied` telemetry if testnet rejects for any documented reason (silent order rejection would be a red-line-0.3-adjacent observability defect)
  - Credential never appears in any observable path (repeat the FU-2 sentinel discipline from T5.1 in the testnet context — same rationale, red line 0.1 code_coverage across both modes)
- **Step 2 (verify red)**: `uv run pytest tests/engines/nautilus/test_real_supertrend_e2e_testnet.py -v -m integration` → test fails (module absent or assertions unmet).
- **Step 3 (green)**: real testnet run completes. If the testnet run fails for infrastructure reasons (network flake, testnet outage, funds exhaustion), the executor may fall back to **partial+manual verification**: run the test manually against testnet, capture the passing output as evidence in a DEV entry (DEV-08-T5.2-MANUAL-VERIFICATION), and mark T5.2 as `⚠️ Manual` in progress tracking rather than fully ✅. This fallback is a DP1 CEO-authorized pathway per Plan 06 T5.2 precedent (`06-ps-supertrend-migration.md:287-289`).
- **Step 4 (verify green)**: baseline `make verify` remains green (T5.2 has the `@integration` marker so it does not run in baseline); testnet run passes or is manually verified.
- **Failure modes covered** (lesson #17):
  - Testnet order rejected silently (no telemetry emitted) → assertion on `OrderDenied` telemetry catches it (red line 0.3 lesson #21 zero-silent)
  - Testnet routing mismatched (e.g. lands on live env by accident) → assertion on `BinanceEnvironment.TESTNET` explicit check; if failed, this is a red-line-0.2-adjacent boundary defect
  - Credential leaks in testnet path but not sandbox → repeat sentinel FU-2 assertion in testnet context
  - Paper→testnet transition breaks (a spec that worked in sandbox mode fails in testnet mode without explanation) → the same spec fixture is used with only `trading_mode` swapped, so any transition-only regression surfaces
- **Step 5**: commit `test(custos): testnet e2e for real supertrend (paper→testnet acceptance)`.

### Track 6 — sidecar retirement docs + Plan 06 close-out

#### Task T6.1: ps sidecar / runner retirement declaration in `docs/design/nautilus_host.md`

**Files**: `docs/design/nautilus_host.md` (modify)

- **Pre-Foundation-Scan**: `grep -n "sidecar\|supertrend migration\|ps 侧\|philosophers" docs/design/nautilus_host.md` → expect 0 hits (scout §8 baseline).
- **Step 1 (red)**: the section absent — Step 1 red confirmed by grep baseline.
- **Step 3 (green)**: append a top-level section "PS supertrend migration" with the following subsections:
  1. **Integration path** — real ps `SuperTrendStrategy` loads on custos via the vendored toolkit substrate + `strategy_registry_name` post-load introspection. Reference `src/custos/engines/nautilus/strategy_loader.py` and `src/custos/engines/nautilus/toolkit/`.
  2. **ps sidecar / runner retirement declaration** — `philosophers-stone/deploy/nautilus/runner.py` + `philosophers-stone/deploy/sidecar/` are no longer the primary production entrypoint once custos takes over supertrend deployment. Custos does **not** delete this ps code. The ps repo may retain the sidecar / runner for team research use (e.g. `deploy/nautilus/main.py` for local backtesting). No coordinated cross-repo delete is scheduled.
  3. **Second production consumer of ps `shared/`** — `the-crucible` ecosystem continues to consume ps sidecar via HTTP (`crucible_engine/supervisor.py` uses `httpx.AsyncClient` to `sidecar_url`, scout §4.2; 25 sidecar-related files across `crucible_engine/`). Additionally, `philosophers-stone/deploy/nautilus/Dockerfile` and `philosophers-stone/deploy/hummingbot/Dockerfile.image` **bundle ps `shared/` directly into the production runtime container images that crucible supervises** — this makes ps `shared/` a Docker-image-level production dependency independent of custos's own vendored toolkit copy. Any coordinated shrink of ps `shared/` must preserve the Docker-buildable closure as long as crucible production containers are live (documented here so future contributors do not remove ps `shared/` under the mistaken belief that custos's vendored copy replaces it).
  4. **Toolkit ↔ G6 code_hash scope** — reference `DEV-06-TOOLKIT-HASH-SCOPE` (Plan 06 CEO DP4 landed): vendored toolkit is covered by custos supply-chain integrity (`TOOLKIT_PROVENANCE.md` + custos release signing), not by per-deploy G6 code_hash layer 3. Layer 3 covers the strategy directory only. Multi-layer defense per lesson #22.
  5. **arx web sidecar HTTP tech-debt** — `arx/web/lib/hooks/useApi.ts:207-217` documents `StrategyPosition` fetched via crucible-relayed sidecar real-time position proxy (7 real source files in arx `web/` per scout §4.3, not 9 as some earlier drafts indicated — the extra hits are `package-lock.json` noise). This is an arx-side migration to NATS-only in a future arx-side follow-up plan (DP2). Custos does not block on it.
- **Post-write verification** (lesson #13 grep self-verification): `grep -c "PS supertrend migration" docs/design/nautilus_host.md` → 1 (section landed exactly once) + `grep -c "ps sidecar\|runner retirement\|Docker-image-level" docs/design/nautilus_host.md` → ≥ 3 (each subsection anchor present).
- **Failure modes covered** (docs-only, structural):
  - Section duplicates existing content → grep verification catches (only 0 baseline expected)
  - Cross-reference to `DEV-06-TOOLKIT-HASH-SCOPE` unresolved → executor confirms Plan 06 marker retention
  - arx follow-up mislabelled as blocker → DP2 CEO decision recorded before commit
- **Step 5**: commit `docs(custos): declare ps sidecar/runner retirement + supertrend migration section in nautilus_host`.

#### Task T6.2: Plan 06 + Plan 08 close-out — **mandatory final task**

**Files**: `.forge/plans/2026-07/06-ps-supertrend-migration.md` (modify) + `.forge/README.md` (modify) + this file (modify)

**Actions** (Plan 06 first, then Plan 08 — parent-child order):

1. **Plan 06 close-out** (Chinese section headings in parens are authoritative — the executor writes them verbatim into the Plan 06 file per `.claude/rules/progress-management.md` §"完成报告模板"):
   - Header: `Status: ✅ Completed` + `Completed: YYYY-MM-DD`
   - Fill §"完成报告" (per progress-management.md template):
     - Completion date (完成日期)
     - Total task count (总 Task 数): 12 (from Plan 06 progress tracking table)
     - Deviation count (偏离数): sum of DEV-06-* entries + Plan 08 DEV-08-* entries that closed Track 5-6 (cross-reference)
     - Verification result (验证结果): all passed (全部通过) or partial (部分通过) with DP1 T5.2 partial/manual outcome recorded
     - Implementation commit range (实施 commit 范围): custos `306b9e5..<T6.2 commit>` + ps side range (from 06a Track 2)
     - Contract impact (契约影响): `docs/domain.md` + `docs/design/nautilus_host.md` + `docs/engines/nautilus.md` + ps `config.yaml`
     - Red-line guardianship (红线守护): fill the C40 red-line satisfaction table with real code_coverage / runtime_wire / defer_status values — 0.1 code_coverage now references T5.1 `test_credential_not_in_telemetry_payload_supertrend` real-strategy-path anchor (DP1-conditional wording: none if T5.2 landed, otherwise testnet-mode credential-path coverage deferred to the successor plan named in DEV-08-T5.2-DEFERRED); 0.2 code_coverage references T5.1 real supertrend dir-hash acceptance; 0.3 per-strategy layer references ps side `test_supertrend_risk_controller_blocks_on_drawdown` (unchanged from 06a landing) + per-runner cap still deferred to Plan 04; 0.4 references the 06a `test_vendored_toolkit_no_new_float_money_math` grep gate
     - Failure-mode coverage (失败模式覆盖): enumerate all NEW test functions actually created (T5.1 + T5.2 + 06a NEW tests) — every name grep-verified per lesson #25 discipline
     - Remaining items (遗留项): per-runner cap (Plan 04) + ps `shared/` curation + convergence discipline (Plan 07, if not landed at close-out time) + arx web sidecar HTTP migration (arx-side follow-up) + T5.2 outcome status (green / partial / deferred) + chaos coverage successor plan if DP3 = C
2. **`.forge/README.md`**:
   - Plan 06 row Status ⏳ → ✅ Completed + Completed date
   - Add Plan 08 row (Status ✅ Completed + Completed date + Depends on / Blocks columns)
   - Update the execution-order (§"执行顺序建议") note about Plan 06 closure
3. **Plan 08 (this file) close-out**:
   - Header Status ⏳ → ✅ Completed + Completed date
   - Fill the §"Close-out report" below with the same template (Plan 08-specific metrics — Task count 4, DEV entries specific to Plan 08)
4. **Cross-repo commit discipline** (mandatory-rules §6): all commits use `git add <specific-file>`, never `git add .` or `-A`. Commit scope=`custos`. Commit message format: `docs(custos): mark plan 06 as completed + close-out report` + separate commit `docs(custos): mark plan 08 as completed`.
5. **Post-commit verification**:
   - `grep -c "^> \*\*Status\*\*: ✅" .forge/plans/2026-07/06-ps-supertrend-migration.md` → 1
   - `grep -c "^> \*\*Status\*\*: ✅" .forge/plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md` → 1
   - `.forge/README.md` Plan 06 row visually flipped to ✅ (grep `Plan 06.*✅`)
- **Step 5**: two commits as described in action 4 above.

---

## Verification

- [ ] `make verify` (fmt-check + lint + pytest baseline) — PASS at every custos Task boundary + before close-out commit
- [ ] `make verify-nt` (adds `nt-runtime` extra tests) — PASS after T5.1 (T5.1 depends on real NT machinery via vendored toolkit)
- [ ] T5.1 sandbox e2e — `pytest tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py -v` fully green (both `test_real_supertrend_loads_and_deploys_sandbox` and `test_credential_not_in_telemetry_payload_supertrend`)
- [ ] T5.2 testnet e2e — `pytest tests/engines/nautilus/test_real_supertrend_e2e_testnet.py -v -m integration` fully green OR partial+manual verification recorded via DEV entry (DP1-conditional)
- [ ] Non-custodial 4 red-lines grep gate — all 4 grep patterns in `.claude/rules/verification.md` §Non-Custodial 红线专项检查 return 0 hits after Plan 08 landing (including the new e2e test files and the new docs section)
- [ ] Contract table NEW test names all grep-verified extant in `tests/` (lesson #25) at close-out time — `grep -rn "def test_real_supertrend_loads_and_deploys_sandbox\|def test_credential_not_in_telemetry_payload_supertrend\|def test_real_supertrend_testnet_deploy" tests/` returns hit counts matching declared status (either 3 hits if T5.2 landed, or 2 hits + T5.2 DEV-deferred registered)
- [ ] `docs/design/nautilus_host.md` "PS supertrend migration" section lands with all 5 subsections (grep verification at close-out)
- [ ] Plan 06 close-out — Status ✅, §"完成报告" (authoritative Chinese heading in the Plan 06 file) filled, C40 red-line satisfaction table filled with real values (no placeholder text)
- [ ] `.forge/README.md` Plan 06 + Plan 08 rows updated to ✅
- [ ] No plan/task/lesson tracking numbers in source-code comments (lesson #15) **scoped to files created or modified by Plan 08** — pre-existing `src/`/`tests/` pollution (e.g., `src/custos/cli/main.py:46` `# Plan 06 —`, `toolkit/TOOLKIT_PROVENANCE.md:22,63`, `tests/test_deployment_reconciler.py:3`, `tests/test_enrollment.py:126`, various `lesson #21` / `lesson #25` markers) is outside Plan 08 scope and gets a follow-up cleanup plan (candidate: Plan 09-adjacent or a dedicated tracking-number-hygiene plan). Plan 08 verification: `git diff --name-only <plan-08-base-commit>..HEAD -- 'tests/**/*.py' 'src/**/*.py' 'docs/**/*.md' | xargs grep -nE "Plan 08\|Plan 06\|T5\.1\|T5\.2\|lesson #" 2>/dev/null` returns 0 hits (the grep runs only against Plan 08's own new/modified files, not the whole repo)
- [ ] Cross-repo commit discipline (mandatory-rules §6) — all commits use `git add <specific-file>`; git status --short reviewed before each commit (lesson #27)
- [ ] Language Policy hook (5c01cdb) passes on all new files (no new CJK in source per hook enforcement)

---

## Progress

| Task | Track | Status | Completed | Notes |
|------|-------|--------|-----------|-------|
| T5.1 sandbox e2e (real supertrend + credential leak-negative) | 5 | 🔲 | | Reuses `_spec()/_credential()/_parked_run()` scaffolding; swaps to vendored toolkit path; DP3 golden path (or +chaos) |
| T5.2 testnet paper→testnet e2e | 5 | 🔲 | | DP1-conditional; `@integration` marker; partial+manual verification fallback authorized |
| T6.1 ps sidecar / runner retirement docs | 6 | 🔲 | | `docs/design/nautilus_host.md` gains 5-subsection "PS supertrend migration" section; DP2 arx follow-up scope |
| T6.2 Plan 06 + Plan 08 close-out | 6 | 🔲 | | Mandatory final task; parent-child order (Plan 06 first) |

**Slice guidance (multi_session_scope=false)**: single session executor can complete all 4 tasks. Only DP1 T5.2 introduces session-boundary risk (testnet network dependency); the partial+manual fallback path avoids forcing a session split. If executor discovers Plan 07 curation has not landed by execution time (START gate not met), the plan blocks at Foundation Scan and escalates to CEO / Planning Lead — do not proceed with T5.1 against a stale toolkit substrate.

---

## Failure-mode coverage contract table (lesson #17 + #25)

> **Status column**: ✓existing = grep-verified extant in `tests/` (executor re-verifies at close-out per lesson #25); NEW = created by this plan. Independent scout §5 verification 2026-07-09 confirmed all NEW names below are 0-hits in the custos repo, ruling out fabrication.

| Track | Failure scenario | Covering test | Status |
|-------|------------------|---------------|--------|
| T5.1 | Real ps supertrend fails to load via vendored toolkit substrate | `test_real_supertrend_loads_and_deploys_sandbox` | NEW |
| T5.1 | `_risk_controller` becomes None on real strategy path (regression on 06a Track 2 config activation) | `test_real_supertrend_loads_and_deploys_sandbox` (explicit non-None assertion) | NEW |
| T5.1 | G6 gate dir-hash rejects real supertrend directory (regression on 06a Track 3 vendored toolkit closure) | `test_real_supertrend_loads_and_deploys_sandbox` (explicit gate acceptance assertion) | NEW |
| T5.1 | Credential leaks into telemetry / DeploymentStatus / structlog in the real-strategy path (red-line 0.1, FU-2 leak-negative positive control) | `test_credential_not_in_telemetry_payload_supertrend` | NEW |
| T5.1 | `strategy_registry_name` post-load introspection breaks on the real supertrend registry entry (regression on 06a Track 1 T1.2) | `test_real_supertrend_loads_and_deploys_sandbox` (explicit registry_name assertion) | NEW |
| T5.2 | Testnet order silently rejected (red-line 0.3 zero-silent, lesson #21) | `test_real_supertrend_testnet_deploy` (asserts `OrderDenied` telemetry surfaces on rejection) | NEW (conditional on DP1) |
| T5.2 | Testnet routing lands on live environment by accident (red-line 0.2 boundary defect) | `test_real_supertrend_testnet_deploy` (asserts `BinanceEnvironment.TESTNET` explicit) | NEW (conditional on DP1) |
| T5.2 | Credential leaks in testnet path but not sandbox (red-line 0.1 cross-mode discipline) | `test_real_supertrend_testnet_deploy` (repeats sentinel FU-2 discipline in testnet context) | NEW (conditional on DP1) |
| T5 (no-regression) | Existing sandbox lifecycle with fixture strategy degrades | `test_full_lifecycle_sandbox_supertrend` — `tests/test_nt_trading_node_host_integration.py:60` (existing, unchanged) | ✓existing |
| T5 (no-regression) | `nt-runtime` extra fails fast when absent | `test_deploy_missing_nt_extra_fails_fast` — `tests/test_nt_trading_node_host_integration.py:91` (existing, unchanged) | ✓existing |
| T5 (no-regression) | Code hash mismatch rejected | `test_deploy_code_hash_mismatch_rejected` — `tests/test_nt_trading_node_host_integration.py:99` (existing, unchanged) | ✓existing |
| T6.1 | Docs section duplicates or misses subsection anchor | `grep -c "PS supertrend migration\|ps sidecar\|Docker-image-level" docs/design/nautilus_host.md` post-commit self-verification (lesson #13) | grep-gate |
| T6.2 | Plan 06 close-out C40 red-line table left with placeholder text | executor verification checklist enforces real values | manual review |

> **NEW test grep verification protocol at close-out (lesson #25)**: executor runs `grep -rn "def test_real_supertrend_loads_and_deploys_sandbox\|def test_credential_not_in_telemetry_payload_supertrend\|def test_real_supertrend_testnet_deploy" tests/` and confirms count matches declared status (3 if T5.2 landed, 2 if T5.2 DP1-deferred). Any mismatch blocks close-out.

---

## Red-line gate satisfaction table (lesson C40)

> **Red line names (vision) ≠ satisfaction declarations (reality)**: separate code_coverage (test coverage of the logic) from runtime_wire (composition root truly wires the guard) from defer_status (which layer is deferred to a follow-up plan).

| Red line | Target satisfaction | code_coverage | runtime_wire | defer_status |
|----------|---------------------|---------------|--------------|--------------|
| 0.1 Key/KEK not out of process | Real-strategy telemetry / status / structlog paths do not leak sentinel credential | T5.1 `test_credential_not_in_telemetry_payload_supertrend` — real-strategy sandbox-path anchor, not just Plan 03 processor regression (always lands). T5.2 sentinel FU-2 repeat in testnet context — **lands only if DP1 = A or B (T5.2 executed)**; if DP1 = C (T5.2 deferred), the testnet-mode credential-path leak-negative anchor is **not delivered by Plan 08** | credential_vault decrypt → NT client only path preserved (scout §7 confirms `_verify_permission_scope` unconditional at `credential_vault.py:84-97`); Plan 03 desensitization processor still wired at telemetry sink | **conditional on DP1 outcome**: DP1 = A (real testnet) or B (mock testnet) → `defer_status = none` (sandbox + testnet code_coverage both delivered by Plan 08); DP1 = C (T5.2 deferred) → `defer_status = testnet-mode credential-path coverage deferred to <successor plan named in DEV-08-T5.2-DEFERRED>`. Executor fills the actual defer_status wording at Plan 06 close-out based on the ratified DP1 decision |
| 0.2 G6 gate not bypassed | Strategy dir code_hash gate accepts real supertrend directory (dir-hash layer 3); vendored toolkit stays in supply-chain integrity layer (provenance + release signing) not per-deploy hash | T5.1 explicit gate acceptance assertion on real supertrend directory | G6 4-layer gate composition root unchanged (Plan 05 `core/g6_gate.py`); toolkit stays in `TOOLKIT_PROVENANCE.md` supply-chain layer per DEV-06-TOOLKIT-HASH-SCOPE (Plan 06 CEO DP4) | none — DP4 already resolved; multi-layer defense (lesson #22) intact |
| 0.3 Disconnect ≠ stop | Per-strategy layer (RiskController drawdown breaker) delivered by 06a Track 2 (ps side) — no additional runtime_wire in this plan | ps side `test_supertrend_risk_controller_blocks_on_drawdown` (delivered by 06a, referenced here for close-out completeness) | `_risk_controller` non-None at runtime confirmed by T5.1 explicit assertion (regression-catches any Plan 06 Track 2 regression) | per-runner cap layer **still deferred to Plan 04** (three-layer full satisfaction requires Plan 04 landing) |
| 0.4 Money math Decimal | Vendored toolkit closure has no new float money math paths (audit delivered by 06a Track 3 grep gate) | 06a `test_vendored_toolkit_no_new_float_money_math` (referenced for close-out completeness; unchanged by this plan) | vendored toolkit paths preserved; T5.1 exercises the RiskController Decimal path indirectly via `_risk_controller` non-None + drawdown scenario coverage | none — 06a Track 3 audit passed |

**Satisfaction declaration (fill at close-out — DP1-conditional wording)**:

- **If DP1 = A or B (T5.2 executed)**: "Plan 08 delivers the code_coverage + runtime_wire anchors for red lines 0.1 (real-strategy credential leak-negative in both sandbox and testnet modes) and 0.2 (G6 dir-hash gate accepts real supertrend directory) at the production-acceptance layer. Red line 0.3 per-strategy layer remains covered by 06a Track 2 (per-runner cap still deferred to Plan 04). Red line 0.4 vendored toolkit audit remains green per 06a Track 3."
- **If DP1 = C (T5.2 deferred)**: "Plan 08 delivers the code_coverage + runtime_wire anchors for red line 0.1 sandbox-mode only (real-strategy credential leak-negative via T5.1) and red line 0.2 (G6 dir-hash gate accepts real supertrend directory). Red line 0.1 testnet-mode credential-path coverage is deferred to <successor plan> per DEV-08-T5.2-DEFERRED. Red line 0.3 per-strategy layer remains covered by 06a Track 2 (per-runner cap still deferred to Plan 04). Red line 0.4 vendored toolkit audit remains green per 06a Track 3."

Neither wording degrades red-line satisfaction capability; the DP1 = C variant honestly declares partial coverage rather than overstating (per lesson #40 / C40 discipline).

---

## Deviations & improvements log

> **CEO decision points ×3 (elevate, do not silently decide)**: DP1 T5.2 testnet credential source, DP2 arx web sidecar HTTP migration scope, DP3 T5.1 fault injection scope. Drafter recommendations noted; CEO ratifies before Plan 08 execution begins.

### DEV-08-RENUMBER-FROM-06B

- **Level**: low (numbering hygiene, no scope change)
- **Issue**: Plan 06 06a spawn prompt named the deferred slice `06b`. After 06a squash-merge (`306b9e5`), Plan 07 (ps `shared/` curation → custos toolkit authority) was drafted and interleaves between the 06 substrate and the 06b remainder.
- **Decision (CEO 2026-07-09)**: renumber the remainder from `06b` to Plan 08. Plan 07 keeps its slot; the sequence 06 → 07 → 08 reads as landed substrate (06) → toolkit curation authority (07) → real-strategy e2e + close-out (08). Continuous `06b` label would misrepresent execution order.
- **Updated documents**: this plan header + `.forge/README.md` (T6.2 close-out); references to `06b` in Plan 06 marker preserved as historical anchor (do not rewrite past artifacts).

### DEV-08-TESTNET-CREDENTIAL-SOURCE 【CEO DECISION POINT 1】

- **Level**: medium (real testnet credential materially changes test surface + operational discipline)
- **Question**: T5.2 testnet credential source
- **Option A (drafter recommendation)**: **Real Binance testnet credential** provisioned via existing `credential_vault` sops+age scheme (mandatory-rules §5 — testnet is a sandbox key, not real-money). Test funds live on Binance testnet, no real capital at risk. Real network I/O, real testnet routing evidence, matches production acceptance gate semantics.
- **Option B**: **Mock testnet** — assert wire-level order intent and routing without real network. Cheaper to run, no operational credential requirement. Weaker acceptance signal — does not exercise real testnet-side rejection paths or credential vault decrypt under real deploy.
- **Option C**: **Defer T5.2 to a pre-live plan** — Plan 08 lands only T5.1 sandbox + T6.1 docs + T6.2 close-out, with T5.2 marked deferred (registered as DEV-08-T5.2-DEFERRED). The pre-live plan (currently unnamed; could be Plan 09 or later) handles testnet acceptance closer in time to live-mode enablement.
- **Impact**:
  - A: executor provisions testnet credential in vault, T5.2 lands green (or partial+manual per network availability); Plan 08 blocks on network reachability at T5.2 execution moment
  - B: T5.2 lands green immediately but with weaker signal; production acceptance shifts to whichever plan first exercises real testnet
  - C: Plan 08 completes with 3 tasks + 1 deferred; testnet acceptance blocked until future plan
- **Drafter recommendation**: **A**. Rationale — production acceptance semantics require real testnet exercise; the partial+manual fallback (`06-ps-supertrend-migration.md:287-289` precedent) already handles network unavailability without forcing option B or C.
- **Decision (CEO pending)**: __to be filled__.
- **Updated documents**: this plan T5.2 section (execution branch), `.forge/README.md` (T6.2 close-out remaining-items list if C selected).

### DEV-08-ARX-WEB-SIDECAR-FOLLOWUP 【CEO DECISION POINT 2】

- **Level**: medium (cross-repo coordination scope — carries from Plan 06 DP3 which resolved to option A)
- **Question**: arx web sidecar HTTP → NATS-only migration — Plan 08 blocker, arx-side follow-up plan, or skip
- **Option A (drafter recommendation)**: **Independent arx-side follow-up plan** — Plan 08 T6.1 documents the tech-debt in the "PS supertrend migration" section; arx team schedules its own migration plan asynchronously. Plan 08 does not block on arx delivery.
- **Option B**: **Upgrade to Plan 08 blocker** — custos + ps + arx three-repo coordination scope; Plan 08 does not close until arx web migrates off sidecar HTTP. Significantly expands Plan 08 scope and coupling.
- **Option C**: **Skip entirely** — do not document the debt in Plan 08; crucible ecosystem auto-maintains. Loses the documentation anchor and risks the debt being forgotten.
- **Drafter recommendation**: **A**. Rationale — this carries the Plan 06 DP3 CEO landing (option A: docs-only for sidecar retirement + arx follow-up not a Plan 06 blocker). Plan 08 T6.1 subsection 5 documents the debt to satisfy the discoverability requirement without expanding scope. Cross-repo coordination overhead is real (mandatory-rules §6 cross-repo commit discipline) and upgrading to option B would materially delay Plan 08 close-out for a debt that is orthogonal to real-strategy e2e acceptance.
- **Decision (CEO pending)**: __to be filled__.
- **Updated documents**: this plan T6.1 subsection 5 wording (independent follow-up vs blocker vs omit), `.forge/README.md` Plan 08 blocks column if B selected.

### DEV-08-SANDBOX-FAULT-INJECTION 【CEO DECISION POINT 3】

- **Level**: low (test breadth trade-off within Plan 08 T5.1 scope)
- **Question**: T5.1 sandbox e2e — golden path only, add fault injection inline, or defer fault injection to a downstream chaos plan
- **Option A (drafter recommendation)**: **Golden path only** — `test_real_supertrend_loads_and_deploys_sandbox` covers the happy load-deploy-teardown path; `test_credential_not_in_telemetry_payload_supertrend` covers the FU-2 leak-negative. No chaos injection in Plan 08.
- **Option B**: **Add chaos test inline in Plan 08 T5.1** — additional test using Plan 04 chaos infrastructure to inject NATS-down + venue-disconnect scenarios **during** the real supertrend running window, asserting safe-halt behaviour (red line 0.3 per-strategy layer plus chaos coverage). Requires Plan 04 chaos harness landed at Plan 08 execution time; if not landed, option B auto-degrades to option A.
- **Option C**: **Defer fault injection to Plan 04 chaos infrastructure or a dedicated pre-live chaos plan** — Plan 08 T5.1 remains golden-path (as in option A), but the plan explicitly declares "sandbox chaos coverage of real supertrend is deferred to <Plan 04 chaos harness landing> or <a pre-live chaos plan>" and registers a follow-up DEV entry naming the successor. Difference from A: option A treats chaos as "may revisit spike-style if Plan 04 lands"; option C treats chaos as an **explicit deferred obligation** with a named owner plan, tracked as an open item on Plan 06 close-out remaining-items.
- **Impact**:
  - A: Plan 08 tight scope; chaos coverage is a soft "might revisit later" item, no explicit follow-up
  - B: Plan 08 scope grows by 1 chaos test; blocks on Plan 04 chaos harness landing before execution
  - C: Plan 08 scope stays tight; chaos coverage becomes an explicit deferred obligation with a named successor plan
- **Drafter recommendation**: **A**. Rationale — T5.1 is already a substantial e2e; the chaos harness is Plan 04's deliverable, and adding it here (option B) risks Plan 08 becoming a de-facto Plan 04 dependency. Option C is a legitimate discipline-focused alternative for CEO to consider — it removes ambiguity about whether chaos coverage is "eventually revisited" (A) vs "explicitly owed" (C). If Plan 04 lands before Plan 08 execution, option B can be revisited without full plan re-drafting (spike-style addition), regardless of whether we start from A or C.
- **Decision (CEO pending)**: __to be filled__.
- **Updated documents**: this plan T5.1 section if B selected; Plan 06 close-out remaining-items list if C selected (naming the successor chaos plan).

### DEV-08-STRATEGY-SOURCE-PATH-TBD (executor-time decision)

- **Level**: low (implementation detail within T5.1)
- **Question**: T5.1 `strategy_path` — point at ps repo file directly, at a `tmp_path` copy, or at a permanent `tests/fixtures/real_supertrend/` mirror
- **Options**:
  - **(i) `tmp_path` copy** — executor stages `philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py` into pytest `tmp_path` before test runs. Self-contained: no runtime ps repo dependency in CI. Recommended for offline reproducibility.
  - **(ii) Direct ps repo path** — executor points `strategy_path` at the ps repo checkout. Requires ps repo alongside custos in test environment. Simpler but couples CI to ps checkout availability.
  - **(iii) Permanent `tests/fixtures/real_supertrend/` mirror** — copy ps strategy file into custos `tests/fixtures/` permanently. Fully self-contained; trades storage duplication and manual sync burden for offline reproducibility.
- **Decision**: executor selects at T5.1 implementation time based on Plan 07 curation scope + local CI environment; records selection here as `Selected: (i|ii|iii) — <rationale>`.
- **Not a CEO decision point** — this is an execution-time detail; escalation to CEO only if executor discovers all three options blocked (e.g. ps repo unavailable + `tests/fixtures/` mirror rejected + `tmp_path` incompatible with vendored toolkit `sys.path`).

### DEV-08-T5.2-DEFERRED (contingent on DP1 option C)

- **Level**: medium (deferred production acceptance gate)
- **Trigger**: DP1 CEO decision = option C (defer T5.2)
- **If triggered**: T5.2 is marked as ⚠️ Deferred in progress tracking + T5.2 details preserved as follow-up specification; close-out remaining-items list references this DEV entry + names the successor plan when identified. Otherwise, this DEV entry is not activated.

### DEV-08-T5.2-MANUAL-VERIFICATION (contingent on DP1 option A + network failure)

- **Level**: low (fallback path within T5.2)
- **Trigger**: DP1 CEO decision = option A + testnet network / funds unavailable at execution time
- **If triggered**: executor runs T5.2 test manually against testnet, captures passing output as evidence, marks T5.2 as ⚠️ Manual in progress tracking, records commands + timestamps in this DEV entry. Baseline `make verify` remains green (test is `@integration`, not baseline).

---

## Codex peer review criteria

Per `teams.yaml codex_audit.max_calls_per_plan=3` (custos budget tightening vs arx's 5):

- **Call 1 (L1 peer review)**: `--deep off`, medium effort. Reviewer checks (a) contract anchors match scout report verbatim (lesson C2 discipline), (b) T5.1 test names grep-verified 0-hits at plan drafting moment (lesson #25 zero-fabrication), (c) failure-mode contract table completeness (lesson #17 happy-path vs failure-mode discipline), (d) C40 red-line satisfaction table structure (three-layer code_coverage / runtime_wire / defer_status per red line), (e) File Inventory scope drift vs 06a landing state (Plan 08 does not silently expand into 06a's substrate), (f) DP1 / DP2 / DP3 options are complete and drafter recommendations are defensible.
- **Call 2 (contingent)**: if L1 surfaces CRITICAL / HIGH findings requiring directed fix, drafter applies in-place refinement (option B/C style) and requests a second call.
- **Call 3 (reserved)**: for extraordinary scenarios (drafter significantly off-track or architect_team elevation needed).

Stdin discipline (lesson #10): `codex exec < /dev/null` to avoid EOF-wait hangs. Effort tuning (lesson #12): `-c model_reasoning_effort="high"` for L1 (not xhigh); `-o <FILE>` to isolate final assistant message from exploration logs.

---

## References

| Ref | Path |
|-----|------|
| Handoff packet | `.forge/handoff/2026-07/plan-team-07-08-09-packet.md` |
| Evidence-scout report (Batch 1) | `.forge/handoff/2026-07/evidence-scout-07-08.md` |
| Plan 06 (parent) | `.forge/plans/2026-07/06-ps-supertrend-migration.md` |
| Plan 06 06a close-out marker | `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-06a-v1.complete.json` (embedded in 306b9e5) |
| Plan 07 (Batch 1 sibling — this plan's START gate) | `.forge/plans/2026-07/07-*.md` (drafted alongside this plan by parallel drafter) |
| Progress-management template | `.claude/rules/progress-management.md` §"完成报告模板" |
| Existing sandbox lifecycle scaffolding | `tests/test_nt_trading_node_host_integration.py` |
| Language Policy hook | `scripts/check-code-english.py` (5c01cdb) + `scripts/install-hooks.sh` + `scripts/hooks/pre-commit` |
| Vendored toolkit (06a substrate) | `src/custos/engines/nautilus/toolkit/` + `TOOLKIT_PROVENANCE.md` |
| Mandatory rules (red lines) | `.claude/rules/mandatory-rules.md` §0 |
| Historical lessons cited | #14 Foundation Scan / #17 happy-path ≠ failure-mode / #22 multi-layer defense / #25 fabricated-test-name gate / #40 (C40) close-out red-line satisfaction / #21 zero-silent / C2 output-pollution / #10 stdin discipline / #12 codex effort tuning |

---

## Close-out report

(Fill at Phase 3 execution completion, following the same template as `.claude/rules/progress-management.md` §"完成报告模板". English labels here are equivalents for readability; the authoritative template heading remains Chinese in the rule file — do not rename it there. When filling Plan 06's own close-out per T6.2, use the Chinese headings verbatim as required by the rule.)

- **Completion date (完成日期)**: {YYYY-MM-DD}
- **Total task count (总 Task 数)**: 4 (T5.1 + T5.2 + T6.1 + T6.2)
- **Deviation count (偏离数)**: {N} (DEV-08-* entries)
- **Verification result (验证结果)**: all passed / partial (T5.2 outcome per DP1)
- **Implementation commit range (实施 commit 范围)**: custos {first_sha}..{last_sha}
- **Contract impact (契约影响)**: `docs/design/nautilus_host.md` (new "PS supertrend migration" section) + Plan 06 close-out + `.forge/README.md` index
- **Red-line guardianship (红线守护)**: Non-custodial 4 red-lines all held (grep record, plus new e2e test files) — see §red-line gate satisfaction table for real values. DP1-conditional wording (see satisfaction declaration above).
- **Failure-mode coverage (失败模式覆盖)**: NEW tests — T5.1 (2 tests) + T5.2 (1 test, DP1-conditional); existing no-regression preserved
- **Remaining items (遗留项)**: per-runner cap layer (Plan 04) + ps `shared/` curation & convergence discipline (Plan 07) + arx web sidecar HTTP → NATS-only migration (arx-side follow-up per DP2) + T5.2 outcome status if partial / deferred / manual + chaos coverage successor plan if DP3 = C

---

## Next

Plan 08 close-out enables:

- **First production paper→testnet e2e landing** for ps supertrend on custos (assuming DP1 option A landed green). Combined with Plan 04 (red line 0.3 per-runner cap), all three layers of red line 0.3 are satisfied; combined with Plan 07 curation landing, custos toolkit substrate stabilizes as the ecosystem's authority.
- **Plan 06 fully closed** — ps supertrend migration considered production-ready on custos; ps sidecar / runner retirement declared docs-side.
- Follow-up candidates:
  - **arx-side follow-up plan**: arx web migrates from sidecar HTTP to NATS-only (DP2 option A materialization; arx team schedules)
  - **Pre-live plan**: if DP1 option C selected (T5.2 deferred), a follow-up plan handles testnet acceptance immediately before live-mode enablement
  - **Plan 09**: hook infra formalization (Batch 2 sibling of this plan; independent of Plan 07 / 08 close-out)
  - **OKX venue support**: `host.py` currently hard-codes Binance; generalization + second venue e2e (README §Not Included Yet)
  - **Chaos harness integration (Plan 04 dependency)**: if DP3 option B revisited after Plan 04 lands, add chaos coverage to T5.1 sandbox path (spike-style addition, not full re-plan)
