# 05 — 结构化重构: arx_runner → custos rename + core/engines 分层 + ExecutionEngineProtocol 引擎无关契约

> **Status**: 🔲 Todo (skeleton candidate, awaiting Phase 2 `/forge:plan-team` 精细化)
> **Created**: 2026-07-09 (Plan 03 close-out 后, user 澄清诉求 — custos 后期需支持多引擎 hummingbot/freqtrade/athanor/nt-rust, 提前规划目录结构)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: skeleton, 需 Phase 2 精细化后可执行
> **Depends on**: Plan 00a ✅ + Plan 00b ✅ + Plan 00c ✅ + Plan 03 ✅
> **Blocks**: Plan 04 (红线 0.3) + Plan 06 (ps supertrend 迁移) + Plan 07 (ps shared 精选迁移) — **本 plan 是基础重构, 应先落地避免其他 plan 二次搬迁**
> **multi_session_scope**: unknown (预估 large ~500-800 LOC 主要是 rename + 目录移动, 逻辑改动少)

---

## 起源 (Origin)

Plan 03 close-out 后, user 澄清 custos 后期定位 (session log 2026-07-09):

> custos 后期需要支持多种策略引擎 (hummingbot / freqtrade / athanor / nt-rust) 等,
> 现阶段主要支持 NT python 版本, 但是你要提前规划好目录结构和命名方式, 方便后续接入

现状阻塞点:
1. **Python 包名 `arx_runner` 是历史遗留** — 从 arx subtree split 保留, README §Not Included Yet + custos historical-lesson C 系列 (若需增补) 已声明 rename 到 `custos` 是 follow-up (lesson #35 boundary constant rename fanout 场景)
2. **目录结构无引擎分层** — 现有 `src/arx_runner/nautilus_host.py` + `nt_risk_engine.py` + `_nt_binance_venue.py` + `_strategy_loader.py` 是 NT 特化但混在顶层, 未来加 hummingbot / freqtrade / athanor 会造成**顶层污染 + 命名冲突**
3. **G6 gate 契约与 NT 耦合** — `NautilusHostProtocol` 是 G6 gate 的输入面, capability 检查通过 `supports_live` / `supports_venue`; 但契约名字 (`NautilusHost*`) 暗示 NT-only, 未来其他引擎接入时需要重新抽象
4. **NATS subject 未含 engine layer** — 当前 subject 是 `arx.{tenant}.{kind}`, 多引擎并存时无法在 NATS 层区分 engine origin (arx 消费端需要 engine 标签做 routing)
5. **pyproject.toml extras 未预留多引擎槽** — 只有 `nt-runtime` extra, 未来 hummingbot / freqtrade / athanor / nt-rust 每个应有独立 extra

**契机**: 这是最佳时机做结构化重构 — Plan 04 (红线 0.3) 和 Plan 06 (ps supertrend 迁移) 尚未开工, 若在重构后再落地则一次到位; 若重构后再做 04/06, 会遭遇 File Inventory 全部漂移 + 二次搬迁。

---

## 上下文 (Context)

**as-of Plan 03 close-out (main HEAD `db75846`, 2026-07-09)**:

**当前 src/ 结构** (14 file, ~3400 LOC):
```
src/arx_runner/
├── __init__.py __main__.py config.py log.py enrollment.py
├── credential_vault.py           # 引擎无关
├── telemetry_actor.py            # 引擎无关
├── deployment_reconciler.py      # 引擎无关 (但 G6 gate 依赖 NautilusHostProtocol)
├── nats_client.py                # 引擎无关
├── reconcile.py                  # 引擎无关
├── nautilus_host.py              # NT 特化 (NtTradingNodeHost + NoopHost)
├── nt_risk_engine.py             # NT 特化 (pre-trade reject bridge)
├── _nt_binance_venue.py          # NT 特化 (Binance venue config)
└── _strategy_loader.py           # NT 特化 (但概念可通用: path → class + code_hash)
```

**引擎无关 vs 引擎特化 现状归类** (grep `nautilus`/`nt_` 命中):
- ✅ **引擎无关** (6 file, 直接进 core/): `credential_vault.py` / `telemetry_actor.py` / `nats_client.py` / `deployment_reconciler.py` (部分, 含 G6 gate 需抽象) / `reconcile.py` / `enrollment.py`
- ⚠️ **需要重构的 G6 gate** (`deployment_reconciler.py:35-61 _check_g6_gate`): 现在依赖 `NautilusHostProtocol`, 重构为依赖 `ExecutionEngineProtocol`
- 🎯 **NT 特化** (4 file, 进 engines/nautilus/): `nautilus_host.py` / `nt_risk_engine.py` / `_nt_binance_venue.py` / `_strategy_loader.py`

**arx subtree 残迹**: 
- `pyproject.toml` name = `custos-runner` (pip 名已 rename ✅)
- Python module 名 = `arx_runner` (需 rename)
- `mandatory-rules.md` §2 明确记载"Python 导入名 `arx_runner` 保留, pip 分发名 `custos-runner`" — 本 plan 消化此已知不一致

---

## Track 划分 (待 Phase 2 精细化)

### Track 1 — Package rename `arx_runner` → `custos` (lesson #35 fanout)

- **rename 影响面** grep 实证 (Phase 2 补齐):
  - `src/arx_runner/` → `src/custos/`
  - `tests/` 内 `from arx_runner import ...` → `from custos import ...` (预估 100+ 处)
  - `pyproject.toml` `[tool.setuptools.packages.find]` 或 `[tool.hatch.build]` 路径更新
  - `Makefile` 里 `arx_runner` 引用
  - `docs/` 内 code snippet 引用
  - `.claude/rules/` 内 path 引用 (`mandatory-rules.md` §1 表格 `src/arx_runner/` 更新)
  - `.forge/plans/` 内 file inventory 引用 (Plan 00a-03 归档, 保留不改; Plan 04-06 skeleton 本 plan 内同步)
- **lesson #35 boundary constant rename fanout 应用**: 起 rename 前必 grep 全仓 `arx_runner` 消费者清单, 逐一 checklist
- **compat shim 是否要?**: v0.1.0 pre-release, 无对外 pip 依赖者, **不建议加 shim** (增复杂度无收益, 干净 rename)

### Track 2 — 目录重构: core/ + engines/ 分层

**target 结构** (与 CLAUDE.md 定位声明同步更新):

```
src/custos/                             # 从 arx_runner rename
├── __init__.py __main__.py config.py log.py
│
├── core/                               # ← 引擎无关承重墙
│   ├── __init__.py
│   ├── credential_vault.py             # 移
│   ├── enrollment.py                   # 移
│   ├── telemetry_actor.py              # 移
│   ├── nats_client.py                  # 移
│   ├── deployment_reconciler.py        # 移 (G6 gate 抽出到 g6_gate.py)
│   ├── reconcile.py                    # 移
│   ├── g6_gate.py                      # 新 (抽 _check_g6_gate + capability 检查)
│   └── engine_protocol.py              # 新 (ExecutionEngineProtocol Protocol/ABC)
│
├── engines/
│   ├── __init__.py                     # 空 namespace
│   │
│   ├── nautilus/                       # ← NT Python 引擎, 现有代码搬进
│   │   ├── __init__.py
│   │   ├── host.py                     # 从 nautilus_host.py 移入 (NoopHost + NautilusHost, 后者是 NtTradingNodeHost 的引擎无关命名 alias)
│   │   ├── risk.py                     # 从 nt_risk_engine.py 移入
│   │   ├── strategy_loader.py          # 从 _strategy_loader.py 移入 (registry-mode 由 Plan 06 补)
│   │   ├── venue_binance.py            # 从 _nt_binance_venue.py 移入
│   │   └── (Plan 06/07 后补 toolkit/ 子目录承接 ps shared 迁移)
│   │
│   └── (未来 hummingbot/ freqtrade/ athanor/ nt_rust/ 各自 subdir, 本 plan 不建这些占位符; Track 7 只加 README stub)
│
└── cli/
    ├── __init__.py
    └── main.py                          # custos deploy --engine nautilus ...
```

### Track 3 — `ExecutionEngineProtocol` 契约设计 + docs/design/engine_protocol.md

`custos/core/engine_protocol.py` 新增 Protocol 定义（Phase 2 精细化后签名可能微调）:

```python
from decimal import Decimal
from typing import Protocol, runtime_checkable

@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    """所有引擎 Host 必须实现. G6 gate + reconciler 只操作此契约面, 引擎无关."""

    # Capability declaration (G6 gate 消费)
    def supports_live(self) -> bool: ...
    def supports_venue(self, venue: str) -> bool: ...
    def supports_trading_mode(self, mode: str) -> bool: ...   # sandbox/testnet/live

    # Lifecycle
    async def deploy(self, spec: "DeploymentSpec", credential: "Credential") -> None: ...
    async def stop(self, spec_id: str) -> None: ...
    async def dispose(self, spec_id: str) -> None: ...

    # State query (对接 Plan 04 状态快照 + zombie detection)
    async def get_status(self, spec_id: str) -> "EngineStatus": ...
    async def check_engine_connected(self, spec_id: str) -> "ConnectivityState": ...
    async def get_positions(self, spec_id: str) -> list["PositionSnapshot"]: ...
    async def get_orders(self, spec_id: str) -> list["OrderSnapshot"]: ...

    # Risk integration (对接 Plan 04 runner-level cap + breaker)
    async def get_open_notional(self, spec_id: str) -> Decimal: ...
    async def flatten_positions(self, spec_id: str, reason: str) -> None: ...
```

- 权威文档 `docs/design/engine_protocol.md` 新增, 明确契约 + 每方法的语义 + 每引擎实现的 checklist
- `docs/design/nautilus_host.md` 加"实现 ExecutionEngineProtocol"段, 逐方法映射到 NT 具体调用

### Track 4 — G6 gate 重构为 Protocol-based (引擎无关)

- 抽出 `core/deployment_reconciler.py:35-61 _check_g6_gate` 到独立 `core/g6_gate.py`
- 4 层检查从 `NautilusHostProtocol.supports_live/venue` 改为 `ExecutionEngineProtocol.supports_live/venue`
- 重命名 `NautilusHostProtocol` → 用 `ExecutionEngineProtocol` 替换 (`NautilusHost` 保留作 NT 引擎的**具体实现类名**)
- 现有 `test_g6_gate.py` + `test_g6_gate_capability_e2e.py` + `test_g6_gate_capability_integration.py` (Plan 03 加的) 需相应更新 import + fixture
- **契约不变, 只是名字换** — G6 gate 4 层 fail-fast + relaxed-double test 保持

### Track 5 — pyproject.toml extras 结构

```toml
[project]
name = "custos-runner"
version = "0.1.0"                              # rename 后升 minor (breaking API change)
requires-python = ">=3.11"
dependencies = [
    "nats-py>=2.9",
    "pydantic>=2.5",
    "structlog>=24",
    "uuid6>=2024.1.12",
]

[project.optional-dependencies]
nautilus = [
    "nautilus-trader>=1.227; python_version >= '3.12'",
    "pyyaml>=6",
]
# 未来引擎槽预留 (本 plan 不填内容, 只占坑)
hummingbot = []
freqtrade = []
athanor = []
nt-rust = []

dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
]

all-engines = ["custos-runner[nautilus]"]      # 现阶段唯一实装引擎
```

**版本升级说明**: `0.0.0` → `0.1.0` (breaking API rename 后首个可发布版本)

### Track 6 — NATS subject 加 engine layer

- 现状 subject: `arx.{tenant}.{kind}` (如 `arx.acme.event`)
- 目标 subject: `arx.{tenant}.{engine}.{kind}` (如 `arx.acme.nautilus.event`)
- 未来 hummingbot 上线时: `arx.acme.hummingbot.event`
- **wire schema 影响** (lesson #40 精神):
  - envelope `payload_schema_version` 不变 (仅路由变)
  - 但 `subject_scheme_version` 应新增记入 envelope (或 subject 前缀 `arx.v2.{tenant}.{engine}.{kind}` 显式版本化)
  - arx 消费端需要同步更新 subject subscription pattern
- **boundary constant rename fanout** (lesson #26): subject pattern 是 boundary constant, custos + arx 两侧 grep 消费者清单
- 决策项: **是否本 plan 就上 v2 subject**, 还是 Plan 05 只做代码重构 subject 保留 v1, 未来加多引擎时再上 v2 subject (推荐后者, 减 blast radius; 但 Phase 2 精细化定)

### Track 7 — 未来引擎占位符 (docs-only)

**不建**未来引擎的 Python 目录 (避免空 subdir 污染 test discovery + 混淆):

- 建 4 份 stub 文档:
  - `docs/engines/nautilus.md` (现有主内容, 迁改)
  - `docs/engines/hummingbot.md` (stub: "未来引擎, 接入模板见 engine_protocol.md")
  - `docs/engines/freqtrade.md` (stub)
  - `docs/engines/athanor.md` (stub, note "Rust 引擎, 需 IPC/subprocess 桥")
  - `docs/engines/nt_rust.md` (stub, note "Rust 引擎, 需 IPC/subprocess 桥")
- 每 stub 含: 引擎简介 + 与 NT 引擎的 similarity/difference + 接入 5 步模板引用 + follow-up plan candidate 编号

### Track 8 — 迁移测试 + CLI 分派

- 现有全部测试重跑一次 (rename 后)
- 新加 `tests/core/test_engine_protocol_contract.py` — 用 fake ExecutionEngineProtocol impl 验证 Protocol 契约完整性
- 新加 `tests/engines/nautilus/test_nautilus_host_implements_engine_protocol.py` — 断言 `NautilusHost` (from `nautilus_host.py`) 实际实现 `ExecutionEngineProtocol` 全部方法
- `cli/main.py` 加 `--engine <name>` 参数, 现阶段仅接受 `nautilus` (default), 未来引擎接入时新增 case

---

## Historical Lessons 强制引用 (待 Phase 2 补齐)

- **lesson #35 (boundary constant rename fanout)**: package rename `arx_runner → custos` 是教科书场景, Phase 2 evidence-scout 必**全仓 grep 消费者清单**
- **lesson #26 (boundary constant validation)**: NATS subject scheme 变化时的 boundary constant 变更, 双侧 (custos + arx) 消费者对齐
- **lesson #14/#30/#33/#33b (Foundation Scan 四维)**: 影响面维尤其关键 — rename fanout 是天然多轮迭代场景 (import → tests → docs → planning → CLAUDE.md)
- **lesson #22/#28 (multi-layer fail-fast + 独立可测)**: G6 gate 抽 Protocol 后, 每层 relaxed-double test 保持
- **lesson #40 (红线 gate 兑现声明)**: 结构重构本身不改红线兑现能力, 但 close-out 报告要显式声明"重构无退化"
- **custos C2 (输出污染贯穿 review/self-review)**: rename 是**大 diff**, review 阶段极易 hallucinate 未改到的引用; 必须逐个消费者 grep 实证
- **custos C1 (CEO override 记录路径)**: 若 Phase 2 决定推迟 Track 6 (subject v2), 走 CEO override 4 件套记录

---

## 目标 (Goal, 待 Phase 2 精细化)

Plan 05 close-out 后:

- **arx_runner Python 包名彻底退场** — 全仓 `arx_runner` 引用 0 命中 (except archived plan .md files)
- **custos.core / custos.engines.nautilus 分层就位** — 引擎无关承重墙与 NT 特化清晰分离
- **`ExecutionEngineProtocol` 契约文档 + 参考实现** — 未来引擎接入有明确契约
- **G6 gate 引擎无关** — 通过 Protocol capability, 可对未来任何引擎工作
- **pyproject.toml extras 结构** — hummingbot / freqtrade / athanor / nt-rust 各自 slot 预留
- **NATS subject scheme 就绪** — 或 v1 保留 + engine layer 决策记录 (per Phase 2)
- **未来引擎接入 5 步模板** — 有文档指引
- **无功能退化** — Plan 03 + 已有全部 test 全绿

---

## Task List (待 Phase 2 精细化)

skeleton 暂列 high-level:

1. [T1] `arx_runner` → `custos` package rename (含 pyproject / setup / test imports / Makefile / docs / CLAUDE.md)
2. [T2] `src/custos/core/` 目录建立 + 6 引擎无关 file 移入
3. [T3] `src/custos/engines/nautilus/` 目录建立 + 4 NT 特化 file 移入 (改 import 路径)
4. [T4] `custos/core/engine_protocol.py` 新增 `ExecutionEngineProtocol` Protocol
5. [T5] `custos/core/g6_gate.py` 抽出 G6 gate + 改为 Protocol-based (rename `NautilusHostProtocol` → `ExecutionEngineProtocol`)
6. [T6] `pyproject.toml` extras 结构 (nautilus / hummingbot / freqtrade / athanor / nt-rust)
7. [T7] `NatsSubject` 命名 scheme 决策 + 实施 (T6 引擎 layer)
8. [T8] `docs/design/engine_protocol.md` 权威文档新增
9. [T9] `docs/engines/{nautilus,hummingbot,freqtrade,athanor,nt_rust}.md` 5 份接入指南 stub
10. [T10] `cli/main.py` `--engine` 参数分派
11. [T11] 全部 test 重跑 + `test_engine_protocol_contract.py` + `test_nautilus_host_implements_engine_protocol.py` 新增
12. [T12] `CLAUDE.md` 更新 (custos 定位从 "minimal daemon" 升级为 "standard non-custodial NT runner + engine-plugin toolkit")
13. [T13] `.claude/rules/mandatory-rules.md` §1 表格 path 更新 (`src/arx_runner/` → `src/custos/`)
14. [T14] `.forge/README.md` + Plan 04/06 candidate 内 file inventory 同步 (本 plan 内做)

---

## File Inventory (待 Phase 2 grep 实证锚点)

**⚠️ 本 plan 是大规模 rename + 目录移动, File Inventory 极多. skeleton 只列关键类别, Phase 2 精细化补 grep 实证清单**:

| 类别 | 大致数量 | 说明 |
|------|---------|------|
| Python 源码 rename + 移动 | ~14 file | src/arx_runner/*.py → src/custos/core/*.py + src/custos/engines/nautilus/*.py |
| Python test rename import | ~30+ file | tests/ 全部 `from arx_runner import ...` |
| pyproject.toml | 1 | package name + extras |
| Makefile | 1 | `uv run python -m arx_runner` 之类 |
| docs/design/*.md | ~6 file | 各 module design doc 内 code snippet + path 引用 |
| CLAUDE.md | 1 | 顶层导航 + 定位声明 |
| .claude/rules/mandatory-rules.md | 1 | §1 路径表 |
| .forge/plans/2026-07/{04,06}.md | 2 | candidate 内 file inventory 同步 (本 plan 内做) |
| .forge/README.md | 1 | plan index 说明段 |
| **新建文件** | ~10 | engine_protocol.py + g6_gate.py + docs/design/engine_protocol.md + docs/engines/*.md ×5 + test_engine_protocol_contract.py + test_nautilus_host_implements_engine_protocol.py |

**precondition grep** (Phase 2 evidence-scout 跑):
- `grep -rn 'arx_runner' src/ tests/ docs/ .claude/ .forge/ Makefile pyproject.toml CLAUDE.md` → 全部 rename 清单
- `grep -rn 'NautilusHostProtocol' src/ tests/` → 全部要改为 `ExecutionEngineProtocol`
- `grep -rn 'nautilus_host\.py\|nt_risk_engine\.py\|_nt_binance_venue\.py\|_strategy_loader\.py' docs/ .forge/ CLAUDE.md` → docs 路径引用清单

---

## 失败模式覆盖契约表 (lesson #17, 待 Phase 2 具体化)

- rename 遗漏 → 某测试 `from arx_runner.X import Y` 报 `ModuleNotFoundError`, CI/make verify 抓
- G6 gate Protocol 抽象后, `NautilusHost` 若未完整实现 `ExecutionEngineProtocol` → `runtime_checkable` isinstance 检查失败
- pyproject.toml extras 结构错 → `pip install custos-runner[nautilus]` 失败
- NATS subject scheme 变化 → arx 消费端 subscription pattern 不匹配 → 消息 drop (需 cross-repo 协调)
- 顶层 CLAUDE.md 定位漂移未同步 → 未来贡献者/审计员困惑

---

## 红线 gate 满足度表 (lesson #40)

| 红线 | 目标状态 |
|------|---------|
| 0.1 Key/KEK | rename 不改 runtime, 保持 Plan 00a + 03 状态 |
| 0.2 G6 gate | **本 plan 重构 gate 为 Protocol-based, 但 4 层 fail-fast + relaxed-double test 全数保留** — 契约不变, 名字换 |
| 0.3 失联 ≠ 停止 | 本 plan 不 touch, 保持 Plan 00c 状态 (per-runner cap 待 Plan 04) |
| 0.4 Money math | 不 touch |

**重构无退化声明**: close-out 报告需显式声明"Plan 03 全部 test 重跑全绿, G6 gate 4 层 fail-fast 保留, Non-Custodial 4 红线 grep 全 0 命中" — 结构重构不允许把红线兑现能力**降级**。

---

## 偏离与改进日志 (Deviation Log)

(Phase 2 精细化阶段填, Phase 3 执行阶段更新)

**candidate slots**:
- `DEV-05-RENAME-COMPAT-SHIM`: 是否加 `arx_runner` shim 兼容层 (推荐否, pre-release 无对外用户)
- `DEV-05-SUBJECT-V2-DEFER`: NATS subject engine layer 是否本 plan 落地, 或推迟到未来加多引擎时
- `DEV-05-ENGINE-PROTOCOL-DECIMAL-VS-INT`: `get_open_notional` 返回 Decimal 还是 str-serialized Decimal (money math 红线 0.4 边界)
- `DEV-05-VERSION-BUMP`: `0.0.0` → `0.1.0` (推荐, 首个可发布版本)

---

## 完成报告 (Close-out Report)

(Phase 3 执行完成后填)

---

## 下一步 (Next)

Plan 05 close-out 后:

**执行顺序建议**:
```
Plan 05 (本 plan, 结构重构 + rename)  ← 先做, 基础
  ↓
Plan 04 (红线 0.3) — 落到 custos.core.*
  ↓ 与 06 可并行
Plan 06 (ps supertrend 迁移) — 落到 custos.engines.nautilus.*
  ↓
Plan 07 (ps shared 精选迁移) — 落到 custos.engines.nautilus.toolkit.*
  ↓
Plan 08+ (未来引擎接入, 一引擎一 plan)
  - Plan 08: hummingbot 引擎接入 (custos.engines.hummingbot.*)
  - Plan 09: freqtrade 引擎接入
  - Plan 10: athanor MEV 引擎接入 (含 Python↔Rust 桥)
  - Plan 11: nt-rust 引擎接入
```

**未来引擎接入 5 步模板** (from `docs/design/engine_protocol.md`):
1. `mkdir src/custos/engines/<name>/` + `tests/engines/<name>/` + `docs/engines/<name>.md`
2. 在 `<name>/host.py` 实现 `ExecutionEngineProtocol` (`<Name>Host` 类)
3. 在 `pyproject.toml` 加 `<name>` optional-dependency 实际内容
4. 加 venue adapter (如需, `venue_<xxx>.py`)
5. 加 CLI 分派: `custos deploy --engine <name>` 路由到 `<Name>Host`

**CLAUDE.md 定位升级建议** (Track 12 落地):

从:
> custos 是"Key 和策略只在用户本地"红线从设计声明升级为工程可验证的**唯一路径**

改为:
> custos 是"非托管 NT 生态"的标准 runner + engine-plugin toolkit: 提供 non-custodial daemon (承重墙) + standard NT strategy harness (Plan 07 ps shared 精选迁移后) + 可插拔多引擎接入 (nautilus / hummingbot / freqtrade / athanor / nt-rust). 用户在自己的基础设施上运行本 daemon, 无论策略引擎是哪种, 都通过 custos 统一的 non-custodial 承重墙 + G6 gate + credential vault + telemetry actor 复用工程能力.
