# 00c - G6 gate 逻辑放宽 (capability-based) + Binance testnet/live 逐级放行 + docker compose e2e

> **Status**: ✅ Completed (2026-07-07)
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

### DEVIATION: DEP-SKIP-CEO-OVERRIDE (DEV-00c-DEP-SKIP-CEO-OVERRIDE)
- **等级**: 高 (CEO override, lesson #38 记录路径)
- **原因**: Plan 00c 头部声明 blocked by Plan 00a + 00b; 00b (telemetry 桥) 未 close-out。CEO wukai 2026-07-07 经 `/forge:execute-team` AskUserQuestion 显式选择 Plan 00c 优先实施 (核心是 G6 gate capability 化 + testnet/live 分支, 与 00b 遥测桥独立)。
- **影响**: 提前放行 00c, 依赖 00a only。Task 4 e2e 观测面部分启用 (无 00b telemetry 桥, testnet 真跑 fill/OrderDenied 只走本地 structlog, 不上报云端 arx) — 已在 examples/supertrend-testnet/README.md 顶部明写此局限。
- **决定**: 走 lesson #38 CEO override 4 件套记录路径 (①CEO 决定 handoff packet §0 ②本 DEV 条 ③.forge/README.md 索引 00c 行脚注 ④historical-lessons.md C1)。四件套齐全, 非静默偏离。
- **更新的文档**: 本 plan 偏离日志 + `.forge/README.md` 00c 行 + `.claude/rules/historical-lessons.md` C1。

### DEVIATION: HOST-WIRING (DEV-00c-HOST-WIRING)
- **等级**: 中 (入口改动, 安全相邻; 非红线违反) — team-lead 已批准 (grep 实证 `__main__.py:151-157` 硬编码 NoopHost; 根因是 plan Task 4 File Inventory Foundation Scan 遗漏 CLI wiring, lesson #33b 层次维)
- **原因**: `src/arx_runner/__main__.py` reconciler 硬编码 `NoopHost()`, testnet/live spec 经 CLI 永远走 NoopHost stub (testnet 非 live → G6 gate 提前 return → NoopHost 静默 stub 不真跑)。Task 4 example "真跑 testnet" 目标无法达成; Plan 00c "G6 live release" 若无 CLI 入口 wiring 则 gate+capability 落地却无法经 CLI 触达。plan Task 4 File Inventory 遗漏此点 (声明"纯配置无源码改动")。
- **影响**: `__main__.py` 加 `--use-nt-host` flag (默认 NoopHost 向后兼容; 置位选 NtTradingNodeHost) + `_build_host` helper + 3-case 单测。
- **命名决定** (team-lead soft 建议, executor 决定): flag 名从初版 `--nt-host` 改为 `--use-nt-host` (bool store_true), 语义比 noun-y 的 `--nt-host` 更直白 (公开 CLU 面向外部用户)。本 plan 只需 noop / nautilus 两选一, 未来 flavour (Hummingbot/freqtrade) 是长期项, 走 YAGNI 不提前引 `--host {choice}`。rename fanout 已 grep 实证 (lesson #35): `__main__.py` / test / docker-compose.yaml / README, 无残留 `--nt-host`。
- **决定**: 加 flag 是 G6 live release 自然收口。**非红线 0.2 违反 / 非 packet §10 dispute**: `--use-nt-host` 只选真 host, 不绕过 gate — G6 gate 仍对每个 live deploy 4 层强制; NtTradingNodeHost.supports_live=True 但 venue/code_hash/scope 三层照查; NT 缺失时 deploy 仍 fail-fast。SendMessage 报备 team-lead (task #6 跟踪)。
- **safety-validator 复核锚点** (逐一可勾):
  - ✅ 默认 = NoopHost (向后兼容, 不带 flag 行为不变) — `_build_host` else 分支 + `test_build_host_defaults_to_noop`
  - ✅ 显式 `--use-nt-host` 才启用 NtTradingNodeHost (非 opt-out env var, 无 `SKIP_G6=1` 类) — grep `SKIP_G6/BYPASS` 无命中
  - ✅ G6 gate 4 层对每个 live deploy 全程强制 (启用真 host 不代表放行 live) — gate 在 reconciler `_apply_spec` deploy 路径, 与 host 选择正交
  - ✅ NT 缺失时 `--use-nt-host` + deploy 仍 fail-fast (`_ensure_nt_available`) — `test_build_host_nt_without_runtime_fails_fast`
  - ✅ `_build_host` TDD 3 case: 默认 NoopHost / `--use-nt-host` 选 NtTradingNodeHost / NT 缺失 + `--use-nt-host` + deploy → RuntimeError "nt-runtime"
- **更新的文档** (中风险偏离强制 docs 同步, team-lead 动作项 2): `docs/design/nautilus_host.md` (新增 §CLI 入口 + G6 gate 段 isinstance→capability 4 层同步 + NtTradingNodeHost 真实现落地状态刷新, 顺带修残留 Plan 00a 未同步的"尚未落地"陈旧) + `docs/design/reconcile.md` (NautilusHostProtocol capability 方法 + G6 gate 描述 + host 选择交叉引用) + `README.md` Supported Trading Modes 脚注 (三档均需 `--use-nt-host`) + examples README/docker-compose。

### DEVIATION: EXAMPLE-VAULT (DEV-00c-EXAMPLE-VAULT)
- **等级**: 中 (偏离 plan 明示设计决策, 但为守红线 0.1)
- **原因**: plan "关键设计决策" 表定 e2e 示例用 "mock vault (env var)"。实证 `CredentialVault.decrypt` (mock) 返回 `secret: "<mock>"` 占位, **无 api_key/api_secret** → 到 `build_data_client_config` 会 KeyError, 无法真跑。造一个读 env var 明文 key 的新 vault (a) 是新源码模块 (超 Task 4 纯配置范围) (b) 把明文 key 放 env 违反 non-custodial 红线 0.1 精神。
- **影响**: 示例改用已 ship 的 `SopsAgeVault` (非托管正道): `.env` 只放非密运行配置, exchange key 走 sops+age 加密文件 + 挂载的 age 私钥 (永不出本地)。vault-fixture/credentials.example.json 是无真 key 的凭证 shape 模板。
- **决定**: 用 sops+age 既守红线又是更 on-brand 的示例 (展示 custos 非托管安全模型)。README 完整文档化步骤 + 生产提示。
- **更新的文档**: examples/supertrend-testnet/README.md + .gitignore (examples vault/ + *.plain.json 忽略)。

### DEVIATION: TESTNET-DATA-ENV (DEV-00c-TESTNET-DATA-ENV)
- **等级**: 低 (Task 3 范围内正确性扩展)
- **原因**: Task 3 File Inventory 只列 exec config, 但 testnet 真跑若 data feed 仍走 LIVE 环境 → live 价格喂 testnet 执行, instrument 不匹配。
- **影响**: `build_data_client_config` 加 `environment` 参数 (默认 LIVE 保持 sandbox + 现有测试兼容) + `data_environment_for_mode` 映射 (sandbox→LIVE, testnet→TESTNET, live→LIVE)。
- **决定**: 属 testnet 正确性必需, 在 Task 3 精神内。加测试 `test_data_environment_for_mode` + `test_build_data_client_config_testnet_env`。

### DEVIATION: FOUNDATION-SCAN-MISS (DEV-00c-FOUNDATION-SCAN-MISS)
- **等级**: 低 (我方 lesson #9 复发, 诚实记录; 无功能影响, Task 4 grep 时自查纠正)
- **原因**: 起工 Foundation Scan 时 `ls -la examples/ 2>/dev/null || echo "不存在"` 中 `ls` 被 shell alias 成 `eza` 而 eza 未安装 (`command not found: eza`), `||` 误把工具报错当"examples/ 不存在"。实际 `examples/supertrend-sandbox/` 由 Plan 00a 提交存在。违反 lesson #9 "grep/ls 空≠不存在" (此处是工具报错≠不存在)。
- **影响**: Task 4 grep 无真 key 时命中 supertrend-sandbox 暴露此漏。已对齐: testnet 示例改用 sandbox 约定 (`spec-example.json` 命名 + 去掉误加的 `strategy_id` 字段, code_hash: null + log_level), 同步 sandbox README 陈旧引用 ("live/testnet 仍被 G6 gate 阻塞" → 已落地)。
- **决定**: 记入教训。预防: `ls`/`find` 空结果先跑已知命中 sanity check (common-errors.md §Foundation Scan 陷阱), 且 `2>/dev/null || echo` 会吞工具报错 → 改用 `find` 或不吞 stderr。

### DEVIATION: CEO-LESSON-37-PACKET-DRIFT (DEV-00c-CEO-LESSON-37-PACKET-DRIFT)
- **等级**: 低 (packet 措辞漂移, 无功能影响)
- **原因**: handoff packet §5 + 本 plan §失败模式表 point 名 `test_case_variants (已有)`, 但仓库现有真实函数是 `test_g6_gate_rejects_live_noophost` (参数化 Live/live/LIVE)。packet 假名与实际漂移 (lesson #37 spawner 元层未 grep 实证测试名)。
- **影响**: 无。executor 按 lesson #9/#25 用真实测试名建契约表, 不照抄 packet 假名。
- **决定**: heartbeat 报备 team-lead (task #5 跟踪)。契约表 test 名以仓库实存为准。

### DEVIATION: PEER-FOLLOWUP-F1F2F3 (DEV-00c-PEER-FOLLOWUP-F1F2F3)
- **等级**: 低 (codex L1 peer review stretch 补丁, 不改主契约; APPROVE_WITH_FOLLOW_UPS 无 blocker)
- **来源**: `.forge/reviews/2026-07/00c-peer-codex.md` (codex-cli high effort, reviewed @ `3375af3`)
- **内容**:
  - **F1** base-install NT-missing fail-fast test: 现有 `test_nt_trading_node_host.py` 有 `importorskip("nautilus_trader")`, 缺 NT 环境下恰好 skip 掉它声称覆盖的 missing-NT 场景。补 `test_main_host_selection.py::test_build_host_nt_without_runtime_fails_fast` (无 importorskip, monkeypatch `TradingNode=None` → deploy → RuntimeError "nt-runtime")。commit `93365c7` (随 HOST-WIRING rename 一并落)。
  - **F2** undeclared capability structured reject: `host.supports_live()` 直调对未声明 capability 的第三方 host 抛 AttributeError 而非 structured `g6_gate_live_capability_denied` (observability 断)。改 `_host_capability(host, method, *args)` getattr-default-False helper (supports_live + supports_venue 同源)。与 packet §10 正交: shipped hosts 仍显式实现 Protocol, getattr 只兜未声明 host (defense-in-depth 非替代显式契约)。test `test_undeclared_capability_host_gets_structured_reject`。commit `5f7bf12`。
  - **F3** unknown-mode 严格 test: `data_environment_for_mode` unknown 兜底返 LIVE (dispatch `_build_exec_plan` 已拒未知 mode 兜底)。**决定保留 LIVE fallback 不改 raise** (dispatch 已 fail-fast, 此处 raise 冗余且改契约); 加两个显式 boundary test: `test_deploy_unknown_trading_mode_rejected` (dispatch 拒绝 + 无 node 构造, commit `5f7bf12`) + `test_data_environment_for_mode_unknown_maps_live` (显式断言安全默认非意外)。
- **决定**: F1-F3 是加固补丁 (无功能回归), 主契约不变。因 mailbox 异步 (executor 主动读 codex 报告先修, team-lead 转达 findings 后到), F1-F3 分落 `93365c7`/`5f7bf12` 而非单 commit; team-lead 要求的单 commit 语义被时序覆盖, 功能结果一致且全 committed。本 delta (F3 显式 data_env 测试 + 本 DEV 条) 单 commit 收口。全绿: `make verify` + `make test-nt` (181→182)。

## 完成报告 (Close-out Report)

- **完成日期**: 2026-07-07
- **总 Task 数**: 5 (+ Task 4a `--use-nt-host` host wiring + review followups: HOST-WIRING 3 动作项 + codex L1 F1-F3)
- **偏离数**: 7 (DEP-SKIP-CEO-OVERRIDE 高 / HOST-WIRING 中 / EXAMPLE-VAULT 中 / TESTNET-DATA-ENV 低 / FOUNDATION-SCAN-MISS 低 / CEO-LESSON-37-PACKET-DRIFT 低 / PEER-FOLLOWUP-F1F2F3 低)
- **验证结果**: 全部通过 — `make verify` (base) + `make test-nt` (real nautilus-trader 1.230, hard preflight) **182 passed** / ruff fmt+lint All checks passed。
- **实施 commit 范围**: `19b7aba..53bf037` (14 commits = 8 初次 close-out + 6 review followup)
  - **初次 close-out (8)**: `19b7aba` T1 host capability / `8b00006` T2 G6 gate capability 4 层 / `19ebc16` T3 testnet+live 分支 / `416d182` T4a CLI host wiring / `17cfcbb` T4 docker compose 示例 / `e4cb3fb` T5 README / `7513d97` self-reflect code_hash 守卫 / `3375af3` mark completed
  - **review followup (6)**: `93365c7` `--nt-host`→`--use-nt-host` rename + codex F1 / `0d8c96a` HOST-WIRING docs 同步 + 安全锚点 / `5f7bf12` codex F2+F3 / `fed918f` marker refresh / `c693504` codex F3 显式 data_env 测试 + DEV 条 / `53bf037` marker refresh
- **契约影响**: 无跨模块契约破坏。docs 同步 (HOST-WIRING 中风险偏离 mandatory): `docs/design/nautilus_host.md` (§CLI 入口 + G6 gate isinstance→capability 4 层同步 + NtTradingNodeHost 落地状态刷新, 顺带修残留 Plan 00a "尚未落地" 陈旧) + `docs/design/reconcile.md` (NautilusHostProtocol capability 方法 + G6 gate 描述 + host 选择交叉引用) + `README.md` (Supported Trading Modes 表 + `--use-nt-host` 脚注) + examples README。
- **红线守护**: Non-Custodial 4 红线全数守住 (grep 记录, CEO 侧独立 grep 复核 0 命中):
  - 0.1 Key/KEK 不出进程: testnet/live exec config forward key 进 NT config, 不 log/publish; `_sanitize_exception` 覆盖 testnet/live 分支; grep `log.*api_key` 无命中。
  - 0.2 G6 gate 不绕过: isinstance → 4 层 capability fail-fast **加强** (含未声明 capability 结构化拒绝 F2); 无 opt-out env var (grep SKIP_G6/BYPASS 无命中); `--use-nt-host` 选真 host 不绕 gate。
  - 0.3 失联≠停止: reconcile loop disconnect 逻辑未改; grep stop_all_strategies 无命中。
  - 0.4 Money math Decimal: 本 plan 触碰 3 文件 grep float( 无命中。
- **codex L1 peer review**: APPROVE_WITH_FOLLOW_UPS 无 blocker (`.forge/reviews/2026-07/00c-peer-codex.md`); F1-F3 全 fix (见 DEV-00c-PEER-FOLLOWUP-F1F2F3); 8 项独立确认全绿。
- **失败模式覆盖** (契约 + review followup 扩展, 全 grep 实存 + 全绿):
  - `g6_gate_live_capability_denied` — test_layer1_capability_relaxed_double
  - `g6_gate_venue_unsupported` — test_layer2_venue_unsupported_relaxed_double
  - `g6_gate_code_hash_mismatch` — test_layer3_code_hash_mismatch_relaxed_double + test_layer3_code_hash_missing_relaxed_double + test_layer3_missing_strategy_path_refused (self-reflect)
  - `g6_gate_credential_scope_violation` — test_layer4_credential_scope_violation_relaxed_double
  - `sod_approval_missing` — test_live_missing_approvers_rejected / test_deploy_live_rejects_missing_approvers
  - trading_mode 大小写 dead-gate 防护 — test_g6_gate_rejects_live_noophost[Live/live/LIVE] (lesson #36 保留)
  - venue_auth_failed — test_venue_auth_failure (Plan 00a 已覆盖, 无新增)
  - 补: test_layer4_skipped_when_no_credential (reconfigure) + test_non_live_mode_bypasses_all_layers
  - review followup (F1/F2/F3): test_build_host_nt_without_runtime_fails_fast (base-install NT 缺失 fail-fast) + test_undeclared_capability_host_gets_structured_reject (未声明 capability 结构化拒绝) + test_deploy_unknown_trading_mode_rejected + test_data_environment_for_mode_unknown_maps_live
- **relaxed-double 独立可测 (lesson #22/#28)**: G6 gate 4 层各有 relaxed-double test 保持其余层有效只翻转目标层, 证明是 live guard 非 dead branch。全绿。
- **遗留项**: telemetry uplink bridge (Plan 00b) — NT MessageBus → arx telemetry actor 未落地, testnet/live 真跑 fill/OrderDenied 只本地可观测 (README "Not Included Yet" + examples README 已声明)。OKX venue / arx_runner→custos_runner rename / 签名 release 见 plan §下一步。

## 下一步 (Next)

Plan 00c close-out 后:
- **短期 follow-up plan 候选**:
  - OKX venue 支持 (Plan 01)
  - `arx_runner` → `custos_runner` Python module rename (Plan 60 遗留, lesson #35 fanout)
  - 签名 release + 可复现构建 (ADR-012 v4 阶段 3, custos README §"Not Included Yet" 第 1 条)
- **中期**: `ExecutionEngineAdapter` 抽象补全 (`docs/nautilus_host.md:62-63`)
- **长期**: 多引擎 flavour (custos-hummingbot / custos-freqtrade), `nautilus_host.md:64-65`
