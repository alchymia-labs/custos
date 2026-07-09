# 历史教训 (custos)

本文件继承 workspace `the-alephain-guild/.claude/rules/historical-lessons.md` 中与 custos
开发直接相关的**精华教训**. 独立仓库 clone 场景外部开发者仍能读到 lesson 核心防护;
完整叙事保留在生态 archive, 本仓库只留 rule 卡片 + custos 特化 binding.

> **custos 内部 lesson 用 `C1` `C2` … 前缀区分生态数字编号** (见文末"记录新 lesson")。

## C1 CEO override 单 plan 依赖跳过路径 (custos 独立仓形态) — 生态 lesson #38 具体化 (2026-07)

- **事件**: Plan 00c (G6 gate capability + Binance testnet/live) 头部声明 `Depends on: Plan 00a + 00b`, 但 00b (telemetry 桥) 未 close-out。CEO wukai 2026-07-07 经 `/forge:execute-team` AskUserQuestion 显式选择先做 00c (核心 G6 gate/testnet/live 与 00b 遥测桥独立)。属高风险偏离 (跳过声明的 plan 依赖), 走生态 lesson #38 CEO override 记录路径。
- **根因**: plan 依赖声明是保守全序 (00a→00b→00c), 但实际 00c 主干与 00b 正交; CEO 战略判断"先放行 live 通道能力, 遥测观测度后补"。custos 独立仓无 ADR 框架, 需把 override 记录落到本仓内自足载体。
- **预防 / 4 件套 (custos 独立仓形态)**:
  - ① CEO 决定: handoff packet §0 (`.forge/handoff/2026-07/00c-execute-team-packet.md`, gitignore 会话物件, 但决策上下文已复制进本 lesson + plan DEV 条)
  - ② 偏离登记: Plan 00c 偏离日志 `DEV-00c-DEP-SKIP-CEO-OVERRIDE` (高风险条)
  - ③ 权威文档: custos 无 ADR → 落 `.forge/README.md` 索引 00c 行 `Depends on` 脚注 ¹ (生态 lesson #38 用 ADR revision, custos 用 plan 索引脚注等效)
  - ④ 本 C1 lesson (先例记录)
  - 四件套齐 = 与 Council/ADR 等效的决策留痕, 非静默 override。后果诚实声明: e2e 观测面部分启用 (00b 未落地, testnet 真跑 fill/OrderDenied 只本地 structlog)。
- **未来同型 (custos 内 plan 依赖跳过)**: 先看四件套 (CEO 决定 + DEV 条 + `.forge/README.md` 脚注 + 本文件 Cx lesson) 是否齐, 齐则批准, 缺则回补。

**Binding**: 生态 `deviation-protocol.md` CEO override 例外路径 (lesson #38) 在 custos 独立仓的等效落点 = plan DEV 条 + `.forge/README.md` 索引脚注 + 本 C1。

## #9/#11/#18/#37 「不信推理信实证」— 全场景适用

- **触发**: fix / review / 起 plan / spawn prompt / SendMessage / 编辑权威 spec 时
  引用代码符号 (enum 变体 / struct 字段 / fn 签名 / 表名 / API 字段) 未 grep 实证
- **防护**: 编辑前必 grep 实证一次, 尤其对称语义 (`create ↔ delete` / `on ↔ off` / `tripped
  ↔ restored`) 不豁免, 双向 grep
- **custos 特化**: NT lifecycle 方法名 (`start` / `stop` / `dispose` / `wait_for_state`)
  / NATS subject naming / Pydantic model 字段名 编辑前必 grep 源定义

## #14/#30/#33/#33b Foundation Scan Gate — 四维方法论

- **触发**: 起 plan / 起 fix / spawn agent
- **防护**: 起草前系统扫骨架 (空间维 #14) + grep migrations DDL (命名空间维 #30) +
  上游 plan close-out 后 as-of 时间锚 (时间维 #33) + 影响面多轮迭代 (层次维 #33b)
- **custos 特化**: 6 模块骨架小 (`ls src/arx_runner/`) + wire fixture 现状扫
  (`ls tests/test_wire_*.py`) + 上游 arx Plan 60 subtree split 影响的现状 as-of 时间锚

## #17 happy-path 测试全绿 ≠ 失败模式覆盖

- **触发**: 起 plan / TDD 实现
- **防护**: 起 plan 声明失败模式覆盖契约 (NATS down / vault_locked / g6 gate deny /
  wire schema drift / async task 异常 silent drop / Decimal 精度丢失)
- **custos 特化**: 已有 `test_telemetry_actor_failure_modes.py` / `test_nats_wal_resilience.py`
  实践该原则; 新增模块须并行加 `test_*_failure_modes.py`

## #21 零静默红线 — silent 路径必接 structlog

- **触发**: 写 try/except / fire-and-forget / drop policy / WAL 暂存 / queue overflow
- **防护**: silent 控制流必须 `structlog.get_logger().warning("<event_name>", **context)`,
  否则加 `# noqa: SILENT-OK <reason>` 注明 fail-safe 理由
- **custos 特化**: telemetry_actor / nats_client 全数覆盖 (对账不静默 = non-custodial 承重墙
  可观测性)

## #22/#28 多层 fail-fast + 独立可测

- **触发**: 设计红线 / 承重墙 / 安全承诺
- **防护**: 多层防御 (config / connection / repository / DDL / SQL where) + 每层独立
  可测 (relaxed-double test 证明 inner layer 不是 dead branch)
- **custos 特化**:
  - Non-Custodial 红线 0.1 (Key 不出进程) 多层守: telemetry_actor 白名单 + structlog
    processor 脱敏 + envelope schema 只允许公开字段
  - G6 gate (红线 0.2) 多层守: `nautilus_host.start()` gate + `LIVE_MODE` env + `paper_only`
    reconciler 默认

## #25 反 fabricated close-out — 契约表测试名必 grep 实存

- **触发**: close-out 报告 / 契约表 / 验证清单
- **防护**: 契约表点名的 `test_*` 函数必须 `grep -rn 'def test_X' tests/` 实证真存在;
  数字统计对齐
- **custos 特化**: close-out 前跑 `pytest --collect-only tests/` 对比契约表

## #26 `pub String` boundary / boundary constant 校验

- **触发**: 边界字段 (fs path / NATS subject / SQL string interp / cookie / env var / storage key)
- **防护**: smart constructor 收口 invariant; 边界裸用前 `validate_*_for_<sink>` 拦截
- **custos 特化**:
  - `TenantId` / `RunnerId` / `StrategyId` 不裸 str 拼 NATS subject
  - `nats.subject` 构造用 `build_subject(tenant, kind, *parts)` 函数收口 (参考
    `test_subject_builder_contract.py`), 拼接前对每个 part 校验字符集/长度

## #27 commit scope discipline — 前必 `git status --short`

- **触发**: commit 前 (含 fix / execute / bootstrap 等各种 stage)
- **防护**: `git add <specific-file>` (禁 `.` / `-A`); commit 前 `git status --short` 核对
  staged 范围, pre-staged 污染即 `git restore --staged` 退出
- **custos 特化**: 独立仓库虽然无跨仓库 add 风险, 但 workspace 场景内改 custos + arx 双仓
  时同样适用; hooks 自动 stage 也可能污染, commit 前核对是双保险

## #29 校验类操作不覆盖 host

- **触发**: 建 config 文件 / 跑 dry-run 校验 / 生成参考 fixture
- **防护**: 用 `/tmp/` 临时路径 + `[ -f <path> ] || cp` 防御性 cp + 不覆盖不 rm 用户真实文件
- **custos 特化**: `credential_vault` test 用 `mktemp -d` fixture, 绝不碰用户真实
  `~/.custos/vault/`

## #34 teammate 收 pre-merge 指令需先 git log 核实

- **触发**: 多 session 编排 / worktree merge 后收到旧 context 指令
- **防护**: 收到关键指令前 `git log -1` + `git worktree list` 核实当前仓库状态, 状态变化
  即上报
- **custos 特化**: 独立仓库单人开发场景少, 但 workspace 场景内多 agent 并行改 custos +
  其他子系统时适用

## #35 boundary constant rename fanout

- **触发**: storage key / cookie name / env var / NATS subject prefix / pip 分发名 / Python
  module 名改名
- **防护**: 起草 rename plan 时 grep 全仓消费者, 显式列改名清单; zustand-类持久化改名
  需外加显式 `removeItem(oldKey)`
- **custos 特化**: Python module 名 `arx_runner` → `custos_runner` (README 已声明 follow-up)
  必须走此协议, 涉及 40+ import site fanout

## #40 含 defer 决策的红线 gate close-out 声明必须显式降级 partial scope — code test 覆盖 ≠ runtime wire 兑现

- **触发**: plan close-out 涉及红线 gate (mandatory-rules §0) 且 plan 内含 defer 决策 (DEV-* 记录)
- **防护**: close-out 声明必须**显式区分三层** —
  (a) **code-level test coverage** (unit / integration 覆盖了什么逻辑) /
  (b) **runtime wire 接线兑现** (composition root 是否真接线) /
  (c) **defer scope** (哪些接线延后到 follow-up plan)。
  不能承袭红线名 (如"Key 不出进程" / "G6 不绕过") 当兑现声明 — 红线名是设计意图 (vision),
  兑现声明是能力实现 (reality), 两者严禁混淆
- **custos 特化**: plan 模板 "完成报告" 章节固定含 "红线 gate 满足度" 表 —
  每条红线一行: `red_line | code_coverage | runtime_wire | defer_status | follow_up_plan_ref`。
  Plan 03 是本 lesson 落地**模板样本** (`FailureEvent.reason_code` 撤除标注 "契约认知修正" 非 defer)
- **与 #17/#22/#28 合并适用**: #17 缺失失败模式测试 / #28 分句借位无 guard / #22 dead-branch
  遮蔽 / **#40 unit-test ≠ runtime wire (close-out 声明侧, 接线 defer 时必须显式降级)**

## 生态 lesson 完整清单

以下 workspace lesson 与 custos 关联度较低, 但保留编号占位便于跨引用:

- #1-#8, #10, #12, #13, #15, #16, #19, #20, #23, #24, #31, #32, #36 (workspace 特化,
  完整叙事见 workspace `historical-lessons.md`, 独立 clone 时可视为背景阅读, 不阻塞 custos 开发)

## 记录新 lesson (custos 内)

custos 自身开发中出现的 lesson 直接在本文件顶部按 workspace 模板追加:

```markdown
### #<N> <标题> (<YYYY-MM>)

**事件**: {发生了什么}

**根因**: {为什么会发生}

**预防**:
- {措施}

**Binding**: {落到 rule / hook / skill 哪里}
```

编号避免与 workspace 冲突: custos 内部编号用 `C1` `C2` ... 前缀区分.
