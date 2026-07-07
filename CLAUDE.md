# custos — AI 助手项目上下文

> 由 `/forge:bootstrap --teams` 于 2026-07-07 生成最小骨架 (仅 forge Agent Teams onboard
> 标记 + 项目定位一段). **完整导航图** (子系统边界 / 6 模块导航 / 红线速览 / 常用命令) 由
> **Plan 01 Task 4** 落地 refine (见 `.forge/plans/2026-07/01-forge-bootstrap.md`).

## 1. 这是什么

**custos** (拉丁语: *guardian*) 是 [The Alephain Guild](https://github.com/the-alephain-guild)
生态的 **non-custodial、自托管** 执行 runner. 用户在自己的基础设施上运行本 daemon,
让它跑经过回测的 NautilusTrader 策略, 本地持有交易所 API Key, **永不上云端**. custos
与生态云端协调器 **arx** 配对: pull 期望态 `DeploymentSpec`, 回报执行遥测. 它是
"Key 和策略只在用户本地" 红线从**设计声明**升级为**工程可验证**的**唯一路径**.

详见: [`README.md`](README.md) · [`docs/domain.md`](docs/domain.md) · 6 module docs
在 [`docs/`](docs/) (Plan 01 后迁 `docs/design/`).

## 2. Forge 工作流入口

- `.forge/plans/2026-07/` — 现有 4 份 plan (00a/00b/00c 执行阶段 + 01 基础设施 bootstrap)
- `.forge/README.md` — plan 索引 (Plan 01 Task 3 落地)
- `.claude/rules/` — custos 独立规则集 (Plan 01 Task 2 落地; 独立开源仓库不依赖 workspace root)

---

## Forge Agent Teams 接入

<!-- forge-teams-onboarded: 2026-07-07 -->

本项目已接入 Forge Agent Teams (plan-team / execute-team / architect-team / ops-team):

- **配置文件**: `.forge/teams.yaml` (schema: `forge/docs/teams/ORG-CHART.md` §10 + §19)
- **启用 env flag**: `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (详见 ORG-CHART §15.1)
- **验证**: 运行 `/forge:plan-team` 触发 Planner Dept dry-run

如需修改 teams 配置 (authority_docs / safety_paths / executor areas / model 分配),
直接编辑 `.forge/teams.yaml`; 重跑 `/forge:bootstrap --teams` 会进入 diff 模式而非覆盖.

**custos 特化 (与 arx 差异)**:
- 单栈 Python daemon, 只有 1 个 executor area (`runner` @ `src/arx_runner`)
- safety.touched_paths 覆盖 `src/arx_runner/` 全部 8 module (non-custodial 承重墙)
- planner_team.drafters_per_session=2, codex_audit.max_calls_per_plan=3 (预算收紧, arx 是 4/5)
- architect_team.experts=`[domain, safety, python]` (无 rust / web 专家)
- opus 强角色显式 pin `claude-opus-4-7[1m]` (禁裸 `opus`, CEO 2026-07-06 禁)
