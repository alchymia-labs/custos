# Plan 00b — Safety-Validator Approval Gate Report

- **Reviewer**: custos/00b/safety-validator (`claude-opus-4-6[1m]`, read-only)
- **Plan**: `.forge/plans/2026-07/00b-telemetry-bridge-nt-messagebus.md`
- **reviewed_at_commit**: `f6d0e684` (actual branch HEAD — see SHA-gate note §0)
- **base**: `232c5a6` (main)
- **diff**: 11 files, +1260/-49 (7 code/test commits + 1 docs addenda)
- **Final verdict**: **APPROVE** (merge SHA gate must target `f6d0e684`, not `1b3bb81`)

---

## §0 SHA-gate note (lesson #32 / #34)

Team-lead pre-merge instruction cited branch HEAD = `1b3bb81` (the close-out marker commit).
Independent `git rev-parse custos/00b/runner` = **`f6d0e684`** — there is **one commit beyond the
marker's SHA**.

| | SHA | content |
|---|---|---|
| marker commit | `1b3bb81` | close-out (marker + plan + index) |
| **actual HEAD** | **`f6d0e684`** | close-out **addenda**: DEV-00B-DEAD-SUBSCRIPTION dual-root-cause + safety-validator concrete-type-discriminator constraint recorded + DEV-00B-LESSON-29-EXTENSION |

**Delta `1b3bb81..f6d0e684` is docs-only** (`marker.complete.json` + plan `.md`, +28/-5, no `src/`
or `tests/` change) — per lesson #32 it does **not** require a code-review re-run. But the
**merge-time SHA gate + marker `commits[-1]` must be reconciled to `f6d0e684`** before squash-merge,
or the addenda (which records my #11 constraint into the deviation log) is dropped. Flagged to
team-lead.

Worktree tree clean at HEAD except one untracked peer artifact
(`.forge/reviews/2026-07/00b-tdd-enforcer-report.md`).

---

## §1 Non-Custodial 4 红线 — grep probes @ `f6d0e684` (vs clean baseline @ 232c5a6)

| 红线 | probe | baseline | HEAD | verdict |
|---|---|---|---|---|
| 0.1a | `log.*(api_key\|secret\|kek)` in `src/` | 0 | 0 | PASS |
| 0.1b | `publish/send/envelope/payload.*(api_key\|secret)` | 0 | 0 | PASS |
| 0.1c | cloud SDK (`boto3/google.cloud/azure`) import | 0 | 0 | PASS |
| 0.2 | self-built venue client outside host/venue | 0 | 0 | PASS |
| 0.3 | `stop_all_strategies/force_shutdown` | 0 | 0 | PASS |
| 0.4 | `float(price/qty/amount/notional/px/fee)` | 0 | 0 | PASS |
| #21 | `except: pass` / silent drop-return | 0 | 0 | PASS |

No red-line regression. All four load-bearing walls hold.

---

## §2 Approval Gate Checklist — 8 base + 4 wildcard 特化 (#9-12)

### Base checklist (teams.yaml `executor_team.safety_validator.checklist`)

| # | item | verdict | evidence |
|---|---|---|---|
| 1 | Key/plaintext 不出进程 (KEK request-scoped) | **PASS** | 00b 不触 `credential_vault`; `deploy(spec, credential)` 收 credential 但 telemetry/reject bridge 只吃 NT event 不碰 credential; `_sanitize_exception` (`nautilus_host.py:64-74`) 防异常消息带 key |
| 2 | G6 gate 不绕过 | **PASS** | `deployment_reconciler.py` 不在 diff（G6 gate 未改）; `__main__.py:_build_host` 注释明示 "does not bypass the G6 gate"; attach 发生在 `deploy()` node build 之后, gate 之内 |
| 3 | 失联≠停止 | **PASS** | publish 失败 log 不 crash (`nt_risk_engine.py:227-235` error log; `telemetry_actor.py:526` BLE001 "never crash the NT engine thread"); attach 失败 degrade 不 abort deploy (`nautilus_host.py:290-292`) |
| 4 | 对账不静默 (独立 subject + str Decimal) | **PASS** | reject 走独立 `arx.{tenant}.pre_trade_reject.{runner_id}` (`nt_risk_engine.py:160-164` via `build_subject`); telemetry 走 `arx.{tenant}.telemetry.{runner}.{session}`; money 全 str |
| 5 | 上报不含 key 明文/策略源码 | **PASS** | normalizers 只取 order/position 元数据 (`client_order_id/symbol/side/qty/price/fee/pnl/ts`, `telemetry_actor.py:435-460`); reject payload 5 字段无 credential |
| 6 | EnrollmentToken 一次性 + paper_only 不发 live | **N/A** | 00b 不触 `enrollment.py` (超出 plan 范围) |
| 7 | Python 用 uv (禁 pip) | **PASS** | `grep -rE 'pip install\|python -m pip'` src/ tests/ = 0 命中 |
| 8 | silent path 接 structlog (lesson #21) | **PASS** | silent-drop grep 0 命中; 每个 `except` 均 log 或带 `# noqa: BLE001 <reason>` (fail-safe 注明) |

### Wildcard 特化 (`events.order.*` + type-filter dispatcher, DEV-00B-DEAD-SUBSCRIPTION)

| # | item | verdict | evidence |
|---|---|---|---|
| 9 | raw-key 泄露面 | **PASS (baseline 事实)** | NT `model/events/order.pyx` 17 个 order event 类 grep `api_key\|secret\|token\|password\|credential` = 0 命中; wildcard 不扩大 raw-key 面 |
| 10 | drop 路径不静默吞失败 | **PASS (designed-filter 框架)** | `nt_risk_engine.py:209-210` `if type(event).__name__ != "OrderDenied": return` = designed-filter 裸 return（数据流路由, 非错误处理, 不适用 lesson #21）; telemetry `on_event:211-217` whitelist drop 带 DEBUG log; 无 `except: pass` |
| 11 | type discriminator = concrete class (**block-level**) | **PASS** | `nt_risk_engine.py:209` `type(event).__name__ == "OrderDenied"` (精确 class-name), **非** `hasattr(reason)`; `on_order_denied:245` 的 `hasattr` 是 type-match **之后**的 shape guard, 非判据; telemetry `NtTelemetryBridge:502-503` 同样用 class-name whitelist (`TELEMETRY_ORDER_EVENT_TYPES`) |
| 12 | envelope 字段只源自 OrderDenied | **PASS** | payload 5 字段 (`tenant_id/rule_id/symbol/order_fingerprint/reject_reason`, `nt_risk_engine.py:279-285`) 全部在 line 209 type-match + 245 shape guard 之后从 `denied` 提取; `tenant_id` 来自 bridge 实例; 无跨类型拉字段 |

**#11 关键实证 (为何 concrete class 必须)**: order.pyx 4 个 event 类共享 `reason` 字段 —
`OrderDenied:637`(reason:797) / `OrderRejected:1952`(2130) / `OrderModifyRejected:3621`(3673) /
`OrderCancelRejected:3915`(3967)。若走 `hasattr(reason)` duck-typed 判据会把 3 个 sibling reject 类
误分类成 OrderDenied → 伪造 pre_trade_reject。executor 用 `type(event).__name__ == "OrderDenied"`
精确匹配, 规避此语义污染。**block 判据满足。**

---

## §3 特化关注点 verdict

- **Q1 架构分歧 (duck-typed vs NT Actor 子类)**: executor 选 **A (duck-typed)** —
  `telemetry_actor.py` 无 top-level `import nautilus_trader` (只 stdlib + arx_runner internal), NtTelemetryBridge 用 `event: Any`。**我原先对 Q1=B 引 NT 硬依赖泄露 credential 的担忧不成立** (选了 A)。PASS。
- **E multi-spec 隔离**: `_telemetry_actors: dict[str, TelemetryActor]` (`nautilus_host.py:143` **per spec_id**, 非全局单例); `_attach_observability` 每 deploy create 新 actor (新 session_id) + 每 node.kernel.msgbus 独立 bootstrap; 测试 `test_multiple_specs_isolated_by_session_id` 覆盖。PASS。
- **红线 0.1 defense-in-depth**: `_sanitize_exception` (`nautilus_host.py:64-74`) — 异常消息可能回显 credential（如 venue client error），host 只 log 异常类型不 log 消息。superior 防御。
- **money 契约 (红线 0.4) 多层**: (a) `MONEY_FIELD_NAMES` frozenset 15 字段; (b) `_reject_floats_in_money_fields` fail-fast 拒 float **和 bool** (bool 显式, 因 `isinstance(True,float)=False` 但 round-trip 成 1.0); (c) normalizers 从 NT `to_dict` 取 string + `_split_money` 拆 CCY 后缀 → 纯 decimal str。

---

## §4 Findings

无 blocker。无 follow-up 阻塞项。以下为非阻塞观察：

- **[INFO] SHA-gate 漂移 (lesson #32)**: 真实 HEAD `f6d0e684` ≠ marker `1b3bb81`（docs-only delta）。merge SHA gate + marker `commits[-1]` 需 reconcile 到 `f6d0e684`。见 §0。已 flag team-lead。
- **[INFO/minor] `_on_publish_done:232`**: `except (asyncio.CancelledError, Exception): return` catch 面偏宽（`fut.exception()` 实际只会 raise CancelledError），但带 `# noqa: BLE001 — reaping the scheduled future` 注明 + 真实失败路径 (line 234-235) log ERROR。fail-safe 注明, 非违规, 不需改。
- **[INFO] executor self-reflect round 1 (commit `e688242`)**: 主动抓 fire-and-forget task GC-safety bug（`self._pending.add(fut)` 持引用防 GC）—— 良性 executor 自纠, 非我提出。
- **executor 3 followups (F1 heartbeat 并存 / F2 fingerprint 退化 / F3 `or ""` 防御)** 非阻塞, 与红线无关, 认可 defer。

---

## §5 Final Verdict

**APPROVE** — reviewed_at_commit `f6d0e684`.

Non-Custodial 4 红线全数守住 (grep 0 回归); 12 项 checklist 全 PASS/N-A (无 FAIL); block-level #11
concrete-type-discriminator 判据满足; `make verify` 发布门 205 passed 绿 (9 wire_shapes 失败 =
pre-existing DEV-01-WIRE-FIXTURES 跨仓 fixture 排除, base 232c5a6 已存在, 非 00b 引入); lesson #25
契约表 5 test 全实存。

**Merge 条件**: worktree-manager squash-merge 前 SHA gate reconcile 到 `f6d0e684` (§0)。
