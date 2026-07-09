# Plan 03 DEVIATION Triage (Step 6.4a)

**Plan**: `03-nt-host-hardening.md` — NT host hardening
**Triaged at**: 2026-07-09
**Triaged at main HEAD**: `52b9dbf`
**Triager**: Execution Lead (main-session Claude)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (无 HIGH triage) |
| MED | **0** | — |
| LOW | **6** | 仅记, 无需 AskUser 或 fix-now |

**Overall triage verdict**: **ALL LOW — 可放行 close-out**, 无阻断项。

---

## LOW 档明细（6 条）

### DEV-03-CREDENTIAL-TEST-NO-NATIVE-NODE

- **等级**: LOW（原 plan md 分级）
- **场景**: Task 1 首版构造真 NT `TradingNode(config)` 触发 SIGABRT (Error 134, 二次原生构造重初始化 NT 全局 Rust logging, verify-nt 全量崩溃单跑不复现)
- **决定 (Path B, per CEO 决议)**: `_walk_dict` 改 walk `TradingNodeConfig` 及其递归子结构（`__dict__` + 容器 depth 5）证明 credential material 不出现在**配置层可达 surface**
- **诚实化措辞** (per codex L1 impl peer review HIGH finding fix): F1 契约措辞降级为 "narrower scope — config surface only" (非"等效证明 invariant #2"); 完整 `TradingNode.__dict__` walk 因 SIGABRT 阻断, **推 Plan 05 candidate (subprocess isolation)**
- **更新的文档**: `tests/test_credential_lifecycle.py` docstring + Plan md §Track 1 脚注 + §F1 契约表 + §红线 gate 满足度表 row 0.1 脚注 + §DEV log
- **状态**: ✅ 已在本 plan 内完全处置

### DEV-03-WAL-TASK-GC-GAP (Q2 solution)

- **等级**: LOW
- **场景**: Task 9 `nats_client.py:315` 补 `self._wal_drain_task = asyncio.create_task(...)` 强引用
- **决定**: 保守只加强引用, **不改 `close()` cancel + await 语义** — pre-existing 竞态非本改动引入 (改动前 ref 全丢, 现在更安全); 加 cleanup 需独立失败模式测试超 Task 10 契约范围
- **safety-validator 复核**: TOUCHED_PASS (`_drain_wal` 开头 `if _js is None: return` guard 缓解 close-during-drain 竞态; task 有限工作自然完成 + 强引用挂 self GC 释放; 异常全 `_log` checklist 8 合规)
- **更新的文档**: Plan md §DEV log + `docs/design/nats_client.md`（若涉及）
- **状态**: ✅ 已 accept, 保守决策合理

### DEV-03-MATRIX-PHASE-FIELD

- **等级**: LOW
- **场景**: Plan 附录 A 写 `phase=healthy`, 代码成功路径实为 `phase=running` / `health=healthy` (`deployment_reconciler.py:309-315`)
- **决定**: 测试 + docs 按代码为准
- **safety-validator FU-1 (LOW, non-blocking)**: 失败路径 `phase='degraded'` ∈ health vocab 但 ∉ `docs/domain.md` phase vocab {pending/starting/running/stopping/stopped/failed}. **Pre-existing drift**, `deployment_reconciler.py` 在 Plan 03 改动清单 0 出现, 非本 plan 引入. 修 → `failed` 或 vocab 合法化 二选一. 已记为 Plan 05+ candidate.
- **更新的文档**: `.forge/plans/2026-07/03-nt-host-hardening.md` 附录 A + §下一步 Plan 05+ candidate list
- **状态**: ✅ 主体 accept; FU-1 记 Plan 05 candidate

### DEV-03-TDD-ORDER-CLARIFICATION (from codex L1)

- **等级**: LOW
- **场景**: Track 5 (Task 6+7+8) 与 Track 6 Test C (Task 9+10) 签名/属性迁移**原子合一**（未拆 RED/GREEN 两 commit）
- **决定**: 签名迁移例外接受, 有 revert-and-run 实证支撑 (tdd-enforcer §D1 用 `git show <prev-sha>` 临时替换 src 复现 RED 状态 — Track 5 `TypeError: order_fingerprint() takes 5 positional arguments but 6 were given` / Track 6 Test C `AttributeError: 'ArxNatsClient' object has no attribute '_wal_drain_task'`)
- **tdd-enforcer non-blocking observation**: DEV 描述"单独提交留破损中间态"措辞略夸大. 建议未来签名迁移场景优先 RED/GREEN 显式两 commit 拆分, 除非确有收集期崩溃等硬性理由. 已记为 Plan 05+ follow-up.
- **更新的文档**: Plan md §DEV log
- **状态**: ✅ 已 accept + follow-up 记录

### DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC

- **等级**: LOW, **workspace-scope only advisory**
- **场景**: T5 fingerprint recipe 加 `client_order_id` 与 crucible-rust `pre_trade_service.rs:82-91` docstring "the same canonical recipe" 分歧
- **决定**: `nt_risk_engine.py:125` docstring 改诚实描述, **不再声称与 Rust 逐字一致** (独立 clone 场景不适用, 只在 workspace 内跨仓协同)
- **更新的文档**: `src/arx_runner/nt_risk_engine.py` docstring
- **状态**: ✅ 已 accept (workspace-scope advisory)

### DEV-03-FAILUREEVENT-DEFER-CLARIFICATION

- **等级**: LOW
- **场景**: Track 2 描述范围降级 — plan 首版假设 `FailureEvent.reason_code` 已存在, evidence-scout 实证 `FailureEvent` 在 `src/arx_runner/` 零实现 (候选 C, 3-round Foundation Scan 抓漏)
- **决定**: 契约认知修正 (非 defer). 集成 test 断言 `phase=degraded` + 双层 structlog (非 `FailureEvent.reason_code` 命中); `docs/design/reconcile.md` + `docs/domain.md` 加实现状态注记
- **Follow-up**: `FailureEvent` first-class 实现推 Plan 05 candidate
- **更新的文档**: `docs/design/reconcile.md` + `docs/domain.md:145-153`
- **状态**: ✅ 已 accept, first-class 实现推 Plan 05

---

## Plan 05+ Candidate Follow-ups（综合本 plan close-out 出 4 项）

1. **NT node lifecycle invariant #2 subprocess isolation** — 从 codex L1 HIGH F1 scope + safety-validator FU-2 canary 合流. 用 `multiprocessing.Process` 隔离 native NT 构造, 绕开 SIGABRT, 完成 red line 0.1 invariant #2 full coverage
2. **matrix phase='degraded' vocab drift** — safety-validator FU-1 (pre-existing, 非 Plan 03 引入). 修 → `failed` 或 vocab 合法化 二选一
3. **future signature migration TDD RED/GREEN explicit split** — tdd-enforcer non-blocking observation. 未来签名迁移场景优先 RED/GREEN 显式两 commit 拆分, 除非确有收集期崩溃等硬性理由
4. **FailureEvent first-class 实现** — 从 DEV-03-FAILUREEVENT-DEFER-CLARIFICATION + docs/domain.md:145-153 spec 设计已就位但代码零实现

---

## Close-out Gate Verdict

- ✅ 无 HIGH triage (无需 AskUserQuestion)
- ✅ 无 MED user-facing summary (0 条 MED)
- ✅ 6 条 LOW 全数记录 + 处置说明
- ✅ Plan 05+ candidate list 已同步 marker `follow_ups_for_plan_05_candidate`

**Close-out 阻断项**: **无**。可推进 Step 6.4d teammate shutdown + Step 6.6 ops-team chain nudge 评估。
