# 06 — ps supertrend 迁移到 custos: registry-mode 加载 + RiskController 启用 + shared/ 依赖打包

> **Status**: ✅ Completed (2026-07-10; 06a slice landed `306b9e5` for Tracks 1-4, Plan 08 landed remainder Tracks 5-6 and this close-out)
> **Created**: 2026-07-09 (Plan 03 close-out 后, user 澄清诉求 — custos 接管 ps supertrend, 移除 ps sidecar/runner 遗留)
> **Refined**: 2026-07-09 (plan-drafter-06, opus-4-7[1m], evidence-scout §Plan 06 报告为唯一 grep 源; codex L1 peer directed-fix 同日: HIGH-1/HIGH-2/MED-3/FU-2)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Phase 2 refined, use `/forge:execute` 或 execute-team 实施
> **Depends on**: Plan 00a ✅ + Plan 00c ✅ + Plan 03 ✅ + **Plan 05** (结构重构 + rename; 本 plan File Inventory 用 Plan 05 之后新目录 `src/custos/engines/nautilus/*`) — **START gate = Plan 05 T2.2 done** (engines/nautilus/ 路径落定, 见 §Depends on 冻结点); **soft-depends** Plan 04 (红线 0.3 per-runner 层, 与本 plan per-strategy 层组合后三层齐)
> **Blocks**: 生产化 ps supertrend 首次 paper/testnet e2e 实跑 (Track 5 T-final 验收点) + Plan 07 (ps shared 精选迁移, 依赖本 plan Track 3 打包方案落地)
> **multi_session_scope**: **true** (跨仓库 custos + ps 双仓 + Track 3 vendoring 文件面广 + Track 5 e2e 依赖真 NT runtime + Binance testnet 网络; 逻辑改动小但集成面重 → 切片见 §进度追踪)

---

## 起源 (Origin)

Plan 03 close-out 后, user 澄清诉求 (session log 2026-07-09):

> custos 这套系统可以被 ps 项目引入, 跑起它之前写好的 supertrend 策略 (可以移除 ps 中 sidecar 等遗留服务)

evidence-scout §Plan 06 实证发现两个原本以为需要"改造 ps 侧"的项目实际 **ps 已就绪, 只需 custos 侧适配**, 且一处 skeleton 前提被 scout 修正 (集成路径远比想象简单):

1. **ps supertrend 已有完整 registry + 模块级 factory 双机制** (scout §2):
   - `philosophers-stone/trend/supertrend/refinement/nautilus/strategy.py:386-391` 模块顶部 `register_strategy(name="supertrend", ...)` **自注册**
   - `strategy.py:394-411` **另有**模块级 `def create_strategy(config: dict) -> SuperTrendStrategy:` — Crucible entry-point factory, 内部 load `base_config.yaml` → deep-merge → wrap `ConfigWrapper` → 调 registry-global `create_strategy("supertrend", config_wrapper=wrapper)`
   - `shared/nautilus/registry.py:222-288` `create_strategy(name, *, config=/config_path=/config_wrapper=)` 通用 factory; unregistered name 抛 `ValueError` 列出可用策略 (scout §3, `:265-267`)

2. **custos `_instantiate_strategy` 已能调 ps 模块级 factory** (scout §1 关键修正):
   - `nautilus_host.py:356-367` (Plan 05 后 `engines/nautilus/host.py`) `_instantiate_strategy()` **已有** factory-probe: `getattr(module, "create_strategy", None)` → `factory(spec.get("strategy_config", {}))`, docstring 明写 "ps-style entry point"
   - 这与 ps `strategy.py:394` 模块级 `create_strategy(config: dict)` **签名精确匹配** → 集成路径 (a) 可能**零改 custos 加载器**, 只需 `shared/` 可 resolve (Track 3)

3. **custos `strategy_loader.py` code_hash 已是 dir-hash** (scout §Plan 06 §1 + lesson #25 实证 `test_compute_dir_hash_is_deterministic_and_content_sensitive`):
   - `_strategy_loader.py:106 _find_strategy_class` path→class + `STRATEGY_CLASS` 属性优先; code_hash 覆盖策略 dir (非单 file) — **G6 layer 3 对策略 dir 已就位**, 但 vendored `shared/` 在策略 dir 之外, 需专项处理 (Track 3 + DEV-06-TOOLKIT-HASH-SCOPE)

4. **ps sidecar / runner.py 定位澄清** (scout §7 实证):
   - **sidecar 主消费者是 Crucible** (19 file: `crucible_engine/{sidecar_models,supervisor,risk_monitor,metrics_persister}.py` + `docker/sidecar.Dockerfile`), 不是 arx
   - arx 侧 9 处全在 `web/` 前端 (`web/lib/hooks/useApi.ts:208` 等), **零 Rust backend crate** 依赖 = crucible 时代 tech debt
   - custos 接管后 ps 侧 sidecar / runner.py **可整体退休** (crucible 生态如仍需要则独立维护)

---

## 上下文 (Context)

### 契约证据锚 (Step 1.5 Contract Verification Gate)

> **as-of evidence-scout Foundation Scan (main HEAD `db75846`, 2026-07-09)** + 上游 Plan 05 refined (as-of Plan 05 close-out 前的 refined 稿, `.forge/plans/2026-07/05-structural-refactor-engine-abstraction.md`)。全部锚点来自 scout 报告, 本 plan 禁 paraphrase, 直接引用 file:line。**dispatch 约束**: 只用 evidence-scout §Plan 06 + Plan 05 refined + skeleton 现有内容, 禁自行 grep 权威文档 (防 lesson C2 output-pollution)。lesson #25 测试名实存核实仅 grep `tests/` (非权威文档), 已执行。

| 被引用契约 | file:line (scout 实证) | 用途 |
|-----------|----------------------|------|
| ps 模块级 factory | scout §2: `strategy.py:394-411 def create_strategy(config: dict) -> SuperTrendStrategy` (内部 wrap ConfigWrapper + 调 registry) | Track 1 集成路径 (a) 核心 |
| ps 自注册 | scout §2: `strategy.py:386-391 register_strategy(name="supertrend", ...)` 模块顶部 | Track 1 |
| registry 通用 factory | scout §3: `shared/nautilus/registry.py:222-288 create_strategy(name, *, config/config_path/config_wrapper)`; unregistered → ValueError `:265-267` | Track 1 failure-mode row 1 |
| custos factory-probe | scout §1: `host.py` (原 `nautilus_host.py:356-367`) `_instantiate_strategy()` 已 probe `getattr(module,"create_strategy")` → `factory(spec.get("strategy_config",{}))` | Track 1 路径 (a) 零改前提 |
| custos loader path→class | scout §Plan 06 §1: `strategy_loader.py` (原 `_strategy_loader.py:59/106`) path→class + `STRATEGY_CLASS` 优先 + 类名以 `Strategy` 结尾 heuristic | Track 1 |
| code_hash 是 dir-hash | lesson #25 grep: `tests/test_strategy_loader.py:43 test_compute_dir_hash_is_deterministic_and_content_sensitive` | Track 1 G6 layer 3 现状 |
| supertrend config 无 risk | scout §5: `trend/supertrend/config.yaml` (340 行) `grep "^risk:\|max_daily_loss\|max_drawdown"` → **0 命中**; sections = strategy/parameters/warmup/trading/position/platforms/snapshot | Track 2 |
| RiskController 挂载点 | scout §5: `shared/nautilus/trading_strategy.py:177 self._risk_controller: RiskController \| None = None`; `:730-732` property getter; `:73 from shared.risk import ... RiskController` | Track 2 |
| RiskController Decimal-only | scout §5: `shared/risk/controller.py:33 class RiskController`; `:10 from decimal import Decimal`; `:22,26` fields `session_pnl/peak_equity: Decimal`; `:107-178 check_limits(current_equity: Decimal)` 全 Decimal | Track 2 红线 0.4 (Track 2 只填 config 不 touch 此 file) |
| ps shared/ 依赖闭包 | scout §4: supertrend 最小闭包 = `shared/config/` + `shared/nautilus/` (+ 传递 `coordinators/*` `risk/*`) + `shared/signals/`; `shared/hummingbot/` **NT path 排除** (scout §4) | Track 3 vendoring scope |
| custos 无跨仓依赖先例 | scout §6: custos `pyproject.toml` **零** `philosophers-stone` / path / git 依赖; `_import_module_from_path` **不 touch sys.path** | Track 3 greenfield |
| ps _create_node_config | scout §8: `deploy/nautilus/runner.py:812` (+`:1196` 第二 host flavor) `_create_node_config`; `:826-830` timeout_{connection/reconciliation/portfolio/disconnection} + reconciliation_lookback_mins; `:836-838` fail-fast validate | Track 4 借鉴 |
| custos TradingNodeConfig minimal | scout §8: `host.py:192-199` (原 `nautilus_host.py`) 仅 trader_id/logging/data_clients/exec_clients/exec_engine, **零** Redis/MessageBus/timeout 调优 | Track 4 |
| ps config timeout shape | scout §8: `config.yaml:213-228 platforms.nautilus.trading_node.{timeout_*,reconciliation_lookback_mins}` | Track 4 plumb 目标 |
| DeploymentSpec 是 dict | scout §10: `grep "class DeploymentSpec"` → **0**; 全签名 typed `dict` (e.g. `host.py deploy(spec: dict)`); 唯一纸面 schema = `docs/domain.md:103` field list, **无** `strategy_registry_name` / `risk_config` | Track 1/2 dict-key 而非 Pydantic field |
| sidecar Crucible 主消费 | scout §7: crucible 19 file (engine core + Dockerfile); arx 9 file 全 `web/` (`useApi.ts:208`), 零 Rust backend | Track 6 退休依据 |
| ps supertrend 现有测试 | scout §9: `tests/strategies/test_supertrend.py` + `test_supertrend_logic.py` (main tree; 另 `test_supertrend_snapshot.py`) | Track 5 避免重复覆盖 |

### plan-to-plan 引用 (Step 1.5)

| plan-id | 状态 | 引用的产物 | 校验 |
|---------|------|-----------|------|
| 05 | refined (未 close-out, Wave D 同批 commit) | `src/custos/engines/nautilus/{host,strategy_loader,risk,venue_binance}.py` 目录 (Plan 05 T2.2 落定) + `core/g6_gate.py` (T4.1) + `core/engine_protocol.py` (T3.1) + DP3 toolkit=`engines/nautilus/toolkit/` | Plan 05 §Blocks 04+06 冻结点 line 154-165 + §File Inventory B/A |
| 07 | 未起 (candidate) | 本 plan Track 3 打包方案 = Plan 07 File Inventory 锁定前提 | 本 plan close-out 提示 (§下一步) |

> **START gate (Plan 05 §Blocks line 158-160)**: Plan 06 T1.1 可 START = **Plan 05 T2.2 done** (engines/nautilus/ 4 文件 move + 去下划线落定)。若与 Plan 05 并行, 用 Plan 05 skeleton 路径起草, T2.2 close 后锁定实际最终目录名 (scout Cross-Plan §已 hedge)。

### custos 侧现状 (Plan 05 后目标态)

- `src/custos/engines/nautilus/strategy_loader.py` — path→class + `STRATEGY_CLASS` 优先 (Plan 05 去下划线 rename)
- `src/custos/engines/nautilus/host.py:356-367` — `_instantiate_strategy` 已 probe 模块级 `create_strategy` (path a 前提)
- `src/custos/core/g6_gate.py` — 4 层 gate (Plan 05 T4.1 抽出, 契约不变), code_hash layer 3 覆盖策略 dir
- `tests/fixtures/minimal_supertrend_strategy.py` — 零依赖 stub (生产要跑 real supertrend, 故 Track 5 e2e)
- `tests/engines/nautilus/` — Plan 05 T8.2 建的净新测试目录 (本 plan 新 test 落此)

### 借鉴机会 (转 Plan 04)

ps `deploy/nautilus/runner.py` `_collect_metrics/orders/positions/engine_status` (scout §Plan 04 §8) 借鉴到 Plan 04 状态快照; `runner.py:101 self._peak_equity: float = 0.0` 是 **float** (scout §8 ⚠️), Plan 04 借鉴须改 Decimal (红线 0.4), 不 copy-paste。本 plan Track 4 只借 `_create_node_config` 的 timeout/reconciliation 参数处理, 不借 float equity。

---

## 目标 (Goal)

Plan 06 close-out 后:
- **custos 直接加载 real ps supertrend** (集成路径 (a): 现有 factory-probe + `shared/` resolve, 策略侧**零改动**), 策略 dir code_hash 过 G6 layer 3
- **supertrend RiskController 启用** (config risk section), per-strategy drawdown breaker 生效 (红线 0.3 per-strategy 层兑现)
- **`shared/` 依赖以 vendored toolkit (方案 A) 打包**到 `src/custos/engines/nautilus/toolkit/`, 独立仓库自足性守住 (审计员 clone 单仓即可)
- **custos `host.py` TradingNodeConfig 借 ps `_create_node_config`** 扩展 timeout/reconciliation 参数 (通过 `DeploymentSpec.nautilus_config` dict-key)
- **e2e 集成测试**覆盖 real supertrend 加载 + G6 gate + RiskController 非 None + telemetry uplink; **testnet 首次 paper→testnet e2e 打通** (生产化验收点)
- **ps sidecar / runner.py 退休声明** (docs-only), 生产 custos 单一 supervisor stack

**红线名 (vision) ≠ 兑现声明 (reality, lesson #40/C40)**: 本 plan 兑现"per-strategy drawdown breaker (红线 0.3 一层) + supertrend 加载不弱化 Key/G6/money math"; per-runner cap (红线 0.3 另一层) 仍归 Plan 04。

---

## 架构 (Architecture)

custos 侧**近零逻辑改动**, 核心是"让现有加载路径找得到 ps 代码": (1) 集成路径 (a) — 复用 `host.py:356-367` 已有 factory-probe 调 ps 模块级 `create_strategy(config: dict)`, custos 不需新写 registry 分支, ps 侧 config-wrapping 内聚在 ps; (2) `shared/` 依赖以 vendored copy (方案 A, `git subtree`/`cp -r` snapshot) 落 `engines/nautilus/toolkit/` + loader/bootstrap 加 sys.path resolution; (3) supertrend config.yaml 加 risk section 激活 dormant 的 `RiskController` (ps 侧 config 改, 策略代码零改); (4) `TradingNodeConfig` 借 ps 参数扩展。**跨仓库** (custos + ps 双仓 commit), e2e 是集成兑现门。

**集成路径决策 (a) vs (b)** (scout §1): 推荐 **(a)** — 复用现有 factory-probe。理由: ps 模块级 `create_strategy(config: dict)` **内部**处理 ConfigWrapper (load base_config → merge → wrap, `strategy.py:402-411`), custos 只传 raw `dict` 即可, **与 ps registry 内部解耦**; 路径 (b) (custos 直调 `registry.create_strategy(name, config_wrapper=...)`) 需 custos 自行构造 `ConfigWrapper` = 复制 ps 内部逻辑, 反而耦合。T1.1 spike 生产路径 (相 B, vendored toolkit) 确认 (a); T1.2 加显式 `strategy_registry_name` 作**加载后校验** (custos 主动 registry 内省断言 probe 产出类匹配预期注册名, 抓静默误加载; unknown-name 错误由此 deliberate 内省确定可达 — 见 §Codex peer fix log HIGH-2), 非替换加载机制。

---

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| **集成路径 (a) 复用 factory-probe vs (b) 直调 registry?** | **(a)** — 复用 `host.py:356-367` 已有 probe (T1.1 spike 确认) | scout §1/§2: ps `create_strategy(config: dict)` 内聚 ConfigWrapper 构造, custos 零改加载器 + 与 ps registry 解耦; (b) 需 custos 复制 ConfigWrapper 逻辑反增耦合 |
| **`strategy_registry_name` 加为 Pydantic field?** | **否 — dict-key** (`spec.get("strategy_registry_name")`) | scout §10: DeploymentSpec 全仓是 plain `dict`, 无 Python class; 加 key 到 `docs/domain.md:103` field list + dict 访问 |
| `strategy_registry_name` 用途 | **加载后校验** (custos 主动 registry 内省: 用 name 查 registry 断言产出类匹配), 非主加载路径 | 抓 heuristic ("类名以 Strategy 结尾") 静默误加载; 路径 (a) 保持工作。**错误可达性 (codex HIGH-2)**: unknown-name 错误由 custos-side **后置内省** raise (deliberate lookup), 非主 factory-probe 加载路径 — registry.py ValueError 经此内省确定可达 |
| **shared/ 打包 A/B/C?** | **A: vendored copy → `engines/nautilus/toolkit/`** (drafter 推荐, DP1 CEO 终裁) | mandatory-rules §7 独立仓库自足 + non-custodial 承重墙 audit-able 优先; 详见 §Track 3 决策 + DEV-06-SHARED-PACKAGING-CHOICE |
| vendored toolkit 是否入 per-deploy code_hash? | **否 — 归 custos 供应链完整性** (provenance file + custos release signing), 非 G6 layer 3 per-deploy hash | toolkit 是 custos 自身 vendored 代码 (被 custos 仓库审计 + 签名 release 覆盖), 非 per-deployment 策略 dir; 见 DEV-06-TOOLKIT-HASH-SCOPE 【CEO DP4】(codex MED-3 elevate) |
| supertrend RiskController 默认参数 | **CEO 拍板** (DP2); drafter 供 3 档 (保守/中/激进) 候选 | 生产化默认值是资金风险决策, 非 drafter 技术判断; 见 DEV-06-RISK-CONTROLLER-PARAMS |
| ps sidecar/runner.py 退休时机 | 本 plan **docs-only** 声明; arx web NATS-only 迁移列 follow-up (DP3 CEO 定是否本 plan 引入 blocker) | scout §7: sidecar 主消费者 Crucible, arx 仅 web tech debt; custos 只负责声明"不再是主生产入口", 不删 ps/crucible 代码 |
| DeploymentSpec `nautilus_config` 加为? | **dict-key** (`spec.get("nautilus_config", {})`) | 同 strategy_registry_name, DeploymentSpec 是 dict; Track 4 timeout/reconciliation 参数走此 key |

---

## 承载决策 (Capability Hosting Decision)

不适用 — 本 plan 是既有 runner 的策略集成 + 依赖打包 + config 激活, 不新增 skill/hook/plan-mode/CLAUDE.md 能力载体。`strategy_registry_name` / `nautilus_config` 是 DeploymentSpec 的 dict-key (wire 数据契约), 非工具能力。

---

## Track 3 — shared/ 依赖打包方案评估 (DP1 core decision)

按 evidence-scout §4 ps `shared/` 目录树 (~90 file / 9 subpackage), supertrend 最小闭包 = `shared/config/` + `shared/nautilus/` (+ 传递 `coordinators/*` + `risk/*`) + `shared/signals/`; `shared/hummingbot/` **NT path 排除**。逐一评估 3 方案:

| 方案 | 机制 | pros | cons | 独立仓自足 (mandatory-rules §7) |
|------|------|------|------|-------------------------------|
| **A: vendored copy** (推荐) | `git subtree` / `cp -r` snapshot → `src/custos/engines/nautilus/toolkit/`, freeze + provenance file 记上游 commit | 独立仓自足最好 (审计员 clone 单仓即可读全部代码); non-custodial 承重墙 audit-able; 无外部 supply-chain | 上游 ps `shared/` 演进不自动同步 (更新失步风险) — **缓解**: `TOOLKIT_PROVENANCE.md` 记 upstream commit + 未来 `make toolkit-sync-check` diff | ✅ 完全自足 |
| **B: git submodule** | 指向 ps `shared/`, 版本 pin | 版本追踪精确 | **独立 clone 场景无法用** (submodule 需 ps 仓库存在) — **违反 mandatory-rules §7** 硬约束; audit 审计员单仓 clone 拿不到代码 | ❌ 破自足 |
| **C: 独立 PyPI package** (`alephain-nautilus-toolkit`) | ps `shared/` 抽出 + PyPI 发布, custos `pip install` | 版本管理 + 独立 clone 可 pip install | 引入外部依赖到 non-custodial 承重墙 (需 audit 该 PyPI pkg, supply-chain 风险 ↑); pip 装的代码审计员不易单仓验证 | ⚠️ 半自足 (依赖 PyPI 可信) |

**drafter 推荐: 方案 A** — 基于 mandatory-rules §7 独立仓库自足纪律 + non-custodial 承重墙"审计员 clone 单仓即可验证承诺"根本要求。B 直接违反 §7 (submodule 破单仓自足); C 引入 supply-chain 审计面到承重墙。**A 的唯一 con (更新失步) 通过 provenance file + sync-check 缓解**, 且 ps supertrend 是相对稳定的已回测策略 (演进频率低)。**仍留 CEO 终裁** (DP1 影响 Plan 07 shared 精选迁移执行路径)。

**Plan 06 / Plan 07 边界**: 本 plan Track 3 落**方案机制** + **supertrend 最小闭包 vendoring** (让 e2e 自足可跑); Plan 07 (ps shared 精选迁移) 做**更广的精选 curation** + 建立**持续 sync 纪律**。本 plan 只 vendor supertrend 跑通所需的最小 subset, 避免 Plan 07 大范围 re-curate 造成 churn。

---

## 文件清单 (File Inventory)

> 状态标注: **create** / **modify** / **vendor** (`git subtree`/`cp -r` 引入外部代码, 视作批量 create) / **delete**。`现状(test -f)` 列 = executor Foundation Scan `test -f` 预检期望。**⚠️ 路径基于 Plan 05 结构重构后新目录** (`src/custos/engines/nautilus/*`); Plan 05 T2.2 未落地则回退 `src/arx_runner/*` (不推荐, 二次搬迁)。

### A. custos 侧源码 (modify/create)

| 文件 | 状态 | 现状(test -f) | Track/Task | 说明 |
|------|------|--------------|-----------|------|
| `src/custos/engines/nautilus/strategy_loader.py` | modify | 存 (Plan 05 后) | T1.2 | 加 `strategy_registry_name` 加载后校验 + registry-import-failure → G6 reject 路径 (非替换 path→class) |
| `src/custos/engines/nautilus/host.py` | modify | 存 (Plan 05 后) | T4.1 | `TradingNodeConfig` 借 ps `_create_node_config` 扩 timeout/reconciliation (via `spec.get("nautilus_config",{})`) |
| `src/custos/engines/nautilus/toolkit/` (目录) | vendor | 缺 | T3.2 | ps `shared/` supertrend 最小闭包 vendored snapshot (方案 A) |
| `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` | create | 缺 | T3.1 | 记 upstream ps commit hash + vendored subset 清单 + sync 纪律 (缓解更新失步 con) |

### B. custos 侧测试 (create, 落 Plan 05 净新 `tests/engines/nautilus/`)

| 文件 | 状态 | 现状(test -f) | Track/Task | 说明 |
|------|------|--------------|-----------|------|
| `tests/engines/nautilus/test_strategy_loader_registry_mode.py` | create | 缺 | T1.1/T1.2 | 路径 (a) spike 确认 + registry-name 校验 + unknown-name reject |
| `tests/engines/nautilus/test_nautilus_config_extension.py` | create | 缺 | T4.1 | timeout/reconciliation 参数 plumb + venue mismatch → G6 reject |
| `tests/engines/nautilus/test_toolkit_provenance.py` | create | 缺 | T3.1/T3.3 | provenance 记录 + vendored 闭包无 float money math (红线 0.4 审计) |
| `tests/engines/nautilus/test_custos_hosts_real_supertrend_e2e.py` | create | 缺 | T5.1 | e2e: real ps supertrend (via vendored toolkit) + G6 + `_risk_controller` 非 None + telemetry |

### C. ps 侧改动 (cross-repo, philosophers-stone 仓)

| 文件 | 状态 | 现状(test -f) | Track/Task | 说明 |
|------|------|--------------|-----------|------|
| `philosophers-stone/trend/supertrend/config.yaml` | modify | 存 | T2.1 | 加 `risk:` section (CEO 定参数 DP2); 触发 dormant `RiskController` 非 None |
| `philosophers-stone/tests/strategies/test_supertrend_risk_controller_enabled.py` | create | 缺 | T2.2 | ps 侧: risk section 存在 → `_risk_controller` 非 None + drawdown 超阈值 → check_limits `(False, reason)` |

### D. 文档 / 配置 (modify/create)

| 文件 | 状态 | 现状(test -f) | Track/Task | 说明 |
|------|------|--------------|-----------|------|
| `docs/domain.md` | modify | 存 | T1.2 | `:103` DeploymentSpec field list 加 `strategy_registry_name` + `nautilus_config` (optional dict-key) |
| `docs/design/nautilus_host.md` | modify | 存 | T6.1 | 加 "PS supertrend migration" 段 + ps runner/sidecar 退休声明 + toolkit 与 code_hash scope 说明 |
| `docs/engines/nautilus.md` | modify | 存 (Plan 05 T7.1 建 stub) | T6.1 | 补 ps supertrend 集成细节 + registry-mode 集成路径 (a) |
| `Makefile` | modify | 存 | T3.1 | (可选) `toolkit-sync-check` target stub (缓解更新失步; 未来 plan 补实) |
| `.forge/README.md` | modify | 存 | T6.2 | close-out Status ⏳ → ✅ |

> **⚠️ 跨仓库改动**: 本 plan 改 custos + philosophers-stone 双仓, 遵守 mandatory-rules §6 "跨仓库 commit 仅 `git add <specific-file>`" + §4 scope 标注。custos commit scope=`custos`, ps commit scope=ps 侧约定。无 atomic 跨仓保证 — e2e (T5.1/T5.2) 是集成兑现门 (DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY)。

---

## 实现任务 (Tasks)

> **TDD 节奏**: 每 Task 先写失败断言 (红) → 最小实现 → 证实 (绿) → `make verify` 全绿 (custos 侧原子性) → commit。源码注释禁编号追踪 (lesson #15: 禁 `Plan 06`/`Task N`/`lesson #M`, 用语义指代如 "ps supertrend 集成")。**executor 起 Task 前先 Foundation Scan** (lesson #14/#30/#33): 确认 Plan 05 目录已落 + `test -f` 预检 File Inventory + grep ps 侧 `_risk_controller =` 挂载点 (scout §5 标记未读)。

### Track 1 — strategy_loader registry-mode 集成 (路径 a + 显式校验)

#### Task T1.1: Spike — 确认集成路径 (a) 加载 real supertrend (两相: 探索 sys.path 桥 → 生产 vendored 路径)
**Files**: `tests/engines/nautilus/test_strategy_loader_registry_mode.py` (create)

> **HIGH-1 校正 (codex peer)**: spike 的**探索桥** (临时 sys.path 指 ps 仓) 与**生产加载路径** (vendored toolkit at T3.2) 是**两条不同路径** — 探索桥仅证明 factory-probe *机制* 可行, **不**证明生产路径。故本 spike 拆两相, 且**加载-路径权威结论 (T1.2 所依赖) 只认相 B (vendored)**。执行顺序见 §进度追踪 06a intra-slice order: **T3.1 → T3.2 (vendor) → T1.1 相 B**; 相 A 可任意早跑作探索, 非 gating。

- **相 A (探索, 可选, 非生产, 非 gating)**: T3.2 vendoring 前想先验机制时, 用**临时 sys.path 指 ps 仓 `shared/`** 跑 `test_factory_probe_mechanism_via_temp_syspath` (标 `@pytest.mark.exploratory`, 断言 factory-probe 拿到 `SuperTrendStrategy`)。此路径 **throwaway** — 测试末移除 sys.path 注入, **明确不代表生产加载**, 不进 baseline gating
- **相 B (生产, gating, 前置 = T3.2 vendored toolkit 已落)**:
  - **Step 1 (红)**: `test -f tests/engines/nautilus/test_strategy_loader_registry_mode.py` → 缺; 写 `test_existing_loader_loads_real_supertrend_via_factory_probe` (经 **vendored toolkit** + T3.2 新加的 sys.path resolution 加载 ps `strategy.py` → 现有 `host.py:_instantiate_strategy` probe 调 `create_strategy(config)` → 断言得 `SuperTrendStrategy` 实例)
  - **Step 2**: 跑 → 红 (T3.2 未落 → toolkit import 失败; 或断言未实现)
  - **Step 3 (绿)**: T3.2 vendored toolkit resolve 后跑通; 断言 `type(instance).__name__ == "SuperTrendStrategy"` + `_find_strategy_class` heuristic 正确定位 (scout §1 (a) 前提)。**这是生产加载路径的权威确认** (与相 A 探索桥不同源)
  - **决策记录**: 相 B 绿 → 路径 (a) 经 vendored toolkit 生产可用确认, T1.2 只加校验; 相 B 红 → 路径 (b) 回退 (DEV-06-INTEGRATION-PATH), T1.2 加显式 registry 分支。**相 A 绿 但相 B 未跑 ≠ 路径确认** (codex HIGH-1)
- **Step 5**: commit `test(custos): spike confirming existing loader loads real supertrend via vendored toolkit`

#### Task T1.2: strategy_registry_name 加载后校验 (post-load registry 内省) + registry-import failure 处理

> **HIGH-2 校正 (codex peer)**: 路径 (a) 主加载按 **path→module→factory-probe**, custos **不**调 `registry.create_strategy(name=<user>)` 作主加载 → 若无额外动作, registry.py 的 unregistered-name `ValueError` (`:265-267`) 不自然可达。**收紧**: `strategy_registry_name` 校验实现为 **custos-side 后置 registry 内省** — custos 在 factory-probe 加载**后**, 用 `strategy_registry_name` **主动查 registry** 作断言步骤 (deliberate lookup)。这使 unknown-name 错误经此内省**确定可达**, 同时保持"post-load validation 非主加载路径"语义。错误分两类: (i) name 已注册但映射类 ≠ 加载类 → custos raise **mismatch** error; (ii) name 未注册 → registry 内省 lookup raise `ValueError` (scout §3 `:265-267`), custos 捕获后转 G6/load reject (结构化 log, 非裸 crash)。

**Files**: `src/custos/engines/nautilus/strategy_loader.py` (modify) + `tests/engines/nautilus/test_strategy_loader_registry_mode.py` (extend) + `docs/domain.md` (modify)
- **Step 1 (红)**: 写 `test_registry_name_mismatch_rejected` (spec `strategy_registry_name="supertrend"` 但 post-load 内省发现该 name 映射类 ≠ factory-probe 加载类 → custos mismatch error) + `test_registry_mode_unknown_strategy_rejected` (`strategy_registry_name` 传未注册名 → **post-load 内省 lookup** 触发 registry.py `ValueError` 列可用策略 scout §3 `:265-267` → custos 捕获转 reject, 非裸 crash) + `test_shared_import_failure_denied_at_g6` (toolkit missing → G6 gate 拒绝非 crash)
- **Step 2**: 跑 → 红
- **Step 3 (绿)**: `strategy_loader.py` 加: (1) 可选 `spec.get("strategy_registry_name")` — 若存在, **加载后主动调 registry 内省** (registry lookup by name) 断言该 name 已注册 **且** 映射类 == factory-probe 产出类 (抓 heuristic 静默误加载); unknown name → registry `ValueError` 捕获转结构化 reject; mismatch → custos error。**此内省是 deliberate 的断言调用, 非主加载路径** (主加载仍 path→probe); (2) `import shared...` (toolkit) 失败 → 结构化 `strategy_toolkit_import_failed` + 触发 G6 layer 拒绝 (非静默 crash, 红线可观测 lesson #21); `docs/domain.md:103` field list 加 `strategy_registry_name` (optional dict-key)
- **failure-mode**: registry-import failure 走 G6 reject (lesson #17 失败模式非 happy-path); unknown registry name → post-load 内省 lookup ValueError → 捕获转 reject (可达性由 deliberate 内省保证, codex HIGH-2); name mismatch → custos 明确 error
- **Step 5**: commit `feat(custos): add strategy_registry_name post-load registry introspection + toolkit import failure gate`

### Track 2 — supertrend config RiskController 激活 (ps 侧)

#### Task T2.1: supertrend config.yaml 加 risk section (ps-side, CEO 参数)
**Files**: `philosophers-stone/trend/supertrend/config.yaml` (modify)
- **前置 (executor Foundation Scan, scout §5 标记未读)**: grep `_risk_controller =` 在 `shared/nautilus/trading_strategy.py` (beyond `:177`) 找 config-driven 激活挂载点 + 确认 config risk section 的期望 key shape (scout §5 未读此机制, executor 必先实证再填 config)
- **Step 1 (红)**: `grep -n "^risk:" trend/supertrend/config.yaml` → 0 (scout §5 基线)
- **Step 3 (绿)**: 加 `risk:` section, 参数用 **CEO 定值** (DEV-06-RISK-CONTROLLER-PARAMS, 见偏离日志 3 档候选); key shape 对齐 Foundation Scan 找到的挂载点契约 (非凭想象)
- **failure-mode**: config risk section key 不匹配挂载点 → `_risk_controller` 仍 None (T2.2 test 抓)
- **Step 5**: commit (ps 侧 scope) `feat: enable RiskController for supertrend via config risk section`

#### Task T2.2: ps 侧 RiskController 激活 + drawdown breaker test
**Files**: `philosophers-stone/tests/strategies/test_supertrend_risk_controller_enabled.py` (create)
- **Step 1 (红)**: `test -f` → 缺; 写 `test_supertrend_risk_controller_activated_when_config_present` (risk section 存在 → `strategy._risk_controller` 非 None) + `test_supertrend_risk_controller_blocks_on_drawdown` (注入超 `max_drawdown` 的 equity → `check_limits(...)` 返回 `(False, <reason>)`)
- **Step 2**: 跑 → 红
- **Step 3 (绿)**: 断言 dormant `RiskController` (scout §5 `trading_strategy.py:177`) 被 config 激活 + drawdown 超阈值拒新单 (红线 0.3 per-strategy 层兑现)
- **failure-mode**: RiskController 内部 Decimal (scout §5 `controller.py` Decimal-only, 红线 0.4 无需额外验证此 file)
- **Step 5**: commit (ps 侧 scope) `test: assert supertrend RiskController activates + blocks on drawdown`

### Track 3 — shared/ vendored toolkit (方案 A) + 红线 0.4 审计

#### Task T3.1: vendoring 决策落地 + provenance file + sync-check stub
**Files**: `src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md` (create) + `Makefile` (modify, 可选) + `tests/engines/nautilus/test_toolkit_provenance.py` (create)
- **前置**: DP1 CEO 已定方案 A (若 CEO 改选 B/C, 本 Track 全部重构 — 故 T3.1 是 DP1 gate)
- **Step 1 (红)**: `test -f .../toolkit/TOOLKIT_PROVENANCE.md` → 缺; 写 `test_toolkit_provenance_records_upstream_commit` (provenance file 存在 + 含 upstream ps commit hash + vendored subset 清单)
- **Step 3 (绿)**: 写 provenance file (upstream commit + `shared/{config,nautilus,signals,risk}` subset 清单 + "vendored snapshot, sync via Plan 07" 说明); (可选) Makefile `toolkit-sync-check` stub target
- **Step 5**: commit `chore(custos): add vendored toolkit provenance manifest (packaging option A)`

#### Task T3.2: vendor supertrend 最小闭包到 toolkit/
**Files**: `src/custos/engines/nautilus/toolkit/` (vendor: `shared/config/` + `shared/nautilus/` 最小 + `shared/signals/` + `shared/risk/`, 排除 `shared/hummingbot/`)
- **Step 1 (红)**: `test -d src/custos/engines/nautilus/toolkit/nautilus` → 缺; loader spike (T1.1) import `shared...` → ModuleNotFoundError
- **Step 3 (绿)**: `git subtree` / `cp -r` vendor supertrend 闭包 (scout §4 最小 subset) → toolkit/; loader/bootstrap 加 sys.path resolution (toolkit root 入 sys.path, scout §6 确认现无 sys.path 逻辑, 需新加); T1.1 spike 转绿
- **failure-mode**: vendored 闭包不完整 (漏传递依赖 `coordinators/*`/`risk/*`) → import error (e2e T5.1 抓)
- **Step 5**: commit `chore(custos): vendor ps shared supertrend dependency closure into engines/nautilus/toolkit`

#### Task T3.3: vendored 闭包红线 0.4 审计 (float money math grep gate)
**Files**: `tests/engines/nautilus/test_toolkit_provenance.py` (extend)
- **Step 1 (红)**: 写 `test_vendored_toolkit_no_float_money_math` (grep vendored toolkit `float(.*price|float(.*amount|float(.*notional|float(.*equity` → 命中即 fail, 除非有 `# noqa: SILENT-OK` 类豁免注释)
- **Step 3 (绿)**: grep 审计 vendored 闭包; scout §5 确认 `shared/risk/controller.py` Decimal-only, 但**更广闭包** (`coordinators/*` 等) executor 必 grep 实证 (scout §8 flag `runner.py:101 float equity` 在 `deploy/` 非 `shared/`, 但闭包内需自查); 发现 float money path → 记 DEV + 决策 (承重墙不接受 float money math, 需上游 fix 或 vendored patch)
- **failure-mode**: vendored 代码含 float money math (红线 0.4) → gate fail, 阻断 e2e
- **Step 5**: commit `test(custos): red-line 0.4 grep gate on vendored toolkit money math`

### Track 4 — TradingNodeConfig 扩展 (借 ps _create_node_config)

#### Task T4.1: nautilus_config timeout/reconciliation plumb
**Files**: `src/custos/engines/nautilus/host.py` (modify) + `tests/engines/nautilus/test_nautilus_config_extension.py` (create)
- **Step 1 (红)**: 写 `test_nautilus_config_timeouts_plumbed` (spec 含 `nautilus_config.{timeout_connection,timeout_reconciliation,...}` → 组装的 `TradingNodeConfig` 反映这些值) + `test_nautilus_config_venue_mismatch_denied` (venue 与 host `supports_venue` 不符 → G6 layer 2 拒, `g6_gate_venue_unsupported`)
- **Step 2**: 跑 → 红
- **Step 3 (绿)**: `host.py:192-199` (scout §8, minimal) 扩展: 读 `spec.get("nautilus_config",{})` 的 timeout_{connection/reconciliation/portfolio/disconnection} + reconciliation_lookback_mins (借 ps `runner.py:826-830`); NT 内部默认为 fallback (无 key 时不改现状); **不借** ps float equity + **不引** Redis/MessageBus (超范围, 留未来)
- **failure-mode**: nautilus_config key 缺省 → NT 内部默认 (向后兼容, 现有 host test 无退化); venue mismatch → G6 layer 2 (scout §4 现成)
- **Step 5**: commit `feat(custos): plumb nautilus_config timeout/reconciliation into TradingNodeConfig`

### Track 5 — E2E real supertrend (sandbox → testnet)

#### Task T5.1: e2e real supertrend sandbox (无 arx)
**Files**: `tests/engines/nautilus/test_custos_hosts_real_supertrend_e2e.py` (create)
- **前置 (Foundation Scan)**: grep ps `tests/strategies/test_supertrend.py` + `test_supertrend_logic.py` (scout §9) 避免重复覆盖 `calculate_signal` 逻辑 — 本 e2e 只验**加载 + G6 + RiskController + telemetry**, 非策略信号逻辑
- **Step 1 (红)**: `test -f` → 缺; 写 `test_real_supertrend_loads_and_deploys_sandbox` (via vendored toolkit 加载 real supertrend → `NtTradingNodeHost` sandbox deploy → 断言 G6 gate 过 + `_risk_controller` 非 None + telemetry event 上报) + **`test_credential_not_in_telemetry_payload_supertrend`** (FU-2, codex peer + authority-reviewer leak-negative 正控: real supertrend deploy 时注入 sentinel credential → 断言 telemetry payload / DeploymentStatus / structlog 输出**均不含** raw key material sentinel, 红线 0.1; 复用 Plan 03 脱敏 processor, 但对 real-strategy telemetry 路径独立断言, 非仅靠既有回归)
- **Step 3 (绿)**: e2e 全绿 (real supertrend, sandbox mode, 无 arx 依赖); 覆盖 minimal stub (`test_nt_trading_node_host_integration.py`) 之外的 real-strategy 场景; credential leak-negative 断言绿
- **failure-mode**: real supertrend + sandbox 加载失败 (toolkit 闭包漏 / RiskController 未激活 / G6 拒) → 各有断言; **credential 泄漏到 telemetry/status/log (红线 0.1)** → `test_credential_not_in_telemetry_payload_supertrend` 拦 (FU-2 NEW leak-negative); testnet order rejected 路径 → OrderDenied → PreTradeRejected telemetry (scout nautilus_host.md §Pre-trade reject)
- **Step 5**: commit `test(custos): e2e real ps supertrend loads + deploys sandbox via vendored toolkit + credential leak-negative`

#### Task T5.2: testnet paper→testnet e2e (生产化验收点)
**Files**: `tests/engines/nautilus/test_custos_hosts_real_supertrend_e2e.py` (extend) + 手动 testnet 验证记录
- **前置**: nt-runtime extra 装 (py3.12+) + Binance testnet credential (via credential_vault, 红线 0.1 — 测试用 sandbox key 非真 key, mandatory-rules §5)
- **Step 1 (红)**: 写 `test_real_supertrend_testnet_deploy` (trading_mode=testnet → `BinanceLiveExecClientFactory` + `BinanceEnvironment.TESTNET`, scout nautilus_host.md §matrix) — 标 `@pytest.mark.integration` (需 testnet 网络, 非 baseline)
- **Step 3 (绿)**: testnet 真跑打通 (paper→testnet 首次 e2e); 若 testnet 网络/资金不可得 → 记 partial (手动验证 + DEV), 不阻断 baseline `make verify`
- **failure-mode**: testnet order rejected → structlog + telemetry 可观测 (红线 0.3 失联不静默); credential 全程不出进程 (红线 0.1, credential_vault 脱敏)
- **Step 5**: commit `test(custos): testnet e2e for real supertrend (paper→testnet acceptance)`

### Track 6 — sidecar/runner.py 退休声明 (docs) + close-out

#### Task T6.1: ps sidecar/runner.py 退休声明 (docs-only)
**Files**: `docs/design/nautilus_host.md` (modify) + `docs/engines/nautilus.md` (modify)
- **Step 1 (红)**: `grep -n "supertrend migration\|sidecar.*退休\|runner.py.*退休" docs/design/nautilus_host.md` → 0
- **Step 3 (绿)**: nautilus_host.md 加 "PS supertrend migration" 段: (1) 集成路径 (a) + vendored toolkit; (2) 声明 ps `deploy/nautilus/runner.py` + `deploy/sidecar/` 在 custos 接管后**不再是主生产入口** (scout §7: crucible 生态如仍需要则独立维护, custos 不删 crucible/ps 代码); (3) toolkit 与 code_hash scope 说明 (DEV-06-TOOLKIT-HASH-SCOPE 【CEO DP4】); nautilus.md 补集成细节; arx web sidecar HTTP tech debt 列独立 follow-up (DP3)
- **failure-mode (docs)**: 无代码 test; grep 自验退休声明落地 (lesson #13)
- **Step 5**: commit `docs(custos): declare ps sidecar/runner.py retirement + supertrend migration in nautilus_host`

#### Task T6.2: 文档收尾 (close-out) — **强制末尾任务**
**Files**: 本 plan md + `.forge/README.md`
**动作**:
1. 本 plan 顶 `Status: ⏳ → ✅ Completed` + `Completed: YYYY-MM-DD`
2. `.forge/README.md` 索引 Plan 06 `⏳ → ✅`
3. **完成报告章节** (含红线 gate 满足度表 lesson C40) 填实
4. Plan 07 起草提示: 本 plan Track 3 方案 A (vendored toolkit) 落定, Plan 07 可锁定 File Inventory (§下一步)
5. `git add <本 plan> .forge/README.md && git commit -m "docs(custos): mark plan 06 as completed"` (custos 侧; ps 侧独立 commit)

---

## 验证清单 (Verification)

- [ ] `make verify` (fmt-check + lint + pytest baseline): PASS (每 custos task 末尾 + close-out)
- [ ] 集成路径 (a) 确认: 现有 loader + factory-probe 加载 real supertrend (T1.1 spike 绿)
- [ ] `strategy_registry_name` 加载后校验 + unknown-name reject + toolkit-import-failure G6 拒 (T1.2)
- [ ] supertrend `RiskController` config 激活 + drawdown breaker 触发 (ps 侧 T2.2)
- [ ] vendored toolkit provenance 记录 + 红线 0.4 float money math grep gate 全绿 (T3.1/T3.3)
- [ ] `nautilus_config` timeout/reconciliation plumb + venue mismatch G6 拒 (T4.1)
- [ ] e2e real supertrend sandbox 全绿 (T5.1); testnet e2e 打通或 partial 记录 (T5.2)
- [ ] Non-Custodial 4 红线 grep 全 0 命中 (verification.md §红线专项, 新路径 + vendored toolkit)
- [ ] 契约表点名 test 全 grep 实存 (lesson #25 — §失败模式表标注)
- [ ] DeploymentSpec `strategy_registry_name` + `nautilus_config` 加到 `docs/domain.md:103` field list (dict-key, 非 Pydantic)
- [ ] 无死代码 / 无编号注释入源码 (lesson #15) / vendored toolkit 保留上游注释不算 custos 编号污染
- [ ] 跨仓库 commit 仅 `git add <specific-file>` (custos + ps 双仓, mandatory-rules §6)

---

## 进度追踪 (Progress)

| Task | Track | Status | Completed | Notes |
|------|-------|--------|-----------|-------|
| T1.1 spike 路径 (a) 确认 (相 A 探索桥 + 相 B 生产 vendored) | 1 | ✅ | 2026-07-09 (`306b9e5`) | 相 B production spike via vendored toolkit; 相 A exploratory bridge |
| T1.2 registry-name 校验 + import-failure gate | 1 | ✅ | 2026-07-09 (`306b9e5`) | dict-key (非 Pydantic); `sys.modules` cache idempotency (DEV-06-06A-STRATEGY-LOADER-SYS-MODULES-CACHE) |
| T2.1 supertrend config risk section (ps) | 2 | ✅ | 2026-07-09 (ps `3443e96`) | CEO DP2 medium tier: `max_daily_loss=0.05` / `max_drawdown=0.15` / `consecutive_loss_pause=5` (canonical name 校正 DEV-06-06A-DP2-FIELD-NAME-CORRECTION) |
| T2.2 ps RiskController 激活 test | 2 | ✅ | 2026-07-09 (ps `34b73a2`) | 红线 0.3 per-strategy 层; T2.1 semantics 校正为 override 非 first-time activation (DEV-06-06A-T21-SEMANTICS-CLARIFICATION) |
| T3.1 vendoring 决策 + provenance | 3 | ✅ | 2026-07-09 (`306b9e5`) | DP1 方案 A (P1 revert from initial C); `TOOLKIT_PROVENANCE.md` + Makefile `toolkit-sync-check` stub |
| T3.2 vendor supertrend 闭包 | 3 | ✅ | 2026-07-09 (`306b9e5`) | vendor ps `shared/` @ `fc4ab1d` + `pandas_ta` @ fork `a3a2228` (MIT, DEV-06-06A-VENDOR-PANDAS-TA-DECISION-B); 247 files / +32,802 LOC |
| T3.3 红线 0.4 float grep gate | 3 | ✅ | 2026-07-09 (`306b9e5`) | vendored 闭包审计: 10 非 fund-flow exemptions (5 warmup/snapshot + 5 startup_validator), watchdog `test_vendored_toolkit_no_new_float_money_math` |
| T4.1 nautilus_config plumb | 4 | ✅ | 2026-07-09 (`306b9e5`) | `TradingNodeConfig` timeout/reconciliation via `DeploymentSpec.nautilus_config`; 3 tests (override / defaults / partial-dict) |
| T5.1 e2e real supertrend sandbox | 5 | 🔲 06b→08 | | 无 arx; **defer to Plan 08** (承接 06b, FU-AUTH-3 独立 clone 场景 vendored `strategy.py` 快照 or `@pytest.mark.integration`) |
| T5.2 testnet paper→testnet e2e | 5 | 🔲 06b→08 | | 生产化验收点; @integration; **defer to Plan 08** |
| T6.1 sidecar/runner 退休 docs | 6 | 🔲 06b→08 | | docs-only, DP3; **defer to Plan 08** |
| T6.2 close-out | 6 | 🔲 06b→08 | | 强制末尾; **Plan 06 完整 close-out 由 Plan 08 收尾** |

**切片建议 (multi_session_scope=true)**:
- **06a (Tracks 1-4)**: registry 集成 + config 激活 + vendoring + node config — custos+ps 代码集成主体 (~8 task)。含 T3 vendoring (文件面广但机械) + 红线审计。**intra-slice 执行序 (HIGH-1 校正)**: `T3.1 (provenance) → T3.2 (vendor 闭包) → T1.1 相 B (生产 spike, 依赖 vendored toolkit) → T1.2 → T2.1/T2.2 (ps 侧可并行) → T3.3 (红线审计) → T4.1`; T1.1 相 A 探索桥非 gating, 可任意早跑
- **06b (Tracks 5-6)**: e2e (sandbox + testnet) + 退休 docs + close-out — 集成验收 + 声明 (~4 task)。T5.2 testnet 依赖网络/testnet 资金, 可能独立 session
- execute-team 单 session 跑不完 06 全量时按此切; 06a 优先 (06b e2e 依赖 06a 代码 + toolkit 落地)。跨仓库改动 (custos+ps) 在 06a 内两仓独立 commit。

---

## 失败模式覆盖契约表 (lesson #17 + #25)

> **status 列**: ✓existing = 本 drafter grep 实证真存在 (lesson #25 反 fabricated, 2026-07-09 grep `tests/`); NEW = executor 创建。existing 测试仅作 no-regression 参照。

| Track | 失败场景 | 覆盖 test | status |
|-------|---------|-----------|--------|
| T1.1 | 现有 loader 无法加载 real supertrend (生产 vendored 路径, 相 B gating) | `test_existing_loader_loads_real_supertrend_via_factory_probe` | NEW |
| T1.1 | factory-probe 机制探索 (临时 sys.path 桥, 相 A 非 gating) | `test_factory_probe_mechanism_via_temp_syspath` (@exploratory, 非 baseline) | NEW |
| T1.2 | registry name 不匹配静默误加载 | `test_registry_name_mismatch_rejected` | NEW |
| T1.2 | strategy_registry_name 未注册 (post-load 内省 lookup) | `test_registry_mode_unknown_strategy_rejected` (post-load registry 内省 → registry.py:265-267 ValueError 捕获转 reject, codex HIGH-2 可达性) | NEW |
| T1.2 | toolkit/shared import failure 静默 | `test_shared_import_failure_denied_at_g6` (→ G6 拒非 crash, lesson #21) | NEW |
| T1 (no-regr) | 现有 path→class 加载退化 | `test_matching_hash_loads_class` / `test_explicit_strategy_class_attribute_wins` / `test_hash_mismatch_rejected` | ✓existing |
| T1 (no-regr) | code_hash dir-hash 退化 | `test_compute_dir_hash_is_deterministic_and_content_sensitive` | ✓existing |
| T2.2 | config risk section 存在但 RiskController 仍 None | `test_supertrend_risk_controller_activated_when_config_present` | NEW (ps) |
| T2.2 | drawdown 超阈值未拒新单 | `test_supertrend_risk_controller_blocks_on_drawdown` | NEW (ps) |
| T3.1 | vendored toolkit 更新失步无追踪 | `test_toolkit_provenance_records_upstream_commit` | NEW |
| T3.3 | vendored 闭包含 float money math (红线 0.4) | `test_vendored_toolkit_no_float_money_math` | NEW |
| T4.1 | nautilus_config timeout 未 plumb | `test_nautilus_config_timeouts_plumbed` | NEW |
| T4.1 | venue mismatch 未拒 | `test_nautilus_config_venue_mismatch_denied` (→ g6_gate_venue_unsupported) | NEW |
| T5.1 | real supertrend sandbox 加载/部署失败 | `test_real_supertrend_loads_and_deploys_sandbox` | NEW |
| T5.1 | credential 泄漏到 telemetry/status/log (红线 0.1, FU-2) | `test_credential_not_in_telemetry_payload_supertrend` (leak-negative 正控, codex FU-2 + authority-reviewer) | NEW |
| T5.2 | testnet order rejected 静默 | `test_real_supertrend_testnet_deploy` (→ OrderDenied telemetry, @integration) | NEW |
| T5 (no-regr) | 现有 sandbox lifecycle 退化 | `test_full_lifecycle_sandbox_supertrend` / `test_deploy_code_hash_mismatch_rejected` | ✓existing |

> **existing test grep 实证 (2026-07-09, lesson #25)**: `tests/test_strategy_loader.py` (6 fn: `test_compute_dir_hash_is_deterministic_and_content_sensitive` / `test_hash_mismatch_rejected` / `test_matching_hash_loads_class` / `test_sandbox_hash_none_skips_check_but_audits` / `test_strategy_path_not_found` / `test_explicit_strategy_class_attribute_wins`) + `tests/test_nt_trading_node_host_integration.py` (3 fn: `test_full_lifecycle_sandbox_supertrend` / `test_deploy_missing_nt_extra_fails_fast` / `test_deploy_code_hash_mismatch_rejected`) + `tests/fixtures/minimal_supertrend_strategy.py` 存在。**NEW test executor close-out 前必 `grep -rn "def test_X" tests/` 实存** (lesson #25 gate)。ps 侧 NEW test 同理 grep ps `tests/`。

---

## 红线 gate 满足度表 (lesson #40 / custos C40)

> **红线名 (vision) ≠ 兑现声明 (reality)**: 区分 code_coverage (test 覆盖逻辑) / runtime_wire (composition root 真接线) / defer_status (延后 scope)。

| 红线 | 目标兑现 | code_coverage | runtime_wire | defer_status |
|------|---------|---------------|--------------|--------------|
| 0.1 Key/KEK 不出进程 | supertrend config 不含明文 key (走 credential_vault 引用); credential 全程解密→NT client, 不 log/publish | T5.1 `test_credential_not_in_telemetry_payload_supertrend` (FU-2 leak-negative 正控) + e2e (T5.1/T5.2) 断言 credential 经 vault 流入 NT, 脱敏 test 无退化 (Plan 03) | `deploy()` 经 credential_vault decrypt → NT client only (scout nautilus_host.md §credential lifecycle 3 层 invariant) | 无 defer |
| 0.2 G6 gate 不绕过 | 策略 dir code_hash 过 G6 layer 3 (dir-hash 现成); vendored toolkit 归 custos 供应链完整性 (provenance + release signing), **非** per-deploy code_hash | T1.2 toolkit-import-failure → G6 拒; G6 4 层不变 (Plan 05 g6_gate.py) | G6 call sites 保持接线 (Plan 05 core/g6_gate.py); registry-import failure 接 gate reject | toolkit-in-code_hash scope = **CEO DP4 决策** DEV-06-TOOLKIT-HASH-SCOPE (codex MED-3 elevate; 非 defer) |
| 0.3 失联 ≠ 停止 | **本 plan 兑现 per-strategy 层** (RiskController drawdown breaker) | ps T2.2 `test_supertrend_risk_controller_blocks_on_drawdown` | `_risk_controller` 非 None at runtime (config 激活, ps trading_strategy.py:177 挂载) | **per-runner cap 层 defer 到 Plan 04** (Tier-2, 三层齐需 Plan 04+06 组合) |
| 0.4 Money math Decimal | RiskController 内部 Decimal (scout §5 `controller.py` Decimal-only); vendored 闭包 grep 审计无 float money math | T3.3 `test_vendored_toolkit_no_float_money_math` grep gate | RiskController Decimal 计算路径 (ps 侧, 不 touch) | 无 defer (审计通过前不合入) |

**兑现范围声明 (close-out 填实)**: "supertrend 加载/config 激活/vendoring 均不弱化 Key(0.1)/G6(0.2)/money math(0.4); per-strategy drawdown breaker(0.3 一层)兑现, per-runner cap(0.3 另一层)仍归 Plan 04。vendored toolkit 红线 0.4 grep 审计全绿; e2e 断言 credential 不出进程。" — 集成不允许把红线兑现能力降级。

---

## 偏离与改进日志 (Deviations & Improvements)

> **CEO 决策点 ×4 (elevate, 不静默决定)**: DP1 drafter 推荐 A + BOTH options 记 (影响 Plan 07); DP2 drafter 供 3 档候选, CEO 拍板; DP3 drafter 主体 docs-only, CEO 定 arx 迁移 follow-up 是否入 blocker; **DP4 (codex MED-3 elevate) DEV-06-TOOLKIT-HASH-SCOPE — G6/红线 0.2 边界决策, drafter 推荐 A (toolkit 不入 per-deploy hash) + BOTH options, CEO 终裁**。

### DEV-06-SHARED-PACKAGING-CHOICE 【CEO DECISION POINT 1】
- **等级**: 中 (影响 Plan 07 执行路径 + 引入外部代码到 non-custodial 承重墙)
- **问题**: ps `shared/` 依赖打包 A (vendored) / B (submodule) / C (PyPI pkg)
- **Option A (推荐, 主体采纳)**: **vendored copy → `engines/nautilus/toolkit/`** (`git subtree`/`cp -r` snapshot + provenance)。理由: mandatory-rules §7 独立仓库自足 + non-custodial 承重墙 audit-able (审计员 clone 单仓即验证)。con (更新失步) 由 provenance file + 未来 sync-check 缓解
- **Option B**: git submodule — **违反 §7** (独立 clone 场景 submodule 不可用, 破单仓自足硬约束)
- **Option C**: 独立 PyPI pkg (`alephain-nautilus-toolkit`) — 引入 supply-chain 审计面到承重墙 (pip 装代码审计员不易单仓验证)
- **影响**: A: `engines/nautilus/toolkit/` vendored (Plan 07 curate) / B: `.gitmodules` / C: `pyproject.toml` 加依赖 + 独立发布 pipeline
- **决定**: 主体 A (T3.1/T3.2); **CEO 终裁** (选 B/C 则 Track 3 全重构)
- **CEO 拍板 (2026-07-09, /forge:execute-team G3 dispatch AskUserQuestion)**: **A: vendored copy** (走 drafter 推荐主体路径, P1 confirm)
  - 初次 CEO 选 C (独立 PyPI pkg), Execution Lead 提示 C 的连锁影响 (Track 3 全重构 + supply-chain 审计面 + 发布节奏耦合 + 超出 06a scope), CEO 二次确认改回 A
  - C 记为 **DEV-06-DP1-DEFERRED-C-OPTION** 未来备忘 — 若 provenance/sync-check 触发 toolkit 更新失步且规模化后, 可作 pkg 化升级路径; 现阶段独立仓库自足 (§7) + audit-able 优先
- **更新的文档**: TOOLKIT_PROVENANCE.md + docs/design/nautilus_host.md

### DEV-06-DP1-DEFERRED-C-OPTION (P1 override 备忘)
- **等级**: 低 (未来备忘, 非本 plan 执行项)
- **背景**: DP1 CEO 初选 C (独立 PyPI pkg), 二次确认改 A。C 的价值 (供应链治理清晰 + 独立发布节奏) 记为未来选项, 不在本 plan 落地
- **触发再评估条件**: (a) toolkit 更新失步频繁 (每季度 >2 次 upstream drift 靠 provenance 追赶不及); (b) 其他 non-Guild 项目复用 toolkit 需求出现; (c) custos 生态 Rust 平替启动时 toolkit 需 pkg 化解耦
- **决定**: 不入本 plan; 由未来独立 plan (候选 Plan 07-pkg-track 或 pivot plan) 承接

### DEV-06-RISK-CONTROLLER-PARAMS 【CEO DECISION POINT 2】
- **等级**: 中 (生产化默认资金风险参数)
- **问题**: supertrend RiskController `max_daily_loss` / `max_drawdown` / `consecutive_loss_limit` 生产化默认值
- **drafter 供 3 档候选** (CEO 拍板, 非 drafter 技术判断):
  - **保守**: `max_daily_loss: 0.03` (3%) / `max_drawdown: 0.10` (10%) / `consecutive_loss_limit: 3`
  - **中 (推荐起点)**: `max_daily_loss: 0.05` (5%) / `max_drawdown: 0.15` (15%) / `consecutive_loss_limit: 5`
  - **激进**: `max_daily_loss: 0.08` (8%) / `max_drawdown: 0.25` (25%) / `consecutive_loss_limit: 8`
- **前置**: executor T2.1 先 grep `_risk_controller =` 挂载点 (scout §5 未读机制) 确认 config key shape, 再填值
- **决定**: **CEO 拍板具体档位** (与 strategy owner 讨论); drafter 无默认权 (资金风险)
- **CEO 拍板 (2026-07-09)**: **中 (推荐起点)** — `max_daily_loss: 0.05` (5%) / `max_drawdown: 0.15` (15%) / `consecutive_loss_limit: 5`
- **更新的文档**: philosophers-stone/trend/supertrend/config.yaml

### DEV-06-SIDECAR-RETIREMENT-TIMING 【CEO DECISION POINT 3】
- **等级**: 中 (跨子系统 arx web tech debt)
- **问题**: ps sidecar/runner.py 退休 — 本 plan 仅 docs-only 声明, vs 引入 arx web NATS-only 迁移 follow-up plan 到 blockers
- **Option A (推荐, 主体采纳)**: **本 plan docs-only** — 声明 ps runner/sidecar 不再是主生产入口 (scout §7: crucible 主消费者, custos 不删 crucible/ps 代码); arx web sidecar HTTP (`useApi.ts:208`) 独立 tech debt, 列 arx 侧 follow-up candidate, **不入本 plan blocker**
- **Option B**: 本 plan 引入 arx web NATS-only 迁移到 blockers — 扩大 scope 到 arx 前端仓, 跨 3 仓 (custos+ps+arx) 协调
- **决定**: 主体 A (T6.1 docs-only + arx follow-up 列 §下一步); **CEO 定** 是否升级 arx 迁移为本 plan blocker
- **CEO 拍板 (2026-07-09)**: **A: docs-only** (对齐 drafter 推荐, arx 迁移不入本 plan blocker, 归 arx 侧 follow-up candidate)
- **更新的文档**: docs/design/nautilus_host.md

### DEV-06-TOOLKIT-HASH-SCOPE 【CEO DECISION POINT 4】
- **等级**: **红线 0.2 / G6 边界** (codex MED-3 elevate: 定义"什么落在 per-deploy G6 hash 之外" = G6 承重墙边界决策, 非 drafter 单方可定; 从原 "drafter 决定 CEO ratify" 升为完整 CEO decision point)
- **问题**: vendored toolkit 是否入 per-deploy G6 code_hash (layer 3) scope
- **Option A (drafter 推荐, 主体采纳)**: **否 — toolkit 不入 per-deploy code_hash**; 归 custos 供应链完整性 (provenance file + custos 签名 release 覆盖)。理由: toolkit 是 custos 自身 vendored 代码 (仓库审计 + 签名 release 已覆盖), 非 per-deployment 策略 dir; G6 layer 3 覆盖策略 dir。**多层守** (lesson #22): 策略 dir code_hash + toolkit provenance + custos release signing 三层, 非单点。若塞进 per-deploy hash, 每次 toolkit 更新需重算所有部署 hash, 且 toolkit 版本本应由 custos release 统一管理 (非 per-deploy)
- **Option B (备选, 被拒理由记录)**: **是 — toolkit 入 per-deploy G6 code_hash layer 3**; 每次部署把 vendored toolkit 一并 hash。pro: 单一 hash 覆盖策略+toolkit 全供应链; con: toolkit 更新 = 全部署 hash 失效需重算 + 与 "toolkit 由 custos release 统一管理" 治理模型冲突 (per-deploy 层不该管 custos 自身代码版本)
- **影响**: A: G6 layer 3 scope 保持仅策略 dir + toolkit 由 provenance/signing 覆盖 (docs 决策) / B: `core/g6_gate.py` code_hash 计算需纳入 toolkit dir + 部署 hash 语义变更 (T3.x/T4.1 追加 toolkit-in-hash 计算)
- **drafter 推荐**: A (承重墙: toolkit 篡改由 custos 供应链层拦, 非策略部署层; 与 Plan 05 G6 4 层契约不变对齐)
- **决定**: 主体 A; **CEO 终裁** (wait state — 选 B 则 g6_gate.py code_hash scope 扩展 + 部署 hash 语义变更)
- **CEO 拍板 (2026-07-09)**: **A: toolkit 不入 per-deploy code_hash** (对齐 drafter 推荐 + G6 4 层契约不变); 多层守 = 策略 dir hash + toolkit provenance + custos release signing
- **更新的文档**: docs/design/nautilus_host.md §G6 + code_hash scope

### DEV-06-INTEGRATION-PATH (spike 决定)
- **等级**: 低 (内部加载机制)
- **问题**: 集成路径 (a) 复用 factory-probe vs (b) 直调 registry
- **决定**: 主体 **(a)** (T1.1 spike 确认); spike 红则回退 (b) 加显式 registry 分支。理由 scout §1/§2: ps `create_strategy(config)` 内聚 ConfigWrapper, custos 零改 + 解耦

### DEV-06-DEPLOYMENTSPEC-DICT-NOT-CLASS (scout §10 修正)
- **等级**: 低 (skeleton 前提修正)
- **问题**: skeleton 原写"DeploymentSpec 数据模型加字段", 实际 DeploymentSpec 是 plain dict (scout §10, 无 Pydantic class)
- **决定**: `strategy_registry_name` + `nautilus_config` 加为 `docs/domain.md:103` field list 条目 + dict-key 访问 (`spec.get(...)`), 非 Pydantic field。若未来 plan 形式化 DeploymentSpec 为 Pydantic model 再迁

### DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY
- **等级**: 中 (跨仓库 custos + ps)
- **问题**: custos + ps 双仓 commit 编排 + atomic 保证
- **决定**: 两仓独立 commit (`git add <specific-file>`, mandatory-rules §6); 无 atomic 跨仓保证 — e2e (T5.1/T5.2) 是集成兑现门。ps 侧 config/test 先落 (strategy owner 变更), custos 侧消费; 但 e2e 需两侧都 ready

---

## Codex peer fix log (Wave D directed fix, 2026-07-09)

> L1 codex peer review (`.forge/reviews/2026-07/04-05-06-peer-codex.md`) 对 Plan 06 verdict = REQUEST_CHANGES (2 net-new HIGH + MED-3 + FU-2)。plan-drafter-06 定向 in-place fix (CEO option C), 只 fix 这 4 项, 不重构其他 Track, 不改 Plan 04/05。verdict → **APPROVED_WITH_FOLLOW_UPS**。

| codex finding | 选项 | fix 位置 | why |
|---------------|------|---------|-----|
| **HIGH-1** T1.1 spike 前置 T3.2 但顺序倒置 + 临时 sys.path 桥 ≠ 生产 vendored 路径 | **Option B** (sys.path 桥语义显式化 + validation gate) | T1.1 拆两相 (相 A 探索桥 throwaway / 相 B 生产 vendored gating) + §进度追踪 06a intra-slice 序 `T3.1→T3.2→T1.1 相 B` + 失败模式表加相 A/相 B 两行 + 进度追踪 T1.1 行注 | 保留 spike 探索性 (相 A 早跑无阻), 但把"探索桥仅证机制"与"生产 vendored 路径才是权威结论"显式拆开; T1.2 依赖的加载确认硬绑相 B (T3.2 后)。比 Option A 全 Track 重排 less disruptive |
| **HIGH-2** registry-mode 错误语义 — post-load validation 下 registry.py ValueError 不自然可达 | **Option B** (澄清错误路径来源: custos-side 后置 registry 内省) | T1.2 头部 HIGH-2 校正块 + T1.2 Step 1/3/failure-mode 重写 + 架构段 + 关键设计决策表 `strategy_registry_name 用途` 行 + 失败模式表 T1.2 unknown 行 | 主加载仍 path→probe (路径 a 不变); `strategy_registry_name` 校验实现为 **custos 主动 registry 内省** (deliberate lookup by name) — unknown-name 经此内省触发 registry.py ValueError 后捕获转 reject, 使错误**确定可达**, 同时"post-load validation 非主加载"语义保持。比 Option A (把 registry_lookup 提为主加载) 保留路径 (a) 解耦优势 |
| **MED-3** DEV-06-TOOLKIT-HASH-SCOPE 是 G6/红线 0.2 边界决策却记为 drafter 决定 | promote 为 **CEO DP4** | DEV-06-TOOLKIT-HASH-SCOPE 改 【CEO DECISION POINT 4】格式 (Option A/B + drafter 推荐 A + wait state) + 偏离日志头 ×3→×4 + 关键设计决策表/红线 gate 表/T6.1 引用同步 | 定义"什么落在 per-deploy G6 hash 之外" = G6 承重墙边界, 非 drafter 单方; 与 DP1/DP2/DP3 同格式 elevate |
| **FU-2** 缺 credential leak-negative 正控 (依赖既有脱敏回归 + e2e flow 断言) | 加 NEW test | T5.1 加 `test_credential_not_in_telemetry_payload_supertrend` (Step 1 红 + failure-mode + 失败模式契约表 + 红线 gate 表 0.1 code_coverage) | grep 实证 (lesson #25) 该 test 名全仓 0 命中 = NEW; real-strategy telemetry 路径独立断言 raw key material 不入 telemetry/status/log (红线 0.1), 非仅靠既有脱敏回归 |

**约束遵守**: 只 fix HIGH-1/HIGH-2/MED-3/FU-2; 未改 Plan 04/05; 未重构其他 Track; 契约引用 grep 实证 (lesson #25 — FU-2 test 名 `grep -rn tests/` 0 命中确认 NEW); in-place refinement; forge:planning skill invoked; 禁 opus 4-8 (opus-4-7[1m])。

---

## 完成报告 (Close-out Report)

> **Status**: ⚠️ **Partial (06a slice) — Plan 06 整体 close-out 由 Plan 08 收尾时统一签发**（06b 已被 `plan-team-07-08-09-packet` §3 明确框定为 Plan 08 = "Plan 06 剩余 e2e / docs / close-out"）。
> 本段记录 06a slice 落地事实；Plan 06 全部 12 task 完整 close-out 待 Plan 08 完成。

### 06a partial close-out (2026-07-09)

- **完成日期 (06a)**: 2026-07-09
- **06a Task 数**: 8 (Tracks 1-4) / 全 plan 12 (4 defer 06b → Plan 08: T5.1 + T5.2 + T6.1 + T6.2)
- **偏离数 (06a)**: 1 MED + 7 LOW + 2 note — 明细见 `.forge/triage/06a-DEVIATION-triage.md`
  - MED: DEV-06-06A-VENDOR-PANDAS-TA-DECISION-B (CEO decision option B, MIT LICENSE, vendored fork `a3a2228`)
  - LOW × 7: SCOUT-COORDINATORS-PATH-CORRECTION / T21-SEMANTICS-CLARIFICATION / DP2-FIELD-NAME-CORRECTION / STALE-LINE-ANCHOR / PANDAS-TA-FLOAT-EXCEPTIONS / CHECK-CODE-ENGLISH-HOOK-EXEMPTION / STRATEGY-LOADER-SYS-MODULES-CACHE
  - note × 2: REVERSE-DEPENDENCY-STRATEGY-D→D' (Plan 07 承接架构最终态) / CEO-PAUSE-FOR-PLAN-07-CROSSED (lesson #34 exemplar, C3 candidate)
- **验证结果 (06a)**: `make verify` 263 pass (custos) + 3 pass (ps) at slice HEAD (per marker constraints_honored)
- **实施 commit 范围**: custos `306b9e5` (06a squash, base `55782d0` → HEAD `69a92dd` 8 commits) + orchestration `55782d0` + hook infra `5c01cdb` + pre-spawn 记录补齐 `5eff170`；ps `develop @ 3443e96..34b73a2` (2 commits, 独立落地, DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY)
- **契约影响 (06a)**: `custos/engines/nautilus/toolkit/` 新建 (vendored ps `shared/` + `pandas_ta`); `strategy_registry_name` post-load registry introspection + toolkit import failure gate; `TradingNodeConfig` timeout/reconciliation plumb; ps 侧 supertrend `config.yaml` risk section + RiskController 激活 test
- **红线守护 (06a)**: 4 红线 grep 全 0 命中（见 06a triage 红线守护实证段）；红线 0.3 per-strategy 层为 supertrend 激活；红线 0.4 vendored 树 10 处 float 已 documented as non-fund-flow exemptions (watchdog `test_vendored_toolkit_no_new_float_money_math`)
- **失败模式覆盖 (06a)**: 15 grep-verified contract test names (marker `contract_test_names_grep_verified`)，覆盖 T1.1 spike / T1.2 registry-mode / T2 ps RiskController / T3 provenance + toolkit float audit / T4.1 nautilus_config plumb
- **06a 落地清单 (marker source of truth)**: `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-06a-v1.complete.json`

### Plan 06 完整 close-out 待办 (Plan 08 承接)

- Track 5: T5.1 sandbox e2e (无 arx, 独立 clone 场景处理策略 — FU-AUTH-3) + T5.2 testnet paper→testnet e2e (@integration, 依赖网络/testnet 资金)
- Track 6: T6.1 ps sidecar/runner 退休 docs (docs-only, DP3) + T6.2 Plan 06 完整 close-out（含红线 gate 满足度表填实）
- Plan 07 curation scope 决策会 impact T3.3 allow-list（需 re-baseline）+ `TOOLKIT_PROVENANCE.md` drift monitoring 节奏
- 06b/Plan 08 DEVIATION triage 交叉引用（本 06a triage 段落作为 Plan 06 整 close-out 组成部分）

### Plan 06 整 close-out (2026-07-10, Plan 08 承接)

- **完成日期 (整 Plan 06)**: 2026-07-10
- **总 Task 数**: 12 (Tracks 1-4 由 06a 落地 8 task at `306b9e5`; Tracks 5-6 由 Plan 08 落地 4 task at `4ac60d7`..`<current HEAD>`)
- **总偏离数**: 06a (1 MED + 7 LOW + 2 note) + Plan 08 (5 LOW execution-time entries) — 明细见 06a `.forge/triage/06a-DEVIATION-triage.md` + Plan 08 §Deviations log
- **验证结果**: 全部通过 — 06a `make verify` 263 pass (custos slice HEAD); Plan 08 landing `make verify` 299 pass + 2 skipped + `make verify-nt` 299 pass + 2 skipped (2 skips = testnet manual-verification opt-in + 1 pre-existing skip). T5.2 real testnet session opening is DP1 partial+manual verification (DEV-08-T5.2-MANUAL-VERIFICATION) — wire-level routing assertion covers baseline, real session runs off-band by operator.
- **实施 commit 范围**:
  - 06a: custos `306b9e5` (squash) + orchestration `55782d0` + hook infra `5c01cdb` + pre-spawn `5eff170`; ps `develop @ 3443e96..34b73a2`
  - Plan 08: custos `4ac60d7` (T5.1) + `0d618eb` (T5.2) + `920e94c` (T6.1) + `<T6.2 SHA>` (close-out) on branch `custos/08-plan/runner` based on Plan 07 HEAD `6373f50`
- **契约影响**:
  - 06a: `custos/engines/nautilus/toolkit/` new; `strategy_registry_name` post-load introspection surface; `TradingNodeConfig` timeout/reconciliation plumb; ps `config.yaml` production-tier risk section + activation test
  - Plan 08: `docs/design/nautilus_host.md` new "PS supertrend migration" section (5 subsections); `tests/fixtures/real_supertrend/` permanent fixture mirror pinned to ps `3443e96`; `pyproject.toml` `integration` marker registration
- **红线守护**:
  - Red line 0.1 (Key/KEK not out of process): 06a leak-negative on desensitisation processor + Plan 08 T5.1 real-strategy sandbox anchor (`test_credential_not_in_telemetry_payload_supertrend`) + Plan 08 T5.2 testnet leak-negative gate (opt-in real testnet path per DP1). 4-line grep check passes.
  - Red line 0.2 (G6 gate not bypassed): 06a G6 dir-hash gate covers strategy directory; Plan 08 T5.1 exercises the gate against real supertrend directory. Toolkit sits in supply-chain integrity (provenance + release signing), not per-deploy G6 — deliberate multi-layer split per DEV-06-TOOLKIT-HASH-SCOPE.
  - Red line 0.3 (Disconnect ≠ stop): per-strategy layer landed 06a Track 2 (ps `test_supertrend_risk_controller_blocks_on_drawdown`); Plan 08 T5.1 config-layer proxy asserts production-tier RiskController values (max_daily_loss=0.05 / max_drawdown=0.15 / consecutive_loss_pause=5) survive the vendored-toolkit load path. Per-runner cap layer is Plan 04's deliverable.
  - Red line 0.4 (Money math Decimal): 06a Track 3 vendored-toolkit float watchdog (`test_vendored_toolkit_no_new_float_money_math`) unchanged by Plan 08.
  - Non-custodial 4 red-lines grep: all 4 grep patterns from `.claude/rules/verification.md` §Non-Custodial 红线专项检查 return 0 hits on Plan 08 landing.
- **失败模式覆盖**: 06a 15 grep-verified names + Plan 08 4 new e2e names (`test_real_supertrend_loads_and_deploys_sandbox`, `test_credential_not_in_telemetry_payload_supertrend`, `test_real_supertrend_testnet_routing_wire`, `test_real_supertrend_testnet_deploy`).
- **遗留项**:
  - Per-runner cap layer (red line 0.3 layer 2) — Plan 04 deliverable.
  - Arx web sidecar HTTP → NATS-only migration — independent arx-side follow-up plan (DP2=a ratified).
  - Real testnet session opening — DP1 partial+manual verification per DEV-08-T5.2-MANUAL-VERIFICATION (opt-in via `CUSTOS_T52_TESTNET_ENABLE` env).
  - Chaos coverage on real supertrend — soft "may revisit" per DP3=a; not an owed obligation.
  - Pre-existing plan/lesson tracking-number pollution in `src/custos/cli/main.py:46`, `toolkit/TOOLKIT_PROVENANCE.md:22,63`, `tests/test_deployment_reconciler.py:3`, `tests/test_enrollment.py:126`, `docs/design/nautilus_host.md:101` (G6 gate lesson-#36 reference) — Plan 08 verification scope excluded these (per plan §Verification line 314); candidate for a follow-up hygiene plan.

---

## 下一步 (Next)

Plan 06 close-out 后:
- **custos + ps supertrend 生态可跑真实 paper/testnet e2e** (与 Plan 04 组合后, 红线 0.3 三层齐: per-order NT RiskEngine + per-strategy RiskController + per-runner cap)
- **ps sidecar / runner.py 退休** (docs 声明; crucible 生态如仍需要则独立维护)
- **arx web sidecar HTTP tech debt** (`useApi.ts:208`, scout §7) — 独立议题, 触发 arx 项目起 plan 迁 NATS-only (DP3 CEO 定是否升为本 plan blocker)
- 后续 candidate:
  - **Plan 07**: ps `shared/` 精选迁移 — 依赖本 plan Track 3 方案 A (vendored toolkit) 落定, Plan 07 起草时可锁定 File Inventory (curate 更广 subset + 建立 sync 纪律)
  - **Plan 08**: OKX venue 支持 (README §Not Included Yet; `host.py` hard-coded Binance 需泛化) — 或第三方 NT 策略适配文档 (通用改造 checklist)
  - *(注: 原 skeleton 的 "Plan 09: arx_runner → custos_runner 包名 rename" candidate 已 **superseded** — Plan 05 T1.1 已 rename module 到 `custos` (非 `custos_runner`); mandatory-rules §2 声明分发名 `custos-runner` 与 module 名 `custos` 故意不一致, 无需再 rename)*
