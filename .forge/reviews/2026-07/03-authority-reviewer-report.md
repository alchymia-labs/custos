# Plan 03 Authority Review 报告

**Reviewer**: authority-reviewer (claude-opus-4-7[1m]), plan-team Phase 2 并行
**Reviewed as-of**: main HEAD `305128c` (Plan 00b close-out)
**权威文档基准**: `.claude/rules/authority-docs.md` §顶层权威 + §六模块设计文档 + §规则集

---

## Summary Verdict

**APPROVE_WITH_FINDINGS**

Plan 03 精细化输出与权威文档整体一致, Non-Custodial 4 红线全数守住, drafter 已消化
evidence-scout 4 项 latent 发现 (候选 C/D + Track 1 覆盖复核 + Track 6 nats_client 漏点),
Track 划分与权威源 file:line 锚点一致。发现 3 项非阻断性 finding, 均可 Phase 3 执行前
修正或作为偏离显式登记, 不影响 plan 整体可执行性。

---

## §A Non-Custodial 4 红线一致性

### 红线 0.1 Key / KEK 永不出进程 — **PASS**

- **Track 1 credential lifecycle invariant**: Task 1 断言 `SENSITIVE_KEY_XYZ` /
  `SENSITIVE_SECRET_ABC` 不出现在深度 5 递归 walk 结果, 补齐 invariant #2 gap; invariant
  #1 (`repr`) + #3 (structlog) 通过 docstring 交叉引用 `test_nt_trading_node_host.py:240` +
  `:301` 已覆盖 — grep 实证两个 test 函数真存在 (line 240 / 301, 与 plan 声明完全一致)
- **T5 correlation handle 语义边界**: `client_order_id` 是 NT venue 层 ID (grep 实证
  `test_nt_risk_engine.py:203 client_order_id=ClientOrderId("O-1")` 存在), **不含 credential
  material**; drafter 明确排除 tamper-evidence 目标 (候选 D), 拒绝在 custos 侧实现 HMAC
  防篡改锚点 — 这与红线 0.1 "KEK 永不出进程" **强正相关** (HMAC 防篡改需 KEK 常驻进程,
  实现即破红线)
- **T5 hash 输入路径 str 化**: `str(getattr(denied, ...) or "")` 沿用 `nt_risk_engine.py:273-275`
  既定 pattern, 无 raw credential 参与 hash

**证据锚点**:
- `docs/design/credential_vault.md` §"KEK 生命周期" (审计入口, mandatory-rules.md §0.1
  已引用) — 无 drift
- `.claude/rules/mandatory-rules.md:11-17` 违反判定 "任何 `send` / `publish` / `log.info`
  调用 payload 含 vault 解密后的原文" — Plan 03 无新 send/publish 路径, 只加 invariant test

### 红线 0.2 G6 host gate 不绕过 — **PASS**

- **Track 2 集成 test**: `handle_spec` 层用 `_CapabilityLessHost` 驱动
  (`test_g6_gate_capability_e2e.py:90 _CapabilityLessHost` grep 实证存在), 断言 gate
  层 1 拒绝信号在 reconciler 包装层不丢失 → **lesson #22/#28 多层 fail-fast + 独立可测**
  的教科书应用
- **Track 3 6 组合 matrix**: 补 `sandbox×{Noop,Nt}` + `testnet×{Noop,Nt}` 共 4 cell;
  已覆盖 `live×{Noop,Nt}` 引用 `test_g6_gate.py:111 test_g6_gate_rejects_live_noophost` +
  `:131 test_g6_gate_allows_live_nt_host` (grep 实证两个 test 函数真存在, line 号完全一致)
- **G6 gate 4 层 fail-fast 一致性**: plan 与 `deployment_reconciler.py:35-61 _check_g6_gate`
  实现完全对齐 (host live capability / venue / code_hash / credential scope)
- **G6 gate helper 引用精确**: plan 已按 evidence-scout drift #2 修正, 引用
  `_host_capability(host, method, *args)` 通用 helper (`deployment_reconciler.py:64-74`),
  非 skeleton 伪代码的内联 lambda — grep 实证 helper 函数签名与描述完全一致

**证据锚点**:
- `docs/design/nautilus_host.md` §"G6 gate 契约" (审计入口, mandatory-rules.md §0.2 已引用)
- `deployment_reconciler.py:35-61 _check_g6_gate` docstring "live 单子一旦落到不具备执行
  能力的 host 上就进了黑洞 (承重墙: live 通道不能落到 stub 上)" — 与 plan Track 2/3 一致

### 红线 0.3 Reconcile 失联 ≠ 停止 — **PASS**

- **Plan 03 不 touch runtime**: 保持 Plan 00a/00c 状态, 无 reconcile loop 语义改动
- **Track 2 `handle_spec` broad except 转 `phase=degraded`**: 与红线 0.3 "本地 fallback
  breaker" 设计延伸一致 — grep 实证 `deployment_reconciler.py:316 except Exception` +
  `:329 phase="degraded"` + `:330 health="unhealthy"`, 不 stop 整个 reconcile loop
- **`_attach_observability` 失败降级**: 已在 Plan 00b close-out 落地 (nautilus_host.py:261-299
  含 `# 红线 0.3: observability loss must not abort deploy` 注释), telemetry 桥 attach
  失败不阻断 trade path

**证据锚点**:
- `docs/design/reconcile.md` §"红线契约·云宕机降级不影响本地 reconcile" — 无 drift, 与
  plan Track 2 broad except 语义一致
- Plan Track 2 决策断言 "handle_spec 不抛出到调用方" 与 reconcile.md 红线契约描述一致

### 红线 0.4 Money math Decimal + str wire — **PASS**

- **T5 `client_order_id` 是 str 字段**: NT `ClientOrderId("O-1")` 的 `str()` 表示是纯字符串
  (非 Decimal / float), 参与 SHA-256 hash 输入无精度语义
- **T5 hash 输入路径已 str-normalized**: `nt_risk_engine.py:273-275` 现有 `str(getattr(...) or "")`
  pattern, T5 Task 7 只加 `client_order_id = str(getattr(denied, "client_order_id", "") or "")`
  一致模式
- **wire schema 不 bump**: `order_fingerprint` 在 payload 中始终是单一 string 字段, 改
  算法不改 wire 形状 — evidence-scout §2 实证 `payload_schema_version=1` 单一权威, 与
  plan §上下文 envelope schema 现状表一致
- **T5 wire test 不动**: plan 验收清单显式 "`grep -n 'payload_schema_version' tests/test_wire_shapes.py`
  保持 =1"

**证据锚点**:
- `docs/design/telemetry_actor.md` §"money contract" (审计入口, mandatory-rules.md §0.4 已引用)
- 与生态历史教训 #23 "money math G5 gate paper/sim only 不上 live" 一致 (custos 从不上 live
  money path, T5 仅是 correlation handle 精度提升)

---

## §B 权威文档 zero-paraphrase 引用一致性

### B.1 引用清单 + grep 实证矩阵

| 权威文档 file:section 引用 | plan 出现位置 | 实证结果 |
|---------------------------|---------------|----------|
| `docs/design/nautilus_host.md:79-80` (telemetry 桥 "未落地") | plan §起源 (drift #1), Orphan Task 11 | ✅ 现状 79-80 行原文 "当前只本地 structlog 可观测" 与 drift 声明一致 |
| `docs/design/nautilus_host.md:79-80` "未来演化路线·短期" 段 | Orphan Task 11 订正目标 | ✅ 段落确实存在, 需订正内容准确 |
| `docs/design/reconcile.md` "Undeclared capability traceability" 段 (缺失) | Task 3 新增 | ✅ evidence-scout drift #3 确认缺失; 待 T2 Task 3 新增 |
| `docs/design/nautilus_host.md` "Credential lifecycle invariants" 段 (缺失) | Orphan Task 11 新增 | ✅ 现状不存在, 需新增 |
| `docs/design/nautilus_host.md` "Host mode × trading_mode matrix" 段 (缺失) | Task 5 新增 | ✅ 现状不存在, 需新增 |
| `docs/design/nautilus_host.md` "Pre-trade reject correlation handle" 段 (缺失) | Orphan Task 11 新增 | ✅ 现状不存在, 需新增 |
| `.claude/rules/mandatory-rules.md` §0 (红线 0.1-0.4) | plan 全文 + 红线 gate 满足度表 | ✅ 4 红线原文与 plan 覆盖一一对应 |
| `docs/domain.md:153 FailureEvent` | plan §起源 (候选 C) + Task 3 描述 | ✅ line:153 定义 FailureEvent 表 (event_id/spec_id/tenant_id/severity/reason_code/detail/at), 与 plan 一致 |

### B.2 源码 file:line 锚点实证 (drafter 引用集)

| plan 引用 | 实证 |
|-----------|------|
| `nautilus_host.py:141 _active_nodes` | ✅ line 141 `self._active_nodes: dict[str, tuple] = {}` + 注释 "Never holds credentials" |
| `nautilus_host.py:146 _cleanup_tasks` | ✅ line 146 `self._cleanup_tasks: set = set()` |
| `nautilus_host.py:108/160 supports_live` | ✅ line 108 (NoopHost False) + line 160 (NtTradingNodeHost True) |
| `nautilus_host.py:113/163 supports_venue` | ✅ line 113 (NoopHost) + line 163 (NtTradingNodeHost) |
| `nautilus_host.py:70-82 _sanitize_exception` | ✅ 逐字对齐 |
| `nautilus_host.py:261-299 _attach_observability` | ✅ line 261 起 `async def _attach_observability`, 含 `NtTelemetryBridge.bootstrap` + `NtRiskEngineBridge.bootstrap` (drift #1 确证 Plan 00b 已落地) |
| `deployment_reconciler.py:35-61 _check_g6_gate` | ✅ line 35 起 docstring 含 "layer 1/2/3/4 fail-fast" + "relaxed-double 测试证明 live guard 而非 dead branch" |
| `deployment_reconciler.py:64-74 _host_capability` | ✅ 通用 helper 函数 (非 lambda), 与 drift #2 修正一致 |
| `deployment_reconciler.py:79-88 g6_gate_live_capability_denied` | ✅ line 80 `_log.error("g6_gate_live_capability_denied", ...)` |
| `deployment_reconciler.py:316-337 handle_spec broad except` | ✅ line 316 `except Exception` + line 318 `deployment_reconcile_failed` + line 325 `_report_status(phase="degraded")` |
| `deployment_reconciler.py:364-393 _report_status` | ✅ line 364-393 定义, payload 无 `reason_code` 字段 (候选 C 验证) |
| `nt_risk_engine.py:122-127 order_fingerprint` docstring | ✅ 逐字实证 "correlation handle, not the tamper-evidence anchor; that's the audit chain HMAC" (候选 D 论据锚) |
| `nt_risk_engine.py:166,217,229 _pending` | ✅ line 166 定义 + line 217/229 add/discard |
| `nt_risk_engine.py:254-275 getattr side/quantity/price` | ✅ getattr 默认空串 pattern 存在, docstring 声明 "side / quantity / price are likewise absent" |
| `nats_client.py:315 asyncio.create_task(self._drain_wal(), name="arx-wal-drain")` | ✅ line 315 `asyncio.create_task(self._drain_wal(), name="arx-wal-drain")` 无 assignment, 与 evidence-scout §5 Track 6 gap 一致 |
| `test_nt_trading_node_host.py:240 test_deploy_does_not_retain_credential` | ✅ grep 实证 line 240 `async def test_deploy_does_not_retain_credential` |
| `test_nt_trading_node_host.py:301 test_exception_log_redacts_credential_material` | ✅ grep 实证 line 301 `async def test_exception_log_redacts_credential_material` |
| `test_g6_gate.py:111 test_g6_gate_rejects_live_noophost` | ✅ grep 实证 line 111 `async def test_g6_gate_rejects_live_noophost` |
| `test_g6_gate.py:131 test_g6_gate_allows_live_nt_host` | ✅ grep 实证 line 131 `async def test_g6_gate_allows_live_nt_host` |
| `test_g6_gate_capability_e2e.py:90 _CapabilityLessHost` | ✅ grep 实证 line 90 `class _CapabilityLessHost:` |
| `test_g6_gate_capability_e2e.py:104 test_undeclared_capability_host_gets_structured_reject` | ✅ grep 实证 line 104 (行号精确一致) |
| `test_nt_risk_engine.py:180 test_dispatcher_forwards_real_order_denied` | ✅ grep 实证 line 180 |
| `test_nt_risk_engine.py:203 ClientOrderId("O-1")` | ✅ grep 实证 line 203 `client_order_id=ClientOrderId("O-1")` |
| `test_nt_risk_engine.py:269 test_fingerprint_is_stable_and_hex` | ✅ grep 实证 line 269 |

### B.3 Drift 独立复核 (evidence-scout 提出的 3 项)

- **Drift #1** (`docs/design/nautilus_host.md:79-80` telemetry 桥 "未落地"): **已被 drafter
  Orphan Task 11 覆盖**, 订正内容为 "Plan 00b (`305128c`, 2026-07-08) close-out 后 telemetry
  桥已落地"; 独立 grep 79-80 行现状确认 "当前只本地 structlog 可观测" 描述仍存在 → drift
  真实 ✅ 订正合理
- **Drift #2** (`_host_capability` 伪代码引用): **已被 drafter 订正**, plan §Track 2 现引用
  "通用 helper 函数 (`deployment_reconciler.py:64-74`)" 与实际代码结构一致 ✅
- **Drift #5** (`_pending` vs `_cleanup_tasks` 属性名混淆): **已被 drafter 分开引用**,
  Track 6 契约表 F12/F13 分别标注 `nt_risk_engine._pending` / `nautilus_host._cleanup_tasks`
  各自属性名 ✅

### B.4 新增权威文档 drift 独立发现

**新 Drift (LOW)**: `docs/domain.md:145-153` FailureEvent 表格描述其为一等实体
(`event_id/spec_id/tenant_id/severity/reason_code/detail/at`), 但 plan Task 3 只在
`docs/design/reconcile.md` 加 "src/arx_runner/ 未实现" 澄清, `docs/domain.md` 本身**未同步**
"实现推 Plan 05 candidate" 注记。未来读者读 domain.md 会误以为 FailureEvent 已实现。**建议**:
Task 3 顺手在 domain.md:145-153 段落末尾加一行小字标注 "**实现状态**: `src/arx_runner/`
未实现, 拟 Plan 05 candidate", 与 reconcile.md Task 3 澄清对齐。这是 lesson #13/#14 "起 plan
未系统扫全骨架" 在权威 spec 端的续编——drafter 已在 impl 层文档订正, spec 层文档需同步。

---

## §C FailureEvent 概念一致性 (候选 C 权威处理)

**verdict**: **APPROVE**

**论据**:
- **domain.md:153 定义**: 独立复核 `docs/domain.md:145-153` §1.5 上报事件章节 — FailureEvent
  在 `HeartbeatEvent / StatusReport / FailureEvent / TelemetrySnapshot` 表格中定义
  (event_id/spec_id/tenant_id/severity/reason_code/detail/at), 与 plan §起源 (候选 C)
  引用一致
- **`src/arx_runner/` 零实现**: 独立 grep `FailureEvent` 在 `src/arx_runner/` 0 命中, 与
  evidence-scout 候选 C 论据一致
- **Track 2 描述范围降级正当**: `_report_status` payload
  (`deployment_reconciler.py:373-382`) 无 `reason_code` 字段 (grep 实证), plan Task 2 集成 test
  改为断言 `phase="degraded"` + `health="unhealthy"` + structlog 双层
  (`g6_gate_live_capability_denied` + `deployment_reconcile_failed`) 是**契约认知修正**
  (不是 defer): drafter 在红线 gate 满足度表 (line 409) 已明确写 "**契约认知修正**, 非 defer"
- **Plan 05 candidate 分离合理**: `FailureEvent` first-class 实现涉及新 subject +
  payload class + publish 方法, 属独立功能面, 不宜塞进本 plan (~200-300 LOC 假设边界)
- **reconcile.md Task 3 新增段合规**: 明确写 "结构化拒绝信号走 DeploymentStatus phase=degraded
  + 双层 structlog 事件名 (`g6_gate_live_capability_denied` + `deployment_reconcile_failed`),
  而非独立的 FailureEvent" — 与 domain.md §1.5 未来 FailureEvent 一等实现之间, 用 file:line
  锚点做 forward reference (`deployment_reconciler.py:79-88` + `:318-324`)

**改进建议 (LOW, 见 §B.4)**: domain.md:145-153 加实现状态注记与 reconcile.md 对齐, 避免
未来读者认知漂移。

---

## §D T5 correlation handle 语义边界 (候选 D 权威处理)

**verdict**: **APPROVE**

**crucible-rust docstring 独立复核**:

grep `crates/risk/src/pre_trade_service.rs:82-91` 结果:

```rust
/// content digest (SHA-256 over `symbol|side|qty|price|ts_seconds`) is a
/// correlation handle — tamper-evidence for the rejection comes from the
/// audit chain's per-tenant HMAC (governance), not from this digest.
fn order_fingerprint(order: &ProposedOrder, at: DateTime<Utc>) -> String {
```

**逐字对齐**: crucible-rust 侧 docstring **明确断言** "correlation handle" + "tamper-evidence
... comes from the audit chain's per-tenant HMAC (governance), not from this digest" —
与 evidence-scout 候选 D 引用完全一致, drafter 决策 "T5 不追求 tamper-evidence" 有权威文档
双侧支撑 (custos `nt_risk_engine.py:122-127` + crucible-rust `pre_trade_service.rs:82-91`
docstring 双向一致)。

**custos 侧 docstring 独立复核**:

`nt_risk_engine.py:122-127` grep 实证 "correlation handle, not the tamper-evidence anchor;
that's the audit chain HMAC" — 逐字与 evidence-scout 候选 D 一致。

**语义边界合理**:
- 真 tamper-evidence 需 KEK 常驻进程 → 违反 custos 红线 0.1 (KEK 永不出进程)
- 云端 audit chain HMAC (governance crate) 是正确的 tamper-evidence 位置, custos 侧
  **不应有可见性也不应实现** — 与 custos 独立仓库 non-custodial 承重墙定位一致
- T5 用 `client_order_id` 提升 correlation handle 精度是**低风险改动**: hash 输入路径全 str,
  不 bump wire schema (evidence-scout §2 实证), 不 touch envelope 字段命名

**改进建议 (LOW)**: `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` 跨仓库 docstring 同步
follow-up 需要明确 scope 边界:
- **custos 是 Apache-2.0 独立仓库**, 跨仓协调**无强制机制**
- workspace 场景下同一 monorepo 内可以协调, 但外部审计员 clone 单 custos 仓时该 follow-up
  不可执行
- 建议在偏离日志显式标记 "**workspace-scope only advisory**", 独立仓视角作为文档一致性
  best-effort 而非 gating

---

## §E historical-lessons 引用完整性 + dogfood E1/E2/E3 aggregate

### E.1 lesson 引用完整性 grep 实证

| lesson 编号 | plan 引用位置 | custos historical-lessons.md 中 grep 结果 |
|-------------|---------------|-------------------------------------------|
| #14 | plan line 191 (Foundation Scan 四维) | ✅ line 32 `## #14/#30/#33/#33b Foundation Scan Gate — 四维方法论` |
| #17 | plan line 193 (happy-path ≠ failure-mode) | ✅ line 40 `## #17 happy-path 测试全绿 ≠ 失败模式覆盖` |
| #22 | plan line 194 (多层 fail-fast 独立可测) | ✅ line 56 `## #22/#28 多层 fail-fast + 独立可测` |
| #25 | plan line 196 (反 fabricated close-out) | ✅ line 67 `## #25 反 fabricated close-out` |
| #26 | plan line 197 (boundary constant matrix) | ✅ line 74 `## #26 pub String boundary / boundary constant 校验` |
| #28 | plan line 194 (与 #22 同段) | ✅ 与 #22 合并 |
| #30 | plan line 191 (Foundation Scan 命名空间维) | ✅ line 32 (与 #14/#33/#33b 合并) |
| #33 / #33b | plan line 191/199 (时间维 + 影响面维) | ✅ line 32 (与 #14/#30 合并) + line 36 提及 |
| #37 | plan line 201 (spawner 元层实证) | ✅ line 23 `## #9/#11/#18/#37 「不信推理信实证」— 全场景适用` |
| **#40** | **plan line 203-204 + line 405 红线 gate 满足度表** | ❌ **NOT PRESENT — custos historical-lessons.md 内无 #40 卡片** |

### E.2 Finding [MED]: lesson #40 独立仓自足性缺口

Plan 03 line 203-204 与 line 405 段头 `## 红线 gate 满足度表 (lesson #40)` 显式引用 lesson
#40 "close-out 声明精确化 — 红线 gate 满足度表按 code_coverage / runtime_wire / defer_status /
follow_up_plan_ref 四列", 但 custos `.claude/rules/historical-lessons.md`:
- 未含 #40 卡片 (line 9-113 的 lesson 卡片段内无该编号)
- "生态 lesson 完整清单" (line 115) 列举 `#1-#8, #10, #12, #13, #15, #16, #19, #20, #23, #24,
  #31, #32, #36` — **不含 #40**

违反 mandatory-rules.md §7 "**独立开源仓库自足纪律**: 规则集 / 权威文档 / verification 命令
不引用 workspace root 路径; 独立场景验证入口应仅需 `uv sync --extra dev` 后即可跑通"。外部
审计员 clone 独立 custos 仓时看到 plan 引用 lesson #40 但无法在 `.claude/rules/historical-lessons.md`
内查到定义。

**修正选项**:
- **(a) 推荐**: 在 custos `.claude/rules/historical-lessons.md` 加 lesson #40 卡片
  (匹配 #17/#22/#25/#26 pattern), 因 Plan 03 主动使用该 pattern (红线 gate 满足度表), 属于
  custos 视角有真实应用的 lesson
- **(b) 备选**: 在 Plan 03 重写 line 203-204 + line 405 段头, 用语义描述替代编号引用
  (如 "close-out 声明精确化 — 红线 gate 满足度四列表pattern"), 不引 workspace-only 编号

### E.3 CEO 层元层 dogfood E1/E2/E3

Plan 03 偏离与改进日志段 (line 424-434) 3 候选 slot 均为 Plan 03 特有偏离
(`DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` / `DEV-03-WAL-TASK-GC-GAP` /
`DEV-03-FAILUREEVENT-DEFER-CLARIFICATION`), **未含** E1/E2/E3 aggregate。

**判定**: E1/E2/E3 来自 Plan 00b 累计 (packet §1 line 92-97 声明), 属于 Plan 00b/00c 执行
期的 CEO 层 lesson dogfood 事件, 应在 Plan 00b/00c 的 close-out 或 `/forge:lessons` 时录入,
**不属 Plan 03 责任范围**。Plan 00c 已 close-out (commit `232c5a6`), 该 aggregate 归属为
close-out 后 `/forge:lessons` 步骤职责, Plan 03 无需承接。

**verdict**: **APPROVE** (E1/E2/E3 归属外部)

---

## Findings 汇总

| # | Severity | 位置 | 问题 | 影响 | 建议 fix |
|---|----------|------|------|------|----------|
| F-AUTH-1 | **MED** | Plan 03 line 203-204 + line 405 引用 lesson #40 | custos `.claude/rules/historical-lessons.md` 无 #40 卡片, 违反独立仓自足纪律 (mandatory-rules.md §7) | 外部审计员 clone 单 custos 仓时看不到 #40 定义, plan 引用悬空 | (a) 加 #40 卡片到 custos historical-lessons.md (推荐), 或 (b) 重写 plan 段落用语义描述替代编号引用 |
| F-AUTH-2 | **LOW** | `docs/domain.md:145-153` FailureEvent 表格 | Task 3 只在 `reconcile.md` 加 "src/arx_runner/ 未实现" 澄清, `domain.md` 本身未同步 | 未来读者读 domain.md 会误以为 FailureEvent 已实现 | Task 3 顺手在 domain.md:145-153 段末加 "**实现状态**: `src/arx_runner/` 未实现, 拟 Plan 05 candidate" 一行 |
| F-AUTH-3 | **LOW** | `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` follow-up | 未标注跨仓 scope 边界 | custos 独立仓视角该 follow-up 无强制机制, 但 workspace 内可协调 | 偏离日志明确标注 "**workspace-scope only advisory**", 外部 clone 时视为 best-effort 而非 gating |

**均非 BLOCK**: 三项都可 Phase 3 执行前修正 (~10 行 docs 改动 + 1 lesson 卡片) 或作为
偏离显式登记后不阻塞执行。

---

## Recommendation

**APPROVE_WITH_FINDINGS to proceed** 前提:

1. **F-AUTH-1 (MED)**: Phase 3 前修正之一
   - 选项 (a): drafter 补 #40 卡片到 `.claude/rules/historical-lessons.md`, 一并 commit
   - 选项 (b): drafter 改写 plan line 203-204 + line 405 段头, 用语义描述替代 "lesson #40" 引用
2. **F-AUTH-2 (LOW)**: 建议 Task 3 顺手 fix (domain.md:145-153 加一行实现状态注记), ~5 行改动;
   若 CEO 判定不修正, 显式登记为 `DEV-03-DOMAIN-DRIFT-DEFER` 偏离
3. **F-AUTH-3 (LOW)**: 建议偏离日志 `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` slot
   预填 "workspace-scope only advisory" 措辞, 明确外部 clone 时 scope 边界

Non-Custodial 4 红线全数守住 (§A), 权威文档引用 zero-paraphrase 一致性极高 (§B, 除 F-AUTH-2
一处 spec 层未同步), FailureEvent 与 T5 correlation handle 两个 evidence-scout 候选处理路径
合理 (§C/§D), lesson 引用完整性除 F-AUTH-1 外全绿 (§E)。plan 可继续 Phase 3, 三项 finding
不阻断整体可行性。
