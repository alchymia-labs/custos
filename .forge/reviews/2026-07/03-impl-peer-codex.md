# Plan 03 Implementation Peer Review — Codex L1 high effort (Code Review)

**Reviewer**: codex-cli 0.142.0, model_reasoning_effort=high, read-only sandbox
**Review type**: Implementation Code Review (Phase 3, 非 plan review — Phase 2 已单独有 `03-peer-codex.md`)
**Reviewed at commit**: `custos/03/runner` HEAD `5f5915e` (diff base `main` @ `1cd5ca0`)
**Reviewed at**: 2026-07-09
**Fallback chain level**: L1 (成功, 无需 L2/L3/L4)

---

HIGH: F1 no longer tests the promised node/host object graph
File: `tests/test_credential_lifecycle.py:19`
Symptom: `test_node_dict_recursive_no_credential` walks `TradingNodeConfig` directly, not a `TradingNode`, `node.__dict__`, or `host._active_nodes`.
Root cause: Commit `23c7a17` replaced the original native-node walk after a shared-process SIGABRT, but the deviation log claims this is equivalent. It is not: config-only walking cannot catch a future/raw credential copy into `TradingNode.__dict__` or another host-retained Python object.
Suggested fix: Run the real native `TradingNode(config)` walk in an isolated subprocess and assert the child exits cleanly with no sentinel leaves. If that is not viable, downgrade/rename F1 and the red-line close-out claim instead of calling it equivalent.

LOW: wire-shape test does not pin `payload_schema_version == 1`
File: `tests/test_wire_shapes.py:41`
Symptom: The test only asserts `payload_schema_version` exists and legacy `schema_version` is absent; it does not assert the value is `1`.
Root cause: Schema preservation is currently enforced by `NatsEnvelope` default/tests elsewhere, not by the specific wire fixture test called out in D3.
Suggested fix: Add a parametrized assertion in `tests/test_wire_shapes.py`: `assert env["payload_schema_version"] == 1`.

INFO: D2-D4 mostly match implementation
File: `src/arx_runner/nt_risk_engine.py:122`
Symptom: `client_order_id` is hash-input-only, no `PreTradeRejected` wire field added; call site passes `str(getattr(...))`; `payload_schema_version` remains `1`; matrix tests assert `phase="running"` / `health="healthy"`; GC property names match `_pending`, `_cleanup_tasks`, `_wal_drain_task`.
Root cause: No issue found in these dimensions.
Suggested fix: None.

Verdict: REQUEST_CHANGES
Rationale: The implementation is otherwise tight, but F1 is a red-line verification contract and the current test does not prove the stated `node.__dict__` invariant. The SIGABRT deviation is understandable, but the replacement proof is narrower than the plan and close-out claim. Add an isolated native-node walk or explicitly downgrade the contract before approval.