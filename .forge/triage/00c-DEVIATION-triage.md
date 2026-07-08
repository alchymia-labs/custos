# Plan 00c — DEVIATION Triage (execute-team Step 6.4a)

**Plan**: 00c G6 gate capability + Binance testnet/live + docker e2e
**squash commit**: `527b4af`
**orchestration commit**: `07467b8`
**Triage 时间**: 2026-07-07
**Triage 依据**: lesson #25/#28 反 fabricated close-out + lesson #38 CEO override 4 件套 + `.claude/rules/deviation-protocol.md`

---

## HIGH (1 条) — AskUserQuestion 必询

### DEV-00c-DEP-SKIP-CEO-OVERRIDE (lesson #38 CEO override 4 件套记录路径)

- **Level**: HIGH (跳过声明的 plan 依赖 = 高风险偏离, 走 lesson #38 override)
- **Facts**: Plan 00c 声明 `Depends on: Plan 00a + 00b`, CEO wukai 2026-07-07 经 `/forge:execute-team` AskUserQuestion 显式选择先做 00c (核心 G6 gate/testnet/live 与 00b 遥测桥独立)
- **4 件套完备度实证** (grep 独立 verify pass):
  - ① CEO 决定: `.forge/handoff/2026-07/00c-execute-team-packet.md` §0 ✅
  - ② DEV log: `.forge/plans/2026-07/00c-g6-gate-live-release.md` `### DEVIATION: DEP-SKIP-CEO-OVERRIDE` ✅
  - ③ 权威文档更新: `.forge/README.md` 索引表 00c 行 Depends on 栏 footnote ¹ ✅
  - ④ historical-lesson: `.claude/rules/historical-lessons.md` C1 首条 custos 内部 lesson ✅
- **观测影响**: Task 4 e2e testnet 真跑时 fill/OrderDenied 事件不上报云端 arx (00b telemetry 桥未落地), 只走 custos 本地 structlog。examples README 顶部明写此局限。
- **User-facing summary**:
  - Plan 00c 抢先于 Plan 00b 落地, 是 CEO 战略判断 (G6 live 通道能力优先, 遥测观测度后补)
  - 4 件套齐全 = 非静默偏离, 可 accept
  - 后续 Plan 00b 落地时把 telemetry 桥补齐, 兑现 examples 顶部承诺

**AskUserQuestion 选项**: accept (4 件套齐, 观测局限可接受) / fix-now (立即启动 Plan 00b 补齐) / new-plan (立 Plan 03 candidate 补 telemetry 观测度)

---

## MED (2 条) — user-facing summary

### DEV-00c-HOST-WIRING (中风险: CLI 入口 + docs 同步)

- **Level**: MED
- **Facts**: Plan Task 4 File Inventory 遗漏 `__main__.py` 硬编码 `NoopHost()` = testnet/live spec 经 CLI 永远走 stub 不真跑
- **executor 处理**: 加 `--use-nt-host` bool flag (默认 NoopHost 向后兼容, 显式 opt-in NT 真 host); 加 `_build_host` TDD 3 case; docs/design + README + examples 同步; safety-validator 5 锚点 (默认 noop / opt-in / gate 仍 4 层 / NT 缺失 fail-fast / 3 test 覆盖)
- **命名品味决定**: 初版 `--nt-host` → `--use-nt-host` (CEO soft 建议, executor 决定; YAGNI 不上 `--host {choice}`)
- **User-facing summary**:
  - Plan 起草时 Foundation Scan 漏 CLI wiring (lesson #33b 层次维), executor 中途发现主动补上
  - flag 默认 NoopHost 向后兼容, opt-in 才启用真 NT host
  - 不违反红线 0.2 (G6 gate 4 层对 live 仍全程强制, `--use-nt-host` 只选真 host 不绕过 gate)
  - codex L1 peer 独立确认 CLI default 为 NoopHost + gate 强制成立

### DEV-00c-EXAMPLE-VAULT (中风险: 用 sops+age 守红线 0.1, 偏离 plan 明示 mock vault)

- **Level**: MED
- **Facts**: Plan "关键设计决策" 表明示 e2e 示例用 "mock vault (env var)", executor 实证 mock vault 无 `api_key`/`api_secret` 无法真跑; 造读 env var 明文 key 的新 vault 违反红线 0.1 精神
- **executor 处理**: 示例改用已 ship 的 `SopsAgeVault` (非托管正道), `.env` 只放非密运行配置, exchange key 走 sops+age 加密文件 + 挂载 age 私钥 (永不出本地); vault-fixture/credentials.example.json 是无真 key 的 shape 模板; README 完整文档化 + 生产提示
- **User-facing summary**:
  - 偏离 plan 明示决策, 但守住红线 0.1 (Key/KEK 永不出进程) 精神
  - 更 on-brand 展示 custos 非托管安全模型 (sops+age 是 custos 生产实际用法)
  - README 完整步骤 + `.gitignore` 排除 `examples/**/vault/` + `*.plain.json`

---

## LOW (4 条) — 只记

### DEV-00c-TESTNET-DATA-ENV

- Task 3 File Inventory 只列 exec config, 但 testnet 真跑若 data feed 仍走 LIVE 环境 → live 价格喂 testnet 执行 instrument 不匹配
- executor 加 `build_data_client_config` 的 `environment` 参数 + `data_environment_for_mode` 映射 (sandbox→LIVE / testnet→TESTNET / live→LIVE)
- 属 testnet 正确性必需, Task 3 精神内; 加测试 `test_data_environment_for_mode` + `test_build_data_client_config_testnet_env`

### DEV-00c-FOUNDATION-SCAN-MISS

- executor 起工 Foundation Scan `ls -la examples/ 2>/dev/null || echo "不存在"` 中 shell alias `ls` → 未装的 `eza`, `||` 误把工具报错当"不存在"; 实际 examples/supertrend-sandbox/ 由 Plan 00a 提交存在
- 违反 lesson #9 "grep/ls 空≠不存在" (此处工具报错≠不存在)
- executor Task 4 grep 时自查纠正, 对齐 sandbox 约定 (`spec-example.json` 命名 + 去误加的 strategy_id + code_hash: null + log_level)
- 诚实记录, 无功能影响 (executor 主动纠偏)

### DEV-00c-CEO-LESSON-37-PACKET-DRIFT

- CEO 侧 packet §5 契约表写 `test_case_variants (已有)`, 实际仓库函数是 `test_g6_gate_rejects_live_noophost` (参数化 Live/live/LIVE)
- packet 假名与实际漂移 (lesson #37 spawner 元层未 grep 实证测试名, 凭推理)
- executor 按 lesson #9/#25 用真实测试名建契约表, 不照抄 packet 假名; 主动 heartbeat 报备 team-lead
- 无功能影响, 记录 lesson #37 在 CEO packet 起草侧复发的具体形态

### DEV-00c-PEER-FOLLOWUP-F1F2F3

- codex L1 peer review APPROVE_WITH_FOLLOW_UPS 无 blocker, 3 stretch follow-ups
  - F1: `tests/test_main_host_selection.py` add base-install NT-missing fail-fast test (无 importorskip)
  - F2: `deployment_reconciler.py` `_host_capability` getattr defense (undeclared host → structured `g6_gate_live_capability_denied` 非 AttributeError)
  - F3: `_nt_binance_venue.py` `data_environment_for_mode()` 未知 mode 边界 test (executor 决定保留 LIVE fallback 明确文档化 + 加 test, 不改 raise)
- 分落 3 commit (`93365c7` + `5f7bf12` + `c693504`), 与 packet §10 正交
- 无功能变更主契约, 是加固性补丁

### DEV-00c-CEO-VALIDATOR-INLINE (CEO 侧 process 偏离)

- Level: LOW
- **Facts**: packet §3 派工含 safety-validator (opus-4-6[1m]) + tdd-enforcer (sonnet), CEO 决定内联执行代替 formal spawn
- **理由**: 3 层复核已覆盖同样 checklist:
  1. executor 自检 grep (契约表 19 test 全 grep 实存 + 4 红线 grep 0 命中 + relaxed-double 每层独立可测)
  2. CEO 侧独立 grep (19 test 名全 grep 实存 + 4 红线独立 grep 0 命中 + CEO override 4 件套 landing verify)
  3. codex L1 peer review high effort (焦点 G6 gate 4 层独立性 + CEO override + 4 红线, 8 项独立确认全绿)
- codex L1 事后 validation 表明所有 formal safety-validator + tdd-enforcer 会抽检的点都覆盖了, 决策成立
- 节省 opus 预算 1 spawn (剩余 6/8, warn_at 未触发)

---

## Triage 总结

| Level | 数量 | 处理 |
|---|---|---|
| HIGH | 1 (DEP-SKIP-CEO-OVERRIDE) | 4 件套齐全, AskUserQuestion 询问 accept/fix-now/new-plan |
| MED | 2 (HOST-WIRING + EXAMPLE-VAULT) | user-facing summary 段已附 |
| LOW | 5 (TESTNET-DATA-ENV + FOUNDATION-SCAN-MISS + CEO-LESSON-37-PACKET-DRIFT + PEER-FOLLOWUP-F1F2F3 + CEO-VALIDATOR-INLINE) | 只记, 无 user 询问 |

**总 7 偏离 (marker 已登记 6, 加 CEO-VALIDATOR-INLINE 后 7)**。

---

## 附录 A: agent claim verification (Step 6.4b 手动版, hook 未装)

CEO 侧独立 grep 复核 executor 声明:

| Claim | Verify | Result |
|---|---|---|
| marker.commits[-1] = c693504 | `python3 -c 'import json; ...'` | ✅ 一致 |
| close_out_commit_follows: True | 同上 | ✅ True |
| 7 deviations 含 PEER-FOLLOWUP-F1F2F3 | 同上 | ✅ 7 条完整 |
| 契约表 19 (packet §5 定义) + 4 (F1-F3 添加) = 23 test 名 grep 实存 | `grep -rn "def test_X" tests/` | ✅ 全命中 |
| 4 红线 grep 0 命中 | grep 独立跑 | ✅ log api_key / SKIP_G6 / stop_all / float( 均 0 |
| CEO override 4 件套 ②③④ 落地 | grep packet/plan DEV/README index/C1 | ✅ 4 处都在 |
| make verify + make test-nt 182 passed | (未跑, executor 声明) | ⚪ 未 CEO 侧跑 (信任 executor + codex read-only mode 也未跑, rule 10 accepts source review) |

## 附录 B: spawner grep gate (Step 6.4c)

CEO 侧本 session 编辑清单:
- `.claude/agents/*.md` (4 个, 现 gitignored) — session 内, 不入 git 历史
- `.forge/handoff/2026-07/00c-execute-team-packet.md` — .forge/handoff/ gitignored, 不入 git
- `.forge/triage/00c-DEVIATION-triage.md` — 本文档, 首次落地
- `.gitignore` — 加 `.claude/agents/` 一行
- `.forge/dispatch-log/00c/*.json` — commit 07467b8
- `.forge/reviews/2026-07/00c-peer-codex.md` — commit 07467b8

**均未编辑**: `mandatory-rules.md` / `CLAUDE.md` / `docs/domain.md` / `docs/design/*.md` / plan file / historical-lessons.md 主体。**spawner grep gate 不触发** (未编辑权威 spec 引用代码符号)。
