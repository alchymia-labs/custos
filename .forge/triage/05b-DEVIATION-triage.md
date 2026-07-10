# Plan 05 05b slice DEVIATION Triage (Step 6.4a — full close-out)

**Plan**: `05-structural-refactor-engine-abstraction.md` — arx_runner → custos rename + core/engines/cli 分层 + ExecutionEngineProtocol + G6 gate 抽出
**Slice**: **05b** (Tracks 5-7 + T-final — pyproject extras + subject v2 docs + engine stubs + Plan 05 完整 close-out; 加性/docs, 无红线风险)
**Slice landed**: `79c1858` (T5.1) → `6528c42` (T5.2) → `591a1a4` (T6.1) → `e82825d` (T7.1) → close-out commit (T-final)
**Predecessor**: 05a `4f0192a` + hotfix `7ffa187` (see `.forge/triage/05a-DEVIATION-triage.md`)
**Triaged at**: 2026-07-10
**Triager**: runner-executor-05b (self-triage per execute-team protocol)
**Protocol**: `.claude/rules/deviation-protocol.md` + `templates/teams/deviation-triage.md`

---

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH | **0** | (无 HIGH triage) |
| MED | **0** | — |
| LOW | **1** | 仅记, 无需 AskUser 或 fix-now |

**Overall triage verdict**: **ALL LOW — 可放行 Plan 05 完整 close-out**, 无阻断项。

---

## LOW 档明细（1 条）

### DEV-05b-ARX-RUNNER-RESIDUE-SWEEP

- **等级**: LOW
- **场景**: T5.2 (nt-runtime → nautilus fanout) 执行前的 Foundation Scan 例行核实了 05a 的
  "全仓 `arx_runner` 引用 0 命中 (除归档 plan .md)" 声明，发现该声明**不完全准确**——
  `scripts/` 与 `examples/` 两个目录不在 Plan 05 Track 1 File Inventory 声明范围内
  (A/B/C/D 段均未列出)，导致 scout 的原始 grep 未覆盖到它们，05a 的 T1.1/T1.2 也未扫到：
  - `examples/supertrend-testnet/Dockerfile:30` — `ENTRYPOINT ["uv", "run", "python", "-m", "arx_runner"]`（真实功能性 bug：容器构建后 entrypoint 会 `ModuleNotFoundError`，因为 `arx_runner` 包已在 05a 被 rename 为 `custos`）
  - `scripts/generate_wire_fixtures.py:16` — `from arx_runner.nats_client import NatsEnvelope, OrderingMeta`（同样真实功能性 bug：脚本会在 import 阶段失败）

  逐文件核实全仓其余 5 处 `arx_runner` 命中（`README.md:116` / `.claude/rules/mandatory-rules.md:55` / `.claude/rules/historical-lessons.md:89,164` / `.forge/README.md:39,55,105` / `docs/domain.md:71,331` / `docs/design/03-implementation.md:84`）后确认它们**均为历史性描述文本**（"rename `arx_runner` → `custos` 已由 Plan 05 完成"这类过去式陈述，或 `docs/domain.md` 描述 arx 仓库抽出前的真实历史路径），非功能性代码引用，故意保留不改，与 05a Track 1 File Inventory §E 归档不改的精神一致。
- **决定**: 两处真实 bug 已在 T5.2 commit (`6528c42`) 内顺手修复（Dockerfile 恰好同时也在做 `nt-runtime`→`nautilus` 改动，import 语句同理修正为 `from custos.core.nats_client import ...`）；5 处历史性文本保留不改
- **根因**: Plan 05 Track 1 File Inventory 的 File Inventory 未覆盖 `scripts/` 和 `examples/` 目录（这两个目录不在 A/B/C/D/E 任一段落中枚举），是 evidence-scout Foundation Scan 覆盖盲区（生态 lesson #14 续编场景：起 plan 时系统扫骨架未覆盖到这两个非 `src/`/`tests/` 的辅助目录）
- **影响**: 2 文件（`examples/supertrend-testnet/Dockerfile` + `scripts/generate_wire_fixtures.py`），均不在 04b 并行执行的 territory 内（04b 只 touch `src/custos/core/` + `tests/core/` + `docs/design/*.md`），无 merge 冲突风险
- **状态**: ✅ 已 fix + accept，形式偏离已如实记录（lesson #9/#11/#14 diligence 的正例，未静默跳过）

---

## 红线守护实证 (05b 落地时守护记录)

- **0.1 Key/KEK 永不出进程**: 05b 纯 docs + build-config 改动，不 touch credential 路径
- **0.2 G6 gate 不绕过**: 05b 不 touch G6 gate 代码；`make verify` 263 passed 含全部 G6 gate 测试
- **0.3 失联 ≠ 停止**: 05b 不 touch reconcile 逻辑
- **0.4 Money math Decimal**: 05b 不 touch money math 路径；T-final 红线专项 grep 复核发现的
  vendored toolkit 1 处 float 例外由 Plan 06 06a slice 引入（早于本切片），非本切片新增，
  已在 plan 红线 gate 满足度表标注

---

## Follow-up 建议

- 生态 lesson #14 (Foundation Scan Gate) 续编素材：evidence-scout 起 plan 时的目录扫描应
  显式覆盖 `scripts/` 和 `examples/` 等非 `src/`/`tests/` 辅助目录，不能只扫 A/B/C/D
  段落里显式枚举到的路径
- 无阻断 Plan 07/08/09 后续 plan 的发现
