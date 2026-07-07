# 01 - Forge 基础设施 bootstrap (custos 独立仓库首次接入 forge 工作流)

> **Status**: 🔲 Todo
> **Created**: 2026-07-07
> **Project**: custos (`tesseract-trading/custos/`)
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: 无 (基础设施先行)
> **Blocks (逻辑上)**: Plan 00a/00b/00c 应在本 plan 之后执行, 但已先起草并 commit; 见"偏离与改进日志"段
> **multi_session_scope**: false (单 session 8 task 可完成; 大部分是文件生成 + 内容提炼)

## 上下文 (Context)

### 现状 (as-of 2026-07-07, custos main HEAD = 87598b5)

custos 是从 arx `runner/` subtree split 出来的独立 Apache-2.0 公开开源仓库(arx Plan 60 已 close-out 2026-07-06)。48 tracked file, 结构简洁 — 源码 + 测试 + 7 份 docs + 3 份刚起草的 plan。但**几乎所有 forge 基础设施都缺**:

- 无 `.claude/` 目录(settings + rules 全缺)
- 无 `CLAUDE.md`
- 无 `.gitignore` (**紧急**: `.venv/` `__pycache__/` 全不在 ignore, 风险 stage)
- 无 `Makefile`
- 无 `.forge/README.md` (虽有 3 份 plan 但无索引)
- `docs/` 扁平 7 份 .md, 未按 design/ops/guides/domain 子目录组织
- 缺 overview / architecture / testing / deployment / runbook / dev-guide 6 份标准文档骨架 (module docs 6 份存在)

### 独立开源仓库的特殊约束

**关键洞察**: custos 与 monorepo 内其他子系统 (arx / synedrion / speculum) **不同** — 后者依赖 workspace root `the-alephain-guild/.claude/rules/`, 生态规则自动加载; custos 是独立开源仓库, 外部审计员会**单仓 clone** 查代码, workspace root 不会跟着来。因此:

1. **必须自建独立 `.claude/rules/`**, 不能仅"继承" — 独立性是 non-custodial 红线兑现的一部分(用户 clone custos 就能审计, 无需 workspace)
2. 规则内容可与 workspace 生态规则**思想一致** (精华层继承), 但**文本必须自足** — 不假设 workspace 规则存在
3. `mandatory-rules.md` 需含 custos 特化红线 (key/plaintext 永不出进程 / G6 gate 不绕过 / reconcile 失联≠停止 / money math str(Decimal))

### 契约证据锚表 (Foundation Scan Gate, file:line 已 grep 实证)

| 引用契约 / 来源 | file:line | 用途 |
|---|---|---|
| custos 独立开源纪律 (Apache-2.0 day 1) | `README.md:11-21` | 规则集独立自足论证依据 |
| non-custodial 红线 (key 只在本地 + 声明式控制 + 云宕机降级) | `README.md:23-38` + `docs/domain.md:178-215` §2 | `mandatory-rules.md` §"custos 红线"素材源 |
| domain-model 6 BC + 分层信任边界 | `docs/domain.md:85-215` | `docs/design/01-architecture.md` 内容源 |
| 六件套 module 设计文档 (已存在 6 份) | `docs/{credential_vault,enrollment,nats_client,nautilus_host,reconcile,telemetry_actor}.md` | 迁到 `docs/design/` 子目录, 无内容改动 |
| README §"Not Included Yet" 6 条 follow-up | `README.md:94-108` | `docs/ops/runbook.md` 未来演化章素材 |
| pyproject.toml 已声明依赖 | `pyproject.toml:6-17` | `docs/design/03-implementation.md` 技术栈章 |
| 20 test files, tests/ 目录 | `tests/` (`ls tests/`) | `docs/guides/04-testing.md` 测试策略源 |
| tracked file 清单 (48 file) | `git ls-files` | .gitignore 起草时对比"应 ignore 但当前 tracked" 逆向检查 |
| workspace root 现有 rules (思想参照) | `../../.claude/rules/*.md` (workspace 视角可读, 独立 clone 后不可见) | 起草 custos 独立规则集时"思想继承"参照, 内容不复制 |
| arx `.claude/settings.json` 参照 | `../arx/.claude/settings.json` (workspace 视角可读) | settings.json permissions/hooks 结构参照 |
| 生态 CLAUDE.md 强制规则 (workspace 视角) | `../../.claude/rules/mandatory-rules.md` | 独立仓 clone 后不可见, 思想参照移入 custos 独立规则集 |

### Plan-to-plan 引用

- **arx Plan 60** (`tesseract-trading/arx/.forge/plans/2026-07/60-runner-custos-split.md`): custos 从 arx 抽出的上游, 已 close-out; 本 plan 是 subtree split 后**独立化收尾**动作(subtree split 只搬源码 + docs, 未同步 forge 基础设施)
- **本 plan 逻辑上先于 00a/00b/00c**: 但事实上 00a-c 已 commit `87598b5`; 见偏离段处理

### Historical lessons 强制引用

- **lesson #14 Foundation Scan Gate**: 起 plan 前系统扫骨架 + 通读权威文档 — 已完成 (48 tracked file 全扫 + docs/domain.md 通读 + README.md 通读 + workspace 生态规则参照)
- **lesson #22 多层 fail-fast**: mandatory-rules 加"key 永不出进程" + "G6 gate 不绕过" + "失联≠停止" 三层, 与 workspace 精神一致但**文本自足** (clone 后不假设 workspace 存在)
- **lesson #25 反 fabricated close-out**: close-out 契约表引用 file 必 grep 实证真存在;规则文件内容不凭"应该有"推理,必读 workspace 参照或代码 grep
- **lesson #26 `pub String` boundary**: `.gitignore` `.env` 通配符准入必显式 `!examples/*/.env.example` 白名单反向豁免
- **lesson #27 commit scope discipline**: 全 Task commit 用 `git add <specific-file>` + 提交前 `git status --short` 核对
- **lesson #29 校验类操作不覆盖 host**: 建 `.gitignore` 前先 `git ls-files` 实证已 tracked file 不会被新 ignore 覆盖;测试若涉 vault 用 mktemp 不碰用户真实 `~/.custos/`
- **lesson #35 boundary constant**: settings.json permissions 用 `Bash(uv run:*)` 等 wildcard, 变体 `uv-run` / `uv_run` 一次定死
- **lesson #37 spawner 元层 grep 实证**: drafter 编辑本 plan 引用的所有代码符号(rule 文件名 / setting key 名 / makefile target 名)前已 grep 实证 workspace 参照

## 目标 (Goal)

给 custos 独立开源仓库补齐 forge 基础设施, 让:

1. 后续 `/forge:execute .forge/plans/2026-07/00a-...md` 有 `make verify` 可跑
2. 外部审计员单仓 clone 后有完整 CLAUDE.md 导航 + `.claude/rules/` 独立规则集可读
3. `.gitignore` 保护开发环境不污染 git 历史
4. docs/ 结构清晰(6 份 module docs 归 `docs/design/`, 补齐 overview/architecture/testing/deployment/runbook/dev-guide 6 份骨架)
5. `.forge/README.md` 索引 Plan 00a/00b/00c + 本 plan, 未来 plan 编号规范

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| custos 独立 `.claude/rules/` vs 依赖 workspace | **自建独立**, 不依赖 workspace | 独立开源仓库外部审计员 clone 单仓, workspace 不跟随; 独立自足是 non-custodial 红线兑现的一部分 |
| 规则内容与 workspace 生态规则关系 | **精华思想继承, 文本自足** | 与 workspace 精神一致但不复制粘贴, 加 custos 特化红线; 后续生态规则演化不自动同步(独立仓库权衡) |
| Bootstrap plan 编号 | **01** (与 00a/00b/00c 并列 `2026-07/`) | 已有 00a-c commit `87598b5`, 编号顺序不倒回; plan 内偏离日志记录"应先于 00a-c 但事实上后置" |
| docs/ 是否强 4 子目录重组 | **建 3 子目录 `design/ops/guides/`, 不建 `domain/`** | custos 简单 daemon 项目, `docs/domain.md` 是纸面 spec 顶层文档保留在 `docs/` 根;6 份 module docs 迁 `docs/design/`, 补 6 份缺失骨架 |
| `.gitignore` 起草粒度 | **含 Python 通用 + custos 特化 `~/.custos/vault/` + examples 环境反向豁免** | 独立仓库 gitignore 必须自足, 不假设 monorepo 根 gitignore 存在 |
| Makefile 目标粒度 | **check/test/lint/fmt/fmt-check/verify + typecheck (未来) + docs (未来)** | Python 项目基础 6 target; typecheck 待 pyright 集成 (README §"Not Included Yet" 之后) |
| Dockerfile 是否本 plan 落地 | **不落**, 留给 Plan 00c examples/supertrend-testnet/ | Docker 与 examples 强绑定, 单独造无用户; ADR-012 v4 阶段 3 signed docker 属 P4 商业化前 |
| CLAUDE.md 层级 | **导航图 + 指针** (~150 行内), 不做百科 | workspace CLAUDE.md 是标杆(每段 3-5 行 + 指向) |

## Task List

**Task 1**: `.gitignore` — 紧急优先, 保护开发环境

- 新文件: `.gitignore` (~40 行)
- 内容: Python 通用 (`.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `dist/`, `build/`, `*.egg-info/`) + custos 特化 (`~/.custos/vault/` 类内容(通配符), `.forge/scratch/`, `.forge/handoff/`, `examples/*/.env`, `!examples/*/.env.example`) + IDE 通用 (`.vscode/`, `.idea/`, `*.swp`)
- 验证: `git check-ignore -v .venv/` 命中, `git check-ignore -v examples/foo/.env` 命中, `git check-ignore -v examples/foo/.env.example` **不**命中
- 失败模式: 已 tracked file (48 file) 不能被新 ignore 覆盖 — 先 `git ls-files` 对比预期 ignore pattern 无交集

**Task 2**: `.claude/settings.json` + `.claude/rules/` 目录骨架 (9 rule 文件)

- 新文件:
  - `.claude/settings.json` (permissions: `Bash(uv run:*)`, `Bash(uv sync:*)`, `Bash(uv lock:*)`, `Bash(pytest:*)`, `Bash(ruff:*)`, `Bash(git status:*)`, `Bash(git add:*)`, `Bash(git commit:*)`, `Bash(git log:*)`, `Bash(git diff:*)`, `Bash(git check-ignore:*)`, `Bash(make:*)`, `Bash(mkdir:*)` + hooks: PostToolUse Write/Edit ruff format --check + ruff check)
  - `.claude/rules/tech-stack.md`
  - `.claude/rules/authority-docs.md`
  - `.claude/rules/mandatory-rules.md` (含 custos non-custodial 4 红线 + 生态精华继承)
  - `.claude/rules/verification.md`
  - `.claude/rules/historical-lessons.md` (精华层继承生态 lesson #9/#11/#14/#17/#21/#22/#25/#26/#27/#28/#33 与 custos 相关的; 完整叙事保留在生态 archive)
  - `.claude/rules/deviation-protocol.md`
  - `.claude/rules/code-style.md`
  - `.claude/rules/common-errors.md`
  - `.claude/rules/progress-management.md`
- 每 rule 文件 > 10 行, 含 custos 特化内容(如 tech-stack 明列 nats-py/pydantic/structlog + optional `nt-runtime` extra 待 Plan 00a 加)
- 失败模式: rule 文件仅通用无 custos 特化 → 违反 skill Step 2.1 "包含项目特定信息" 判定

**Task 3**: `.forge/README.md` — plan 索引 + 编号规范

- 新文件: `.forge/README.md` (~60 行)
- 内容: (a) 编号规范 (`NN[a-z]?-<slug>.md`, custos 用 00a/00b/00c/01 已启用) + (b) 目录约定 (`plans/YYYY-MM/`) + (c) 现有 plan 索引表 (00a/00b/00c/01 各一行短描述 + 状态) + (d) close-out 归档规范
- 失败模式: 索引漏 plan → grep 实证 4 份 plan 全部命中

**Task 4**: `CLAUDE.md` — 项目导航图

- 新文件: `CLAUDE.md` (~150 行内)
- 结构: (a) 这是什么 (1 段 non-custodial 定位) + (b) 子系统边界 (custos ↔ arx 独立开源 vs 云端闭源) + (c) 6 模块导航表 (指向 docs/design/) + (d) forge 工作流入口 + (e) 红线速览 (指向 mandatory-rules.md 不复述) + (f) 常用命令表
- 遵循 workspace CLAUDE.md 精神: **导航图 + 指针, 不是百科** — 每段 3-5 行 + 指向具体权威源
- 失败模式: CLAUDE.md 复述 domain.md / rules 内容 → 违反 skill Step 2.4 "导航图非百科" 判定

**Task 5**: `Makefile` — Python 通用代码质量 target

- 新文件: `Makefile` (~60 行)
- 参考: `alchymia-labs/philosophers-stone/Makefile` (Python 单栈) — 但 custos 更简
- Target: `help` (默认) / `check` (fmt-check + lint) / `test` (uv run pytest) / `lint` (uv run ruff check) / `fmt` (uv run ruff format) / `fmt-check` (uv run ruff format --check) / `verify` (check + test) / `install` (uv sync --extra dev)
- 后续 target (本 plan 不做, 待 Plan 00a 加): `install-nt` (`uv sync --extra dev --extra nt-runtime`) + `typecheck` (待 pyright)
- 失败模式: `make verify` 首跑失败 → 已有 20 test 全绿 (pyproject.toml 已配 pytest-asyncio, 应通过)

**Task 6**: `docs/design/` 迁移 6 份 module docs + 补 overview + architecture 骨架

- 迁移: `docs/{credential_vault,enrollment,nats_client,nautilus_host,reconcile,telemetry_actor}.md` → `docs/design/` (共 6 files, `git mv` 保 history)
- 新建骨架:
  - `docs/design/00-overview.md`: 从 `README.md:1-40` 提炼 custos 定位 + trust boundary + 六件套 (~80 行)
  - `docs/design/01-architecture.md`: 从 `docs/domain.md:85-215` 提炼 6 BC + 上下游图 + Non-Custodial 分层信任边界专章 (~120 行)
  - `docs/design/02-module-design.md`: 索引文件, 表格列 6 module docs + 一句话职责 (~40 行)
  - `docs/design/03-implementation.md`: 技术栈 + 关键 dependency + 项目结构 + 运行方式 (~80 行)
- 保留: `docs/domain.md` 在 `docs/` 根 (顶层纸面 spec)
- 失败模式: 迁移后 workspace `authority-docs.md` 引用 `custos/docs/foo.md` 断链 → grep 生态其他子系统对 custos 的引用, 更新为 `docs/design/foo.md`

**Task 7**: `docs/ops/` + `docs/guides/` — 补 4 份骨架

- 新建:
  - `docs/ops/05-deployment.md`: daemon 部署方式 (a) `pip install custos-runner` + systemd unit 示例 (b) docker container 示例 (待 Plan 00c examples/) (c) 未来 signed release + 可复现构建 (README §"Not Included Yet")
  - `docs/ops/runbook.md`: 运维手册骨架 — 常见故障排查 (vault_locked / venue_auth_failed / code_hash_mismatch / nats 断连) + 恢复流程 + 日志 pattern
  - `docs/guides/04-testing.md`: 测试策略 — 20 test files 概览 + 单测/集成/失败模式测试分层 + pytest fixture / mock 惯例
  - `docs/guides/dev-guide.md`: 开发上手 — `uv sync --extra dev` + `make verify` + 目录结构导航 + 首次 PR 检查清单
- 每份骨架必含项目特定内容 (skill Step 2.6 明确"仅 TODO 占位不算 ✅")
- 失败模式: 骨架仅 TODO 占位 → 违反 skill "文档骨架不是最终交付物" 规则

**Task 8**: 集成验证 + commit

- 验证清单:
  - `test -f .gitignore .claude/settings.json .claude/rules/{tech-stack,authority-docs,mandatory-rules,verification,historical-lessons,deviation-protocol,code-style,common-errors,progress-management}.md .forge/README.md CLAUDE.md Makefile` — 全命中
  - `git check-ignore -v .venv/` 命中, `git check-ignore -v examples/foo/.env.example` **不**命中
  - `python3 -c "import json; json.load(open('.claude/settings.json'))"` 无异常
  - `make verify` 全绿 (20 现有 test)
  - `.forge/README.md` grep 4 份 plan 全部命中 (00a/00b/00c/01)
  - `find docs -name '*.md' | wc -l` = 7 (原) + 6 (design 骨架) + 2 (ops) + 2 (guides) = 17 → 或按迁移后实际
- Commit: `git add <specific files>` (禁 `git add .`, lesson #27) + Conventional Commits scope custos + 每 Task 一 commit 或分批合理分组
- 失败模式: staged file 超范围 → `git status --short` 核对拒 commit

## 失败模式覆盖契约表 (lesson #17)

| 失败模式 | 触发点 | 检测方法 | 处理 |
|---|---|---|---|
| `.gitignore` 覆盖已 tracked file | Task 1 | `git ls-files` cross-check pattern | 起草前对比排除交集 |
| examples/ .env.example 被错误 ignore | Task 1 | `git check-ignore -v examples/foo/.env.example` 应不命中 | `!examples/*/.env.example` 反向豁免 |
| 规则文件仅通用无项目特化 | Task 2 | grep custos 特有关键字 (non-custodial / G6 / vault) 每 rule ≥ 1 命中 | 内容审查 |
| settings.json JSON 语法错误 | Task 2 | `python3 -c "json.load(open(...))"` | fail-fast |
| CLAUDE.md 复述规则内容 | Task 4 | 与 mandatory-rules.md 内容交叉查重, 重复段 > 3 行 → 警告 | 重写为指针 |
| Makefile `make verify` 首跑 fail | Task 5 | CI 或本地跑 | 修复原因(通常 ruff 配置或 pytest-asyncio 未配) |
| docs 骨架仅 TODO 无内容 | Task 6/7 | grep "TODO" 计数 vs 段落总数 | 补齐项目特定内容 |
| .forge/README.md 漏 plan | Task 3 | grep 每份 plan 文件名命中 | 补录 |

## File Inventory

| 文件 | 类型 | 决定 |
|---|---|---|
| `.gitignore` | 新建 | Python + custos 特化 |
| `.claude/settings.json` | 新建 | permissions + hooks |
| `.claude/rules/tech-stack.md` | 新建 | Python 3.11+/uv 技术栈 |
| `.claude/rules/authority-docs.md` | 新建 | domain.md + design/ + README 为权威 |
| `.claude/rules/mandatory-rules.md` | 新建 | non-custodial 红线 + 生态精华 |
| `.claude/rules/verification.md` | 新建 | make verify 命令清单 |
| `.claude/rules/historical-lessons.md` | 新建 | 生态 lesson 精华继承 (custos 视角) |
| `.claude/rules/deviation-protocol.md` | 新建 | 低/中/高风险偏离协议 |
| `.claude/rules/code-style.md` | 新建 | ruff 88 + custos 特化 (日志全英文, 服务器约束) |
| `.claude/rules/common-errors.md` | 新建 | Python + custos NT lifecycle 陷阱 |
| `.claude/rules/progress-management.md` | 新建 | SemVer + 状态标记 + close-out 模板 |
| `.forge/README.md` | 新建 | plan 索引 + 编号规范 |
| `CLAUDE.md` | 新建 | 项目导航图 (~150 行) |
| `Makefile` | 新建 | help/check/test/lint/fmt/fmt-check/verify/install |
| `docs/credential_vault.md` | git mv | → `docs/design/credential_vault.md` |
| `docs/enrollment.md` | git mv | → `docs/design/enrollment.md` |
| `docs/nats_client.md` | git mv | → `docs/design/nats_client.md` |
| `docs/nautilus_host.md` | git mv | → `docs/design/nautilus_host.md` |
| `docs/reconcile.md` | git mv | → `docs/design/reconcile.md` |
| `docs/telemetry_actor.md` | git mv | → `docs/design/telemetry_actor.md` |
| `docs/domain.md` | 不动 | 保留 `docs/` 根 (顶层纸面 spec) |
| `docs/design/00-overview.md` | 新建 | 从 README 提炼 |
| `docs/design/01-architecture.md` | 新建 | 从 domain.md §0.2 提炼 |
| `docs/design/02-module-design.md` | 新建 | 6 module docs 索引 |
| `docs/design/03-implementation.md` | 新建 | 技术栈 + 依赖 + 项目结构 |
| `docs/ops/05-deployment.md` | 新建 | daemon 部署方式 |
| `docs/ops/runbook.md` | 新建 | 运维手册骨架 |
| `docs/guides/04-testing.md` | 新建 | 测试策略 |
| `docs/guides/dev-guide.md` | 新建 | 开发上手 |

## 验收清单

- [ ] `.gitignore` 命中 `.venv/` `__pycache__/` 等, 未覆盖已 tracked file, `examples/*/.env.example` 反向豁免生效
- [ ] `.claude/settings.json` JSON 合法, permissions 含 `Bash(uv run:*)` 等 12 项, hooks 含 ruff format --check + ruff check
- [ ] `.claude/rules/` 9 份规则文件全存在, 每份 > 10 行, 含 custos 特化关键字
- [ ] `.forge/README.md` 索引 4 份 plan (00a/00b/00c/01), grep 每 plan 文件名命中
- [ ] `CLAUDE.md` 存在, ≤ 150 行 (导航图非百科), grep 与 mandatory-rules 重复段 ≤ 3 行
- [ ] `Makefile` 8 target 全落地, `make help` 有输出, `make verify` 20 test 全绿
- [ ] `docs/design/` 12 file (6 迁 + 4 新骨架 + 已有 domain.md 不算, 归 docs/ 根), 骨架每份含项目特定内容 (非仅 TODO)
- [ ] `docs/ops/` `docs/guides/` 4 骨架含项目特定内容
- [ ] 每份骨架 file grep "TODO" 计数 < 段落总数的 30%
- [ ] `pytest tests/` 全绿 (基础设施不动源码, 应无影响)
- [ ] 全 Task commit 用 `git add <specific file>`, `git status --short` 核对无 pre-staged 污染

## 偏离与改进日志 (Deviation Log)

### DEVIATION: bootstrap 编号后置于 00a-c
- **等级**: 低
- **原因**: custos 从 arx `runner/` subtree split 后, 用户直接起草 execution plan (00a-c), 未先跑 forge bootstrap 建基础设施
- **影响**: plan 编号顺序视觉上 01 在 00a-c 之后, 但逻辑上是基础设施先行
- **决定**: 编号 `01-forge-bootstrap.md` 与 00a-c 并列 `2026-07/`; 通过本段偏离日志 + `.forge/README.md` 索引段明记
- **更新的文档**: 本 plan 头部"Blocks (逻辑上)" 段 + `.forge/README.md` (Task 3)

(执行阶段可继续追加)

## 完成报告 (Close-out Report)

(执行完成填写)

## 下一步 (Next)

Plan 01 close-out 后:
- 后续 Plan 00a/00b/00c 执行有 `make verify` 保护
- 外部审计员可单仓 clone custos 有完整 forge 基础设施
- 后续 plan (如 `nt-runtime` extra 加入 / OKX venue 支持) 直接沿用编号 02/03/...
