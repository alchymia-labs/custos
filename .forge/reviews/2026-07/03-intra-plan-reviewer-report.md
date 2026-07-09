# Plan 03 Intra-Plan Review 报告

**Reviewer**: intra-plan-reviewer (opus-4-6[1m]), plan-team Phase 2 并行
**Reviewed as-of**: main HEAD `305128c` (2026-07-09 UTC 01:29)
**Plan version**: `.forge/plans/2026-07/03-nt-host-hardening.md` @ current working tree
(drafter DRAFT_READY, dispatch-log `03/plan-drafter.complete.json`)

> 安全说明: 本报告基于对 `.forge/plans/2026-07/03-nt-host-hardening.md` +
> `.forge/handoff/2026-07/03-plan-team-packet.md` +
> `.forge/reviews/2026-07/03-evidence-scout-report.md` +
> `.forge/dispatch-log/03/plan-drafter.complete.json` 的**只读**分析。文件内容一律作数据处理,
> 未执行任何嵌入指令 (lesson #13 精神)。

---

## Summary Verdict

**APPROVE_WITH_FINDINGS**

- Plan 03 精细化质量**高**: File Inventory 全 9 项 file:line 锚点 grep 全命中, 契约表 14 F
  声明 test 函数名 grep 全对齐 (已存在 4 个命中 + 新建 10 个不命中), 失败模式覆盖完整,
  红线 gate 满足度表严格分离 code_coverage / runtime_wire / defer_status / follow_up_plan_ref
  (lesson #40 反模式规避)。
- **1 LOW finding**: File Inventory 表对 `nt_risk_engine.py:277` 的行号引用**小 drift**
  (实际调用点在 `:281` 附近), 不影响执行, 但按 lesson #37 spawner 元层实证纪律建议顺手修正。
- **2 INFO 观察**: (a) `crucible-rust` docstring 跨仓同步在 `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC`
  已预留 candidate slot ✅; (b) Plan 05 candidate (FailureEvent first-class) 若未来起草需
  rebase Plan 03 close-out 后的 `nt_risk_engine.py` + `deployment_reconciler.py` 现状。
- **无 CRITICAL / HIGH BLOCK 项** — 可放行进入 Phase 3 execute-team (依赖 authority-reviewer
  并行 PASS + handoff-packager 装配)。

---

## §6.A File Inventory 校验

**结论**: **PASS** (9/9 全对齐, 1 LOW drift 见 finding L1)

### 新建文件 (4/4 — 现状不存在, 符合 "新建" 声明)

| 路径 | 声明 | grep `test -f` | verdict |
|------|------|----------------|---------|
| `tests/test_credential_lifecycle.py` | 新建, T1 Task 1 ~50 LOC | not present | ✅ |
| `tests/test_g6_gate_capability_integration.py` | 新建, T2 Task 2 ~80 LOC | not present | ✅ |
| `tests/test_host_mode_matrix.py` | 新建, T3 Task 4 ~60 LOC | not present | ✅ |
| `tests/test_gc_safety_invariant.py` | 新建, T6 Task 10 ~80 LOC | not present | ✅ |

### 修改文件 (5/5 — 现状存在, 锚点行号 grep 实证)

| 路径 | 声明锚点 | 现状 grep 验证 | verdict |
|------|---------|---------------|---------|
| `src/arx_runner/nt_risk_engine.py` | `:122` (order_fingerprint sig) + `:277` (on_order_denied call) | :122 精确命中 `def order_fingerprint(...)`; :277 附近 (实际 :281) 命中 `fingerprint = order_fingerprint(...)` | ✅ (L1 LOW: :277 → :281 小 drift, 见 findings) |
| `src/arx_runner/nats_client.py` | `:315` (arx-wal-drain create_task) | :315 精确命中 `asyncio.create_task(self._drain_wal(), name="arx-wal-drain")` | ✅ |
| `tests/test_nt_risk_engine.py` | `:269` (test_fingerprint_is_stable_and_hex) + `:180` (test_dispatcher_forwards_real_order_denied) + `:203` (ClientOrderId("O-1")) | 三行号均精确命中 | ✅ |
| `docs/design/nautilus_host.md` | `:79-80` drift #1 (telemetry 桥未落地过时描述) | 精确命中 "当前只本地 structlog 可观测" 过时表述 | ✅ (drift 声明属实) |
| `docs/design/reconcile.md` | 新增 "Undeclared capability traceability" 段 | 现状无此段, 属新增 (evidence-scout §3 drift #3 确认缺失) | ✅ |

---

## §6.B 契约表 grep 实存 (lesson #25 fabricated probe)

**结论**: **PASS** (14/14 全对齐, 无 fabricated test name)

### 已存在 test 声明 (4/4 grep 必命中)

| # | 契约声明 | grep 结果 | verdict |
|---|---------|----------|---------|
| F2 | `test_nt_trading_node_host.py::test_deploy_does_not_retain_credential` line:240 | `:240:async def test_deploy_does_not_retain_credential(...)` | ✅ 命中且行号精确 |
| F3 | `test_nt_trading_node_host.py::test_exception_log_redacts_credential_material` line:301 | `:301:async def test_exception_log_redacts_credential_material(...)` | ✅ 命中且行号精确 |
| F9 | `test_g6_gate.py::test_g6_gate_rejects_live_noophost` line:111 | `:111:async def test_g6_gate_rejects_live_noophost(mode: str)` | ✅ 命中且行号精确 |
| F10 | `test_g6_gate.py::test_g6_gate_allows_live_nt_host` line:131 | `:131:async def test_g6_gate_allows_live_nt_host(strategy_dir)` | ✅ 命中且行号精确 |

### 新建 test 声明 (6/6 grep 必不命中)

| # | 契约声明 (新建) | grep 结果 | verdict |
|---|-----------------|----------|---------|
| F1 | `test_credential_lifecycle.py::test_node_dict_recursive_no_credential` | not present | ✅ 未 fabricate |
| F4 | `test_g6_gate_capability_integration.py::test_undeclared_host_at_reconciler_layer_degrades` | not present | ✅ 未 fabricate |
| F5-F8 | `test_host_mode_matrix.py::test_mode_host_matrix` (4 parametrize cell) | not present | ✅ 未 fabricate |
| F12 | `test_gc_safety_invariant.py::test_nt_risk_engine_pending_discards_after_await` | not present | ✅ 未 fabricate |
| F13 | `test_gc_safety_invariant.py::test_nautilus_host_cleanup_tasks_discards_after_await` | not present | ✅ 未 fabricate |
| F14 | `test_gc_safety_invariant.py::test_nats_client_wal_drain_task_strong_referenced` | not present | ✅ 未 fabricate |

### 修改 test 声明 (2/2 已存在, 计划扩参/断言)

| # | 契约声明 (修改) | grep 结果 | verdict |
|---|-----------------|----------|---------|
| F11 (a) | `test_nt_risk_engine.py::test_fingerprint_is_stable_and_hex` line:269 | `:269:def test_fingerprint_is_stable_and_hex()` | ✅ 命中, 计划扩 `client_order_id` 参数合理 |
| F11 (b) | `test_nt_risk_engine.py::test_dispatcher_forwards_real_order_denied` line:180 | `:180:async def test_dispatcher_forwards_real_order_denied()` + `:203 ClientOrderId("O-1")` | ✅ 命中且行号精确, 真 NT OrderDenied 携带 `client_order_id` 事实实证 |

**lesson #25 fabricated test name probe verdict**: **PASS** — 无编造 test 名, 无 "已覆盖" 空
声明命中失败, 无 "新建" 但实际已存在的漂移。契约表诚信档次高。

---

## §6.C 失败模式覆盖完整性 (lesson #17)

**结论**: **PASS** (F1-F14 契约表覆盖完整, 无本轮抓漏的隐性失败模式)

### 覆盖矩阵 verdict

| # | 失败模式 | 触发点 (Track/Task) | 覆盖 verdict |
|---|---------|---------------------|-------------|
| F1 | credential leak in `node.__dict__` 深度 5 递归 walk | T1/Task 1 | ✅ 新建覆盖 invariant #2 |
| F2 | credential leak in `repr(node)` | 已有 (line:240) | ✅ 交叉引用不重复 |
| F3 | credential leak in structlog `_sanitize_exception` | 已有 (line:301) | ✅ 交叉引用不重复 |
| F4 | undeclared host capability → `handle_spec` 层降级信号 | T2/Task 2 | ✅ 新建, 断言 `phase=degraded` + 双 structlog 事件名 |
| F5-F8 | matrix 4 cell (sandbox×{Noop,Nt} + testnet×{Noop,Nt}) | T3/Task 4 | ✅ 新建 parametrize |
| F9-F10 | matrix 2 cell (live×{Noop,Nt}) | 已有 (test_g6_gate.py:111/131) | ✅ 交叉引用 |
| F11 | fingerprint 加 `client_order_id` 参与 hash | T5/Task 8 | ✅ 修改扩参 + 断言 |
| F12 | `_pending` GC-safety (nt_risk_engine) | T6/Task 10 | ✅ 新建 |
| F13 | `_cleanup_tasks` GC-safety (nautilus_host, 与 F12 属性名不同, drift #5 修正) | T6/Task 10 | ✅ 新建 (属性名分别覆盖) |
| F14 | `_wal_drain_task` GC-safety (nats_client, evidence-scout 新发现漏点) | T6/Task 9+10 | ✅ 新建, Task 9 补代码 fix + Task 10 断言 |

### 潜在遗漏候选独立复核

**候选 X1: T1 credential leak `copy.deepcopy` / `pickle` 边界层是否漏?**
- grep `copy.deepcopy\|deepcopy\|pickle` src/arx_runner/ → **0 命中**
- verdict: **不是 gap** — custos code base 目前不用 deepcopy/pickle 序列化 credential-loaded
  objects, invariant #2 (`__dict__` recursive walk) 已充分覆盖当前对象序列化边界。若未来引入
  deepcopy/pickle 使用, 需新起 plan 补 invariant #4/#5 覆盖新边界。

**候选 X2: T5 correlation handle `venue_order_id` 是否漏?**
- grep `venue_order_id\|VenueOrderId\|OrderInitialized\|OrderAccepted` src/arx_runner/ → **0 命中**
- verdict: **不是 gap** — OrderDenied 是 NT 的 pre-trade reject 事件, venue 尚未看到订单 →
  `venue_order_id` 在本阶段**不存在** (是 post-accept 事件才携带的字段)。Plan T5 选
  `client_order_id` 是 pre-trade 阶段唯一可用的稳定 id (test_nt_risk_engine.py:203 实证是
  真 NT `OrderDenied` 构造参数)。

**候选 X3: T6 是否漏 module (async context / __main__.py fire-and-forget)?**
- grep `asyncio.create_task\|asyncio.ensure_future\|run_coroutine_threadsafe` src/arx_runner/*.py
- **命中清单**:
  - `__main__.py:193, 200` — 2 处 `tasks.append(asyncio.create_task(...))`, **强引用已通过 local `tasks` list + `asyncio.gather` 持有** → 不属"无容器无强引用"家族, 排除合理。
  - `nt_risk_engine.py:214/216` — `_pending` set 持有 → Plan T6 Task 10 F12 覆盖 ✅
  - `nats_client.py:315` — 无容器, Plan T6 Task 9 补 fix + Task 10 F14 覆盖 ✅
  - `nautilus_host.py:216` — `task = asyncio.create_task(node.run_async())`, 存进 `_active_nodes` 强引用
  - `nautilus_host.py:386` — `_cleanup_tasks` set 持有 → Plan T6 Task 10 F13 覆盖 ✅
  - `telemetry_actor.py:275/276` — `self._flush_task = ...` / `self._heartbeat_task = ...` 实例属性持有 (grep 实证 line:172-173 `_flush_task: asyncio.Task[None] | None = None` + line:302-303 shutdown 清理) → 已 GC-safe, 无需 T6 覆盖
- verdict: **不是 gap** — Plan T6 覆盖 3 module 精准, 未漏。asyncio.TaskGroup / anyio nursery
  在本 code base 无使用, 无需覆盖。

**候选 X4: T2 是否漏 `deployment_reconcile_failed` 事件名不同分支?**
- grep `except Exception` src/arx_runner/deployment_reconciler.py → line:226, 242, 316, 388 (4 处 broad except)
- Plan T2 Task 2 断言 line:316 处的 broad except (`handle_spec` 层) 转 `phase=degraded` + `deployment_reconcile_failed` structlog (line:319 实证)
- line:80 `g6_gate_live_capability_denied` structlog (evidence-scout candidate C 实证) ✅
- verdict: **不是 gap** — 其余 3 处 broad except (line:226, 242, 388) 属不同调用层, 与 Plan T2
  scope (undeclared capability → handle_spec 层) 无关。

---

## §6.D 偏离日志 + close-out + 红线 gate 满足度表 (lesson #40)

**结论**: **PASS**

### 偏离日志骨架

- Plan 03 line 424-434 有 3 个 `DEV-03-*` candidate slot 预留 ✅:
  - `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` (跨仓文档 sync candidate)
  - `DEV-03-WAL-TASK-GC-GAP` (Task 9 shutdown cleanup 边界)
  - `DEV-03-FAILUREEVENT-DEFER-CLARIFICATION` (evidence-scout 候选 C 归档)
- 未见 LOW/MED/HIGH 分级明示模板, 但 candidate 描述已含分级线索, 执行阶段可按
  `.claude/rules/deviation-protocol.md` §偏离等级 补齐 (可作为 LOW finding 提示, 不阻断)。

### 完成报告模板

- Plan 03 line 436-452 使用 `.claude/rules/progress-management.md` 模板 (`完成日期 / 总 Task 数 /
  偏离数 / 验证结果 / 实施 commit 范围 / 契约影响 / 红线守护 / 失败模式覆盖 / 遗留项`) ✅

### 红线 gate 满足度表 (lesson #40 精华)

Plan 03 line 404-411 结构:

| 红线 | code_coverage | runtime_wire | defer_status | follow_up_plan_ref |
|------|--------------|--------------|--------------|--------------------|
| 0.1 | ✅ 列出 T1/Task 1 + 已有 :240/:301 | ✅ 显式声明 "本 plan 不改 runtime path, 只扩 invariant test 覆盖面" | 无 defer | — |
| 0.2 | ✅ T2 Task 2 + T3 Task 4 + 已有 :111/:131 | ✅ 显式声明 "runtime 已由 Plan 00c `_check_g6_gate()` 兑现; 本 plan 加集成层与 matrix 深化覆盖" | 无 defer (**FailureEvent.reason_code 撤除标注为 "契约认知修正", 非 defer** — lesson #40 精神) | Plan 05 (candidate): FailureEvent first-class |
| 0.3 | ✅ "Plan 03 不 touch, 保持 Plan 00a/00c 状态" | ✅ "runtime 不动" | 无 defer | — |
| 0.4 | ✅ T5 Task 6 显式声明 `client_order_id` 是 str 非 Decimal, hash 输入路径 str-normalized | ✅ "全部 str 参数, 不 touch Decimal 路径" | 无 defer | — |

**lesson #40 反模式规避核心**: 未承袭红线名当兑现声明 ✅ — 每条红线 code_coverage 与
runtime_wire 显式分离, `FailureEvent.reason_code` 断言撤除明确标注为 "契约认知修正" 而非
"defer 暗坑" (evidence-scout 候选 C 实证 wire 上无此字段, drafter 正确定性)。

**verdict**: 红线 gate 满足度表**完全对齐 lesson #40 精神**, Plan 03 是 custos 独立仓 lesson
#40 落地的模板样本, 未来 plan 可对齐。

---

## §6.E File Inventory 与其他 plan 交集

**结论**: **PASS** (单 drafter 场景 pair-wise N/A; 跨 plan 交集只需 close-out 后 follow-up plan
rebase 提示)

### 已 close-out plan 交集扫描

- Plan 00a (`07467b8` close-out) — F1 defer 转 Plan 03 T1 ✅ (Plan 03 上下文段明确记录源头)
- Plan 00b (`305128c` close-out) — telemetry 桥 `_attach_observability()` 落地, Plan 03 Task 11
  订正 `docs/design/nautilus_host.md:79-80` drift #1 ✅
- Plan 00c (`527b4af` close-out) — G6 gate capability, Plan 03 T2/T3 加固 ✅
- Plan 01 — forge bootstrap, 与 Plan 03 无 src / tests 文件交集 ✅

### In-flight / candidate plan 交集

- `.forge/plans/2026-07/` 目录内只有 00a/00b/00c/01/03, 无 Plan 04/05 candidate 起草中 ✅
- Plan 05 candidate (FailureEvent first-class): Plan 03 T2 描述范围降级已把 FailureEvent
  推 Plan 05 candidate, Plan 03 close-out 后若 Plan 05 起草, 需重新 grep
  `deployment_reconciler.py` + `nt_risk_engine.py` 现状 (Plan 03 T5 修改 nt_risk_engine.py:122 +
  ~281) → **INFO 观察 I2**: 未来 Plan 05 需 as-of Plan 03 close-out 时间锚 (lesson #33)

### 单 drafter 场景说明

`03-plan-team-packet.md §6 团队约束` 明确单 drafter (drafters_per_session=2 但本 plan 单主题),
无 pair-wise 交集 → N/A.

---

## §6.F T5 wire schema 判定复核 (drafter 声明 "不 bump")

**结论**: **PASS** (drafter 判定成立)

### envelope schema 现状实证

grep `payload_schema_version` src/arx_runner/ tests/:
- `nats_client.py:10`: `"payload_schema_version": 1` (docstring 权威声明)
- `nats_client.py:72`: `payload_schema_version: int = 1` (default)
- `nats_client.py:81`: 序列化字段
- `tests/test_wire_shapes.py:35/42`: `test_envelope_uses_payload_schema_version_not_legacy` (防
  legacy `schema_version` 回归)
- `tests/test_nats_envelope.py:28`: `assert env.payload_schema_version == 1`
- `tests/test_telemetry_actor.py:117`, `test_subject_builder_contract.py:39` 均 = 1

### PRE_TRADE_REJECTED_FIELDS 结构

- `nt_risk_engine.py:41-47`: 5 字段 tuple (`tenant_id / rule_id / symbol / order_fingerprint /
  reject_reason`)
- `test_nt_risk_engine.py:113/219`: `assert set(decoded["payload"].keys()) == set(PRE_TRADE_REJECTED_FIELDS)`
  (payload keys 严格锁定)

### T5 修改影响面判定

- Task 6+7: `order_fingerprint()` 签名加 `client_order_id` 参数 → 只改**哈希输入串**
  `symbol|client_order_id|side|qty|price|ts_seconds`, 返回值仍是**单一 hex 字符串**
- Task 6+7: `on_order_denied()` 调用点更新 → payload 中 `order_fingerprint` 字段类型不变 (str)
- payload keys 保持 5 字段 tuple 不变 → wire 形状不变 → **`payload_schema_version=1` 保持** ✅
- Plan §验收清单 line 397 明确要求 `grep -n 'payload_schema_version' tests/test_wire_shapes.py`
  保持 =1 作 close-out gate ✅

### crucible-rust 跨仓 canonical recipe 一致性

- `../crucible-rust/crates/risk/src/pre_trade_service.rs` 真实存在 (grep `.rw-r--r-- 19k`) ✅
- Plan 03 偏离日志预留 `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` candidate slot,
  drafter 已声明"非代码 sync, 是文档措辞同步" ✅

**verdict**: drafter T5 wire schema 判定与实证完全一致, `payload_schema_version` 不 bump 判定
成立, 跨仓文档同步已预留 candidate slot。

---

## Findings

### L1 [LOW] File Inventory `nt_risk_engine.py:277` 行号小 drift

- **track/task**: T5 Task 7 / File Inventory 表
- **problem**: Plan §Task 7 [T5] 段 (line 299) 声明 "`nt_risk_engine.py:277` 现调用:
  `fingerprint = order_fingerprint(symbol, side, quantity, price, ts_seconds)`"; File Inventory
  表 (line 386) 同引 `:277`; 实际 grep 该调用位于 `nt_risk_engine.py:~281` 附近 (sed 250-285
  输出末尾行)
- **impact**: 4 行 drift, 不影响 executor 定位 (function scope 内唯一 `fingerprint = order_fingerprint(...)`
  调用), 但违反 lesson #37 spawner 元层 grep 实证纪律
- **suggested fix**: 精修 `:277` → `:281` (或以 executor 二次 grep 为准, 附 `deviation-log`
  DEV-03-T5-LINE-ANCHOR-DRIFT LOW 记录); 或改成 "on_order_denied() 内 `fingerprint = order_fingerprint(...)`
  唯一调用点" 描述型锚点 (行号无关)

### L2 [LOW] 偏离日志段缺分级模板明示

- **track/task**: 全 plan §偏离与改进日志段 (line 424-434)
- **problem**: candidate slot 已列出 3 个 `DEV-03-*`, 但未按
  `.claude/rules/deviation-protocol.md` §偏离等级 明示 LOW/MED/HIGH 分级模板 (executor 填写时
  可能忘记分级)
- **impact**: close-out 阶段偏离登记质量降级 (lesson #38 CEO override 四件套依赖分级明确)
- **suggested fix**: 偏离日志段加一行注释 "每条 `DEV-03-*` 必标 LOW/MED/HIGH 等级 (按
  `.claude/rules/deviation-protocol.md` §偏离等级)", 或直接在 candidate slot 描述里预标建议
  分级 (例: `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` [LOW-文档跨仓 sync])

### I1 [INFO] crucible-rust 跨仓文档同步已预留 candidate slot ✅

- Plan §偏离日志段已列 `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` candidate slot,
  drafter 已在 track_decisions 声明 "非代码 sync, 是跨仓 docstring 措辞同步"
- **无需 action** — 只作观察记录

### I2 [INFO] 未来 Plan 05 candidate (FailureEvent first-class) 需 as-of Plan 03 close-out rebase

- Plan 03 T2 描述范围降级把 FailureEvent 推 Plan 05 candidate; Plan 03 T5 修改
  `nt_risk_engine.py` 与 Plan 05 可能修改 `deployment_reconciler.py` 有交集风险
- Plan 05 candidate 起草时需按 lesson #33 as-of Plan 03 close-out 时间锚重新扫 `deployment_reconciler.py:316-337`
  与 `nt_risk_engine.py:122`/`:281` 现状
- **无需 action** — 只作 follow-up plan drafter 提示

---

## Recommendation

**APPROVE_WITH_FINDINGS**, 建议放行进入 Phase 3 execute-team (依赖 authority-reviewer 并行 PASS +
handoff-packager 装配 execute-team-packet)。

**放行前建议 (非阻断)**:
- L1 精修 `:277` → `:281` (或改描述型锚点) — 可让 handoff-packager 装配阶段顺手订正, 或由
  executor Foundation Scan 时按 lesson #37 spawner 元层实证纪律主动纠偏 (executor-side lesson
  #9/#11 内化率高的 canary)
- L2 偏离日志段加 LOW/MED/HIGH 分级模板明示 — 可在 close-out 前补齐, 不影响执行阶段

**放行核心依据**:
- File Inventory 全 9 项锚点 grep 全命中 (§6.A PASS)
- 契约表 14 F test 名 grep 全对齐, 无 fabricated (§6.B PASS, lesson #25 精神严格)
- 失败模式覆盖完整 (§6.C PASS, X1-X4 独立复核确认无隐性 gap)
- 红线 gate 满足度表严格分离 code_coverage/runtime_wire/defer_status/follow_up_plan_ref (§6.D
  PASS, lesson #40 落地模板样本)
- 跨 plan 交集只 INFO 提示 (§6.E PASS, 无 rebase 阻断)
- T5 wire schema 判定与实证完全一致, `payload_schema_version` 不 bump (§6.F PASS)

Plan 03 精细化质量在本次审计中是 custos 独立仓 lesson #14/#17/#25/#37/#40 综合落地的
**高质量模板样本**, 可放行执行。
