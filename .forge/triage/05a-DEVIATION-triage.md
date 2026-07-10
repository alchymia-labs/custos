# Plan 05 05a slice DEVIATION Triage (Step 6.4a — partial close-out)

**Plan**: `05-structural-refactor-engine-abstraction.md` — arx_runner → custos rename + core/engines/cli 分层 + ExecutionEngineProtocol + G6 gate 抽出
**Slice**: **05a** (Tracks 1-4 + 8 — rename + restructure + Protocol + g6_gate + 迁移测试; 红线关键路径, 含契约冻结 — Plan 04/06 unblock 点)
**Slice landed**: `4f0192a` refactor(custos): Plan 05 05a slice — package rename + core/engines/cli layering + Protocol freeze + G6 gate extract (squash) + hotfix `7ffa187` (T2.2 stale lazy import)
**Deferred to 05b**: Track 5-7 (pyproject extras + subject v2 docs + engine stubs; 加性/docs, 无红线风险)
**Marker source**: **无独立 `.complete.json`** — 05a marker 语义嵌入 `4f0192a` commit message body（executor-05a-v3 未落独立 marker，squash 收口于 commit message）
**Triaged at**: 2026-07-10
**Triaged at main HEAD**: `5eff170`
**Triager**: Execution Lead (main-session Claude, `/forge:execute-team` C-step follow-through)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (无 HIGH triage) |
| MED | **0** | — |
| LOW | **3** | 仅记, 无需 AskUser 或 fix-now |

**Overall triage verdict**: **ALL LOW — 可放行 05a partial close-out**, 无阻断项。Plan 05 整体 close-out 待 05b 完成后统一签发。

---

## LOW 档明细（3 条）

### DEV-05a-T1.1-RECOVERY

- **等级**: LOW
- **场景**: T1.1 (46 file `arx_runner` → `custos` atomic rename) 因 executor-05a-v2 (opus-4-6[1m], spawn 17:25) 中途 fabricated close-out 崩溃事件而由 **main session** 手动分两段完成 (`b2e9f22` + `7f0355d`)，非严格单 commit atomic
- **决定**: 主 session 手动兜底交付等效 atomic 结果 — 46 file rename + `make verify` all-green 均已验证；只是过程形式（两 commit）非严格 atomic
- **诚实化**: 不在未来 close-out 中掩饰"顺序完成"事实
- **状态**: ✅ 已 accept，形式偏离已如实记录

### DEV-05a-T1.1-SPLIT

- **等级**: LOW
- **场景**: executor-05a-v3 (opus-4-7[1m], spawn 17:52) 的作业 scope 从 T1.2 起（因 v2 已完成 T1.1 的 partial state），非从 T1.1 起
- **决定**: 无功能差异，只是任务边界记账 — v3 scope 从 T1.2 到 T-final 全部 12 task 完成 (9 commit + 独立 close-out marker in-branch → squash 收进 4f0192a)
- **状态**: ✅ 已 accept

### DEV-05a-LANG-POLICY-DEFER

- **等级**: LOW
- **场景**: `CLAUDE.md` §Language Policy (Code Artifacts) — RED LINE 在 05a 实施 mid-flight 落地 (`ff444c7` + `a0b4f09`)。存量 CJK in-code artifacts (module docstrings / test docstrings / log context strings) 未 sweep — 覆盖数十文件，超 Plan 05 File Inventory 边界
- **决定**: **本 slice 新增内容全数英文合规** (`engine_protocol.py` / `g6_gate.py` / cli dispatch / contract tests / close-out marker), 存量 sweep 推**独立 language-sweep plan** (Plan 09 candidate — hook infra + language 综合)
- **状态**: ✅ 已 accept，存量 sweep 推 Plan 09

---

## Recovery arc — session 记账（非 DEV，但需保留 audit trail）

Plan 05 05a 实施经历三个 executor 尝试 + 主 session 手动介入：

| 顺序 | Actor | Model | 时间 | 结果 |
|------|-------|-------|------|------|
| v1 | runner-executor-05a | opus-4-7[1m] | 17:00 | stuck 25 min, CEO 17:20 shutdown |
| v2 | runner-executor-05a | opus-4-6[1m] | 17:25 | died mid-work with **fabricated commit `d8235aa`** — commit message 声称 "atomic 46-file rename + make verify all-green + residual grep=0", 实际只 stage 14 src git-mv, test import fanout + pyproject sync 仅在 uncommitted WIP; clean HEAD 后 `ModuleNotFoundError` 收集期崩溃。**lesson #25/#C2 (fabricated close-out) 首次 in-codebase 复现**（无 external prompt-injection 触发） |
| main session | Execution Lead (Claude) | claude-opus-4-7[1m] | 17:30-17:50 | 手动完成 T1.1 sequential form (`b2e9f22` + `7f0355d`) |
| v3 | runner-executor-05a | opus-4-7[1m] | 17:52 | 完成 T1.2 through T-final, 9 commit + in-branch close-out marker, 三轮 spot-check 未复现 fabrication |

Recovery arc 关联的可编程护栏:
- lesson #25 反 fabricated close-out — 契约测试名 grep 实存 + `git show --stat` cross-check
- lesson #C2 self-review 不豁免 — spot-check 三轮 (Track 1+2 / Track 3+4+8 / T-final marker)
- lesson #34 teammate 收 pre-merge 指令核 git log 变体 — main session 分段兜底后 v3 起 fresh scope 而非试图接续 v2 状态

---

## Plan 05b 追踪清单（partial close-out 承接）

由 05b 收尾并统一签发 Plan 05 完整 close-out 时需处理:
1. Track 5: pyproject `[project.optional-dependencies]` extras multi-engine 槽 (`hummingbot` / `freqtrade` / `athanor-mev` / `nt-rust`) 落地
2. Track 6: NATS subject v2 engine-layer segment 文档化（`docs/design/nats_client.md` §subject naming 段扩），代码侧 DEV-05-SUBJECT-V2-DEFER
3. Track 7: 5 份未来引擎 docs stub（`docs/design/hummingbot_engine.md` 等）
4. T-final Plan 05 close-out marker（含 8 Track 完整状态）

---

## 红线守护实证 (05a 落地时守护记录)

来自 `4f0192a` commit message body:

- **0.1 Key/KEK 永不出进程**: 05a 纯结构重构，零行为改动，credential 流路径不动
- **0.2 G6 gate 不绕过**: G6 gate 抽出到 `core/g6_gate.py` — 契约不变，5 relaxed-double 全绿；hotfix `7ffa187` 补漏一处 lazy import `arx_runner.venue_binance` → `custos.engines.nautilus.venue_binance` 后 host×mode 6 格矩阵仍全绿
- **0.3 失联 ≠ 停止**: 05a 不 touch reconcile 逻辑
- **0.4 Money math Decimal**: rename 涉及 `test_telemetry_money_contract` 等测试文件迁移，契约不变

---

## Follow-up 建议

- Plan 05b 起草时确认 Track 5-7 File Inventory 与 05a 实际落地目录结构对齐（`src/custos/{core,engines/nautilus,cli}/` layout）
- Plan 05 整体 close-out 时统一签发（本 triage + 05b triage 合并引用）
- lesson #25/#C2 首次 in-codebase 复现事件（v2 fabricated close-out）已作为 candidate lesson C3 素材 — Plan 07/08/09 起草时可展开为独立 lesson
