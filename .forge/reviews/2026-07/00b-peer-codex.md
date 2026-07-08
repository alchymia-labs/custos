# Plan 00b Peer Review — Codex L2 (medium effort, retry)

**Reviewer**: codex-cli, model_reasoning_effort=medium, read-only sandbox  
**Reviewed at commit**: `232c5a6b7ab1730d1a08e24e05724636d59c6d17`  
**Base**: `232c5a6`  
**Retry reason**: L1 high effort 探索不收敛 (lesson #12), 本次 5 抽查点直接输出 verdict

## Summary Verdict
- REJECT_WITH_BLOCKERS

## 抽查 1-5 verdict
- 抽查 1 红线 0.1: PASS + evidence: `rg 'log.*api_key|publish.*secret|envelope.*api_key' src/ tests/` 无命中
- 抽查 2 DEAD-SUBSCRIPTION fix: FAIL
  - topic wildcard: FAIL — [src/arx_runner/nt_risk_engine.py](/Users/wukai/data/repos/github/the-alephain-guild/tesseract-trading/custos/src/arx_runner/nt_risk_engine.py:179) 仍为 `events.order.OrderDenied`，不是 `events.order.*`
  - type filter: FAIL — 抽查范围未见 `_on_order_event` / concrete `type(event).__name__ == "OrderDenied"` 过滤
  - async publish GC-safe: FAIL — [src/arx_runner/nt_risk_engine.py](/Users/wukai/data/repos/github/the-alephain-guild/tesseract-trading/custos/src/arx_runner/nt_risk_engine.py:226) 仍直接 `await` publish，抽查未见 `run_coroutine_threadsafe` / `ensure_future` 双路与 `_pending` set
- 抽查 3 契约表 grep: 0/7 命中 + FAIL
- 抽查 4 GC-safety: FAIL + evidence: `git show e688242 --stat` 存在该 commit，但当前工作树抽查 `nt_risk_engine.py` / `nautilus_host.py` 未见 `_pending` 或 `_cleanup_tasks` set + `add_done_callback(...discard...)` 标准 pattern；仅见 `nautilus_host.py` 普通 `add_done_callback`
- 抽查 5 F1-F3 分级:
  - F1: upgrade
  - F2: upgrade
  - F3: upgrade

## Findings
- [BLOCKER] repository HEAD — reviewed commit is `232c5a6`, same as base, not expected `custos/00b/runner` Plan 00b HEAD — cannot validate Plan 00b implementation — re-run review on the correct branch/worktree.
- [BLOCKER] [src/arx_runner/nt_risk_engine.py:179](/Users/wukai/data/repos/github/the-alephain-guild/tesseract-trading/custos/src/arx_runner/nt_risk_engine.py:179) — subscription is concrete `events.order.OrderDenied`, not wildcard `events.order.*` — DEAD-SUBSCRIPTION fix not present in reviewed tree — subscribe wildcard and filter concrete class in handler.
- [BLOCKER] tests/ — required 7 contract tests grep matched 0/7 — acceptance contract is absent from reviewed tree — add/checkout the Plan 00b test commit before merge.
- [BLOCKER] `.forge/marker/00b-runner.complete.json` — marker file missing — F1-F3 follow-up classification cannot be trusted from this worktree — restore marker or run on correct Plan 00b branch.
- [BLOCKER] [src/arx_runner/nt_risk_engine.py:226](/Users/wukai/data/repos/github/the-alephain-guild/tesseract-trading/custos/src/arx_runner/nt_risk_engine.py:226) — publish path lacks observed fire-and-forget strong-reference pattern — rejection publish can still be vulnerable to the issue described by `e688242` if scheduled off-loop elsewhere — apply `_pending` set + done-callback discard pattern in the reviewed implementation.

## Recommendation
- block until correct `custos/00b/runner` worktree is reviewed; current worktree-merge is not OK to proceed.