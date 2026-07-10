# 04 — 红线 0.3 完整兑现: runner-level cap + 状态快照 + zombie detection + fallback breaker + arx-disconnect chaos

> **Status**: 🔲 Todo (Phase 2 refined 2026-07-09, ready for intra-plan review → execute-team)
> **Created**: 2026-07-09 (Plan 03 close-out 后 dogfood 深度审计 — safety-validator 跨范围审 + Lead 独立复核发现红线 0.3 组合级熔断未兑现)
> **Refined**: 2026-07-09 (plan-drafter-04, opus-4-7[1m], evidence-scout report 为唯一 grep 源)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Phase 2 refined, use `/forge:execute` 或 execute-team 实施
> **Depends on**: Plan 00a ✅ + Plan 00b ✅ + Plan 00c ✅ + Plan 03 ✅ + **Plan 05 T4.2** (START gate — `ExecutionEngineProtocol` Tier-1 冻结 + `core/g6_gate.py` 抽出 + `deployment_reconciler.execution_engine` 字段改名收口; 见 §Depends on / START gate)
> **Blocks**: 上 live 前的 **1 号硬阻断项** (即使 paper/testnet 也必须先做 — 需 chaos test 验证失联期间行为)
> **multi_session_scope**: **true** (14 task / 6 Track / 6 net-new Tier-2 Protocol 方法 × 2 host + 4 净新 dataclass + 3 净新 core 模块 + chaos suite; 预估 ~700-1000 LOC; safety.touched_paths 全命中需谨慎审查 → 建议切片, 见 §进度追踪 切片建议)

---

## 起源 (Origin)

Plan 03 close-out 后, safety-validator 主动跨范围深度审 custos "能否托付真钱", grep 实证发现 (evidence-scout report §Plan 04 已复核确认):

1. **CLAUDE.md / mandatory-rules §0.3 红线 0.3** 明文承诺 "云端断线时本地 fallback breaker + `max_notional_per_runner` cap 继续守护", 但:
   - `grep -rn 'max_notional_per_runner' src/ tests/` → **0 命中** (scout §Plan 04 §1 复核确认, 设计文档 7 处引用但零实现)
   - `grep -rn 'flatten' src/ tests/ docs/` → **0 命中** (scout §Plan 04 §2)
   - `grep -rniE 'zombie|orphan' src/ tests/` → **0 命中** (scout §Plan 04 §7)
   - `drawdown` 唯一 code 命中是 `telemetry_actor.py:67` 一个字段名 `drawdown_pct` (遥测白名单字段, 非熔断计算, scout §Plan 04 §3 复核确认)
   - 现有失联测试全是**网络层降级** (NATS WAL / MessageBus disconnected / stale-spec rejection), 无 **runner 级累计 notional cap + drawdown 熔断 + zombie chaos 测试** (scout §Plan 04 §6)

2. **红线 0.3 分层的当前实现状态**:
   - ✅ per-order (NT `RiskEngine` 单笔限额 max_qty/max_notional/price_collar, `nt_risk_engine.py` — scout §Plan 04 §3 确认这是 per-order 层, **非** fallback breaker)
   - ✅ per-strategy drawdown (ps `shared/risk/RiskController`, config 启用; Plan 06 迁移范围)
   - ❌ per-runner **max_notional_per_runner cap** (custos 无实现)
   - ❌ per-runner **fallback breaker** (arx 断线时自主熔断, 无实现)
   - ❌ per-runner **zombie detection** (engine disconnected 但进程 alive 时无主动降级信号)

3. **教科书级 lesson #40 / C40 场景**: 红线名 (设计意图 = "失联≠停止但不失控") vs runtime 兑现 (能力实现 = 实际有哪层守护) 的鸿沟。CLAUDE.md 段落是"应该守什么", 但代码是"实际守了什么", 二者严重不对齐。**本 plan 是红线 0.3 从设计声明升级为 runtime-wire 兑现的唯一路径**。

---

## 上下文 (Context)

**as-of Plan 03 close-out (main HEAD `cbf5556`) + evidence-scout Foundation Scan (main HEAD `db75846`), 2026-07-09**。全部 file:line 锚点来自 `.forge/reviews/2026-07/04-05-06-evidence-scout-report.md` §Plan 04, 本 plan 禁 paraphrase 现状, 直接引用 (lesson #9/#11/#C2 不信推理信实证)。

> **⚠️ as-of upstream Plan 05 close-out 时间锚 (lesson #33)**: 本 plan File Inventory 使用 Plan 05 结构重构后新路径 (`src/custos/core/*` + `src/custos/engines/nautilus/*`)。scout 现状扫描时 Plan 05 **尚未落地** (代码仍在 `src/arx_runner/*`)。executor 起 Foundation Scan 时**必须**按 Plan 05 实际 close-out 后目录名复核 (scout Cross-Plan §已 hedge: `nautilus_host.py`→`engines/nautilus/host.py` / `_strategy_loader.py`→`strategy_loader.py` 等去下划线)。若 Plan 05 未先落地, 本 plan 阻塞 (见 §Depends on / START gate)。

### 契约证据锚 (Step 1.5 Contract Verification Gate)

| 被引用契约 | file:line (源码实证, scout §Plan 04) | 用途 |
|-----------|--------------------------------------|------|
| `max_notional_per_runner` 零实现 | scout §1: `grep` src/tests **0 命中** (7 处仅设计文档) | Track 1 净新基线 |
| `flatten` 零实现 + NT SDK 实名 | scout §2: custos **0 命中**; NT `Strategy` 实名是 `close_all_positions` / `close_position`, **无** `flatten_positions` | Track 4 (引擎层映射, DEV-04-FLATTEN-NT-MAPPING) |
| `drawdown` code 命中 | scout §3: 仅 `telemetry_actor.py:67` `"drawdown_pct"` (白名单字段名, 非计算) | Track 4 breaker drawdown 计算净新 |
| reconcile loop 失联处理 | scout §4: `deployment_reconciler.py:206-265` `reconcile_loop()` — 断线 log-and-retry, `:243` `deployment_reconciler_recv_failed` warning + `:248` sleep+continue, **零 cap/breaker/drawdown 检查** | Track 3/4 wiring 锚 |
| reconcile hook 点 (本 drafter grep 补锚) | `deployment_reconciler.py:206` `reconcile_loop` / `:267` `handle_spec` / `:364` `_report_status` | Track 3/4 composition wiring |
| 状态快照 API 零实现 | scout §5: `nautilus_host.py` snapshot/positions/orders/open_notional **0 命中**; 两 host 无任何 state-query 方法 | Track 1/2/3 Tier-2 方法净新 |
| `_active_nodes` 枚举源 | scout §7 + drafter grep: `nautilus_host.py:141` `dict[str, tuple]` (`spec_id -> (TradingNode, task)`), 无 liveness 语义; 键可作枚举源 | Track 2/3 (需自加 check_connected + timer) |
| `zombie`/`orphan` 零概念 | scout §7: `grep -rniE 'zombie|orphan'` **0 命中** | Track 3 净新 |
| `PreTradeRuleConfig` Decimal 范式 | scout §3 + drafter grep: `nt_risk_engine.py:56-84` `Decimal(str(raw["max_notional"]))` (`:79-80`), 红线 0.4 established convention | Track 1 `LocalCapConfig` 借鉴范式 |
| `DeploymentSpec` 是 dict 非 class | scout §10: `grep 'class DeploymentSpec'` **0 命中**; 全 signature 类型是 `dict`; `docs/domain.md:103` 字段清单**无** `risk_config` | Track 1/T6.1 (加字段清单 key + `spec.get("risk_config", {})` dict 访问, DEV-04-DEPLOYMENTSPEC-DICT) |
| DeploymentStatus phase 词表 | drafter grep: `docs/domain.md:104` phase `(pending/running/degraded/stopped)` + health `(healthy/warning/error + reason)` | Track 3 zombie 设 `phase=degraded` (合法词表) |
| ps `_collect_*` 借鉴 (跨仓, scout 已实证) | scout §8: `runner.py:216 _collect_metrics` / `:344 _collect_orders` / `:383 _collect_positions` / `:453 _collect_engine_status` (`kernel.data_engine.check_connected()` + `exec_engine.check_connected()`) | Track 2/3 借鉴; **`:101 _peak_equity: float` 是 float → custos 必 Decimal 重推 (DEV-04-PEAK-EQUITY-DECIMAL)** |
| ps sidecar Rule 2 zombie (跨仓, scout 已实证) | scout §8: `sidecar/app.py:298` Rule 2 persistent-degradation; `:321 persistent_degraded_since: dict[str, float]` monotonic timer; `:359-368` `now - since >= unhealthy_after` 升级; **paused 豁免** | Track 3 watchdog 算法借鉴 + pause-exemption |
| 现有 disconnect test 范式 (无 cap/breaker 组合) | scout §6: `test_deployment_reconciler.py:68` / `test_nats_wal_resilience.py:64` / `test_nats_client_telemetry.py:97,105` / `test_telemetry_nt_bridge.py:316` | Track 5 chaos 在此之上组合 |

### 引擎无关 vs 引擎特化 落点 (与 Plan 05 分层一致)

- **引擎无关 → `custos/core/`**: `local_cap.py` (net-new) / `state_snapshot.py` (net-new 框架) / `fallback_breaker.py` (net-new) / `engine_protocol.py` (Plan 05 T3.1 create → 本 plan 扩 Tier-2) / `deployment_reconciler.py` (Plan 05 移入 → 本 plan wire zombie+breaker)
- **NT 特化 → `custos/engines/nautilus/`**: `host.py` (Tier-2 6 方法真实现) / `risk.py` (cap 集成 pre-trade path)

---

## Depends on / START gate

**START gate (Plan 04 T1.1 可 START 的条件)** — 引 Plan 05 §Blocks 04+06 契约冻结点 (Plan 05 line 154-165):

| 冻结产物 | 来自 Plan 05 | 本 plan 依赖点 |
|---------|-------------|--------------|
| `ExecutionEngineProtocol` Tier-1 冻结 (5 方法 + `@runtime_checkable`) | **T3.1 done** | 本 plan 只**扩展** Tier-2, 不改 Tier-1 (UPSTREAM FROZEN) |
| `core/engine_protocol.py` 路径落定 | T3.1 done | Tier-2 方法 + 4 dataclass 追加到此文件 |
| `core/g6_gate.py` 抽出 + `deployment_reconciler.execution_engine` 字段改名收口 | **T4.2 done** | 本 plan wire zombie/breaker 进 `deployment_reconciler.py`, 需字段名稳定 |
| `engines/nautilus/host.py` / `core/deployment_reconciler.py` / `core/telemetry_actor.py` 路径落定 | T2.1/T2.2 done | File Inventory 锚定 |

**结论**: Plan 04 最早 START = **Plan 05 T4.2 done** (保守可等 05a 切片 close)。若 Plan 05/04 并行, 本 plan Task 编号顺序前置对齐 Plan 05 05a 切片; 单独执行时确认 `test -d src/custos/core` + `grep 'class ExecutionEngineProtocol' src/custos/core/engine_protocol.py` 命中 + `grep 'execution_engine' src/custos/core/deployment_reconciler.py` 命中后再起 T1.1。

**UPSTREAM PROTOCOL FROZEN**: Plan 05 T3.1 定的 Tier-1 5 方法 (`deploy`/`reconfigure`/`stop`/`supports_live`/`supports_venue`) 契约不可动。本 plan **只扩展 Tier-2 6 方法**, 不改现有 Tier-1。

---

## 目标 (Goal)

Plan 04 close-out 后:
- **红线 0.3 三层齐 (runtime wire 兑现, 非仅设计声明)**:
  - per-order (NT RiskEngine, existing — 不改)
  - per-strategy drawdown (ps RiskController, Plan 06 迁移范围 — 不改)
  - **per-runner: max_notional_per_runner cap (软限) + fallback breaker (硬限) + zombie detection (自主降级)** — 本 plan 兑现, 且**接线进 composition root** (reconciler 构造 + 失联路径 invoke), 非仅定义未接线
- **状态可见性**: runner 定期 push 状态快照 (positions/orders/engine_status) 到 NATS, 为 arx 前端摆脱 sidecar HTTP 依赖铺路 (arx 侧迁移是 arx 自己 follow-up plan, 本 plan 不 touch arx)
- **Zombie 自主检测**: engine disconnected 且 process alive 超阈值时无需 arx 命令即本地 `phase=degraded` 降级
- **Chaos 覆盖**: arx-disconnect 失联期间 cap/breaker/zombie 继续生效的 fault injection 测试全绿 (lesson #17 — 不允许仅 happy-path)
- **Tier-2 Protocol 落地**: `ExecutionEngineProtocol` 扩 6 net-new state/risk 方法 (required), 两 host (`NoopHost` + `NtTradingNodeHost`) 成对实现, `isinstance` 契约不破 (Plan 05 T8.2 test 仍绿)
- 上 live 前的 **1 号硬阻断项** 消除

---

## 架构 (Architecture)

红线 0.3 的 runtime 兑现 = **多层 fail-fast 结构性守护 (lesson #22/#28), 每层独立可测**:

```
                       ┌─────────────────────────────────────────────┐
   order intent ──────►│ Track 1: LocalCap (软限)                     │
                       │   current_open_notional + new ≤ cap ?        │──拒─► PreTradeRejected wire
                       │   (get_open_notional, Decimal)               │      (runner_cap_exceeded)
                       └─────────────────────────────────────────────┘
                       ┌─────────────────────────────────────────────┐
   reconcile loop ────►│ Track 4: FallbackBreaker (硬限)              │
   (含失联路径)         │   notional > trip  OR  drawdown_pct > trip   │──触发─► flatten_positions
                       │   (Decimal 计算, 云端断线仍评估)             │        + freeze new orders
                       └─────────────────────────────────────────────┘         (fallback_breaker_tripped)
                       ┌─────────────────────────────────────────────┐
   watchdog tick ─────►│ Track 3: ZombieWatchdog (自主降级)          │
                       │   check_engine_connected == False            │──超阈─► phase=degraded
                       │   持续 > grace (per _active_nodes key timer)  │        health.reason=engine_disconnected_zombie
                       └─────────────────────────────────────────────┘         (engine_zombie_detected)
                       ┌─────────────────────────────────────────────┐
   snapshot tick ─────►│ Track 2: StateSnapshot (可观测)             │──publish─► arx.{tenant}.snapshot.state
                       │   positions/orders/engine_status (Decimal)   │           (WAL 缓存 if disconnected)
                       └─────────────────────────────────────────────┘
```

**Tier-2 Protocol 是引擎中立接缝**: 4 层守护全部通过 `ExecutionEngineProtocol` 的 6 net-new 方法与具体引擎解耦 — core/ 层守护逻辑引擎无关, NT 特化只在 `host.py` 的方法实现里 (映射到 NT SDK `close_all_positions` / `portfolio` / `kernel.*_engine.check_connected()`)。

**cap (软限) vs breaker (硬限) 差异**: cap 是**拒绝超额新单** (不动已有仓); breaker 是**触发即平仓 + 冻结** (drawdown/失控兜底)。两者独立层, 各有 relaxed-double 证明是 live guard 非 dead branch (lesson #22/#28)。

---

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| **Tier-2 6 方法加为 `ExecutionEngineProtocol` required 还是 optional/独立 Protocol?** | **required, 加到同一 `ExecutionEngineProtocol`** (成对落地两 host) | Plan 05 §Tier-2 (line 141-150) 已冻结此决策; `@runtime_checkable` isinstance 只校验方法名存在, 两 host 全实现 → `isinstance` 恒 True。**约束**: 每个扩方法的 task 必须**同时**加 Protocol + 两 host 实现 (原子), 保 Plan 05 T8.2 isinstance test 每 commit 边界全绿。多引擎前瞻 friction 见 DEV-04-TIER2-PROTOCOL-REQUIRED |
| `DeploymentSpec.risk_config` 读法 | **`spec.get("risk_config", {}).get(...)` dict 访问** + `docs/domain.md:103` 字段清单加 key | scout §10: DeploymentSpec 是 plain dict, 无 Pydantic class 可加 typed field; `LocalCapConfig` 自己是 frozen dataclass (借 `PreTradeRuleConfig` 范式), 从 dict 解析。DEV-04-DEPLOYMENTSPEC-DICT |
| breaker flatten NT SDK 映射 | **引擎层 `host.py` 映射 `flatten_positions` → NT `Strategy.close_all_positions(instrument_id)`** | scout §2: NT `Strategy` **无** `flatten_positions` 方法; core/ 层 Protocol 用引擎中立名 `flatten_positions`, host.py 实现映射。DEV-04-FLATTEN-NT-MAPPING |
| peak_equity / drawdown 计算精度 | **custos 全 Decimal 重推, 禁 copy-paste ps float** | scout §8: ps `runner.py:101 _peak_equity: float` 是 float; 红线 0.4 禁 money float。DEV-04-PEAK-EQUITY-DECIMAL |
| zombie 降级 phase 值 | **`phase=degraded`** (health.reason=`engine_disconnected_zombie`) | drafter grep: `domain.md:104` phase 合法词表含 `degraded`; 复用现有 `handle_spec` degraded 路径 (reconcile.md §Undeclared capability) |
| snapshot 是否推动 arx 侧迁移 | **本 plan 只 push NATS 快照, arx 消费端迁移 defer 到 arx 自己 plan** | custos 独立仓自足纪律 (mandatory-rules §7); 跨仓协调不在本 plan 范围 |
| dataclass types 落点 | **`core/engine_protocol.py` 同文件** (与 Protocol 内聚) | 4 dataclass (`PositionSnapshot`/`OrderSnapshot`/`ConnectivityState`/`EngineStatus`) 被 Protocol 签名 + core/ 消费者共享; 同文件避免 `types.py` 额外文件 (Plan 05 已 create engine_protocol.py) |
| CEO 决策点 ×3 | cap 默认值 / chaos 手段 / zombie 阈值 | 见 §偏离与改进日志, 3 点全 elevate CEO 终裁 |

### Tier-2 Protocol 契约 (Plan 04 owns, 扩展 Plan 05 Tier-1)

**追加到 `src/custos/core/engine_protocol.py` 的 `ExecutionEngineProtocol` (required, 两 host 成对实现)**:

```python
from dataclasses import dataclass, fields
from decimal import Decimal

# 红线 0.4 runtime invariant (lesson #40 / codex peer MED-1 fix): dataclass 注解不 enforce,
# 需 __post_init__ 显式 check money 字段是 Decimal 非 float. 用 shared helper 保持 DRY.
_MONEY_FIELDS_SHOULD_BE_DECIMAL = {
    "quantity", "avg_px", "unrealized_pnl", "notional",  # PositionSnapshot
    "price",                                             # OrderSnapshot (quantity 复用)
    "open_notional", "peak_equity", "drawdown_pct",      # EngineStatus
}

def _reject_float_money(instance) -> None:
    """Reject float 混入 money 字段. Called from every snapshot dataclass __post_init__."""
    for f in fields(instance):
        if f.name in _MONEY_FIELDS_SHOULD_BE_DECIMAL:
            v = getattr(instance, f.name)
            if not isinstance(v, Decimal):
                raise TypeError(
                    f"{type(instance).__name__}.{f.name} must be Decimal, got {type(v).__name__}"
                )

@dataclass(frozen=True)
class PositionSnapshot:
    instrument_id: str
    quantity: Decimal          # 红线 0.4
    avg_px: Decimal
    unrealized_pnl: Decimal
    notional: Decimal
    def __post_init__(self) -> None: _reject_float_money(self)

@dataclass(frozen=True)
class OrderSnapshot:
    client_order_id: str
    instrument_id: str
    side: str
    quantity: Decimal
    price: Decimal
    status: str
    def __post_init__(self) -> None: _reject_float_money(self)

@dataclass(frozen=True)
class ConnectivityState:
    data_connected: bool
    exec_connected: bool
    checked_at_epoch_s: float   # 非 money, float 允许 (时间戳; _reject_float_money 白名单外)

@dataclass(frozen=True)
class EngineStatus:
    phase: str
    position_count: int
    order_count: int
    open_notional: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    def __post_init__(self) -> None: _reject_float_money(self)

# ExecutionEngineProtocol 追加 6 required 方法 (Tier-1 5 方法不动):
    async def get_open_notional(self, spec_id: str) -> Decimal: ...          # Track 1 (cap)
    async def get_positions(self, spec_id: str) -> list[PositionSnapshot]: ... # Track 2 (snapshot)
    async def get_orders(self, spec_id: str) -> list[OrderSnapshot]: ...       # Track 2 (snapshot)
    async def get_engine_status(self, spec_id: str) -> EngineStatus: ...       # Track 2 (snapshot; == Plan 05 get_status slot)
    async def check_engine_connected(self, spec_id: str) -> ConnectivityState: ... # Track 3 (zombie)
    async def flatten_positions(self, spec_id: str, reason: str) -> None: ...  # Track 4 (breaker)
```

- **NoopHost 实现 (stub, paper/sim)**: `get_open_notional`→`Decimal("0")`; `get_positions`/`get_orders`→`[]`; `get_engine_status`→零值 EngineStatus (`phase="running"`); `check_engine_connected`→`ConnectivityState(True, True, ...)` (stub 恒连通); `flatten_positions`→no-op + structlog `noophost_flatten_noop`。NoopHost 只跑 paper, cap/breaker 对它 no-op 语义正确。
- **NtTradingNodeHost 实现 (真)**: 从 `_active_nodes[spec_id]` 取 `TradingNode`, 读 `kernel.portfolio` / `kernel.cache` positions+orders, `kernel.data_engine.check_connected()` + `kernel.exec_engine.check_connected()` (scout §8 ps 范式), `flatten_positions`→逐 instrument `strategy.close_all_positions(instrument_id)` (DEV-04-FLATTEN-NT-MAPPING)。全 money Decimal 重推 (DEV-04-PEAK-EQUITY-DECIMAL)。

---

## 文件清单 (File Inventory)

> 状态标注: **create**=净新 / **modify**=改内容。`现状(test -f)` 列 = executor Foundation Scan `test -f` 预检期望 (**以 Plan 05 close-out 后新路径为准**, 见 §上下文 as-of 时间锚)。

### A. 源码 (核心守护 + Protocol + host 实现)

| 文件 | 状态 | 现状(test -f) | Track/Task | 说明 |
|------|------|--------------|-----------|------|
| `src/custos/core/engine_protocol.py` | modify | 存 (Plan 05 T3.1 create) | T1.1/T2.1/T3.1/T4.1 | 扩 Tier-2 6 方法 + 4 dataclass (Tier-1 不动) |
| `src/custos/core/local_cap.py` | create | 缺 | T1.2 | `LocalCapConfig` + cap-check (引擎无关, 借 PreTradeRuleConfig 范式) |
| `src/custos/core/state_snapshot.py` | create | 缺 | T2.2 | 周期快照发布框架 (引擎无关, 走 Protocol get_*) |
| `src/custos/core/fallback_breaker.py` | create | 缺 | T4.2 | breaker trip 逻辑 (notional+drawdown, Decimal) + freeze state |
| `src/custos/core/deployment_reconciler.py` | modify | 存 (Plan 05 移入) | T3.2/T4.3 | wire zombie watchdog (`:206` reconcile_loop) + breaker 失联路径 invoke (composition root) |
| `src/custos/engines/nautilus/host.py` | modify | 存 (Plan 05 T2.2 rename) | T1.1/T2.1/T3.1/T4.1 | Tier-2 6 方法 NT 真实现 (safety.touched_paths, 红线 0.2 主载体) |
| `src/custos/engines/nautilus/risk.py` | modify | 存 (Plan 05 rename `nt_risk_engine.py`) | T1.3 | cap 集成 pre-trade path → PreTradeRejected wire |
| `src/custos/cli/main.py` | modify | 存 (Plan 05 T2.3 create) | T4.3 | composition root — 构造 local_cap/breaker/watchdog 注入 reconciler (runtime wire, lesson #40) |

### B. 测试 (全 NEW)

| 文件 | 状态 | Track/Task | 说明 |
|------|------|-----------|------|
| `tests/core/test_local_cap.py` | create | T1.2/T1.3 | cap 阈值 + Decimal 解析 + 失联期间拒单 |
| `tests/core/test_state_snapshot.py` | create | T2.2 | 快照 Decimal money + 周期 + 断线缓存 |
| `tests/core/test_zombie_detection.py` | create | T3.1/T3.2 | check_engine_connected + grace 计时 + pause 豁免 |
| `tests/core/test_fallback_breaker.py` | create | T4.1/T4.2/T4.3 | notional/drawdown trip + freeze + 失联触发 + Decimal |
| `tests/core/test_arx_disconnect_chaos.py` | create | T5.1/T5.2 | 失联注入 + 多守护继续 + long-run |
| `tests/core/test_engine_protocol_tier2.py` | create | T1.1/T2.1/T3.1/T4.1 | Tier-2 契约完整 + 两 host isinstance 不破 + fake relaxed-double |
| `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py` | create | T1.1/T2.1/T3.1/T4.1 | NT host Tier-2 方法真实现 (flatten→close_all_positions 映射) |

> `tests/core/` + `tests/engines/nautilus/` 目录由 Plan 05 T8.1/T8.2 建 (`__init__.py` 已在)。若 Plan 05 未落地, executor T1.1 先建目录 + `__init__.py`。

### C. 文档 (modify, T6.1)

| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/design/reconcile.md` | modify | §失联降级新增 — 红线 0.3 三层 (cap/breaker/zombie) runtime 兑现描述 |
| `docs/domain.md` | modify | `DeploymentSpec` 字段清单 (`:103`) 加 `risk_config`(optional JSON) + 新 domain 概念 `RunnerRiskConfig`(`max_notional_per_runner` / `fallback_breaker`{`max_drawdown_pct`,`max_notional`}, wire `str(Decimal)`) + `EngineStatus` 快照概念 |
| `docs/design/engine_protocol.md` | modify | Tier-2 6 方法 finalize (Plan 05 文档化推荐签名 → Plan 04 实装的落地签名对齐) + 4 dataclass |
| `docs/design/nautilus_host.md` | modify | §组合熔断兜底 (`:49-50`, 已引 `max_notional_per_runner`) 补 runtime 兑现锚 + Tier-2 方法 NT 映射 |
| `.forge/README.md` | modify | close-out Status 更新 (T-final) |

> **File Inventory 合计**: A 8 (5 create + 3 modify... 实为 3 create + 5 modify) + B 7 create + C 5 modify = **20 live-touch 文件**。红线 0.4 money 路径文件 (`local_cap.py`/`state_snapshot.py`/`fallback_breaker.py`/`host.py` Tier-2 impl) 全 Decimal。

---

## 实现任务 (Tasks)

> **TDD 节奏 (executing/SKILL.md)**: 每 task 先写失败测试 → 实现 → `make verify` 全绿 → commit。**Protocol 扩展 task 铁律**: 加 Protocol required 方法**必同时**加两 host 实现 (原子), 否则 Plan 05 T8.2 isinstance test 立即红。源码注释禁编号追踪 (`Plan NN`/`Task NN`/`lesson #M`/`unimplemented!("Plan …")` — lesson #15), 接力用语义指代 (如 "runner cap plan 真实现")。silent 控制流必接 structlog 或 `# noqa: SILENT-OK <reason>` (lesson #21)。NATS subject 走 `build_subject()` 不裸 f-string (lesson #26, scout §6 已标 `reconcile.py:127` 旁路)。

### Track 1 — Runner-level notional cap (软限, 结构性)

#### Task T1.1: Tier-2 `get_open_notional` + 两 host 实现 (Protocol foundation for cap)
**Files**: `core/engine_protocol.py` (加 `get_open_notional` + 若首个则加 dataclass import) + `engines/nautilus/host.py` (NoopHost stub + NtTradingNodeHost 真) + `tests/core/test_engine_protocol_tier2.py` + `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py`
- **红**: `grep -n "async def get_open_notional" src/custos/core/engine_protocol.py` → 0; isinstance test 尚未含此方法
- **绿**: Protocol 加 `async def get_open_notional(self, spec_id: str) -> Decimal`; NoopHost→`Decimal("0")`; NtTradingNodeHost→从 `_active_nodes[spec_id]` node.kernel.portfolio 累加 open position notional (Decimal 重推); `isinstance(both, ExecutionEngineProtocol)` 仍 True; `make verify` 绿
- **failure-mode (NEW)**: `test_get_open_notional_returns_decimal` / `test_get_open_notional_noophost_zero` / `test_both_hosts_still_isinstance_after_tier2` (relaxed-double: 缺 get_open_notional 的 fake → isinstance False)
- commit `feat(custos): add ExecutionEngineProtocol.get_open_notional Tier-2 method (+both hosts)`

#### Task T1.2: `LocalCapConfig` + `core/local_cap.py` cap-check
**Files**: `core/local_cap.py` (create) + `tests/core/test_local_cap.py`
- **红**: `test -f src/custos/core/local_cap.py` → 缺
- **绿**: `LocalCapConfig` frozen dataclass (`max_notional_per_runner: Decimal`, 借 `PreTradeRuleConfig.from_dict` 范式 `Decimal(str(raw[...]))`); `from_spec(spec: dict)` → `spec.get("risk_config", {}).get("max_notional_per_runner")`, 缺则用结构性 floor default (DP1); `check_cap(current_open: Decimal, new_order_notional: Decimal, cfg) -> bool`; `make verify` 绿
- **failure-mode (NEW)**: `test_local_cap_rejects_over_threshold` / `test_local_cap_allows_under_threshold` / `test_local_cap_config_parses_decimal_not_float` (红线 0.4) / `test_local_cap_falls_back_to_floor_when_spec_missing` (失联无 spec 场景)
- commit `feat(custos): add LocalCapConfig + runner notional cap check`

#### Task T1.3: cap 集成 pre-trade path + PreTradeRejected wire
**Files**: `engines/nautilus/risk.py` (modify) + `tests/core/test_local_cap.py` (追加集成 case)
- **红**: `grep -n "runner_cap_exceeded\|LocalCap" src/custos/engines/nautilus/risk.py` → 0
- **绿**: pre-trade path 调 `get_open_notional` + `check_cap`, 超额 → 走现有 `PreTradeRejected` wire (复用 `nt_risk_engine` bridge) + structlog `runner_cap_exceeded` (红线 0.4 敞口 Decimal); `make verify` 绿
- **failure-mode (NEW)**: `test_cap_exceeded_emits_pre_trade_rejected` / `test_cap_exceeded_during_disconnect_still_rejects` (失联期间 cap 仍拦, 红线 0.3 核心) / `test_cap_is_live_guard_relaxed_double` (breaker 禁用时 cap 仍 fire, lesson #22/#28 独立可测)
- commit `feat(custos): integrate runner cap into pre-trade path (PreTradeRejected wire)`

### Track 2 — 状态快照 (可观测, 借鉴 ps `_collect_*`)

#### Task T2.1: Tier-2 `get_positions`/`get_orders`/`get_engine_status` + 3 dataclass + 两 host
**Files**: `core/engine_protocol.py` (加 3 方法 + `PositionSnapshot`/`OrderSnapshot`/`EngineStatus`) + `engines/nautilus/host.py` + `tests/core/test_engine_protocol_tier2.py` + `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py`
- **红**: `grep -n "class PositionSnapshot\|async def get_positions" src/custos/core/engine_protocol.py` → 0
- **绿**: 3 dataclass (money 全 Decimal) + 3 Protocol 方法; NoopHost→`[]`/零值 EngineStatus; NtTradingNodeHost→读 kernel.cache positions/orders + peak_equity/drawdown_pct Decimal 重推 (DEV-04-PEAK-EQUITY-DECIMAL, 跨线程安全 caveat scout §8 复核); isinstance 仍 True; `make verify` 绿
- **failure-mode (NEW)**: `test_get_positions_returns_decimal_money` / `test_engine_status_drawdown_is_decimal` / `test_snapshot_dataclasses_reject_float_money`
- commit `feat(custos): add snapshot Tier-2 methods (positions/orders/engine_status +both hosts)`

#### Task T2.2: `core/state_snapshot.py` 周期发布 → NATS
**Files**: `core/state_snapshot.py` (create) + `tests/core/test_state_snapshot.py`
- **红**: `test -f src/custos/core/state_snapshot.py` → 缺
- **绿**: 周期 (default 10s, configurable) 调 Protocol get_* → 组装 payload (money `str(Decimal)`) → `build_subject(tenant, "snapshot", "state")` publish (lesson #26); 断线走 WAL 缓存 (复用现有 nats_client fire-and-forget/WAL); `make verify` 绿
- **failure-mode (NEW)**: `test_state_snapshot_publishes_str_decimal_money` (红线 0.4 wire) / `test_state_snapshot_periodic_interval_respected` / `test_snapshot_cached_when_disconnected` (失联缓存, 复用 scout §6 WAL 范式)
- commit `feat(custos): add periodic state snapshot publisher (NATS uplink)`

### Track 3 — Zombie detection (自主降级, 对标 sidecar Rule 2)

#### Task T3.1: Tier-2 `check_engine_connected` + `ConnectivityState` + 两 host
**Files**: `core/engine_protocol.py` (加方法 + `ConnectivityState`) + `engines/nautilus/host.py` + `tests/core/test_zombie_detection.py` + `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py`
- **红**: `grep -n "async def check_engine_connected" src/custos/core/engine_protocol.py` → 0
- **绿**: `ConnectivityState` dataclass + Protocol 方法; NoopHost→`ConnectivityState(True, True, ...)`; NtTradingNodeHost→`kernel.data_engine.check_connected()` + `exec_engine.check_connected()` (scout §8); isinstance 仍 True; `make verify` 绿
- **failure-mode (NEW)**: `test_check_engine_connected_reports_disconnected` / `test_check_engine_connected_noophost_connected`
- commit `feat(custos): add ExecutionEngineProtocol.check_engine_connected (+both hosts)`

#### Task T3.2: zombie watchdog wire 进 reconcile loop + degraded 信号
**Files**: `core/deployment_reconciler.py` (modify, `:206` reconcile_loop 加 watchdog tick) + `tests/core/test_zombie_detection.py`
- **红**: `grep -n "engine_zombie_detected\|persistent_degraded" src/custos/core/deployment_reconciler.py` → 0
- **绿**: watchdog per `_active_nodes` key 维护 `persistent_degraded_since: dict[str, float]` monotonic timer (借 sidecar `app.py:359-368` 范式); `check_engine_connected()==False` 持续 > grace (DP3) → `_report_status(phase="degraded", health.reason="engine_disconnected_zombie")` + structlog `engine_zombie_detected`; **paused 豁免** (维护窗口不误升级, scout §8); **本地自主** (不等 arx 命令); `make verify` 绿
- **failure-mode (NEW)**: `test_zombie_detected_after_grace_period` / `test_zombie_not_flagged_during_transient_blip` (< grace 不误报) / `test_zombie_exempt_when_paused` / `test_zombie_detection_works_when_arx_disconnected` (自主性, 红线 0.3)
- commit `feat(custos): add engine zombie watchdog to reconcile loop (autonomous degraded)`

### Track 4 — Fallback breaker (硬限, arx 断线自主熔断 — 红线 0.3 核心)

#### Task T4.1: Tier-2 `flatten_positions` + 两 host (NT→close_all_positions 映射)
**Files**: `core/engine_protocol.py` (加方法) + `engines/nautilus/host.py` + `tests/core/test_fallback_breaker.py` + `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py`
- **红**: `grep -n "async def flatten_positions" src/custos/core/engine_protocol.py` → 0
- **绿**: Protocol `async def flatten_positions(self, spec_id, reason) -> None`; NoopHost→no-op + structlog `noophost_flatten_noop`; NtTradingNodeHost→逐 instrument `strategy.close_all_positions(instrument_id)` (DEV-04-FLATTEN-NT-MAPPING, **非** 同名直调) + structlog `positions_flattened`; isinstance 仍 True; `make verify` 绿
- **failure-mode (NEW)**: `test_flatten_positions_maps_to_close_all` (NT 映射断言) / `test_flatten_positions_noophost_noop`
- commit `feat(custos): add ExecutionEngineProtocol.flatten_positions (NT→close_all_positions)`

#### Task T4.2: `core/fallback_breaker.py` trip 逻辑 (notional+drawdown, Decimal)
**Files**: `core/fallback_breaker.py` (create) + `tests/core/test_fallback_breaker.py`
- **红**: `test -f src/custos/core/fallback_breaker.py` → 缺
- **绿**: `FallbackBreakerConfig` (`max_notional: Decimal`, `max_drawdown_pct: Decimal`, 从 `spec.get("risk_config", {}).get("fallback_breaker", {})`); `evaluate(open_notional, peak_equity, current_equity) -> BreakerVerdict` (drawdown_pct Decimal 重推, DEV-04-PEAK-EQUITY-DECIMAL); trip → freeze state (拒新单 flag); `make verify` 绿
- **failure-mode (NEW)**: `test_breaker_trips_on_notional_breach` / `test_breaker_trips_on_drawdown_breach` / `test_breaker_drawdown_uses_decimal_not_float` (红线 0.4) / `test_breaker_freezes_new_orders_after_trip` / `test_breaker_is_live_guard_relaxed_double` (cap 缺时 breaker 仍 fire, lesson #22/#28)
- commit `feat(custos): add fallback breaker trip logic (notional+drawdown, Decimal)`

#### Task T4.3: breaker/cap/watchdog wire 进 composition root (runtime wire, lesson #40)
**Files**: `core/deployment_reconciler.py` (失联路径 invoke breaker) + `src/custos/cli/main.py` (构造 3 守护注入 reconciler) + `tests/core/test_fallback_breaker.py`
- **红**: `grep -n "fallback_breaker\|FallbackBreaker" src/custos/cli/main.py src/custos/core/deployment_reconciler.py` → 0 (仅定义未接线 = lesson #40 陷阱)
- **绿**: `DeploymentReconciler` 加字段 (`local_cap` / `fallback_breaker` / `zombie_watchdog`); `cli/main.py` 构造并注入 (composition root); reconcile loop 失联路径 (`:206-265`, arx unreachable) 评估 breaker → trip 则 `flatten_positions` + freeze; `make verify` 绿
- **failure-mode (NEW)**: `test_breaker_trips_during_arx_disconnect` (失联期间自主熔断, 红线 0.3 核心) / `test_reconciler_constructs_all_three_guards` (composition root 实接线, 非仅定义)
- commit `feat(custos): wire cap/breaker/watchdog into reconciler composition root`
- **⟶ 红线 0.3 runtime wire 兑现点** (close-out 红线 gate 表 runtime_wire 列填实依据)

### Track 5 — Chaos test (arx-disconnect fault injection, lesson #17)

#### Task T5.1: `test_arx_disconnect_chaos.py` — 多守护失联组合
**Files**: `tests/core/test_arx_disconnect_chaos.py` (create)
- **红**: `test -f tests/core/test_arx_disconnect_chaos.py` → 缺
- **绿**: 注入 NATS 断线 (mock, DP2; 复用 scout §6 `test_deployment_reconciler.py:68` 范式) → 断言 reconciler 不 crash + cap 仍拒超额 + breaker 仍评估 + zombie watchdog 仍跑 + snapshot WAL 缓存; `make verify` 绿
- **failure-mode (NEW)**: `test_arx_disconnect_reconciler_no_crash` / `test_arx_disconnect_cap_breaker_zombie_continue` (红线 0.3 失联≠停止且不失控) / `test_arx_disconnect_snapshot_wal_cached`
- commit `test(custos): add arx-disconnect chaos suite (multi-guard continuity)`

#### Task T5.2: long-run 失联 chaos (云端断线 N 小时守护持续)
**Files**: `tests/core/test_arx_disconnect_chaos.py` (追加 long-run case)
- **红**: `grep -n "long_run\|guards_persist" tests/core/test_arx_disconnect_chaos.py` → 0
- **绿**: 模拟云端断线延续 (加速时钟/多轮 loop) → 本地 cap/breaker/zombie 仍强制 (lesson #17 非 happy-path); `make verify` 绿
- **failure-mode (NEW)**: `test_arx_disconnect_long_run_guards_persist`
- commit `test(custos): add long-run arx-disconnect chaos (guards persist)`

### Track 6 — 文档同步 + close-out

#### Task T6.1: docs 同步 (reconcile / domain / engine_protocol / nautilus_host)
**Files**: `docs/design/reconcile.md` + `docs/domain.md` + `docs/design/engine_protocol.md` + `docs/design/nautilus_host.md`
- **红**: `grep -n "risk_config\|RunnerRiskConfig\|fallback_breaker" docs/domain.md` → 0 (scout §10 确认)
- **绿**: reconcile.md §失联降级补三层 runtime 兑现; domain.md `:103` DeploymentSpec 加 `risk_config` + `RunnerRiskConfig` 概念 (wire `str(Decimal)`); engine_protocol.md Tier-2 6 方法 + 4 dataclass finalize; nautilus_host.md §组合熔断兜底补 runtime 锚; grep 自验 anchor 存在 (lesson #13); `make verify` (docs 不影响但跑一次)
- commit `docs(custos): sync red-line-0.3 runtime fulfillment (reconcile/domain/engine_protocol/nautilus_host)`

#### Task T-final: close-out — **强制末尾任务**
**Files**: 本 plan md + `.forge/README.md`
- **动作**:
  1. 本 plan 顶 `Status: ⏳ → ✅ Completed` + `Completed: YYYY-MM-DD`
  2. `.forge/README.md` 索引 Plan 04 `⏳ → ✅`
  3. **完成报告章节** (含 §红线 gate 满足度表, lesson #40/C40 三层区分 code_coverage / runtime_wire / defer_status) 填实
  4. **契约表 test 名全 grep 实存** (lesson #25): `grep -rn "def <test_name>" tests/` 逐一验证 NEW test 真存在, 命中数 = 契约表条目数
  5. `git add <本 plan> .forge/README.md && git status --short` 核对 staged 范围 (lesson #27) → commit `docs(custos): mark plan 04 as completed`

---

## 验证清单 (Verification)

- [ ] `make verify` (fmt-check + lint + pytest baseline): PASS (每 task 末尾 + close-out)
- [ ] `grep -rn "max_notional_per_runner" src/custos/` → **≥1 命中** (红线 0.3 从 0 实现升级为有实现)
- [ ] `isinstance(NoopHost/NtTradingNodeHost, ExecutionEngineProtocol)` True (Tier-2 加后仍不破, Plan 05 T8.2 test 绿)
- [ ] `grep -rn "fallback_breaker\|local_cap\|zombie_watchdog" src/custos/cli/main.py` → **≥1** (composition root 实接线, lesson #40 非仅定义)
- [ ] chaos test 全绿: `test_arx_disconnect_cap_breaker_zombie_continue` + `test_breaker_trips_during_arx_disconnect` (失联≠停止且不失控)
- [ ] Non-Custodial 4 红线 grep 全 0 违反 (verification.md §红线专项): 无 `float(` money 路径 (`local_cap`/`breaker`/`snapshot`/`host` Tier-2), 无 raw key material log/publish
- [ ] money math: `LocalCapConfig`/`FallbackBreakerConfig`/`EngineStatus` money 字段全 Decimal; wire `str(Decimal)`; `test_*_uses_decimal_not_float` 全绿 (红线 0.4)
- [ ] 每层守护独立可测: cap relaxed-double + breaker relaxed-double 各证 live guard (lesson #22/#28)
- [ ] 契约表点名 test 全 grep 实存 (lesson #25 — §失败模式表标注)
- [ ] 无死代码 / 无编号注释入源码 (lesson #15) / silent 路径接 structlog (lesson #21)
- [ ] 所有引用契约有 file:line 证据锚 (Step 1.5 gate — §契约证据锚表)

---

## 失败模式覆盖契约表 (lesson #17 + #25 + #40)

> **status 列**: ✓existing = 本 drafter grep 实证真存在 (file:line 锚, 反 fabricated lesson #25); NEW = executor 本 plan 创建。**红线 0.3 兑现的关键是失联期间行为 (lesson #17 非 happy-path)** — 下表失联相关行 (Track 4/5) 是 close-out 硬门。

| Track | 失败场景 | 覆盖 test | file | status |
|-------|---------|-----------|------|--------|
| T1.1 | get_open_notional 非 Decimal | `test_get_open_notional_returns_decimal` / `test_get_open_notional_noophost_zero` | tests/core/test_engine_protocol_tier2.py | NEW |
| T1.1 | Tier-2 加后 isinstance 破 | `test_both_hosts_still_isinstance_after_tier2` (relaxed-double 缺方法 fake → False) | tests/core/test_engine_protocol_tier2.py | NEW |
| T1.2 | cap 阈值失效 | `test_local_cap_rejects_over_threshold` / `test_local_cap_allows_under_threshold` | tests/core/test_local_cap.py | NEW |
| T1.2 | cap config float 混入 (红线 0.4) | `test_local_cap_config_parses_decimal_not_float` | tests/core/test_local_cap.py | NEW |
| T1.2 | 失联无 spec → cap floor 兜底 | `test_local_cap_falls_back_to_floor_when_spec_missing` | tests/core/test_local_cap.py | NEW |
| **T1.3** | **失联期间 cap 仍拒超额 (红线 0.3)** | `test_cap_exceeded_during_disconnect_still_rejects` | tests/core/test_local_cap.py | NEW |
| T1.3 | cap 是 live guard (breaker 禁用仍 fire) | `test_cap_is_live_guard_relaxed_double` | tests/core/test_local_cap.py | NEW |
| T1.3 | cap 超额发 PreTradeRejected | `test_cap_exceeded_emits_pre_trade_rejected` | tests/core/test_local_cap.py | NEW |
| T2.1 | snapshot money 非 Decimal | `test_get_positions_returns_decimal_money` / `test_engine_status_drawdown_is_decimal` / `test_snapshot_dataclasses_reject_float_money` | tests/core/test_engine_protocol_tier2.py | NEW |
| T2.2 | snapshot wire 非 str(Decimal) (红线 0.4) | `test_state_snapshot_publishes_str_decimal_money` | tests/core/test_state_snapshot.py | NEW |
| T2.2 | 断线 snapshot 丢失 | `test_snapshot_cached_when_disconnected` | tests/core/test_state_snapshot.py | NEW |
| T2.2 | 周期间隔失效 | `test_state_snapshot_periodic_interval_respected` | tests/core/test_state_snapshot.py | NEW |
| T3.1 | check_engine_connected 误报 | `test_check_engine_connected_reports_disconnected` / `test_check_engine_connected_noophost_connected` | tests/core/test_zombie_detection.py | NEW |
| T3.2 | zombie 超 grace 未降级 | `test_zombie_detected_after_grace_period` | tests/core/test_zombie_detection.py | NEW |
| T3.2 | transient blip 误升级 | `test_zombie_not_flagged_during_transient_blip` | tests/core/test_zombie_detection.py | NEW |
| T3.2 | 维护窗口 pause 误升级 | `test_zombie_exempt_when_paused` | tests/core/test_zombie_detection.py | NEW |
| **T3.2** | **arx 断线时 zombie 自主检测 (红线 0.3)** | `test_zombie_detection_works_when_arx_disconnected` | tests/core/test_zombie_detection.py | NEW |
| T4.1 | flatten NT 映射错 (调不存在方法) | `test_flatten_positions_maps_to_close_all` / `test_flatten_positions_noophost_noop` | tests/engines/nautilus/test_state_snapshot_nautilus_impl.py | NEW |
| T4.2 | breaker notional/drawdown 未触发 | `test_breaker_trips_on_notional_breach` / `test_breaker_trips_on_drawdown_breach` | tests/core/test_fallback_breaker.py | NEW |
| T4.2 | breaker drawdown float (红线 0.4) | `test_breaker_drawdown_uses_decimal_not_float` | tests/core/test_fallback_breaker.py | NEW |
| T4.2 | trip 后未冻结新单 | `test_breaker_freezes_new_orders_after_trip` | tests/core/test_fallback_breaker.py | NEW |
| T4.2 | breaker 是 live guard (cap 缺仍 fire) | `test_breaker_is_live_guard_relaxed_double` | tests/core/test_fallback_breaker.py | NEW |
| **T4.3** | **失联期间 breaker 自主熔断 (红线 0.3 核心)** | `test_breaker_trips_during_arx_disconnect` | tests/core/test_fallback_breaker.py | NEW |
| T4.3 | composition root 未接线 (lesson #40) | `test_reconciler_constructs_all_three_guards` | tests/core/test_fallback_breaker.py | NEW |
| **T5.1** | **失联多守护继续 (红线 0.3 chaos)** | `test_arx_disconnect_cap_breaker_zombie_continue` / `test_arx_disconnect_reconciler_no_crash` / `test_arx_disconnect_snapshot_wal_cached` | tests/core/test_arx_disconnect_chaos.py | NEW |
| **T5.2** | **long-run 失联守护持续** | `test_arx_disconnect_long_run_guards_persist` | tests/core/test_arx_disconnect_chaos.py | NEW |
| T1-4 (回归) | 红线 0.1 credential 泄漏退化 | `test_node_dict_recursive_no_credential` | tests/test_credential_lifecycle.py:109 | ✓existing |
| T1-4 (回归) | 红线 0.4 money float 退化 | `test_float_money_field_rejected` | tests/test_telemetry_money_contract.py:51 | ✓existing |
| T5 (范式) | 断线 log+degrade 已有范式 | `test_nt_messagebus_disconnected_logs_and_degrades` | tests/test_telemetry_nt_bridge.py:316 | ✓existing |
| T2/T5 (范式) | 断线 WAL 缓存已有范式 | `test_wal_stashes_telemetry_while_disconnected_and_drains_on_connect` | tests/test_nats_client_telemetry.py:105 | ✓existing |

> **统计**: **P=4 existing (全 grep 实证 file:line, lesson #25)** + **Q≈33 NEW** (executor close-out 前必 `grep -rn "def <test>" tests/` 逐一实存, 命中数=契约条目数, lesson #25 gate)。红线 0.3 失联硬门 = 加粗 6 行 (T1.3/T3.2/T4.3/T5.1/T5.2)。

---

## 红线 gate 满足度表 (lesson #40 / custos C40)

> close-out 阶段填实**三层区分**: (a) code-level test coverage / (b) runtime wire 接线兑现 (composition root grep 实证) / (c) defer scope。红线名 (vision) ≠ 兑现声明 (reality)。

| 红线 | 目标兑现层 | code_coverage | runtime_wire | defer_status | follow_up_plan_ref |
|------|-----------|---------------|--------------|--------------|---------------------|
| 0.1 Key/KEK 不出进程 | 本 plan 不 touch key I/O | 现有脱敏 test 全绿 (无退化) | 不变 (Tier-2 方法不 log/publish credential) | 无 defer | — |
| 0.2 G6 gate 不绕过 | 本 plan 不 touch gate | 保 Plan 00c/05 状态 | 不变 (host.py 加 Tier-2 不改 G6 路径) | 无 defer | — |
| **0.3 失联 ≠ 停止 (per-runner 层)** | **本 plan 兑现: cap+breaker+zombie** | {close-out 填: cap/breaker/zombie/chaos test 覆盖} | {close-out 填: `cli/main.py` composition root 构造 3 守护 + reconcile loop 失联路径 invoke — grep 实证 T4.3} | {snapshot→arx 消费端迁移 defer 到 arx 自己 plan; 本 plan runtime wire 完整} | arx sidecar 迁移 (arx 项目 plan) |
| 0.4 Money math Decimal | cap/breaker/snapshot 敞口计算 | {close-out 填: `test_*_uses_decimal_not_float` 全绿} | {close-out 填: LocalCapConfig/FallbackBreakerConfig/EngineStatus Decimal + wire str} | 无 defer | — |

**兑现范围声明 (close-out 填实)**: "红线 0.3 per-runner 层从 runtime **未实现** (max_notional_per_runner 0 code 命中) 升级为 **code + runtime wire 完整闭环** (cap 集成 pre-trade + breaker 接 reconcile 失联路径 + zombie watchdog 自主降级, composition root grep 实证接线)。state snapshot 的 arx 消费端迁移非本 plan 范围 (defer 到 arx plan), custos 侧 push 端完整。" — **不承袭红线名当兑现声明** (lesson #40): 本 plan 兑现的是 custos runner 侧 per-runner 守护 runtime wire, arx 前端消费迁移显式 defer。

---

## 偏离与改进日志 (Deviations & Improvements)

> **CEO 决策点 ×3 (elevate, 不静默决定)**: DP1/DP2/DP3 主体给推荐 scope, BOTH options 列此供终裁。

### DEV-04-CAP-DEFAULT 【CEO DECISION POINT 1】
- **等级**: 中 (影响 live 资金结构性上限默认值)
- **问题**: runner-level cap 默认值来源 — config (spec.risk_config) vs env var vs 硬编码; 结构性 floor default (spec 缺 risk_config 或失联无新 spec 时) 取值 paper=200 USD / live=1000 USD?
- **Option A (推荐)**: **config-driven + 保守硬编码 floor 兜底** — 正常从 `spec.get("risk_config", {}).get("max_notional_per_runner")` (云端权威, 缓存自上次成功 pull); spec 缺该字段或首启无缓存时用结构性 floor default (paper=200 / live=1000 USD, Decimal 常量 + 来源注释)。理由: 失联期间必须有兜底值 (红线 0.3 场景), config 缺失不能等于无 cap
- **Option B**: env var (`CUSTOS_MAX_NOTIONAL_PER_RUNNER`) — 运维可调但脱离云端权威
- **Option C**: 纯硬编码 — 简单但不可调
- **影响**: `core/local_cap.py` `LocalCapConfig.from_spec` floor 分支
- **决定**: 主体 A; **CEO 终裁** floor 具体值 (200/1000 是建议, nautilus_host.md:50 提及 `≤ NAV × 5x` 结构性上限口径可参考)

### DEV-04-CHAOS-MECHANISM 【CEO DECISION POINT 2】
- **等级**: 低 (测试手段, 非红线本体)
- **问题**: arx-disconnect chaos test 用 real NATS testcontainer vs mock 断线注入
- **Option A (推荐)**: **mock 断线注入** — 复用 scout §6 现有范式 (`test_deployment_reconciler.py:68` raise / `test_nats_wal_resilience.py:64` stash); 快, 进 `make verify` baseline CI; 覆盖 reconciler/cap/breaker/zombie 逻辑层
- **Option B**: real NATS testcontainer — 更真实 (真 reconnect 行为) 但慢 (容器起停), 归 `make verify-nt` 深度门而非 baseline
- **影响**: `tests/core/test_arx_disconnect_chaos.py` fixture 选型
- **决定**: 主体 A (mock baseline); B 作可选深度补充; **CEO 终裁**

### DEV-04-ZOMBIE-THRESHOLD 【CEO DECISION POINT 3】
- **等级**: 中 (影响 live 降级灵敏度 vs 误报率)
- **问题**: zombie detection grace 阈值 (`engine_disconnected_grace_s`) 默认 60s vs 300s
- **Option A (推荐)**: **60s** (~2× 典型 recon poll interval) — live 安全优先, engine 断连 1 分钟即本地降级; configurable per spec.risk_config
- **Option B**: 300s — 更宽容, 避免瞬时抖动误报, 但 live 下 5 分钟盲区风险
- **影响**: `core/deployment_reconciler.py` watchdog grace 常量 + `test_zombie_detected_after_grace_period` 参数
- **决定**: 主体 A (60s, live 优先); **CEO 终裁**

### DEV-04-TIER2-PROTOCOL-REQUIRED (drafter 决定, 遵 Plan 05 冻结)
- **等级**: 低 (遵上游冻结契约)
- **问题**: Tier-2 6 方法加为 `ExecutionEngineProtocol` required 还是独立 optional Protocol
- **决定**: **required, 加同一 Protocol + 两 host 成对实现** (Plan 05 §Tier-2 line 141-150 已冻结)。约束: 每扩方法 task 原子加 Protocol + 两 host, 保 isinstance 每 commit 绿。**多引擎前瞻 note**: 未来引擎 (hummingbot) 若无 state 支持需 stub 实现 (如 NoopHost 范式); 若 friction 显现, 未来 plan 可拆 optional `EngineStateProtocol` — 本 plan 不预先抽象 (YAGNI)

### DEV-04-FLATTEN-NT-MAPPING (drafter 决定, scout 证据)
- **等级**: 低 (引擎层实现细节)
- **问题**: Protocol `flatten_positions` 在 NT 引擎的实名
- **决定**: core/ 层用引擎中立名 `flatten_positions`; `host.py` 映射到 NT `Strategy.close_all_positions(instrument_id)` (scout §2 实证 NT SDK **无** `flatten_positions`/`flatten_position`)。`test_flatten_positions_maps_to_close_all` 断言映射

### DEV-04-PEAK-EQUITY-DECIMAL (drafter 决定, 红线 0.4)
- **等级**: 低 (money 精度)
- **问题**: 借鉴 ps `_collect_metrics` peak_equity/drawdown 计算精度
- **决定**: **Decimal 重推, 禁 copy-paste ps `runner.py:101 _peak_equity: float`** (scout §8 实证 ps 用 float); 红线 0.4 禁 money float

### DEV-04-DEPLOYMENTSPEC-DICT (drafter 决定, scout §10)
- **等级**: 低 (数据访问范式)
- **问题**: DeploymentSpec 无 Pydantic class, risk_config 怎么读
- **决定**: `spec.get("risk_config", {}).get(...)` dict 访问 (scout §10 实证 DeploymentSpec 全 signature 是 dict); `docs/domain.md:103` 字段清单加 `risk_config` key + `RunnerRiskConfig` 概念 (非加 Python typed field, 因无 class); `LocalCapConfig`/`FallbackBreakerConfig` 自身是 frozen dataclass 从 dict 解析

---

## 完成报告 (Close-out Report)

> **Status**: ⚠️ **Partial (04a slice) — Plan 04 整体 close-out 由 04b 收尾时统一签发**。
> 本段记录 04a slice 落地事实；Plan 04 全部 14 task 完整 close-out 待 04b 完成。

### 04a partial close-out (2026-07-09)

- **完成日期 (04a)**: 2026-07-09
- **04a Task 数**: 9 (含 partial T1.3/T4.2/T4.3) / 全 plan 14 (5 defer 04b)
- **偏离数 (04a)**: 12 LOW (7 impl/CEO 决策 applied + 5 04a new-deviation) — 明细见 `.forge/triage/04a-DEVIATION-triage.md`
- **验证结果 (04a)**: `make verify` 全绿 at slice HEAD (per marker constraints_honored)
- **实施 commit 范围**: `3e85c50` (04a squash) → `b77fbf9` (DEV-04a-TEST-FILE-NAMING annotation)
- **契约影响 (04a)**: `core/engine_protocol.py` Tier-2 3 方法 (get_open_notional / check_engine_connected / flatten_positions); `core/local_cap.py` + `core/fallback_breaker.py` + `core/zombie_watchdog.py` 新建; `deployment_reconciler.py` composition wire; 完整 docs 同步 defer 04b (T6.1)
- **红线守护 (04a)**: 4 红线 grep 全 0 命中（见 04a triage 红线守护实证段）；红线 0.3 **cap 层 + zombie 层 + notional breaker 层 runtime-wire 已 live**，drawdown 层 runtime-wire deferred 04b（lesson #40 code_coverage vs runtime_wire 显式区分）
- **失败模式覆盖 (04a)**: 04a scope 内新增 failure-mode test 全绿 (marker 未详列具体条目数，Plan 04 完整 close-out 时 grep 实存核数收口，per §5 packet FU-INTRA-5)
- **04a 落地清单 (marker source of truth)**: `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-04a-v1.complete.json`

### Plan 04 完整 close-out 待办 (04b 收尾)

- Track 2 完整实施 (state snapshot 3 方法 + dataclass + `state_snapshot.py` 周期发布)
- T5.2 long-run chaos
- Track 6 docs 同步 (reconcile / domain / engine_protocol / nautilus_host)
- T-final Plan 04 完整红线 gate 满足度表填实（drawdown wire 应转 live）
- File Inventory §A 补 `zombie_watchdog.py`
- NT per-order intercept hook (DEV-04a-CAP-ENFORCEMENT-HOOK-DEFER) — 若 v1 pre-live 前完成则并入 Plan 04；否则独立 plan
- 04b DEVIATION triage 并入本文件段落，或独立签发 `.forge/triage/04b-DEVIATION-triage.md` 交叉引用

---

## 下一步 (Next)

Plan 04 close-out 后:
- 红线 0.3 完整兑现, 组合级熔断三层齐 (cap 软限 + breaker 硬限 + zombie 自主降级), 上 live **1 号硬阻断项**消除
- 触发 arx web 的 sidecar HTTP tech debt 独立迁移 (arx 项目自己起 plan, 消费 custos push 的 NATS 快照)
- 与 Plan 06 (ps supertrend 迁移) 组合完成后, custos + ps 生态可跑真实 paper/testnet e2e
- 后续 pre-live 硬门槛清单 (from safety-validator 深度审, 本 plan 消除第 1 项):
  1. ~~红线 0.3 组合级熔断兑现 (本 plan)~~
  2. credential_vault 独立第三方安全审计 (candidate)
  3. 密钥不出进程的 runtime 验证 (抓包/内存 dump 级, candidate)
  4. 跨语言 wire 契约真实跑 (fixture 修复, Plan 05 tech debt)
  5. 签名 release pipeline (供应链, candidate)
  6. 红队/绕过测试 (G6 gate / 失联降级 / 注入, candidate)
  7. 清零 stub (滚动清理)

---

## 进度追踪 (Progress)

| Task | Track | Status | Completed | Notes |
|------|-------|--------|-----------|-------|
| T1.1 get_open_notional + 两 host | 1 | ✅ | 2026-07-09 (`3e85c50`) | Tier-2 Protocol foundation (cap) |
| T1.2 LocalCapConfig + cap-check | 1 | ✅ | 2026-07-09 (`3e85c50`) | 借 PreTradeRuleConfig Decimal 范式; floor paper=200/live=1000 (DP1) |
| T1.3 cap 集成 pre-trade + wire | 1 | ✅ | 2026-07-09 (`3e85c50`) | 失联期间拒单 runtime wire; NT per-order intercept hook 04b (DEV-04a-CAP-ENFORCEMENT-HOOK-DEFER) |
| T2.1 snapshot 3 方法 + 3 dataclass | 2 | 🔲 04b | | peak_equity Decimal 重推; **defer to 04b** |
| T2.2 state_snapshot.py 周期发布 | 2 | 🔲 04b | | NATS build_subject (lesson #26); **defer to 04b** |
| T3.1 check_engine_connected + 两 host | 3 | ✅ | 2026-07-09 (`3e85c50`) | ConnectivityState |
| T3.2 zombie watchdog + degraded | 3 | ✅ | 2026-07-09 (`3e85c50`) | 借 sidecar Rule 2; arx 断线自主; grace=60s (DP3); 独立 `zombie_watchdog.py` (DEV-04a-ZOMBIE-WATCHDOG-MODULE) |
| T4.1 flatten_positions + 两 host | 4 | ✅ | 2026-07-09 (`3e85c50`) | NT→close_all_positions 映射 (DEV-04-FLATTEN-NT-MAPPING) |
| T4.2 fallback_breaker.py trip 逻辑 | 4 | ✅ (partial) | 2026-07-09 (`3e85c50`) | notional trip live; drawdown code ready + equity feed wire 04b (DEV-04a-BREAKER-DRAWDOWN-EQUITY-DEFER, lesson #40 partial scope) |
| T4.3 wire composition root | 4 | ✅ (partial) | 2026-07-09 (`3e85c50`) | notional cap + zombie watchdog wired ⟶ 红线 0.3 runtime wire 部分兑现; drawdown wire 04b |
| T5.1 chaos 多守护失联 | 5 | ✅ | 2026-07-09 (`3e85c50`) | mock NATS disconnect (DP2) |
| T5.2 long-run 失联 chaos | 5 | 🔲 04b | | lesson #17 非 happy-path; **defer to 04b** |
| T6.1 docs 同步 | 6 | 🔲 04b | | reconcile/domain/engine_protocol/nautilus_host; **defer to 04b** |
| T-final close-out | 6 | 🔲 04b | | 红线 gate 表填实 + test grep 实存; **Plan 04 完整 close-out 由 04b 收尾** |

**切片建议 (multi_session_scope=true, lesson #31)**:
- **04a (Tracks 1+3+4 + T5.1)**: cap + zombie + breaker + chaos 核心 — **红线 0.3 runtime wire 硬阻断路径** (Tier-2: get_open_notional / check_engine_connected / flatten_positions)。~9 task。优先。
- **04b (Track 2 + T5.2 + Track 6)**: state snapshot 可观测 (unblock arx sidecar 迁移) + long-run chaos + docs (Tier-2: get_positions / get_orders / get_engine_status)。~5 task。
- execute-team 单 session 跑不完 04 全量时按此切; 04a 优先 (红线核心)。Tier-2 方法按切片分布, 每方法 task 内原子加 Protocol + 两 host (保 isinstance)。
