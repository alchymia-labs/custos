# reconcile — 声明式部署 reconcile loop + 对账上传

> Custos 六件套之一。源码：`src/arx_runner/deployment_reconciler.py`（声明式部署
> loop）+ `src/arx_runner/reconcile.py`（对账结果上传）。

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
| `DeploymentReconciler` | dataclass(`nats_client`, `tenant_id`, `runner_id`, `nautilus_host`, `credential_vault`, `drift_threshold=3`) | 声明式 reconcile loop |
| `NautilusHostProtocol` | `async deploy(spec, credential) -> str` / `async reconfigure(spec)` / `async stop(spec_id)` | reconciler 依赖的 NT host 契约（duck-typed） |
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

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G6**（live 前 NT host 真实实现） | reconciler 在 live mode 下把 spec 交给 `nautilus_host`，`_check_g6_gate` 检测到 `NoopHost` 立即 `RuntimeError` 拒绝 | 处理 `trading_mode == "live"` 的 `DeploymentSpec` 时（见 [nautilus_host.md](nautilus_host.md)） |
| **G5-A**（money math differential 已收敛） | `ReconResult` 的金额差分对账依赖 Crucible Python 已收敛的对账逻辑 | 上报 `recon_result` 时；arx 聚合层 live 由 G5-A 不阻塞 |
| **G5-B**（arx Rust internal BC 平替切换） | reconciliation crate 当前仅 smoke harness，按 G5-B arx Rust internal 视角暂禁 live，仍 paper/sim | crucible-rust 平替触发时（休眠中） |

## 未来演化路线

- **短期**：`run_reconciliation_cycle` 接通 NT 的 `Reconciler` / `AccountState`
  surface（当前是显式 stub，属 NT-host 集成阶段职责）。
- **中期**：`recon_result` 若量增可从当前专用 subject 进一步按 dimension 拆分；
  drift 检测阈值（`drift_threshold`）可分档配置。
- **长期**：多引擎 flavour 下 reconcile loop 抽象出引擎中立的期望态对齐协议
  （`ExecutionEngineAdapter`），支撑「设计 for 3、实现 1」。
