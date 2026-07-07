# Plan 00a Peer Review — Codex L1

- **Date**: 2026-07-07
- **Reviewer**: codex-cli 0.142.0 (`model_reasoning_effort=high`, sandbox=read-only)
- **Scope**: `custos/00a/runner` @ `77dabff` vs `main` @ `b60c41f`
- **Diff**: 17 files, +1803 / -31
- **Protocol**: lesson #10/#12/#19 fallback chain L1 (`-c effort=high` + `-o` + `< /dev/null` + `timeout 600`)
- **Cost**: 1/3 codex calls (budget from `teams.yaml` codex_audit.max_codex_calls_per_plan)

## Raw Findings

```json
[
  {
    "id": "F1",
    "severity": "high",
    "file": "src/arx_runner/nautilus_host.py",
    "line": 134,
    "category": "red-line",
    "issue": "Host state retains credentials transitively through the active TradingNode",
    "evidence": "self._active_nodes[spec_id] = (node, task); node_config.data_clients contains data_cfg built with api_key/api_secret at src/arx_runner/_nt_binance_venue.py:103-111",
    "recommendation": "Do not pass live credentials into the sandbox data config if public market data is sufficient. If NT requires credentials, treat this as explicit credential retention: document it, redact repr/log surfaces, and replace the current fake repr-based test with an object graph assertion or a redaction invariant."
  },
  {
    "id": "F2",
    "severity": "high",
    "file": "src/arx_runner/nautilus_host.py",
    "line": 126,
    "category": "red-line",
    "issue": "Unredacted NT exception messages are logged after credential-bearing config is constructed",
    "evidence": "_log.error(\"nt_startup_failure\", spec_id=spec_id, error=str(exc)); background task failures also log error=str(exc) at line 213",
    "recommendation": "Log exception type and a sanitized error code/message only. Add a redaction helper that strips api_key/api_secret and use it for startup and run-loop errors."
  },
  {
    "id": "F3",
    "severity": "medium",
    "file": "src/arx_runner/nautilus_host.py",
    "line": 134,
    "category": "correctness",
    "issue": "Deploying the same spec_id twice overwrites the active node without stopping the old task",
    "evidence": "self._active_nodes[spec_id] = (node, task) has no prior-entry check or cleanup",
    "recommendation": "Reject duplicate deploys for an active spec_id or serialize deploy/stop with a lock and stop the previous node before replacement."
  },
  {
    "id": "F4",
    "severity": "medium",
    "file": "src/arx_runner/nautilus_host.py",
    "line": 207,
    "category": "robustness",
    "issue": "Completed or failed background run tasks leave stale entries in _active_nodes",
    "evidence": "_on_node_task_done only logs task.exception(); it never removes spec_id from _active_nodes or disposes the node",
    "recommendation": "In the done callback, if the stored task matches, remove the active entry and dispose the node or schedule an async cleanup path."
  },
  {
    "id": "F5",
    "severity": "medium",
    "file": "src/arx_runner/nautilus_host.py",
    "line": 129,
    "category": "correctness",
    "issue": "Strategy instantiation/add failure after node.build leaks the built node",
    "evidence": "node.build() is inside the try block, but strategy = self._instantiate_strategy(...) and node.trader.add_strategy(strategy) run after it with no dispose cleanup",
    "recommendation": "Either instantiate the strategy before building the node or extend the startup try/finally so any failure before active registration disposes the built node."
  },
  {
    "id": "F6",
    "severity": "medium",
    "file": "Makefile",
    "line": 41,
    "category": "test-quality",
    "issue": "verify-nt can pass without exercising real NT because NT tests importorskip",
    "evidence": "test-nt runs `uv run --extra nt-runtime pytest ...`, while NT suites use pytest.importorskip(\"nautilus_trader\") at tests/test_nt_binance_venue.py:17, tests/test_nt_trading_node_host.py:24, and tests/test_nt_trading_node_host_integration.py:22",
    "recommendation": "Add a preflight import/version check to test-nt, or make import absence a hard failure under the NT gate while preserving importorskip only for baseline."
  }
]
```

## Lead Triage (2026-07-07, Team-Lead)

| ID | Severity | Codex Category | Lead Decision | Rationale |
|---|---|---|---|---|
| F1 | high | red-line | **Follow-up, not blocking** | credential 在 in-process TradingNode 内存持有是 NT 与 exchange 通信的**设计必要**, 不违反红线 0.1 (禁 "log/publish/send raw"); 但 codex 建议加 redaction invariant test 是合理 hardening — 记入 `.forge/README.md` 后续 plan / 或独立 style plan (`03-nt-host-hardening.md`), 不阻塞本 plan close-out |
| F2 | high | red-line | **Fix now** | `str(exc)` 若 NT exception message 内含 config repr 会间接泄漏 credential; 保守做法加 exception redaction helper (grep api_key/secret pattern → sanitize) 立即修 |
| F3 | medium | correctness | **Fix now** | dup deploy overwrite = 资源泄漏 + 并发 bug, 简单单文件 fix |
| F4 | medium | robustness | **Fix now** | task done 不清 `_active_nodes` → dict 泄漏, 简单 callback fix |
| F5 | medium | correctness | **Fix now** | build() 后 add_strategy fail → built node 泄漏, try/finally 或调换顺序 |
| F6 | medium | test-quality | **Fix now** | `verify-nt` 若被 `importorskip` 静默 skip 就是 fake gate; 加 Makefile preflight `python -c "import nautilus_trader"` 或改 conftest 在 verify-nt 环境强制 NT |

**5 fix-now findings** (F2/F3/F4/F5/F6) → 一轮 executor round 2 fix。**1 follow-up** (F1) → 记 `.forge/README.md` 后续 plan 段。

## Follow-up Plan Candidate

**`03-nt-host-hardening.md`** (proposed, low priority): 加 credential lifecycle test suite (F1 hardening invariant) + reconcile 流程增加 credential lifetime sanitization; verifies "no credential in node repr / node.__dict__ recursive dump / structlog processor output" 三层 invariant。
