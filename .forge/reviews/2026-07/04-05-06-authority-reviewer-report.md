# Authority Reviewer Report — Plan 04/05/06

> **Role**: authority-reviewer (custos plan-team). Zero-paraphrase compliance + 红线语义 drift 审查.
> **Model**: claude-opus-4-7[1m].
> **as-of**: main HEAD `cbf5556` (Plan 03 close-out) + evidence-scout `db75846`, 2026-07-09.
> **Method**: 每条事实性 finding 附 file:line + grep 实证 (lesson #9/#11/#C2 不信推理信实证). 本 reviewer **独立 grep 权威文档原文**核对 plan 引用, 未止步于 scout 报告转引.

---

## 汇总 verdict

| Plan | Verdict | 一句话 |
|------|---------|-------|
| **Plan 04** (红线 0.3 兑现) | **APPROVED_WITH_FOLLOW_UPS** | 红线 0.3 引用与 mandatory-rules §0.3 语义完全一致, 无弱化; cap+breaker 直接映射 §0.3 双守护, zombie 为附加强化; 2 项 FU |
| **Plan 05** (结构重构 + rename) | **APPROVED_WITH_FOLLOW_UPS** | zero-paraphrase 合规, G6 gate 契约逐字保留不破; 1 项 G6 authority-doc 源指针 drift FU + 1 项 CLAUDE.md 定位 CEO-override FU |
| **Plan 06** (ps supertrend 迁移) | **APPROVED_WITH_FOLLOW_UPS** | vendored toolkit (方案 A) 与 §7 独立仓自足纪律契合优秀, submodule 正确否决; 1 项 e2e 自足性 provenance FU |
| **Red-line drift risk** | **LOW** | 四条红线无任一弱化; float 仅用于时间戳 (正确豁免); G6 契约保留; 失联守护从 0 实现升级为 runtime-wire 兑现 |

**实证核对结论**: 抽查的全部 authority-doc 锚点 (domain.md:103/104, nautilus_host.md:39/50/83, reconcile.md:33, mandatory-rules §0.3, teams.yaml:90-106/116) **逐一与源文件字节匹配**, plan 引用无 paraphrase-代替-引用违规。

---

## Plan 04 findings

### §Auth-A — Zero-paraphrase compliance ✅

- **红线 0.3 兑现声明 vs mandatory-rules §0.3 原文语义一致性 (核心审查项)**: 通过。
  - mandatory-rules §0.3 原文 (grep 实证, `.claude/rules/mandatory-rules.md`):「云端 (arx) 断线时, custos runner **本地**继续运行: 保留每策略/每账户 drawdown breaker; 保留结构性 `max_notional_per_runner` cap; **禁止** `reconcile.py` 在云端断线时暴力 `stop_all_strategies()` (除非本地 breaker 触发)」。
  - Plan 04 goal (line 88-91):「per-runner: max_notional_per_runner cap (软限) + fallback breaker (硬限) + zombie detection (自主降级)」。
  - **判定**: cap + fallback breaker **直接映射** §0.3 双守护, 无弱化、无缩义。plan 谨慎声明 per-strategy drawdown 层归 Plan 06 RiskController (不冒领), per-order 层归现有 NT RiskEngine — 三层归属清晰, 与 §Context line 25-30 现状分层实证一致。
  - breaker trip → `flatten_positions` 正是 §0.3「除非本地 breaker 触发」的**允许例外**; zombie 仅 `phase=degraded` (不 stop), 未触碰 `stop_all_strategies()` 禁令。**语义完全忠实。**
- **契约证据锚表 (line 44-59)**: 每条引用有 scout `file:line` 锚点; 本 reviewer 抽查 `nautilus_host.md:50` (`max_notional_per_runner ≤ NAV × 5x`) 与 `domain.md:104` phase 词表 (`pending/running/degraded/stopped`), **两处均与源文件字节一致**。

### §Auth-B — 红线语义 drift ✅

- **红线 0.3**: 无弱化, 见 §Auth-A。**附加观察 (非 drift)**: zombie detection 超出 §0.3 字面 (§0.3 只列 cap + drawdown breaker), 属**附加强化层**而非弱化 — engine disconnected 但进程 alive 时自主 `phase=degraded`。plan 架构图 (line 104-124) 把 zombie 与 cap/breaker 并列为独立守护层, 定位准确。**不构成 drift, 但建议 close-out 红线 gate 表明确标注 zombie 为「§0.3 附加, 非字面要求」以免未来读者误判红线范围。**(→ FU-4 附带)
- **红线 0.4**: 无 drift。
  - `ConnectivityState.checked_at_epoch_s: float` (line 174) — plan 显式注「非 money, float 允许 (时间戳)」。**正确**: 时间戳非 money 路径, 不受 §0.4 约束。
  - DEV-04-PEAK-EQUITY-DECIMAL (line 139): scout §8 实证 ps `runner.py:101 _peak_equity: float`, plan 强制 custos 全 Decimal 重推、禁 copy-paste。**红线 0.4 边界守护到位。**
- **红线 0.1 / 0.2**: 本 plan 不 touch key I/O 与 G6 gate 路径; Tier-2 方法 (state/risk query + flatten) 不 log/publish credential。红线 gate 表 (line 425-426) 声明「不变」, 与实际范围一致。

### §Auth-C — 契约 spec 一致性 (2 处 FU)

- **Tier-1 冻结遵守**: plan line 74-81 明确「UPSTREAM PROTOCOL FROZEN」, 只扩 Tier-2 6 方法不改 Plan 05 Tier-1 5 方法。与 Plan 05 §Tier-2 (line 141-150) 决策互洽。✅
- **dataclass 命名 vs domain.md 6 BC**: `PositionSnapshot`/`OrderSnapshot`/`ConnectivityState`/`EngineStatus` 是支撑值对象, 非 BC 级实体 (6 BC = enrollment/reconcile/nautilus_host/telemetry_actor/credential_vault/nats_client)。命名符 domain PascalCase 值对象惯例, 无冲突。✅ plan 新增 `EngineStatus`/`RunnerRiskConfig` 概念到 domain.md (T6.1) — 属**中风险** domain.md 补充 (更新契约文档, 非新增/删除 BC), 经 T6.1 docs sync 正确处理。
- **FU-4**: Tier-2 方法名 Plan 05 与 Plan 04 有分歧 — Plan 05 engine_protocol.md 文档化推荐签名用 `get_status` (line 146); Plan 04 实装用 `get_engine_status` (line 189, 自注「== Plan 05 get_status slot」)。Plan 04 T6.1 已 scoped「engine_protocol.md Tier-2 6 方法 finalize (Plan 05 推荐签名 → Plan 04 落地签名对齐)」— 覆盖此收口。**建议 close-out 显式核实 engine_protocol.md 已 finalize 到实装名 (`get_engine_status`), 防 authority 文档遗留 `get_status` 旧名 drift。**
- **FU-5 (跨 04/06 merge 热点)**: Plan 04 (加 `risk_config`) 与 Plan 06 (加 `strategy_registry_name` + `nautilus_config`) **均改 `docs/domain.md:103` DeploymentSpec field list**。若并行执行, 该行是 merge 热点 (lesson #16)。**建议 execute-team 指定 domain.md:103 field-list 编辑的单一权威顺序 (如 04 先 / 06 后 rebase), 或 close-out 合并核对 field list 一致。**

### §Auth-E — Git 规范 ✅ (1 处轻提示)

- 全 Task commit scope = `custos` (line 255/262/269/... 逐一核对), 非 `arx_runner`。✅
- 一逻辑一 commit; T-final 走 `git add <specific-file>` + `git status --short` 核对 (line 358, lesson #27)。✅
- **轻提示**: 无独立 FU。各 Track task 无 mass-rename 场景 (Plan 04 是 create/modify 净新, 非 rename), pre-staged 污染风险低。

---

## Plan 05 findings

### §Auth-A — Zero-paraphrase compliance ✅

- **Tier-1 Protocol 逐字 rename 核实**: Plan 05 line 121-136 声明「从 `NautilusHostProtocol` deployment_reconciler.py:166-174 逐字 rename」5 方法。本 reviewer grep 实证:
  - scout §3 + 现场 grep: `NautilusHostProtocol` 定义在 `deployment_reconciler.py:156`, 5 方法 `deploy`/`reconfigure`/`stop`/`supports_live`/`supports_venue`。
  - `reconcile.md:33` + `nautilus_host.md:39` 权威文档亦列同 5 方法。
  - **判定**: 方法集相等 (5→5), 唯一新增 = `@runtime_checkable` (scout §3 实证当前无) — plan 诚实标注为「**净新**能力」(line 138) 而非伪装为等价 rename。**zero-paraphrase 优秀。**
- 契约证据锚表 (line 38-56) 与 scout 一一对应; 抽查 teams.yaml safety.touched_paths 声明 (line 230)「行 92-106 8 个 `src/arx_runner/*.py`」— 现场 grep 实证 8 路径确在 90-106, area root 在 116; 且 teams.yaml:153 第二 touched_paths 块是 ops_team `.forge/plans/**` 模式 **不含 arx_runner**, 故 plan 的 fanout 识别**完整无遗漏**。✅ (skeleton 漏项被 drafter 捕获, lesson #35 高价值)

### §Auth-B — 红线语义 drift ✅ (G6 契约保留)

- **红线 0.2 (G6 gate 不绕过) — 契约保留核实**:
  - G6 gate 4 层 + 结构化事件名 grep 实证 (`nautilus_host.md:83`): `g6_gate_live_capability_denied` / `g6_gate_venue_unsupported` / `g6_gate_code_hash_mismatch` / `g6_gate_credential_scope_violation` — 与 scout §4 + plan Track 4 (line 51) **逐字一致**。
  - Plan 05 T4.1 (line 314) 保留「case-insensitive live 检测 (lesson #36 dead-gate 防护)」— 与 `nautilus_host.md:83`「`trading_mode` 大小写不敏感 (Rust PascalCase `"Live"` + Python 小写)」一致, **未引入 dead-gate 风险**。
  - 验证清单 (line 398)「G6 gate 4 层 + 5 relaxed-double test 全绿」+ 失败模式表 (line 447-453) 列全 5 relaxed-double + NoopHost-拒-live + 非 live 旁路 — **relaxed-double NoopHost still denied 契约保留 (符 task §Auth-B 要求)**。✅
- 红线 0.1/0.3/0.4: 纯 rename/move, plan 红线 gate 表 (line 470-473) 声明「不变 / move only / 保 Plan 03 状态」, 与「零行为改动」架构声明 (line 79) 一致。✅

### §Auth-C — 契约 spec 一致性 ✅

- ExecutionEngineProtocol Tier-1 与 `nautilus_host.md §状态机` / §G6 gate 契约兼容: Tier-1 只操作 deploy/reconfigure/stop + supports_* capability 面, G6 gate 层 1/2 调 `supports_live()`/`supports_venue()` (line 139), 契约不变只换类型注解名。✅ Tier-2 明确「不进 Plan 05 runtime Protocol, 仅文档化」(line 141) — 与 Plan 04 owns Tier-2 决策边界清晰。

### §Auth-D — 独立仓自足纪律 ✅

- 无 `../../..` workspace 路径引入; docs/engines/*.md + engine_protocol.md 均 net-new create (File Inventory B 正确标注)。✅
- 权威文档引用 spot-check: reconcile.md / nautilus_host.md / domain.md / mandatory-rules.md / verification.md / teams.yaml — 现场核对**全部存在**, 无 dangling ref。✅

### §Auth-E — Git 规范 ✅ (1 轻提示)

- Track commit scope 全 `custos` (line 261/268/... refactor/docs/build/feat/test 各 scope 正确)。✅
- **轻提示 (非独立 FU)**: T1.1 扁平 rename 是**大范围原子 commit** (`git mv` + 31 test import + pyproject), staged 文件面广。plan T-final 引 lesson #27 但 T1.1 步骤未显式列 `git status --short` 核对。建议 executor T1.1 commit 前核对 staged 仅含 rename 相关文件 (防 pre-staged 污染混入大 rename commit)。

### §Auth-F — CEO override 记账 (1 处 FU)

- **DEV-05-CLAUDE-POSITIONING (line 516-518)**: 定位从「'Key/策略只在本地' 红线的**唯一路径** minimal daemon」→「standard NT runner + engine-plugin toolkit」。plan **正确 elevate 到 CEO** (「是否落地 CEO 定」), 未自行决定。✅ 未构成静默 override。
- **FU-2**: 该定位升级触碰 custos CLAUDE.md §1 non-custodial「**唯一路径**」核心框定 — 属 deviation-protocol.md **中/高风险** (顶层对外定位声明变更)。**若 CEO 批准**, 须走 lesson #38/C1 CEO-override **4 件套** (CEO 决定 + DEV 条 + `.forge/README.md` 脚注 + historical-lesson 先例), 而非仅 T-final 改 CLAUDE.md 一行。建议 T-final 预置「若 CEO 批 = 触发 C1 4 件套」的 gate, 防止定位升级绕过 override 记账路径。

---

## Plan 06 findings

### §Auth-A — Zero-paraphrase compliance ✅

- 契约证据锚表 (line 47-65) 全 scout `file:line`; ps 侧引用 (registry.py:222-288 / trading_strategy.py:177 / controller.py Decimal-only) 均锚定。plan dispatch 约束 (line 45)「只用 evidence-scout + Plan 05 refined + skeleton, 禁自行 grep 权威文档 (防 lesson C2)」— **方法论正确** (避免 review 阶段 output-pollution)。✅
- DeploymentSpec dict 修正 (DEV-06-DEPLOYMENTSPEC-DICT-NOT-CLASS, line 431): scout §10 实证 `class DeploymentSpec` 0 命中, plan 正确 re-scope 为 domain.md:103 field-list dict-key。本 reviewer 现场核对 domain.md:103 = `spec_id · tenant_id · ... · pulled_at`, **无 strategy_registry_name / nautilus_config 字段** — plan 前提准确。✅

### §Auth-B — 红线语义 drift ✅

- **红线 0.1 (Key/KEK 不出进程) — credential 流路径核查 (task 点名审查项)**: 无泄漏点。
  - 红线 gate 表 0.1 (line 377):「supertrend config 不含明文 key (走 credential_vault 引用); credential 全程解密→NT client, 不 log/publish」。
  - T5.2 testnet e2e (line 278) 前置「测试用 sandbox key 非真 key (mandatory-rules §5)」— 符 §5「测试用 API Key 必须 mock/一次性 sandbox」。
  - supertrend config.yaml 加 risk section (Track 2) **不涉 credential** (纯风控参数), 无 key 落 config 风险。**红线 0.1 守护到位。**
- **红线 0.4**: vendored toolkit float 审计 (T3.3 `test_vendored_toolkit_no_float_money_math`, line 251) + RiskController Decimal-only (scout §5 `controller.py` 实证)。**审计通过前不合入** (line 380)。✅
  - **轻提示**: T3.3 grep pattern (`float(.*price|amount|notional|equity`) 覆盖显式 float 构造, 但**不覆盖隐式 float 算术** (如 scout §8 flag 的 `drawdown/peak*100`)。plan line 252 已声明「更广闭包 executor 必 grep 实证」— 覆盖此缺口, 可接受。
- **红线 0.2**: 策略 dir code_hash 过 G6 layer 3 (dir-hash 现成); vendored toolkit **不入** per-deploy code_hash (DEV-06-TOOLKIT-HASH-SCOPE), 归 custos 供应链完整性 (provenance + release signing) — **多层守 (lesson #22)**: 策略 dir hash + toolkit provenance + release signing 三层。决策合理, 未弱化 G6。✅

### §Auth-C — credential 流符 credential_vault §KEK 生命周期 ✅

- 红线 gate 表 0.1 runtime_wire (line 377):「`deploy()` 经 credential_vault decrypt → NT client only (scout nautilus_host.md §credential lifecycle 3 层 invariant)」— 与 `nautilus_host.md` 红线契约「`deploy` 收到的 credential 由 credential_vault 本地解密, KEK 永不出主机」(现场 grep 实证 line 51-52) 一致。✅

### §Auth-D — 独立仓自足纪律 (1 处 FU) ✅ 主体优秀

- **shared/ 打包决策 (方案 A vendored) 与 §7 契合度 — 优秀**: Track 3 决策表 (line 137-143) 逐一评估 A/B/C, **正确否决 B (submodule 破单仓自足, 违反 §7 硬约束)** + C (引入 supply-chain 审计面)。方案 A vendored + provenance 是**审计员 clone 单仓即验证**的正确选择, 与 mandatory-rules §7 + non-custodial 承重墙根本要求高度契合。✅ **本 plan §Auth-D 主体是全批次最佳实践。**
- **FU-3 (e2e 自足性 provenance 缺口)**: Track 3 只 vendor `shared/` 依赖闭包 (scout §4: shared/config + shared/nautilus + shared/signals + shared/risk), **但 supertrend 策略本体 (`ps trend/supertrend/strategy.py`) 不在 shared/ 内, 未 vendored**。T5.1 e2e (line 271)「real ps supertrend (via vendored toolkit)」若从 ps 仓路径加载 strategy.py → **独立 clone 场景 (无 ps 仓) e2e 无法跑 + make verify baseline 在独立 clone 断裂 (违 §7)**。
  - plan 现有 `tests/fixtures/minimal_supertrend_strategy.py` 是零依赖 stub (自足), 但 T5.1 明确要 "real" 非 stub。
  - **建议二选一**: (a) T5.1 标 `@pytest.mark.integration` / workspace-only (如 T5.2 testnet), 排除出 baseline; 或 (b) vendor supertrend strategy.py 快照到 `tests/fixtures/` (连同 toolkit) 使 e2e 独立自足。plan 当前对 real supertrend 的 provenance 在独立 clone 语境**未澄清**, 需 execute-team 定夺。

### §Auth-E — Git 规范 ✅

- 跨仓库 commit 规范 (line 188 + 317):「custos + ps 双仓, 仅 `git add <specific-file>` (mandatory-rules §6)」+ custos scope=`custos`。✅ DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY (line 436) 声明无 atomic 跨仓保证, e2e 为集成兑现门 — 编排诚实。
- **轻提示**: ps 侧 commit 示例 (line 223)「commit (ps 侧 scope) `feat: enable RiskController...`」无显式 scope。属 ps 仓自身约定 (workspace §6 用 subsystem scope), custos plan 无权规定 ps scope, 可接受。

### §Auth-F — CEO override ✅

- DP1 (packaging A/B/C) / DP2 (RiskController 参数) / DP3 (sidecar 退休时机) 均**参数/机制决策**, 非红线例外声明。DP2 明确「资金风险决策, drafter 无默认权, CEO 拍板」(line 408) — 正确 elevate。**无需 CEO override 4 件套** (未触碰红线本体)。✅

---

## §Auth-B 红线 drift 检测汇总

| 红线 | mandatory-rules §0 原文锚 (grep 实证) | Plan 影响 | drift 判定 |
|------|------------------------------------|----------|-----------|
| **0.1 Key/KEK 永不出进程** | §0.1「禁 telemetry/日志/status/heartbeat 携带 raw key material; 禁 cloud SDK」 | 06 credential 走 vault decrypt→NT client only; sandbox key 测试; 04/05 不 touch key I/O | **无 drift** — 无泄漏点 |
| **0.2 G6 gate 不绕过** | §0.2 + nautilus_host.md:83 (4 层 + 4 事件名) | 05 逐字 rename Protocol + extract g6_gate.py, 契约不变, 5 relaxed-double 保留, case-insensitive 保留; 06 toolkit 归供应链非 per-deploy hash (多层守) | **无 drift** — 契约保留 (docs 源指针 FU-1 见下) |
| **0.3 失联 ≠ 停止** | §0.3「本地 drawdown breaker + max_notional_per_runner cap 继续守; 禁 stop_all 除非本地 breaker 触发」 | 04 兑现 cap+breaker (直接映射) + zombie (附加); 06 兑现 per-strategy RiskController 层; 组合三层齐 | **无 drift, 强化兑现** — 从 0 实现升级为 runtime-wire (cap/breaker 映射忠实, zombie 附加非弱化) |
| **0.4 Money math Decimal** | §0.4「money 路径全 Decimal; wire str; 禁 float(price)」 | 04 全 Decimal (时间戳 float 正确豁免) + PEAK-EQUITY-DECIMAL 重推; 06 toolkit float grep gate + RiskController Decimal-only | **无 drift** — float 仅时间戳 (非 money), 审计门守 vendored |

**整体 red-line drift risk = LOW**: 四条红线无任一弱化/缩义/绕过; 唯一 G6 相关 FU (FU-1) 是 authority-doc 源指针滞后, **不影响红线 0.2 的执行强制**。

---

## HIGH findings (阻塞进 Wave D)

**无 HIGH findings。** 三 plan 均无红线弱化、无 zero-paraphrase 违规、无已执行的静默 CEO override。全部 FU 可 defer 到执行/close-out 阶段处理, 不阻塞进 Wave D。

---

## FOLLOW_UP findings (可 defer)

- **FU-1 【Plan 05 · §Auth-B/红线 0.2 · docs-sync 中】**: G6 gate authority-doc 源指针滞后。现场 grep 实证 `_check_g6_gate` 实际在 `deployment_reconciler.py:35` (**非** nautilus_host.py), 但 `docs/design/nautilus_host.md:3` 声明「源码：`src/arx_runner/nautilus_host.py`。G6 gate 主载体」— 这是**既有 design-doc drift** (scout §Cross-Plan §3 亦 flag 相关漂移)。Plan 05 T4.1 把 G6 gate 抽到 `core/g6_gate.py`, 但 T1.2 (机械 rename 路径) + T3.2 (加 Protocol 段) **未显式修正 G6 gate 源指针**。风险: T1.2 机械改 `nautilus_host.py`→`engines/nautilus/host.py` 会使「G6 gate 主载体 = host.py」**更错** (G6 实际在 core/g6_gate.py)。nautilus_host.md 是 authority-docs.md 指定的「G6 host gate 主载体」权威文档, 其源指针必须准确。**建议**: Plan 05 T4.1/T3.2 显式将 nautilus_host.md 的 G6 gate 源指针更新为 `src/custos/core/g6_gate.py` (并顺手修既有「在 host.py」的历史 drift)。契约与执行不受影响, 仅 docs 准确性。

- **FU-2 【Plan 05 · §Auth-F · CEO override 中】**: DEV-05-CLAUDE-POSITIONING 若 CEO 批准, 须走 lesson #38/C1 CEO-override 4 件套。定位从「非托管唯一路径」→「standard NT runner + engine-plugin toolkit」触碰 CLAUDE.md §1 non-custodial 核心框定 (中/高风险偏离)。plan 已正确 elevate 到 CEO (未静默), 但 T-final 仅「改 CLAUDE.md 一行」不足。**建议**: T-final 预置 gate「CEO 批 → 触发 C1 4 件套 (CEO 决定 + DEV 条 + `.forge/README.md` 脚注 + historical-lesson 先例)」, 防定位升级绕过 override 记账。

- **FU-3 【Plan 06 · §Auth-D · 独立仓自足 中】**: T5.1 "real ps supertrend" e2e 的 strategy 本体 provenance 在独立 clone 语境未澄清。vendored toolkit 只覆盖 `shared/` 依赖闭包 (scout §4), **supertrend strategy.py 本体 (ps trend/supertrend/) 不在 shared/ 内, 未 vendored**。若 e2e 从 ps 仓路径加载 → 独立 clone (无 ps 仓) 断裂 + make verify baseline 在独立 clone 失效, 违 §7。**建议二选一**: (a) T5.1 标 `@integration`/workspace-only 排除出 baseline (如 T5.2); 或 (b) vendor supertrend strategy.py 快照到 tests/fixtures/ 使 e2e 自足。

- **FU-4 【Plan 04 · §Auth-C · authority-doc drift 低】**: Tier-2 方法名 Plan 05 doc (`get_status`) 与 Plan 04 实装 (`get_engine_status`) 分歧。Plan 04 T6.1 已 scoped finalize engine_protocol.md, **建议 close-out 显式核实**已收口到实装名, 防 authority 文档遗留旧名。附带: 红线 gate 表建议标注 zombie 为「§0.3 附加层 (非字面要求)」以精确红线范围。

- **FU-5 【Plan 04 + 06 · §Auth-C · merge 热点 中】**: Plan 04 (加 `risk_config`) 与 Plan 06 (加 `strategy_registry_name` + `nautilus_config`) **均改 `docs/domain.md:103` DeploymentSpec field list** — 并行执行时为 merge 热点 (lesson #16)。**建议**: execute-team 指定 domain.md:103 field-list 编辑单一权威顺序 (如 04 先落 / 06 后 rebase), 或 close-out 合并核对 field list 一致无覆盖。

---

## 附: 本 reviewer 独立 grep 实证记录 (lesson #C2 — finding 起源附锚点)

| 核对项 | grep/read 命令 | 结果 |
|-------|---------------|------|
| domain.md DeploymentSpec 字段 | `sed -n 103p docs/domain.md` | `spec_id·tenant_id·...·pulled_at`, 无 risk_config/registry_name — 证 plan 前提准确 |
| domain.md phase 词表 | `sed -n 104p docs/domain.md` | `phase(pending/running/degraded/stopped)` — 证 zombie phase=degraded 合法 (亦印证 lesson #C2 degraded ∈ vocab) |
| nautilus_host.md cap 口径 | `grep -n max_notional_per_runner docs/design/nautilus_host.md` | `:50 ≤ NAV × 5x 结构性 cap` — 证 Plan 04 DP1 引用准确 |
| G6 gate 实际位置 | `grep -rn "def _check_g6_gate" src/` | `deployment_reconciler.py:35` (非 host.py) — 触发 FU-1 |
| G6 gate 4 事件名 | `sed -n 83p docs/design/nautilus_host.md` | 4 事件名逐字匹配 Plan 05 Track 4 line 51 |
| mandatory-rules §0.3 原文 | `sed -n '/### 0.3/,/### 0.4/p'` | drawdown breaker + max_notional cap + 禁 stop_all — 证 Plan 04 语义忠实 |
| teams.yaml touched_paths | `grep -n "arx_runner" .forge/teams.yaml` | 8 路径 90-106 + area root 116; 153 块是 ops `.forge/plans/**` 不含 arx_runner — 证 Plan 05 fanout 完整 |
| Protocol 定义 | `grep -n NautilusHostProtocol docs/design/reconcile.md` | `:33` 5 方法 — 证 Plan 05 逐字 rename 准确 |

---

*authority-reviewer, custos plan-team, 2026-07-09.*
