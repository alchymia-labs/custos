# 06 — ps supertrend 迁移到 custos: registry-mode 加载 + RiskController 启用 + shared/ 依赖打包

> **Status**: 🔲 Todo (skeleton candidate, awaiting Phase 2 `/forge:plan-team` 精细化)
> **Created**: 2026-07-09 (Plan 03 close-out 后, user 澄清诉求 — custos 接管 ps supertrend, 移除 ps sidecar/runner 遗留)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: skeleton, 需 Phase 2 精细化后可执行
> **Depends on**: Plan 00a ✅ + Plan 00c ✅ + Plan 03 ✅ + **Plan 05** (结构重构 + rename, 本 plan 的 File Inventory 使用 Plan 05 之后的新目录路径 `src/custos/engines/nautilus/*`); **soft-depends** Plan 04 (若并行推进, 红线 0.3 三层齐)
> **Blocks**: 生产化 ps supertrend 首次 paper/testnet e2e 实跑
> **multi_session_scope**: unknown (预估 medium ~150-300 LOC, 大部分 test + config, 主逻辑改动小)

---

## 起源 (Origin)

Plan 03 close-out 后, user 澄清诉求 (session log 2026-07-09):

> custos 这套系统可以被 ps 项目引入, 跑起它之前写好的 supertrend 策略 (可以移除 ps 中 sidecar 等遗留服务)

grep 实证发现两个原本以为需要"改造 ps 侧"的项目实际**ps 已经就绪, 只需 custos 侧适配**:

1. **ps supertrend 已有完整 registry 机制** (contra 我上一版误判 "需要给 supertrend 加 create_strategy factory"):
   - `philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py:23` `from shared.nautilus import register_strategy`
   - `strategy.py:386` `register_strategy(...)` 模块顶部**自注册**
   - `philosophers-stone/shared/nautilus/registry.py:173` `register_strategy`, `:222` `create_strategy(name, config_wrapper=...)`, `:148` `discover_strategies`
   - 已服务于 Crucible 侧 (`strategy.py:411 _create_registered_strategy("supertrend", config_wrapper=wrapper)`)

2. **custos `_strategy_loader.py` 只支持 path→class 查找模式** (`_find_strategy_class` line 106), 缺 registry-mode 分支
   - 现状能加载 "任意 NT `Strategy` 子类只要类名以 `Strategy` 结尾", 但**无法直接调 ps registry**
   - 补一个 registry-mode 分支即可, 策略侧**零改动**

3. **ps sidecar / runner.py 定位澄清** (from user + grep):
   - **sidecar 主消费者是 Crucible** (`the-crucible/crucible_engine/sidecar_models.py` + `risk_monitor.py:568 sidecar_url`), 不是 arx
   - arx web 前端仍在代理 sidecar HTTP API 是 **crucible 时代 tech debt** (`arx/web/lib/hooks/useApi.ts:208` 等)
   - custos 接管后, ps 侧 sidecar / runner.py **可整体退休** (crucible 生态如仍需要则单独维护)

4. **借鉴机会**: ps `deploy/nautilus/runner.py` `_collect_metrics/orders/positions/engine_status` 借鉴到 Plan 04 (状态快照); ps `_create_node_config` 里的 Redis cache + MessageBus + reconciliation timeout 参数处理可借鉴扩展 custos `nautilus_host.py`。

---

## 上下文 (Context)

**as-of Plan 03 close-out (main HEAD `cbf5556`, 2026-07-09)**:

**custos 侧现状**:
- `src/arx_runner/_strategy_loader.py:106` `_find_strategy_class` 只支持 path→class 查找
- `src/arx_runner/nautilus_host.py:203` hard-coded `BinanceLiveDataClientFactory` + `BinanceLiveExecClientFactory` (与 ps `_create_strategy` 用同一套 factory ✅)
- `tests/test_nt_trading_node_host_integration.py:7` 已声明 "the real supertrend couples to philosophers-stone/shared/"
- `tests/fixtures/minimal_supertrend_strategy.py` 存在**零依赖 stub** — 但生产要跑 real supertrend

**ps supertrend 侧现状**:
- `trend/supertrend/refinement/nautilus/strategy.py` — `SuperTrendStrategy(NautilusTradingStrategy)`, 模块顶部 `register_strategy(...)` 自注册
- `trend/supertrend/config.yaml` — RiskController 参数 (`max_daily_loss` / `max_drawdown`) **未启用** (grep 0 命中)
- `shared/nautilus/registry.py` — `create_strategy(name, config_wrapper=cw)` 通用 factory
- `shared/nautilus/trading_strategy.py:177` — `self._risk_controller: RiskController | None = None` (config 未启用则 None)

**依赖打包挑战**:
- ps supertrend 依赖 `shared/nautilus/*` (line 19-26 imports) + `shared/config` + `shared/risk`
- custos `_strategy_loader.py:90 _import_module_from_path` 从策略 path 加载, 需要 sys.path 里能找到 `shared/`
- 生产部署时策略 dir 必须**包含或链接** `shared/` 子树

---

## Track 划分 (待 Phase 2 精细化)

### Track 1 — custos `_strategy_loader.py` 加 registry-mode 分支

- 现状: `_strategy_loader.py:59 load_strategy_class` 只做 path→class 查找
- 新增: 若 spec 里含 `strategy_registry_name` (如 `"supertrend"`), 走 registry-mode:
  ```python
  # pseudocode
  from shared.nautilus.registry import create_strategy as registry_create_strategy
  instance = registry_create_strategy(spec["strategy_registry_name"], config_wrapper=cw)
  ```
- 保留原有 path→class 模式作为 fallback (对无 registry 的第三方策略仍可用)
- G6 gate code_hash 校验层: registry-mode 下 code_hash 覆盖**整个 registered strategy dir** 而非单 file

### Track 2 — supertrend config 启用 RiskController

- `philosophers-stone/trend/supertrend/config.yaml` 加 risk section:
  ```yaml
  risk:
    max_daily_loss: 0.05      # 5% daily loss cap
    max_drawdown: 0.15        # 15% drawdown cap
    consecutive_loss_limit: 5
  ```
- 值由 user + strategy owner 讨论敲定, 上面是初值示例
- 触发 `NautilusTradingStrategy:177 self._risk_controller = RiskController(...)` 非 None
- 验证: 单元测试注入超阈值 P&L, 断言 `RiskController.check(...)` 返回 `(False, "Max drawdown reached")`

### Track 3 — `shared/` 依赖打包路径

三选一 (待 Phase 2 决策):

- **选项 A**: 部署时把 `shared/` 目录**打包进策略 dir**, custos `_strategy_loader.py` 从策略 dir 相对路径加载
- **选项 B**: `shared/` **发布为 pip 包** (如 `alephain-shared`), 策略环境 `pip install` 依赖
- **选项 C**: custos 侧配置 `PS_SHARED_PATH` env var, sys.path 里显式加入; 部署时 mount 到容器
- 每选项的 code_hash / G6 gate 兼容性需 Phase 2 评估

### Track 4 — custos NtTradingNodeHost 扩展 TradingNodeConfig 借鉴 ps `_create_node_config`

- 当前 custos `nautilus_host.py:deploy` 组装的 `TradingNodeConfig` 是 minimal
- ps `runner.py:812 _create_node_config` 覆盖:
  - Redis cache + MessageBus (可选启用)
  - `timeout_connection` / `timeout_reconciliation` / `timeout_portfolio` / `timeout_disconnection`
  - `reconciliation_lookback_mins`
  - `LiveExecEngineConfig.reconciliation` toggle
- 借鉴到 custos, 通过 `DeploymentSpec.nautilus_config` 配置项传入

### Track 5 — E2E integration test (real supertrend, 无 arx)

- 新加 `tests/test_custos_hosts_real_supertrend_e2e.py`:
  - 从 fixture 加载 real ps supertrend (含 `shared/` 依赖)
  - 用 `NtTradingNodeHost` 跑 sandbox mode
  - 断言 G6 gate 通过 + `_risk_controller` 非 None + telemetry event 上报正常
- 覆盖 Plan 00a integration test 之外的 real-strategy 场景 (现有 `test_nt_trading_node_host_integration.py` 是 minimal stub)

### Track 6 — ps sidecar / runner.py 退休声明 (docs-only)

- 更新 `docs/design/nautilus_host.md` 加 "PS supertrend migration" 段
- 声明 ps `deploy/nautilus/runner.py` + `deploy/sidecar/` 在 custos 接管后**不再是主生产入口** (crucible 生态如仍需要则独立维护)
- arx web 侧 sidecar HTTP tech debt 独立议题, 记入 arx 侧 follow-up

---

## Historical Lessons 强制引用 (待 Phase 2 补齐)

- **lesson #14/#30/#33/#33b (Foundation Scan 四维)**: Phase 2 evidence-scout 必扫 `ps shared/nautilus/registry.py` + `ps supertrend config.yaml` 现状 + `custos _strategy_loader.py` 加载路径 + 上游 Plan 03 close-out 时间锚
- **lesson #17 (failure-mode ≠ happy-path)**: Track 5 e2e 必覆盖 real supertrend 的 config-partial / shared-missing / registry-not-found 失败模式
- **lesson #26 (boundary constant)**: registry name (`"supertrend"`) 是 boundary constant, custos + ps 侧命名对齐; 打包路径 (`PS_SHARED_PATH`) 若采 env var 是 lesson #35 fanout 场景
- **custos C2 (输出污染贯穿 review/self-review)**: 起 plan 时 grep 实证 registry API 签名 + shared 依赖树, 不采信推理
- **user 关键纠错保留**: sidecar 主消费者是 Crucible 不是 arx; supertrend 已有 `register_strategy` 无需策略侧改动 (记为 Phase 2 evidence 前提)

---

## 目标 (Goal, 待 Phase 2 精细化)

Plan 06 close-out 后:
- **custos 直接加载 real ps supertrend** (registry-mode + shared 依赖 resolve), 策略侧**零改动**
- **supertrend RiskController 启用**, 策略级 drawdown breaker 生效 (红线 0.3 per-strategy 层兑现)
- **e2e 集成测试** 覆盖 real supertrend 加载 + G6 gate + telemetry uplink
- **ps sidecar / runner.py 可退休**, 生产 custos 单一 supervisor stack

---

## Task List (待 Phase 2 精细化)

skeleton 暂列 high-level:

1. [T1] custos `_strategy_loader.py` 加 registry-mode 分支
2. [T2] `DeploymentSpec` 数据模型加 `strategy_registry_name` optional 字段
3. [T3] G6 gate code_hash 对 registered strategy dir 的适配
4. [T4] supertrend `config.yaml` risk section 加 (Plan 06 覆盖 ps 侧 patch)
5. [T5] `shared/` 依赖打包决策实施 (选项 A/B/C)
6. [T6] custos `nautilus_host.py` TradingNodeConfig 扩展 (借鉴 ps `_create_node_config`)
7. [T7] `test_custos_hosts_real_supertrend_e2e.py` 集成测试
8. [T8] `docs/design/nautilus_host.md` PS supertrend migration 段
9. [T9] ps sidecar / runner.py 退休声明 (仅文档, 不删代码)

---

## File Inventory (待 Phase 2 grep 实证锚点)

**⚠️ 路径基于 Plan 05 结构重构后的新目录**（`src/custos/engines/nautilus/*`）。若 Plan 05 未先落地则本 plan 路径需回退到 `src/arx_runner/*` 老路径（不推荐 — 会造成二次搬迁）。

skeleton 候选:

| 文件 | 类型 | 说明 |
|------|------|------|
| `custos/src/custos/engines/nautilus/strategy_loader.py` | 改 | Track 1 registry-mode 分支 (原 `_strategy_loader.py`) |
| `custos/src/custos/engines/nautilus/host.py` | 改 | Track 6 TradingNodeConfig 扩展 (原 `nautilus_host.py`) |
| `custos/tests/engines/nautilus/test_strategy_loader_registry_mode.py` | 新建 | Track 1 test |
| `custos/tests/engines/nautilus/test_custos_hosts_real_supertrend_e2e.py` | 新建 | Track 5 e2e (real ps supertrend + shared 依赖 resolve) |
| `custos/docs/design/nautilus_host.md` | 改 | Track 8 迁移说明 |
| `custos/docs/engines/nautilus.md` | 改 | Plan 05 已建 stub, 本 plan 补 ps supertrend 集成细节 |
| `philosophers-stone/trend/supertrend/config.yaml` | 改 (ps side!) | Track 4 启用 RiskController |
| `philosophers-stone/tests/test_supertrend_risk_controller_enabled.py` | 新建 (ps side!) | Track 4 test |
| custos 部署配置 (Dockerfile / entrypoint) | 改 | Track 3 shared 依赖打包决策实施 |
| custos DeploymentSpec 数据模型 (`custos/core/*.py` 或 `docs/domain.md`) | 改 | Track 2 加 `strategy_registry_name` optional 字段 |

**⚠️ 注意**: 本 plan **跨仓库改动** (custos + philosophers-stone 双仓 commit), 遵守 workspace `mandatory-rules.md` §6 "跨仓库 commit 仅 `git add <specific-file>`" 纪律。

---

## 失败模式覆盖契约表 (lesson #17, 待 Phase 2 具体化)

- registry-mode: strategy_registry_name 未注册 → 明确错误 (非 crash)
- registry-mode: `shared.nautilus.registry` import failure → G6 gate 拒绝
- code_hash: registry 策略 dir 内容变化 → G6 gate layer 1 拒绝
- config: RiskController 启用后, drawdown 超阈值 → 策略拒绝新单
- shared 依赖: `shared/nautilus` missing → 明确错误 (Track 3 决策项)
- real supertrend + sandbox: e2e 全绿

---

## 红线 gate 满足度表 (lesson #40, 待 Phase 2 填实)

| 红线 | 目标兑现 |
|------|---------|
| 0.1 Key/KEK | supertrend 配置里若含 key 引用 → 走 credential_vault (不允许明文) |
| 0.2 G6 gate | registry-mode 下 code_hash 覆盖 registered dir; 保持 4 层 gate |
| 0.3 失联 ≠ 停止 | **本 plan 兑现 per-strategy 层 (RiskController)**; per-runner 层由 Plan 04 兑现 |
| 0.4 Money math | RiskController 内部用 Decimal (grep `philosophers-stone/shared/risk/*.py` 需 Phase 2 实证) |

---

## 偏离与改进日志 (Deviation Log)

(Phase 2 精细化阶段填, Phase 3 执行阶段更新)

**candidate slots**:
- `DEV-06-SHARED-PACKAGING-CHOICE`: Track 3 选项 A/B/C 最终决策
- `DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY`: custos + ps 跨仓 commit 编排 (哪个先落, atomic 保证)

---

## 完成报告 (Close-out Report)

(Phase 3 执行完成后填)

---

## 下一步 (Next)

Plan 06 close-out 后:
- **custos + ps supertrend 生态可跑真实 paper/testnet e2e** (与 Plan 04 组合后, 红线 0.3 三层齐)
- **ps sidecar / runner.py 退休** (crucible 生态如仍需要则独立维护)
- **arx web sidecar HTTP tech debt 独立议题** — 触发 arx 项目起 plan 迁 NATS-only
- 后续 candidate:
  - **Plan 07**: OKX venue 支持 (README §Not Included Yet 已声明; custos `nautilus_host.py:203` hard-coded Binance 需泛化)
  - **Plan 08**: 第三方 NT 策略适配文档 (通用改造 checklist, 承接 user 诉求 2 — 一般 NT 策略仅需 ~10-30 LOC + 打包)
  - **Plan 09**: `arx_runner` → `custos_runner` 包名 rename (lesson #35 fanout, README 已声明 follow-up)
