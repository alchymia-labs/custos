# 05 — 结构化重构: arx_runner → custos rename + core/engines 分层 + ExecutionEngineProtocol 引擎无关契约

> **Status**: 🔲 Todo (Phase 2 refined 2026-07-09, ready for intra-plan review → execute-team)
> **Created**: 2026-07-09 (Plan 03 close-out 后, user 澄清诉求 — custos 后期需支持多引擎 hummingbot/freqtrade/athanor/nt-rust, 提前规划目录结构)
> **Refined**: 2026-07-09 (plan-drafter, opus-4-7[1m], evidence-scout report 为唯一 grep 源)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Phase 2 refined, use `/forge:execute` or execute-team 实施
> **Depends on**: Plan 00a ✅ + Plan 00b ✅ + Plan 00c ✅ + Plan 03 ✅
> **Blocks**: Plan 04 (红线 0.3) + Plan 06 (ps supertrend 迁移) + Plan 07 (ps shared 精选迁移) — **本 plan 是基础重构, 应先落地避免其他 plan 二次搬迁**
> **multi_session_scope**: **true** (60 文件 rename fanout + 18 新文件 + ~352 import 行 + 8 Track; 逻辑改动少但文件面广 + safety.touched_paths 全命中需谨慎审查 → 建议切片, 见下)

---

## 起源 (Origin)

Plan 03 close-out 后, user 澄清 custos 后期定位 (session log 2026-07-09):

> custos 后期需要支持多种策略引擎 (hummingbot / freqtrade / athanor / nt-rust) 等,
> 现阶段主要支持 NT python 版本, 但是你要提前规划好目录结构和命名方式, 方便后续接入

现状阻塞点 (evidence-scout §Plan 05 实证):
1. **Python 包名 `arx_runner` 是历史遗留** — 从 arx subtree split 保留; `mandatory-rules.md` §2 明记"Python 导入名 `arx_runner` 保留, pip 分发名 `custos-runner`, 未来 rename 单独 plan" — **本 plan 即那个 rename plan** (lesson #35 boundary constant rename fanout 教科书场景)
2. **目录结构无引擎分层** — 现有 NT 特化文件 (`nautilus_host.py` / `nt_risk_engine.py` / `_nt_binance_venue.py` / `_strategy_loader.py`) 混在顶层, 未来加 hummingbot / freqtrade / athanor 会造成顶层污染 + 命名冲突
3. **G6 gate 契约与 NT 耦合** — `NautilusHostProtocol` (deployment_reconciler.py:156) 是 G6 gate 输入面, 但名字暗示 NT-only, 未来其他引擎接入需重新抽象
4. **NATS subject 未含 engine layer** — 当前 `arx.{tenant}.{kind}` (nats_client.py:151), 多引擎并存时无法在 NATS 层区分 engine origin
5. **pyproject.toml extras 未预留多引擎槽** — 只有 `nt-runtime` extra (pyproject.toml:130), 未来每引擎应有独立 extra

**契机**: Plan 04 (红线 0.3) 和 Plan 06 (ps supertrend 迁移) 尚未开工, 若在重构后再落地则一次到位; 若重构后再做 04/06, 会遭遇 File Inventory 全部漂移 + 二次搬迁 (evidence-scout Cross-Plan §已确认 04/06 skeleton 均以 `src/custos/*` 新路径起草)。

---

## 上下文 (Context)

**as-of evidence-scout Foundation Scan (main HEAD `db75846`, 2026-07-09)** — 全部 file:line 锚点来自 `.forge/reviews/2026-07/04-05-06-evidence-scout-report.md`, 本 plan 禁 paraphrase, 直接引用:

### 契约证据锚 (Step 1.5 Contract Verification Gate)

| 被引用契约 | file:line (源码实证) | 用途 |
|-----------|---------------------|------|
| `arx_runner` rename fanout | scout §1: **352 行 / 60 文件** (`grep -rn arx_runner src/ tests/ docs/ .claude/ .forge/ Makefile pyproject.toml CLAUDE.md README.md`) | Track 1 File Inventory 基线 |
| test import fanout | scout §1: **31 test 文件 / 62 import 行** | Track 1 test 改名清单 |
| Makefile arx_runner | scout §1: **0 hits** | Track 1 **不含 Makefile rename** (skeleton 假设已撤) |
| pyproject packages 路径 | scout §1/§5: `pyproject.toml:137` (dump line 39) `packages = ["src/arx_runner"]` = **唯一**需改行 | Track 1 |
| `NautilusHostProtocol` 定义 | scout §3: `deployment_reconciler.py:156`, 方法 `:166` deploy / `:168` reconfigure / `:170` stop / `:172` supports_live / `:174` supports_venue | Track 3/4 |
| Protocol 无 `@runtime_checkable` | scout §3: 当前是 plain structural Protocol, duck-typed via `_host_capability()` (`:64`), 非 isinstance | Track 3 (加 runtime_checkable 是**净新**能力) |
| 6 state/risk 方法状态 | scout §3 + §Plan 04 §5: `get_status`/`check_engine_connected`/`get_positions`/`get_orders`/`get_open_notional`/`flatten_positions` 全 **0 命中 = 100% 净新** | Tier-2 设计决策 (见下) |
| Protocol 实现 | scout §3: `NoopHost` (`nautilus_host.py:85`), `NtTradingNodeHost` (`nautilus_host.py:117`) | Track 3/8 isinstance 断言 |
| Protocol 消费点 | scout §3: `DeploymentReconciler.nautilus_host` 字段 (`deployment_reconciler.py:199`) | Track 4 字段改名 fanout |
| Protocol 文档引用 | scout §3: `docs/design/reconcile.md:33`, `docs/design/nautilus_host.md:14,39,129`, `nautilus_host.py:3,93` docstring | Track 4 docs fanout |
| G6 gate 4 层 | scout §4: `_check_g6_gate` (`:35`), `_host_capability` (`:64`), 层 1 `:77` / 层 2 `:91` / 层 3 `:106` / 层 4 `:142`; call sites `:349`/`:353` | Track 4 抽取 |
| G6 结构化事件名 | scout §4: `g6_gate_code_hash_mismatch` (`:109,119,130`) / `g6_gate_live_capability_denied` (`:80`) / `g6_gate_venue_unsupported` (`:95`) / `g6_gate_credential_scope_violation` (`:146`) | Track 4 保持不变 |
| pyproject 现状 | scout §5: extras 仅 `dev` + `nt-runtime` (`:129-130`), **无** `nautilus`; version `0.0.0` (`:123`) | Track 5 |
| `nt-runtime` 是 boundary constant | scout §5: 建议 Track 5 前先 `grep -rn "nt-runtime"` (README / tech-stack.md / common-errors.md / Makefile 均引用) | Track 5 fanout |
| NATS subject builder | scout §6: `build_subject` (`nats_client.py:141`), `return "arx." + ".".join(parts)` (`:151`); `heartbeat_subject` (`:134`) | Track 6 |
| subject 手写旁路 | scout §6: `reconcile.py:127` `f"arx.{tenant}.recon_result.{runner}.{session}"` **不走 build_subject** | Track 6 tech-debt 锚 |
| CLI 入口 | scout §7: **无** `[project.scripts]`; `python -m arx_runner` (`__main__.py:8`); `_parse_args` prog=`arx-runner` (`:31`); `--use-nt-host` (`:72-77`); `_build_host` (`:124`/`:139`/`:146`); **无** `cli/` package | Track 2/8 |

### 引擎无关 vs 引擎特化 现状归类 (scout §Plan 05 §2)

- **引擎无关 → `custos/core/`** (8 file): `config.py` `credential_vault.py` `deployment_reconciler.py` (减 G6 gate Protocol 耦合) `enrollment.py` `log.py` `nats_client.py` `reconcile.py` `telemetry_actor.py`
- **NT 特化 → `custos/engines/nautilus/`** (4 file): `_nt_binance_venue.py` `_strategy_loader.py` `nautilus_host.py` `nt_risk_engine.py`
- **入口 → `custos/cli/`** (1 file): `__main__.py` (逻辑 ~220 行搬 `cli/main.py`, 顶层留 `__main__.py` 薄 shim)
- **测试目录**: scout §2 确认 `tests/core/` + `tests/engines/nautilus/` 是**净新目录**, 非现有子目录 rename; 现有 32 test 文件当前扁平在 `tests/`

### 与 arx subtree 残迹 (skeleton 已述)

`pyproject.toml` name = `custos-runner` (pip 名已 rename ✅); Python module 名 = `arx_runner` (本 plan rename → `custos`); `mandatory-rules.md` §2 记载的"已知不一致"由本 plan 消化。

---

## 目标 (Goal)

Plan 05 close-out 后: **arx_runner Python 包名彻底退场** (全仓 `arx_runner` 引用 0 命中, 除归档 plan .md) + **custos.core / custos.engines.nautilus 分层就位** + **`ExecutionEngineProtocol` 引擎无关契约 (Tier-1 冻结 + Tier-2 扩展面文档化)** + **G6 gate 引擎无关** + **pyproject extras 多引擎槽** + **未来引擎接入 5 步模板文档** — 且**无功能退化** (Plan 03 全部 test + G6 gate 4 层 relaxed-double 全绿, Non-Custodial 4 红线 grep 全 0)。

---

## 架构 (Architecture)

纯结构重构 + boundary constant rename, **零行为改动**。三步走: (1) `arx_runner`→`custos` 扁平 rename; (2) 引擎无关文件入 `core/`, NT 特化文件入 `engines/nautilus/` (去下划线前缀); (3) `NautilusHostProtocol`→`ExecutionEngineProtocol` 抽到 `core/engine_protocol.py` + G6 gate 抽到 `core/g6_gate.py`, 契约不变只换名 + 加 `@runtime_checkable`。多引擎前瞻通过 pyproject extras 空槽 + `docs/engines/*.md` 5 stub 表达, **不建**未来引擎的空 Python 目录 (避免 test discovery 污染)。

**target 目录结构** (与 skeleton 一致, config.py/log.py 依 scout §2 归 core/):

```
src/custos/
├── __init__.py
├── __main__.py                     # 薄 shim: from custos.cli.main import main
├── core/                           # ← 引擎无关承重墙 (8 file 移入)
│   ├── __init__.py
│   ├── config.py  log.py
│   ├── credential_vault.py  enrollment.py  telemetry_actor.py
│   ├── nats_client.py  reconcile.py  deployment_reconciler.py
│   ├── engine_protocol.py          # 新 (ExecutionEngineProtocol)
│   └── g6_gate.py                  # 新 (抽 _check_g6_gate 4 层)
├── engines/
│   ├── __init__.py                 # 空 namespace
│   └── nautilus/                   # ← NT Python 引擎 (4 file 移入 + 去下划线)
│       ├── __init__.py
│       ├── host.py                 # ← nautilus_host.py
│       ├── risk.py                 # ← nt_risk_engine.py
│       ├── strategy_loader.py      # ← _strategy_loader.py
│       └── venue_binance.py        # ← _nt_binance_venue.py
└── cli/
    ├── __init__.py
    └── main.py                     # ← __main__.py 逻辑 + Track 8 加 --engine
```

---

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| **ExecutionEngineProtocol 是否含 6 state/risk 方法?** | **否 — 分 Tier-1/Tier-2** (见下专节) | scout §3: 6 方法 100% 净新, 加为 required 会破 `@runtime_checkable` backward-compat (两 host 未实现 → isinstance False) + 引入净新 stub = 行为改动, 违 "重构无退化"。Tier-2 由 Plan 04 落地 (它才实现 cap/breaker/snapshot) |
| config.py / log.py 归 core/ 还是顶层? | **core/** | scout §2 分类为引擎无关; "一切引擎无关入 core/" 更一致 (skeleton 图曾示顶层, 本 plan 精细化归 core/) |
| 现有 32 test 是否重排入 tests/core + tests/engines? | **否 — 保持扁平, 仅改 import** | 减 churn + 避 lesson C2 大 diff 幻觉; Plan 05 只建 `tests/core/` + `tests/engines/nautilus/` 两目录并各放 1 个净新 test (给 04/06 target), 现有 test 扁平不动 |
| `DeploymentReconciler.nautilus_host` 字段改名? | **是 → `execution_engine`** (Track 4) | 引擎无关命名一致; 属 internal 非红线 boundary constant, 但 fanout 到全部构造点 (tests + cli), Track 4 grep 收口 |
| CEO 决策点 ×3 | Track 6 defer / 无 compat shim / toolkit → engines/nautilus/ | 见 §偏离与改进日志, 主体按推荐 scope, 3 点全 elevate CEO 终裁 |

### ExecutionEngineProtocol 契约 (Tier-1 冻结 + Tier-2 扩展面)

**Tier-1 (Plan 05 runtime Protocol, required, 两 host 已满足 — 从 `NautilusHostProtocol` deployment_reconciler.py:166-174 逐字 rename)**:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    """所有引擎 Host 必须实现的 Tier-1 契约. G6 gate + reconciler 只操作此面, 引擎无关.
    supports_live / supports_venue 是显式 capability 契约 (sync, gate 不 await 即决策)."""

    async def deploy(self, spec: dict, credential: dict) -> str: ...
    async def reconfigure(self, spec: dict) -> None: ...
    async def stop(self, spec_id: str) -> None: ...
    def supports_live(self) -> bool: ...
    def supports_venue(self, venue: str) -> bool: ...
```

- **superset delta vs 当前 `NautilusHostProtocol`**: 方法集**相等** (5→5, 逐字 rename), 唯一新增能力 = `@runtime_checkable` 装饰器 (scout §3 确认当前无)。两 host (`NoopHost` nautilus_host.py:85 / `NtTradingNodeHost` :117) 已实现全部 5 方法 → `isinstance(host, ExecutionEngineProtocol)` 恒 True, backward-compat 守住。
- **G6 gate 集成**: gate 层 1 调 `supports_live()` (scout §4 `:78`), 层 2 调 `supports_venue(connector)` (`:93`); 契约不变, 只是被调对象类型注解从 `NautilusHostProtocol` → `ExecutionEngineProtocol`。

**Tier-2 (Plan 04 扩展面, 仅 `docs/design/engine_protocol.md` 文档化, **不进** Plan 05 runtime Protocol)**:

| 方法 (推荐签名) | 归属 | 说明 |
|----------------|------|------|
| `async def check_engine_connected(self, spec_id: str) -> ...` | Plan 04 Track 3 | zombie watchdog (scout §Plan 04 §5/§7 确认 0 命中) |
| `async def get_status/get_positions/get_orders(self, spec_id) -> ...` | Plan 04 Track 2 | 状态快照 |
| `async def get_open_notional(self, spec_id) -> Decimal` | Plan 04 Track 1 | runner cap; **Decimal** (红线 0.4), 但绑定决策归 Plan 04 (见 DEV-05-ENGINE-PROTOCOL-DECIMAL) |
| `async def flatten_positions(self, spec_id, reason) -> None` | Plan 04 Track 4 | breaker; scout §Plan 04 §2 提醒 NT SDK 实名是 `close_all_positions`, 引擎实现层映射 |

> Tier-2 由 Plan 04 **同时**加 Protocol required 方法 + 两 host 实现 (成对落地, 保 isinstance 不破)。Plan 05 只文档化, 不写未实现方法。

---

## Blocks 04+06 契约冻结点

execute-team 据此判定 Plan 04/06 最早可 START 的 Plan 05 task:

| 下游 plan | 需要冻结的产物 | 最早可 START 点 |
|-----------|--------------|----------------|
| **Plan 06** | `custos/engines/nautilus/strategy_loader.py` + `host.py` 路径 (scout Cross-Plan: 去下划线) | **T2.2 done** (engines/nautilus/ 路径落定) — 若并行则用 skeleton 路径, T2.2 后锁定 |
| **Plan 04** | `custos/core/deployment_reconciler.py` + `core/telemetry_actor.py` + `engines/nautilus/host.py` 路径 + **ExecutionEngineProtocol Tier-1 冻结** + Tier-2 扩展面命名 (Plan 04 owns) | **T4.2 done** (Protocol 冻结 + g6_gate 抽出 + 字段改名收口) |
| 全绿硬门 | 全部 8 Track close-out (paths + Protocol + pyproject 全定) | **Plan 05 close-out** (保守 gate) |

**推荐**: Plan 04/06 drafter 在 **05a 切片 (Tracks 1-4+8) close** 后将各自 File Inventory 从 skeleton 状态锁定为 Plan 05 实际最终目录名 (scout Cross-Plan §已 hedge)。

---

## 承载决策 (Capability Hosting Decision)

不适用 — 本 plan 是既有源码的结构重构 + rename, 不新增 skill/hook/plan-mode/CLAUDE.md 能力载体; `ExecutionEngineProtocol` 是普通 Python Protocol (代码产物非工具能力)。

---

## 文件清单 (File Inventory)

> 状态标注: **rename**=`git mv` 改路径 / **move**=`git mv` 移目录 / **modify**=改内容 / **create**=净新 / **no-change**=保留不改。`现状(test -f)` 列 = executor Foundation Scan `test -f` 预检期望。

### A. 源码 rename + move (14 file, scout §2)

| 文件 | 状态 | 现状(test -f) | 说明 |
|------|------|--------------|------|
| `src/arx_runner/__init__.py` → `src/custos/__init__.py` | rename | 旧存/新缺 | T1.1 |
| `src/arx_runner/__main__.py` → `src/custos/__main__.py` (shim) + `src/custos/cli/main.py` (逻辑) | rename+split | 旧存/新缺 | T1.1 rename, T2.3 split (scout §7 ~220 行) |
| `src/arx_runner/config.py` → `src/custos/core/config.py` | move | 旧存/新缺 | T2.1 |
| `src/arx_runner/log.py` → `src/custos/core/log.py` | move | 旧存/新缺 | T2.1 |
| `src/arx_runner/credential_vault.py` → `src/custos/core/credential_vault.py` | move | 旧存/新缺 | T2.1 (safety.touched_paths, 红线 0.1) |
| `src/arx_runner/enrollment.py` → `src/custos/core/enrollment.py` | move | 旧存/新缺 | T2.1 (safety.touched_paths) |
| `src/arx_runner/telemetry_actor.py` → `src/custos/core/telemetry_actor.py` | move | 旧存/新缺 | T2.1 (safety.touched_paths, 红线 0.1/0.4) |
| `src/arx_runner/nats_client.py` → `src/custos/core/nats_client.py` | move | 旧存/新缺 | T2.1 (safety.touched_paths, lesson #26) |
| `src/arx_runner/reconcile.py` → `src/custos/core/reconcile.py` | move | 旧存/新缺 | T2.1 (safety.touched_paths, 红线 0.4) |
| `src/arx_runner/deployment_reconciler.py` → `src/custos/core/deployment_reconciler.py` | move+modify | 旧存/新缺 | T2.1 move; T3.1/T4.x 抽 Protocol+gate (safety.touched_paths) |
| `src/arx_runner/nautilus_host.py` → `src/custos/engines/nautilus/host.py` | rename+move | 旧存/新缺 | T2.2 (safety.touched_paths, G6 主载体红线 0.2) |
| `src/arx_runner/nt_risk_engine.py` → `src/custos/engines/nautilus/risk.py` | rename+move | 旧存/新缺 | T2.2 (safety.touched_paths) |
| `src/arx_runner/_strategy_loader.py` → `src/custos/engines/nautilus/strategy_loader.py` | rename+move | 旧存/新缺 | T2.2 (去下划线, scout Cross-Plan) |
| `src/arx_runner/_nt_binance_venue.py` → `src/custos/engines/nautilus/venue_binance.py` | rename+move | 旧存/新缺 | T2.2 (去下划线) |

### B. 净新文件 (18 file)

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/custos/core/__init__.py` | create | T2.1 namespace |
| `src/custos/engines/__init__.py` | create | T2.2 空 namespace |
| `src/custos/engines/nautilus/__init__.py` | create | T2.2 |
| `src/custos/cli/__init__.py` | create | T2.3 |
| `src/custos/core/engine_protocol.py` | create | T3.1 ExecutionEngineProtocol (Tier-1) |
| `src/custos/core/g6_gate.py` | create | T4.1 抽 _check_g6_gate 4 层 |
| `docs/design/engine_protocol.md` | create | T3.2 权威文档 (Tier-1 契约 + Tier-2 扩展面 + 5 步接入模板) |
| `docs/engines/nautilus.md` | create | T7.1 引擎接入 overview stub (指向 docs/design/nautilus_host.md) |
| `docs/engines/hummingbot.md` | create | T7.1 stub |
| `docs/engines/freqtrade.md` | create | T7.1 stub |
| `docs/engines/athanor.md` | create | T7.1 stub (Rust, IPC/subprocess 桥 note) |
| `docs/engines/nt_rust.md` | create | T7.1 stub (Rust, IPC/subprocess 桥 note) |
| `tests/core/__init__.py` | create | T8.1 |
| `tests/core/test_engine_protocol_contract.py` | create | T8.1 (fake impl 验证 Tier-1 契约完整) |
| `tests/engines/__init__.py` | create | T8.2 |
| `tests/engines/nautilus/__init__.py` | create | T8.2 |
| `tests/engines/nautilus/test_nautilus_host_implements_engine_protocol.py` | create | T8.2 (isinstance 断言) |
| `tests/cli/test_cli_engine_dispatch.py` (或扩 `test_main_host_selection.py`) | create | T8.3 (`--engine` 分派) |

### C. 测试 import 改 (scout §1: 31 file / 62 import 行, modify)

全部 `from arx_runner...` → `from custos...` (含 core/engines 子路径)。31 文件逐一 (scout §1 清单): `test_credential_vault.py` `test_credential_lifecycle.py` `test_credential_vault_sops.py` `test_deployment_reconciler.py` `test_enrollment.py` `test_g6_gate.py`(3) `test_g6_gate_capability_e2e.py`(3) `test_g6_gate_capability_integration.py`(2) `test_gc_safety_invariant.py`(4) `test_heartbeat.py` `test_log.py` `test_main_host_selection.py`(2) `test_nats_client_telemetry.py` `test_nats_wal_resilience.py` `test_host_mode_matrix.py`(4) `test_nautilus_host_capability.py` `test_nt_binance_venue.py`(2) `test_nt_telemetry_e2e.py`(3) `test_nt_trading_node_host_integration.py`(3) `test_nats_envelope.py` `test_nt_trading_node_host.py`(3) `test_smoke.py` `test_strategy_loader.py` `test_subject_builder_contract.py`(2) `test_nats_wire_contract.py` `test_telemetry_nt_bridge.py` `test_telemetry_actor.py`(2) `test_nt_risk_engine.py`(2) `test_reconcile.py`(2) `test_telemetry_actor_failure_modes.py`(3) `test_telemetry_money_contract.py`(2)。
> `tests/fixtures/minimal_supertrend_strategy.py`: executor T1.1 grep 核实是否含 `arx_runner` import, 有则一并改。

### D. 配置 / 权威文档 / 规则 fanout (modify)

| 文件 | 状态 | 说明 |
|------|------|------|
| `pyproject.toml` | modify | line 39 `packages=["src/custos"]` (T1.1) + extras 重构 + version 0.0.0→0.1.0 (T5.1) |
| `.forge/teams.yaml` | modify | **safety.touched_paths (行 92-106) 8 个 `src/arx_runner/*.py` → `src/custos/core/*` + `src/custos/engines/nautilus/*`** (T1.2 — skeleton 漏项, lesson #35 fanout 高价值捕获) + executor_team areas root (行 116) |
| `.claude/rules/mandatory-rules.md` | modify | §1 路径表 `src/arx_runner/` → `src/custos/` (T1.2) + §2 module 名不一致注记更新为"rename 已完成" |
| `.claude/rules/verification.md` | modify | 红线专项 grep pattern 路径 (`nautilus_host.py`/`reconcile.py` 等) 更新到新路径 (T1.2) |
| `CLAUDE.md` | modify | §3 六模块表路径 + 定位声明 (T1.2 路径; §Next 定位升级建议见下, 是否本 plan 落由 CEO) |
| `README.md` | modify | Quick Start `python -m custos` + extras `[nautilus]` (T1.2 + T5.2) |
| `docs/design/{03-implementation,credential_vault,enrollment,nats_client,nautilus_host,reconcile,telemetry_actor}.md` | modify | code snippet + path 引用 arx_runner→custos (T1.2, 7 file) |
| `docs/domain.md` | modify | §0.3 六模块表 + §References `arx_runner` 路径 (T1.2) |
| `docs/guides/{04-testing,dev-guide}.md` `docs/ops/05-deployment.md` | modify | 命令/路径引用 (T1.2, 3 file) |
| `Makefile` + `docs/*` `nt-runtime` 引用 | modify | T5.2 `nt-runtime`→`nautilus` extra 名 fanout (scout §5 建议先 `grep -rn "nt-runtime"`) |
| `.forge/README.md` | modify | close-out Status 更新 (T-final) |

### E. 归档不改 (no-change, 说明 60 与本表差额)

scout §1 的 60 文件含**归档 .forge 产物**, 保留历史记录不改 (Track 1 policy): `.forge/dispatch-log/03/*.json` · `.forge/handoff/2026-07/{00a,00b,00c,03}-*.md` · `.forge/marker/{00b,03}-runner.complete.json` · `.forge/plans/2026-07/{00a,00b,00c,01,03}-*.md` (归档 plan) · `.forge/reviews/2026-07/*` (14 报告) · `.forge/triage/03-*.md` · `.claude/rules/historical-lessons.md` (lesson 叙事内的历史 `arx_runner` 引用, 保留) — 这些的 `arx_runner` 是历史事实记录, **故意保留**, 不计入本 plan 的 rename 目标 (goal §"全仓 0 命中 except archived plan .md")。

> **File Inventory 合计**: A 14 (rename/move) + B 18 (create) + C 31 (test modify) + D ~16 (config/docs/rules modify) = **~79 live-touch 文件**, 覆盖 scout 60 中的全部非归档项 + 18 净新; 归档项 (E) 明确 no-change。**≥ scout 60 基线, 无 regression。**

---

## 实现任务 (Tasks)

> **TDD 节奏**: rename/move 类 task 的"红→绿"= 改前 `grep arx_runner` 有命中 / `make verify` 依赖旧路径, 改后 grep 0 命中 + `make verify` 全绿。每 task 独立可 commit, `make verify` 必须在 task 末尾全绿 (原子性)。源码注释禁编号追踪 (lesson #15)。

### Track 1 — Package rename `arx_runner` → `custos` (lesson #35 fanout)

#### Task T1.1: 扁平 rename src + test + pyproject (**big-bang exception**, make verify 绿)
**Files**: `git mv src/arx_runner src/custos` (14 .py 扁平, 暂不入子目录) + `pyproject.toml:39` + 31 test 文件 import + `src/custos/__main__.py` prog 名

**big-bang exception 声明 (codex peer MED-2 fix)**: 本 task 违反 "一 task 一原子小 commit" 惯例 — 单 commit 覆盖 14 src file + 31 test file import + pyproject + `__main__.py`, 46 文件 / ~350 LOC 改动。理由: import fanout 是**原子 rename**性质, 中间态 (rename 一半) 必然 `ModuleNotFoundError`, 无法产生"中间原子 commit 绿"。**explicit gate 而非默认惯例**:
1. **Pre-commit gate**: `git status --short` 打印所有 staged 文件 + 对比 scout §1 counts (31 test / 60 total distinct file with 归档 E 段扣除)
2. **make verify 全绿** 才允许 commit (fmt-check + lint + pytest baseline 全绿; 中间态 partial rename 会撞 ImportError, 抓漏)
3. **grep 0 命中** `arx_runner` 于 src/ + tests/ + pyproject.toml (归档 E 段除外)
4. **commit 后立即 T1.2 起** (不允许在 T1.1 未验证前进 T1.2), 防止 rename fanout 与 non-code fanout 混淆漂移

- **Step 1 (红)**: `grep -rc "arx_runner" src/ tests/ pyproject.toml` → 非 0 (基线 scout §1)
- **Step 2**: `git mv src/arx_runner src/custos`; 全仓 `arx_runner`→`custos` 于 src 内部 import + 31 test import (`from arx_runner` → `from custos`) + `pyproject.toml:39` `packages=["src/custos"]` + `__main__.py:8` docstring + `_parse_args` prog `arx-runner`→`custos` (scout §7)
- **Step 3 (绿)**: 按 big-bang exception gate 4 步逐一 tick (git status + make verify + grep + 立即 T1.2 sequencing)
- **failure-mode**: rename 遗漏 → `ModuleNotFoundError` (make verify 抓); 红线 test (`test_credential_lifecycle` / `test_telemetry_money_contract` / `test_g6_gate*`) 全绿证无退化
- **Step 5**: commit `refactor(custos): rename python package arx_runner → custos (flat, big-bang T1.1)`

#### Task T1.2: 非代码 fanout (docs + rules + teams.yaml + CLAUDE.md)
**Files**: D 段全部非 pyproject 文件 (docs ~11 + .claude/rules 3 + teams.yaml + CLAUDE.md + README 路径部分)
- **Step 1 (红)**: `grep -rc "arx_runner" docs/ .claude/ .forge/teams.yaml CLAUDE.md README.md` → 非 0 (归档 .forge 除外)
- **Step 3 (绿)**: 逐文件改 `arx_runner`→`custos` 路径 (含 `src/arx_runner/nautilus_host.py`→`src/custos/engines/nautilus/host.py` 等新路径); **teams.yaml safety.touched_paths 8 项改新路径** + executor area root; mandatory-rules §2 注记更新为"rename 完成"; `grep` 归档外 0 命中
- **grep 自验 (lesson #13)**: `grep -c "src/custos/engines/nautilus/host.py" .forge/teams.yaml` ≥1
- **Step 5**: commit `docs(custos): fanout arx_runner→custos path refs (docs/rules/teams.yaml/CLAUDE)`

### Track 2 — 目录重构: core/ + engines/nautilus/ + cli/ 分层

#### Task T2.1: 建 core/ + 移 8 引擎无关文件
**Files**: `src/custos/core/__init__.py` (create) + `git mv` config/log/credential_vault/enrollment/telemetry_actor/nats_client/reconcile/deployment_reconciler → `core/`; 全内部 import + 31 test import 更新
- **Step 1 (红)**: `test -d src/custos/core` → 缺
- **Step 3 (绿)**: 移动 + `from custos.X`→`from custos.core.X` 收口; `make verify` 全绿
- **failure-mode**: import 漏改 → ModuleNotFoundError; deployment_reconciler 内 `NautilusHostProtocol` 暂留原处 (T3 抽), move 不改逻辑
- **Step 5**: commit `refactor(custos): move engine-agnostic modules into custos.core`

#### Task T2.2: 建 engines/nautilus/ + 移 4 NT 文件 (去下划线)
**Files**: `engines/__init__.py` + `engines/nautilus/__init__.py` (create) + `git mv` 4 文件带 rename (host/risk/strategy_loader/venue_binance); import + test import 更新
- **Step 1 (红)**: `test -d src/custos/engines/nautilus` → 缺
- **Step 3 (绿)**: 移动+改名; `from custos.nautilus_host`→`from custos.engines.nautilus.host` 等收口 (含 `_strategy_loader`→`strategy_loader` / `_nt_binance_venue`→`venue_binance`); `make verify` 全绿
- **failure-mode**: `test_strategy_loader.py` / `test_nt_binance_venue.py` import 漏改 → fail (抓)
- **Step 5**: commit `refactor(custos): move NT-specific modules into custos.engines.nautilus (drop _ prefix)`
- **⟶ 契约冻结**: engines/nautilus/ 路径落定, **Plan 06 可 START**

#### Task T2.3: 建 cli/ + __main__ 逻辑搬 cli/main.py + 顶层 shim
**Files**: `src/custos/cli/__init__.py` + `src/custos/cli/main.py` (create) + `src/custos/__main__.py` (改薄 shim)
- **Step 1 (红)**: `test -f src/custos/cli/main.py` → 缺
- **Step 3 (绿)**: __main__.py ~220 行逻辑 (`_parse_args`/`_build_vault`/`_build_host`/`_run`/`main`, scout §7) 移 `cli/main.py`; 顶层 `__main__.py` = `from custos.cli.main import main; ...`; `test_main_host_selection.py` import 更新; `python -m custos --help` 可跑; `make verify` 绿
- **failure-mode**: `test_build_host_defaults_to_noop` / `test_build_host_nt_when_flagged` / `test_build_host_nt_without_runtime_fails_fast` 全绿证 host 选择逻辑无退化
- **Step 5**: commit `refactor(custos): extract cli/main.py from __main__, keep thin shim`

### Track 3 — ExecutionEngineProtocol 契约 (引擎无关)

#### Task T3.1: 建 core/engine_protocol.py + rename Protocol + @runtime_checkable
**Files**: `src/custos/core/engine_protocol.py` (create) + `core/deployment_reconciler.py` (modify: 删 `NautilusHostProtocol`, import `ExecutionEngineProtocol`)
- **Step 1 (红)**: `grep -rn "class ExecutionEngineProtocol" src/` → 0; `test_engine_protocol_contract` 未建 → fail
- **Step 3 (绿)**: `engine_protocol.py` 定义 Tier-1 5 方法 (deploy/reconfigure/stop/supports_live/supports_venue 逐字 from deployment_reconciler.py:166-174) + `@runtime_checkable`; deployment_reconciler 删旧 Protocol, import 新; 无 compat shim (pre-release, DEV-05-RENAME-COMPAT-SHIM); `make verify` 绿
- **failure-mode**: 两 host 未实现全 5 方法 → isinstance False (T8.2 守); docstring 保留 supports_* 显式 capability 语义 (scout §3)
- **Step 5**: commit `refactor(custos): rename NautilusHostProtocol → ExecutionEngineProtocol (+runtime_checkable) in custos.core`

#### Task T3.2: docs/design/engine_protocol.md 权威文档
**Files**: `docs/design/engine_protocol.md` (create) + `docs/design/nautilus_host.md` (modify: 加"实现 ExecutionEngineProtocol"段, 逐方法映射)
- **Step 1 (红)**: `test -f docs/design/engine_protocol.md` → 缺
- **Step 3 (绿)**: 文档写 Tier-1 契约 (5 方法语义) + Tier-2 扩展面 (Plan 04 owns) + 未来引擎接入 5 步模板 + authority-docs.md 登记; nautilus_host.md 逐方法映射到 NT 调用; grep 自验 anchor 存在
- **Step 5**: commit `docs(custos): add engine_protocol.md authority doc (Tier-1/Tier-2 + onboarding template)`

### Track 4 — G6 gate 重构为 Protocol-based

#### Task T4.1: 抽 core/g6_gate.py (4 层, 契约不变)
**Files**: `src/custos/core/g6_gate.py` (create) + `core/deployment_reconciler.py` (modify: 抽出 `:35-146` gate 逻辑, import g6_gate) + `test_g6_gate*.py` import 更新
- **Step 1 (红)**: `grep -rn "def _check_g6_gate" src/custos/core/g6_gate.py` → 0
- **Step 3 (绿)**: 移 `_check_g6_gate`/`_host_capability`/`_g6_require_*` 4 层 + 结构化事件名 (`g6_gate_*` 逐字保留 scout §4) 到 `g6_gate.py`; deployment_reconciler call sites (`:349`/`:353`) 改 import; case-insensitive live 检测保留 (lesson #36 dead-gate 防护); `make verify` + 全 G6 test 绿
- **failure-mode (grep-verified 现存, lesson #25)**: 5 relaxed-double 全绿 — `test_layer1_capability_relaxed_double` / `test_layer2_venue_unsupported_relaxed_double` / `test_layer3_code_hash_mismatch_relaxed_double` / `test_layer3_code_hash_missing_relaxed_double` / `test_layer4_credential_scope_violation_relaxed_double` (tests/test_g6_gate_capability_e2e.py); NoopHost 仍拒 live — `test_g6_gate_rejects_live_noophost` / `test_noophost_still_rejects_live`; 非 live 旁路 — `test_non_live_mode_bypasses_all_layers`
- **Step 5**: commit `refactor(custos): extract G6 gate 4-layer into custos.core.g6_gate (contract unchanged)`

#### Task T4.2: 字段改名 nautilus_host → execution_engine + 构造点收口
**Files**: `core/deployment_reconciler.py` (`:199` 字段) + 全部 `DeploymentReconciler(nautilus_host=...)` 构造点 (tests + cli/main.py)
- **Step 1 (红)**: `grep -rn "nautilus_host=" tests/ src/custos/cli` → 非 0 (需全改)
- **Step 3 (绿)**: `nautilus_host: ExecutionEngineProtocol` → `execution_engine: ExecutionEngineProtocol` (`:199`); 全构造点 kwarg 改名; `make verify` 绿
- **failure-mode**: 构造点漏改 → TypeError unexpected kwarg (抓); reconciler 行为不变
- **Step 5**: commit `refactor(custos): rename reconciler field nautilus_host → execution_engine`
- **⟶ 契约冻结**: ExecutionEngineProtocol Tier-1 冻结, **Plan 04 可 START**

### Track 5 — pyproject.toml extras 结构

#### Task T5.1: extras 重构 + version bump + nt-runtime→nautilus (pyproject 侧)
**Files**: `pyproject.toml`
- **Step 1 (红)**: `grep -n "nt-runtime" pyproject.toml` 命中 + 无 `nautilus`/`hummingbot` slot
- **Step 2 (前置 grep, lesson #35)**: `grep -rn "nt-runtime" . --include=*.md --include=Makefile --include=*.toml` 列全 fanout
- **Step 3 (绿)**: extra `nt-runtime`→`nautilus` (含 `nautilus-trader>=1.227; python_version >= '3.12'` + pyyaml) + 空槽 `hummingbot=[]`/`freqtrade=[]`/`athanor=[]`/`nt-rust=[]` + `all-engines=["custos-runner[nautilus]"]` + version `0.0.0`→`0.1.0` (DEV-05-VERSION-BUMP); `uv sync --extra nautilus --extra dev` 成功
- **failure-mode**: extras 结构错 → `uv sync --extra nautilus` 失败
- **Step 5**: commit `build(custos): restructure extras (nautilus + engine slots) + bump 0.0.0→0.1.0`

#### Task T5.2: nt-runtime 字符串 fanout (Makefile + docs)
**Files**: `Makefile` (`make install`/`verify-nt` extra 名) + tech-stack.md / common-errors.md / verification.md / README.md `nt-runtime` 引用
- **Step 1 (红)**: T5.1 §Step 2 fanout 清单非空
- **Step 3 (绿)**: 逐处 `--extra nt-runtime`→`--extra nautilus` + 文档 extra 名; `make install` / `make verify-nt` 目标可跑; grep `nt-runtime` 归档外 0
- **Step 5**: commit `docs(custos): fanout nt-runtime → nautilus extra name (Makefile + docs)`

### Track 6 — NATS subject engine layer 【DECISION POINT 1 — DEFER (docs-only)】

#### Task T6.1: subject v2 scheme 文档化 (不改代码, DEFER)
**Files**: `docs/design/nats_client.md` (modify)
- **决策**: 主体按 CEO 推荐 **DEFER** — Plan 05 **不改** subject scheme (`build_subject` nats_client.py:151 保 v1 `arx.{tenant}.{kind}`), 仅文档化未来 `arx.{tenant}.{engine}.{kind}` v2 方案 + 记 `reconcile.py:127` 手写旁路 (scout §6) 为 v2 落地时必迁的 tech-debt 锚。BOTH options 记 §偏离日志 DEV-05-SUBJECT-V2-DEFER 供 CEO 终裁
- **Step 1 (红)**: `grep -n "engine.*subject.*reserved\|v2 subject" docs/design/nats_client.md` → 0
- **Step 3 (绿)**: nats_client.md 加"多引擎 subject scheme (reserved)"段: v2 方案 + boundary constant fanout (custos+arx 双侧, lesson #26) + reconcile.py:127 旁路锚; **无代码改动** (make verify 不受影响)
- **Step 5**: commit `docs(custos): document reserved v2 engine-layer NATS subject scheme (deferred)`

### Track 7 — 未来引擎 docs stubs

#### Task T7.1: docs/engines/ 5 份接入 stub
**Files**: `docs/engines/{nautilus,hummingbot,freqtrade,athanor,nt_rust}.md` (create ×5)
- **Step 1 (红)**: `test -d docs/engines` → 缺
- **Step 3 (绿)**: 5 stub, 各含: 引擎简介 + 与 NT 的 similarity/difference + 接入 5 步模板引用 (docs/design/engine_protocol.md) + follow-up plan candidate; nautilus.md 是 overview (指向 docs/design/nautilus_host.md 详情, 非搬移); athanor/nt_rust 注 Rust IPC/subprocess 桥
- **Step 5**: commit `docs(custos): add 5 engine onboarding stubs (nautilus + 4 future)`

### Track 8 — 迁移测试 + CLI 分派

#### Task T8.1: tests/core/test_engine_protocol_contract.py (NEW)
**Files**: `tests/core/__init__.py` + `tests/core/test_engine_protocol_contract.py` (create)
- **Step 1 (红)**: `test -f tests/core/test_engine_protocol_contract.py` → 缺 → pytest 无此 test
- **Step 3 (绿)**: fake `ExecutionEngineProtocol` impl (全 5 方法) → `isinstance(fake, ExecutionEngineProtocol)` True; 缺方法 fake → False (relaxed-double 证契约是 live guard); `make verify` 绿
- **Step 5**: commit `test(custos): add ExecutionEngineProtocol Tier-1 contract test`

#### Task T8.2: tests/engines/nautilus/test_nautilus_host_implements_engine_protocol.py (NEW)
**Files**: `tests/engines/__init__.py` + `tests/engines/nautilus/__init__.py` + `tests/engines/nautilus/test_nautilus_host_implements_engine_protocol.py` (create)
- **Step 1 (红)**: `test -f .../test_nautilus_host_implements_engine_protocol.py` → 缺
- **Step 3 (绿)**: 断言 `isinstance(NoopHost(), ExecutionEngineProtocol)` + `isinstance(NtTradingNodeHost(...), ExecutionEngineProtocol)` 均 True (scout §3 两 host 有全 5 方法); `make verify` 绿
- **failure-mode**: Protocol rename 破契约 → isinstance False (本 test 直接抓)
- **Step 5**: commit `test(custos): assert both NT hosts implement ExecutionEngineProtocol`

#### Task T8.3: cli/main.py --engine 分派 + test (NEW)
**Files**: `src/custos/cli/main.py` (modify: 加 `--engine`) + `tests/cli/test_cli_engine_dispatch.py` (create)
- **Step 1 (红)**: `grep -n "\-\-engine" src/custos/cli/main.py` → 0
- **Step 3 (绿)**: `--engine <name>` flag, 现仅接受 `nautilus` (default), 未知值 → 明确 error (非 crash); `--engine nautilus` 路由到 NT host (兼容现 `--use-nt-host` 或替代, scout §7); test `test_cli_engine_defaults_to_nautilus` + `test_cli_engine_unknown_rejected`; `make verify` 绿
- **failure-mode (NEW)**: `--engine hummingbot` (未实装) → 明确 "engine not available" error, 非 crash (lesson #17 failure-mode)
- **Step 5**: commit `feat(custos): add cli --engine dispatch (nautilus only, future-ready)`

### Task T-final: 文档收尾 (close-out) — **强制末尾任务**
**Files**: plan md + `.forge/README.md` + `CLAUDE.md` (定位, 若 CEO 批) + `mandatory-rules.md` §2
**动作**:
1. 本 plan 顶 `Status: ⏳ → ✅ Completed` + `Completed: YYYY-MM-DD`
2. `.forge/README.md` 索引 Plan 05 `⏳ → ✅`
3. 版本: pyproject 已在 T5.1 升 0.1.0 (feat 级 rename), 确认一致
4. **完成报告章节** (含 lesson C40 红线 gate 满足度表, 见下模板) 填实
5. CLAUDE.md 定位升级 (§下一步建议, **是否落地由 CEO** — 见 DEV-05-CLAUDE-POSITIONING)
6. `git add <本 plan> .forge/README.md && git commit -m "docs(custos): mark plan 05 as completed"`

---

## 验证清单 (Verification)

- [ ] `make verify` (fmt-check + lint + pytest baseline): PASS (每 task 末尾 + close-out)
- [ ] `grep -rn "arx_runner" src/ tests/ pyproject.toml Makefile` → **0** (归档 plan .md 除外)
- [ ] `grep -rn "nt-runtime" . --include=*.toml --include=Makefile --include=*.md` → 归档外 **0**
- [ ] G6 gate 4 层 + 5 relaxed-double test 全绿 (无退化, lesson #22/#28)
- [ ] `isinstance(NoopHost/NtTradingNodeHost, ExecutionEngineProtocol)` True (T8.2)
- [ ] Non-Custodial 4 红线 grep 全 0 命中 (verification.md §红线专项, 新路径)
- [ ] `.forge/teams.yaml` safety.touched_paths 已指向 `src/custos/*` 新路径
- [ ] 所有引用契约有 file:line 证据锚 (Step 1.5 gate — §上下文契约证据锚表)
- [ ] 无死代码 / 无编号注释入源码 (lesson #15)
- [ ] 契约表点名 test 全 grep 实存 (lesson #25 — §失败模式表标注)

---

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|------|--------|-----------|-------|
| T1.1 flat rename src+test+pyproject | 🔲 | | 原子, make verify 绿 |
| T1.2 非代码 fanout | 🔲 | | teams.yaml safety paths (skeleton 漏项) |
| T2.1 core/ 移 8 file | 🔲 | | |
| T2.2 engines/nautilus/ 移 4 file | 🔲 | | ⟶ Plan 06 START |
| T2.3 cli/main.py 抽出 | 🔲 | | |
| T3.1 engine_protocol.py rename | 🔲 | | Tier-1 5 方法 + runtime_checkable |
| T3.2 engine_protocol.md 权威文档 | 🔲 | | |
| T4.1 抽 g6_gate.py | 🔲 | | 红线 0.2, 5 relaxed-double 守 |
| T4.2 字段改名 | 🔲 | | ⟶ Plan 04 START (Protocol 冻结) |
| T5.1 pyproject extras + version | 🔲 | | |
| T5.2 nt-runtime fanout | 🔲 | | |
| T6.1 subject v2 docs (DEFER) | 🔲 | | CEO decision 1 |
| T7.1 engine docs 5 stub | 🔲 | | |
| T8.1 test_engine_protocol_contract | 🔲 | | NEW |
| T8.2 test_nautilus_host_implements | 🔲 | | NEW |
| T8.3 cli --engine | 🔲 | | NEW |
| T-final close-out | 🔲 | | |

**切片建议 (multi_session_scope=true)**:
- **05a (Tracks 1-4 + 8)**: rename + restructure + Protocol + g6_gate + 迁移测试 — **红线关键路径, 含契约冻结** (Plan 04/06 unblock 点)。~11 task
- **05b (Tracks 5-7)**: pyproject extras + subject docs + engine stubs — 加性/docs, 无红线风险。~4 task
- execute-team 单 session 跑不完 05 全量时按此切; 05a 优先 (下游依赖)。

---

## 失败模式覆盖契约表 (lesson #17 + #25)

> **status 列**: ✓existing = 本 drafter grep 实证真存在 (lesson #25 反 fabricated); NEW = executor 创建。**existing 测试仅 Track 4/8 需 import 路径更新, 逻辑不改。**

| Track | 失败场景 | 覆盖 test | status |
|-------|---------|-----------|--------|
| T1/T2 | rename/move 遗漏 | `test_smoke` + 全 baseline ModuleNotFoundError | ✓existing |
| T1 | 红线 0.1 credential 泄漏退化 | `test_credential_lifecycle` (脱敏) | ✓existing |
| T1 | 红线 0.4 money math 退化 | `test_telemetry_money_contract` | ✓existing |
| T2.3 | host 选择逻辑退化 | `test_build_host_defaults_to_noop` / `test_build_host_nt_when_flagged` / `test_build_host_nt_without_runtime_fails_fast` | ✓existing |
| T4 | 红线 0.2 NoopHost 上 live | `test_g6_gate_rejects_live_noophost` / `test_noophost_still_rejects_live` / `test_noophost_rejects_live_capability` | ✓existing |
| T4 | 层 1 capability dead-branch | `test_layer1_capability_relaxed_double` | ✓existing |
| T4 | 层 2 venue unsupported dead-branch | `test_layer2_venue_unsupported_relaxed_double` | ✓existing |
| T4 | 层 3 code_hash mismatch/missing | `test_layer3_code_hash_mismatch_relaxed_double` / `test_layer3_code_hash_missing_relaxed_double` | ✓existing |
| T4 | 层 4 credential scope violation | `test_layer4_credential_scope_violation_relaxed_double` | ✓existing |
| T4 | 非 live 旁路 gate | `test_non_live_mode_bypasses_all_layers` | ✓existing |
| T4 | undeclared capability host 结构化拒 | `test_undeclared_capability_host_gets_structured_reject` / `test_undeclared_host_at_reconciler_layer_degrades` | ✓existing |
| T4 | host×mode 6 格矩阵无退化 | `test_mode_host_matrix` (参数化) | ✓existing |
| T4 | NT host capability 声明 | `test_ntlivehost_declares_live` / `test_ntlivehost_venue_binance_supported` | ✓existing |
| T3/T8 | Protocol 契约完整性 | `test_engine_protocol_contract` (fake impl relaxed-double) | NEW |
| T8 | 两 host 未实现 Protocol → isinstance False | `test_nautilus_host_implements_engine_protocol` | NEW |
| T8 | `--engine` 未知值 crash | `test_cli_engine_unknown_rejected` | NEW |
| T8 | `--engine` default 分派 | `test_cli_engine_defaults_to_nautilus` | NEW |
| T5 | extras 结构错 | `uv sync --extra nautilus` 成功 (非 pytest, 验证步) | 验证步 |

> **existing test 全 grep 实证 (2026-07-09)**: `tests/test_g6_gate.py` / `tests/test_g6_gate_capability_e2e.py` / `tests/test_nautilus_host_capability.py` / `tests/test_host_mode_matrix.py` / `tests/test_main_host_selection.py` / `tests/test_g6_gate_capability_integration.py`。NEW test executor close-out 前必 `grep -rn "def test_X" tests/` 实存 (lesson #25 gate)。

---

## 红线 gate 满足度表 (lesson #40 / custos C40)

| 红线 | 目标状态 | code_coverage | runtime_wire | defer_status |
|------|---------|---------------|--------------|--------------|
| 0.1 Key/KEK 不出进程 | rename 不改 runtime, 保 Plan 00a+03 | 现有脱敏 test 全绿 (T1 无退化) | 不变 (move only) | 无 defer |
| 0.2 G6 gate 不绕过 | **重构 gate 为 Protocol-based, 4 层 fail-fast + 5 relaxed-double 全保留** | T4 全 G6 test 绿 (契约不变名换) | gate call sites (`:349`/`:353`) 保持接线 | 无 defer |
| 0.3 失联 ≠ 停止 | 本 plan 不 touch | 保 Plan 00c 状态 | per-runner cap 待 Plan 04 (Tier-2) | Tier-2 defer 到 Plan 04 (文档化) |
| 0.4 Money math Decimal | 不 touch (rename only) | 保 Plan 03 状态 | 不变 | 无 defer |

**重构无退化声明 (close-out 填实)**: "Plan 03 全部 baseline test 重跑全绿; G6 gate 4 层 + 5 relaxed-double 保留; Non-Custodial 4 红线 grep (verification.md §红线专项, 新路径) 全 0 命中" — 结构重构不允许把红线兑现能力降级。**红线名 (vision) ≠ 兑现声明 (reality)**: 本 plan 兑现的是"重构后红线兑现能力不变", 非新增红线兑现 (0.3 per-runner 仍是 Plan 04 的)。

---

## 偏离与改进日志 (Deviations & Improvements)

> **CEO 决策点 ×3 (elevate, 不静默决定)**: DP1/DP2 主体已按 CEO 推荐 scope, BOTH options 列此供终裁; DP3 drafter 依 scout 证据决 + 供 CEO ratify。

### DEV-05-SUBJECT-V2-DEFER 【CEO DECISION POINT 1】
- **等级**: 中 (跨 BC subject scheme, 影响 custos↔arx wire)
- **问题**: NATS subject engine layer (`arx.{tenant}.{engine}.{kind}` v2) 本 plan 上 vs 推迟
- **Option A (推荐, 主体采纳)**: **DEFER** — Plan 05 保 v1 subject (nats_client.py:151), 仅文档化 v2。理由: 减 blast radius (arx 消费端 subscription pattern 需同步 = 跨仓协调); 多引擎实际接入时再上 v2 更聚焦
- **Option B**: 本 plan 即上 v2 — subject 加 `{engine}` 段 + envelope `subject_scheme_version` + reconcile.py:127 手写旁路同迁 + arx 侧对齐。风险: 无第二引擎时 v2 是投机性抽象
- **影响**: nats_client.py (A: 0 改 / B: build_subject + reconcile.py:127) + arx 消费端 (B only)
- **决定**: 主体 A (docs-only T6.1); **CEO 终裁**
- **更新的文档**: docs/design/nats_client.md (reserved 段)

### DEV-05-RENAME-COMPAT-SHIM 【CEO DECISION POINT 2】
- **等级**: 低 (pre-release 无对外用户)
- **问题**: `arx_runner`→`custos` 是否加 compat shim (`arx_runner/__init__.py` re-export custos)
- **Option A (推荐, 主体采纳)**: **不加** — v0.1.0 pre-release, 无对外 pip 依赖者 (scout §1 确认 fanout 全在本仓); 干净 rename 减复杂度
- **Option B**: 加 shim — `arx_runner` 保留 deprecation re-export。理由: 若有未知外部脚本引用。收益低 (无已知外部消费者)
- **决定**: 主体 A (无 shim, T3.1 直接删 NautilusHostProtocol); **CEO 终裁**

### DEV-05-TOOLKIT-LOCATION 【CEO DECISION POINT 3】
- **等级**: 低 (影响 Plan 07 File Inventory, 非红线)
- **问题**: ps `shared/` 精选迁移 (Plan 07) 落 `engines/nautilus/toolkit/` vs 顶层 `core/toolkit/`
- **drafter 决 (scout 证据)**: **`engines/nautilus/toolkit/`** — scout §Plan 06 §4 实证 ps `shared/nautilus/*` (~35 file: coordinators/indicators/config 全 NT 特化) + `shared/nautilus/trading_strategy.py` 是 `NautilusTradingStrategy` 基类, **引擎特化非引擎无关**; `shared/hummingbot/` 独立 (NT path 排除)。故 toolkit 属 NT 引擎子树, 非 core/。与 skeleton line 352 (Plan 07 → `custos.engines.nautilus.toolkit.*`) + Plan 06 skeleton line 105 一致
- **决定**: `engines/nautilus/toolkit/` (Plan 05 不建目录, Plan 07 落地); **CEO ratify**

### DEV-05-VERSION-BUMP
- **等级**: 低; **决定**: `0.0.0`→`0.1.0` (breaking API rename 后首个可发布版本, T5.1)

### DEV-05-ENGINE-PROTOCOL-DECIMAL (Tier-2, 转 Plan 04)
- **等级**: 中 (money math 红线 0.4 边界)
- **问题**: Tier-2 `get_open_notional` 返回 `Decimal` vs str-serialized
- **决定**: 文档化推荐 `-> Decimal` (红线 0.4 内部计算用 Decimal), 但方法本身 Plan 04 落地 → **绑定决策归 Plan 04**; Plan 05 engine_protocol.md 只记推荐签名

### DEV-05-CONFIG-LOG-CORE (drafter 精细化决定)
- **等级**: 低 (内部目录); **决定**: config.py/log.py 归 `core/` (scout §2 分类), 精细化 skeleton 图 (曾示顶层)

### DEV-05-CLAUDE-POSITIONING (待 CEO)
- **等级**: 中 (对外定位声明); **问题**: CLAUDE.md 定位从"唯一路径 minimal daemon"升级为"standard NT runner + engine-plugin toolkit" (skeleton §下一步) 是否本 plan 落
- **决定**: T-final 保留升级建议原文, **是否落地 CEO 定** (定位声明是对外承诺, 需 CEO 拍板)

---

## 完成报告 (Close-out Report)

(Phase 3 执行完成后填, 按 progress-management.md 模板)

- **完成日期**: {YYYY-MM-DD}
- **总 Task 数**: 17 (含 close-out)
- **偏离数**: {N} (DEV-05-* 详见偏离日志)
- **验证结果**: 全部通过 / 部分通过
- **实施 commit 范围**: {first_sha}..{last_sha}
- **契约影响**: docs/design/engine_protocol.md (新) + nautilus_host.md / nats_client.md / domain.md (改) + teams.yaml safety paths
- **红线守护**: Non-Custodial 4 红线全数守住 (grep 记录, 新路径) — 见红线 gate 满足度表
- **失败模式覆盖**: 现有 G6/host test 全绿 (无退化) + 新增 test_engine_protocol_contract / test_nautilus_host_implements_engine_protocol / test_cli_engine_dispatch
- **遗留项**: Tier-2 Protocol 方法 (Plan 04) + v2 subject (defer) + toolkit 迁移 (Plan 07)

---

## 下一步 (Next)

**执行顺序**:
```
Plan 05 (本 plan)  ← 先做, 基础重构
  ↓ (05a Tracks 1-4+8 close 后契约冻结)
Plan 04 (红线 0.3) — 落 custos.core.* + Tier-2 Protocol 方法
  ↓ 与 06 可并行 (06 在 T2.2 后即可 START)
Plan 06 (ps supertrend 迁移) — 落 custos.engines.nautilus.*
  ↓
Plan 07 (ps shared 精选迁移) — 落 custos.engines.nautilus.toolkit.* (DEV-05-TOOLKIT-LOCATION)
  ↓
Plan 08+ (未来引擎接入, 一引擎一 plan: hummingbot / freqtrade / athanor / nt-rust)
```

**未来引擎接入 5 步模板** (from docs/design/engine_protocol.md):
1. `mkdir src/custos/engines/<name>/` + `tests/engines/<name>/` + `docs/engines/<name>.md`
2. `<name>/host.py` 实现 `ExecutionEngineProtocol` (`<Name>Host` 类, Tier-1 + 按需 Tier-2)
3. `pyproject.toml` 填 `<name>` optional-dependency 实际内容 (Plan 05 已留空槽)
4. 加 venue adapter (如需, `venue_<xxx>.py`)
5. CLI 分派 `custos deploy --engine <name>` 路由 (Plan 05 T8.3 已建骨架)

**CLAUDE.md 定位升级建议** (DEV-05-CLAUDE-POSITIONING, 待 CEO): 从"'Key/策略只在本地'红线的唯一路径" → "非托管 NT 生态标准 runner + engine-plugin toolkit (nautilus/hummingbot/freqtrade/athanor/nt-rust 可插拔, 统一复用 non-custodial 承重墙 + G6 gate + credential vault + telemetry actor)"。

---

## 跨 plan 提示 (给 Planning Lead / 04+06 drafter)

- **Plan 06 skeleton line 231** 列"Plan 09: arx_runner → custos_runner 包名 rename"为未来 candidate — 与本 Plan 05 (已做 `arx_runner`→`custos` rename) **冲突/冗余**。本 plan 采 `custos` (非 `custos_runner`), 与 skeleton Track 1 + mandatory-rules §2 一致。请 Planning Lead 通知 Plan 06 drafter: Plan 05 owns rename, Plan 06 line 231 candidate 已被 superseded。
- **Tier-2 Protocol 归属**: Plan 04 需在其 plan 内 owns 6 state/risk 方法 (Protocol required + 两 host 实现成对落地)。Plan 04 File Inventory 已引用 `check_engine_connected`/`flatten_positions`/`get_open_notional` — 与本 plan Tier-2 设计一致, 无需回改。
