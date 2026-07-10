# Plan 06 06a slice DEVIATION Triage (Step 6.4a — partial close-out)

**Plan**: `06-ps-supertrend-migration.md` — ps supertrend 迁移: custos registry-mode 加载 + RiskController 启用 + shared/ 依赖打包 + e2e 集成
**Slice**: **06a** (Tracks 1-4 — registry 集成 + config 激活 + vendoring + node config; custos+ps 代码集成主体)
**Slice landed**: `306b9e5` refactor(custos): Plan 06 06a slice — ps supertrend integration + vendored toolkit + red-line 0.3 per-strategy layer (squash) + orchestration `55782d0` + hook infra `5c01cdb`
**Deferred to 06b** (**将被 Plan 08 吸收**): Track 5 (T5.1 sandbox e2e + T5.2 testnet e2e) + Track 6 (T6.1 sidecar retirement docs + T6.2 close-out)
**Marker source**: `.forge/dispatch-log/2026-07-04-05-06-execute-team-packet/runner-executor-06a-v1.complete.json` (10 DEV 条目) + pre-spawn `runner-executor-06a-v1.json`（`5eff170` 补齐入库）
**Cross-repo**: ps repo `develop @ 3443e96..34b73a2` (2 commits, DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY)
**Triaged at**: 2026-07-10
**Triaged at main HEAD**: `5eff170`
**Triager**: Execution Lead (main-session Claude, `/forge:execute-team` C-step follow-through)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (无 HIGH triage) |
| MED | **1** | DEV-06-06A-VENDOR-PANDAS-TA-DECISION-B — user-facing summary 段（下） |
| LOW | **7** | 仅记 |
| note | **2** | 归 note (架构方向 / recovery arc)，不计 severity |

**Overall triage verdict**: **1 MED (CEO 决策已 landed) + 7 LOW + 2 note — 可放行 06a partial close-out**, 无阻断项。Plan 06 整体 close-out 待 06b (由 Plan 08 吸收) 完成后统一签发。

---

## MED 档明细（1 条 — user-facing summary）

### DEV-06-06A-VENDOR-PANDAS-TA-DECISION-B

- **等级**: MED（供应链 vendoring 决策 + 涉及 fork 上游 LICENSE 尽调）
- **场景**: evidence-scout §4 vendoring 闭包分析未识别 `pandas_ta` 作为 ps `shared/nautilus/indicators/{supertrend,adx,macd,atr,rsi}.py` 的 git-URL transitive dep（scout 只看 direct import chain，跳过 setup.py `install_requires` git-URL 分析）
- **CEO 决策 (option B)**: vendor `pandas_ta` 到 `toolkit/vendor/pandas_ta/` from CEO-owned fork `wukai9203/Technical-Analysis-Indicators---Pandas.git @ a3a2228`。LICENSE precheck: **MIT** (Copyright 2020 pandas-ta) — 允许 vendored + attribution。LICENSE 文件已保留在 vendored 树内。
- **实施影响**:
  - `toolkit/vendor/pandas_ta/` +149 files / +13,939 LOC
  - `toolkit/__init__.py` bootstraps `sys.path` (vendor/) + `pkg_resources` Distribution shim (满足 pandas_ta 自身的 `get_distribution('pandas_ta')` 调用无需 patch vendored code)
  - `nt-runtime` extra 加 pin `setuptools>=50,<70` + `packaging` (transitive)
- **user-facing summary** (供 CEO 未来审 supply-chain 审计参考): vendored `pandas_ta` 是 audit-able 承重墙的一部分，任何 vendored subset 边界收窄/扩展决策 (Plan 07 curation) 都要重新评估 LICENSE 合规 + drift 监测节奏 (`Makefile toolkit-sync-check` stub → 真实现)
- **红线关联**: 0.2 G6 gate — vendored toolkit 不进 per-deploy `code_hash` scope (DEV-06-TOOLKIT-HASH-SCOPE, CEO DP4=A)。toolkit 由 `TOOLKIT_PROVENANCE.md` + 未来 release signing 治理
- **红线关联**: 0.4 Money math — vendored 树内 10 处 `float(<money-word>)` 允许 (T3.3 exemption allow-list in `test_vendored_toolkit_no_new_float_money_math`, 见 DEV-06-06A-PANDAS-TA-FLOAT-EXCEPTIONS 明细)
- **状态**: ✅ 已 accept + applied，Plan 07 curation 时可重估边界

---

## LOW 档明细（7 条）

### DEV-06-06A-SCOUT-COORDINATORS-PATH-CORRECTION

- **等级**: LOW
- **场景**: evidence-scout §4 描述 ps `shared/coordinators/*` 为 top-level path; 实际 repo 布局是 `shared/nautilus/coordinators/`（嵌套 nautilus/ 下）
- **决定**: T3.2 vendor `shared/nautilus/` 整个子树, 自动带上 coordinators subtree — 无需 scout 层修正即闭合
- **契约影响**: `TOOLKIT_PROVENANCE.md` 记录 chained path; sync procedure 复制 `shared/nautilus/` 涵盖 coordinators
- **状态**: ✅ 已 applied

### DEV-06-06A-T21-SEMANTICS-CLARIFICATION

- **等级**: LOW
- **场景**: T2.1 plan 原措辞 "add risk section to activate `_risk_controller`"; 实际 `base_config.yaml` 已提供 `risk.global.*` defaults，`_risk_controller` 已 first-time activated
- **决定**: T2.1 semantics 更正为 **override with medium-tier production values** (非 first-time activation)。supertrend `config.yaml` deep-merges `risk.global.{max_daily_loss=0.05, max_drawdown=0.15, consecutive_loss_pause=5}` onto base defaults
- **状态**: ✅ 已 applied，plan 措辞待 Plan 06 完整 close-out 时更新

### DEV-06-06A-DP2-FIELD-NAME-CORRECTION

- **等级**: LOW
- **场景**: CEO DP2 决策文本用字段名 `consecutive_loss_limit`; grep 实证 ps `shared/risk/controller.py:55/160`, `base_config.yaml:456`, `shared/nautilus/config/risk.py:16/205`, `shared/config/loader.py:489` — canonical name 是 `consecutive_loss_pause`
- **决定**: DP2 semantic (5 = 5th consecutive loss) 不变; binding key 校正为 `consecutive_loss_pause: 5`
- **lesson #37 应用**: spawner (CEO) 元层未 grep 实证字段名 → executor 主动 grep 纠偏（lesson #37 executor 100% 内化率的又一实例；本 slice 累计 6 处元层复发一致模式）
- **状态**: ✅ 已 applied

### DEV-06-06A-STALE-LINE-ANCHOR

- **等级**: LOW
- **场景**: Plan §契约证据锚 anchored factory-probe at `host.py:356-367`; 实际 post-Plan-05 layout 是 `_instantiate_strategy at :431` with `factory=getattr(module,'create_strategy') at :439`。行锚 drift 未在 plan refinement 阶段被 catch
- **决定**: Marker + commit message 使用 canonical 锚点; plan 文件本身不改（plan 是先前 Wave 的 upstream artifact）
- **状态**: ✅ 已 applied，Plan 07 起草时若引用需重锚

### DEV-06-06A-PANDAS-TA-FLOAT-EXCEPTIONS

- **等级**: LOW
- **场景**: T3.3 红线 0.4 grep audit 在 vendored 树中发现 10 处 `float(<money-word>)`:
  - 5 处在 `warmup/snapshot.py`（`PriceSnapshot` dataclass 用于 indicator warmup OHLCV — pandas_ta 与 NT indicators 原生用 float）
  - 5 处在 `startup_validator.py`（`initial_capital` vs `actual_balance` fail-fast threshold at startup — 非 fund-flow 计算; 订单 sizing 由 NT 下游的 Decimal `Money`/`Quantity` 承接）
- **决定**: `test_vendored_toolkit_no_new_float_money_math` 枚举 exemption 并对 drift fail (Plan 07 curation 时需 re-baseline allow-list)。Vendored code stays byte-identical to upstream; 未 patch
- **状态**: ✅ 已 applied

### DEV-06-06A-CHECK-CODE-ENGLISH-HOOK-EXEMPTION

- **等级**: LOW
- **场景**: `scripts/check-code-english.py` pre-commit hook 在 main custos worktree 是 untracked 状态 (Plan 06 06a 执行时). Local worktree 副本被 patch 加 `/toolkit/shared/` + `/toolkit/vendor/` 到 `EXEMPT_PATH_SUBSTRINGS`, 让 vendored CJK (from ps upstream config comments) 不阻断 commit
- **决定**: hook 3 files 后由 `5c01cdb` (post-06a) 正式入库；Plan 09 承接 hook infra 正式化
- **状态**: ✅ 已 applied，Plan 09 承接正式化

### DEV-06-06A-STRATEGY-LOADER-SYS-MODULES-CACHE

- **等级**: LOW
- **场景**: `load_strategy_class` 调 `_import_module_from_path` 之前总是 create fresh module; ps `register_strategy` 在第二次调用带不同 class object 时 raise `ValueError('already registered')`, toolkit registry 停留 stale class
- **决定**: 加 `sys.modules` cache check — 重执行相同 strategy path 复用 cached module; upstream `code_hash` check 保 cache 安全性。cache slot 在 failed load 时清理不掩盖真实错误
- **状态**: ✅ 已 applied，`_import_module_from_path` 现在幂等

---

## note 档明细（2 条 — 架构方向 / recovery arc）

### DEV-06-06A-REVERSE-DEPENDENCY-STRATEGY-D → D'（CEO re-review 校正）

- **等级**: note (架构方向声明，非 code deviation)
- **场景**: Plan 06 阶段短期保留 ps `shared/` (vendor = copy not move); **Plan 07 承接架构最终态** — custos toolkit 是 shared 主体权威，ps 收敛为策略研发副本（团队新指标 / 实验代码，稳定后回流 custos）
- **CEO re-review 2026-07-09**: 校正 initial DEV 措辞（"transitional state" 一度被写成 permanent）。cross-references:
  - `.forge/README.md:59` §执行顺序建议
  - Plan 05 DEV-05-TOOLKIT-LOCATION
  - Plan 06 §Plan 06/07 boundary
  - 04-05-06-execute-team-packet §Plan 06 §Out
- **06a 落地影响**: T3.2 vendored trees 是 byte-identical snapshots，可以 widen 或 narrow；T1.1/T1.2 engine-side plumb 不 depend on subset 精确 shape；T2 ps-side config 承载策略 owner intent 独立于权威位置。**唯一 Plan 07 敏感点是 T3.3 exemption allow-list** — Plan 07 widens vendored subset 时 allow-list 需 re-baseline（小机械 delta，非 rework）
- **状态**: ✅ 已 accept，Plan 07 承接最终态

### DEV-06-06A-CEO-PAUSE-FOR-PLAN-07-CROSSED

- **等级**: note (recovery arc, lesson #34 教科书应用)
- **场景**: CEO 发 pause-06a 指令 (要求 T3.2 partial delivery + Plan 07 架构澄清后再继续); 但 executor 已完成剩余 5 task (T1.1 phase B / T1.2 / T2.1 / T2.2 / T3.3) + 初版 close-out marker `cba207c`。两条信息 in-flight 交叉
- **lesson #34 应用**: executor 未静默按 pause 指令回滚到 `git reset --hard`; 而是**上报实际状态** (7 landed commits, all tests green, marker written) 并 offer 4 选项 (accept-all / revert-to-731425e / keep-with-pause-note / other), 等 CEO 方向再动。CEO 复核 executor 论证 (T3.2 vendored snapshot + T1.1/T1.2 engine-side plumb + T2 config 都保留 Plan 07 architectural freedom) 后选 Option (I): accept full 06a delivery
- **follow-up (candidate lesson C3)**: spawner 发 pause 指令前应先 verify executor 实际进度状态；executor 收 crossed 指令应把 lesson #34 作为 teammate-exemplar path
- **状态**: ✅ 已 accept + lesson C3 candidate 记录

---

## Cross-repo 记账（非 DEV, 但需保留 audit trail）

ps repo `develop` HEAD `34b73a2` (2 commits 独立落地):
- `3443e96 feat(nautilus): supertrend production tier risk config`
- `34b73a2 test(nautilus): assert supertrend RiskController activates and blocks on drawdown`

跨仓 commit choreography (DEV-06-CROSS-REPO-COMMIT-CHOREOGRAPHY):
- custos + ps 是**独立仓库 with 独立 commit sequence**, 无 atomic guarantee
- custos commit scope=`custos`, ps commit scope=按 ps convention
- e2e integration acceptance deferred 到 06b Track 5 (由 Plan 08 吸收)

---

## Plan 06b 追踪清单（Plan 08 承接 partial close-out）

由 Plan 08 收尾并统一签发 Plan 06 完整 close-out 时需处理:
1. Track 5 T5.1 sandbox e2e (无 arx, custos 独立 clone 场景 vendored `strategy.py` 快照 or `@pytest.mark.integration`) — 参见 authority-reviewer FU-AUTH-3
2. Track 5 T5.2 testnet paper→testnet e2e (@integration, 依赖网络/testnet 资金, 可能独立 session)
3. Track 6 T6.1 ps sidecar/runner 退休 docs (docs-only, DP3)
4. Track 6 T6.2 Plan 06 完整 close-out（含红线 gate 满足度表填实 + 契约影响列全）

---

## 红线守护实证 (06a 落地时 grep 记录)

来自 marker `constraints_honored`（`.forge/dispatch-log/.../runner-executor-06a-v1.complete.json`）:

- **0.1 Key/KEK 永不出进程**: `grep 'log.(info|debug|warning).*api[_-]?key' src/ tests/` = 0；新 code (host.py plumb, strategy_loader.py registry check) 只 touch spec/config dict-keys, 不涉及 credential material
- **0.2 G6 gate 不绕过**: `grep 'CEXOMS|BinanceClient|OKXClient' src/ excluding host.py/venue_binance.py/toolkit/` = 0；G6 gate 契约不变；toolkit code_hash scope 保留 (DEV-06-TOOLKIT-HASH-SCOPE, DP4=A)
- **0.3 失联 ≠ 停止**: `grep 'stop_all_strategies|force_shutdown' src/custos/core/reconcile.py` = 0；RiskController per-strategy 层为 supertrend 激活 (T2.1/T2.2)
- **0.4 Money math Decimal**: `grep 'float(.*(price|amount|notional))' src/custos/ --exclude-dir=toolkit` = 0；vendored toolkit float documented as non-fund-flow exemptions (T3.3 watchdog)

---

## Follow-up 建议

- Plan 08 起草时确认 06b 范围完全对齐（Track 5 e2e + Track 6 docs + close-out），不要重复吸收 06a 已完成的 Tracks 1-4
- lesson C3 candidate (crossed instruction, spawner-side pause verify) 已在 Plan 07/08/09 packet 里记录 — 起草期间展开为独立 lesson
- Plan 07 curation scope 决策会 impact T3.3 allow-list（需 re-baseline）+ TOOLKIT_PROVENANCE.md drift monitoring 节奏
