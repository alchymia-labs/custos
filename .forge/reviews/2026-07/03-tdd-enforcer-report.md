# Plan 03 (nt-host-hardening) — TDD Enforcer 报告

> **审查对象**: `main..HEAD` (10 code/docs commits + 1 marker commit), branch `custos/03/runner`
> **审查人**: tdd-enforcer (sonnet)
> **审查方法**: 静态 diff 阅读 + reflog 核查 + **revert-and-run 实证**（把 src 改动临时回退到 impl 变更前状态，重跑相关测试，验证是否真实产生 claim 中所述的 RED 失败，而非仅信任 commit message 叙事）

## D1 — 严格 red→green 顺序（针对 code impl 变更）

### Track 5 (Task 6+7+8, commit `3ca3afb`) — `order_fingerprint()` 签名迁移

**判定**: PASS_WITH_DEVIATION_ACCEPTED（签名迁移例外, 实证支持）

- 用 `git show 3221591:src/arx_runner/nt_risk_engine.py`（Task 6 前一个 commit 的 src 状态）临时替换当前 `nt_risk_engine.py`，保留 `3ca3afb` 改后的 test 不动，重跑 `tests/test_nt_risk_engine.py`：
  - **实测结果**: `test_fingerprint_is_stable_and_hex` 和 `test_dispatcher_forwards_real_order_denied` 均 `TypeError: order_fingerprint() takes 5 positional arguments but 6 were given`，与 commit message 声称的"Task 8 先红 TypeError 6-arg"**精确吻合**。这不是凭空断言, 是可复现的技术事实。
- 结论: DEV-03-TDD-ORDER-CLARIFICATION 对 Track 5 的例外声明（"Task 6/7/8 签名迁移互依赖, 原子合一 commit"）**有实证支撑, 不是编造**。
- **一点观察（非阻塞）**: "单独提交留破损中间态"这一措辞略有夸大——按我的 revert 实验, 若拆成「commit 1: test 先改 6-arg 调用 (RED, TypeError)」→「commit 2: 签名跟进 (GREEN)」, 并不会导致测试收集 (collection) 阶段整体崩溃, 只是那一个 commit 点上部分测试为红. 这本就是标准 TDD 两步提交该有的样子, 谈不上"破损". 团队若倾向于保留可 bisect 的 RED commit, 未来可考虑显式拆分而非原子合一;但当前选择（原子合一 + 偏离日志记录 + 事后可 revert-验证)是**可接受**的工程判断, 不视为违规。

### Track 6 (Task 9+10, commit `2512d74`) — `nats_client.py` WAL-drain 强引用 + 3-module GC-safety test

**判定**: PASS_WITH_DEVIATION_ACCEPTED（实证支持, Test A/B 与 Test C 需分别判定）

- **Test A** (`test_nt_risk_engine_pending_discards_after_await`) / **Test B** (`test_nautilus_host_cleanup_tasks_discards_after_await`): 驱动的 `_pending` / `_cleanup_tasks` 机制经 `git log -S` 核实**均来自 `d76ef81`（Plan 00b squash, 早于本 plan）**, 不是本 commit 新增代码。这两个 test 是对既有行为的**特征化测试 (characterization test)**, 首跑即绿属预期, GREEN-first 合理, 不违反 TDD 铁律（characterization 测试不适用 RED-first 要求, plan 正文与 DEV log 均已明确此区分）。
- **Test C** (`test_nats_client_wal_drain_task_strong_referenced`): 用 `git show 3221591:src/arx_runner/nats_client.py`（Task 9 前一个 commit 的 src 状态, 即无 `_wal_drain_task` field）临时替换当前 `nats_client.py`, 保留 test 不动, 重跑 `tests/test_gc_safety_invariant.py`：
  - **实测结果**: `test_nats_client_wal_drain_task_strong_referenced` 报 `AttributeError: 'ArxNatsClient' object has no attribute '_wal_drain_task'`, 其余 2 test (`Test A`/`Test B`) 通过 (`1 failed, 2 passed`)。与 commit message 声称的"Test C 先红 (AttributeError _wal_drain_task 不存在)"**精确吻合**。
- 结论: Track 6 的三个 test 里, A/B 是合规的 characterization GREEN-first, C 是有实证支撑的 RED→GREEN（签名/属性迁移例外, 与 Track 5 同构, 原子合一理由同样成立）。

## D2 — Task 1 → Task 4 → Task 10 严格 test-first

**判定**: PASS

| Task | 判定依据 |
|------|---------|
| Task 1 (`4559d04`) | test-only commit（无 src 变更）。invariant #2（credential 不出现在 `TradingNodeConfig.__dict__` 递归 walk）由 msgspec `__slots__` **既有属性**保证, 不需要新写 src 逻辑——这是纯 invariant/characterization test, "test 应先 fail" 不适用于此类无对应 impl 变更的用例, 首跑绿属正确预期 |
| Task 1 fix (`23c7a17`) | 同为 test-only 修改（改测试对象从原生 `TradingNode` 换成 `TradingNodeConfig`, 规避 SIGABRT）。DEV-03-CREDENTIAL-TEST-NO-NATIVE-NODE 描述的是真实场景: 首版在 `make verify-nt` 全量套件里遇到 SIGABRT (Error 134, 单跑不复现), 这本身就是一次真实的 RED（崩溃）→ 诊断根因 (NT Rust logging 全局单例二次初始化) → 换测试策略 → GREEN 的过程, 不是"凭空补救" |
| Task 2 (`4f376bc`) | test-only commit, 未触碰 `deployment_reconciler.py`。`git diff --name-only main..HEAD` 确认全 plan 期间 `deployment_reconciler.py` 源码**零改动**——`handle_spec` / `_check_g6_gate` 逻辑是 Plan 00c 遗留的既有实现, Task 2 是在既有 runtime 上加一层集成测试覆盖, 属 characterization test, GREEN-first 合理 |
| Task 4 (`3d11177`) | test-only commit, 同样未触碰 `deployment_reconciler.py` / `nautilus_host.py`。matrix 4 cell 走的都是既有 `handle_spec` + `NoopHost`/`NtTradingNodeHost` 已有实现路径, characterization test, GREEN-first 合理 |
| Task 10 (Test A/B, `2512d74`) | 见 D1 Track 6 — GREEN-first 合理（既有机制的特征化测试） |
| Task 10 (Test C, `2512d74`) | 见 D1 Track 6 — RED-first 有实证支撑 |

## D3 — commit 消息合规（编号纯净）

**判定**: PASS

- Commit message 层面: 9 个 commit message 含 "plan 03 Task N" 措辞——按 lesson #15, commit message 是允许的追踪号载体（非源码注释）, 合规。
- 源码注释层面: `git diff main..HEAD -- 'src/arx_runner/*.py' 'tests/test_*.py'` 全量新增行 grep `Plan 0[0-9]|Task [0-9]+|DEV-03-|lesson #[0-9]+` → **0 命中**。
- 补充核实: 对当前完整代码树（非仅 diff）跑同一 grep pattern, 命中的 13 处全部经 `git blame` / `git log -S` 核实为**其他 plan 遗留**（`d76ef81` Plan 00b / `test_enrollment.py` 提及 "Plan 06 Task 6" / `test_nats_client_telemetry.py`+`test_telemetry_actor.py` 提及 "Plan 04 Task 8" / 多处 "lesson #21"/"lesson #25" 引用），均**不在本 plan 的 diff 范围内**, 不算 Plan 03 违规。

## D4 — 失败模式覆盖契约表 F1-F14 独立性

**判定**: PASS

- **契约表实存实证**（对照 marker `contract_table_grep_verification`）:
  - F1 `test_node_dict_recursive_no_credential` — grep 命中 `tests/test_credential_lifecycle.py:100` ✓
  - F2/F3（cross-ref, 既有）— grep 命中 `tests/test_nt_trading_node_host.py:240`/`:301` ✓
  - F4 `test_undeclared_host_at_reconciler_layer_degrades` — grep 命中 `tests/test_g6_gate_capability_integration.py:81` ✓
  - F5-F8（parametrize）— `pytest --collect-only tests/test_host_mode_matrix.py` 实测 4 node id 齐全 (`sandbox-NoopHost` / `sandbox-NtTradingNodeHost` / `testnet-NoopHost` / `testnet-NtTradingNodeHost`) ✓
  - F9/F10（cross-ref, 既有）— grep 命中 `tests/test_g6_gate.py:111`/`:131` ✓
  - F12/F13/F14 — grep 命中 `tests/test_gc_safety_invariant.py:34`/`:56`/`:74` ✓
  - 全部行号与 marker 声明一致, 无 lesson #25 式"编造测试名"迹象
- **独立性核查**:
  - F1 单函数, 无共享 state
  - F4 独立 `_CapabilityLessHost` fixture, 单函数
  - F5-F8 每个 parametrize case 各自 function-scoped `strategy_dir` (tmp_path), 无 case 间共享 state
  - F12/F13/F14 三个独立函数, 各自构造独立 client/host/bridge 对象, 属性名互不相同（`_pending` / `_cleanup_tasks` / `_wal_drain_task`, drift #5 修正生效, 经 `git log -S` 核实是三个模块各自独立的历史沿革属性, 非同一属性被误伤覆盖）
- **实测跑通**: `uv run pytest tests/ -q --ignore=tests/test_wire_shapes.py` → **214 passed**, 与 marker `test_run_summary.total=214/passed=214` 一致

## Overall Verdict

**APPROVE_WITH_FOLLOW_UPS**

- D1/D2/D3/D4 全部 PASS（含实证验证, 非仅信任叙事）。
- 无 lesson #15 源码注释追踪号命中, 无需 escalation。
- 唯一记录的观察项（非阻塞）: Track 5 的 DEV-03-TDD-ORDER-CLARIFICATION 中"单独提交留破损中间态"措辞略有夸大——按 revert 实证, 拆分 test-first/impl-second 两个 commit 技术上可行且不会导致收集阶段整体崩溃。当前"原子合一 + 偏离日志记录"的做法可接受, 但建议未来签名迁移场景优先尝试拆分为显式 RED commit + GREEN commit, 除非确有收集期崩溃等硬性理由。
