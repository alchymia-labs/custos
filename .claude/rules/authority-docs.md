# 权威文档声明 (custos)

以下文档是 custos 独立仓库的真理源. 代码与文档冲突时以权威文档为准并更新代码,
除非文档本身已过时需要更新.

**独立仓库自足**: 本清单仅列 custos 仓库内文档, 不引 workspace root, 保证外部审计员
单仓 clone 即有完整权威锚点.

## 顶层权威 (最优先)

| 文档 | 路径 | 用途 |
|------|------|------|
| README | `README.md` | 门面 + Trust Boundary 三条 (non-custodial 红线原文) |
| Domain 纸面 spec | `docs/domain.md` | 6 BC + Non-Custodial 分层信任边界专章 (设计契约) |
| 项目导航图 | `CLAUDE.md` | AI 助手会话入口 (导航图非百科) |
| LICENSE | `LICENSE` | Apache-2.0 |
| NOTICE | `NOTICE` | 归属声明 |

## 六模块设计文档 (Plan 01 之后位于 `docs/design/`)

| 模块 | 文档 | 承担红线 |
|------|------|---------|
| enrollment | `docs/design/enrollment.md` | EnrollmentToken 一次性 + `paper_only` 默认 |
| reconcile | `docs/design/reconcile.md` | Declarative loop + 失联≠停止 (local fallback breaker) |
| nautilus_host | `docs/design/nautilus_host.md` | **G6 host gate** — live release 核心闸门 |
| telemetry_actor | `docs/design/telemetry_actor.md` | NT MessageBus → 白名单 + 脱敏 + envelope schema |
| credential_vault | `docs/design/credential_vault.md` | sops+age 本地 KEK + `trade_no_withdraw` scope |
| nats_client | `docs/design/nats_client.md` | subject naming + envelope 版本化 |

## 规则集 (本目录内)

| 文档 | 用途 |
|------|------|
| `mandatory-rules.md` | non-custodial 4 红线 + 强制规则 |
| `tech-stack.md` | Python 3.11+ / uv / 依赖清单 |
| `code-style.md` | ruff + custos 特化 (脱敏日志 / 英文日志字段) |
| `common-errors.md` | Python + NT lifecycle + async 陷阱 |
| `verification.md` | make verify 命令清单 |
| `historical-lessons.md` | 生态 lesson 精华 (custos 视角) |
| `deviation-protocol.md` | 低/中/高风险偏离协议 |
| `progress-management.md` | 状态标记 + SemVer + close-out 模板 |
| 本文件 | 权威文档路径清单 |

## Plan 与 forge 工作流

| 文档 | 路径 | 用途 |
|------|------|------|
| plan 索引 | `.forge/README.md` | plan 编号规范 + 现有 plan 表 |
| 现有 plan | `.forge/plans/YYYY-MM/NN-<slug>.md` | 实施计划 (活文档) |
| teams 配置 | `.forge/teams.yaml` | forge Agent Teams schema |

## 使用规则

1. **修改前查阅**: 触及模块设计前先读对应 `docs/design/<module>.md`
2. **同步更新**: 代码变更导致文档失效时, 必须在同一 commit / PR 中更新文档
3. **红线冲突以 mandatory-rules 为准**: `mandatory-rules.md` 是所有其他文档的宪法约束
4. **domain.md 变更需 councils 审议**: 顶层 spec 变更 = 中/高风险偏离 (见 `deviation-protocol.md`)

## 生态参照 (workspace 视角, 独立 clone 后失效)

以下仅在开发者从 `the-alephain-guild` monorepo 内工作时可见, 独立 clone custos 后**不可用**.
custos 自身的规则集与设计文档已把这些参照的精华固化为本仓库自足内容, 不假设它们存在.

- `../../.claude/rules/*.md` (workspace 生态规则)
- `../arx/.claude/settings.json` (孪生子系统 settings 参照)
- `../../grimoire/` (方法论宪法, 生态级)
