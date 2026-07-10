# Plan 04 04a slice DEVIATION Triage (Step 6.4a — partial close-out)

**Plan**: `04-red-line-03-runner-fallback.md` — 红线 0.3 完整兑现: runner-level cap + 状态快照 + zombie detection + arx-disconnect chaos
**Slice**: **04a** (Tracks 1+3+4 + T5.1 — cap + zombie + breaker + chaos 核心; 红线 0.3 runtime-wire 硬阻断路径)
**Slice landed**: `3e85c50` refactor(custos): Plan 04 04a slice — red-line 0.3 runtime-wire tri-guard (squash), followed by delta `b77fbf9` (DEV-04a-TEST-FILE-NAMING annotation)
**Deferred to 04b**: Track 2 (state snapshot 可观测层) + T5.2 (long-run chaos) + Track 6 (docs 同步 + close-out)
**Marker source**: `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-04a-v1.complete.json`
**Triaged at**: 2026-07-10
**Triaged at main HEAD**: `5eff170`
**Triager**: Execution Lead (main-session Claude, `/forge:execute-team` C-step follow-through)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (无 HIGH triage) |
| MED | **0** | — |
| LOW | **12** | 仅记, 无需 AskUser 或 fix-now |

**Overall triage verdict**: **ALL LOW — 可放行 04a partial close-out**, 无阻断项。Plan 04 整体 close-out 待 04b 完成后统一签发（届时可能追加 04b 段 DEV 条目）。

---

## LOW 档明细（12 条）

### CEO decision landing (3 条 — 决策点 04 DP1/DP2/DP3)

#### DEV-04-CAP-DEFAULT

- **等级**: LOW
- **场景**: Runner-level notional cap 硬编码 floor 默认值终裁
- **决定**: paper=200 USD / live=1000 USD (`src/custos/core/local_cap.py:29-30`), CEO DP1 拍板
- **状态**: ✅ 已 applied (source-of-truth in code)

#### DEV-04-CHAOS-MECHANISM

- **等级**: LOW
- **场景**: arx-disconnect chaos test 断线注入手段
- **决定**: mock NATS disconnect (`tests/core/test_arx_disconnect_chaos.py`), CEO DP2 拍板
- **状态**: ✅ 已 applied

#### DEV-04-ZOMBIE-THRESHOLD

- **等级**: LOW
- **场景**: Zombie detection grace period 长度
- **决定**: 60 秒 (`src/custos/core/zombie_watchdog.py:27`), CEO DP3 拍板 (保守选)
- **状态**: ✅ 已 applied

### Implementation decisions (4 条 — executor 落地技术选择)

#### DEV-04-FLATTEN-NT-MAPPING

- **等级**: LOW
- **场景**: `flatten_positions` Tier-2 方法在 NT 端的 SDK 映射
- **决定**: `flatten_positions` → `Strategy.close_all_positions` (`src/custos/engines/nautilus/host.py:423`), grep-verified NT SDK 接口
- **状态**: ✅ 已 applied

#### DEV-04-PEAK-EQUITY-DECIMAL

- **等级**: LOW
- **场景**: FallbackBreaker `_peak_equity` 数值精度类型
- **决定**: `Decimal` (`src/custos/core/fallback_breaker.py:73`), 拒 ps 侧 float 参考实现 (红线 0.4 显式重推)
- **状态**: ✅ 已 applied — 红线 0.4 一致

#### DEV-04-DEPLOYMENTSPEC-DICT

- **等级**: LOW
- **场景**: `DeploymentSpec.risk_config` 读取方式
- **决定**: `spec.get('risk_config', {})` dict-access (`src/custos/core/local_cap.py:51`, `fallback_breaker.py:42`), 不引入 Pydantic model (最小改动 DeploymentSpec)
- **状态**: ✅ 已 applied

#### DEV-04-TIER2-PROTOCOL-REQUIRED

- **等级**: LOW
- **场景**: Tier-2 3 方法 (get_open_notional / check_engine_connected / flatten_positions) 是否 optional
- **决定**: **required** on same `ExecutionEngineProtocol` (both hosts pairwise 实现; isinstance 每 commit 绿), 拒 optional protocol split 保 04a 契约紧凑
- **状态**: ✅ 已 applied

### New deviations from execution (5 条 — 实施发现的偏离)

#### DEV-04a-ZOMBIE-WATCHDOG-MODULE

- **等级**: LOW
- **场景**: `src/custos/core/zombie_watchdog.py` 是独立 `ZombieWatchdog` class；plan File Inventory §A 未列此文件（原假设 watchdog 逻辑内嵌 `deployment_reconciler.py`）
- **决定**: 保留独立模块 — Task T4.3 + verification §388 都要求可注入 `zombie_watchdog` fixture，独立文件更合乎单一职责 + 更易 test
- **契约影响**: File Inventory §A 需在 Plan 04 close-out 时补收（04b 时 batch）
- **状态**: ✅ 已 applied，需 04b 补 File Inventory

#### DEV-04a-BREAKER-DRAWDOWN-EQUITY-DEFER

- **等级**: LOW (lesson #40 partial scope 显式标注 — 非隐性 defer)
- **场景**: Reconciler `_breaker_tick` 目前只 enforce notional ceiling; drawdown breach 需要 `current_equity` feed 从 Tier-2 `get_engine_status`（属 04b Track 2）
- **决定**: FallbackBreaker.evaluate 已完整支持 drawdown when equity supplied (isolated test 全绿); reconciler 侧 wire 待 04b 补
- **红线 0.3 影响**: notional 层 runtime-wire 已 live; drawdown 层 code ready + runtime wire deferred（lesson #40 code_coverage ≠ runtime_wire 教科书应用）
- **状态**: ✅ 已 applied，04b 补 runtime wire

#### DEV-04a-CAP-ENFORCEMENT-HOOK-DEFER

- **等级**: LOW (lesson #40 partial scope)
- **场景**: `RunnerNotionalCap` guard + `PreTradeRejected` reject wire 已构造 + 注入 + decision-tested (disconnect-independent); NT per-order intent interception (submit 前 call `guard.allows`) 是 v1 follow-up
- **决定**: hook 路径 defer 到 v1 pre-live（04b 或独立 plan）
- **红线 0.3 影响**: cap decision layer 已 runtime-wire; intercept 层 deferred
- **状态**: ✅ 已 applied，v1 补 intercept

#### DEV-04a-LANG-SWEEP

- **等级**: LOW
- **场景**: 本 slice 新增 comments/docstrings 全数英文化 + 移除源码 plan/lesson 编号 (per CLAUDE.md §Language Policy RED LINE + lesson #15)
- **决定**: 存量 CJK 未 sweep（属 DEV-05a-LANG-POLICY-DEFER 范围 — 独立 language-sweep plan candidate）
- **状态**: ✅ 已 applied（本 slice 新增内容合规），存量 sweep 推 language plan

#### DEV-04a-TEST-FILE-NAMING

- **等级**: LOW
- **场景**: `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py` 当前只覆盖 NT-side `get_open_notional` (Track 1) + `flatten_positions` (Track 4); 文件名 "state_snapshot" 预期 04b 会追加 `get_positions` / `get_orders` / `get_engine_status`
- **决定**: 保留命名，04b Track 2 时同文件扩容
- **状态**: ✅ 已 applied，命名对齐 04b 预期（本 DEV 由 `b77fbf9` 追加登记，是 lesson #25 反 fabricated 精神的正例 — executor 主动记录预期而非事后补拟）

---

## Plan 04b 追踪清单（partial close-out 承接）

由 04b 收尾并统一签发 Plan 04 完整 close-out 时需处理：
1. File Inventory §A 补 `src/custos/core/zombie_watchdog.py`（DEV-04a-ZOMBIE-WATCHDOG-MODULE）
2. drawdown breach runtime wire — reconciler 侧 `current_equity` feed（DEV-04a-BREAKER-DRAWDOWN-EQUITY-DEFER）
3. NT per-order intent interception hook（DEV-04a-CAP-ENFORCEMENT-HOOK-DEFER）
4. `test_state_snapshot_nautilus_impl.py` 扩容 get_positions/get_orders/get_engine_status（DEV-04a-TEST-FILE-NAMING）
5. Track 6 docs 同步（reconcile.md / domain.md / engine_protocol.md / nautilus_host.md — Plan 04 §File Inventory §C）
6. T5.2 long-run chaos + T-final close-out marker（含 Plan 04 完整红线 gate 满足度表）

---

## 红线守护实证 (04a 落地时 grep 记录)

来自 marker `constraints_honored`（`.forge/dispatch-log/.../runner-executor-04a-v1.complete.json`，落 `3e85c50` 里）:

- **0.1 Key/KEK 永不出进程**: `grep 'log.(info|debug|warning).*api[_-]?key' src/ tests/` = 0
- **0.2 G6 gate 不绕过**: 契约未动，5 relaxed-double 全绿
- **0.3 失联 ≠ 停止**: notional cap runtime-wire ✅ / breaker code ready + drawdown wire deferred / zombie watchdog live — partial scope 精确到子路径
- **0.4 Money math Decimal**: `grep 'float\(.*(price|amount|notional)' src/custos/ --exclude-dir=toolkit` = 0

---

## Follow-up 建议

- Plan 04b 起草前，将上述"04b 追踪清单"作为 File Inventory 优先项
- Plan 04b close-out 时统一签发 Plan 04 完整 close-out（本 triage + 04b 时追加的 triage 合并到 Plan 04 完成报告段引用）
