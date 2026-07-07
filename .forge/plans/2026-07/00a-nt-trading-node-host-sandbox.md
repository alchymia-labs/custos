# 00a - NtTradingNodeHost 真实现 + Binance sandbox 打通 (supertrend 首策略)

> **Status**: 🔲 Todo
> **Created**: 2026-07-07
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: arx Plan 60 (runner-custos-split) — 已 close-out 2026-07-06, custos 独立仓库骨架就位
> **multi_session_scope**: false (单 session 5-6 task, 估 ~600 LOC 可完成; 若 Foundation Scan 发现 ps runner.py 提炼粒度分歧再切片)

## 上下文 (Context)

### 现状 (as-of 2026-07-07, custos main HEAD = 0c10a9c)

custos 是从 arx `runner/` 抽出的独立 Apache-2.0 公开开源仓库(Plan 60 已 close-out)。当前 `nautilus_host.py` 只有 `NoopHost` stub — 不真起 NT 进程, `deploy/reconfigure/stop` 三方法只记结构化日志占位返回 `container-{spec_id}`。G6 gate (`deployment_reconciler.py:30-53`) 已硬编码: `trading_mode=="live" + isinstance(NoopHost)` → `RuntimeError` fail-fast, live deploy 全线阻塞。README §"Not Included Yet" 最后一条自述: 「NtTradingNodeHost real implementation — live deploy stays blocked until the real implementation lands here」。

`pyproject.toml` **完全没有 `nautilus-trader` 依赖**, 也没有 optional extra。`grep -rn "from nautilus_trader" src/` 全仓 0 命中。

用户诉求: 让 `philosophers-stone/trend/supertrend/` 策略通过 custos 自托管治理面(vault + reconcile + NATS)真跑起来。走路径 B (提炼 ps `runner.py`, 而非绕开 custos 直接用 ps `deploy/nautilus/docker-compose up`)。

### 契约证据锚表 (Foundation Scan Gate, 全部 file:line 已 grep 实证)

| 引用契约 / 来源 | file:line | 用途 |
|---|---|---|
| `NoopHost` 现状 stub | `src/arx_runner/nautilus_host.py:12-33` | 本 plan 要替换的靶子 (保留 NoopHost 供 paper/sim, 新增 NtTradingNodeHost 并列) |
| `NautilusHostProtocol` 三方法契约 (duck-type) | `src/arx_runner/deployment_reconciler.py:56-63` | NtTradingNodeHost 必须逐字满足 `deploy/reconfigure/stop` 签名 |
| G6 gate 现状逻辑 (case-insensitive live + isinstance NoopHost) | `src/arx_runner/deployment_reconciler.py:30-53` | 本 plan 保留不变; Plan 00c 才改造 gate 逻辑 |
| `_apply_spec` 编排 | `src/arx_runner/deployment_reconciler.py:230-251` | reconciler 已把 G6 gate → decrypt cred → host 调用编排完; NtTradingNodeHost 只需实现三方法 |
| `CredentialVault.decrypt` 契约 (返回 dict, 含 `permission_scope`) | `src/arx_runner/credential_vault.py:49-54,83-98` | deploy(spec, credential) 收到的 credential 是 vault decrypt 后的 dict, 已通过 `trade_no_withdraw` scope 校验 |
| custos domain-model §1.4 NT 执行适配红线 | `docs/domain.md:130-143` | 三红线: NT 启动必先校验 code_hash / Vault 引用而非明文 / strategy 隔离 |
| ps `runner.py` BaseRunner 完整 TradingNode 装配 | `alchymia-labs/philosophers-stone/deploy/nautilus/runner.py:33-54,594-967` | 提炼靶子: `_create_node_config` (行 812-955) + `run()` (行 968-1017) 是首个可复用逻辑 |
| ps runner.py Binance venue 配置 | `alchymia-labs/philosophers-stone/deploy/nautilus/runner.py:886-922` | `BinanceDataClientConfig` + `BinanceExecClientConfig` + `InstrumentProviderConfig` 装配模板 |
| ps runner.py 非 Binance NotImplementedError | `alchymia-labs/philosophers-stone/deploy/nautilus/runner.py:923-927` | 本 plan 沿用 Binance-only, OKX/其他 venue 显式拒 |
| ps runner.py `EXCHANGE_MAP` | `alchymia-labs/philosophers-stone/deploy/nautilus/runner.py:509-518` | 提炼时保留 map, 但只落 Binance 实现 |
| ps runner.py credential 读取 (env var, 本 plan 不复用) | `alchymia-labs/philosophers-stone/deploy/nautilus/runner.py:684-724` | 本 plan 用 custos `CredentialVault.decrypt` 替代, 不走 env var |
| ps supertrend 目录 | `alchymia-labs/philosophers-stone/trend/supertrend/` | 首策略靶子; `config.yaml` + `refinement/nautilus/` |
| ps supertrend Nautilus 部署 conf | `alchymia-labs/philosophers-stone/deploy/nautilus/conf/supertrend/config.yaml` | 参考 strategy_config 结构 |
| custos nautilus_host.md 未来演化路线 (短期 NtTradingNodeHost 落地) | `docs/nautilus_host.md:60-62` | 本 plan 兑现此路线的短期项 |
| 生态强制规则 §1 源码 vs 运行时分离 | `.claude/rules/mandatory-rules.md` §1 | 本 plan 只改 custos `src/`, 不碰 `~/.crucible/` 运行时 |

### Plan-to-plan 引用

- **arx Plan 60** (`tesseract-trading/arx/.forge/plans/2026-07/60-runner-custos-split.md`) — custos 独立仓库骨架的上游, 已 close-out; 本 plan 是 custos 首份内部 plan
- **本 plan 00a 是 Plan 00b/00c 上游**: 00b (telemetry 桥) 依赖 00a 的 NtTradingNodeHost 真起 NT + NT MessageBus 可访问; 00c (live 放行) 依赖 00b + 00a 完成后 G6 gate 才有意义放宽

### Historical lessons 强制引用

- **lesson #14 Foundation Scan Gate**: 起 plan 前已系统扫骨架 + 通读权威文档 — custos 6 篇 docs 全读 (`docs/domain.md`/`nautilus_host.md`/`reconcile.md`/`credential_vault.md`/`telemetry_actor.md`/`nats_client.md`) + ps `runner.py` + `main.py` + Dockerfile + docker-compose.yaml + supertrend 目录扫过, 契约表逐行 file:line 锚定
- **lesson #17 failure-mode coverage contract**: 本 plan 含 wire (NT MessageBus) + async (asyncio) + persistence (TradingNode state) + concurrency (NT engine thread vs asyncio loop), 强制列 failure mode 契约 (见"失败模式契约表"段)
- **lesson #22 多层 fail-fast 兜底**: NT 启动前 code_hash 校验 (第 1 层) + credential permission_scope 校验 (第 2 层, vault 侧已守) + venue capability 校验 (第 3 层) + G6 gate isinstance 拒 (第 4 层, 00c 才放宽) 四层守 non-custodial 红线
- **lesson #25 反 fabricated close-out**: close-out 契约表所有 `test_*` 函数名必 grep 实证真存在, 数字必真跑 pytest 命中数, 不凭"应该有 8 个测试"推理
- **lesson #27 commit scope discipline**: 全 Task commit 用 `git add <specific-file>` + 提交前 `git status --short` 核对
- **lesson #29 校验类操作不覆盖 host**: 集成测试若需 NT credential 文件, 用 `/tmp/` 或 mktemp, 禁 `cp` host 真实 `.env`
- **lesson #31 单 plan > 单 session**: 本 plan `multi_session_scope: false`, 6 task 单 session 可完成; 若 executor Foundation Scan 发现 ps runner.py 提炼粒度分歧 (helper 分组不合适) 再切
- **lesson #35 boundary constant**: `NAUTILUS_HOST_TYPE` env var / spec 字段名一次定死 (`nt_trading_node` 而非 `nt-trading-node` / `NT`), 后续 flavour (hummingbot) 扩展时按此空间命名
- **lesson #37 spawner 元层 grep 实证**: drafter 编辑本 plan 引用的所有代码符号 (Python module 名 / NT class 名 / Binance factory 名 / config 类名) 已 grep 实证, 见契约表

## 目标 (Goal)

在 custos `src/arx_runner/nautilus_host.py` 新增真 `NtTradingNodeHost` 类 (与 `NoopHost` 并列, 不删除后者 — paper/sim mode 仍用 NoopHost), 满足 `NautilusHostProtocol` 三方法真实现:

- `deploy(spec, credential)`: 装配 `TradingNodeConfig` (从 spec 派生 venue/instrument/leverage + 从 credential dict 派生 API key/secret) → `TradingNode.build()` → 加载 strategy 类 → `add_strategy` → `node.run()` async → 返回 `spec_id` 作 container_id
- `reconfigure(spec)`: 参数级变更 (leverage / notional cap 等), 不重启 TradingNode; 需重启的变更 → stop + deploy
- `stop(spec_id)`: 优雅关闭 TradingNode (`node.stop()` + `node.dispose()`), 清理 process state

覆盖范围:
- **venue**: 仅 Binance sandbox mode (`SandboxLiveExecClientFactory`) — testnet/live 由 Plan 00c 放行
- **策略**: supertrend 首策略, code_hash 校验从 `code_hash` spec 字段派生
- **credential 源**: custos `CredentialVault.decrypt(credential_id) -> dict` 返回 `{api_key, api_secret, permission_scope=trade_no_withdraw}`; **不走 env var** (与 ps runner.py 分道)
- **测试**: pytest 集成测试用 `SandboxLiveExecClientFactory` (真模拟撮合 + 无真钱), CI 不联外网

## 架构 (Architecture)

**分层**:
```
DeploymentReconciler._apply_spec (unchanged)
  ├─ _check_g6_gate (unchanged, 00c 改造)
  ├─ credential_vault.decrypt(cred_id) → dict
  └─ nautilus_host.deploy(spec, cred_dict) → container_id
        └─ NtTradingNodeHost.deploy
              ├─ _validate_code_hash(spec, local_strategy_dir)  # 红线 #1
              ├─ _build_binance_venue_configs(spec, cred_dict)  # 提炼自 ps runner.py:812-955
              ├─ _load_strategy_class(spec.strategy_path)       # 动态 import (供 supertrend)
              ├─ TradingNode(config) + build() + add_strategy   # NT 装配
              └─ asyncio.create_task(node.run())                # 后台跑, 不 block reconciler
```

**关键分工**:
- `_nt_binance_venue.py` (新, 纯函数): `build_data_client_config(spec, cred) -> BinanceDataClientConfig` + `build_exec_client_config_sandbox(spec, cred, starting_balances) -> SandboxExecutionClientConfig` — 无 IO 便于单测
- `_strategy_loader.py` (新): `load_strategy_class(strategy_path: Path, expected_code_hash: str) -> type[Strategy]` — 计算目录 sha256 + 校验 + `importlib.util` 动态加载
- `nautilus_host.py` (改): 新增 `NtTradingNodeHost` 类, 保留 `NoopHost`; 顶层 `nautilus_trader` import 用 `try/except ImportError` 兜底 (dev 环境未装 NT extra 时不炸)

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| `nautilus-trader` 引入方式 (base dep vs optional extra) | **optional extra `nt-runtime`** (`pip install custos-runner[nt-runtime]`) | NT 是重依赖 (Rust 编译), 但 telemetry/reconcile/vault 模块无 NT 也能跑 (paper/sim mode + NoopHost); optional 让轻装用户不被强制装 NT |
| 复用 ps runner.py 的方式 | **copy + 适配, 不反向依赖 ps** | (a) custos 是 Apache-2.0 公开开源仓, 不该 runtime 依赖 ps 研究仓内部代码; (b) ps runner.py 耦合 Crucible 部署形态 (env var 读 key / `/app/scripts/` 硬编码 / Unix socket IPC), 原样共享不干净; (c) copy 后 custos 掌握完整控制权 |
| credential 来源 | **`CredentialVault.decrypt(credential_id) -> dict`**, 不走 env var | 满足 custos 红线 "Key 只在本地 + 明文不越进程边界"; ps runner.py 的 env var 模式适合 Crucible 部署 (env inject), 但击穿 custos non-custodial 红线 |
| Binance venue 提炼粒度 | **纯函数 helper** (`_nt_binance_venue.py`), 不做 class 抽象 | (a) 单测友好 (纯函数 pytest 直断 config obj 字段); (b) 后续 OKX/其他 flavour 加 `_nt_okx_venue.py` 并列, 不做过早继承; (c) lesson coding-taste "组合优于继承, 克制版" — 单文件 3-4 helper 足够 |
| 策略源码装载路径 | **spec 显式指定 `strategy_path` + `code_hash`**, 不硬编码 | 兼容多策略场景 (supertrend / adaptive_grid / ...); code_hash 校验守 non-custodial 红线 (`docs/domain.md:141` "NT 启动必先校验 code_hash") |
| `TradingNode` 生命周期在 asyncio loop 中的位置 | **`asyncio.create_task(node.run())` 后台跑**, `deploy` 返回后 reconciler 立刻可继续 | NT `TradingNode.run()` 是 blocking 的 (`runner.py:1007`); 若在 `deploy` 内 await, reconciler loop 会卡死。用 `create_task` 后台跑, `stop` 时 `node.stop()` 让 task 自然收敛 |
| starting_balances (sandbox 首笔资金) | **spec 显式字段 `sandbox.starting_balances`** (默认 `["10_000 USDT"]`) | 与 ps runner.py `SandboxRunner._starting_balances` 一致; 让 spec 端可控 |

## Task List

**Task 1**: `pyproject.toml` 加 `nautilus-trader` optional extra `nt-runtime` + `pyyaml` (读 strategy config)

- 文件: `pyproject.toml`
- 依赖: `nautilus-trader>=1.227` + `pyyaml>=6` 落在 `[project.optional-dependencies].nt-runtime`
- 验证: `uv sync --extra nt-runtime` 成功 + `python -c "import nautilus_trader; print(nautilus_trader.__version__)"` 返回版本
- 失败模式: NT 编译失败 (macOS ARM64 需 Rust toolchain) → 记 `nt_install_failed` in log

**Task 2**: 提炼 Binance venue 装配 helper (纯函数)

- 新文件: `src/arx_runner/_nt_binance_venue.py` (~150 LOC)
- 参考: ps `runner.py:812-955` `_create_node_config` 中 Binance 分支
- 导出: `build_data_client_config(spec: dict, credential: dict) -> BinanceDataClientConfig` + `build_exec_client_config_sandbox(spec, credential, starting_balances) -> SandboxExecutionClientConfig` + `build_futures_leverages(spec) -> dict` + `build_instrument_ids(spec) -> frozenset[InstrumentId]`
- 契约: 入参 spec (dict, DeploymentSpec.parameters 段) + credential (dict, vault decrypt 后) → 出参 NT config 对象; 无 IO, 无副作用
- 测试: `tests/test_nt_binance_venue.py` (新) — 断言 config 对象字段命中预期
- 失败模式: spec 缺 required 字段 → `KeyError` fail-fast; unsupported connector (非 binance* / okx*) → 显式 `NotImplementedError`

**Task 3**: `NtTradingNodeHost.deploy(spec, credential)` 真实现

- 文件: `src/arx_runner/nautilus_host.py` (改, ~200 LOC 新增, `NoopHost` 保留)
- 顶层 import: `try: from nautilus_trader.live.node import TradingNode; except ImportError: TradingNode = None` (dev 环境无 NT extra 时不炸 module load, 首次调用时 fail-fast)
- 实现:
  - `deploy(self, spec, credential) -> str`:
    - `_ensure_nt_available()` (若 `TradingNode is None` → `RuntimeError` "install `custos-runner[nt-runtime]`")
    - `_validate_code_hash(spec, local_strategy_dir)` (Task 4 落)
    - `venue_configs = build_binance_venue_configs(spec, credential)` (Task 2)
    - `strategy_cls = load_strategy_class(spec.strategy_path, spec.code_hash)` (Task 4)
    - `node_config = TradingNodeConfig(...)` (从 spec + venue_configs 装)
    - `node = TradingNode(config=node_config); node.add_data_client_factory(...); node.add_exec_client_factory(SandboxLiveExecClientFactory)` (sandbox mode)
    - `node.build()`; `node.trader.add_strategy(strategy_cls.from_config(...))`
    - `task = asyncio.create_task(node.run_async())`; 注册到 `self._active_nodes: dict[spec_id, (node, task)]`
    - 返回 `spec_id` 作 container_id
- 契约: 逐字满足 `NautilusHostProtocol.deploy` (`deployment_reconciler.py:59`)
- 测试: `tests/test_nt_trading_node_host.py::test_deploy_sandbox` (mock TradingNode 类; 断言 build + add_strategy 被调 + spec_id 返回)
- 失败模式: `_ensure_nt_available` fail → `nt_not_installed`; `_validate_code_hash` fail → `code_hash_mismatch`; venue config build fail → 冒泡 (Task 2 已处理); `TradingNode.build()` raise → 记 `nt_startup_failure` + re-raise (reconciler 侧走 degraded status)

**Task 4**: 策略源码装载 + `code_hash` 校验

- 新文件: `src/arx_runner/_strategy_loader.py` (~80 LOC)
- 导出:
  - `compute_strategy_dir_hash(strategy_dir: Path) -> str` (sha256 目录 recursive)
  - `load_strategy_class(strategy_path: Path, expected_code_hash: str | None) -> type` (importlib.util 动态加载, hash mismatch → `CodeHashMismatch` 异常)
- 契约: `strategy_path` 是 spec 字段 (如 `/opt/strategies/supertrend/strategy.py`); `expected_code_hash` = spec.code_hash (为 None 时 sandbox mode 允许跳过, live mode reconciler 侧强制)
- 测试: `tests/test_strategy_loader.py` (mock 策略目录 + 篡改 hash 断言拒绝)
- 失败模式: strategy_path 不存在 → `FileNotFoundError`; hash mismatch → `CodeHashMismatch` (触发 `FailureEvent.reason_code=code_hash_mismatch`)

**Task 5**: `NtTradingNodeHost.stop(spec_id)` + `reconfigure(spec)`

- 文件: `src/arx_runner/nautilus_host.py` (改, ~80 LOC)
- `stop`: 从 `self._active_nodes` 取 (node, task) → `await node.stop_async()` + `node.dispose()` + `task.cancel()` + 从 dict 删除; 若 spec_id 不存在 → 记 log 返回 (幂等)
- `reconfigure`: v1 最小实现 — 若参数变化仅涉及 leverage/notional_cap 类"运行时可调" → 记 log + call NT 相应 API; 涉及策略类/venue/symbol 变更 → `stop(spec_id) + deploy(spec, cred)` 重启 (reconciler 已有 credential ref, 但 reconfigure 签名不带 credential — v1 抛 `NotImplementedError` "structural reconfigure requires spec drop + re-deploy", reconciler 侧走 stop+deploy 路径)
- 测试: `tests/test_nt_trading_node_host.py::test_stop_idempotent` + `::test_reconfigure_structural_raises`
- 失败模式: `node.stop_async` 卡死 → 加超时 (default 30s, spec 可覆盖); 超时 → `nt_stop_timeout` + 强制 dispose

**Task 6**: 集成测试 + 用法示例

- 新文件: `tests/test_nt_trading_node_host_integration.py` (~150 LOC)
- 覆盖: 
  - `test_full_lifecycle_sandbox_supertrend`: 用真 `SandboxLiveExecClientFactory` + mock Binance data client factory (WebSocket 用 stub) + 装 supertrend 策略 (从 `alchymia-labs/philosophers-stone/trend/supertrend/refinement/nautilus/` 拷贝 fixture) → 断言 node 起来 + strategy 加载成功 + stop 干净 
  - `test_deploy_missing_nt_extra_fails_fast`: mock `TradingNode = None` → 断言 `RuntimeError` with install hint
  - `test_deploy_code_hash_mismatch_rejected`: 篡改 hash → 断言 `CodeHashMismatch`
- 新文件: `examples/supertrend-sandbox/README.md` + `examples/supertrend-sandbox/spec-example.json` (示例 DeploymentSpec + credential dict + 运行命令)
- 失败模式: (无新增 — Task 3/4/5 已覆盖)

## 失败模式覆盖契约表 (lesson #17)

本 plan 覆盖以下失败模式 (每条需 pytest 断言):

| 失败模式 | 触发点 | 测试文件:函数 | 上报 reason_code |
|---|---|---|---|
| NT 未装 (import fail) | `_ensure_nt_available` | `test_nt_trading_node_host.py::test_deploy_missing_nt_extra_fails_fast` | `nt_not_installed` |
| code_hash mismatch | `_validate_code_hash` | `test_strategy_loader.py::test_hash_mismatch_rejected` | `code_hash_mismatch` |
| Binance credential missing/malformed | `build_data_client_config` | `test_nt_binance_venue.py::test_missing_api_key_raises` | `venue_auth_failed` (间接 via NT `TradingNode.build()`) |
| unsupported venue | `build_*_client_config` | `test_nt_binance_venue.py::test_unsupported_connector_notimpl` | `NotImplementedError` (显式) |
| NT startup exception | `TradingNode.build()` | `test_nt_trading_node_host.py::test_build_failure_records_startup_error` | `nt_startup_failure` |
| stop 超时 | `NtTradingNodeHost.stop` | `test_nt_trading_node_host.py::test_stop_timeout_forces_dispose` | `nt_stop_timeout` |
| reconfigure 结构变更 | `NtTradingNodeHost.reconfigure` | `test_nt_trading_node_host.py::test_reconfigure_structural_raises` | (reconciler 侧走 stop+deploy) |
| vault decrypt fail 后 deploy 被跳过 | 上游 `_apply_spec` | (由 reconciler 覆盖, 已有 `test_deployment_reconciler.py`) | `vault_locked` |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `pyproject.toml` | 改 | 加 `nt-runtime` optional extra |
| `src/arx_runner/nautilus_host.py` | 改 | 新增 `NtTradingNodeHost` 类, 保留 `NoopHost` |
| `src/arx_runner/_nt_binance_venue.py` | 新建 | Binance venue 装配 helper 纯函数 |
| `src/arx_runner/_strategy_loader.py` | 新建 | 策略源码装载 + code_hash 校验 |
| `tests/test_nt_binance_venue.py` | 新建 | Task 2 单测 |
| `tests/test_strategy_loader.py` | 新建 | Task 4 单测 |
| `tests/test_nt_trading_node_host.py` | 新建 | Task 3/5 单测 |
| `tests/test_nt_trading_node_host_integration.py` | 新建 | Task 6 集成测试 |
| `examples/supertrend-sandbox/README.md` | 新建 | 用法示例 |
| `examples/supertrend-sandbox/spec-example.json` | 新建 | DeploymentSpec 示例 |

## 验收清单 (Acceptance Criteria)

- [ ] `uv sync --extra nt-runtime` 成功装 NT 1.227+
- [ ] `NoopHost` 类保留不动, 现有测试 (`test_nautilus_host` 若有 / 各现有测试) 全绿
- [ ] `NtTradingNodeHost.deploy/reconfigure/stop` 三方法签名逐字满足 `NautilusHostProtocol` (`deployment_reconciler.py:56-63`)
- [ ] 8 处失败模式全部 pytest 覆盖 (契约表 8 行 8 test)
- [ ] G6 gate 逻辑未改动 (`deployment_reconciler.py:30-53` diff 无变化; live mode + NtTradingNodeHost 组合此 plan 内**仍被拒** — Plan 00c 才放行)
- [ ] sandbox mode 集成测试跑通 supertrend 策略装载 (从 ps 目录拷贝 fixture)
- [ ] `pytest tests/` 全绿 (包括现有 20 test file)
- [ ] `examples/supertrend-sandbox/` 有可跑的 spec + README

## 偏离与改进日志 (Deviation Log)

(执行阶段填写; 空白 = 无偏离)

## 完成报告 (Close-out Report)

- **完成日期**: (待填)
- **总 Task 数**: 6
- **偏离数**: (待填)
- **验证结果**: (待填)
- **遗留项**: 
  - Plan 00b 承接: NT MessageBus → telemetry_actor 桥
  - Plan 00c 承接: G6 gate 逻辑放宽 + live/testnet 放行

## 下一步 (Next)

Plan 00a close-out 后启动 Plan 00b (telemetry 桥 NT MessageBus)。
