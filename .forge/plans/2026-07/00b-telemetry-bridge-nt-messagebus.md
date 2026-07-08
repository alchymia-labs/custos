# 00b - telemetry_actor 接 NT MessageBus + pre_trade_bridge 接 NT OrderDenied

> **Status**: ✅ Completed (2026-07-08)
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

> 触发点 / 测试位置以 Q1=A 实现为准 (原表按 Q1=B "TelemetryActor 子类" 假设写；实现走 duck-typed bridge，真实位置如下，lesson #25 反 fabricated)。

| 失败模式 | 触发点 | 测试文件:函数 | reason_code |
|---|---|---|---|
| NATS publish 失败 | `TelemetryActor._drain_batch_starting_with` | `test_nt_telemetry_e2e.py::test_nats_publish_fail_does_not_crash_actor` | log `telemetry_publish_failed` |
| NT event 结构不匹配 | `NtTelemetryBridge._forward` (normalize KeyError) | `test_telemetry_nt_bridge.py::test_shape_mismatch_skipped` | log `telemetry_event_shape_mismatch` |
| pre_trade_reject event 结构不匹配 | `NtRiskEngineBridge.on_order_denied` (shape guard) | `test_nt_risk_engine.py::test_denied_shape_mismatch` | log `pre_trade_reject_event_shape_mismatch` |
| telemetry actor attach 失败 | `NtTradingNodeHost._attach_observability` | `test_nt_trading_node_host.py::test_deploy_survives_telemetry_attach_failure` | log `telemetry_actor_attach_failed`, deploy 继续 |
| multi-spec envelope 混流 (isolation 失守) | `TelemetryActor.session_id` (per-spec 实例) | `test_nt_telemetry_e2e.py::test_multiple_specs_isolated_by_session_id` | (invariant test) |
| NT MessageBus 断连 / unavailable | `NtTelemetryBridge.bootstrap` (None bus fail-fast) | `test_telemetry_nt_bridge.py::test_nt_messagebus_disconnected_logs_and_degrades` | log `nt_messagebus_disconnected` |
| telemetry forward 触达 NT thread 崩溃 (额外) | `NtTelemetryBridge._forward` (on_event raise) | `test_telemetry_nt_bridge.py::test_bridge_forward_never_crashes_on_actor_error` | log `telemetry_forward_failed` (红线 0.3) |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `src/arx_runner/telemetry_actor.py` | 改 | 加 TelemetryActor NT Actor 子类 + payload dataclass |
| `src/arx_runner/nt_risk_engine.py` | 改 | 接 NT OrderDenied 事件订阅 |
| `src/arx_runner/nautilus_host.py` | 改 | deploy 时 attach TelemetryActor + NtRiskEngineBridge |
| `src/arx_runner/__main__.py` | 改 | 撤销 pre_trade_bridge_pending log |
| `tests/test_telemetry_nt_bridge.py` | 新建 (实际) | normalizer money-safe + bridge dispatch/filter/shape/disconnect (Task 1+2) — 替代不存在的 `test_telemetry_envelope.py` |
| `tests/test_nt_risk_engine.py` | 扩 | wildcard topic + dispatcher filter + real-NT OrderDenied + shape mismatch |
| `tests/test_nt_trading_node_host.py` | 扩 | deploy attach + attach-failure survives + skip-without-client + stop |
| `tests/test_nt_telemetry_e2e.py` | 新建 | e2e 数据路径 (fill/denied/publish-fail/isolation) + real-NT 变体 |
| ~~`tests/test_telemetry_envelope.py`~~ | DRIFT | plan 说"已存在"，实际不存在；envelope 契约由 `test_nats_envelope.py`+`test_telemetry_money_contract.py` 覆盖，payload 契约落 `test_telemetry_nt_bridge.py` |
| ~~`tests/test_telemetry_actor.py` / `_failure_modes.py`~~ | 未改 | Q1=A 保留 duck-typed，14 个现有 test 不动 (契约稳定验证) |

## 验收清单

- [x] Foundation Scan Round 4+ 完成 (NT 1.230 msgbus/Actor/OrderDenied 实证), 契约锚点更新 (见偏离日志 Foundation Scan iteration log)
- [x] TelemetryActor 集成 NT MessageBus 通过实证的 subscribe API (Q1=A duck-typed bridge，非 Actor 子类；`events.order.*`/`events.position.*` wildcard 经 grep+empirical 实证)
- [x] `OrderDenied` event 字段名从 NT 源码 grep 实证 (无 side/qty/price/rule_id/ts_seconds；真实 = reason/instrument_id/client_order_id/ts_event)
- [x] 6 处失败模式全 pytest 覆盖 (+1 额外 forward-crash guard；契约表点名 test 全 grep 实存)
- [x] `NtTradingNodeHost.deploy` attach telemetry/risk bridge, `stop` 干净收敛 (drain + cancel actor loops)
- [x] session_id 隔离多 spec (per-spec TelemetryActor 各自 uuid7 session_id + subject 分离)
- [x] `make verify` 全绿 (base 156 pass/7 skip；NT 205 pass/0 skip)
- [x] silent path (except / skip) 全接 structlog (lesson #21 grep 探针 0 命中)
- [x] 契约表点名 `test_*` 函数 grep 实存 (lesson #25，6/6 命中)

## 偏离与改进日志 (Deviation Log)

### Foundation Scan iteration log (Round 4+, executor, as-of Plan 00a/00c close-out)

NT 1.230.0 installed (`--extra nt-runtime`, py3.13). Round 4 grep + empirical probes against site-packages:

- **NT API (lesson #25/#37 实证)**: `MessageBus` = `nautilus_trader.common.component.MessageBus`; `subscribe(topic, handler, priority=0)`, topic supports `*`/`?` wildcards (empirically: `events.order.*` dispatches a publish on `events.order.ST-1`). `node.kernel.msgbus` is the subscribe path (`node.kernel` is an instance attr set in node.py:71). `node.trader.add_actor(actor)` exists.
- **NT publish topics** (execution/engine.pyx:910/918/926): order events → `events.order.{strategy_id}`; position → `events.position.{strategy_id}`; fills → `events.fills.{instrument_id}`.
- **NT event `to_dict`** is the static form `type(event).to_dict(event)` (instance `.to_dict()` raises). Money fields arrive as `str`; enums via `*_to_str` ("BUY", not `str(OrderSide.BUY)=='1'`). So the telemetry normalizer must use `to_dict`, never raw `str(property)`.
- **OrderDenied real fields** (order.pyx): `trader_id / strategy_id / instrument_id / client_order_id / venue_order_id / account_id / reason / reconciliation / id / ts_event / ts_init`. No `side / quantity / price / rule_id / reference_price / ts_seconds`.

### DEVIATION: DEV-00B-ARCH-DECISIONS (Q1/Q2/Q3)
- **等级**: 低
- **原因**: handoff §3 三个架构决策交 executor 判定
- **决定**:
  - **Q1 = A (duck-typed on_event + NT MessageBus subscribe adapter)** — 现有 `TelemetryActor.on_event(str, dict)` 契约不变, 14 个现有 telemetry test 全绿, telemetry_actor.py 保持 NT-import-free (base install 可测试), money gate 留在 on_event 边界. 方案 B (继承 NT Actor) 无红线必要且破坏现有单测.
  - **Q2 = A (dict payload, 不引入 dataclass)** — normalizer 在边界产出 money-safe dict, key 用 MONEY_FIELD_NAMES 兼容名 (qty/price/pnl) 让现有 money gate 校验; dataclass 无 wire 边界收益 (money 已在 gate 校验).
  - **Q3 = deploy-per-spec** — NT MessageBus 仅在 `node.build()` 后存在于 deploy 内, `__main__.py` 全局单例无法订阅 per-node msgbus; per-spec TelemetryActor 天然 session_id 隔离. `__main__.py` pending-log bridge 实例化改为 deploy 内 attach.
- **更新的文档**: 本 plan; 关键设计决策表 Q1 已与实现对齐

### DEVIATION: DEV-00B-DEAD-SUBSCRIPTION (nt_risk_engine reject bridge 双重死 / doubly dead)
- **等级**: 中 (修正既有 correctness bug, 不改 wire 契约)
- **原因 (双根因, 任一独立致死 — reject bridge 事实上从不触发)**:
  - **根因 A — literal topic mismatch**: `nt_risk_engine.py:179` 订阅字面量 `"events.order.OrderDenied"`, 但 NT 所有 order event 都发到 `events.order.{strategy_id}` (`execution/engine.pyx:910` + `:1341-1343` 实证) — 字面 topic 永不匹配 = dead subscription. `test_bootstrap_subscribes_when_bus_present` 只断言 subscribe 被调用, 未断言 topic (happy-path gap, lesson #17), 让 bug 潜伏.
  - **根因 B — async handler on sync MessageBus**: NT `MessageBus` 同步调用 handler (`common/component.pyx:2834 sub.handler(msg)`, 无 `await`/coroutine 检查). 原代码把 `async def on_order_denied` 直接 subscribe → handler 返回一个从不被 await 的 coroutine → 静默丢弃. 即便根因 A 修好, publish 也永不发生.
- **决定**:
  - 根因 A: 订阅改 `events.order.*` (wildcard, NT `portfolio.pyx:197` / `risk/engine.pyx:189` 同惯用 pattern); 强化 bootstrap test 断言 topic == `events.order.*`.
  - 根因 B: 加同步 dispatcher `_on_order_event`, 用 **concrete type discriminator** `type(event).__name__ == "OrderDenied"` 过滤, 再 `run_coroutine_threadsafe` (off-loop) / `ensure_future` (on-loop) 双路调度 async `on_order_denied`, publish 失败 log (`pre_trade_reject_publish_failed`, 对账不静默).
  - **type discriminator 硬约束 (safety-validator block-level 实证)**: NT `order.pyx` 有 4 个 order event 类共享 `reason` 字段 (OrderDenied / OrderRejected / OrderModifyRejected / OrderCancelRejected), **禁** `hasattr(reason)` / attribute-set / duck-typed 判据 (会误分类 OrderRejected 为 pre-trade denial → 伪造 reject 语义污染). 用 concrete 类名匹配 (dev-friendly optional-NT-import 场景用字符串 fallback, 已获 approve). `on_order_denied` 内的 `hasattr` 是**已 type-matched 之后的 shape guard**, 非分类器, 不违反此约束.
  - 测试: dispatcher 过滤 live-guard (`test_dispatcher_ignores_non_denied_order_events`) + real-NT OrderDenied (`test_dispatcher_forwards_real_order_denied`, lesson #25 跑真 NT 对象).
- **实证记录**: tdd-enforcer close-out report (独立跑真 NT OrderDenied 对象 + grep `order.pyx:637-680 OrderDenied.__init__` 核验真实字段) 为第一手证据.
- **更新的文档**: 本 plan; nt_risk_engine.py; test_nt_risk_engine.py

### DEVIATION: DEV-00B-ORDERDENIED-FIELDS (OrderDenied 无 side/qty/price/rule_id)
- **等级**: 低
- **原因**: 骨架 `on_order_denied` getattr 了 `side/quantity/price/rule_id/reference_price/ts_seconds` — 真实 NT OrderDenied 无这些字段, getattr 静默默认.
- **决定**: 保持 ducktyped getattr (real 事件缺字段优雅降级为空, fake 测试仍绿); `ts_seconds` 改为优先读 real `ts_event`(ns)→秒派生; 5 字段 wire 契约不变 (fingerprint 退化为 (symbol, ts) 相关句柄, docstring 已声明非 tamper-evidence anchor). 加 real-NT OrderDenied test 证明对真实契约生效.
- **更新的文档**: 本 plan; nt_risk_engine.py

### DRIFT (plan 锚点): `test_telemetry_envelope.py` 不存在
- plan Task 1 说 "tests/test_telemetry_envelope.py (已存在, 扩展)", 实际 tests/ 无此文件; envelope 契约由 `test_nats_envelope.py` + `test_telemetry_money_contract.py` 覆盖. Task 1 的 payload 契约测试落到 telemetry 侧 (money-safe normalizer test)，不新建 test_telemetry_envelope.py。

### DEVIATION: DEV-00B-LESSON-29-EXTENSION (git 历史查询副作用覆盖工作区 — 生态 lesson #29 扩展)
- **等级**: 低 (编排事故, 已即时修复, 无产出损失)
- **事件**: 实施期间 tdd-enforcer-00b 为对比历史版本用了 `git stash` + `git checkout 232c5a6 -- .` (后者非只读, 覆盖工作区), 意外把 executor 未 commit 的 plan 偏离日志编辑挪进 stash 且把 `src/arx_runner/telemetry_actor.py` 覆盖回旧版. tdd-enforcer 立即 `git checkout HEAD -- telemetry_actor.py` + `git stash pop` 修复, grep 核验三段 deviation 完整. executor close-out 前二次核对 (`git show HEAD:<plan>` grep 4 段 deviation 全在 + telemetry_actor 4 符号全在 + 工作树 clean) 确认无 stash-pop 遗漏.
- **根因**: `git checkout <ref> -- .` 与 `git stash` 组合不是只读操作, 会覆盖工作区 — 与生态 lesson #29 "校验类操作副作用覆盖 host" 同源 (AI 默认某操作只读, 实际有写副作用).
- **预防**: 历史版本查询用 `git show <ref>:<path>` (stdout only, 零副作用) 或 `git diff <ref1> <ref2> -- <path>`; 绝不用 `git checkout <ref> -- .` / `git checkout <ref> -- <path>` 做"只读对比" (它写工作区).
- **Binding**: 生态 `historical-lessons.md` #29 加 "git 历史查询" 子条; custos 侧 `.claude/rules/historical-lessons.md` #29 可加 alias. tdd-enforcer (事故 dogfood 受害者+受益者) 与 executor close-out 阶段协作署名补写扩展文本.
- **更新的文档**: 本 plan; close-out marker acknowledge; (lesson 文本扩展由 tdd-enforcer 主笔, executor 收口 acknowledge)

## 完成报告 (Close-out Report)

- **完成日期**: 2026-07-08
- **总 Task 数**: 5 (+ Foundation Scan Round 4+ + self-reflect)
- **偏离数**: 3 (DEV-00B-ARCH-DECISIONS / DEV-00B-DEAD-SUBSCRIPTION / DEV-00B-ORDERDENIED-FIELDS) + 1 plan-anchor DRIFT (test_telemetry_envelope.py 不存在)
- **验证结果**: 全部通过
- **实施 commit 范围**: `93dc631`..`e688242` (6 commits)
  - `93dc631` telemetry NT event normalizers + event-type whitelist (Task 1)
  - `6a8768f` NtTelemetryBridge — NT MessageBus order/position → TelemetryActor (Task 2)
  - `7a329b3` NtRiskEngineBridge dead subscription + real OrderDenied fields (Task 3)
  - `bf02ad5` NtTradingNodeHost.deploy attaches telemetry + reject bridges (Task 4)
  - `fc5e3d8` end-to-end telemetry + pre-trade-reject flow (Task 5)
  - `e688242` self-reflect round 1 — hold refs to fire-and-forget tasks
  - (close-out docs commit 随后，仍在 worktree branch 内)
- **契约影响**: 无 wire 契约变更 (telemetry envelope + PreTradeRejected 5 字段不变)。新增内部 API: `normalize_fill_event` / `normalize_position_event` / `NtTelemetryBridge` / `DEFAULT_TELEMETRY_EVENT_TYPES` (telemetry_actor.py)；`NtTradingNodeHost` 增可选 telemetry 装配参数。设计文档 `docs/design/*.md` 未改 (本 plan 未触碰 6 模块契约边界的对外声明；telemetry_actor/nautilus_host 内部实现)。
- **红线守护**: Non-Custodial 4 红线全数守住 (grep 记录 0 命中):
  - 0.1 Key/KEK 不出进程: telemetry payload 只 curated 摘要字段 (symbol/side/qty/price/pnl/fee/ts)，无 credential；异常日志经 `_sanitize_exception` 脱敏
  - 0.2 G6 gate 不绕过: 未触碰 G6 逻辑；attach 在 deploy 内、G6 前置于 reconciler 不变
  - 0.3 失联≠停止: telemetry/risk 上报失败 → log + counter，不 crash NT 线程 (bridge `_forward` catch + deploy attach fail-safe)
  - 0.4 Money Decimal + wire str: normalizer 用 `to_dict` 取 str money，Money 拆 value+ccy 去后缀，`fee` 入 MONEY_FIELD_NAMES gate；0 处 float money
- **失败模式覆盖**: 7 个 (契约表 6 + forward-crash guard 1)，全 pytest 实存 (lesson #25 grep 6/6 命中)。新增测试文件: `test_telemetry_nt_bridge.py` (10)、`test_nt_telemetry_e2e.py` (5)；扩展 `test_nt_risk_engine.py` (+4)、`test_nt_trading_node_host.py` (+4)
- **验证证据**: base (no NT) `make verify` = 156 passed / 7 skipped；NT `make verify` + `make test-nt` = 205 passed / 0 failed；ruff fmt+lint clean。`test_wire_shapes.py` 排除于 baseline (Plan 01 DEV-01-WIRE-FIXTURES，非本 plan 引入)
- **遗留项 / follow-up (peer-review candidates)**:
  - **F1 heartbeat 冗余**: 每个 deploy 的 TelemetryActor 各发 heartbeat (默认 10s)，与 `__main__.py` runner fallback `_heartbeat_loop` 同 subject 并存 (多 session_id)。v1 无害 (consumer 按 session dedup)，但可整合为单一 liveness 源 (__main__ docstring 声明"actor lands 后 retire fallback loop"—— 本 plan per-spec 多 actor 使该整合非平凡，留 follow-up)
  - **F2 fingerprint 弱化**: 真实 OrderDenied 无 side/qty/price，fingerprint 退化为 (symbol, ts) 相关句柄；如需强 fingerprint，未来可从 NT order cache 按 client_order_id 补全 (需扩 wire 契约，中风险)
  - **F3 tenant_id 空兜底**: `_attach_observability` 用 `self._tenant_id or ""`；CLI 恒传 tenant_id，空值仅防御 (build_subject 会在 publish 时对空 token fail-fast)

## 下一步 (Next)

Plan 00b close-out 后启动 Plan 00c (G6 gate 放宽 + live/testnet 放行 + docker compose e2e 示例)。
