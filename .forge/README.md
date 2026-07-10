# custos forge 工作流

`.forge/` 目录是 custos 独立仓库的 forge 工作流物件根. 包含 plan 目录 + Agent Teams 配置.

## 目录约定

```
.forge/
├── README.md              — 本索引 (plan 编号规范 + 现有 plan 表)
├── teams.yaml             — Agent Teams 配置 (plan-team / execute-team / architect-team / ops-team)
├── plans/YYYY-MM/         — Plan 文件, 按月份归档
│   └── NN[a-z]?-<slug>.md
├── reviews/YYYY-MM/       — Peer review 报告 (未来)
├── fixes/YYYY-MM/         — Fix plan (未来)
├── incidents/YYYY-MM/     — 紧急偏离记录 (未来)
├── scratch/               — 临时 scratchpad (gitignore)
└── handoff/               — Agent handoff packet (gitignore)
```

## Plan 编号规范

- **格式**: `NN[a-z]?-<kebab-slug>.md`
- **NN**: 两位数字, 从 `00` 开始; `00` 保留给"起始阶段规划簇"(可用 `00a` / `00b` / `00c`
  子编号并列相关 plan)
- **kebab-slug**: 简短语义标识 (如 `nt-trading-node-host-sandbox`)
- **月份归档**: `.forge/plans/YYYY-MM/` (以 plan 创建月为准)
- **子编号使用场景**: 一个大特性拆多个并行 plan (如 00a NT host + 00b telemetry + 00c
  G6 live release), 每 plan 相对独立可实施

## 现有 Plan 索引

| # | Slug | Status | Depends on | Blocks | 说明 |
|---|------|--------|-----------|--------|------|
| [00a](plans/2026-07/00a-nt-trading-node-host-sandbox.md) | NtTradingNodeHost + Binance sandbox | ✅ Completed (2026-07-07) | arx Plan 60 (已 close-out) | Plan 00b | NoopHost → 真 TradingNode; sandbox 策略打通 (codex peer review 落地 F2-F6) |
| [00b](plans/2026-07/00b-telemetry-bridge-nt-messagebus.md) | telemetry_actor 接 NT MessageBus | ✅ Completed (2026-07-08) | Plan 00a | Plan 00c | NT MessageBus → telemetry uplink; OrderDenied 桥 (fixed dead subscription; deploy attach) |
| [00c](plans/2026-07/00c-g6-gate-live-release.md) | G6 gate 放宽 + Binance testnet/live 逐级 | ✅ Completed (2026-07-07) | Plan 00a + 00b ¹ | Plan 03 (硬化候选) | capability-based G6 + docker compose e2e |
| [03](plans/2026-07/03-nt-host-hardening.md) | NT host hardening (credential lifecycle + capability integration + host×mode matrix + correlation handle 精度提升 + GC-safety 扩展) | ✅ Completed (2026-07-09) | Plan 00a + 00b + 00c ✅ | Plan 05 candidate (subprocess isolation + FailureEvent first-class) | 起源: 00a F1 defer + 00c HIGH triage new-plan; Phase 2 精细化含 evidence-scout 4 latent + 5 drift 消化; Phase 3 execute-team 11 Task ~450 LOC 落地 (214 passed, 4 红线 0 命中), peer review chain codex L1 REQUEST_CHANGES → Path B 契约诚实化 fix → tdd/safety APPROVE_WITH_FOLLOW_UPS |
| [04](plans/2026-07/04-red-line-03-runner-fallback.md) | 红线 0.3 完整兑现: runner-level cap + 状态快照 + zombie detection + arx-disconnect chaos | ✅ Completed (2026-07-10; 04a `3e85c50` + 04b squash `d0dd537` + 04b-fix commits `b04071e`+`1c9f3dd`; drawdown wire + state snapshot publisher wire + WAL-backed path + risk_config live-refresh 三层 runtime-wire live) | Plan 00a + 00b + 00c + 03 ✅ + **05** (结构重构) ✅ | 上 live **1 号硬阻断项** | 起源: Plan 03 close-out 后 safety-validator 跨范围深度审 + Lead 复核 — 红线 0.3 组合级熔断 grep 0 命中 (max_notional_per_runner + drawdown breaker 均无实现); 教科书级 lesson #40 project-level dogfood. Refinement: 14 tasks / 6 tracks / 39 failure-mode tests (4 grep + 35 NEW) / 6 Tier-2 methods owns. **04a squash `3e85c50`** + **04b squash `d0dd537`** landed 全部 Tracks 1+2+3+4+5+6. **Drawdown wire flip 确认真实** (codex + safety + lead 三方 grep 实证 `_breaker_tick → get_engine_status → FallbackBreaker.evaluate`). **04b codex L1 REQUEST_CHANGES 关闭 (04b-fix cycle 2026-07-10)**: HIGH-1 wire `StateSnapshotPublisher` 进 `cli/main.py` via `asyncio.create_task(publisher.run(stop, reconciler.active_spec_ids))` + 新增 `DeploymentReconciler.active_spec_ids()` public 方法 (`b04071e`); MED-2 publisher 切到 `publish_telemetry_envelope` WAL-backed at-least-once path + `--wal-path` CLI flag (`b04071e`, Option A); MED-3 `RunnerNotionalCap.apply_config` + `FallbackBreaker.apply_config` + `DeploymentReconciler._refresh_risk_config(spec)` 在每次 accepted spec 前跑 (`1c9f3dd`, Option A). 见 `.forge/reviews/2026-07/04b-peer-codex.md` |
| [05](plans/2026-07/05-structural-refactor-engine-abstraction.md) | 结构化重构: arx_runner → custos rename + core/engines 分层 + ExecutionEngineProtocol + pyproject extras + NATS subject engine layer | ✅ Completed (2026-07-10; 05a `4f0192a`+`7ffa187` 2026-07-09 + 05b `79c1858`..`e82825d` 2026-07-10) | Plan 00a + 00b + 00c + 03 ✅ | Plan 04 + 06 + 07 (本 plan 是基础重构, 已先行落地避免其他 plan 二次搬迁) | 起源: user 澄清诉求 — custos 后期需支持多引擎 (hummingbot / freqtrade / athanor / nt-rust), 提前规划目录结构 + 命名方式; 消化 arx subtree 遗留 (arx_runner Python 包名 rename, lesson #35 fanout). 17 tasks / 8 tracks 全落地. **05a squash `4f0192a`** 落 Tracks 1-4+8 (46 file rename + core/engines/cli 分层 + Protocol Tier-1 冻结 + g6_gate 抽出 + isinstance 契约测试), unblocks Plan 04/06 START gates; 3 LOW triage `.forge/triage/05a-DEVIATION-triage.md` (含 v2 fabricated close-out event lesson #25/C2 首次 in-codebase 复现). **05b** 落 Tracks 5-7 (pyproject extras `nt-runtime`→`nautilus` + 4 空槽 + `docs/engines/` 5 stub + NATS subject v2 reserved docs) + T-final 完整 close-out; 1 LOW triage `.forge/triage/05b-DEVIATION-triage.md` (Foundation Scan 顺手修复 05a 遗漏的 2 处 `arx_runner` 功能性残留). `make verify` 263 passed / `make verify-nt` 263 passed |
| [06](plans/2026-07/06-ps-supertrend-migration.md) | ps supertrend 迁移: custos registry-mode 加载 + RiskController 启用 + shared/ 依赖打包 + e2e 集成 | ✅ Completed (2026-07-10; 06a slice `306b9e5` for Tracks 1-4 + Plan 08 for Tracks 5-6 + full close-out) | Plan 00a + 00c + 03 ✅ + **05** (结构重构); soft-depends Plan 04 | 生产化 ps supertrend 首次 paper/testnet e2e | 起源: user 澄清 custos 接管 ps supertrend 移除 sidecar/runner; grep 实证 supertrend 已有 register_strategy 无需策略侧改造, custos 只需 registry-mode 分支. Refinement: 12 tasks / 6 tracks / 15 failure-mode tests (3 grep + 12 NEW) / shared toolkit 打包方案 A vendored 推荐. codex peer fix cycle: HIGH-1 option B + HIGH-2 option B + MED-3 promoted DP4 + FU-2 NEW test 已应用. **06a squash 306b9e5 landed Tracks 1-4** (vendored toolkit + strategy_registry_name + RiskController activation + TradingNodeConfig plumb); Track 5-6 remainder + full close-out landed via Plan 08 (`4ac60d7`..`<Plan 08 T6.2 SHA>`) on branch `custos/08-plan/runner` per `DEV-08-RENUMBER-FROM-06B`. Full close-out: 4 red-line gates satisfied with real code_coverage / runtime_wire values (DP1=A partial+manual for testnet real-session opening per `DEV-08-T5.2-MANUAL-VERIFICATION`). |
| [07](plans/2026-07/07-ps-shared-curation-and-convergence.md) | ps shared curation + convergence: custos-as-shared-authority landing + sync discipline real implementation + ps convergence path | ✅ Completed (2026-07-10; runner-executor-07 sonnet ran Tracks 1-4 + T5.1 partial; main-session takeover T5.1 close-out after runner-07 session quota hit; 8 commits base `4437991`..`ce9fce2`) | Plan 06 06a squash `306b9e5` ✅ + Plan 05 (via 06a inheritance) ✅ | Plan 08 START gate now open | 起源: 06a `DEV-06-06A-REVERSE-DEPENDENCY-STRATEGY-D'` — custos toolkit = 权威 body-of-truth, ps = research 副本. Refinement: 5 tracks / 9 tasks / 9 NEW tests + 1 no-regression / no source-code changes (`DEV-07-NO-SOURCE-CODE-CHANGES`). Batch 1 peer chain: L1 REQUEST_CHANGES (10 findings) → in-place fix → L2 APPROVED_WITH_FOLLOW_UPS (2 LOW). **4 CEO DPs ratified 2026-07-10**: DP1=(a) keep 06a 90-file vendor status quo / DP2=(a) short-term keep ps Docker-buildable shared+deploy (HIGH hard-constraint — crucible/nautilus Dockerfile) / DP3=(b) weekly diff review / DP4=(a+b) status quo + formalized trigger criteria. **2 LOW follow-ups applied**: L2-FU-07-1 (fix log CR-10 grep BRE/ERE correction with 6 prose FPs recorded) + L2-FU-07-2 (scout line count 230→255 post-errata). ps cross-repo commit `2bf06e6` on philosophers-stone `develop`. |
| [08](plans/2026-07/08-plan-06-remainder-e2e-and-close-out.md) | Plan 06 remainder: real supertrend e2e (sandbox + testnet) + ps sidecar retirement docs + Plan 06 close-out | ✅ Completed (2026-07-10; runner-executor-08-2 landed 4 tasks on branch `custos/08-plan/runner` @ base `6373f50`, 4 commits `4ac60d7`..`<T6.2 SHA>`) | Plan 07 landing (START gate) + Plan 06 06a landed `306b9e5` ✅ + Plan 00a/00b/00c/03/05 ✅ | Plan 06 close-out (T6.2 flipped 06 → ✅) + first paper→testnet production acceptance for ps supertrend on custos | 起源: Plan 06 06a spawn 显式 defer Track 5-6 到 06b, CEO 2026-07-09 renumber 到 Plan 08 (Plan 07 crosses 中间) per `DEV-08-RENUMBER-FROM-06B`. 4 tasks (T5.1 sandbox e2e + T5.2 testnet DP1-conditional + T6.1 sidecar retirement docs + T6.2 close-out). Batch 1 peer chain: L1 REQUEST_CHANGES (9 findings) → in-place fix → L2 REQUEST_CHANGES CR-1 PARTIAL only (verbatim column synthesized cells), 8/9 RESOLVED, CEO 2026-07-10 accept path 降级 CR-1 为 LOW follow-up. **3 CEO DPs ratified 2026-07-10**: DP1=A real testnet credential via vault (partial+manual verification per `DEV-08-T5.2-MANUAL-VERIFICATION`) / DP2=A independent arx-side follow-up plan / DP3=A golden path only, no chaos test in Plan 08. **5 execution-time DEV entries**: STRATEGY-SOURCE-PATH-SELECTED-III (permanent fixture mirror pinned to ps `3443e969`) / RISK-CONTROLLER-ACTIVATION-PROXY (config-layer proxy for `_risk_controller` assertion since `on_start` not fired under parked `run_async`) / T5.2-MANUAL-VERIFICATION (skip-if-not-provisioned + operator runbook) / INTEGRATION-MARKER-REGISTERED (pyproject.toml) / L2-FU-08-1-VERBATIM-DISCIPLINE (no rewrite; discipline point recorded). `make verify` 299 pass + 2 skip; `make verify-nt` 299 pass + 2 skip. |

> ¹ Plan 00b (telemetry 桥) close-out 前, 由 CEO override 提前放行 00c
> (`DEV-00c-DEP-SKIP-CEO-OVERRIDE`, lesson #38 CEO override 4 件套记录路径)。
> 后果: e2e 观测面部分启用 — testnet 真跑 fill/OrderDenied 只走 custos 本地
> structlog, 00b telemetry 桥落地后才对外上报云端 arx。见
> [Plan 00c §偏离日志](plans/2026-07/00c-g6-gate-live-release.md#偏离与改进日志-deviation-log)
> + [historical-lessons C1](../.claude/rules/historical-lessons.md)。
| [01](plans/2026-07/01-forge-bootstrap.md) | Forge 基础设施 bootstrap | ✅ Completed (2026-07-07) | 无 | (逻辑上先于 00a-c) | `.gitignore` / `.claude/rules/` / `Makefile` / `docs/design/ops/guides/` / `CLAUDE.md` |

### 执行顺序建议 (Plan 04/05/06/07/08 + Batch 2 09)

```
Plan 05 (结构重构 + arx_runner → custos rename + core/engines 分层) ✅ Completed (05a `4f0192a` + 05b `e82825d`)
  ↓
Plan 04 (红线 0.3 兑现) — 落到 custos.core.*
  ↓ 与 06 可并行 (串行推荐 04→06, 见 04-05-06 packet §12)
Plan 06 (ps supertrend 迁移 06a slice ✅ landed 306b9e5)
  ↓
Plan 07 (ps shared curation + convergence — Batch 1) — 落到 custos.engines.nautilus.toolkit.*
  ↓
Plan 08 (Plan 06 remainder — Batch 1) — real supertrend e2e + Plan 06 close-out
  ↓
Plan 09 (hook infra formalization — Batch 2, 独立 dispatch 后续)
  ↓
Plan 10+ (未来引擎接入, 一引擎一 plan: hummingbot / freqtrade / athanor / nt-rust)
```

**Batch 1** (Plan 07 + Plan 08): 2026-07-10 CEO ratified `APPROVED_WITH_FOLLOW_UPS`. Plan 07 landed 2026-07-10 (base `4437991`..`ce9fce2`, 8 commits, sonnet executor + main-session T5.1 takeover). Plan 08 START gate now open — awaiting Slot 2 dispatch. Batch 1 内 serial (Plan 07 landing → Plan 08 START gate).

**Batch 2** (Plan 09): 独立 dispatch 后续, 独立于 Batch 1 close-out.

### 编号顺序说明

Plan `01` 在**逻辑上**应先于 `00a`/`00b`/`00c` 执行 (bootstrap 提供 `make verify` 等基础
设施), 但用户在 arx Plan 60 subtree split 之后**先起草了** 00a-c 三份 execution plan
+ commit (`87598b5`), 之后才补起 01 bootstrap. 编号顺序未倒回, 通过 Plan 01 偏离日志
+ 本索引段落显式记录. 见 [Plan 01 §偏离与改进日志](plans/2026-07/01-forge-bootstrap.md#偏离与改进日志-deviation-log).

## Close-out 归档

Plan close-out 后 (Status: ✅ Completed):

1. plan 文件末尾追加 `## 完成报告 (Close-out Report)` 章节 (模板见
   `../.claude/rules/progress-management.md`)
2. 本 README 表格 Status 列更新为 ✅
3. plan 文件**留在原路径**不迁移 (git history 是唯一真相)
4. 若产出 review / fix 副本, 归档到 `.forge/reviews/YYYY-MM/` / `.forge/fixes/YYYY-MM/`

## Agent Teams 入口

- **配置**: `.forge/teams.yaml`
- **启用 env flag**: `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- **触发命令**: `/forge:plan-team` / `/forge:execute-team` / `/forge:architect-team` /
  `/forge:ops-team`
- **schema 参照**: `forge/docs/teams/ORG-CHART.md` §10 + §19 (workspace 内可见, 独立
  clone 后不适用; 若独立场景需 teams, 手写 teams.yaml)

## 后续 plan 规划

Plan 01 close-out 之后:

- **02+**: 按需起 (如 `pyright` 集成 / OKX venue 支持 / 签名 release pipeline /
  Python 模块 rename `arx_runner` → `custos_runner`)
- **03 候选 `03-nt-host-hardening.md`** (来自 00a codex peer review F1, high red-line 观察):
  NtTradingNodeHost 通过 `_active_nodes` 的 `node` 引用间接内存持有 credential (via
  data/exec config)。Lead 判定这是 NT ↔ exchange 通信的**设计必要** (custos daemon 本就要
  本地持 key), 红线 0.1 原文限 log/publish/send I/O 边界, in-process 内存持有不违反 —
  **不阻塞 00a close-out**。后续 plan 加 credential lifecycle test suite, 验证三层 invariant:
  no credential in (1) `node` repr / (2) `node.__dict__` recursive dump / (3) structlog
  processor output。
- 编号沿用 `02` `03` ..., 不复用 `00` / `01`
