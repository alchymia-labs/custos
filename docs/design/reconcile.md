# reconcile — 声明式部署 reconcile loop + 对账上传

> Custos 六件套之一。源码：`src/custos/core/deployment_reconciler.py`（声明式部署
> loop）+ `src/custos/core/reconcile.py`（对账结果上传）。

## 模块职责

`reconcile` 是 Custos 的**控制模型核心**：它把「命令式（平台 `docker run`）」换成
「**声明式 reconciliation**」——runner 拉取期望态（`DeploymentSpec`），本地把
NautilusTrader 进程对齐到期望态，再把实际态（`DeploymentStatus`）回报云端。这是真
自托管区别于中心化编排的根本（architecture §1 信任边界）。

两个协作面：

- **`DeploymentReconciler`（`deployment_reconciler.py`）**：云端经 NATS 下发
  `DeploymentSpec` → runner 按 `generation` 幂等比对 → 调 `nautilus_host` 起/停/
  重配 NT → 经 NATS 回报 `DeploymentStatus`。level-triggered、失联≠停止。
- **`ReconcileUploader`（`reconcile.py`）**：把 NT 产出的一次对账比较
  （balance / position / order / fill）包进标准 NATS envelope，经专用
  `recon_result` subject 上报，供后端 `ReconciliationService` 消费。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块的 `DeploymentSpec` 来源与
> `DeploymentStatus` / `recon_result` 去向都是 arx 协调层 gateway，不对外部客户端
> 暴露。custos 不直连 Crucible——arx 收编后再与 Crucible 对齐。*This module's API
> surface is consumed exclusively by the arx coordination layer; no direct external
> client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `DeploymentReconciler` | dataclass(`nats_client`, `tenant_id`, `runner_id`, `execution_engine`, `credential_vault`, `readiness`, `drift_threshold=3`) | 声明式 reconcile loop；subscription 采用 bounded exponential backoff |
| `NautilusHostProtocol` | `async deploy(spec, credential) -> str` / `async reconfigure(spec)` / `async stop(spec_id)` / `supports_live() -> bool` / `supports_venue(venue) -> bool`（后二为 sync capability） | reconciler 依赖的 host 契约（duck-typed）；`--engine nautilus` 选择真实 host，`--engine noop` 仅供 sandbox/dev contract test |
| `ReadinessFile` | `mark_ready(strategy_id, nats_connected, deployment_subscription)` / `clear()` | 原子 JSON readiness；subscription 建立后写入，丢失或退出时删除 |
| `ReconResult` | `@dataclass(frozen=True)`（`dimension`/`domain`/`source_amount`/`target_amount`/`tolerance`/`in_flight_count`/`deployment_spec_id`/`scope` …） | 一次对账比较结果，字段镜像后端 `reconciliation::service::ReconResult` |
| `ReconcileUploader.run_reconciliation_cycle` | `async run_reconciliation_cycle() -> list[ReconResult]` | NT 对账 API 集成 stub（返回 `[]`，不返回假数据） |
| `ReconcileUploader.upload_recon_result` | `async upload_recon_result(result, seq) -> None` | 序列化 + publish 一次比较 |

`recon_result` 走**专用 subject**（`arx.{tenant}.recon_result.{runner_id}.{session_id}`，
plan-index §6 WR-NATS-2 demux），不混在 telemetry 流里，让 consumer dispatch 表保持
显式。money 字段以 `str(Decimal)` 上线（见 `ReconResult.to_payload`）。

## 红线契约

- **云宕机降级不影响本地 reconcile**：NATS 断连时 reconcile loop 继续运行，本地 NT
  不停（`失联≠停止`，domain-model L229）；重连后补报最新 status。对应 CLAUDE.md
  「云宕机不影响本地交易」红线。
- **对账不静默**：`recon_result` 独立 subject + silent path 必接 structlog
  （lesson #21）；账实不符不能被吞。stub `run_reconciliation_cycle` 返回 `[]` 而非
  假数据——「一个撒谎的 stub 比什么都不做的 stub 更糟」。
- **money math 用 str(Decimal)**：`ReconResult` 的金额字段在 wire 上是
  `str(Decimal)`，后端反序列化为 `rust_decimal::Decimal`，守 differential-test 不变量。
- **幂等 + level-triggered**：同 `generation` 多次到达不重复执行，防重放导致重复起停。
- **严格 consumer contract**：每个 payload 先经过
  `custos.contracts.DeploymentMessage.parse()` 恢复 canonical subject 并校验 tenant，内部 spec
  再经过 `DeploymentSpec.model_validate()`；未知字段、generation 0、无效 lifecycle、
  缺失 sandbox balances 或 live code hash 都在 Vault/G6/host 之前拒绝。host 只收到
  `model_dump(mode="json")` 的规范化 dict，`strategy_config` 保持原值。

## 失联降级（Runtime Fulfillment of Red-line 0.3）

红线 0.3「失联 ≠ 停止」的 runtime 兑现由三层 fail-fast 结构性守护（lesson #22 / #28
独立可测），每层由引擎无关的 core 模块承担，从 `ExecutionEngineProtocol` Tier-2
方法读引擎侧状态：

| 层 | 模块 | 触发条件 | Tier-2 依赖 | 动作 |
|----|------|---------|-------------|------|
| Soft cap | `core/local_cap.py` (`RunnerNotionalCap`) | `current_open + new ≥ max_notional_per_runner` | `get_open_notional` | 拒绝新单 → `runner_cap_exceeded` structlog + 尝试 wire `PreTradeRejected`（arx 失联时 log-only） |
| Hard breaker | `core/fallback_breaker.py` (`FallbackBreaker`) | `open_notional > max_notional` 或 `drawdown_pct > max_drawdown_pct` | `get_open_notional` + `get_engine_status.current_equity` | 首次触发 `flatten_positions` 每个 active spec + 冻结新单（`allows_new_orders=False`）；后续 tick 不重复 flatten |
| Zombie watchdog | `core/zombie_watchdog.py` (`ZombieWatchdog`) | `check_engine_connected` 连续 `disconnected` 超过 `grace_secs` | `check_engine_connected` | 本地升级 `phase=degraded` + `health.reason=engine_disconnected_zombie`，`_report_status` 试图上报 |

Composition root（`cli/main.py::_build_reconciler`）实例化三守护并注入
`DeploymentReconciler`，每个 poll tick 依次调用 `_watchdog_tick` / `_breaker_tick`
之后再处理云端消息——所以即便 `sub.next_msg` 抛异常，本地守护也已经跑过一轮。
`test_arx_disconnect_long_run_guards_persist`（60 tick 无云端）证明守护随时间持续
生效、breaker 首次 trip 后不重复 flatten、reconciler 状态无泄漏。

## Subscription retry and readiness

Initial subscribe failure does not exit the reconciler. It retries indefinitely with bounded
exponential backoff (`0.25s × 2`, capped at `5s`), and the stop event interrupts each backoff
slice. `_watchdog_tick` and `_breaker_tick` continue at `poll_interval_secs` while subscription
is unavailable, preserving the local fallback boundary.

Successful subscribe emits `deployment_reconciler_subscribed` and atomically writes the ready
file. A receive-side subscription failure emits `deployment_reconciler_subscription_lost`,
deletes readiness, and returns to the subscribe loop. Each failed subscribe emits
`deployment_reconciler_subscribe_failed`; no retry path is silent.

The ready JSON contains `ready`, `tenant_id`, `runner_id`, `strategy_id`, `nats_connected`, and
`deployment_subscription`. It is written through a temporary file plus `os.replace()` with
mode `0600`. `arx-runner health --ready-file <path>` succeeds only for a complete ready state.

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G6**（live 前 host capability 校验） | reconciler deploy 路径先解密 credential 再调 `_check_g6_gate(host, spec, credential)`：live 下四层 capability fail-fast（host live / venue / code_hash / credential scope），任一层拒即 `RuntimeError`；`NoopHost` 声明 `supports_live()=False` 在层 1 被拒 | 处理 `trading_mode == "live"` 的 `DeploymentSpec` 时（见 [nautilus_host.md §相关 gate](nautilus_host.md)） |
| **G5-A**（money math differential 已收敛） | `ReconResult` 的金额差分对账依赖 Crucible Python 已收敛的对账逻辑 | 上报 `recon_result` 时；arx 聚合层 live 由 G5-A 不阻塞 |
| **G5-B**（arx Rust internal BC 平替切换） | reconciliation crate 当前仅 smoke harness，按 G5-B arx Rust internal 视角暂禁 live，仍 paper/sim | crucible-rust 平替触发时（休眠中） |

## Undeclared capability traceability

当一个 host 不具备 live 能力（`NoopHost` 声明 `supports_live()=False`，或第三方 host
未声明 capability 契约），G6 gate 在层 1 拒绝并记 `g6_gate_live_capability_denied`
（`deployment_reconciler.py:79-88`）。该拒绝**不打断 reconcile loop**：`handle_spec`
的 broad `except`（`deployment_reconciler.py:316-337`）是 `失联≠停止` 式 fail-safe——
一个被拒的 spec 不能让守护其他部署的 loop 崩溃。它接住异常后:

- 记 `deployment_reconcile_failed`（reconciler 包装层，`deployment_reconciler.py:318-324`）
- 发布 `DeploymentStatus` 且 `phase=degraded` / `health=unhealthy`
  （`deployment_reconciler.py:325-331`）

因此结构化拒绝信号走 **`DeploymentStatus` phase=degraded + 双层 structlog 事件名**
（`g6_gate_live_capability_denied` gate 层 + `deployment_reconcile_failed` 包装层），
**而非独立的 `FailureEvent`**。`FailureEvent`（含 `reason_code` 枚举）是 `docs/domain.md`
§1.5 的纸面设计，`src/custos/` 尚未 first-class 实现——`_report_status()`
（`deployment_reconciler.py:364-393`）发布的 `DeploymentStatus` payload 无 `reason_code`
字段。真正的 first-class `FailureEvent` uplink 属独立功能面（FailureEvent first-class
实现 follow-up plan 候选）。集成层覆盖见
`tests/test_g6_gate_capability_integration.py`。

## 未来演化路线

- **短期**：`run_reconciliation_cycle` 接通 NT 的 `Reconciler` / `AccountState`
  surface（当前是显式 stub，属 NT-host 集成阶段职责）。
- **中期**：`recon_result` 若量增可从当前专用 subject 进一步按 dimension 拆分；
  drift 检测阈值（`drift_threshold`）可分档配置。
- **长期**：多引擎 flavour 下 reconcile loop 抽象出引擎中立的期望态对齐协议
  （`ExecutionEngineAdapter`），支撑「设计 for 3、实现 1」。
