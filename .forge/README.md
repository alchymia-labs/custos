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
| [00a](plans/2026-07/00a-nt-trading-node-host-sandbox.md) | NtTradingNodeHost + Binance sandbox | 🔲 Todo | arx Plan 60 (已 close-out) | Plan 00b | NoopHost → 真 TradingNode; supertrend 策略首打通 sandbox |
| [00b](plans/2026-07/00b-telemetry-bridge-nt-messagebus.md) | telemetry_actor 接 NT MessageBus | 🔲 Todo (blocked by 00a) | Plan 00a | Plan 00c | NT MessageBus → telemetry uplink; OrderDenied 桥 |
| [00c](plans/2026-07/00c-g6-gate-live-release.md) | G6 gate 放宽 + Binance testnet/live 逐级 | 🔲 Todo (blocked by 00a+00b) | Plan 00a + 00b | (live 放行终点) | capability-based G6 + docker compose e2e |
| [01](plans/2026-07/01-forge-bootstrap.md) | Forge 基础设施 bootstrap | ⏳ In Progress | 无 | (逻辑上先于 00a-c) | `.gitignore` / `.claude/rules/` / `Makefile` / `docs/design/ops/guides/` / `CLAUDE.md` |

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

- **02+**: 按需起 (如 `pyright` 集成 / `nt-runtime` extra 加入 / OKX venue 支持 /
  签名 release pipeline / Python 模块 rename `arx_runner` → `custos_runner`)
- 编号沿用 `02` `03` ..., 不复用 `00` / `01`
