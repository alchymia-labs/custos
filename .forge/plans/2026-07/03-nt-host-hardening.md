# 03 - NT host hardening (credential lifecycle test suite + follow-up 硬化)

> **Status**: 🔲 Todo (candidate skeleton; 未起 executor, 记录 defer 项)
> **Created**: 2026-07-08 (Plan 00c close-out 追加, DEV-00c-DEP-SKIP-CEO-OVERRIDE HIGH triage 决定 = new-plan)
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: candidate — 待需要时用 `/forge:plan-team` 精细化后 `/forge:execute`
> **Depends on**: Plan 00a ✅ + Plan 00c ✅ (NT host 真起, capability 契约面已就位)
> **Blocks**: (无硬 block, 属安全深化)
> **multi_session_scope**: false (预估 3-4 task, ~200 LOC test + docs 少量)

## 起源 (Origin)

本 plan candidate 起源为两条独立 defer 项汇合:

1. **来自 Plan 00a codex peer review F1 (defer 项)** — `.forge/marker/00a-runner.complete.json`
   记 F1_in_process_credential_memory: "deferred (not a violation; NT<->exchange comms
   design necessity, red line limits I/O boundary) -> Plan 03 candidate (credential
   lifecycle test suite)"
2. **来自 Plan 00c HIGH DEVIATION triage 决定 (2026-07-08)** — CEO override 4 件套齐
   accept 后 CEO 选 `new-plan` 路径, 让 Plan 03 candidate 承载"Plan 00c 未覆盖的 NT host
   硬化项", 记录本 plan (非立即执行)

## 上下文 (Context)

Plan 00a + 00c 落地后 NT host 已就位:
- `NtTradingNodeHost` 真起 sandbox / testnet / live 三档 (via `spec.trading_mode` dispatch)
- `NautilusHostProtocol` 加 `supports_live` + `supports_venue` capability 契约面
- G6 gate 4 层 fail-fast + relaxed-double 独立可测
- credential vault 已守 `permission_scope == "trade_no_withdraw"`, gate 侧 double-check

但仍有几处**深化空间**属"非红线违反, 但值得加固":

### Track 1: Credential lifecycle test suite (来自 00a F1 defer)

- **问题**: `NtTradingNodeHost._active_nodes[spec_id] = (node, task)` 通过 `node` 引用
  间接持有 credential (data_client_config + exec_client_config 的 api_key/api_secret
  在 node 内存里)。这**不违反红线 0.1** (红线原文限 log/publish/send I/O 边界; in-process
  内存持有是 NT ↔ exchange 通信的设计必要), 但**没有 invariant test**。
- **需求**: 加 test suite 验证三层 invariant:
  1. `repr(node)` / `str(node)` 不含 raw credential material
  2. `node.__dict__` recursive dump (深度 5) 不含 raw credential (dict comprehension +
     递归 walk + credential prefix match)
  3. `structlog` processor output (call `_sanitize_exception` on exceptions containing
     credential-like messages) 不 leak
- **交付**: `tests/test_credential_lifecycle.py` (新, ~120 LOC), 3 test 覆盖三层

### Track 2: Undeclared host capability test (加固 Plan 00c F2)

- Plan 00c F2 fix `_host_capability = getattr(host, "supports_live", lambda: False)()`
  已在 (`src/arx_runner/deployment_reconciler.py:64`); 但只有 unit-level test 覆盖 (test
  double 无 supports_live method)。
- **深化**: 加集成 test 用**假的第三方 host 类** (无 supports_live/supports_venue 方法)
  测跨 gate → reconciler 全链路的 structured RuntimeError 传递 (`g6_gate_live_capability_denied`
  reason 不被吞) + `FailureEvent.reason_code` 命中

### Track 3: `--use-nt-host` + `spec.trading_mode` 组合矩阵 (加固 Plan 00c HOST-WIRING)

- Plan 00c 加 `--use-nt-host` flag 后, sandbox/testnet/live 三 mode × NoopHost/NtTradingNodeHost
  两 host = 6 组合
- 当前 test 覆盖: NoopHost×live rejected / NtTradingNodeHost×live accepted (with all
  layers) / NoopHost 默认 CLI 路径
- **深化**: 补全 6 组合的期望行为 matrix test (skip live×NoopHost 因已覆盖):
  - sandbox × NoopHost = stub 静默接受 (dev 路径)
  - sandbox × NtTradingNodeHost = 真跑 sandbox
  - testnet × NoopHost = stub (G6 gate 非 live 直接 return, stub 静默接受)
  - testnet × NtTradingNodeHost = 真跑 testnet
  - live × NtTradingNodeHost = G6 gate 4 层 + approved_by 校验
  - matrix test 用参数化 pytest 覆盖

### (可选) Track 4: telemetry 桥 (若 Plan 00b 未启动)

- 目前 Plan 00b (telemetry_actor 接 NT MessageBus) 独立存在 🔲 Todo
- 如果 Plan 03 execute 时 00b 还未落地, **可选**加 3 test suite 里的 credential + observation
  层桥接 skeleton, 为 00b 铺路; 但**不重叠 Plan 00b 主实现**, 只补测试脚手架
- 默认: Plan 03 execute 时先看 Plan 00b 状态, 决定是否 optional Track 4

## Historical lessons 强制引用

- **lesson #17 failure-mode coverage**: credential lifecycle 属"隐性红线"覆盖, 需失败模式
  test (credential 出现在 repr / __dict__ / structlog)
- **lesson #22/#28 多层 fail-fast + 独立可测**: capability contract 加集成 test 证实 gate
  层 → reconciler → FailureEvent 端到端 structured reason 传递不被吞
- **lesson #25 反 fabricated close-out**: matrix test 契约表点名 test 必 grep 实存
- **lesson #26 boundary constant**: `--use-nt-host` × `spec.trading_mode` 6 组合矩阵是
  boundary constant 空间, 一次定死 matrix

## 目标 (Goal)

- **Track 1**: NT host credential 三层 invariant test suite 落地
- **Track 2**: undeclared host capability 集成 test 加固
- **Track 3**: `--use-nt-host` × `spec.trading_mode` 6 组合 matrix test 全覆盖
- **(可选) Track 4**: telemetry 桥测试脚手架 (若 Plan 00b 未启动)

## Task List (skeleton, 精细化前占位)

**Task 1**: `tests/test_credential_lifecycle.py` 三层 invariant test suite

- 3 test: repr / dict recursive dump / structlog processor output
- 用 mock TradingNode + credential dict {"api_key": "SENSITIVE_KEY_XYZ", "api_secret":
  "SENSITIVE_SECRET_ABC", "permission_scope": "trade_no_withdraw"}
- 深度 recursive walk 用 `_walk_dict` 辅助 (test util)

**Task 2**: `tests/test_g6_gate_capability_integration.py` undeclared capability 集成

- 假第三方 host 类 无 supports_live/supports_venue 方法
- gate 层 → reconciler → FailureEvent 全链路 structured RuntimeError 传递验证

**Task 3**: `tests/test_host_mode_matrix.py` 6 组合 matrix test

- pytest 参数化: (mode, host, expected) triples
- 覆盖 Table 附录 A

**Task 4** (可选): 若 Plan 00b 未启动, 加 telemetry 桥测试脚手架 (由 00b executor 决定是否接手)

## 失败模式覆盖契约表 (lesson #17)

| 失败模式 | 触发点 | 测试文件:函数 | reason_code / invariant |
|---|---|---|---|
| credential leak in node.repr | Track 1 | `test_credential_lifecycle.py::test_node_repr_no_credential` | invariant |
| credential leak in node.__dict__ recursive | Track 1 | `test_credential_lifecycle.py::test_node_dict_recursive_no_credential` | invariant |
| credential leak in structlog processor | Track 1 | `test_credential_lifecycle.py::test_structlog_processor_no_credential_leak` | invariant |
| undeclared host capability → AttributeError (regression) | Track 2 | `test_g6_gate_capability_integration.py::test_undeclared_host_structured_reject` | reason=`g6_gate_live_capability_denied` |
| matrix cell 未覆盖 | Track 3 | `test_host_mode_matrix.py::test_mode_host_matrix` (parametrize) | expected behavior per cell |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `tests/test_credential_lifecycle.py` | 新建 | Track 1 三层 invariant |
| `tests/test_g6_gate_capability_integration.py` | 新建 | Track 2 集成 |
| `tests/test_host_mode_matrix.py` | 新建 | Track 3 matrix |
| `docs/design/nautilus_host.md` | 改 | 加 §"Credential lifecycle invariants" 段 (Track 1 落地后) |
| `docs/design/reconcile.md` | 改 | 加 undeclared capability 端到端 traceability 段 (Track 2) |

## 验收清单

- [ ] Track 1: 3 test 全 pytest 覆盖 + `make verify` 全绿
- [ ] Track 2: 假第三方 host 集成 test 通过 + FailureEvent reason 命中
- [ ] Track 3: 6 组合 matrix test 参数化全绿
- [ ] `docs/design/nautilus_host.md` + `reconcile.md` 同步 (invariant 段 + traceability)
- [ ] (可选) Track 4: 若 Plan 00b 未启动 → telemetry 桥测试脚手架

## 附录 A: 6 组合 matrix 期望表

| trading_mode | host | expected |
|---|---|---|
| sandbox | NoopHost | stub 静默接受 (`nautilus_host_deploy_stub` log) |
| sandbox | NtTradingNodeHost | 真跑 sandbox (SandboxLiveExecClientFactory) |
| testnet | NoopHost | stub 静默接受 (G6 gate 非 live 直接 return) |
| testnet | NtTradingNodeHost | 真跑 testnet (BinanceLiveExecClientFactory + BinanceEnvironment.TESTNET) |
| live | NoopHost | G6 gate 层 1 rejected (`g6_gate_live_capability_denied`) |
| live | NtTradingNodeHost | G6 gate 4 层 + approved_by ≥ 2 校验, 全通过则真跑 live |

## 偏离与改进日志 (Deviation Log)

(执行阶段填写)

## 完成报告 (Close-out Report)

(执行完成填写)

## 下一步 (Next)

Plan 03 close-out 后:
- 硬化面基本完备; 后续 plan 候选见 Plan 00c §下一步 (OKX venue / arx_runner→custos_runner
  rename / 签名 release pipeline / ExecutionEngineAdapter 抽象补全 / 多引擎 flavour)
