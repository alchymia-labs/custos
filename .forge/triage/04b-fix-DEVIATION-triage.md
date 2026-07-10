# Plan 04 04b-fix cycle DEVIATION Triage (codex L1 REQUEST_CHANGES closure)

**Plan**: `04-red-line-03-runner-fallback.md` — 红线 0.3 完整兑现: runner-level cap + 状态快照 + zombie detection + arx-disconnect chaos
**Fix cycle**: **04b-fix** (closes 04b codex L1 REQUEST_CHANGES: 1 HIGH + 2 MED runtime-wire gaps)
**Cycle landed**: `b04071e` fix(custos): 04b-fix HIGH-1 + MED-2 — wire state snapshot publisher on the WAL-backed path + `1c9f3dd` fix(custos): 04b-fix MED-3 — risk_config live-refresh from spec per loop
**Marker source**: `.forge/dispatch-log/2026-07-04b-05b-execute-team-packet/runner-executor-04b-fix.complete.json`
**Peer review source**: `.forge/reviews/2026-07/04b-peer-codex.md`
**Triaged at**: 2026-07-10
**Triaged at worktree HEAD**: `1c9f3dd`
**Triager**: runner-executor-04b-fix (fix-cycle executor teammate)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (all 3 findings closed via fix; no new HIGH introduced) |
| MED | **0** | — |
| LOW | **0** | — |

**Overall triage verdict**: **NO NEW DEVIATIONS OPENED DURING FIX CYCLE**. Each of the 3 codex L1 findings accepted the recommended **Option A** resolution direction listed in the spawn packet — no A-vs-B escalation, no design conflict, no scope surprises. Fix cycle is a straight closure; Plan 04 reflipped to ✅ Completed.

---

## Findings closure summary

### HIGH-1 CLOSED — StateSnapshotPublisher wire

- **Finding source**: `.forge/reviews/2026-07/04b-peer-codex.md` §Finding 1 (`src/custos/cli/main.py:224` HIGH — StateSnapshotPublisher is never wired into the runner entrypoint)
- **Team-lead independent grep confirmation**: `grep -rn 'StateSnapshotPublisher' src/ --include='*.py'` returned 1 hit only (the class definition at `src/custos/core/state_snapshot.py:109`). Zero wire in `cli/main.py` at squash HEAD `d0dd537`.
- **Resolution direction chosen**: **default (spawn packet HIGH-1 direction)** — import + construct in `_run` alongside reconciler/heartbeat, start via `asyncio.create_task(publisher.run(...))`
- **Landed at**: commit `b04071e`
- **Files touched**:
  - `src/custos/core/state_snapshot.py` — `run(stop, spec_id_source: Callable[[], Sequence[str]])` replaces `run(stop, spec_id: str)` so N concurrent deployments share one task
  - `src/custos/core/deployment_reconciler.py` — new public method `active_spec_ids()` returning spec ids whose `container_id` is set
  - `src/custos/cli/main.py` — imports `StateSnapshotPublisher`, constructs it after `_build_host` + `_build_reconciler`, schedules `publisher.run(stop, reconciler.active_spec_ids)` alongside `reconcile_loop` + `_heartbeat_loop`
- **Contract tests grep-实存 (lesson #25)**: `test_reconciler_exposes_active_spec_ids` (1 hit) + `test_main_starts_state_snapshot_publisher` (1 hit)
- **New deviation opened**: **none**

### MED-2 CLOSED — WAL-backed publish path (Option A)

- **Finding source**: `.forge/reviews/2026-07/04b-peer-codex.md` §Finding 2 (`src/custos/core/state_snapshot.py:167` MED — disconnected snapshot caching is not implemented for the publisher path)
- **Team-lead independent grep confirmation**: `state_snapshot.py:42-43` docstring explicitly said client "swallows disconnected calls" — that is the at-most-once fire-and-forget contract, not the WAL-backed telemetry contract Plan §304-306 required.
- **Resolution direction chosen**: **Option A** (switch publisher to `publish_telemetry_envelope` — matches plan §304-306 intent + docs contract). Option B (revise contract downgrading the WAL claim) was rejected because the JetStream path exists and is the correct default for at-least-once observability.
- **Landed at**: commit `b04071e` (same commit as HIGH-1, they share the state_snapshot + cli/main hunk clusters)
- **Files touched**:
  - `src/custos/core/state_snapshot.py` — `_NatsPublisher` Protocol now requires `publish_telemetry_envelope(subject, NatsEnvelope)`; `publish_once` builds a `NatsEnvelope` (not a dict-wrapped-bytes) and hands it to the client
  - `src/custos/cli/main.py` — new `--wal-path` CLI flag defaulting to `~/.custos/state/telemetry-wal.db`; `ArxNatsClient` construction passes `wal_path=args.wal_path`; parent directory is auto-created for fresh installs
- **Contract test grep-实存 (lesson #25)**: `test_state_snapshot_wal_cached_when_disconnected` (1 hit) — directly exercises the real `ArxNatsClient` disconnected boot path (`_js is None + _wal set`) and asserts the WAL row lands with the correct snapshot subject + payload shape
- **Replaced test**: `test_snapshot_cached_when_disconnected` (only tested the fire-and-forget no-op semantics, which no longer applies)
- **New deviation opened**: **none**

### MED-3 CLOSED — risk_config live-refresh (Option A)

- **Finding source**: `.forge/reviews/2026-07/04b-peer-codex.md` §Finding 3 (`src/custos/cli/main.py:177` MED — RunnerRiskConfig is documented as live from spec, but runtime still uses defaults)
- **Team-lead independent grep confirmation**: `cli/main.py:178` constructed `LocalCapConfig.from_spec({}, live=False)` and `:183` `FallbackBreakerConfig.from_spec({})` with empty dict at startup only. `docs/domain.md:104` says "daemon reads risk_config from the spec and changes take effect next loop" — actual behavior = defaults forever.
- **Resolution direction chosen**: **Option A** (implement per-poll refresh in the reconciler). Option B (revise docs to acknowledge startup-only semantics) was rejected because the live-refresh path is genuinely small and closing the docs-vs-code drift is more valuable than pinning a v1 constraint.
- **Landed at**: commit `1c9f3dd` (guard-side `apply_config` methods + new failing-first tests); the reconciler wire (`_refresh_risk_config` method + call from `handle_spec` + imports of `LocalCapConfig` / `FallbackBreakerConfig`) landed in the preceding commit `b04071e` because it shares the same `deployment_reconciler.py` hunk cluster as `active_spec_ids`.
- **Files touched**:
  - `src/custos/core/local_cap.py` — `RunnerNotionalCap.apply_config(new)` swaps config, returns True on real change
  - `src/custos/core/fallback_breaker.py` — `FallbackBreaker.apply_config(new)` swaps config, preserves `_peak_equity` + `_frozen` so a refresh does not silently reset the drawdown high-water mark or clear an existing trip
  - `src/custos/core/deployment_reconciler.py` — new private `_refresh_risk_config(spec)` runs before the generation gate; emits `risk_config_refreshed` structlog exactly once per real change; no-op refresh stays silent; live vs paper cap floor is picked from `spec.lifecycle_state == "live"`
- **Contract tests grep-实存 (lesson #25)**: `test_local_cap_refreshes_when_spec_changes_max_notional` (1 hit) + `test_fallback_breaker_refreshes_when_spec_changes_max_notional` (1 hit) + `test_risk_config_refresh_is_noop_when_unchanged` (1 hit) + `test_risk_config_refresh_uses_lifecycle_for_live_floor` (1 hit)
- **New deviation opened**: **none**

---

## Verification snapshot

- `make verify` (with `--extra dev --extra nautilus`): **288 passed, 1 warning** at 04b-fix HEAD `1c9f3dd`
- Non-Custodial 4 red-line grep gates:
  - 0.1 Key/KEK 出进程: **0 hits** in `src/` / `tests/`
  - 0.2 G6 gate 绕过: **0 hits** (excluding `host.py`)
  - 0.3 失联即停止: **0 hits** in `deployment_reconciler.py` (`stop_all_strategies` / `force_shutdown`)
  - 0.4 float money math: hits only in vendored `pandas_ta` OHLCV serialization inside `toolkit/` — pre-existing, third-party, outside the custos daemon money path
- All 7 contract test names introduced by 04b-fix grep-实存 with 1 hit each (lesson #25 gate satisfied)

---

## References

- Peer review: `.forge/reviews/2026-07/04b-peer-codex.md`
- Fix commits: `b04071e` + `1c9f3dd`
- Marker: `.forge/dispatch-log/2026-07-04b-05b-execute-team-packet/runner-executor-04b-fix.complete.json`
- Plan md close-out reflip: `.forge/plans/2026-07/04-red-line-03-runner-fallback.md` — Status ⏳ → ✅
- Prior triage: `.forge/triage/04a-DEVIATION-triage.md` (Plan 04 04a slice, 12 LOW + 0 HIGH/MED)
