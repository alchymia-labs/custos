# 04 — 红线 0.3 完整兑现: runner-level cap + 状态快照 + zombie detection + arx-disconnect chaos

> **Status**: 🔲 Todo (skeleton candidate, awaiting Phase 2 `/forge:plan-team` 精细化)
> **Created**: 2026-07-09 (Plan 03 close-out 后 dogfood 深度审计 — safety-validator 跨范围审 + Lead 独立复核发现红线 0.3 组合级熔断未兑现)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: skeleton, 需 Phase 2 精细化后可执行
> **Depends on**: Plan 00a ✅ + Plan 00b ✅ + Plan 00c ✅ + Plan 03 ✅
> **Blocks**: 上 live 前的**硬阻断项** (即使 paper/testnet 也建议先做, 因为需要 chaos test 验证)
> **multi_session_scope**: unknown (待 Phase 2 精细化后判定, 预估 medium ~200-400 LOC)

---

## 起源 (Origin)

Plan 03 close-out 后, safety-validator 主动跨范围深度审 custos "能否托付真钱", grep 实证发现:

1. **CLAUDE.md 红线 0.3** 明文承诺 "云端断线时本地 fallback breaker + `max_notional_per_runner` cap 继续守护", 但:
   - `grep -rn 'max_notional_per_runner' src/ tests/` → **0 命中**
   - `grep -rn 'breaker|circuit_break|kill_switch' src/arx_runner/` → **0 命中**
   - `drawdown` 唯一命中是 `telemetry_actor.py:67` 一个字段名 `drawdown_pct` (遥测字段, 非熔断实现)
   - 现有失联测试全是**网络层降级** (NATS WAL / MessageBus disconnected / stale-spec rejection), 无 **runner 级累计 notional cap + drawdown 熔断 chaos 测试**

2. **红线 0.3 分层的当前实现状态**:
   - ✅ per-order (NT `RiskEngine` 单笔限额, Plan 00c 已配)
   - ✅ per-strategy drawdown (ps `shared/risk/RiskController`, `NautilusTradingStrategy:177` 基类可选装载, 需 config 启用)
   - ❌ per-runner **max_notional_per_runner cap** (custos + ps 均无)
   - ❌ per-runner **fallback breaker** (arx 断线时自主熔断, 无实现)

3. **教科书级 lesson #40 场景**: 红线名 (设计意图) vs runtime 兑现 (能力实现) 的鸿沟。CLAUDE.md 段落是"应该守什么", 但代码是"实际守了什么", 二者严重不对齐。

4. **借鉴机会**: ps `deploy/nautilus/runner.py` (`_collect_metrics/orders/positions/engine_status`) 有成熟的状态快照收集实现, 可迁到 custos telemetry_actor; ps sidecar `app.py:298` "Rule 2 persistent degradation" 检测逻辑可移植到 custos deployment_reconciler。

---

## 上下文 (Context)

**as-of Plan 03 close-out (main HEAD `cbf5556`, 2026-07-09)**:

- custos NtTradingNodeHost (Plan 00a/00c) 已实现 G6 gate + NT `TradingNode` lifecycle + credential vault + telemetry 桥 + reconciler
- 但 CLAUDE.md 红线 0.3 定义的"runner 层结构性守护"是**空白**:
  - 无本地 notional cap
  - 无本地 fallback breaker (arx 断线时纯靠 NT 单笔限额兜底)
  - 无 zombie detection (engine disconnected 但进程 alive 时无主动降级信号)
- 上 live 前的**硬阻断项**

**ps 端可借鉴的模块** (grep 实证):
- `philosophers-stone/deploy/nautilus/runner.py:216` `_collect_metrics` (含 `_peak_equity` + `drawdown` 计算)
- `philosophers-stone/deploy/nautilus/runner.py:344` `_collect_orders`
- `philosophers-stone/deploy/nautilus/runner.py:383` `_collect_positions`
- `philosophers-stone/deploy/nautilus/runner.py:453` `_collect_engine_status` (`kernel.data_engine.check_connected()` + `kernel.exec_engine.check_connected()`)
- `philosophers-stone/deploy/sidecar/app.py:298` "Rule 2 persistent degradation" 检测算法

---

## Track 划分 (待 Phase 2 精细化)

### Track 1 — Runner-level notional cap (结构性)

- 在 custos 新加 `arx_runner/local_cap.py` 或扩展 `deployment_reconciler.py`
- Cap 从 `DeploymentSpec.risk_config.max_notional_per_runner` 读入
- 每次 order intent 前 pre-trade check: `current_open_notional + new_order_notional <= cap` 否则拒绝
- 与 `nt_risk_engine.on_order_denied()` 现有路径集成, 拒绝时走 `PreTradeRejected` wire
- 云端断线时 cap 保留 (从上次成功 pull 的 spec 缓存)

### Track 2 — 状态快照 (借鉴 ps `_collect_*`)

- 迁 ps `_collect_metrics/orders/positions/engine_status` 到 custos `telemetry_actor.py` 或新加 `state_snapshot.py`
- 周期性 (可配, 默认 10s) publish NATS `arx.{tenant}.snapshot.state` 
- 与 custos 现有 event stream 并存 — event 是 push (低延迟), snapshot 是 pull-friendly (arx 前端可拿最新状态)
- 触发 arx web 的 sidecar HTTP tech debt 迁移 (arx web 前端换成消费 NATS 快照, 见 Plan 03 close-out 分析 tech debt)

### Track 3 — Zombie detection (对标 sidecar `app.py:298` Rule 2)

- 在 custos `deployment_reconciler.py` 加 "engine liveness watchdog": 每 N 秒调 `node.kernel.data_engine.check_connected()` + `exec_engine.check_connected()`
- 若 `check_connected() == False` 持续 > threshold (默认 30s), 且 process/IPC 仍 alive → 标 `phase=degraded` + `health.reason=engine_disconnected_zombie`
- **本地自主降级**: 不需要等 arx 命令; arx 断线时 zombie detection 仍触发本地降级
- structlog 事件名 `engine_zombie_detected`

### Track 4 — Fallback breaker (arx 断线时自主熔断)

- 云端断线时 (NATS reconnect_attempts 耗尽 → `arx_unavailable`), custos 本地缓存的 spec 里含 `runner_fallback_breaker`:
  - accumulate 敞口超 threshold → 主动 flatten (close_all_positions + reject new orders)
  - drawdown 超 threshold → 同上
- 与 Track 1 (cap) 差异: cap 是**软限** (拒绝超额新单), breaker 是**硬限** (触发即平仓 + 冻结)
- **红线 0.3 核心兑现**: 云端断线 ≠ 停止, 但也**不能失控**

### Track 5 — Chaos test (arx-disconnect fault injection)

- 新加 `tests/test_arx_disconnect_chaos.py`:
  - 用 mock NATS 断线注入 (nats_client 层 raise `ConnectionClosedError`)
  - 断言: reconciler 不 crash, telemetry 缓存 WAL, cap/breaker 继续生效, engine liveness 检查继续跑
- 覆盖 Plan 00b 的 telemetry WAL resilience 之外的**全 runner 断线场景**

---

## Historical Lessons 强制引用 (待 Phase 2 补齐)

- **lesson #40 (ecosystem) + custos C2**: 红线名 vs runtime 兑现 — 本 plan 是 lesson #40 在 project-level 的兑现
- **lesson #14/#30/#33/#33b (Foundation Scan 四维)**: Phase 2 evidence-scout 必扫 ps runner.py / sidecar 现状 + custos 6 模块骨架 + 引 上游 Plan 00b close-out 后 as-of 时间锚
- **lesson #17 (failure-mode ≠ happy-path)**: Chaos test (Track 5) 是本 plan 核心, 不允许仅 happy-path 覆盖
- **lesson #22/#28 (multi-layer fail-fast + 独立可测)**: cap / breaker / zombie / snapshot 4 层, 每层独立 relaxed-double test
- **custos C2 (输出污染贯穿 review/self-review)**: 起 plan 时 grep 实证每条现状, 不采信推理

---

## 目标 (Goal, 待 Phase 2 精细化)

Plan 04 close-out 后:
- **红线 0.3 三层齐**:
  - per-order (NT RiskEngine, existing)
  - per-strategy drawdown (ps RiskController, Plan 06 依赖)
  - per-runner max_notional_per_runner cap + fallback breaker (本 plan)
- **状态可见性**: arx 前端拿到 custos 定期 push 的状态快照, 摆脱 sidecar HTTP 依赖
- **Zombie 自主检测**: engine disconnected 时无需 arx 命令即本地降级
- **Chaos 覆盖**: arx-disconnect 场景 fault injection 测试全绿
- 上 live 前的 **1 号硬阻断项** 消除

---

## Task List (待 Phase 2 精细化)

**skeleton 暂列 High-level, 精细化后拆到具体 file:line + LOC**:

1. [T1] Runner-level cap 实现 + `PreTradeRejected` 集成
2. [T2] 状态快照 4 函数迁移 + NATS publish
3. [T3] Zombie detection watchdog + degraded signaling
4. [T4] Fallback breaker (arx 断线时 flatten + freeze)
5. [T5] Chaos test suite (arx-disconnect fault injection)
6. [T6] `docs/design/reconcile.md` + `docs/domain.md` 同步 (红线 0.3 兑现描述)

---

## File Inventory (待 Phase 2 grep 实证锚点)

skeleton 阶段暂列**候选文件**, Phase 2 evidence-scout 确认后精确到 file:line:

| 候选文件 | 类型 | 说明 |
|----------|------|------|
| `src/arx_runner/local_cap.py` | 新建 | Track 1 cap 主体 |
| `src/arx_runner/state_snapshot.py` | 新建 | Track 2 快照, 借鉴 ps `_collect_*` |
| `src/arx_runner/deployment_reconciler.py` | 改 | Track 3 zombie watchdog + Track 4 fallback breaker |
| `src/arx_runner/nt_risk_engine.py` | 改 | Track 1 cap 集成到 pre-trade path |
| `src/arx_runner/telemetry_actor.py` | 改 | Track 2 snapshot publish 集成 |
| `tests/test_local_cap.py` | 新建 | Track 1 test |
| `tests/test_state_snapshot.py` | 新建 | Track 2 test |
| `tests/test_zombie_detection.py` | 新建 | Track 3 test |
| `tests/test_fallback_breaker.py` | 新建 | Track 4 test |
| `tests/test_arx_disconnect_chaos.py` | 新建 | Track 5 chaos test |
| `docs/design/reconcile.md` | 改 | 红线 0.3 三层兑现说明 |
| `docs/domain.md` | 改 | RunnerFallbackConfig / RiskConfig 数据模型 |

---

## 失败模式覆盖契约表 (lesson #17, 待 Phase 2 具体化)

skeleton 阶段列**必覆盖场景**, Phase 2 归一化为 F1-Fn:

- arx 断线 + 敞口未超 cap → normal
- arx 断线 + 敞口超 cap → 拒绝新单 (Track 1)
- arx 断线 + drawdown 触发 breaker → 主动 flatten (Track 4)
- engine disconnected + process alive > 30s → zombie 降级 (Track 3)
- NATS mock disconnect + reconnect → snapshot 缓存 + drain (Track 2 + WAL 已有)
- 云端断线 6 小时 → 本地 cap/breaker 仍工作 (chaos long-run)

---

## 红线 gate 满足度表 (lesson #40, 待 Phase 2 填实)

skeleton 阶段声明**目标状态**, Phase 2 close-out 填 code_coverage / runtime_wire / defer_status:

| 红线 | 目标兑现层 | 目标状态 |
|------|-----------|---------|
| 0.1 Key/KEK 出进程 | 本 plan 不 touch | 保持 Plan 00a + Plan 03 状态 |
| 0.2 G6 gate | 本 plan 不 touch | 保持 Plan 00c 状态 |
| **0.3 失联 ≠ 停止** | **本 plan 兑现 per-runner 层** | **runtime_wire 从"未实现"升级到 code + wire 完整闭环** |
| 0.4 Money math | Track 4 breaker 敞口计算用 Decimal | 保持 Plan 03 状态 |

---

## 偏离与改进日志 (Deviation Log)

(Phase 2 精细化阶段填, Phase 3 执行阶段更新)

---

## 完成报告 (Close-out Report)

(Phase 3 执行完成后填, 按 progress-management.md 模板)

---

## 下一步 (Next)

Plan 04 close-out 后:
- 红线 0.3 完整兑现, 组合级熔断三层齐, 上 live **1 号硬阻断项**消除
- 触发 arx web 的 sidecar HTTP tech debt 独立迁移 (arx 项目自己起 plan)
- 与 Plan 06 (ps supertrend 迁移) 组合完成后, custos + ps 生态可跑真实 paper/testnet e2e
- 后续 pre-live 硬门槛清单 (from safety-validator 深度审):
  1. ~~红线 0.3 组合级熔断兑现 (本 plan)~~
  2. credential_vault 独立第三方安全审计 (Plan 07+ candidate)
  3. 密钥不出进程的 runtime 验证 (抓包/内存 dump 级, Plan 08+ candidate)
  4. 跨语言 wire 契约真实跑 (fixture 修复, Plan 05 tech debt)
  5. 签名 release pipeline (供应链, Plan 09+ candidate)
  6. 红队/绕过测试 (G6 gate / 失联降级 / 注入, Plan 10+ candidate)
  7. 清零 15 处 stub (滚动清理)
