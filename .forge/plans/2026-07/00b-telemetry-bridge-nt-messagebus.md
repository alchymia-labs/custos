# 00b - telemetry_actor 接 NT MessageBus + pre_trade_bridge 接 NT OrderDenied

> **Status**: 🔲 Todo (blocked by Plan 00a close-out)
> **Created**: 2026-07-07
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Plan 00a (NtTradingNodeHost 真起 TradingNode, 才有 MessageBus 可订阅)
> **multi_session_scope**: false (4-5 task, ~400 LOC 单 session 可完成)

## 上下文 (Context)

### 现状 (as-of Plan 00a close-out 之后)

Plan 00a 完成后 `NtTradingNodeHost` 会真起 `TradingNode`, `node.kernel.msgbus` 有真实 event stream (fill / position / order / OrderDenied)。但当前 custos 侧:

- `telemetry_actor.py` (`src/arx_runner/telemetry_actor.py`) 只有骨架, 顶部注释 "We don't import nautilus_trader at module load time because the runner is..." — 已刻意留 NT 未接的钩子
- `nt_risk_engine.py` (`src/arx_runner/nt_risk_engine.py`) 有 `NtRiskEngineBridge` 骨架, `__main__.py:176-184` 已 log "pre_trade_bridge_pending_nt_messagebus" 承认在等 MessageBus

用户价值: 让 arx 云端能看到 supertrend 实际交易 (fill 事件 + position 摘要 + 拒单事件), 兑现 custos domain-model §1.5 上报事件 BC。

### 契约证据锚表 (待 Plan 00a close-out 时 executor Foundation Scan 重新实证)

| 引用契约 / 来源 | file:line | 用途 |
|---|---|---|
| `telemetry_actor.py` 骨架 (NT 未接) | `src/arx_runner/telemetry_actor.py:1-4` | 本 plan 接通 NT |
| `NtRiskEngineBridge` 骨架 | `src/arx_runner/nt_risk_engine.py` | 本 plan 接 NT OrderDenied |
| `__main__.py` pre_trade_bridge 待接 | `src/arx_runner/__main__.py:176-184` | log "pre_trade_bridge_pending_nt_messagebus" 撤销点 |
| `ArxNatsClient.publish_telemetry` / `.publish_pre_trade_reject` | `src/arx_runner/nats_client.py` (grep 实证签名) | telemetry_actor + pre_trade_bridge 上报出口 |
| NT MessageBus subscribe API | ps `runner.py:73-79` `_EXTERNAL_STREAM_TYPES_FILTER` + NT `Actor.subscribe` | 参考 filter 白名单 |
| custos domain-model §1.5 上报事件红线 (脱敏 + 摘要 + 不含策略源码) | `docs/domain.md:156-160` | 红线契约 |
| custos telemetry_actor.md | `docs/telemetry_actor.md` | schema versioning + whitelist + buffered uplink |
| Plan 00a NtTradingNodeHost `_active_nodes` dict | `src/arx_runner/nautilus_host.py` (Plan 00a 落地后) | 本 plan 需从此取 node 引用给 telemetry_actor 订阅 |

### Historical lessons 强制引用

- **lesson #14/#33/#33b Foundation Scan iteration**: Plan 00a close-out 后 executor 必先重扫 `nautilus_host.py` 实际 NT 装配代码 + `_active_nodes` 结构再动手 (00a 实施可能对本 plan 的假设有偏差)
- **lesson #17 failure-mode coverage**: NT MessageBus 断连 / uplink buffer 满 / NATS 发失败 / OrderDenied event 结构不匹配 全部需 failure-mode test
- **lesson #21 零静默红线**: silent drop / silent fail / silent retry 路径必接 structlog (setup-pre-commit hook 会 grep)
- **lesson #22 多层 fail-fast 兜底**: telemetry 上报失败**不能**吞 — 记 log + 降级到 local WAL (若已存在); 不能让"云端看不到 fill"变默认状态
- **lesson #25 反 fabricated close-out**: OrderDenied 事件字段名 (`reason` / `denied_at` / `client_order_id`) 必 grep NT 源码 (`nautilus_trader/model/events/order.py`) 实证, 不凭"应该叫这个"推理
- **lesson #26 边界裸用 (tenant_id 拼接)**: telemetry subject `arx.{tenant_id}.telemetry.{session_id}` 拼接前 tenant_id 走 boundary validation (与现有 audit_subscriber 一致)
- **lesson #37 spawner 元层 grep 实证**: drafter 引用 NT 类名 (`Actor` / `TradeReport` / `PositionEvent` / `OrderDenied`) 必 grep NT 源码, 不凭"NT 应该有这些类"推理

## 目标 (Goal)

- **telemetry_actor**: 通过 NT `Actor` 或 `msgbus.subscribe` API 订阅 supertrend 策略产生的 fill / position / pnl 事件, 按白名单 + 采样 + schema-versioned envelope 上报到 NATS `arx.{tenant}.telemetry.{session_id}` subject
- **pre_trade_bridge**: 订阅 NT `OrderDenied` event → 转成 pre-trade reject envelope → 上报 `arx.{tenant}.pre_trade_reject.{runner_id}` subject
- **绑定生命周期**: 与 `NtTradingNodeHost._active_nodes` 联动 — deploy 时 attach subscriber, stop 时 detach; 多 spec 隔离 (每 spec 独立 subscriber + subject `session_id`)

覆盖范围:
- **首 event**: fill / position / OrderDenied (order lifecycle 三关键点; 订单簿明细不上报, domain §1.5 红线)
- **不覆盖**: 完整 order snapshot (太重), 账户 balance (由 reconcile 独立通道)
- **schema 版本**: v1 (与现有 telemetry_actor whitelist 对齐)

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| NT 事件订阅方式 (Actor vs 直接 subscribe msgbus) | **Actor 子类** | NT 官方推荐; 生命周期跟 TradingNode 一致; 天然 async |
| telemetry_actor 与 NtTradingNodeHost 耦合 | **NtTradingNodeHost.deploy 时创建 & attach TelemetryActor 到 node.trader**, stop 时 detach | 避免 telemetry_actor 全局单例吞多个 spec 的事件混流 |
| 上报节流 (fill 事件可能高频) | **v1 每事件即报**, 不批 | 简化实施; supertrend 类趋势策略 fill 频率低 (分钟-小时级); 高频策略未来加 batching |
| OrderDenied → pre_trade_reject subject 分离 | **单独 subject** (`arx.{tenant}.pre_trade_reject.{runner_id}`, 非混 telemetry) | 与 reconcile.md WR-NATS-2 demux 精神一致 — consumer dispatch 表显式 |
| upload 失败降级 | **记 structlog + 记本地 counter, 不 crash** | domain §1.2 红线 "失联≠停止"; NT 本地继续跑, 云端补报由后续心跳/reconcile 走 |

## Task List

**Task 1**: 定义 telemetry envelope schema v1 + fill/position/pnl 事件 payload dataclass

- 文件: `src/arx_runner/telemetry_actor.py` (改, ~50 LOC)
- payload dataclass: `FillEvent` (client_order_id, instrument, side, qty, price, ts_event, fee) + `PositionSnapshot` (instrument, side, qty, avg_px, unrealized_pnl_summary) + `OrderDeniedEvent` (client_order_id, reason, denied_at)
- 契约: 所有 money 字段用 `str(Decimal)` 上线 (与 reconcile.md 红线一致); ts 用 nanosecond int
- 测试: `tests/test_telemetry_envelope.py` (已存在, 扩展)
- 失败模式: (无新增, schema 定义无 IO)

**Task 2**: `TelemetryActor` NT Actor 子类

- 文件: `src/arx_runner/telemetry_actor.py` (改, ~150 LOC)
- 继承 `nautilus_trader.common.actor.Actor` (类似 `Actor`), 在 `on_start` 订阅 `TradeReport` / `PositionEvent` / `OrderDenied` (grep 实证 NT 事件类名)
- 每事件 → 转 payload → `self._nats_client.publish_telemetry(envelope)` (async fire-and-forget, 失败记 log 不 crash)
- 与 `NtTradingNodeHost.deploy` 集成: deploy 时 `actor = TelemetryActor(...); node.trader.add_actor(actor)` (grep 实证 NT `add_actor` API)
- 测试: `tests/test_telemetry_actor.py` (已存在, 扩展) + `tests/test_telemetry_actor_failure_modes.py` (已存在, 扩展 NT MessageBus 断连 case)
- 失败模式: NATS publish fail → log warning; NT event 缺 required 字段 → skip 该 event + counter++; 阻塞 NT engine thread → 违反红线, 用 async task 隔离

**Task 3**: `NtRiskEngineBridge` 接 NT OrderDenied

- 文件: `src/arx_runner/nt_risk_engine.py` (改, ~80 LOC)
- 撤销 `__main__.py:176-184` 的 pending log, 改为真订阅
- OrderDenied event → `PreTradeRejectEnvelope` → `nats_client.publish_pre_trade_reject`
- 集成: 由 `NtTradingNodeHost.deploy` 时 attach 到 node.trader (与 Task 2 同机制)
- 测试: `tests/test_nt_risk_engine.py` (已存在, 扩展 OrderDenied 场景)
- 失败模式: OrderDenied event 结构不匹配 (NT 版本升级致) → 记 `pre_trade_reject_event_shape_mismatch` + skip

**Task 4**: 与 `NtTradingNodeHost` 集成 (deploy/stop 联动)

- 文件: `src/arx_runner/nautilus_host.py` (改, ~30 LOC)
- `deploy` 内在 `node.build()` 之后 `add_strategy` 之前: 创建 `TelemetryActor` + `NtRiskEngineBridge` → `node.trader.add_actor(...)`
- `stop` 内在 `node.stop_async` 之前: 无需显式 detach (NT actor lifecycle 跟 node)
- 测试: `tests/test_nt_trading_node_host.py::test_deploy_attaches_telemetry_and_risk_bridge`
- 失败模式: telemetry/risk bridge 创建失败 → 记 log 不阻断 deploy (fail-safe, 因为主流程 = 交易; 观测面丢失是次级损失)

**Task 5**: 集成测试 (mock NT MessageBus, 断言 event → NATS envelope 流转)

- 文件: `tests/test_nt_telemetry_e2e.py` (新, ~120 LOC)
- 覆盖:
  - `test_fill_event_flows_to_nats`: mock TradingNode + 手动 push fill event → 断言 nats_client.publish_telemetry 被调 + envelope 字段命中
  - `test_order_denied_flows_to_pre_trade_reject_subject`
  - `test_nats_publish_fail_does_not_crash_actor`
  - `test_multiple_specs_isolated_by_session_id`
- 失败模式: 均由子测试覆盖

## 失败模式覆盖契约表 (lesson #17)

| 失败模式 | 触发点 | 测试文件:函数 | reason_code |
|---|---|---|---|
| NATS publish 失败 | `TelemetryActor._on_event` | `test_nt_telemetry_e2e.py::test_nats_publish_fail_does_not_crash_actor` | log `telemetry_publish_failed` |
| NT event 结构不匹配 | `TelemetryActor._normalize` | `test_telemetry_actor.py::test_shape_mismatch_skipped` | log `telemetry_event_shape_mismatch` |
| pre_trade_reject event 结构不匹配 | `NtRiskEngineBridge._on_denied` | `test_nt_risk_engine.py::test_denied_shape_mismatch` | log `pre_trade_reject_event_shape_mismatch` |
| telemetry actor attach 失败 | `NtTradingNodeHost.deploy` | `test_nt_trading_node_host.py::test_deploy_survives_telemetry_attach_failure` | log `telemetry_actor_attach_failed`, deploy 继续 |
| multi-spec envelope 混流 (isolation 失守) | `TelemetryActor.session_id` | `test_nt_telemetry_e2e.py::test_multiple_specs_isolated_by_session_id` | (invariant test) |
| NT MessageBus 断连 (dev / test 环境) | `TelemetryActor.on_stop` | `test_telemetry_actor_failure_modes.py` (已有, 扩展) | log `nt_messagebus_disconnected` |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `src/arx_runner/telemetry_actor.py` | 改 | 加 TelemetryActor NT Actor 子类 + payload dataclass |
| `src/arx_runner/nt_risk_engine.py` | 改 | 接 NT OrderDenied 事件订阅 |
| `src/arx_runner/nautilus_host.py` | 改 | deploy 时 attach TelemetryActor + NtRiskEngineBridge |
| `src/arx_runner/__main__.py` | 改 | 撤销 pre_trade_bridge_pending log |
| `tests/test_telemetry_envelope.py` | 扩 | 加 payload schema 断言 |
| `tests/test_telemetry_actor.py` | 扩 | 加 NT Actor 集成 case |
| `tests/test_telemetry_actor_failure_modes.py` | 扩 | 加 MessageBus 断连 case |
| `tests/test_nt_risk_engine.py` | 扩 | 加 OrderDenied 场景 |
| `tests/test_nt_trading_node_host.py` | 扩 | 加 attach 集成 test |
| `tests/test_nt_telemetry_e2e.py` | 新建 | e2e mock 测试 |

## 验收清单

- [ ] Foundation Scan 重扫 (Plan 00a close-out 后 `nautilus_host.py` 实际状态) 完成, 契约锚点更新
- [ ] `TelemetryActor` 继承 NT `Actor` 通过 grep 实证的类名 (不用推理名)
- [ ] `OrderDenied` event 字段名从 NT 源码 grep 实证
- [ ] 6 处失败模式全 pytest 覆盖
- [ ] `NtTradingNodeHost.deploy` attach telemetry/risk bridge, `stop` 干净收敛
- [ ] session_id 隔离多 spec (subject 分离)
- [ ] `pytest tests/` 全绿
- [ ] silent path (except / skip) 全接 structlog (lesson #21 grep 探针 0 命中)

## 偏离与改进日志 (Deviation Log)

(执行阶段填写)

## 完成报告 (Close-out Report)

(执行完成填写)

## 下一步 (Next)

Plan 00b close-out 后启动 Plan 00c (G6 gate 放宽 + live/testnet 放行 + docker compose e2e 示例)。
