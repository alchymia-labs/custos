# Plan 03 Peer Review — Codex L1 high effort (Plan Review)

**Reviewer**: codex-cli 0.142.0, model_reasoning_effort=high, read-only sandbox  
**Reviewed at commit**: main HEAD 305128c  
**Review type**: Plan Review (非 code review)

## Summary Verdict
- APPROVE_WITH_FOLLOW_UPS

## 维度 1: Track 划分合理性
APPROVE。6 Track 与 evidence-scout 的 4 latent + 5 drift 对齐。T1 缩窄到 `__dict__` recursive walk 合理；T2 从不存在的 `FailureEvent.reason_code` 降级到 `DeploymentStatus phase=degraded` 合理；T5 重命名为 correlation handle 精度提升符合 `nt_risk_engine.py:122-127` “非 tamper-evidence anchor” 边界；T6 扩展到 `nats_client.py:315` 是同族漏点。

## 维度 2: 契约证据完整性 (lesson #25)
APPROVE_WITH_FINDING。4 个已存在测试 grep 命中：
- `tests/test_nt_trading_node_host.py:240` `test_deploy_does_not_retain_credential`
- `tests/test_nt_trading_node_host.py:301` `test_exception_log_redacts_credential_material`
- `tests/test_g6_gate.py:111` `test_g6_gate_rejects_live_noophost`
- `tests/test_g6_gate.py:131` `test_g6_gate_allows_live_nt_host`

但契约表把 F5-F8 的 pytest 参数化 node id 当作 4 个“test 函数”，且把 F11 两个已存在测试修改项计入“10 新建 test”。这会削弱 close-out grep gate，见 Finding 1。

## 维度 3: File Inventory test -f 预检
APPROVE。Plan 表实际是 10 条：4 新建测试文件均不存在，6 个修改文件均存在。

新建预检：
- `tests/test_credential_lifecycle.py` missing
- `tests/test_g6_gate_capability_integration.py` missing
- `tests/test_host_mode_matrix.py` missing
- `tests/test_gc_safety_invariant.py` missing

修改预检：
- `src/arx_runner/nt_risk_engine.py:122` / `:277` 命中
- `src/arx_runner/nats_client.py:315` 命中
- `tests/test_nt_risk_engine.py:180` / `:269` 命中
- `docs/design/nautilus_host.md:79-80` 命中待订正 drift
- `docs/domain.md:145-153` 命中 FailureEvent 表
- `docs/design/reconcile.md` 存在，目标新段当前不存在，符合“待新增”

## 维度 4: 失败模式覆盖完整性 (lesson #17)
APPROVE_WITH_FOLLOW_UP。F1-F14 覆盖主失败家族足够全面。有限扫描 `src/arx_runner` 调度点显示：`__main__.py:192/199` 用 `tasks` 列表强引用，`telemetry_actor.py:275-276` 有 `_flush_task/_heartbeat_task` 且 `:287-294` cancel+await，`nt_risk_engine.py:216-218` 有 `_pending`，`nautilus_host.py:386-388` 有 `_cleanup_tasks`。唯一未赋值同族漏点仍是 `nats_client.py:315`。

补充风险：F14 只断言强引用，不断言 shutdown cancel/await。见 Finding 3。

## 维度 5: 与 intra 互补覆盖
APPROVE_WITH_FINDINGS。
- 测试命名：`test_node_dict_recursive_no_credential`、`test_undeclared_host_at_reconciler_layer_degrades`、GC 三个测试名语义清楚；`test_mode_host_matrix[...]` 是 pytest collection node id，不是 grep-able function name。
- T5 hash 分布：`client_order_id` 非空时显著改善现有 `(symbol, ts)` 退化；为空时不比现状更差，只是无新增熵。handoff Q1 已给偏离记录路径，够用。
- T6 shutdown：当前 `ArxNatsClient.close()` 在 `nats_client.py:317-324` 关闭 `_wal`，没有 cancel/await `_drain_wal` task；计划应把 Q2 从“evaluate”提升为验收或显式偏离。

## 维度 6: Non-Custodial 4 红线复核
APPROVE。
- 红线 0.1：T5 加 `client_order_id`，证据 `tests/test_nt_risk_engine.py:203 ClientOrderId("O-1")`，不是 credential 或 credential-adjacent 字段。
- 红线 0.2：T2 `phase=degraded` 是 gate 拒绝后的状态上报，不是 bypass；`deployment_reconciler.py:316-331` broad except 后上报 degraded/unhealthy。
- 红线 0.3：Plan 03 不改 reconcile stop 语义；degraded 保持 loop 继续。
- 红线 0.4：T5 全是 str-normalized hash 输入，不改 Decimal money math 或 wire schema。

## Findings (最多 5 条独立 finding)
- [MED] 契约表 / lesson #25 — F5-F8 与 F11 的“10 新建 test 函数”计数不精确 — pytest 参数化 case 不是 `def test_*`，F11 是修改现有 `tests/test_nt_risk_engine.py:180/269` — close-out grep gate 可能误报或漏报 — 建议改成“10 contract checks”，F5-F8 用 `pytest --collect-only` 验证 node ids，F11 标为“修改已存在测试”。
- [LOW] TDD 顺序 — handoff §2 把 T5 写成 Task 6→7→8、T6 写成 Task 9→10 — 若执行层按严格 TDD，会先实现再写红测 — 建议改为 Task 8 red → Task 6/7 green，Task 10 red → Task 9 green；或显式记录这是签名迁移例外。
- [LOW] T6 Task 9/10 — `_wal_drain_task` 只要求强引用，shutdown 语义仍开放 — `nats_client.py:317-324` 当前 close 不 cancel/await drain task，可能与 `_wal.close()` 竞争 — 建议 Task 10 增加 close-time cancel/await 测试，或在 deviation log 明确保守不改的理由。

## Recommendation
- APPROVE_WITH_FOLLOW_UPS to proceed。上述 3 条建议在 Phase 3 执行前或执行中修正即可；未发现需要阻断 Plan 03 的 HIGH/CRITICAL 问题。