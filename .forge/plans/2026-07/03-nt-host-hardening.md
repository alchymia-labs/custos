# 03 — NT host hardening (credential lifecycle + capability traceability + correlation handle 精度 + GC-safety invariant)

> **Status**: 🔲 Todo (Phase 2 精细化后可执行; 未起 executor)
> **Created**: 2026-07-08 (Plan 00c close-out 追加, DEV-00c-DEP-SKIP-CEO-OVERRIDE HIGH triage 决定 = new-plan)
> **Refined**: 2026-07-09 (`/forge:plan-team 精细化` — Phase 2 evidence-scout + plan-drafter 深化)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: 精细化完毕, 可 `/forge:execute` 单会话内跑完
> **Depends on**: Plan 00a ✅ (NT host 真起) + Plan 00b ✅ (telemetry 桥 close-out `305128c`) + Plan 00c ✅ (capability G6 gate)
> **Blocks**: (无硬 block, 属安全深化)
> **multi_session_scope**: false (11 Task, ~250-300 LOC 含 docs; 单 session 可完成)

## 起源 (Origin)

本 plan 起源为两条独立 defer 项汇合, Phase 2 精细化后由 evidence-scout 深化发现补齐 scope:

1. **来自 Plan 00a codex peer review F1 (defer 项)** — `.forge/marker/00a-runner.complete.json`
   记 F1_in_process_credential_memory: "deferred (not a violation; NT<->exchange comms
   design necessity, red line limits I/O boundary) -> Plan 03 candidate (credential
   lifecycle test suite)"
2. **来自 Plan 00c HIGH DEVIATION triage 决定 (2026-07-08)** — CEO override 4 件套齐
   accept 后 CEO 选 `new-plan` 路径, 让 Plan 03 承载 "Plan 00c 未覆盖的 NT host 硬化项"
3. **Phase 2 精细化 evidence-scout 深化发现 (2026-07-09, `.forge/reviews/2026-07/03-evidence-scout-report.md`)**:
   - **候选 C (新)**: `FailureEvent` 概念在 `src/arx_runner/` **零实现**, `_report_status()`
     发布的 `DeploymentStatus` payload 无 `reason_code` 字段 → **Track 2 描述范围降级**
     (改为断言 `phase=degraded` + structlog 双层日志, 不断言 `FailureEvent.reason_code`)
   - **候选 D (新)**: Track 5 原命名"fingerprint tamper-evidence 恢复"与两侧代码库
     (custos + crucible-rust) 自己的设计文档相矛盾——真正的防篡改锚点是云端 audit chain
     HMAC (governance crate), custos non-custodial 承重墙**不该有可见性** → **Track 5 重命名**
     为 "pre-trade reject correlation handle 精度提升" (加真实存在的 `client_order_id`,
     不追求 tamper-evidence)
   - **Track 1 现有覆盖复核 (新)**: skeleton 三层 invariant 中的 #1 (repr) 已由
     `test_nt_trading_node_host.py:240 test_deploy_does_not_retain_credential` 覆盖,
     #3 (structlog) 已由 `test_nt_trading_node_host.py:301 test_exception_log_redacts_credential_material`
     覆盖, **真正缺的只有 #2 (node.__dict__ recursive walk)** → **Track 1 缩窄**
     (~120 LOC → ~50-70 LOC, 只补 #2, 其余交叉引用不重复造轮子)
   - **Track 6 范围扩展 (新)**: `nats_client.py:315` WAL-drain fire-and-forget task 是与
     `_pending` (nt_risk_engine.py) / `_cleanup_tasks` (nautilus_host.py) **同族失败模式的
     唯一漏点** (无强引用容器保护) → **Track 6 扩展**到 3 module + 补 `self._wal_drain_task`
     1 行代码 fix
   - **Drift #1**: `docs/design/nautilus_host.md:79-80` "未来演化路线·短期" 段仍称 Plan 00b
     telemetry 桥"未落地", 但代码已随 `_attach_observability()` 落地 → File Inventory 加订正
   - **Drift #2**: skeleton `03-nt-host-hardening.md:49` 引用 `_host_capability = getattr(...)`
     是伪代码, 实际 `deployment_reconciler.py:64-74` 是通用 helper 函数 → 措辞修正
   - **Drift #5**: packet 把 `_pending` (nt_risk_engine) 与 `_cleanup_tasks` (nautilus_host)
     混为同一个属性名 → Track 6 测试按各自真实属性名分别覆盖
4. **Track 4 移除**: Plan 00b close-out (2026-07-08 `305128c`) 已把 telemetry 桥落地
   (`_attach_observability()` 真调 `NtTelemetryBridge.bootstrap`), Track 4 (telemetry 桥测试
   脚手架 optional) 需求消失

## 上下文 (Context)

**现状 (2026-07-08 as-of Plan 00b close-out `305128c`, 2026-07-09 evidence-scout 复核)**:

Plan 00a + 00b + 00c 落地后 NT host 已就位:
- `NtTradingNodeHost` 真起 sandbox / testnet / live 三档 (`nautilus_host.py:166-228 deploy()`)
- `NautilusHostProtocol` 加 `supports_live` / `supports_venue` capability 契约面
  (`nautilus_host.py:108/160/113/163`)
- G6 gate 4 层 fail-fast + relaxed-double 独立可测 (`deployment_reconciler.py:35-61 _check_g6_gate`)
- credential vault 已守 `permission_scope == "trade_no_withdraw"`, gate 侧 double-check
- telemetry 桥已通 (`nautilus_host.py:261-299 _attach_observability`, Plan 00b close-out)
- pre-trade 拒绝走 `nt_risk_engine.on_order_denied()` → `PreTradeRejected` wire 5 字段
  (`nt_risk_engine.py:41-47`)

**src 模块** (14 file, Plan 00c/00b 期后):

```
src/arx_runner/
├── __init__.py __main__.py config.py log.py enrollment.py
├── credential_vault.py         # 7.7k — T1 邻近先例 (stdlib logging 用 caplog)
├── nautilus_host.py            # 18k — T1/T3/T6 焦点 (_active_nodes + G6 gate + _cleanup_tasks)
├── nt_risk_engine.py           # 15k — T5/T6 焦点 (order_fingerprint + _pending)
├── telemetry_actor.py          # 23k — 参考 (dict-index 正确模式)
├── deployment_reconciler.py    # 15k — T2 焦点 (_check_g6_gate + handle_spec broad except)
├── _nt_binance_venue.py        # 9.3k
├── _strategy_loader.py         # 5.2k
├── nats_client.py              # 17k — T6 扩展 (arx-wal-drain 无强引用容器)
└── reconcile.py                # 5.4k
```

**tests** (28 file, T1/T2/T3 已有覆盖复核见 evidence-scout report §5):
- **T1 现有覆盖**: `test_nt_trading_node_host.py:240` (repr, invariant #1) +
  `test_nt_trading_node_host.py:301` (structlog, invariant #3) → 只缺 invariant #2 (__dict__ walk)
- **T2 现有覆盖**: `test_g6_gate_capability_e2e.py:104 test_undeclared_capability_host_gets_structured_reject`
  只测 gate 单层, 缺 `handle_spec` 集成层 (phase=degraded 断言)
- **T3 现有覆盖**: `test_main_host_selection.py:19/24` + `test_g6_gate.py:111/131` 已覆盖
  live×{Noop, Nt} 2 格, 缺 sandbox×{Noop, Nt} + testnet×{Noop, Nt} 共 4 格
- **T5 现有覆盖**: `test_nt_risk_engine.py:180 test_dispatcher_forwards_real_order_denied`
  已有真 NT `OrderDenied(client_order_id=ClientOrderId("O-1"))` 驱动; `:269 test_fingerprint_is_stable_and_hex`
  已测 fingerprint 稳定性 → 需扩以覆盖 `client_order_id` 参与 hash
- **T6 现有覆盖**: 无独立 gc-safety-invariant test 文件

**envelope schema 现状** (`src/arx_runner/nats_client.py:61-89`):
- `envelope_version=1` + `payload_schema_version=1` 单一权威
- `PRE_TRADE_REJECTED_FIELDS` (`nt_risk_engine.py:41-47`) 5 字段 (`tenant_id / rule_id /
  symbol / order_fingerprint / reject_reason`)
- T5 只改 `order_fingerprint()` 哈希输入, 不改 wire 字段形状 → `payload_schema_version` **不 bump**
  (evidence-scout §2 已实证)

## Track 划分 (Phase 2 精细化后)

### Track 1 — Credential lifecycle recursive dict invariant (缩窄)

- **问题**: `NtTradingNodeHost._active_nodes[spec_id] = (node, task)` (`nautilus_host.py:141`)
  通过 `node` 引用间接持有 credential; 现有测试覆盖 `repr(node)` (invariant #1) +
  structlog `_sanitize_exception` (invariant #3), **缺 `node.__dict__` 深度 5 递归 walk**
  (invariant #2)
- **决策**: skeleton "3 test suite ~120 LOC" 缩窄为 **1 test ~50 LOC** (只补 invariant #2);
  invariant #1/#3 用 docstring 交叉引用已有测试, 不重复造轮子 (evidence-scout §5 建议)
- **交付**: `tests/test_credential_lifecycle.py` (新, ~50 LOC, 1 test + `_walk_dict` util)

### Track 2 — Undeclared capability traceability at reconciler level (描述范围降级)

- **问题**: Plan 00c F2 fix `_host_capability(host, "supports_live")`
  (`deployment_reconciler.py:64-74` 通用 helper, 非 skeleton 描述的内联 lambda) 已在,
  但只有 `_check_g6_gate` gate 单层测过 (`test_g6_gate_capability_e2e.py:104`);
  `handle_spec` 集成层 (broad `except Exception` 转 `phase=degraded` 状态上报) 未测
- **决策 (范围降级)**: evidence-scout 候选 C 实证 `FailureEvent` 概念在 `src/arx_runner/`
  **零实现**, `_report_status()` (`deployment_reconciler.py:364-393`) 发布的
  `DeploymentStatus` payload 无 `reason_code` 字段 → **Track 2 集成 test 不断言
  `FailureEvent.reason_code` 命中**, 改为断言:
  1. `handle_spec` 不抛出到调用方 (不打断 reconcile loop, 红线 0.3 式设计的自然延伸)
  2. `_report_status` 被调用且 `phase="degraded"` / `health="unhealthy"`
  3. structlog 命中 `g6_gate_live_capability_denied` (gate 层, `deployment_reconciler.py:79-88`)
     + `deployment_reconcile_failed` (reconciler 包装层, `deployment_reconciler.py:318-324`)
- **交付**: `tests/test_g6_gate_capability_integration.py` (新, ~80 LOC)
- **Follow-up 建议**: `FailureEvent` first-class 实现是独立功能面, 若未来需要真正的 uplink,
  另开 follow-up plan `05-failure-event-first-class.md` (docs/domain.md 已有设计但从未排期)

### Track 3 — `--use-nt-host` × `spec.trading_mode` 6 组合 matrix (增量补 4 cell)

- **问题**: sandbox / testnet / live 三 mode × NoopHost / NtTradingNodeHost 两 host = 6 组合;
  现状 live×{Noop, Nt} 已由 `test_g6_gate.py:111/131` 覆盖, 缺 sandbox / testnet 各 2 格
- **决策**: skeleton 的 "6 组合 matrix test 全覆盖" 精确为**增量补 4 cell**
  (sandbox×{Noop, Nt} + testnet×{Noop, Nt}); 已覆盖 cell 在附录 A 引用现有 test 位置
- **交付**: `tests/test_host_mode_matrix.py` (新, ~60 LOC, pytest 参数化, 覆盖 4 cell)

### Track 5 — Pre-trade reject correlation handle 精度提升 (重命名 + in-scope)

- **问题 (evidence-scout 候选 D)**: skeleton 原命名 "fingerprint tamper-evidence 恢复"
  与两侧代码库设计文档相矛盾:
  - `nt_risk_engine.py:125` docstring: "correlation handle, not the tamper-evidence anchor;
    that's the audit chain HMAC"
  - `crucible-rust/crates/risk/src/pre_trade_service.rs:82-91` docstring: "tamper-evidence
    ... comes from the audit chain's per-tenant HMAC (governance), not from this digest"
  - 真正的防篡改锚点是**云端 audit chain HMAC (governance crate)**, custos non-custodial
    承重墙不该有可见性也不该实现
- **同时**: `nt_risk_engine.py:254-275` 生产路径 `getattr(denied, "side"/"quantity"/"price",
  "") or ""` 恒为空字符串 (真 NT `OrderDenied` 事件无这些字段, `test_nt_risk_engine.py:180`
  实证), fingerprint 实质退化为 `(symbol, ts)` 二元组
- **决策 (重命名 + 精度提升)**: Track 5 目标从 "tamper-evidence 恢复" 改为
  "pre-trade reject correlation handle 精度提升" — 用**真实存在**的 `client_order_id`
  (`test_nt_risk_engine.py:203` 实证 `ClientOrderId("O-1")` 是真 NT `OrderDenied` 构造参数)
  参与 hash, 提升相关性句柄唯一性; **明确不追求防篡改能力**
- **wire schema 影响**: `order_fingerprint` 在 payload 中始终是单一字符串字段, 改算法不改
  wire 形状, `payload_schema_version` **不 bump** (evidence-scout §2 实证);
  与 `crucible-rust/crates/risk/src/pre_trade_service.rs:82-91` "the same canonical recipe"
  文档约定同步更新 (跨仓文档一致性, 不需要代码同步)
- **交付**:
  - `src/arx_runner/nt_risk_engine.py`: `order_fingerprint()` 签名加 `client_order_id` 参数 +
    `on_order_denied()` 调用点更新 (~15 LOC 改动)
  - `tests/test_nt_risk_engine.py`: 更新 `test_fingerprint_is_stable_and_hex` +
    `test_dispatcher_forwards_real_order_denied` 断言 (~20 LOC 改动)

### Track 6 — GC-safety invariant test 3 module (扩展 + 补代码 fix)

- **问题**:
  1. `nt_risk_engine.py:166,217,229` 的 `_pending: set` GC-safe 已在
  2. `nautilus_host.py:146,388` 的 `_cleanup_tasks: set` GC-safe 已在 (**注意: 与 #1 属性名
     不同**, 是同族模式的两个独立实例, drift #5 修正)
  3. `nats_client.py:315` `asyncio.create_task(self._drain_wal(), name="arx-wal-drain")`
     **未被任何强引用容器持有** → 与 `_pending` / `_cleanup_tasks` 同族失败家族的**唯一漏点**
- **决策**: skeleton "invariant test optional" 升级为 **in-scope**:
  1. `nats_client.py` 加 `self._wal_drain_task = asyncio.create_task(...)` 保留强引用
     (~1 行代码 fix)
  2. `tests/test_gc_safety_invariant.py` 覆盖 3 module (**按各自真实属性名分别覆盖**,
     drift #5): `nt_risk_engine._pending` / `nautilus_host._cleanup_tasks` /
     `nats_client._wal_drain_task`
- **交付**:
  - `src/arx_runner/nats_client.py`: 加 `self._wal_drain_task` 实例属性 (~1 行)
  - `tests/test_gc_safety_invariant.py` (新, ~80 LOC, 3 test 覆盖 3 module)

### (removed) Track 4 — telemetry 桥测试脚手架

Plan 00b close-out (`305128c`, 2026-07-08) 已让 `_attach_observability()` 真调
`NtTelemetryBridge(actor=actor).bootstrap(msgbus)` + `NtRiskEngineBridge.bootstrap(...)`,
Track 4 需求消失。

## Historical lessons 强制引用

- **lesson #14 / #30 / #33 / #33b (Foundation Scan 四维方法论)**: evidence-scout 已按四维
  完成深化, drafter 复用其结论不重复扫
- **lesson #17 (happy-path ≠ failure-mode)**: 每 Track 加失败模式覆盖契约表 (§失败模式段)
- **lesson #22 / #28 (多层 fail-fast + 独立可测)**: Track 2 集成 test 用假 `_CapabilityLessHost`
  驱动 `handle_spec` 层, 证实 gate 层 → reconciler 包装层的降级信号不丢失 (每层独立可测)
- **lesson #25 (反 fabricated close-out)**: 契约表点名的 `test_*` 函数名, close-out 前
  必 `grep -rn 'def test_X' tests/` 实证真存在, 新建 test 明确标 "新建"
- **lesson #26 (boundary constant)**: `--use-nt-host` × `spec.trading_mode` 6 组合 matrix
  是 boundary constant 空间, 一次定死 matrix
- **lesson #33b (影响面维多轮迭代)**: evidence-scout 3 轮迭代抓出 4 latent 候选 (C/D +
  Track 1 覆盖复核 + Track 6 nats_client gap)
- **lesson #37 (spawner 元层实证)**: drafter 已按 evidence-scout 具体 file:line 落地引用,
  不凭 skeleton 伪代码推理
- **lesson #40 (close-out 声明精确化)**: 红线 gate 满足度表按 code_coverage / runtime_wire /
  defer_status / follow_up_plan_ref 四列分, 不承袭红线名当兑现声明

## 目标 (Goal)

- **Track 1**: NT host credential `__dict__` recursive walk invariant test 落地
  (invariant #1/#3 交叉引用已有测试)
- **Track 2**: undeclared host capability 集成 test 加固到 `handle_spec` 层, 断言
  `phase=degraded` + structlog 双层 (不断言 `FailureEvent.reason_code`)
- **Track 3**: `--use-nt-host` × `spec.trading_mode` 6 组合 matrix 补齐 (增量 4 cell)
- **Track 5**: pre-trade reject correlation handle 加 `client_order_id` 参与 hash
  (**不追求 tamper-evidence**), 不 bump wire schema
- **Track 6**: `nats_client.py` 补 `self._wal_drain_task` 强引用 + GC-safety invariant test
  3 module 覆盖

## Task List

### T1: Credential lifecycle recursive dict walk invariant

**Task 1** [T1]: `tests/test_credential_lifecycle.py` (新) — invariant #2 递归 walk

- 用真实 `_nt_binance_venue.build_data_client_config()` 构造 credential-loaded
  `BinanceDataClientConfig(api_key="SENSITIVE_KEY_XYZ", api_secret="SENSITIVE_SECRET_ABC")`,
  经 `TradingNodeConfig` 存入 `host._active_nodes[spec_id] = (node, task)`
- 定义辅助 `_walk_dict(obj, depth=5)`: 递归遍历 `node.__dict__` (含 list/dict/tuple 展开)
  到深度 5, 收集所有 str 型 leaf
- 断言: `"SENSITIVE_KEY_XYZ"` / `"SENSITIVE_SECRET_ABC"` 不出现在递归 walk 结果 (若出现即
  invariant #2 违反, 红线 0.1 深化 gap)
- **docstring 交叉引用**: `invariant #1 (repr) 已由 test_nt_trading_node_host.py:240 覆盖`
  + `invariant #3 (structlog) 已由 test_nt_trading_node_host.py:301 覆盖; 本文件只补 #2`
- **LOC 预估**: ~50 (含 fixture + `_walk_dict` util + 1 test 主体)

### T2: Undeclared capability traceability at reconciler level

**Task 2** [T2]: `tests/test_g6_gate_capability_integration.py` (新) — handle_spec 层集成

- 定义 `_CapabilityLessHost` (无 `supports_live` / `supports_venue` 方法, 参照
  `test_g6_gate_capability_e2e.py:90 _CapabilityLessHost` 模式)
- 用 `DeploymentReconciler.handle_spec()` (非 `_apply_spec` / `_check_g6_gate` 单层) 驱动 +
  live `DeploymentSpec`
- 断言 (按范围降级决策):
  1. `handle_spec` 返回不抛出 (broad `except Exception` `deployment_reconciler.py:316-337`
     故意吞异常, 红线 0.3 式设计)
  2. `_report_status` mock 被调用, 参数 `phase="degraded"`, `health="unhealthy"`
  3. `caplog` (或 structlog capture) 命中事件名 `g6_gate_live_capability_denied` +
     `deployment_reconcile_failed`
- **不断言**: `FailureEvent` / `reason_code` 字段 (evidence-scout 候选 C 实证不存在)
- **LOC 预估**: ~80

**Task 3** [T2]: 更新 `docs/design/reconcile.md` + `docs/domain.md` (spec 层同步, F-AUTH-2 fix)

- (a) `docs/design/reconcile.md`: 新增 "Undeclared capability traceability" 段, 明确
  "结构化拒绝信号走 `DeploymentStatus` phase=degraded + 双层 structlog 事件名
  (`g6_gate_live_capability_denied` + `deployment_reconcile_failed`), **而非独立的
  `FailureEvent`**; `FailureEvent` first-class 概念在 `docs/domain.md:153` 有设计但
  `src/arx_runner/` 未实现, 属独立功能面 (follow-up `05-failure-event-first-class.md`
  候选)"; 引用 `deployment_reconciler.py:79-88` + `:318-324` file:line 锚点
- (b) `docs/domain.md`: `:145-153` FailureEvent 表格加一行 "**实现状态**: `src/arx_runner/`
  未 first-class 实现, `_report_status()` `DeploymentStatus` payload 无 `reason_code`
  字段; 详见 `docs/design/reconcile.md` §Undeclared capability traceability + Plan 05
  candidate" (spec 层与 module design 层同步, 避免独立 clone 场景外部审计员误以为
  reason_code 已实现)
- **LOC 预估**: (a) ~30 + (b) ~2 = ~32

### T3: `--use-nt-host` × `spec.trading_mode` matrix 补齐

**Task 4** [T3]: `tests/test_host_mode_matrix.py` (新) — 参数化补 4 cell

- pytest `@pytest.mark.parametrize` 3-tuple `(mode, host_factory, expected_phase)`:
  - `("sandbox", NoopHost, "healthy")` — stub 静默接受
  - `("sandbox", NtTradingNodeHost, "healthy")` — 真跑 sandbox (mock NT node)
  - `("testnet", NoopHost, "healthy")` — G6 gate 非 live 直接 return, stub 静默接受
  - `("testnet", NtTradingNodeHost, "healthy")` — 真跑 testnet (mock NT node)
- 每 cell 断言: `handle_spec` 完成 + `_report_status` 参数 `phase=expected_phase`
- **docstring 交叉引用**: `live×NoopHost 已由 test_g6_gate.py:111 覆盖;
  live×NtTradingNodeHost 已由 test_g6_gate.py:131 覆盖; 本文件补剩余 4 cell`
- **LOC 预估**: ~60

**Task 5** [T3]: 更新 `docs/design/nautilus_host.md` — 新增 "Host mode × trading_mode matrix" 段

- 表格列出 6 cell 期望行为 + 每格 test 位置 (`test_g6_gate.py:111/131` 引用 + 本 plan
  新建的 4 cell 引用)
- **LOC 预估**: ~20 (docs 表格 + 说明)

### T5: Pre-trade reject correlation handle 精度提升

**Task 6** [T5]: `src/arx_runner/nt_risk_engine.py` — `order_fingerprint()` 签名加
`client_order_id`

- 现签名 (`nt_risk_engine.py:122`): `def order_fingerprint(symbol: str, side: str,
  quantity: str, price: str, ts_seconds: int) -> str`
- 新签名: 加 `client_order_id: str` 参数 (位置在 symbol 之后 side 之前, 或末尾, 按顺序对齐
  SHA-256 输入串 `symbol|client_order_id|side|qty|price|ts_seconds`)
- docstring 更新: 明确写 "correlation handle 精度提升: `client_order_id` (NT `OrderDenied`
  真实携带的稳定字段, 见 `test_nt_risk_engine.py:203 ClientOrderId('O-1')`) 参与 hash
  提升唯一性; **仍然是 correlation handle, 非 tamper-evidence anchor** — 后者仍属云端
  audit chain HMAC (governance), custos non-custodial 承重墙不实现"
- **LOC 预估**: ~10 (签名 + docstring 修改)

**Task 7** [T5]: `src/arx_runner/nt_risk_engine.py` — `on_order_denied()` 调用点更新

- `nt_risk_engine.py:277` 现调用: `fingerprint = order_fingerprint(symbol, side, quantity,
  price, ts_seconds)`
- 新调用: 加 `client_order_id = str(getattr(denied, "client_order_id", "") or "")` (与 line
  254-275 的 getattr 模式一致, 已知永久缺失时降级) + 参数传入
  `order_fingerprint(..., client_order_id=client_order_id, ...)`
- **LOC 预估**: ~5

**Task 8** [T5]: `tests/test_nt_risk_engine.py` — 更新 test

- 更新 `test_fingerprint_is_stable_and_hex` (`test_nt_risk_engine.py:269`):
  加 `client_order_id` 参数 + 断言 hash 值随 `client_order_id` 改变
- 更新 `test_dispatcher_forwards_real_order_denied` (`test_nt_risk_engine.py:180`):
  确认真 NT `OrderDenied(client_order_id=ClientOrderId("O-1"))` 驱动路径 fingerprint
  确实纳入 `"O-1"` (可用 pre-compute expected fingerprint 对比, 或断言
  `"O-1"` 参与 hash 计算的 side-effect)
- **LOC 预估**: ~20

### T6: GC-safety invariant test 3 module

**Task 9** [T6]: `src/arx_runner/nats_client.py:315` — 补 `self._wal_drain_task` 强引用

- 现代码: `asyncio.create_task(self._drain_wal(), name="arx-wal-drain")` (未 assign)
- 新代码: `self._wal_drain_task = asyncio.create_task(self._drain_wal(),
  name="arx-wal-drain")`
- 若需在 `close()` 或 shutdown 阶段清理: 补 `if self._wal_drain_task is not None:
  self._wal_drain_task.cancel(); await self._wal_drain_task` (evaluate 是否触发实际 cleanup
  路径, 保守起见先只加强引用)
- **LOC 预估**: ~1-3

**Task 10** [T6]: `tests/test_gc_safety_invariant.py` (新) — 3 module 覆盖

- Test A: `nt_risk_engine._pending` invariant — schedule fire-and-forget task, 断言
  `assert task in engine._pending` (in-flight), await task 完成后
  `assert task not in engine._pending` (discard callback)
- Test B: `nautilus_host._cleanup_tasks` invariant — 同上, 用真实 `_on_node_task_done` 触发
  路径 (或直接 add task 到 `host._cleanup_tasks`), 断言 in-flight / after 语义
- Test C: `nats_client._wal_drain_task` invariant — 连 NATS mock, 断言
  `client._wal_drain_task is not None` (Task 9 补完后), 且 task 未被 GC (强引用保留)
- **LOC 预估**: ~80

### Orphan: 权威文档 drift 订正

**Task 11** [Drift]: `docs/design/nautilus_host.md:79-80` 订正 + 加 "Credential lifecycle
invariants" 段

- **订正 Drift #1**: 79-80 行 "当前只本地 structlog 可观测" 描述已过时 (Plan 00b close-out
  `305128c` 已让 telemetry 桥落地), 改为 "Plan 00b (`305128c`, 2026-07-08) close-out 后
  telemetry 桥已落地, testnet / live 真跑 fill / `OrderDenied` 通过 `_attach_observability()`
  上报云端"
- **新增段**: "Credential lifecycle invariants" — 明确列 invariant #1 (repr) / #2 (dict
  recursive walk) / #3 (structlog processor) 三层, 引用 test 位置
  (`test_nt_trading_node_host.py:240/301` + `test_credential_lifecycle.py::test_node_dict_recursive_no_credential`)
- **新增段**: "Pre-trade reject correlation handle" — 明确写 fingerprint 是 correlation
  handle 不是 tamper-evidence, 真防篡改在云端 audit chain HMAC (governance crate)
- **LOC 预估**: ~50 (docs 3 段)

## 失败模式覆盖契约表 (lesson #17)

| # | 失败模式 | 触发点 | 测试文件:函数 | reason_code / invariant |
|---|---------|--------|--------------|-------------------------|
| F1 | credential leak in `node.__dict__` recursive walk (深度 5) | T1 Task 1 | `test_credential_lifecycle.py::test_node_dict_recursive_no_credential` (**新建**) | invariant #2 (red line 0.1 深化) |
| F2 | credential leak in `repr(node)` | 已有 | `test_nt_trading_node_host.py::test_deploy_does_not_retain_credential` (**已存在, grep 实证 line:240**) | invariant #1 (交叉引用, 不重复) |
| F3 | credential leak in structlog `_sanitize_exception` output | 已有 | `test_nt_trading_node_host.py::test_exception_log_redacts_credential_material` (**已存在, grep 实证 line:301**) | invariant #3 (交叉引用, 不重复) |
| F4 | undeclared host capability → `handle_spec` 层降级信号 | T2 Task 2 | `test_g6_gate_capability_integration.py::test_undeclared_host_at_reconciler_layer_degrades` (**新建**) | `phase=degraded` + structlog `g6_gate_live_capability_denied` + `deployment_reconcile_failed` (**不断言** `FailureEvent.reason_code`) |
| F5 | matrix cell sandbox×NoopHost | T3 Task 4 | `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NoopHost]` (**新建, parametrize**) | stub 静默接受, `phase=healthy` |
| F6 | matrix cell sandbox×NtTradingNodeHost | T3 Task 4 | `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NtTradingNodeHost]` (**新建, parametrize**) | 真跑 sandbox, `phase=healthy` |
| F7 | matrix cell testnet×NoopHost | T3 Task 4 | `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NoopHost]` (**新建, parametrize**) | G6 gate 非 live 直接 return, `phase=healthy` |
| F8 | matrix cell testnet×NtTradingNodeHost | T3 Task 4 | `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NtTradingNodeHost]` (**新建, parametrize**) | 真跑 testnet, `phase=healthy` |
| F9 | matrix cell live×NoopHost | 已有 | `test_g6_gate.py::test_g6_gate_rejects_live_noophost` (**已存在, grep 实证 line:111**) | G6 gate 层 1 rejected (交叉引用) |
| F10 | matrix cell live×NtTradingNodeHost | 已有 | `test_g6_gate.py::test_g6_gate_allows_live_nt_host` (**已存在, grep 实证 line:131**) | G6 gate 4 层 + approved_by 校验 (交叉引用) |
| F11 | fingerprint 相关性句柄 client_order_id 参与 hash | T5 Task 8 | `test_nt_risk_engine.py::test_fingerprint_is_stable_and_hex` (**修改扩参**) + `test_dispatcher_forwards_real_order_denied` (**修改断言**) | fingerprint 随 `client_order_id` 变化 |
| F12 | `_pending` GC-safety invariant (nt_risk_engine) | T6 Task 10 | `test_gc_safety_invariant.py::test_nt_risk_engine_pending_discards_after_await` (**新建**) | in-flight ⇒ `task in _pending`; done ⇒ `task not in _pending` |
| F13 | `_cleanup_tasks` GC-safety invariant (nautilus_host) | T6 Task 10 | `test_gc_safety_invariant.py::test_nautilus_host_cleanup_tasks_discards_after_await` (**新建**) | 同 F12, 但属性名 `_cleanup_tasks` (drift #5 修正) |
| F14 | `_wal_drain_task` GC-safety invariant (nats_client) | T6 Task 10 (需 Task 9 补 fix) | `test_gc_safety_invariant.py::test_nats_client_wal_drain_task_strong_referenced` (**新建**) | `client._wal_drain_task` 非 None, 强引用保留 |

**契约表 grep 实存前置** (lesson #25, codex L1 MED fix 精细化):

14 F **contract checks** (非 14 个独立 `def test_*` 函数; codex L1 finding 1 修正: pytest 参数化 case 与修改现有测试不宜按 "def test_" grep 计数):

- **已存在交叉引用** (F2/F3/F9/F10): 4 个 `def test_*` 已 evidence-scout + drafter 二次 grep 实证 (`test_nt_trading_node_host.py:240/301`, `test_g6_gate.py:111/131`), close-out 沿用 grep 断言
- **修改现有测试** (F11 覆盖 2 处): `test_nt_risk_engine.py:180 test_dispatcher_forwards_real_order_denied` + `:269 test_fingerprint_is_stable_and_hex` (grep 实证已存在), Phase 3 Task 8 扩参/改断言, close-out 用 `git diff` 校验 (非 grep 新增)
- **新建独立 def test_*** (F1/F4/F12/F13/F14): 5 个新测试函数, close-out 前必 `grep -rn 'def <test_name>' tests/` 实存实证
- **新建 parametrize node id** (F5-F8): 1 个测试函数 `test_mode_host_matrix` 承载 4 parametrize case, close-out 前用 `pytest --collect-only tests/test_host_mode_matrix.py` 验证 4 node id 齐 (grep `def test_*` 只命中 1 个函数, 属预期非 fabricated close-out)

**总数校验**: 4 已存在 + 2 修改 (F11) + 5 新建 def + 1 新建 parametrize (承载 4 case) = 14 F contract checks. 6 独立 def test_* 新增 (`test_node_dict_recursive_no_credential` + `test_undeclared_host_at_reconciler_layer_degrades` + `test_mode_host_matrix` + 3 GC-safety).

## File Inventory

| 文件 | 类型 | 决定 (含 grep 现状锚点) |
|------|------|------------------------|
| `tests/test_credential_lifecycle.py` | 新建 | T1 Task 1: invariant #2 (`_walk_dict` util + 1 test, ~50 LOC); invariant #1/#3 docstring 交叉引用 `test_nt_trading_node_host.py:240/301` |
| `tests/test_g6_gate_capability_integration.py` | 新建 | T2 Task 2: handle_spec 层集成 (~80 LOC); 参照 `test_g6_gate_capability_e2e.py:90 _CapabilityLessHost` 模式; **不断言** FailureEvent.reason_code |
| `tests/test_host_mode_matrix.py` | 新建 | T3 Task 4: 参数化补 4 cell (`sandbox×{Noop,Nt}` + `testnet×{Noop,Nt}`, ~60 LOC); 已覆盖 live×{Noop,Nt} 引用 `test_g6_gate.py:111/131` |
| `tests/test_gc_safety_invariant.py` | 新建 | T6 Task 10: 3 test 覆盖 3 module (~80 LOC); 分别引用 `nt_risk_engine._pending` / `nautilus_host._cleanup_tasks` / `nats_client._wal_drain_task` (drift #5 各自属性名) |
| `src/arx_runner/nt_risk_engine.py` | 改 | T5 Task 6+7: `order_fingerprint()` 签名 (`:122`) 加 `client_order_id` + `on_order_denied()` 调用点 (`:277`) 更新 (~15 LOC) |
| `src/arx_runner/nats_client.py` | 改 | T6 Task 9: `:315` `asyncio.create_task(self._drain_wal(), name="arx-wal-drain")` 加 `self._wal_drain_task = ...` 强引用 (~1-3 LOC) |
| `tests/test_nt_risk_engine.py` | 改 | T5 Task 8: 更新 `test_fingerprint_is_stable_and_hex` (`:269`) + `test_dispatcher_forwards_real_order_denied` (`:180`) 断言 (~20 LOC) |
| `docs/design/nautilus_host.md` | 改 | T3 Task 5 + Orphan Task 11: 订正 `:79-80` drift + 新增 "Credential lifecycle invariants" / "Host mode × trading_mode matrix" / "Pre-trade reject correlation handle" 3 段 (~70 LOC) |
| `docs/design/reconcile.md` | 改 | T2 Task 3: 新增 "Undeclared capability traceability" 段, 明确 `phase=degraded` + structlog 双层 (非 FailureEvent) (~30 LOC) |
| `docs/domain.md` | 改 | T2 Task 3 顺手 (F-AUTH-2 fix): `:145-153` FailureEvent 表格加一行 "**实现状态**: `src/arx_runner/` 未实现 first-class, `_report_status()` `DeploymentStatus` payload 无 `reason_code` 字段; 详见 `docs/design/reconcile.md` §Undeclared capability traceability + Plan 05 candidate" (~2 LOC, spec 层与 module design 层同步) |

## 验收清单

- [ ] T1 (Task 1): `test_credential_lifecycle.py::test_node_dict_recursive_no_credential` 全绿, credential material 不出现在深度 5 递归 walk 结果
- [ ] T2 (Task 2+3): `test_g6_gate_capability_integration.py` 全绿, `handle_spec` 层降级信号 (`phase=degraded` + structlog 双层) 断言通过; `docs/design/reconcile.md` "Undeclared capability traceability" 段落地
- [ ] T3 (Task 4+5): `test_host_mode_matrix.py` 4 cell 参数化全绿; `docs/design/nautilus_host.md` "Host mode × trading_mode matrix" 段落地
- [ ] T5 (Task 6+7+8): `order_fingerprint()` 签名扩加 `client_order_id`; `on_order_denied()` 调用点更新; `test_fingerprint_is_stable_and_hex` + `test_dispatcher_forwards_real_order_denied` 更新后全绿; **envelope schema 不 bump** 验证 (`grep -n 'payload_schema_version' tests/test_wire_shapes.py` 保持 =1)
- [ ] T6 (Task 9+10): `nats_client._wal_drain_task` 强引用落地; `test_gc_safety_invariant.py` 3 test 全绿
- [ ] Orphan (Task 11): `docs/design/nautilus_host.md:79-80` drift 订正 (删 "当前只本地 structlog 可观测"); "Credential lifecycle invariants" + "Pre-trade reject correlation handle" 2 段落地
- [ ] `make verify` 全绿 (含 fmt-check + lint + baseline test)
- [ ] Non-Custodial 4 红线 grep 全绿 (见 §红线 gate 满足度表)
- [ ] 契约表 (F1-F14) 中标 "新建" 的 10 个 `test_*` 函数 `grep -rn 'def test_X' tests/` 实存实证 (lesson #25)

## 红线 gate 满足度表 (lesson #40)

| 红线 | code_coverage | runtime_wire | defer_status | follow_up_plan_ref |
|------|--------------|--------------|--------------|--------------------|
| 0.1 Key / KEK 永不出进程 | T1 Task 1 加 invariant #2 (`__dict__` recursive walk) 覆盖 code + 已有 `test_nt_trading_node_host.py:240/301` 覆盖 invariant #1/#3 | runtime 已由 Plan 00a `_sanitize_exception()` + credential vault `_verify_permission_scope()` 兑现; 本 plan 不改 runtime path, 只扩 invariant test 覆盖面 | 无 defer | — |
| 0.2 G6 host gate 不绕过 | T2 Task 2 加 `handle_spec` 层集成 test + T3 Task 4 加 4 matrix cell; 已有 `test_g6_gate.py:111/131` + `test_g6_gate_capability_e2e.py:104` 等覆盖 gate 单层 | runtime 已由 Plan 00c `_check_g6_gate()` 4 层 fail-fast 兑现; 本 plan 加集成层与 matrix 深化覆盖, 不改 runtime | 无 defer (Track 2 描述范围降级 — `FailureEvent.reason_code` 断言撤除是**契约认知修正**, 非 defer) | Plan 05 (candidate): FailureEvent first-class 实现 |
| 0.3 Reconcile 失联 ≠ 停止 | Plan 03 不 touch, 保持 Plan 00a/00c 状态 | runtime 不动 (T2 `handle_spec` broad `except` 转 `phase=degraded` 是本红线的自然延伸) | 无 defer | — |
| 0.4 Money math Decimal + str wire | T5 Task 6 `order_fingerprint()` 加 `client_order_id` 是 str 字段 (非 Decimal / float), hash 输入路径已 str-normalized (`nt_risk_engine.py:273-275 str(getattr(...) or "")`); T5 Task 8 test 沿用现有 Decimal 断言路径 | runtime `order_fingerprint()` 调用点 (`nt_risk_engine.py:277`) 全部 str 参数, 不 touch Decimal 路径 | 无 defer | — |

## 附录 A: 6 组合 matrix 期望表

| trading_mode | host | expected | existing_coverage / 本 plan 新建 |
|--------------|------|----------|---------------------------------|
| sandbox | NoopHost | stub 静默接受 (`nautilus_host_deploy_stub` log), `phase=healthy` | **新建 T3 Task 4** `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NoopHost]` |
| sandbox | NtTradingNodeHost | 真跑 sandbox (`SandboxLiveExecClientFactory`), `phase=healthy` | **新建 T3 Task 4** `test_host_mode_matrix.py::test_mode_host_matrix[sandbox-NtTradingNodeHost]` |
| testnet | NoopHost | stub 静默接受 (G6 gate 非 live 直接 return), `phase=healthy` | **新建 T3 Task 4** `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NoopHost]` |
| testnet | NtTradingNodeHost | 真跑 testnet (`BinanceLiveExecClientFactory` + `BinanceEnvironment.TESTNET`), `phase=healthy` | **新建 T3 Task 4** `test_host_mode_matrix.py::test_mode_host_matrix[testnet-NtTradingNodeHost]` |
| live | NoopHost | G6 gate 层 1 rejected (`g6_gate_live_capability_denied`), `phase=degraded` | **已存在** `test_g6_gate.py:111 test_g6_gate_rejects_live_noophost` |
| live | NtTradingNodeHost | G6 gate 4 层 + approved_by ≥ 2 校验, 全通过则真跑 live, `phase=healthy` | **已存在** `test_g6_gate.py:131 test_g6_gate_allows_live_nt_host` |

## 偏离与改进日志 (Deviation Log)

(执行阶段填写, 预留 `DEV-03-*` 空位)

**分级模板** (按 `.claude/rules/deviation-protocol.md`, intra L2 fix):

```markdown
### DEV-03-<slug>
- **等级**: LOW / MED / HIGH
- **原因**: <为什么需要偏离>
- **影响**: <受影响的模块和文件>
- **决定**: <最终采取的方案>
- **更新的文档**: <列出已更新的权威文档 或 "无">
```

**candidate slots** (Phase 2 精细化阶段预填, 执行阶段填实):

- `DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC` (LOW 预估, **workspace-scope only
  advisory** — 独立 clone 场景不可见, F-AUTH-3 fix): crucible-rust 侧
  `pre_trade_service.rs:82-91` docstring "the same canonical recipe" 措辞是否与 custos
  `nt_risk_engine.py:125` 同步。仅在 workspace 场景内跨仓协同, custos 独立仓 clone 后此
  follow-up 不适用 (independent audit 只看 custos 侧 docstring, 已明确 "correlation
  handle, not tamper-evidence anchor")
- `DEV-03-WAL-TASK-GC-GAP` (candidate slot): 若 Task 9 shutdown cleanup 路径评估发现更多
  边界情况 (如 `close()` 时 cancel + await 的语义), 独立记录
- `DEV-03-FAILUREEVENT-DEFER-CLARIFICATION` (candidate slot, LOW 预估):
  Track 2 `FailureEvent.reason_code` 断言撤除的完整依据 (evidence-scout 候选 C 实证
  `FailureEvent` 在 `src/arx_runner/` 零实现, `_report_status()` `DeploymentStatus` payload
  无 `reason_code` 字段) 归档到本条。**性质**: 契约认知修正 (skeleton 起草时误假设概念已
  first-class), 非 defer; drafter 已在 Task 3 加 `docs/design/reconcile.md` "Undeclared
  capability traceability" 段澄清; 完整 first-class 实现推 Plan 05 candidate

## 完成报告 (Close-out Report)

(执行完成填写, 按 `.claude/rules/progress-management.md` 模板)

```
- **完成日期**: {YYYY-MM-DD}
- **总 Task 数**: 11
- **偏离数**: {N} (详见偏离日志)
- **验证结果**: 全部通过 / 部分通过
- **实施 commit 范围**: {first_sha}..{last_sha}
- **契约影响**: docs/design/nautilus_host.md (3 段新增 + Drift #1 订正) +
                docs/design/reconcile.md (1 段新增)
- **红线守护**: Non-Custodial 4 红线全数守住 (grep 记录, 见 §验收清单红线专项)
- **失败模式覆盖**: F1/F4-F8/F11-F14 (10 个新增 test 函数), F2/F3/F9/F10 (4 个已存在交叉引用)
- **遗留项**: FailureEvent first-class 实现 (Plan 05 candidate) + crucible-rust 侧 docstring
              同步 (若 DEV-03-T5-CANONICAL-RECIPE-CROSS-REPO-DOC-SYNC 触发)
```

## 下一步 (Next)

Plan 03 close-out 后:
- 硬化面基本完备; 后续 plan 候选:
  - **Plan 05 candidate**: `FailureEvent` first-class 实现 (`docs/domain.md:153` 已有设计,
    `src/arx_runner/` 未实现)
  - Plan 00c §下一步继承: OKX venue / `arx_runner`→`custos_runner` rename (boundary
    constant rename fanout, lesson #35) / 签名 release pipeline / ExecutionEngineAdapter
    抽象补全 / 多引擎 flavour
