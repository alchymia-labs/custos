# nautilus_host — NT 进程监管 + ExecutionEngineAdapter

> Custos 六件套之一。源码：`src/arx_runner/nautilus_host.py`。G6 gate 主载体。

## 模块职责

`nautilus_host` 是 Custos 与 **NautilusTrader 执行引擎**之间的适配层：监管 NT 进程
的起 / 停 / 重配，并提供 `ExecutionEngineAdapter` 的 CEX/NT 实现。它体现 vision 支柱
一「**设计 for 3、实现 1**」——接口按多引擎设计，v1 只落 NT 一个 flavour。

当前落地：

- **`NoopHost`（stub）**：不真起 NT 进程，只记结构化日志后返回占位
  （`container-{spec_id}`）。方法签名与 `NautilusHostProtocol`
  （`deployment_reconciler.py`）**逐字一致**，使 reconciler 可 duck-type 依赖、G6
  gate 可 `isinstance` 命中。
- **`NtTradingNodeHost`（真实实现，follow-up）**：真起 NT `TradingNode` 的宿主，
  尚未落地——**本模块迁移只搬 NoopHost 现有代码**，真实实现是独立 follow-up plan。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块不对外暴露任何 API；它只被
> 本地 `DeploymentReconciler` 调用，NT 进程完全在 runner 本地。任何对部署状态的外部
> 访问都经 arx 协调层的 gatekeeper。*This module's API surface is consumed
> exclusively by the arx coordination layer; no direct external client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `NoopHost.deploy` | `async deploy(spec: dict, credential: dict) -> str` | stub 起进程，返回 `container-{spec_id}` |
| `NoopHost.reconfigure` | `async reconfigure(spec: dict) -> None` | stub 重配 |
| `NoopHost.stop` | `async stop(spec_id: str) -> None` | stub 停 |
| `NautilusHostProtocol` | `deploy` / `reconfigure` / `stop`（见 `deployment_reconciler.py`） | reconciler 依赖的 host 契约；`NtTradingNodeHost` 与 `NoopHost` 均须满足 |

`NoopHost` 仅供 paper / dev / sim mode 让 reconcile 流程跑通。live mode 下由 G6 gate
拒绝——因为 stub 会**静默接受** live execution spec 却不实际执行，等于把 live 单子丢进
黑洞（承重墙：live 通道不能落到 stub 上）。

## 红线契约

- **paper / live 通道物理隔离（承重墙）**：live mode 绝不能落在 `NoopHost` 上；这是
  paper/live 物理隔离红线在执行侧的兑现点。
- **组合熔断兜底**：NT 本地 RiskEngine + runner 本地 fallback 熔断（单策略 / 单账户
  回撤）在云宕机时仍生效；`max_notional_per_runner ≤ NAV × 5x` 结构性 cap 兜底。
- **Key 只在本地**：`deploy` 收到的 `credential` 由 credential_vault 本地解密而来，
  KEK 永不出主机（见 [credential_vault.md](credential_vault.md)）。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G6**（live 前 NT host 真实实现）**【主载体】** | `_check_g6_gate(host, spec)`：`trading_mode == "live"` 且 `isinstance(host, NoopHost)` → `RuntimeError` fail-fast。`trading_mode` 大小写不敏感比对（Rust `TradingMode` serde 序列化为 PascalCase `"Live"`，Python/oracle 侧小写 `"live"`，两侧 wire 都要命中，否则沦为 dead gate — lesson #36 dogfood） | 每次处理 live mode `DeploymentSpec` 时 |
| **G-SoD**（高敏感动作双人审批） | live 部署审批 approver ≠ applicant | 云端 arx 审批 live deploy 时 |

> **G6 当前状态（as-of 2026-07-05）**：`NoopHost` reject 校验 + `isinstance` 校验 +
> `trading_mode` PascalCase dead-gate 修已落地（Plan 46）；`NtTradingNodeHost` 真实
> 实现尚未落地——**live deploy 按 G6 暂禁**，paper / sim 放行。

## 未来演化路线

- **短期**：`NtTradingNodeHost` 真实实现落地（起 NT `TradingNode` + 进程监管 +
  健康探针），替换 `NoopHost`，解锁 live deploy 的 G6 门。
- **中期**：`ExecutionEngineAdapter` 抽象补全 CEX 侧对账 / 下单 / 撤单 / 查询接口，
  与 NT 的 `ExecEngine` 对齐。
- **长期**：多引擎 flavour（`custos-nt` / `custos-hummingbot` / `custos-freqtrade`），
  各 flavour 各自实现 `NautilusHostProtocol`，落地「设计 for 3、实现 1」的多引擎前景。
