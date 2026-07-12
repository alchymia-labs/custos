# nats_client — NATS JetStream client + transport envelope

> Custos 六件套之一。源码：`src/custos/core/nats_client.py`。

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
DeploymentSpec 使用 `custos.contracts.DeploymentMessage`，其 payload 固定为：

```json
{
  "strategy_id": "supertrend-sandbox",
  "spec": { "spec_id": "...", "generation": 1 }
}
```

wrapper 让 consumer 只拿 envelope bytes 也能恢复并校验 canonical subject；严格的
`DeploymentSpec` 本身不混入 transport routing 字段。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：phone-home 只向 arx 协调层 publish；
> 唯一入站 bytes 是声明式 DeploymentMessage，先做 envelope/tenant/spec 严格校验再进入
> reconciler。外部访问 custos 状态仍经 arx
> gatekeeper 中转。*This module's API surface is consumed exclusively by the arx
> coordination layer; no direct external client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `NatsEnvelope` | `@dataclass`（`event_id`/`tenant_id`/`occurred_at`/`payload`/`envelope_version=1`/`payload_schema_version=1`/`ordering=None`）+ `to_bytes()` | 传输 envelope；单向序列化，无 `from_bytes` |
| `DeploymentMessage` | `create(tenant_id, strategy_id, spec)` / `parse(data, expected_tenant_id)` / `to_bytes()` | DeploymentSpec 唯一 producer/consumer seam；wrapper payload 恢复 subject，parse 验证 UUIDv7、版本、tenant 与 strict spec |
| `OrderingMeta` | `@dataclass(frozen=True)`（`session_id`, `seq`），`seq >= 0` | telemetry-only 排序；跨 session 不可比 |
| `ArxNatsClient` | `async connect()` / `async close()` / `async publish_heartbeat(...)` / `async publish_fire_and_forget(subject, payload)` / `async publish_telemetry_envelope(...)` / `async publish_deployment_status(...)` / `async publish_enrollment(*, payload)` | JetStream client |
| `build_subject` | `build_subject(tenant, kind, *path_parts) -> str` | plan-index §6 subject builder；空 token 抛错 |
| `build_heartbeat_envelope` / `heartbeat_subject` | 构造 heartbeat envelope / subject | payload 四字段 pin（runner_id / uptime_secs / active_deployments / health） |

WAL 缓冲（`stash` / `drain` / `forget` / `depth`）：telemetry 在断线时暂存 sqlite WAL，
重连后补发；**heartbeat 不 WAL 缓冲**（at-most-once，过期心跳无补发价值）。

## Standalone JetStream topology

Standalone deployments explicitly run:

```bash
arx-runner nats bootstrap --profile standalone \
  --nats-url nats://nats:4222 --tenant-id acme
```

`arx-runner start` never creates streams implicitly. The bootstrap waits for NATS, then
idempotently reconciles two FILE-backed streams whose names use the first 12 uppercase hex
characters of SHA-256 over the validated tenant id:

| Stream suffix | Subjects | Managed limits |
|---|---|---|
| `DEPLOYMENT` | `arx.<tenant>.deployment_spec.>` | `max_msgs_per_subject=1` |
| `OBSERVED` | `deployment_status`, `heartbeat`, `telemetry`, `snapshot`, `pre_trade_reject`, and `enrollment` tenant subjects | default retention limits |

Both streams carry `owner=custos`, `profile=standalone`, and `tenant_hash` metadata. Missing
streams are created and owned-stream drift is updated. Bootstrap does not enumerate or delete
unknown streams, and it refuses to take over a deterministic-name collision without matching
ownership metadata.

## 红线契约

- **tenant 隔离（subject 命名空间）**：所有 subject 以 `arx.{tenant}.…` 开头；空
  tenant / kind / path token 在 `build_subject` 直接 `ValueError` 抛错，防 typo 静默
  路由到 `arx..heartbeat.`（F4/IN-NATS-1）。
- **零静默**：`nats_fire_and_forget_noop_disconnected`、`wal_stash`、`wal_drain_failed`
  等 silent path 都接 structlog（lesson #21），断连 / 丢弃 / 重传都可观测。
- **声明式入站最小面**：runner 不接受 imperative command；唯一入站控制消息是
  `DeploymentMessage` desired-state snapshot。`parse()` 严格验证 envelope version、UUIDv7、
  tenant、routing wrapper 与 DeploymentSpec，失败不会触达 Vault/G6/host。
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

## 多引擎 subject scheme (reserved) — v2 subject engine-layer segment

> **状态：reserved / deferred**（DEV-05-SUBJECT-V2-DEFER，Plan 05 CEO 决策）。本节只
> 文档化未来的 v2 subject 方案（engine-layer segment 插入，见下），**Plan 05 不改代码** ——
> `build_subject` (`nats_client.py:141`) 仍产出 v1 scheme，`arx.{tenant}.{kind}.{...}`（`:151`）。

Custos 现阶段只支持 NautilusTrader 一个引擎，subject 命名空间不需要区分 engine 来源。
未来第二个引擎（hummingbot / freqtrade / athanor / nt-rust，见
[`docs/engines/`](../engines/)）接入时，同一 runner 上可能并存多引擎部署，v1 scheme 会
在 NATS 层无法区分事件源自哪个引擎。

**v2 方案（未来落地时采纳）**：subject 插入一个 `{engine}` segment：

```
v1（现行）: arx.{tenant}.{kind}.{...}
v2（reserved）: arx.{tenant}.{engine}.{kind}.{...}
```

- `{engine}` 取值对齐 `src/custos/engines/<name>/` 目录名（如 `nautilus` / `hummingbot`）
- envelope 需新增 `subject_scheme_version` 字段（区分 v1/v2 消费者，dual-read 过渡期）
- arx 消费端的 subscription pattern 需同步更新（跨仓协调，非 custos 单方决定）

**已知 tech-debt 迁移点**：`src/custos/core/reconcile.py:127` 的 recon-result subject
是手写字符串拼接（`f"arx.{self._tenant_id}.recon_result.{self._runner_id}.{self._session_id}"`），
**不走** `build_subject`。v2 落地时这一处连同 `build_subject` 本身都需要迁移；现在
`build_subject` 已对空 token 做 `ValueError` 防御（红线 lesson #26 boundary constant
校验），但手写旁路没有同等防御，是 v1 阶段就存在的已知裂缝，v2 迁移时应一并收口到
`build_subject`（或其 v2 版本）。

**为什么现在不上 v2（DEV-05-SUBJECT-V2-DEFER 摘要，决策全文见 Plan 05 偏离日志）**：
无第二引擎实际接入前，`{engine}` segment 是投机性抽象；且 v2 改动会牵动 arx 侧
subscription pattern，是跨仓协调而非 custos 单仓可闭环的变更。留到真正接入第二引擎的
那个 plan 再一次性上齐（含 arx 侧同步），比现在预先埋一个没有消费者验证过的抽象更聚焦。
