# telemetry_actor — NT MessageBus → NATS 白名单缓冲上传

> Custos 六件套之一。源码：`src/arx_runner/telemetry_actor.py`。

## 模块职责

`telemetry_actor` 把 **NautilusTrader MessageBus** 的执行事件桥接到 NATS phone-home
通道。它是 custos 的观测数据面出口：订单 / 成交 / 持仓 / 净值 / 健康等遥测经这里过滤、
缓冲、上行到 arx 协调层。

设计要点：

- **不在 import 期加载 `nautilus_trader`**：CI / 单测环境不带 NT，actor 通过
  `on_event(name, payload)` 驱动（真 NT MessageBus 回调或 fake 都可）。
- **schema 白名单**：只有构造时声明的 event name 才漏到 NATS，其余在边界丢弃——
  新增 NT event type 不会在 operator opt-in 前意外泄露 PII。
- **有界队列 + 周期 flush**：事件经 bounded `asyncio.Queue` 批量上行。
- **session 内单调 seq**：每条出站消息盖一个 `session_id` 内单调 `seq`；`on_start`
  铸新 `session_id`，runner 重启强制 consumer 侧 watermark 重新对齐
  （domain-model §1 ③）。
- **cross-thread 安全**：`on_event` 跑在 NT MessageBus 派发线程，队列在 asyncio loop
  上；用 `loop.call_soon_threadsafe` 安全交接 envelope，`seq` 变更用
  `threading.Lock` 串行化，防两个并发回调产生重复 / 乱序 seq。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块只向 arx 协调层上行遥测，
> 不对外部客户端暴露任何订阅口。dashboard 看到的遥测经 arx 聚合后由 arx gatekeeper
> 授权分发。*This module's API surface is consumed exclusively by the arx coordination
> layer; no direct external client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `TelemetryActorConfig` | `@dataclass(frozen=True)`（`allowed_event_types`, `queue`） | actor 配置；`allowed_event_types` 是 schema 白名单 |
| `TelemetryPublisher` | `Protocol`：`async publish_telemetry(*, session_id, envelope)` / `async publish_heartbeat_fire_and_forget(*, session_id, envelope)` | NATS client 侧最小契约；真实现是 `ArxNatsClient` |
| `MONEY_FIELD_NAMES` | `frozenset[str]`（`equity`/`qty`/`price`/`pnl`/`notional`/`cumulative_pnl` …） | 必须以 `str(Decimal)` 或 `int` 到达的 money 字段集 |
| `MoneyFieldFloatRejected` | `TypeError` 子类 | money 字段以 `float`（含 `bool`）到达时 fail-fast 抛出 |

`on_event(name, payload)` 是 actor 的驱动入口：白名单命中 → money 字段 float 拒收
→ 入队 → 周期 flush 到 NATS。

## 红线契约

- **零静默丢弃**：白名单 drop / 队列 overflow / 断线重传等 silent path 都接 structlog
  （`telemetry_event_dropped_whitelist` 等），不静默吞（lesson #21）。
- **money math 用 str(Decimal) 不用 float**：`_reject_floats_in_money_fields` 在边界
  fail-fast 拒收 float——binary fraction 会静默腐蚀对 Crucible Python 参考的
  differential-test 不变量（ADR-008 红线）。`bool` 显式拒收（`isinstance(True, float)`
  为 False 但会以 `1.0` round-trip）。
- **PII 边界白名单**：只有显式声明的 event type 漏出，新增 NT event 不会在 operator
  opt-in 前泄露。
- **cross-thread 无数据竞争**：`call_soon_threadsafe` + `threading.Lock` 守 seq 单调，
  是 failure-mode 覆盖契约的一部分（lesson #17）。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G5-A**（money math differential coverage 已收敛） | 遥测 money 字段的 wire 表示对齐 Crucible Python 参考；float reject 守此不变量 | 每条含 money 字段的遥测出站时 |
| **G5-B**（arx Rust internal BC 平替切换） | telemetry crate wire schema 演化受 differential coverage 约束（休眠中，crucible-rust 平替触发时启用） | crucible-rust 平替触发时 |

## 未来演化路线

- **短期**：`allowed_event_types` 白名单随 NT event 类型扩充，配套 schema 版本化
  （`payload_schema_version` bump）。
- **中期**：断线重传的 WAL 缓冲策略调优（backpressure / 丢弃优先级），队列深度可分档配置。
- **长期**：遥测 schema 通过 versioned API 契约与 arx 协调层的 `TransportEnvelope`
  canonical 类型对齐，防多 envelope 字段名漂移（lesson #20）。
