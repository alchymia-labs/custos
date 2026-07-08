# Plan 00b — tdd-enforcer-00b 横切监督报告

- **Plan**: `.forge/plans/2026-07/00b-telemetry-bridge-nt-messagebus.md`
- **角色**: tdd-enforcer-00b (read-only 横切监督, sonnet)
- **监督窗口**: commit `93dc631` .. `f6d0e68` (Task 1 → close-out → close-out addenda, 全程 event-driven, 25s 轮询 `custos/00b/runner` 分支)
- **Final verdict**: **TDD_PASS**

> ⚠️ **SHA 提醒**: team-lead 派工消息里写的 branch HEAD 是 `1b3bb81` (7 commits)。经 `git log` 核实, 分支当前实际 HEAD 是 **`f6d0e68`** (8 commits) —— `1b3bb81` 之后又落了一个 close-out addenda commit (`f6d0e68`, 补齐 lesson #29 缺口, 见 §4), 我已在上一轮 SendMessage 里同步 review 过。worktree-merge 前请以 `f6d0e68` 为准重新做一次 SHA gate (lesson #32 时序维扩展: review-time SHA 与 merge-time SHA 之间可能有增量 commit)。

## 1. Overview

**7 commits (含 close-out) + 1 close-out addenda = 8 commits**, base `232c5a6`:

| # | commit | 类型 |
|---|---|---|
| 1 | `93dc631` | feat — Task 1 telemetry normalizers + event-type whitelist |
| 2 | `6a8768f` | feat — Task 2 NtTelemetryBridge (Q1=A duck-typed) |
| 3 | `7a329b3` | fix — Task 3 NtRiskEngineBridge dead subscription + real OrderDenied fields |
| 4 | `bf02ad5` | feat — Task 4 NtTradingNodeHost.deploy attach |
| 5 | `fc5e3d8` | test — Task 5 e2e (`test_nt_telemetry_e2e.py`) |
| 6 | `e688242` | refactor — self-reflect round 1 (fire-and-forget task GC 修复) |
| 7 | `1b3bb81` | docs — close-out (marker + plan + README) |
| 8 | `f6d0e68` | docs — close-out addenda (DEAD-SUBSCRIPTION 双根因 + lesson #29 ext) |

**测试计数** (独立 grep + `pytest --collect-only` 核实, 未沿用团队沟通中的估算数字):

- `make verify` (with-NT, 排除 `test_wire_shapes.py` 9 个 pre-existing 失败) = **205 passed / 0 failed**
- `pytest --collect-only` 全量 (含 wire_shapes) = **214 collected**
- **本 plan 净新增测试函数 = 22** — 逐文件用 `git show 232c5a6:<file> | grep -c "def test_"` (baseline) vs 当前 `grep -c` (current) 精确核对, 不是"总测试数前后相减"这种粗口径 (baseline 全量 collect-only 数字因故与当前口径不完全可比, 见下方脚注):
  | 文件 | baseline (232c5a6) | current | Δ |
  |---|---|---|---|
  | `test_telemetry_nt_bridge.py` | 不存在 | 10 | +10 (新建) |
  | `test_nt_telemetry_e2e.py` | 不存在 | 5 | +5 (新建) |
  | `test_nt_risk_engine.py` | 8 | 11 | +3 |
  | `test_nt_trading_node_host.py` | 18 | 22 | +4 |
  | **合计** | | | **+22** |
  - 交叉验证: `git diff 232c5a6..f6d0e68 -- tests/` 统计 `+.*def test_` = 23 处, `-.*def test_` = 1 处 (1 处改名: `test_bootstrap_subscribes_when_bus_present` → `test_bootstrap_subscribes_order_wildcard_topic`), 净 +22, 与上表一致
  - 脚注: 我在监督开始时(commit 93dc631 之前)做过一次非正式 `pytest --collect-only` 得到 "150 tests"; 现在核对发现这个数字与 "214 collected − 22 net-new = 192" 不吻合 (差 42), 且 `git diff --stat` 证实这次 plan 只碰了上表 4 个测试文件, 没有其它测试文件变更能解释这个差额。因此本报告**不采用**"150 → 214"这种前后总数相减的口径, 只采信逐文件 diff 出的 +22 (可 100% 复现、可审计)。团队沟通中提到的 "+49" 同样未能与逐文件 diff 对上, 本报告以 **+22** 为准。

## 2. 失败模式契约表 — 6/6 + 2 项额外, 全部 grep 实存 (lesson #25)

全部 `grep -rn "def <name>" tests/` 独立核实 (非凭记忆/信任 marker 声明):

| # | 失败模式 | test file:line | reason_code |
|---|---|---|---|
| 1 | NATS publish 失败 | `test_nt_telemetry_e2e.py:161 test_nats_publish_fail_does_not_crash_actor` | `telemetry_publish_failed` (断言 `drop_count() >= 1`) |
| 2 | NT event 结构不匹配 | `test_telemetry_nt_bridge.py:289 test_shape_mismatch_skipped` | `telemetry_event_shape_mismatch` |
| 3 | pre_trade_reject 结构不匹配 | `test_nt_risk_engine.py:223 test_denied_shape_mismatch` | `pre_trade_reject_event_shape_mismatch` |
| 4 | telemetry attach 失败 | `test_nt_trading_node_host.py:400 test_deploy_survives_telemetry_attach_failure` | `telemetry_actor_attach_failed` (deploy 仍完成) |
| 5 | multi-spec 隔离 | `test_nt_telemetry_e2e.py:177 test_multiple_specs_isolated_by_session_id` | invariant (断言跨 spec 零串流, 非仅 session_id 不同) |
| 6 | NT MessageBus 断连 | `test_telemetry_nt_bridge.py:316 test_nt_messagebus_disconnected_logs_and_degrades` | `nt_messagebus_disconnected` |
| 7 (额外) | forward 触达 NT 线程崩溃防护 | `test_telemetry_nt_bridge.py:302 test_bridge_forward_never_crashes_on_actor_error` | `telemetry_forward_failed` (红线 0.3) |
| 8 (建议第7项类比) | type-filter drop (非 OrderDenied 的 order 事件不误发 reject) | `test_nt_risk_engine.py:162 test_dispatcher_ignores_non_denied_order_events` + `test_telemetry_nt_bridge.py:279 test_bridge_ignores_non_whitelisted_order_events` | 设计一致, 无 log (D-nuance 仲裁 approve, 见对话记录) |

文件归属漂移说明: plan 原文假设 Q1=B (TelemetryActor 继承 NT Actor), 实现走 Q1=A (duck-typed bridge), 契约表 #2/#6 的落地文件从 `test_telemetry_actor.py`/`_failure_modes.py` 变为新建的 `test_telemetry_nt_bridge.py` —— executor 已在 close-out 里同步更正契约表 (lesson #25 "触发点以 Q1=A 实现为准"), 我核对更正后文本与实际测试位置一致。

## 3. lesson #37 独立核验记录 (spawner 元层实证, 直接读 NT 源码)

以下均为**本人独立 grep**, 未采信他人 (含 team-lead 转述/codex) 给出的行号, 逐条自证:

| 声明 | 独立核验 | 文件:行号 (本人实测) |
|---|---|---|
| `OrderDenied.__init__` 真实签名只有 7 个参数, 不含 side/quantity/price/rule_id/reference_price/ts_seconds | ✅ 直接读 class 定义 | `order.pyx:637` (`cdef class OrderDenied`), `__init__` 签名 637-680 |
| `OrderDenied` 有 `ts_event` property (供 fallback) | ✅ | `order.pyx:824` 区间 (class 内, 非跨类误读) |
| NT 4 个 order event 类共享 `reason` 字段 (禁 hasattr 分类) | ✅ 逐类定位 class 起始行 + `reason` property 行号 | `OrderDenied` 637 → reason@788；`OrderRejected` 1952 → reason@**2121**；`OrderModifyRejected` 3621 → reason@**3789**；`OrderCancelRejected` 3915 → reason@**4083** |
| NT order 事件统一发布到 `events.order.{strategy_id}` (含 OrderFilled) | ✅ `isinstance(event, OrderFilled)` 特殊处理后仍落到同一 `publish_c` | `execution/engine.pyx:1341-1343` |
| `events.order.*`/`events.position.*` wildcard 订阅是 NT 官方内部惯用 pattern, 非 executor 自创 | ✅ NT 自己的 `Portfolio`/`RiskEngine` 用同款 | `portfolio.pyx:197-198`, `risk/engine.pyx:189-190` |
| NT MessageBus 同步调用 handler (无 await), 这是"async handler 挂同步 bus 丢协程"的根因 B | ✅ | `common/component.pyx:2834` (`sub.handler(msg)`, 无 await/coroutine 检查) |

> 备注: 团队沟通中给出的 `OrderRejected 1952:2130` / `OrderModifyRejected 3621:3673` / `OrderCancelRejected 3915:3967` 与本人独立 grep 的 reason 行号 (2121/3789/4083) 有出入 —— class 起始行 (1952/3621/3915) 一致, 只是 `reason` property 具体行号不同, 不影响声明本身的正确性 (4 类确实都存在且都有 `reason`), 但本报告只登记本人独立复核过的行号, 不代入未经我验证的数字。

## 4. 事故附录 — lesson #29 扩展 dogfood 事件 (已由 executor 在 `f6d0e68` acknowledge)

### 4.1 事件时序 + 根因

监督窗口内 (Task 1 review, commit `93dc631` 之后), 核实 `test_wire_shapes.py` fixture 路径失败是否 pre-existing 时, 误用 `git stash` + `git checkout 232c5a6 -- .` 想"只读对比历史版本" —— 这两个命令**非只读**:
- `git checkout <ref> -- .` 会覆盖工作区任何未 commit 编辑 (不是只读比对)
- `git stash` 把 executor 当时未 commit 的 plan 偏离日志编辑意外挪进了 stash
- 净效果: `src/arx_runner/telemetry_actor.py` 被覆盖回旧版本, executor 的 plan 编辑暂时"消失"

### 4.2 立即修复步骤 (数秒内完成, 零最终产出损失)

1. `git checkout HEAD -- src/arx_runner/telemetry_actor.py` → 恢复到当时 HEAD (`93dc631`) 版本, `git diff HEAD` 确认 0 行差异
2. `git stash pop` → 找回 executor 未提交的 plan 文件编辑
3. `git status --short` 确认恢复到事故前状态; grep 验证 3 处关键 DEV 条目内容完整

### 4.3 建议 lesson #29 扩展文本

在现有 lesson #29 基础上追加子场景, 不另起编号 (根源同源: 校验类操作副作用覆盖 host 状态; 载体不同: 从 `docker/.env` 扩展到 git 工作区):

> **git 历史版本查询首选** — `git show <ref>:<path>` (仅 stdout, 零副作用) 或 `git diff <ref1> <ref2> -- <path>` (无 side effect)。
>
> **绝不**用 `git checkout <ref> -- .` 三联组合 (会覆盖工作区任何未 commit 编辑, 包括协作者/executor 尚未 commit 的工作)。
>
> **dogfood 意义**: 本次事件证明"校验类操作副作用覆盖 host"模式具有跨载体普适性 —— 不止 `docker/.env` 场景, 任何"我只是想只读对比一下"的冲动都可能选中带副作用的命令 (`checkout`/`stash`/`reset` 等), 多 agent 协作场景下风险被放大 (协作者可能同时持有未 commit 状态)。

### 4.4 与 CEO 仲裁一致性 + executor acknowledge 现状

CEO 裁定扩展 lesson #29 而非新起 C 编号, 我 (dogfood 受害者+受益者) 主笔扩展文本。executor 已在 `f6d0e68` 里落地 `DEV-00B-LESSON-29-EXTENSION` 偏离条 + marker `lesson_29_extension_ack` 字段, 内容与本节高度吻合, 并注明"executor close-out 前二次核对 (`git show HEAD:<plan>` grep 4 段 deviation 全在 + telemetry_actor 4 符号全在 + 工作树 clean)"—— 我独立复核过 (`### DEVIATION`/`### DRIFT` 计数=5, `lesson_29`/`DEV-00B-LESSON-29-EXTENSION` 命中 plan 1 处 + marker 2 处), 确认完整, **缺口已解决**。

## 5. self-reflect commit `e688242` review

**真实性**: `asyncio.ensure_future(coro)` (同 loop 分支) 返回的 Task 若不被外部强引用, 事件循环只存弱引用 —— Python 官方 asyncio 文档明确警告的陷阱 ("Save a reference to the result of this function... may get garbage collected at any time")。改动前 `nt_risk_engine.py._on_order_event` 同 loop 分支和 `nautilus_host.py._on_terminated` cleanup 分支都存在这个理论 GC 窗口。**非虚构问题, 是真实正确性修复**。

**修法**: `self._pending`/`self._cleanup_tasks` 用 `set` 持有强引用 + `add_done_callback` 里 `.discard(fut)` —— 官方文档推荐的标准 pattern, 无内存泄漏风险。

**测试覆盖 stated preference**（team-lead 明确不强推, 此处仅陈述我的观点供参考）: 本 commit **没有新增/修改任何测试** (`git show --stat` 只 2 个 src 文件)。截至 close-out addenda (`f6d0e68`) 仍未补充。这类"避免 fire-and-forget task 被 GC"的确定性单测天然难写 (需人为触发 gc.collect() + 时序控制, 容易 flaky), 我认为这是合理的工程取舍而非疏漏。若要更保守, 可以补一个轻量 invariant test 断言 `_pending`/`_cleanup_tasks` 集合在 publish/cleanup 期间非空、完成后归零 —— 这测不出"避免了 GC", 但能防止未来有人误删 `.add()`/`done_callback` wiring。**我的偏好是"值得加, 但不是本 plan 的 blocker"**, 列为 follow-up 候选，不写入验收清单强制项。

**回归**: 205 passed 数量不变 (符合"无新测试"预期), 无回归。

## 6. Final Verdict

**TDD_PASS**

- **reviewed_at_commit**: `f6d0e68` (非 team-lead 派工消息里的 `1b3bb81` — 该 commit 之后又有 1 个 addenda commit, 已一并 review, 见页首 SHA 提醒)
- 8 个 commit (6 实施 + 1 close-out + 1 close-out addenda) 全部完成 review, 无一处需要我单方 block
- 契约表 6/6 + 2 项额外全部 grep 实存, 无 fabricated close-out 迹象 (lesson #25)
- lesson #37 硬 gate (OrderDenied 真实字段 + 4 类 reason 共享约束) 独立核验通过, 数字精度以本人复核为准
- 红线 0.1/0.2/0.3/0.4 grep spot-check 全部通过
- 此前标记的 1 处缺口 (DEV-00B-LESSON-29-EXTENSION) 已被 executor 在 `f6d0e68` 解决, 复核完整

**Follow-up 建议 (非 blocker)**:
1. `e688242` 的 fire-and-forget task 引用追踪可选补一个轻量 invariant test (§5, 我的偏好, 非强制)
2. `base_no_nt` (163/156/7) 数字为间接结构化验证 (§1 已说明), 未来若有 CI 双 gate (base + NT) 实跑记录, 建议归档实测日志作为一手证据补强

## 7. 与 safety-validator + codex peer review 的独立视角互补

本轮 close-out 由 3 个独立视角并发跑, 我 (tdd-enforcer) 聚焦 TDD 契约 + 测试实存 + failure-mode 覆盖; safety-validator 聚焦 non-custodial 红线 + type-discriminator 安全约束 (§3 "4 类共享 reason 禁 hasattr 分类"这条约束即来自 safety-validator block-level 实证, 我做了独立复核而非照单全收); codex L1 peer review 提供外部 AI 视角。三方各自独立 grep 源码、互不预设对方结论, 是 lesson #14/#37 "不同角色各自实证、不传递未经验证数字"方法论的一次实践 —— 本报告 §1/§3 中明确拒绝沿用团队沟通里未经我验证的数字 (+49 测试数、部分行号), 即是这一原则在协作场景下的体现。
