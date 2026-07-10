# nautilus_host — NT 进程监管 + ExecutionEngineAdapter

> Custos 六件套之一。源码：`src/custos/engines/nautilus/host.py`。G6 gate 主载体。

## 模块职责

`nautilus_host` 是 Custos 与 **NautilusTrader 执行引擎**之间的适配层：监管 NT 进程
的起 / 停 / 重配，并提供 `ExecutionEngineAdapter` 的 CEX/NT 实现。它体现 vision 支柱
一「**设计 for 3、实现 1**」——接口按多引擎设计，v1 只落 NT 一个 flavour。

当前落地：

- **`NoopHost`（stub）**：不真起 NT 进程，只记结构化日志后返回占位
  （`container-{spec_id}`）。方法签名与 `ExecutionEngineProtocol`
  （`core/engine_protocol.py`）**逐字一致**，使 reconciler 可 duck-type 依赖。它显式
  声明 `supports_live() -> False` / `supports_venue() -> False`，G6 gate 据此在 live
  下拒绝它（fail-safe：stub 永不上真 venue）。
- **`NtTradingNodeHost`（真实实现）**：真起 NT `TradingNode` 的宿主。`deploy` 按
  `spec.trading_mode` 分派三档执行通道 —— `sandbox`（实时 Binance 数据 + 本地模拟撮合）
  / `testnet`（真 Binance exec 走 testnet 端点，测试资金）/ `live`（真交易所，过 G6 gate
  + 云端双人审批）。它声明 `supports_live() -> True` / `supports_venue(name)`（Binance
  connector 集）。

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
| `NtTradingNodeHost.deploy` | `async deploy(spec: dict, credential: dict) -> str` | 按 `spec.trading_mode` 分派 sandbox / testnet / live；组装 `TradingNode` 后台任务运行 |
| `<host>.supports_live` | `def supports_live() -> bool`（sync） | 显式 capability 契约：host 是否支持 live 执行。G6 gate 层 1 查询 |
| `<host>.supports_venue` | `def supports_venue(venue: str) -> bool`（sync） | host 是否支持该 venue（connector）。G6 gate 层 2 查询 |
| `NautilusHostProtocol` | `deploy` / `reconfigure` / `stop` / `supports_live` / `supports_venue`（见 `deployment_reconciler.py`） | reconciler 依赖的 host 契约；`NtTradingNodeHost` 与 `NoopHost` 均须满足。capability 方法是显式契约面（非 hasattr 兜底） |

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

## Credential lifecycle invariants

`deploy` 收到的解密 credential 只用于构造 NT client config，绝不落在 host 状态里、不 log、
不 publish（non-custodial 红线 0.1）。三层 defence-in-depth invariant 各有测试守：

| # | invariant | 覆盖测试 |
|---|-----------|----------|
| #1 | `repr(host._active_nodes)` 不泄露 credential | `test_nt_trading_node_host.py::test_deploy_does_not_retain_credential` |
| #2 | `node.__dict__` 深度 5 递归 walk 不泄露 credential（key 只存于 NT msgspec config 的 `__slots__`，`__dict__` walk 不下降到 slots） | `test_credential_lifecycle.py::test_node_dict_recursive_no_credential` |
| #3 | structlog 异常日志经 `_sanitize_exception` 脱敏可能含 key 的消息 | `test_nt_trading_node_host.py::test_exception_log_redacts_credential_material` |

真 NT client 在内存里持有 key 以签名请求是必需且合规的——红线是 I/O 边界（log / publish /
network），非内存 client 状态。

## Pre-trade reject correlation handle

pre-trade 拒绝走 `nt_risk_engine.on_order_denied()` → `PreTradeRejected` wire。其中
`order_fingerprint` 是 SHA-256 over `symbol|client_order_id|side|qty|price|ts_seconds`，
是 **correlation handle，不是 tamper-evidence anchor**：真正的防篡改锚点是云端 audit chain
的 per-tenant HMAC（governance），custos non-custodial 承重墙不实现、也不该有可见性。真 NT
`OrderDenied` 只携带 `client_order_id`（side / quantity / price 恒空），故 handle 折入
`client_order_id` 提升唯一性，避免退化为 `(symbol, ts)` 二元组。覆盖测试
`test_nt_risk_engine.py::test_fingerprint_is_stable_and_hex` +
`::test_dispatcher_forwards_real_order_denied`。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G6**（live 前 host capability 校验）**【主载体】** | `_check_g6_gate(host, spec, credential)`：`trading_mode == "live"` 时四层 fail-fast，缺一即 `RuntimeError` + 结构化 error（reason_code = event 名）：层 1 `host.supports_live()`（`g6_gate_live_capability_denied`）/ 层 2 `host.supports_venue(connector)`（`g6_gate_venue_unsupported`）/ 层 3 `code_hash` 与本地源目录哈希一致（`g6_gate_code_hash_mismatch`）/ 层 4 `credential.permission_scope == trade_no_withdraw`（`g6_gate_credential_scope_violation`，vault 已守，此为兜底）。`trading_mode` 大小写不敏感（Rust `TradingMode` serde PascalCase `"Live"` + Python 小写，两侧 wire 都命中否则 dead gate — lesson #36）。每层各有 relaxed-double 测试证明是 live guard 非 dead branch（lesson #22/#28） | 每次处理 live mode `DeploymentSpec` 时 |
| **G-SoD**（高敏感动作双人审批） | live 部署审批 approver ≠ applicant（云端决策）；custos 侧 `NtTradingNodeHost` 构建 live exec config 前校验 `spec.approved_by` ≥ 2 distinct，缺则 `sod_approval_missing` | 云端 arx 审批 + custos live 部署预检 |

> **G6 当前状态（as-of 2026-07-07）**：从 `isinstance(NoopHost)` 单点升级为 **capability-based
> 4 层校验**（Plan 00c）。`NtTradingNodeHost` 真实实现已落地（Plan 00a sandbox + Plan 00c
> testnet/live），live deploy 过 4 层 gate + 云端双人审批后放行；`NoopHost` 声明
> `supports_live() -> False` 仍在 live 下被层 1 拒绝。

## CLI 入口

runner 入口（`python -m custos`）在 reconciler 构造时绑定单一 host：

- **默认 `NoopHost`**（paper / dev）：不带 flag 时行为不变（向后兼容）；live spec 被 G6 gate
  层 1 拒，sandbox / testnet spec 落 stub 为 no-op（不真起 NT）。
- **`--use-nt-host`**：显式选 `NtTradingNodeHost`，启用 sandbox / testnet / live 真执行。
  这是**启用真执行通道**，**非绕过 G6 gate** —— gate 4 层对每个 live deploy 仍全程强制；
  nautilus 未装时 `deploy` fail-fast（`_ensure_nt_available`）。无 opt-out env var 绕过
  gate（红线 0.2）。

## Host mode × trading_mode matrix

`--use-nt-host`（host 选择）× `spec.trading_mode` 是一个 6 格空间。非 live 三格（sandbox /
testnet）由各自 host 通道自洽；live 两格是承重墙——落到 stub 上即被 G6 gate 层 1 拒。
每格的期望行为与覆盖测试:

| trading_mode | host | 期望行为 | 覆盖测试 |
|--------------|------|----------|----------|
| sandbox | NoopHost | stub 静默接受（`nautilus_host_deploy_stub`），reconcile 报 `phase=running` / `health=healthy` | `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NoopHost]` |
| sandbox | NtTradingNodeHost | 真跑 sandbox（`SandboxLiveExecClientFactory`，本地模拟撮合），`phase=running` / `health=healthy` | `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NtTradingNodeHost]` |
| testnet | NoopHost | G6 gate 非 live 旁路，stub 静默接受，`phase=running` / `health=healthy` | `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NoopHost]` |
| testnet | NtTradingNodeHost | 真跑 testnet（`BinanceLiveExecClientFactory` + `BinanceEnvironment.TESTNET`），`phase=running` / `health=healthy` | `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NtTradingNodeHost]` |
| live | NoopHost | G6 gate 层 1 拒（`g6_gate_live_capability_denied`）；`_apply_spec` `RuntimeError`，经 `handle_spec` 则 `phase=degraded` | `test_g6_gate.py::test_g6_gate_rejects_live_noophost` |
| live | NtTradingNodeHost | G6 gate 4 层 + SoD ≥ 2 审批全通过则真跑 live，`phase=running` | `test_g6_gate.py::test_g6_gate_allows_live_nt_host` |

成功部署走 reconcile 成功路径 `_report_status(phase="running", health="healthy")`
（`deployment_reconciler.py:309-315`）——`phase` 是 `running`（非 `healthy`），`health` 才是
`healthy`。

## 未来演化路线

- **短期（已落地）**：telemetry uplink 桥（NT `MessageBus` → arx telemetry actor）已随
  `_attach_observability()` 落地（Plan 00b close-out）——testnet / live 真跑的 fill /
  `OrderDenied` 现通过遥测桥对外上报云端，不再只本地 structlog 可观测。
- **中期**：`ExecutionEngineAdapter` 抽象补全 CEX 侧对账 / 下单 / 撤单 / 查询接口，
  与 NT 的 `ExecEngine` 对齐。
- **长期**：多引擎 flavour（`custos-nt` / `custos-hummingbot` / `custos-freqtrade`），
  各 flavour 各自实现 `NautilusHostProtocol`，落地「设计 for 3、实现 1」的多引擎前景。
