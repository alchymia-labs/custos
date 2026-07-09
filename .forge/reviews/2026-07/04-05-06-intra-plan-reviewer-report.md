# Intra-Plan Reviewer Report — Plan 04/05/06

> **Role**: intra-plan-reviewer (custos plan-team, Wave C). Model: claude-opus-4-6[1m].
> **Scope**: 内部结构质量 (§6.A-D) + 跨 plan File Inventory 交集分析 (§6.E, core value) + 契约冻结点核对 (§6.F).
> **Method**: 三 plan 全文读 + evidence-scout report 为事实基线 + drafter marker 数字独立复核 + `tests/` 目录 grep 实证 (lesson #25/#C2).
> **实证纪律**: 凡涉事实断言 (test 名存在 / 文件被多 plan touch) 均附 `file:line` + grep 命令原文; 无实证锚点标 UNVERIFIED.
> **as-of**: main HEAD `55b079d` (Plan 05 skeleton + 04/06 File Inventory 同步), 2026-07-09. Plan 04/05/06 均为 refined 稿 (未 close-out, 未 commit — Wave D commit gate).

---

## 汇总 verdict

- **Plan 04** (红线 0.3 runner fallback): **APPROVED_WITH_FOLLOW_UPS** — 结构完整、失败模式覆盖强、红线 gate 三层声明教科书级; 仅 NEW test 计数轻微不一致 + 共享文件协调 (跨 plan) 需处理
- **Plan 05** (结构重构 + rename): **APPROVED_WITH_FOLLOW_UPS** — rename fanout 覆盖全、契约冻结点清晰、G6 relaxed-double 保全; `test_smoke` 命名 imprecision + teams.yaml touched_paths glob 归属需明确
- **Plan 06** (ps supertrend 迁移): **APPROVED_WITH_FOLLOW_UPS** — 集成路径 (a) 证据充分、vendoring 方案 A 论证扎实、跨仓编排已记; credential 红线 0.1 失败模式依赖 existing test
- **Cross-plan overlap**: **SERIAL_REQUIRED** (仅 2 个热点文件) — Plan 04 与 Plan 06 均在 Plan 05 之后 **modify `src/custos/engines/nautilus/host.py`** + **`docs/domain.md:103` 同一 field list**; plan 声明 04‖06 可并行, 但这两文件不加 owner/merge 协议并行必冲突 (lesson #16 execute-time 形态)。其余文件依赖序自然消解, 可并行。

**lesson #25/#C2 核心结论**: 三 plan 契约表所有 `✓existing` test 名 **全部 grep 实证真存在, 零编造** (Plan 04 4/4 命中且行号精确匹配 / Plan 05 17/17 命名函数命中 / Plan 06 9/9 命中 + ps 侧 supertrend test 存在)。无 CRITICAL fabricated-test finding。

---

## Plan 04 findings

### §6.A 内部结构完整性 — PASS
- 14 Task 全部原子 + 独立 committable, 每 Task 含 红/绿/failure-mode/commit message 四段; 每 Task 末尾 `make verify` 全绿承诺明列 (line 245 铁律段)。
- File Inventory 三段 (A 源码 / B 测试 / C 文档) 每文件 `create|modify` + `现状(test -f)` 预检齐全 (line 205-238)。
- **偏离日志完整**: 7 条 DEV (3 CEO 决策点 DP1/DP2/DP3 elevate 不静默 + 4 drafter 决定), BOTH options 列全 (line 438-481)。
- close-out (T-final) 为强制末尾 task, 含契约表 test grep 实存 gate (lesson #25) + git status 核对 (lesson #27) (line 351-358)。
- Depends on / START gate / Blocks 声明清晰 (line 8-9, 68-81): START = Plan 05 T4.2 done + UPSTREAM PROTOCOL FROZEN 声明。
- **轻微**: File Inventory 合计行 (line 240) 有内联自更正 "A 8 (5 create + 3 modify... 实为 3 create + 5 modify)" — 更正后数字与表一致 (3 create: local_cap/state_snapshot/fallback_breaker; 5 modify), 仅文字凌乱, 非错误。

### §6.B Failure-mode 覆盖 (lesson #17) — STRONG
- Track 5 chaos suite (arx-disconnect fault injection) + long-run 是本 plan 亮点; 失联硬门 6 行加粗标注 (T1.3/T3.2/T4.3/T5.1/T5.2, line 380)。
- **arx-disconnect 覆盖度充分** (brief 关注点): `test_cap_exceeded_during_disconnect_still_rejects` / `test_zombie_detection_works_when_arx_disconnected` / `test_breaker_trips_during_arx_disconnect` / `test_arx_disconnect_cap_breaker_zombie_continue` / `test_arx_disconnect_long_run_guards_persist` — 每层守护均有失联期间断言。
- lesson #22/#28 relaxed-double 独立可测: cap (`test_cap_is_live_guard_relaxed_double`) + breaker (`test_breaker_is_live_guard_relaxed_double`) 各证 live guard 非 dead branch。
- lesson #40 runtime-wire: `test_reconciler_constructs_all_three_guards` 证 composition root 实接线非仅定义。

### §6.C 契约表测试名 grep 实证 (lesson #25) — PASS (4/4 existing 命中, 行号精确)
- `grep -rn "def <t>" tests/` 逐一实证 4 个 `✓existing` (line 410-413):
  - `test_node_dict_recursive_no_credential` → `tests/test_credential_lifecycle.py:109` ✓ (契约表标注 :109, 精确匹配)
  - `test_float_money_field_rejected` → `tests/test_telemetry_money_contract.py:51` ✓ (标注 :51, 匹配)
  - `test_nt_messagebus_disconnected_logs_and_degrades` → `tests/test_telemetry_nt_bridge.py:316` ✓ (标注 :316, 匹配)
  - `test_wal_stashes_telemetry_while_disconnected_and_drains_on_connect` → `tests/test_nats_client_telemetry.py:105` ✓ (标注 :105, 匹配)
- NEW test (~34 个) 全标注 `NEW`, 无一伪造为 existing。名称与 Task 语义一致, spot-check 通过。

### §6.D 红线守护 + lesson #40/C40 close-out 分层 — EXEMPLARY
- 红线 gate 满足度表 (line 419-431) 四条红线全列, **三层区分清晰** (code_coverage / runtime_wire / defer_status)。红线 0.3 runtime_wire 显式指向 T4.3 composition root grep 实证; snapshot→arx 消费端 defer 显式声明 (follow_up_plan_ref = arx plan)。
- 兑现范围声明 (line 430) 明确 "不承袭红线名当兑现声明" — 本 lesson #40 落地样本。
- silent path structlog (lesson #21) 在 Task 铁律段 (line 246) + 各 breaker/cap/zombie 事件名明列。

---

## Plan 05 findings

### §6.A 内部结构完整性 — PASS
- 17 Task (含 close-out), 8 Track; rename/move 类 Task 的红→绿以 `grep arx_runner` 命中→0 + `make verify` 定义 (line 251), 每 Task 原子可 commit。
- File Inventory 五段 (A rename/move 14 + B create 18 + C test import 31 + D config/docs 19 + E 归档 no-change) 覆盖 scout 60 基线全部非归档项 + 18 净新; E 段明确归档 `arx_runner` 故意保留 (goal §"全仓 0 命中 except archived plan .md")。**归档差额解释到位** (line 241-245)。
- 偏离日志 6 DEV (3 CEO DP + 3 drafter), BOTH options 列全。
- 切片建议 (05a Tracks 1-4+8 契约冻结路径 / 05b Tracks 5-7 加性) 清晰 (line 430-433)。

### §6.B Failure-mode 覆盖 — ADEQUATE (rename plan 特性)
- rename 类失败模式 = `ModuleNotFoundError` via `make verify` + 红线 test (credential_lifecycle / telemetry_money_contract / g6_gate) 无退化证明。对纯结构重构合理。
- G6 gate 5 relaxed-double + host×mode 6 格矩阵全部 existing 保留 (契约不变名换)。
- **rename 期间 test suite 断层 (brief 关注点)**: T1.1 单 Task 原子 rename 14 src + 31 test import + pyproject (line 255-261) 是大 big-bang 步; 若中断则 suite 断裂。plan 以"单原子 commit + make verify 末尾全绿"处理, 且 multi_session_scope=true 标注。可接受 — 属 rename 原子性固有代价。

### §6.C 契约表测试名 grep 实证 (lesson #25) — PASS (17/17 命名函数命中)
- `grep -rln "def <t>" tests/` 逐一实证 17 个命名 `✓existing` (line 443-455) 全命中:
  - host 选择 3: `test_build_host_defaults_to_noop`/`test_build_host_nt_when_flagged`/`test_build_host_nt_without_runtime_fails_fast` → `tests/test_main_host_selection.py` ✓
  - G6 5 relaxed-double: `test_layer1_capability_relaxed_double`/`test_layer2_venue_unsupported_relaxed_double`/`test_layer3_code_hash_mismatch_relaxed_double`/`test_layer3_code_hash_missing_relaxed_double`/`test_layer4_credential_scope_violation_relaxed_double` → `tests/test_g6_gate_capability_e2e.py` ✓
  - NoopHost 拒 live 3 / 非 live 旁路 / undeclared 2 / mode matrix / NT capability 2 全命中 (见 grep 输出)。
- 4 NEW test 全标注 NEW (`test_engine_protocol_contract` / `test_nautilus_host_implements_engine_protocol` / `test_cli_engine_unknown_rejected` / `test_cli_engine_defaults_to_nautilus`)。

### §6.D 红线守护 + close-out 分层 — PASS
- 红线 gate 表 (line 466-475): 0.2 G6 显式声明"重构 gate 为 Protocol-based, 4 层 + 5 relaxed-double 全保留"; 0.3 显式标 Tier-2 defer 到 Plan 04; 重构无退化声明 (line 475) 正确区分"重构后兑现能力不变 ≠ 新增兑现"。lesson #40 应用正确。

### §6.E-relevant: Plan 05 是 teams.yaml 唯一 owner
- 见 §6.E FU-C1 — teams.yaml safety.touched_paths 归 Plan 05 T1.2 独占改, 04/06 引用不改 (正确)。

---

## Plan 06 findings

### §6.A 内部结构完整性 — PASS
- 12 Task 跨 6 Track, TDD 节奏 (红→绿→make verify→commit) 齐; 每 Task 含 failure-mode 段。
- File Inventory 四段 (A custos src 4 + B custos test 4 + C ps cross-repo 2 + D docs 5)。跨仓库改动 (custos + ps 双仓) 明确 `git add <specific-file>` (mandatory-rules §6) + scope 标注 (line 188)。
- 偏离日志 7 DEV: 3 CEO DP (packaging A/B/C, RiskController 参数 3 档, sidecar 退休时机) + 4 drafter (toolkit-hash-scope / integration-path / deploymentspec-dict / cross-repo-choreography)。
- START gate = Plan 05 T2.2 done 声明清晰 (line 8, 74)。DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY 明确无 atomic 跨仓保证, e2e 为集成兑现门 (line 436-439)。

### §6.B Failure-mode 覆盖 — GOOD
- registry mismatch / unknown-name reject / toolkit import failure → G6 拒 (非 crash, lesson #21) / vendored 闭包 float money grep gate / venue mismatch → G6 layer 2 / e2e 加载失败各断言。
- **credential 泄漏路径 (brief 关注点)**: 红线 0.1 由 e2e (T5.1/T5.2) "credential 经 vault 流入 NT 不 log/publish" 断言 + Plan 03 脱敏 test 无退化覆盖 (line 377, 381)。**依赖 existing 脱敏 test, 无 NEW credential-specific negative test** — 见 FU-4。
- vendored 闭包不完整 (漏传递依赖) → import error, 由 e2e T5.1 抓 (line 246) — 覆盖但间接。

### §6.C 契约表测试名 grep 实证 (lesson #25) — PASS (9/9 命中 + ps 侧存在)
- custos 侧 9 个 `✓existing` (line 355-367) 全命中:
  - `test_matching_hash_loads_class`/`test_explicit_strategy_class_attribute_wins`/`test_hash_mismatch_rejected`/`test_compute_dir_hash_is_deterministic_and_content_sensitive`/`test_sandbox_hash_none_skips_check_but_audits`/`test_strategy_path_not_found` → `tests/test_strategy_loader.py` ✓
  - `test_full_lifecycle_sandbox_supertrend`/`test_deploy_code_hash_mismatch_rejected`/`test_deploy_missing_nt_extra_fails_fast` → `tests/test_nt_trading_node_host_integration.py` ✓
- `tests/fixtures/minimal_supertrend_strategy.py` 存在 ✓。ps 侧 `tests/strategies/test_supertrend.py` + `test_supertrend_logic.py` 存在 ✓ (scout §9 引用真实)。
- NEW test (12 个) 全标注 NEW; ps 侧 NEW test 标注 `NEW (ps)`。

### §6.D 红线守护 + close-out 分层 — PASS
- 红线 gate 表 (line 375-382): 0.3 显式区分 per-strategy 层 (本 plan 兑现) vs per-runner 层 (defer Plan 04); 0.2 toolkit-in-code_hash scope 标 **文档化决策 (DEV-06-TOOLKIT-HASH-SCOPE) 非 defer**; 0.4 vendored 闭包 float grep gate (T3.3)。lesson #40 分层清晰。
- DEV-06-TOOLKIT-HASH-SCOPE 多层守 (策略 dir code_hash + toolkit provenance + custos release signing 三层, lesson #22) 论证扎实。

---

## §6.E Cross-plan File Inventory overlap matrix (core value)

> 图例: **C**=create · **M**=modify · **R**=rename/move · **V**=vendor · **–**=不 touch。
> 依赖序: Plan 05 先落 (基础重构) → Plan 04 (START=05 T4.2) + Plan 06 (START=05 T2.2) 均下游。
> 冲突判据: 若 **04 与 06 均在 05 之后 modify 同一文件** → 并行写危险 (05→单 plan 的串行天然安全)。

### 源码交集

| File | 04 | 05 | 06 | Owner / 判定 |
|------|----|----|----|-------------|
| `src/custos/engines/nautilus/host.py` | **M** (Tier-2 6 方法) | R+M (T2.2) | **M** (T4.1 TradingNodeConfig) | 🔴 **HIGH-1**: 05 建 → 04 与 06 **均 post-05 modify** = 并行必冲突 |
| `docs/domain.md` | **M** (:103 risk_config) | M (path refs) | **M** (:103 strategy_registry_name+nautilus_config) | 🟠 **HIGH-2**: 04+06 同改 `:103` DeploymentSpec field list 同一块 |
| `docs/design/nautilus_host.md` | M (组合熔断锚) | M (T3.2 impl 段+path) | M (T6.1 supertrend 段) | 🟡 MED (FU-1): 三 plan 改, 不同 section, append-heavy |
| `src/custos/core/engine_protocol.py` | M (扩 Tier-2) | C (T3.1 Tier-1) | – | ✅ 串行安全 (05 create → 04 扩, 04 START=05 T4.2) |
| `src/custos/core/deployment_reconciler.py` | M (zombie+breaker wire) | R+M (抽 Protocol+gate) | – | ✅ 串行安全 (05→04) |
| `src/custos/engines/nautilus/risk.py` | M (T1.3 cap) | R+M (T2.2 rename) | – | ✅ 串行安全 (05→04) |
| `src/custos/engines/nautilus/strategy_loader.py` | – | R+M (T2.2 rename) | M (T1.2 校验) | ✅ 串行安全 (05→06) |
| `src/custos/cli/main.py` | M (T4.3 wire) | C (T2.3)+M (T8.3) | – | ✅ 串行安全 (05→04) |
| `src/custos/core/{local_cap,state_snapshot,fallback_breaker}.py` | C | – | – | ✅ 04 排他 (净新) |
| `src/custos/engines/nautilus/toolkit/` | – | – | V (T3.2) | ✅ 06 排他 (净新 vendor) |
| `src/custos/core/g6_gate.py` | – | C (T4.1) | – | ✅ 05 排他 |

### 测试交集

| File | 04 | 05 | 06 | Owner / 判定 |
|------|----|----|----|-------------|
| `tests/core/*` (6 新 test) | C | (`__init__` C by 05 T8.1) | – | ✅ 04 排他 test; `tests/core/__init__.py` 由 05 建, 04 若 05 未落先建 (line 228 已 hedge) |
| `tests/engines/nautilus/test_state_snapshot_nautilus_impl.py` | C | (`__init__` C by 05 T8.2) | – | ✅ 04 排他 |
| `tests/engines/nautilus/test_{strategy_loader_registry_mode,nautilus_config_extension,toolkit_provenance,custos_hosts_real_supertrend_e2e}.py` | – | (`__init__` C by 05) | C | ✅ 06 排他 |
| `tests/engines/nautilus/test_nautilus_host_implements_engine_protocol.py` | – | C (T8.2) | – | ✅ 05 排他 |
| `tests/test_*.py` (31 existing) | – | M (import rewrite) | – | ✅ 05 排他 (import fanout) |

> **测试目录 `__init__.py` 归属**: `tests/core/__init__.py` + `tests/engines/nautilus/__init__.py` 由 Plan 05 T8.1/T8.2 建。Plan 04 line 228 + Plan 06 已 hedge "若 Plan 05 未落地, executor 先建目录"。**无冲突** (create-if-missing 幂等), 但见 FU-2 顺序建议。

### 文档 / 配置交集

| File | 04 | 05 | 06 | Owner / 判定 |
|------|----|----|----|-------------|
| `docs/domain.md` | M (:103) | M (path) | M (:103) | 🟠 见 HIGH-2 (源码表已列) |
| `docs/design/nautilus_host.md` | M | M | M | 🟡 见 FU-1 |
| `docs/design/engine_protocol.md` | M (Tier-2 finalize) | C (T3.2) | – | ✅ 串行 (05→04) |
| `docs/design/reconcile.md` | M (三层兑现) | M (path ref) | – | ✅ 低冲突 (05 path / 04 content), 串行 |
| `docs/engines/nautilus.md` | – | C (T7.1 stub) | M (T6.1 细节) | ✅ 串行 (05→06) |
| `.forge/teams.yaml` | – | M (T1.2 safety paths) | – | ✅ **05 独占 owner** (见 FU-C1) |
| `Makefile` | – | M (T5.2 nt-runtime) | M (T3.1 toolkit-sync stub 可选) | 🟡 FU-3: 05+06 均改, 不同区, 低冲突 |
| `pyproject.toml` / `.claude/rules/*` / `CLAUDE.md` / `README.md` / `docs/guides,ops/*` | – | M | – | ✅ 05 排他 |
| `.forge/README.md` | M (close-out row) | M (close-out row) | M (close-out row) | 🟡 FU-2: 三 plan close-out 各改自己索引行, 低冲突 |

### 交集结论

- **04 ∩ 05**: 全部串行安全 (04 下游于 05, 每共享文件 05 先建/改 → 04 后扩)。
- **05 ∩ 06**: 全部串行安全 (06 下游于 05) + Makefile 低冲突 (FU-3)。
- **04 ∩ 06** (关键): **`host.py` (HIGH-1) + `docs/domain.md:103` (HIGH-2) 两文件均 post-05 双改** = 真并行写危险。plan 声明 04‖06 并行 (Plan 05 line 545 "与 06 可并行"), 但这两文件需 owner/merge 协议。
- **04 ∩ 05 ∩ 06** (三重): `host.py` / `docs/domain.md` / `docs/design/nautilus_host.md` / `.forge/README.md` — 前二是热点 (HIGH), 后二低冲突 (FU)。

**→ Cross-plan overlap = SERIAL_REQUIRED** (仅 host.py + domain.md:103 两热点; 其余可并行)。

---

## §6.F 契约冻结点核对 — CONSISTENT (无偏差)

| 校验项 | Plan 05 声明 | 下游 plan 声明 | 一致? |
|--------|-------------|--------------|-------|
| Plan 04 START = 05 T4.2 done (Protocol Tier-1 冻结 + g6_gate 抽出 + execution_engine 字段改名收口) | line 161 | Plan 04 line 8 + line 70-79 START gate 表 | ✅ 一致 |
| Plan 06 START = 05 T2.2 done (engines/nautilus/ 路径落定) | line 160 | Plan 06 line 8 + line 74 | ✅ 一致 |
| Tier-1 5 方法冻结 (deploy/reconfigure/stop/supports_live/supports_venue) | line 121-136 | Plan 04 line 81 "UPSTREAM PROTOCOL FROZEN, 只扩 Tier-2" | ✅ 一致 |
| Tier-2 6 方法归属 = Plan 04 owns (Plan 05 仅文档化) | line 141-150, 567 | Plan 04 line 145-195 Tier-2 契约 (owns) | ✅ 一致 |
| toolkit 落点 = engines/nautilus/toolkit/ (DEV-05-TOOLKIT-LOCATION) | line 499-503 | Plan 06 line 119, 159 (vendored → toolkit/) | ✅ 一致 |
| skeleton line 231 "Plan 09 rename to custos_runner" superseded | line 566 (通知 06 drafter) | Plan 06 line 468 (注: 已 superseded, module=custos 非 custos_runner) | ✅ 一致 (drafter marker 06 确认 fix applied) |

**§6.F 结论**: 三 plan 的 Depends on / START gate / Blocks / 契约冻结点 **完全自洽**, 无矛盾。Plan 05 §Blocks 04+06 冻结点 (line 154-165) 与 04/06 各自 §Depends on 段逐条对齐。

---

## HIGH findings (阻塞进 Wave D / 需 CEO or execute-team 决策)

### HIGH-1 — `host.py` 被 Plan 04 + Plan 06 均 post-05 modify, 并行执行必冲突 (lesson #16 execute-time 形态)
- **实证**: Plan 04 File Inventory line 212 `src/custos/engines/nautilus/host.py | modify | T1.1/T2.1/T3.1/T4.1 | Tier-2 6 方法 NT 真实现`; Plan 06 File Inventory line 158 `src/custos/engines/nautilus/host.py | modify | T4.1 | TradingNodeConfig 借 ps _create_node_config`。二者均 START 于 Plan 05 之后, Plan 05 line 545 明示 "Plan 04 ↓ 与 06 可并行"。
- **风险**: 04 改 host.py 的 Tier-2 方法 (NoopHost + NtTradingNodeHost 6 方法) + 06 改 host.py 的 `_create_node_config`/`TradingNodeConfig` 构造 (deploy 路径)。虽属不同 method 区, 但同一文件并行分支编辑, git 3-way merge 若相邻 hunk 即 conflict; 即便自动 resolve 也需 execute-team 处理 (lesson #16 "共享文件三路冲突")。
- **建议**: execute-team 二选一 —
  (A) **串行 host.py**: 04 先落 host.py Tier-2 → 06 rebase TradingNodeConfig 改动 on top (推荐, 04 是红线核心);
  (B) **owner+merge 协议**: 声明 host.py owner = Plan 04, Plan 06 T4.1 在 04 host.py 合入后再动, 或走 plan-index §7b 类 merge 热点表。
- **不阻塞起草质量** — 是 execute-team 编排决策, 但必须在 Wave D packet / dispatch 前明示, 否则 04‖06 并行会静默撞车。

### HIGH-2 — `docs/domain.md:103` DeploymentSpec field list 被 04 + 06 同块编辑
- **实证**: Plan 04 line 235 `docs/domain.md | modify | :103 字段清单加 risk_config + RunnerRiskConfig`; Plan 06 line 182 `docs/domain.md | modify | :103 DeploymentSpec field list 加 strategy_registry_name + nautilus_config`。二者均改 `docs/domain.md:103` **同一 field list 块** (scout §10 确认该块是单一 prose schema)。
- **风险**: 同块并行编辑, 文本相邻/同行冲突概率高于 code (docs 无 3-way 语义 merge)。
- **建议**: 同 HIGH-1 owner 协议 — 指定 domain.md:103 编辑 owner (建议 04 先加 risk_config, 06 后加 strategy_registry_name/nautilus_config on top), 或串行。可与 HIGH-1 合并为"04→06 串行 host.py + domain.md"单一协议解决。

---

## FOLLOW_UP findings (可 defer, 不阻塞)

### FU-C1 — teams.yaml touched_paths 需 directory-glob 以覆盖 04 净新红线文件 (跨 plan 安全依赖)
- **实证**: 当前 `.forge/teams.yaml` safety.touched_paths 为 **per-file** 列 8 个 `src/arx_runner/*.py` (grep 命中 line 92-106, 逐文件非 glob)。Plan 05 line 230 声明 T1.2 改为 `src/custos/core/* + src/custos/engines/nautilus/*`。
- **依赖**: Plan 04 创建净新红线 0.4 money-math 文件 (`core/local_cap.py` / `core/fallback_breaker.py` / `core/state_snapshot.py`) + Plan 06 vendor `engines/nautilus/toolkit/`。这些 net-new 文件必须落在 safety.touched_paths 内, safety-validator gate 才会审。
- **建议**: 明确要求 Plan 05 T1.2 写 **directory-glob** (`src/custos/core/*` + `src/custos/engines/nautilus/*`) 而非逐文件, 使 04/06 净新文件自动覆盖 (04/06 引用不改 teams.yaml, 归属 05 独占 — 正确)。若 05 写成逐文件精确路径, 04 的 `local_cap.py`/`fallback_breaker.py` 会漏出承重墙审查面。**Plan 05 是 owner, 请在其 T1.2 Step 3 明示 glob 形态。**

### FU-1 — docs/design/nautilus_host.md 三 plan 改, 建议 append 语义 + section 锚
- 04 加"组合熔断 runtime 锚"/ 05 加"实现 ExecutionEngineProtocol 段"+path / 06 加"PS supertrend migration 段"。不同 section, 但同文件三改。建议 execute-team 走 append-only + 明确各自 section 标题锚, 降 merge 摩擦 (低于 HIGH, 因 append-heavy)。

### FU-2 — 测试目录 `__init__.py` + `.forge/README.md` close-out 建议顺序
- `tests/core/__init__.py` + `tests/engines/nautilus/__init__.py` 由 05 T8.1/T8.2 建, 04/06 已 hedge create-if-missing。建议若 05 先落则 04/06 不重建; `.forge/README.md` 三 plan 各改自己索引行 (低冲突, 各自 close-out commit 时更新自己行, 不并发写同行)。

### FU-3 — Makefile 被 05 + 06 均改
- 05 T5.2 `nt-runtime`→`nautilus` extra 名 fanout; 06 T3.1 加 `toolkit-sync-check` stub (标"可选")。不同区低冲突。建议 06 T3.1 若做 Makefile 改动, 在 05 Makefile 改动合入后进行 (06 下游于 05, 天然序), 或 06 明示 toolkit-sync-check 为独立 target append。

### FU-4 — Plan 06 credential 红线 0.1 失败模式依赖 existing 脱敏 test, 无 NEW negative test
- Plan 06 红线 0.1 兑现由 e2e 断言 "credential 经 vault 流入 NT" + Plan 03 existing 脱敏 test 无退化 (line 377)。建议 T5.1/T5.2 e2e 显式加一条 credential-not-in-telemetry-payload 断言 (NEW), 而非仅靠 existing 回归 — 与 Plan 04 `test_node_dict_recursive_no_credential` 回归行对称。低优先, e2e 已间接覆盖。

### FU-5 — Plan 04 NEW test 计数三处不一致 (drafter 自身数字)
- Plan 04 marker `failure_mode_tests_new=35`; plan §统计 (line 415) `Q≈33 NEW` (用 ≈ hedge); 本 reviewer 逐行数 ~34。三处轻微不一致。**非编造** (所有 NEW 名合法且标注 NEW), 但建议 close-out 前 (lesson #25 gate) 用 `grep -rn "def test_" tests/core tests/engines` 精确核数, 使契约表条目数 = 实建 test 数。marker 精确"35"应与最终实建对齐。

### FU-6 — Plan 05 `test_smoke` 是文件非函数 (命名 imprecision)
- Plan 05 失败模式表 line 443 列 `test_smoke` 为 existing。实证: `tests/test_smoke.py` 存在但内含函数 `def test_import():`, **无** 名为 `test_smoke` 的函数 (`grep "def test_smoke" tests/` 0 命中)。属"文件名当函数名"轻微 imprecision — smoke 安全网真实存在 (file + test_import), 非编造。建议改引 `test_import` 或写 "test_smoke.py (test_import)" 消歧。低优先。

---

## 附: lesson #C2 自我实证声明

本报告所有事实性 finding 均附实证锚:
- test 名存在性: `grep -rn "def <name>" tests/` 命令原文 + 命中 `file:line` (§6.C 三 plan 全跑, 输出见 dispatch 会话)。
- 文件多 plan touch: 引 plan File Inventory 表 `file:line` (HIGH-1 引 04:212 + 06:158; HIGH-2 引 04:235 + 06:182)。
- teams.yaml 格式: `grep -n "touched_paths" .forge/teams.yaml` 命中 line 90-106 per-file 形态 (FU-C1)。
无实证锚点的推测均未写入 finding (归罪偏置防护, lesson #C2)。
