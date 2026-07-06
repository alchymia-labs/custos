# nats_client — NATS JetStream client + transport envelope

> Custos 六件套之一。源码：`src/arx_runner/nats_client.py`。

## 模块职责

`nats_client` 是 Custos 出网的**唯一传输层**：封装 NATS JetStream client + 统一的
transport envelope 模型 + subject 命名规则。所有 phone-home（heartbeat / telemetry /
deployment status / enrollment / recon_result）都经这里序列化上行到 arx 协调层。

统一 transport envelope（每条 NATS 消息）：

```json
{
  "envelope_version": 1,
  "event_id": "<uuid>",
  "tenant_id": "<tenant>",
  "occurred_at": "<RFC3339 nanoseconds>",
  "payload_schema_version": 1,
  "payload": { ... },
  "ordering": { "session_id": "<uuid>", "seq": <int> }
}
```

subject 命名统一 `arx.{tenant}.{kind}.{...}`；heartbeat 走
`arx.{tenant}.heartbeat.{runner_id}`，**at-most-once fire-and-forget**（不阻塞 ack）。
telemetry / spec / status 各自扩展同一 envelope，subject + 投递语义见 plan-index §6。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块只向 arx 协调层 publish，
> runner 侧从不接受不可信 bytes（无对称 `from_bytes`）。外部访问 custos 状态经 arx
> gatekeeper 中转。*This module's API surface is consumed exclusively by the arx
> coordination layer; no direct external client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `NatsEnvelope` | `@dataclass`（`event_id`/`tenant_id`/`occurred_at`/`payload`/`envelope_version=1`/`payload_schema_version=1`/`ordering=None`）+ `to_bytes()` | 传输 envelope；单向序列化，无 `from_bytes` |
| `OrderingMeta` | `@dataclass(frozen=True)`（`session_id`, `seq`），`seq >= 0` | telemetry-only 排序；跨 session 不可比 |
| `ArxNatsClient` | `async connect()` / `async close()` / `async publish_heartbeat(...)` / `async publish_fire_and_forget(subject, payload)` / `async publish_telemetry_envelope(...)` / `async publish_deployment_status(...)` / `async publish_enrollment(*, payload)` | JetStream client |
| `build_subject` | `build_subject(tenant, kind, *path_parts) -> str` | plan-index §6 subject builder；空 token 抛错 |
| `build_heartbeat_envelope` / `heartbeat_subject` | 构造 heartbeat envelope / subject | payload 四字段 pin（runner_id / uptime_secs / active_deployments / health） |

WAL 缓冲（`stash` / `drain` / `forget` / `depth`）：telemetry 在断线时暂存 sqlite WAL，
重连后补发；**heartbeat 不 WAL 缓冲**（at-most-once，过期心跳无补发价值）。

## 红线契约

- **tenant 隔离（subject 命名空间）**：所有 subject 以 `arx.{tenant}.…` 开头；空
  tenant / kind / path token 在 `build_subject` 直接 `ValueError` 抛错，防 typo 静默
  路由到 `arx..heartbeat.`（F4/IN-NATS-1）。
- **零静默**：`nats_fire_and_forget_noop_disconnected`、`wal_stash`、`wal_drain_failed`
  等 silent path 都接 structlog（lesson #21），断连 / 丢弃 / 重传都可观测。
- **单向信任**：runner 侧从不 `from_bytes` 反序列化不可信 bytes——只 publish，不消费
  外部指令流（控制走声明式 reconcile 拉取，不走命令推送）。
- **at-most-once heartbeat**：heartbeat fire-and-forget，不阻塞 ack、不 WAL 补发，
  过期心跳无意义（plan-index §6）。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G5-A**（wire schema 演化 / money differential 已收敛） | envelope `payload_schema_version` 版本化承载 money wire 演化，对齐 Crucible Python 参考 | wire schema 变更时 |
| **G5-B**（arx Rust internal BC 平替切换） | canonical envelope 类型（`TransportEnvelope`）字段命名对齐受平替 gate 约束（休眠中） | crucible-rust 平替触发时 |

## 未来演化路线

- **短期**：envelope canonical 类型统一——`schema_version` / `payload_schema_version`
  等同语义字段收口到 plan-index §6 单一权威表，防多 envelope 字段名漂移（lesson #20）。
- **中期**：WAL 缓冲的持久化策略（sqlite → 更强的本地队列）与背压控制调优。
- **长期**：subject 命名与投递语义通过 versioned API 契约与 arx 协调层同步，支撑外部
  custos 版本滞后 arx 半年仍能互操作（ADR-012 v4 契约驱动开发纪律）。
