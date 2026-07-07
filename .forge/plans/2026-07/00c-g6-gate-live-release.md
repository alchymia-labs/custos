# 00c - G6 gate 逻辑放宽 (capability-based) + Binance testnet/live 逐级放行 + docker compose e2e

> **Status**: 🔲 Todo (blocked by Plan 00a + 00b close-out)
> **Created**: 2026-07-07
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Plan 00a (NtTradingNodeHost 真起 NT) + Plan 00b (telemetry 桥可观测), 缺一 live 放行都不安全
> **multi_session_scope**: false (5 task, ~500 LOC + docker/example 配置)

## 上下文 (Context)

### 现状 (as-of Plan 00a + 00b close-out)

- `NtTradingNodeHost` 真起 sandbox mode; supertrend 在 sandbox 已跑通 (Plan 00a)
- telemetry_actor + pre_trade_bridge 已上报 fill/position/OrderDenied (Plan 00b)
- G6 gate 当前逻辑 (`deployment_reconciler.py:30-53`): `trading_mode=="live" + isinstance(NoopHost)` → reject. **NtTradingNodeHost + live 组合此时被 gate 放行, 但这是隐式** — 靠 `isinstance` 单点决策, 不是显式 capability 校验

用户价值: 让 supertrend 在 Binance testnet → live 逐级真跑; 完善 G6 gate 逻辑, 从"拒 NoopHost"升级为"承认真 host + 校验 venue capability + 验证 credential scope + 校验 code_hash provenance", 兑现 domain-model §1.2 red-line `trading_mode=live` 时 `code_hash` 必与本地 image sha 匹配。

### 契约证据锚表 (Plan 00b close-out 后 executor 重新 Foundation Scan 实证)

| 引用契约 / 来源 | file:line | 用途 |
|---|---|---|
| G6 gate 现状 | `src/arx_runner/deployment_reconciler.py:30-53` | 本 plan 改造靶子 |
| custos domain-model §1.2 `code_hash` 红线 | `docs/domain.md:103` | live mode `code_hash` 必匹配 local image sha |
| `NautilusHostProtocol` 三方法 | `deployment_reconciler.py:56-63` | 加 capability 方法 (可选, 需 review 是否触发协议 breaking) |
| lesson #23 G5 gate 全局门 | `.claude/rules/historical-lessons.md` #23 | money math 上 live 需 differential coverage — custos 不做 money math, 但对齐精神 |
| lesson #28 复合契约独立可测 | `.claude/rules/historical-lessons.md` #28 | 多层 fail-fast 每层需 relaxed-double test |
| Binance testnet vs live env 区分 | ps `runner.py:745-752` `_get_binance_environment` (`BinanceEnvironment.LIVE/TESTNET/DEMO`) | Plan 00a 引入过 sandbox, 本 plan 加 testnet + live |
| pyproject.toml `nt-runtime` extra | Plan 00a 落地位置 | 本 plan 可能加 e2e testnet 相关 extra |
| docker-compose 参考 | ps `deploy/nautilus/docker-compose.yaml` | custos 的 examples/ 参考此结构但**不带 Redis** (custos v1 无持久化外部依赖) |
| custos README §"Not Included Yet" G6 gate 条 | `README.md:107-108` | close-out 时删除此条 |

### Historical lessons 强制引用

- **lesson #14/#33/#33b Foundation Scan iteration**: Plan 00a + 00b close-out 状态多点变化, executor Foundation Scan 至少 3 轮 (domain-model + reconciler + host + telemetry + 上游 close-out)
- **lesson #17 failure-mode**: live/testnet 场景失败模式指数增加 (Binance auth / 网络分区 / venue 限流 / testnet ↔ live 配置串)
- **lesson #22/#28 多层 fail-fast + 每层独立可测**: G6 gate 改为 capability-based 后必须 relaxed-double test 证明每层 (host capability / credential scope / code_hash / venue factory 注册) 都是 live guard 不是 dead branch
- **lesson #25 反 fabricated close-out**: 声称"Binance testnet 端到端跑通"必须**真跑一次 testnet order** (需 CI secrets 或 human loop), 不凭 mock 蒙混
- **lesson #29 校验类操作不覆盖 host**: docker compose 示例 `.env.example` 用户 cp 出的 `.env` 是他们真实凭证, executor 绝不 `cp .env.example .env` 覆盖 (与 CEO 上批次踩过的坑同)
- **lesson #35 boundary constant**: `trading_mode` 值域 `sandbox|testnet|live` 一次定死, PascalCase/snake_case 兼容 (Plan 46 dead-gate lesson #36 教训) — Rust `TradingMode` enum 序列化 wire 值必 grep 实证
- **lesson #37 spawner 元层 grep 实证**: drafter 编辑 G6 gate 逻辑 / capability 方法名 / Binance env enum 名 必 grep 实证

## 目标 (Goal)

1. **G6 gate capability-based 改造**: 从 `isinstance(NoopHost)` 单点决策 → 显式多层校验:
   - 层 1: host 声称支持 live mode? (`host.supports_live() -> bool`)
   - 层 2: host 声称支持 spec 中的 venue? (`host.supports_venue(venue_name) -> bool`)
   - 层 3: spec.code_hash 与 local strategy dir hash 匹配? (domain §1.2 红线)
   - 层 4: credential.permission_scope == `trade_no_withdraw` (vault 侧已守, gate 侧兜底 double-check)
   - 任一层 fail → `FailureEvent.reason_code=<layer>` + reject
2. **NtTradingNodeHost 加 capability API**: `supports_live() -> True`, `supports_venue(name) -> name in {"binance", "binance_perpetual"}`
3. **testnet mode**: 加 `BinanceEnvironment.TESTNET` 分支, 用 `BinanceLiveExecClientFactory` (非 sandbox)
4. **live mode**: 加 `BinanceEnvironment.LIVE` 分支; 加显式 warning log + 双人审批钩子 (对齐 G-SoD gate, `docs/nautilus_host.md:52`)
5. **docker compose e2e 示例**: `examples/supertrend-testnet/` (docker-compose.yaml + `.env.example` + vault fixture + README) — 用户可以 `cp .env.example .env` (填 Binance testnet key) → `docker compose up` 真跑 supertrend testnet

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| G6 gate 从 isinstance 改 capability, breaking `NautilusHostProtocol`? | **加 optional Protocol 方法**, `NoopHost` 显式返回 `False`; 未声明 capability 的 host 默认 fail-safe reject | 不 breaking 现有 NoopHost 契约; 新 host 显式声明 capability 是最小侵入 |
| live mode 双人审批实施位置 | **arx 云端 (approver ≠ applicant)**, custos 侧只校验 spec 携带 `approved_by[]` 字段长度 ≥ 2 | domain §G-SoD 云端职责 (`docs/nautilus_host.md:52`); custos 是执行侧 |
| Binance live/testnet 切换如何 driven? | **spec.trading_mode 单一入口** ({`sandbox`, `testnet`, `live`}) → NtTradingNodeHost 映射到 `BinanceEnvironment.{DEMO, TESTNET, LIVE}` | 与 ps runner.py 分层一致; 单一 boundary constant |
| e2e docker compose 示例带不带 sops+age vault? | **带 mock vault (env var), 但示例文档明确注明"生产必用 sops+age"** | 降低上手门槛; 但不能让示例默认反 non-custodial 红线 |
| e2e 是否真跑 Binance testnet order? | **CI 跳过 (需 secrets), README 提供 manual smoke test 步骤** | CI secrets 泄露风险 vs 覆盖度; manual smoke test 是最小折中 |
| README §"Not Included Yet" G6 条何时删? | **本 plan close-out 时删**, 撤下 "live deploy stays blocked" 描述 | 兑现承诺 |

## Task List

**Task 1**: `NautilusHostProtocol` 加 capability 方法 + `NoopHost`/`NtTradingNodeHost` 实现

- 文件: `src/arx_runner/deployment_reconciler.py` (改, `Protocol` 加 `supports_live` + `supports_venue`) + `src/arx_runner/nautilus_host.py` (改, `NoopHost.supports_live() -> False` + `NtTradingNodeHost.supports_live() -> True, supports_venue(name) -> name.lower() in {"binance", "binance_perpetual"}`)
- 契约: capability 方法 sync (非 async), 因为 gate 层需同步决策
- 测试: `tests/test_nautilus_host_capability.py` (新)
- 失败模式: 未声明 capability 的旧 host 默认返 False (fail-safe)

**Task 2**: G6 gate 从 `isinstance` 改 capability-based 多层校验

- 文件: `src/arx_runner/deployment_reconciler.py` (改, `_check_g6_gate` 逻辑重写, ~40 LOC)
- 层 1 层 2 sync (host capability); 层 3 code_hash (strategy_loader `compute_strategy_dir_hash`); 层 4 credential scope (vault 已守, gate 侧 assert 兜底)
- 任一层 fail → `RuntimeError` + reason 明码 (`g6_gate_live_capability_denied` / `g6_gate_venue_unsupported` / `g6_gate_code_hash_mismatch` / `g6_gate_credential_scope_violation`)
- 测试: `tests/test_g6_gate.py` (已存在, 扩展; 用 relaxed-double 证明每层独立可测 — lesson #28)
- 失败模式: 见契约表

**Task 3**: Binance testnet + live 分支

- 文件: `src/arx_runner/_nt_binance_venue.py` (改, ~80 LOC 增)
- 新加 `build_exec_client_config_testnet(spec, credential) -> BinanceExecClientConfig` (with `environment=TESTNET`) + `build_exec_client_config_live(spec, credential) -> BinanceExecClientConfig` (with `environment=LIVE`)
- `NtTradingNodeHost.deploy` 根据 `spec.trading_mode` 分发
- live 分支加 warning log + 校验 `spec.approved_by` 数组长度 (fail-safe 双人审批)
- 测试: `tests/test_nt_binance_venue.py::test_testnet_env_pin` + `::test_live_env_pin` + `::test_live_missing_approvers_rejected`
- 失败模式: `spec.approved_by` 缺 → `sod_approval_missing`

**Task 4**: docker compose e2e 示例 `examples/supertrend-testnet/`

- 新文件:
  - `examples/supertrend-testnet/docker-compose.yaml` (custos runner + 可选 NATS — 或直接连外部 NATS)
  - `examples/supertrend-testnet/.env.example` (Binance testnet API_KEY + SECRET 占位)
  - `examples/supertrend-testnet/vault-fixture/` (mock vault json — 生产环境用户会用 sops+age)
  - `examples/supertrend-testnet/spec.json` (DeploymentSpec with `trading_mode=testnet`)
  - `examples/supertrend-testnet/README.md` (跑步骤 + manual smoke test + non-custodial 生产环境提示)
- 无源码改动, 纯配置
- 失败模式: (无 — 静态配置)

**Task 5**: README 门面同步 + 集成测试

- 文件: `README.md` (改, 删除 §"Not Included Yet" G6 gate 条)
- 新加 §"Supported Trading Modes" 表格 (sandbox ✅ Plan 00a / testnet ✅ Plan 00c / live ⚠️ 需 arx 双人审批)
- 集成测试: `tests/test_g6_gate_capability_e2e.py` (新, ~100 LOC), 覆盖:
  - `test_noophost_still_rejects_live` (向后兼容)
  - `test_ntlive_host_accepted_with_all_layers_passing`
  - `test_layer1_capability_relaxed_double` (custom test double 声明不支持 live → 拒)
  - `test_layer2_venue_unsupported_relaxed_double` (spec.venue=okx → 拒)
  - `test_layer3_code_hash_mismatch_relaxed_double`
  - `test_layer4_credential_scope_violation_relaxed_double`
- 失败模式: 每 relaxed-double 一条

## 失败模式覆盖契约表 (lesson #17 + #28)

| 失败模式 | 触发点 | 测试文件:函数 (含 relaxed-double) | reason_code |
|---|---|---|---|
| host 不支持 live | G6 gate 层 1 | `test_g6_gate_capability_e2e.py::test_layer1_capability_relaxed_double` | `g6_gate_live_capability_denied` |
| venue 不支持 | G6 gate 层 2 | `test_g6_gate_capability_e2e.py::test_layer2_venue_unsupported_relaxed_double` | `g6_gate_venue_unsupported` |
| code_hash mismatch | G6 gate 层 3 | `test_g6_gate_capability_e2e.py::test_layer3_code_hash_mismatch_relaxed_double` | `g6_gate_code_hash_mismatch` |
| credential scope 违规 | G6 gate 层 4 | `test_g6_gate_capability_e2e.py::test_layer4_credential_scope_violation_relaxed_double` | `g6_gate_credential_scope_violation` |
| 双人审批缺失 | live 分支预检 | `test_nt_binance_venue.py::test_live_missing_approvers_rejected` | `sod_approval_missing` |
| trading_mode 大小写变体 dead-gate 复发 | G6 gate `.lower()` 保留 | `test_g6_gate.py::test_case_variants` (已有, 扩展) | (invariant) |
| testnet 与 live env 串 (spec.trading_mode=testnet 但 credential 是 live key) | 无法检测, 归 Binance 侧 auth fail | `test_nt_trading_node_host.py::test_venue_auth_failure_records_reason` (Plan 00a 已覆盖) | `venue_auth_failed` |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `src/arx_runner/deployment_reconciler.py` | 改 | G6 gate 重写 + Protocol 加 capability 方法 |
| `src/arx_runner/nautilus_host.py` | 改 | NoopHost/NtTradingNodeHost 加 capability 方法 + 加 testnet/live 分支 |
| `src/arx_runner/_nt_binance_venue.py` | 改 | 加 testnet/live venue config builder |
| `README.md` | 改 | 删 "Not Included Yet" G6 条; 加 Supported Trading Modes 表 |
| `tests/test_nautilus_host_capability.py` | 新建 | Task 1 单测 |
| `tests/test_g6_gate.py` | 扩 | Task 2 扩展 + capability 分层 |
| `tests/test_nt_binance_venue.py` | 扩 | Task 3 testnet/live 分支断言 |
| `tests/test_g6_gate_capability_e2e.py` | 新建 | Task 5 relaxed-double e2e |
| `examples/supertrend-testnet/docker-compose.yaml` | 新建 | e2e 示例 |
| `examples/supertrend-testnet/.env.example` | 新建 | 示例 env (不含真 key) |
| `examples/supertrend-testnet/vault-fixture/vault.json` | 新建 | mock vault (dev, README 明确不建议生产) |
| `examples/supertrend-testnet/spec.json` | 新建 | 示例 DeploymentSpec |
| `examples/supertrend-testnet/README.md` | 新建 | 步骤 + manual smoke test + 生产建议 |

## 验收清单

- [ ] G6 gate 从 isinstance 改为 capability-based; NoopHost 向后兼容 (老逻辑 test 全绿)
- [ ] 4 层校验各有 relaxed-double test 证明独立可测 (lesson #28)
- [ ] 7 处失败模式全 pytest 覆盖
- [ ] `NtTradingNodeHost` 支持 sandbox / testnet / live 三档
- [ ] live 分支强制 `spec.approved_by` 校验
- [ ] `examples/supertrend-testnet/` 可以 `docker compose up` 起来 (需用户填 Binance testnet key)
- [ ] README §"Not Included Yet" G6 条已删
- [ ] `pytest tests/` 全绿 (含现有 20+ test file)
- [ ] `trading_mode` PascalCase/lowercase 变体 dead-gate 检测保留 (lesson #36)
- [ ] `examples/` 下无真 API key (grep 实证)
- [ ] silent path grep (`except.*pass|except.*return\s+None`) 命中数不增

## 偏离与改进日志 (Deviation Log)

(执行阶段填写)

## 完成报告 (Close-out Report)

(执行完成填写)

## 下一步 (Next)

Plan 00c close-out 后:
- **短期 follow-up plan 候选**:
  - OKX venue 支持 (Plan 01)
  - `arx_runner` → `custos_runner` Python module rename (Plan 60 遗留, lesson #35 fanout)
  - 签名 release + 可复现构建 (ADR-012 v4 阶段 3, custos README §"Not Included Yet" 第 1 条)
- **中期**: `ExecutionEngineAdapter` 抽象补全 (`docs/nautilus_host.md:62-63`)
- **长期**: 多引擎 flavour (custos-hummingbot / custos-freqtrade), `nautilus_host.md:64-65`
