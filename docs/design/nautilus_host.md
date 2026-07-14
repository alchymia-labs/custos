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
  connector 集）。sandbox 行情使用匿名公共 feed，vault credential 不进入 NT data/exec
  config；testnet/live 才构造 authenticated client。

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
- **组合熔断兜底（红线 0.3 runtime 兑现）**：三层结构性守护，全部通过 host 的
  Tier-2 protocol 与引擎解耦（core 层无 NT 特化）：
  - **NT 本地 per-order RiskEngine** — 单笔 `max_qty` / `max_notional` / `price_collar`
    (`nt_risk_engine.py`, 已存在)。
  - **Runner 层 soft cap** — `RunnerNotionalCap` 读 host 的 `get_open_notional` +
    `spec.risk_config.max_notional_per_runner`，超额发 `runner_cap_exceeded`；缺失
    结构性 floor `paper=200 USD` / `live=1000 USD` (DEV-04-CAP-DEFAULT)，`≤ NAV × 5x`
    仍是操作侧参考上限。
  - **Runner 层 hard fallback breaker** — `FallbackBreaker` 每 tick 从
    `get_open_notional` + `get_engine_status.current_equity` 计算 drawdown_pct
    (Decimal，红线 0.4)；notional 或 drawdown 超阈 → host 的 `flatten_positions`
    (映射 NT `Strategy.close_all_positions`, DEV-04-FLATTEN-NT-MAPPING) + 冻结新单。
    首次 trip 后不重复 flatten (`_breaker_tick` 用 `was_frozen` gate)。
  - **Zombie watchdog** — `ZombieWatchdog` 用 `check_engine_connected`，连续
    disconnect 超 `grace_secs` (默认 60s, DEV-04-ZOMBIE-THRESHOLD) 升级
    `phase=degraded` + `health.reason=engine_disconnected_zombie`。

  Composition root (`cli/main.py::_build_reconciler`) 是三守护的 runtime wire
  锚点；`test_arx_disconnect_long_run_guards_persist` 证明 60 tick 无云端时守护
  持续生效。runtime 详见 [`reconcile.md` §失联降级](reconcile.md)。
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

`arx-runner start` 在 reconciler 构造时绑定单一 host，0.3.0 clean break 只有一个选择面：

- **`--engine nautilus`（默认）**：选择 `NtTradingNodeHost`，启用 sandbox / testnet / live
  真执行。nautilus 未安装时 `deploy` fail-fast；G6 四层对 live 仍全程强制。
- **`--engine noop`**：显式选择 `NoopHost`，仅用于 sandbox/dev contract tests；live spec
  仍由 G6 layer 1 拒绝。

`--use-nt-host` 已删除，不保留双重选择或 compatibility alias。

## Host mode × trading_mode matrix

`--engine`（host 选择）× `spec.trading_mode` 是一个 6 格空间。非 live 三格（sandbox /
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

成功的 active deployment 走 reconcile 成功路径
`_report_status(phase="running", health="healthy")`；成功处理 `stopped` 或 `archived`
lifecycle 则上报 `phase="stopped"`。`phase` 表示生命周期实际态，`health` 才表示健康度，
两者不能互相替代。

## Toolkit sync discipline

`nautilus_host` 运行时从两个正式 distribution 消费策略工具链：Python 3.11
兼容的 `custos_toolkit`，以及 Python 3.12 Nautilus lane 的
`custos_toolkit_nautilus`。241 个实现文件的唯一物理落点、源 commit 和 digest
记录在 `docs/authority/strategy-toolkit-inventory-v1.json` 与
`strategy-toolkit-extraction-v1.json`；`make check-toolkit-extraction` 逐文件重建
期望内容并 fail closed。`src/custos/engines/nautilus/toolkit/` 只保留无副作用的
deprecation marker，不再承载实现或修改 `sys.path`。

- **权威声明**：Custos package source 是 execution toolkit 的 body of truth；
  philosophers-stone 继续拥有策略研究源和 canonical BOM producer 职责，不是
  Custos runtime import path。
- **同步检查机制**：`make toolkit-sync-check`（`PS_ROOT` 必填）用于显式发现研究
  源与冻结提取物的 drift。任何采纳都必须生成新版本 inventory/extraction，不能
  原地改写 v1 evidence；规则见
  `docs/authority/strategy-toolkit-provenance.md`。
- **crucible Docker preservation window（硬约束）**：`the-crucible` 生产
  supervisor 对 ps `shared/*.py` **零直接 import**（纯 HTTP 编排，走
  `crucible_engine/supervisor.py` 的 `httpx.AsyncClient` 到 sidecar），但 ps
  自己的 Docker 构建把 `shared/` **打进生产运行时容器镜像**：
  `philosophers-stone/deploy/nautilus/Dockerfile:1-8`（header 注释
  "runtime base: NT + deps + shared + sidecar"）+ `:35 COPY
  shared/README.md /tmp/deps/shared/README.md`；
  `philosophers-stone/deploy/hummingbot/Dockerfile.image:28-29 COPY
  --chown=hummingbot:hummingbot shared /home/hummingbot/shared` + `:49 ENV
  PYTHONPATH=/home/hummingbot:/home/hummingbot/shared`。因此 ps `shared/`
  + `deploy/` 必须在 `the-crucible` 生产容器依赖它们期间保持 Docker
  可构建 —— 这是硬约束，非软偏好；任何 ps 侧收敛动作**不得**破坏这条链。
  crucible→custos 运行时迁移是未来独立候选 plan
  （`crucible-runtime-migration`），解锁后才能真正让 ps `shared/` 收敛为纯
  研究副本。
- **收敛流向**：ps `shared/` 中稳定下来的代码，经 sync-check 流回 custos
  toolkit 的新版本提取计划；custos toolkit 不会运行时反向依赖 ps checkout。
- **no-destructive-delete 保证**：在 crucible Docker preservation window
  存续期间，ps `shared/` 与 `deploy/` **不得**被删除或破坏性移动 —— 无论
  采纳哪个 curation / convergence 选项。

**决策落地（CEO 已裁定）**：

- **Curation scope**：保持 06a 全 9 子包 vendor 现状（详见
  `strategy-toolkit-inventory-v1.json`）；T4 物理落点为 36 个 base、55 个
  Nautilus adapter 和 150 个 private vendor 文件。
- **ps convergence timing**：短期保留 ps Docker-buildable `shared/` +
  `deploy/`，直至 crucible→custos 运行时迁移落地；该迁移是独立候选 plan，非
  本次交付范围。
- **Sync-check cadence**：周检（weekly diff review），custos 无 CI 前走 ops
  runbook 强制执行。
- **pandas_ta governance**：保持 private vendored fork，只能从
  `custos_toolkit_nautilus._vendor.pandas_ta` 导入；禁止发布顶层 `pandas_ta`
  alias。升级必须新建 versioned inventory/extraction evidence。

## PS supertrend migration

Real-strategy production acceptance on custos landed with the sandbox +
testnet e2e slice (`tests/engines/nautilus/test_real_supertrend_e2e_sandbox.py`
and `test_real_supertrend_e2e_testnet.py`). This section states what changes
about the operational picture across the ecosystem — what custos now owns, what
the philosophers-stone (ps) side keeps, and where the residual tech-debt sits.

### Integration path

The extracted `SuperTrendStrategy` fixture loads through the published toolkit
namespaces. The production load path is:

1. `custos.engines.nautilus.strategy_loader.load_strategy_class` reads the
   strategy source file and passes it through the code_hash gate (dir-hash
   layer 3 in production, skipped in sandbox).
2. Strategy code imports platform-neutral helpers from `custos_toolkit` and
   engine adapters from `custos_toolkit_nautilus.adapter`. Private indicator
   code resolves only below `custos_toolkit_nautilus._vendor`; there is no
   path bootstrap or top-level compatibility alias.
3. `load_strategy_class(..., expected_registry_name="supertrend")` invokes
   the loader's post-load registry binding check
   (`custos_toolkit_nautilus.adapter.registry.get_strategy_info`) to assert the module the
   loader picked matches the class registered under the operator-supplied
   name.
4. `NtTradingNodeHost._instantiate_strategy` calls the ps
   module-level `create_strategy(config)` factory when present (production
   entry-point contract), otherwise instantiates the class with NT defaults.

Sandbox acceptance is asserted end-to-end in the sandbox e2e test; testnet
routing is asserted at the wire level in the testnet e2e test (real testnet
session opening is DP1 opt-in / manual verification per its DEV entry).

### Ps sidecar / runner retirement declaration

`philosophers-stone/deploy/nautilus/runner.py` and
`philosophers-stone/deploy/sidecar/` are no longer the primary production
entrypoint for the supertrend strategy — custos takes over that role.
Retirement is **declarative only**: custos does not delete, rename, or
otherwise mutate any ps code. The ps repo may keep the runner + sidecar
alive for research use (local backtesting via `deploy/nautilus/main.py`,
team-internal experiments), and no coordinated cross-repo delete is
scheduled. The declaration exists so future contributors do not build new
production wiring on top of the retired ps entrypoints.

### Second production consumer of ps `shared/`

Even after the supertrend production entrypoint moves to custos, ps
`shared/` remains a production dependency — but of `the-crucible`, not
custos. The full mechanics of the hard constraint (Docker preservation
window, no-destructive-delete guarantee, HTTP-only coupling) are in
§"Toolkit sync discipline" above; the migration-side implication is:
retiring the ps runner / sidecar as the supertrend production entrypoint
does **not** remove ps `shared/` from the ecosystem's production surface.
It stays a Docker-image-level dependency of any strategy container the
crucible ecosystem supervises for as long as those containers are alive.
A "ps shared/ is only research now" reading of this retirement declaration
would be incorrect and would break crucible production if acted on.

### Toolkit vs G6 code_hash scope

The toolkit substrate is covered by custos's supply-chain integrity layer
(`strategy-toolkit-extraction-v1.json` + wheel receipt + Custos release signing), not by the
per-deploy G6 code_hash gate. G6 layer 3 (dir-hash) hashes only the
strategy directory the operator's spec points at, not the transitive
packaged toolkit closure. This split is deliberate: the toolkit is
compiled into custos releases and audited as part of the release
provenance chain, while the strategy directory is what changes per-deploy
and needs the per-deploy gate. Together the two layers form the
multi-layer defence for red line 0.2 — a toolkit tamper surfaces at
release-verification time, a strategy tamper surfaces at deploy time, and
neither depends on the other's coverage.

### Arx web sidecar HTTP tech-debt (arx-side follow-up)

`arx/web/lib/hooks/useApi.ts` documents a `StrategyPosition` interface
fetched via the crucible-relayed sidecar real-time position-proxy
endpoint. This is HTTP-level coupling between arx web and crucible's
sidecar-proxied API — orthogonal to the ps `shared/` curation scope and
untouched by the custos migration. Migrating this consumer from sidecar
HTTP to a NATS-only path is scheduled as an **independent arx-side
follow-up plan**; the arx team schedules and executes it on their own
cadence. Custos does not block on it, and the retirement declaration
above does not depend on its completion.

## 未来演化路线

- **短期（已落地）**：telemetry uplink 桥（NT `MessageBus` → arx telemetry actor）已随
  `_attach_observability()` 落地（Plan 00b close-out）——testnet / live 真跑的 fill /
  `OrderDenied` 现通过遥测桥对外上报云端，不再只本地 structlog 可观测。
- **中期**：`ExecutionEngineAdapter` 抽象补全 CEX 侧对账 / 下单 / 撤单 / 查询接口，
  与 NT 的 `ExecEngine` 对齐。
- **长期**：多引擎 flavour（`custos-nt` / `custos-hummingbot` / `custos-freqtrade`），
  各 flavour 各自实现 `NautilusHostProtocol`，落地「设计 for 3、实现 1」的多引擎前景。
