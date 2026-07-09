# Plan 00b DEVIATION Triage (Step 6 4a)

> **触发**: execute-team skill Step 6 4a 强制 DEVIATION triage 产出 (lesson #25/#28)
> **Triage author**: CEO Claude (main session)
> **Triage date**: 2026-07-08
> **Squash SHA**: `d76ef81` (feat main entry)
> **Chore SHA**: `305128c` (dispatch-log)
> **Base**: `232c5a6`

---

## 分类矩阵 (5 deviations, LOW/MED/HIGH)

| DEV ID | 分级 | 分类 | 描述 | 处理路径 | Verdict |
|---|---|---|---|---|---|
| DEV-00B-ARCH-DECISIONS | **LOW** | 决策 (handoff 推荐默认) | Q1=A duck-typed on_event + msgbus adapter / Q2=A dict payload / Q3=deploy-per-spec | Executor 自主决策, handoff §3 推荐默认, safety-validator + tdd-enforcer + L4 manual peer 三视角 confirm | **ACCEPT** (无红线冲突, plan-index / marker 已记) |
| DEV-00B-DEAD-SUBSCRIPTION | **MED** | Pre-existing bug fix 中风险 | Plan 00a 落地骨架双根因 doubly dead: (A) literal topic `events.order.OrderDenied` vs NT 真实 publish `events.order.{strategy_id}` mismatch (execution/engine.pyx:1341-1343 实证) + (B) async handler 挂 sync MessageBus 导致 coroutine 从不 await drop (component.pyx:2834 实证) | Fix: `events.order.*` wildcard subscribe + sync dispatcher `_on_order_event` + `type(event).__name__ == "OrderDenied"` concrete-class type filter (safety-validator #11 硬判据) + `run_coroutine_threadsafe`/`ensure_future` 双路 + `_pending` set GC-safe pattern (Python 官方 fire-and-forget standard) | **ACCEPT (fix 已合入 squash d76ef81)** — 中风险偏离协议要求 (a) 更新契约文档 ✓ (nt_risk_engine.py docstring + plan 偏离日志) (b) 记入 plan 偏离日志 ✓; safety-validator + tdd-enforcer + L4 manual 三视角 confirm fix 正确性 |
| DEV-00B-ORDERDENIED-FIELDS | **LOW** | Fabricated getattr 修正 | 真实 NT OrderDenied 无 `side/quantity/price/rule_id/reference_price/ts_seconds` — 骨架 getattr 了不存在字段; executor grep NT `order.pyx:637-680` `OrderDenied.__init__` 独立实证 (tdd-enforcer 独立复核 order.pyx:637 定义确认) | Ducktyped 优雅降级 (真实事件 → empty getattr fallback; 假测试 → present); `ts_seconds` 改读真实 `ts_event(ns)`; 加 shape guard `pre_trade_reject_event_shape_mismatch` (skip 缺 reason/instrument_id 事件); 5 字段 wire 契约不变; fingerprint 退化为 (symbol, ts) correlation handle (docstring 已声明非 tamper-evidence) | **ACCEPT** (lesson #25 反 fabricated 教科书应用) |
| DEV-00B-TEST-FILE-DRIFT | **LOW** | Plan 契约表 file drift | Plan 契约表 Task 1 引用 `tests/test_telemetry_envelope.py` (实际不存在); envelope 契约实际覆盖分布在 `test_nats_envelope.py` + `test_telemetry_money_contract.py` (原有) + 新建 `test_telemetry_nt_bridge.py` | 记录 drift, 不改文件名 (契约覆盖已充分, 单纯 rename 无价值); Plan 03 candidate 精细化时 File Inventory 引用真实文件名 | **ACCEPT** (记录 drift 供未来 plan 参考; lesson #9/#11 CEO 元层复发提示 — plan drafter 阶段未 grep 实证 test file 名) |
| DEV-00B-LESSON-29-EXTENSION | **LOW** | Dogfood lesson 扩展 | tdd-enforcer 事故自曝 (git checkout `<ref>` -- . 覆盖工作区非只读 + git stash pop 竞态): 意外 stash 掉 executor 未 commit plan 编辑 + 覆盖 telemetry_actor.py 回旧版; 立即修复 `git checkout HEAD -- <file>` + `git stash pop` + grep 验证完整; 主动识别 lesson #29 同源 (校验类操作副作用覆盖 host) 在 git 历史查询场景复发 | 扩展生态 `historical-lessons.md` #29 "校验类操作副作用覆盖 host" 加 git 历史查询子场景: 首选 `git show <ref>:<path>` (stdout) / `git diff <ref1> <ref2> -- <path>` (无 side effect); 禁 `git checkout <ref> -- .` 三联组合; tdd-enforcer report §4 完整叙事 + marker `lesson_29_extension_ack` acknowledge | **ACCEPT + Follow-up `/forge:lessons` 录入** (Phase 2/3 后 aggregate 阶段正式录入生态 lesson) |

---

## 分级统计

- **HIGH**: 0 (无 HIGH 偏离, 无需 AskUserQuestion accept/fix-now/new-plan)
- **MED**: 1 (DEV-00B-DEAD-SUBSCRIPTION, fix 已合入 squash + 3 视角 confirm)
- **LOW**: 4 (arch decisions / OrderDenied fields / test file drift / lesson #29 extension)

---

## MED 档 user-facing summary (skill 4a §3 强制)

**DEV-00B-DEAD-SUBSCRIPTION** 是 Plan 00a 落地时遗留的 pre-existing bug (骨架 dead subscription doubly dead), Plan 00b executor Foundation Scan Round 4+ 独立抓到 (lesson #14/#33b 影响面维方法论落地示范), fix 属 Plan 00b Task 3 wire attach 前置修复合理范围内。fix 后 tdd-enforcer + safety-validator + L4 manual peer 三视角独立 confirm 正确性:

- topic wildcard 参照 NT 惯用 (portfolio.pyx:197 + risk/engine.pyx:189)
- type discriminator 用 `type(event).__name__ == "OrderDenied"` concrete-class 匹配 (safety-validator #11 硬判据严格约束: 避免 OrderRejected/OrderModifyRejected/OrderCancelRejected 4 类共享 `reason` 语义污染)
- async publish `run_coroutine_threadsafe`/`ensure_future` 双路调度 + `_pending` set 强引用 + `add_done_callback(discard)` GC-safe pattern (Python 官方 fire-and-forget standard)

自我修复 wire contract 无变化, PreTradeRejected envelope 5 字段唯一性保持。**无需 CEO override 或 4 件套** (lesson #38), 属正常中风险偏离协议闭环 (契约文档更新 + plan 偏离日志 + 三视角 review confirm)。

---

## 编排层元层 dogfood 事件 (非 executor plan 内 deviation, 但 CEO 侧 close-out 记录 for lesson aggregate)

按 execute-team skill Step 6 close-out 精神, CEO 层元层 dogfood 累计:

### E1: CEO 层 lesson #11 复发 (未 grep 实证转达 executor stale-view)
- **事件**: CEO 收到 executor SendMessage "`.forge/reviews/2026-07/00b-tdd-enforcer-report.md` untracked, worktree squash-merge 前若不 commit 会丢失" → CEO 未先自己 grep 实证就 SendMessage tdd-enforcer 让她 cp/commit → tdd-enforcer 现场 `git ls-tree custos/00b/runner` 实证 report 已 tracked in c05171e → push back CEO 指令
- **根因**: CEO 层 lesson #37 "spawner 元层不豁免" 适用 SendMessage 转达阶段, 依赖 peer report 未核实同 lesson #9/#11 "不信推理信实证" 复发
- **挽救**: tdd-enforcer fail-safe push back 阻止错误 rework (若走 cp/commit 会引入 stale 主 worktree 副本覆盖 tdd-enforcer 已实证的 c05171e 版本)
- **binding**: 生态 lesson #11/#37 精神扩展; Plan 03 精细化时 CEO SendMessage 转达 peer report 需先 grep 实证再转达 (可作为 handoff packet 起草 checklist 一项)

### E2: CEO 层 lesson #37 复发 (未 grep 实证 Git worktree "one branch = one worktree" 约束)
- **事件**: CEO SendMessage worktree-manager 说 "主 worktree `git checkout custos/00b/runner` 切分支做 consolidation" → worktree-manager 跑发现 `fatal: 'custos/00b/runner' is already used by worktree at ...` → 采用等价替代 (branch worktree 里 cp + commit)
- **根因**: CEO 未事前 grep/查 Git worktree 语义 (Git 不允许同分支两 worktree 同时 checkout) 就出方案
- **挽救**: worktree-manager 事前跑测试无副作用 + 等价替代方案安全落地 (lesson #9/#11 事前实证 + fail-safe 教科书)
- **binding**: 生态 lesson #37 spawner 元层实证扩展 (encoding SendMessage 里含 git/tool 操作指令时应查 tool 语义)

### E3: codex L1/L2 双 fail 记录 (peer review chain fallback)
- **L1 探索不收敛** (lesson #12 症状): high effort 4240 行 log 全 grep/exec 探索, 未收敛 final message
- **L2 sandbox 视图错误**: 主 worktree 处于 main state, codex sandbox 看到 base 232c5a6 disk (非 branch delta)
- **L4 manual 兜底成功**: CEO 亲手在 branch worktree spot-check 7 findings + APPROVED
- **binding**: `.forge/reviews/2026-07/00b-peer-manual.md` §1 Fallback 链失败实证 齐全 (含 exit code + `-o` 文件大小 + 错误片段)

---

## Peer artifact 实证 (rule 10)

按 execute-team skill Step 6 4 peer review artifact 实证 (mandatory-rule 10):

```
PLAN_ID=00b; YYYY_MM=2026-07
ARTIFACTS=.forge/reviews/2026-07/00b-*peer*.md  (含: 00b-peer-codex.md L2 output + 00b-peer-manual.md L4 兜底)
Additionally: 00b-tdd-enforcer-report.md + 00b-safety-validator-report.md (peer review 覆盖面扩展视角)
```

- `00b-peer-manual.md`: **14k bytes > 500 bytes** ✓ (authoritative peer review artifact, APPROVED verdict)
- `00b-peer-codex.md`: 3.2k bytes > 500 bytes ✓ (L2 output 记录, fallback chain 失败证据)
- `00b-safety-validator-report.md`: 8.6k bytes > 500 bytes ✓ (12/12 checklist APPROVE)
- `00b-tdd-enforcer-report.md`: 13k bytes > 500 bytes ✓ (TDD_PASS + 契约表 grep 实证)

**4 artifacts 全 > 500 字节, PASS rule 10 gate**。

---

## Final Verdict

- **Plan 00b close-out APPROVED**
- 全部 5 deviations 已 ACCEPT (无 HIGH, 1 MED fix 已合入 + 3 视角 confirm, 4 LOW 记录/follow-up)
- 3 编排层元层 dogfood 事件已记 (E1/E2/E3, 待 Phase 2/3 后 `/forge:lessons` aggregate 录入)
- Peer artifact rule 10 gate PASS (4 artifacts 齐)
- L4 worktree prune 强制盘点: worktree list clean (仅主 worktree, 无残留)
- Non-Custodial 4 红线 grep 全 0 命中 (baseline + squash 后一致)

**Plan 00b Status: ✅ Completed** (2026-07-08, main HEAD `305128c`)

**Next**: Phase 2 `/forge:plan-team` 精细化 Plan 03 (含 F2 fingerprint 转 Plan 03 candidate Track 5 或独立 follow-up plan + F4 GC-safety invariant test 可选 + E1/E2/E3 lesson dogfood aggregate)。
