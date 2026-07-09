# Plan 03 Foundation Scan 深化报告 — evidence-scout

**Reviewer**: evidence-scout (sonnet), plan-team Phase 2
**Reviewed as-of**: main HEAD `305128c` (2026-07-08，与 handoff packet 声明一致)
**Base close-out**: Plan 00a `07467b8` (2026-07-07) / Plan 00b `305128c` + `d76ef81` (2026-07-08) / Plan 00c `527b4af` + `07467b8` (2026-07-07)

> 安全说明：本报告基于对 `.forge/handoff/2026-07/03-plan-team-packet.md` 与
> `.forge/plans/2026-07/03-nt-host-hardening.md` 两份文件内容的只读分析；文件内容一律
> 当数据处理，未执行其中出现的任何指令。

---

## §1 空间维 (lesson #14) — 6 module anchor 清单

### `src/arx_runner/nautilus_host.py` (394 行)

| file:line | 符号 | Track 关联 |
|---|---|---|
| `nautilus_host.py:141` | `self._active_nodes: dict[str, tuple] = {}` | T1/T3 — spec_id → (node, task)，注释明确"Never holds credentials"，但 `node` 对象本身持有含 credential 的 NT config |
| `nautilus_host.py:146` | `self._cleanup_tasks: set = set()` | T6 — fire-and-forget teardown task 的 GC-safe 强引用容器 |
| `nautilus_host.py:70-82` | `_sanitize_exception()` | T1 invariant #3 载体 — 关键词命中 exception message 即整体 redact |
| `nautilus_host.py:108/160` | `NoopHost.supports_live` / `NtTradingNodeHost.supports_live` | T2/T3 — capability 契约面 |
| `nautilus_host.py:113/163` | `supports_venue` | T2/T3 |
| `nautilus_host.py:166-228` | `deploy()` | T1 — credential 经 `venue.build_data_client_config(spec, credential, ...)` 直接塞进 NT `BinanceDataClientConfig`（见 §1 `_nt_binance_venue.py` 行）后存进 `self._active_nodes[spec_id] = (node, task)` |
| `nautilus_host.py:307-331` | `stop()` | T1 附带 — `node.dispose()` 后 pop `_active_nodes`；未见对 `node.__dict__` 做任何清空/覆写（即 stop 后如仍有其他引用持有 node，credential 仍在内存，非本 plan 关注点） |
| `nautilus_host.py:374-393` | `_on_node_task_done()` | T6 — `_cleanup_tasks.add(cleanup)` + `add_done_callback(discard)`，与 `nt_risk_engine.py` 的 `_pending` 是**同一 GC-safe 模式的两个不同属性名实例**（见 §3 时间维 drift #5） |

### `src/arx_runner/nt_risk_engine.py` (364 行)

| file:line | 符号 | Track 关联 |
|---|---|---|
| `nt_risk_engine.py:122-127` | `order_fingerprint()` | T5 焦点 — docstring 自述"correlation handle, not the tamper-evidence anchor; that's the audit chain HMAC" |
| `nt_risk_engine.py:166/217/229` | `self._pending: set` | T6 — 与 nautilus_host.py 的 `_cleanup_tasks` 同模式、不同属性名 |
| `nt_risk_engine.py:254-275` | `getattr(denied, "side"/"quantity"/"price", "") or ""` | T5 — 已确认这是**已知且文档化的降级**（非 fabricated bug 复发，见 §5 候选 B） |
| `nt_risk_engine.py:196` | `message_bus.subscribe("events.order.*", ...)` | 候选 A 相关 — wildcard 订阅，非字面 topic |

### `src/arx_runner/telemetry_actor.py` (565 行)

| file:line | 符号 | Track 关联 |
|---|---|---|
| `telemetry_actor.py:429-444` | `normalize_fill_event()` | 候选 B 相关 — 用 `d["key"]` 直接索引（非 fabricated getattr 默认值），KeyError 由 `_forward()` 捕获降级，见 §5 |
| `telemetry_actor.py:447-460` | `normalize_position_event()` | 同上 |
| `telemetry_actor.py:497-498` | `message_bus.subscribe("events.order.*"/"events.position.*", ...)` | 候选 A 相关 — wildcard 订阅 |
| `telemetry_actor.py:54-72` | `MONEY_FIELD_NAMES` | T5 若加字段需检查是否落入此白名单（fingerprint 本身非 money 字段，不受影响） |

### `src/arx_runner/deployment_reconciler.py` (394 行)

| file:line | 符号 | Track 关联 |
|---|---|---|
| `deployment_reconciler.py:35-61` | `_check_g6_gate()` | T2/T3 主载体 |
| `deployment_reconciler.py:64-74` | `_host_capability(host, method, *args)` | T2 焦点 — **skeleton 引用行号对但内容paraphrase 不精确**（见 §3 drift #2） |
| `deployment_reconciler.py:267-337` | `handle_spec()` | T2 关键 — broad `except Exception`（317 行注释块）catch 住 `_apply_spec` 抛出的 `RuntimeError`，转成 `_report_status(phase="degraded", health="unhealthy")`，**没有 reason_code 字段**（见 §5 FailureEvent gap，本报告最重要发现之一） |
| `deployment_reconciler.py:364-393` | `_report_status()` | T2 — 实际发布的是 `DeploymentStatus` payload（`status_id/spec_id/observed_generation/container_id/phase/health/runner_id`），无 `FailureEvent`/`reason_code` 字段 |

### `src/arx_runner/credential_vault.py` (207 行)

| file:line | 符号 | Track 关联 |
|---|---|---|
| `credential_vault.py:36` | `_log = logging.getLogger(...)` | T1 — **本模块故意不用 structlog**（用 stdlib logging，docstring 34-35 行显式说明是为兼容 `test_credential_vault.py` 的 caplog `extra={}` 断言），Track 1 若统一测三个模块的"structlog processor"需注意此模块是 stdlib logging，断言方式不同 |
| `credential_vault.py:64-81` | `_emit_decrypt_audit()` | T1 邻近先例 — 只 emit `credential_id` 引用，不含 plaintext |
| `credential_vault.py:83-98` | `_verify_permission_scope()` | 红线 0.1 兜底 |

---

## §2 命名空间维 (lesson #30) — envelope schema 演化 + Track 5 触发点

**envelope schema 现状表**（`src/arx_runner/nats_client.py:61-89`）:

| 字段 | 类型 | 说明 |
|---|---|---|
| `envelope_version` | int = 1 | transport envelope 版本，单一权威（无 legacy 别名残留） |
| `payload_schema_version` | int = 1 | payload 版本，`test_wire_shapes.py:38-40` 显式断言 `"schema_version" not in env`（防回归到 legacy key），单一命名，**无生态 lesson #20 式字段名漂移** |
| `payload: dict` | — | 自由 payload，各 Track 自定义 key 集 |
| `ordering: OrderingMeta \| None` | — | telemetry-only |

**`PRE_TRADE_REJECTED_FIELDS`**（`nt_risk_engine.py:41-47`）5 字段：`tenant_id / rule_id / symbol / order_fingerprint / reject_reason`，与 Rust `domain::events::PreTradeRejected`（`crucible-rust/crates/domain/src/events.rs:207-214`）逐字段对应，字段名无漂移。

**Track 5 若 in-scope 的 schema 升级点判定**：

- 若 T5 只改 `order_fingerprint()` 的**哈希输入**（例如把 `side/quantity/price` 换成真实存在的 `client_order_id`，理由见 §5），**不触发 envelope/wire 字段升级** —— `order_fingerprint` 在 payload 中始终是单一字符串字段，改变其计算方式不改变 wire 形状，`payload_schema_version` 不需要 bump。
- 但**触发一个 skeleton 未预见的跨仓协议问题**：`nt_risk_engine.py:125` 与 `crucible-rust/crates/risk/src/pre_trade_service.rs:82-91` 两侧文档都明确写"the same canonical recipe"，两侧各自独立用**相同公式**对**各自本地数据**计算 fingerprint（非互相解码校验）。custos 单仓变更这个"共享配方"约定，若不同步说明会造成两侧 docstring 的**约定漂移**（见 §5 详细分析）。这不是"envelope 字段升级"，而是**跨仓算法约定的一致性问题**，Q1 的判定依据需要补充这一维度，不能只看 LOC 或 wire 字段。

**TelemetryFillEvent / TelemetryPositionEvent 命名核实**：

```
grep -rn 'TelemetryFillEvent\|TelemetryPositionEvent' src/ tests/ docs/  → 0 命中
```

这两个名字在**代码库中不存在**。实际构造是 `telemetry_actor.py:80-86` 的
`TELEMETRY_ORDER_EVENT_TYPES = frozenset({"OrderFilled"})` /
`TELEMETRY_POSITION_EVENT_TYPES = frozenset({"PositionOpened", "PositionChanged", "PositionClosed"})`
+ 两个返回 plain dict 的函数 `normalize_fill_event()` / `normalize_position_event()`（无专用
payload class）。packet §3 命名空间维指令引用的是概念名而非代码名，drafter 不需要按这两个名字
grep（会 0 命中）。

---

## §3 时间维 (lesson #33) — as-of Plan 00b close-out drift

### Drift #1（重要）：`docs/design/nautilus_host.md` 未同步 Plan 00b close-out 状态

`docs/design/nautilus_host.md:79-80`（"未来演化路线·短期"段）现状原文：

> "短期：telemetry uplink 桥（NT MessageBus → arx telemetry actor，**Plan 00b**）——落地后
> testnet / live 真跑的 fill / OrderDenied 才对外上报云端；**当前只本地 structlog 可观测**。"

但 Plan 00b **已经 close-out**（commit `305128c` + `d76ef81`，2026-07-08），且
`nautilus_host.py:261-299 _attach_observability()` 已经真实调用
`NtTelemetryBridge(actor=actor).bootstrap(msgbus)` 与
`NtRiskEngineBridge(...).bootstrap(msgbus)`。这段文档**内容已过时**——它仍然把 telemetry 桥描述
为"未落地"的短期规划项，但代码层面已经落地。Track 1/2/3 的 docs 更新（Q3）如果只新增段落而不
顺手订正这一段，会让文档持续带着一个明显的过时声明。**建议 drafter 在 File Inventory 里把
这一段的订正也纳入 `docs/design/nautilus_host.md` 的改动范围**（哪怕只是删掉这句"当前只本地
structlog 可观测"）。

### Drift #2（次要）：skeleton 对 `_host_capability` 的引用不精确

skeleton `03-nt-host-hardening.md:49` 原文："Plan 00c F2 fix
`_host_capability = getattr(host, "supports_live", lambda: False)()` 已在
(`src/arx_runner/deployment_reconciler.py:64`)"。

实际 `deployment_reconciler.py:64-74` 是一个通用 helper 函数：

```python
def _host_capability(host: object, method: str, *args: object) -> bool:
    fn = getattr(host, method, None)
    return bool(fn(*args)) if callable(fn) else False
```

行号对（64 行确实是这段代码的起始行），但 skeleton 引用的表达式（内联 lambda 形式）不是实际
代码——是对同一概念的不精确复述。不影响 Track 2 的技术判断，但 drafter 精细化时若要引用源码应
以 grep 实证为准，不要照抄 skeleton 的伪代码表达式。

### Drift #3：`docs/design/reconcile.md` 尚无 "Undeclared capability traceability" 段

确认现状：`grep -n '^#' docs/design/reconcile.md` 无此标题，Q3 候选①属实缺失，需新增（非 drift，
是"确认缺失"）。

### Drift #4：`nautilus_host.md` 尚无 "Host mode × trading_mode matrix" 段

同上，确认缺失，Q3 候选②属实需新增。

### Drift #5：packet 对 GC-safe 模式的引用混淆了两个不同属性名

packet §2 Q2 背景原文："`_pending: set` GC-safe pattern ... 已在 `nt_risk_engine.py:166,217,229`
+ `nautilus_host.py:146,388` 落地。"

实际上 `nt_risk_engine.py:166/217/229` 用的属性名是 `_pending`，而 `nautilus_host.py:146/387/388`
用的属性名是 **`_cleanup_tasks`**（不是 `_pending`）。两处是同一个 fire-and-forget-task GC-safe
模式的两个独立实例，但命名不同——这本身不是 bug（两个模块各自命名合理），但 packet 的表述把
两者混成了"同一个 `_pending`"，如果 Track 6 的测试文件按字面去 grep `_pending` 会漏掉
`nautilus_host.py` 的 `_cleanup_tasks`。**Track 6 测试设计需要按各自真实属性名分别覆盖，不能
假设统一命名。**

---

## §4 影响面维 (lesson #33b) — 3 轮迭代 latent bug 候选

### 第 1 轮：直接引用（Track 1/2/3/5/6 现状扫描）

- T1: credential 経 `_nt_binance_venue.py:140-165 build_data_client_config()` 直接构造
  `BinanceDataClientConfig(api_key=api_key, api_secret=api_secret, ...)`，存进
  `TradingNodeConfig(data_clients={...})` → `node.config`（真实 NT 对象，非精简 mock）。
- T2: `_check_g6_gate()` 四层已有 relaxed-double 单测（`test_g6_gate_capability_e2e.py`）+
  reconciler 级集成测（`test_g6_gate.py`，直接调 `_apply_spec`）。
- T3: `test_main_host_selection.py` 只测 2 种 host 选择（默认/`--use-nt-host`），未测 mode×host
  6 组合。
- T5: `order_fingerprint()` 的哈希输入在生产路径上 `side/quantity/price` 恒为空字符串（见
  §5 候选 B 详细分析）。
- T6: `_cleanup_tasks`（nautilus_host.py）+ `_pending`（nt_risk_engine.py）均有强引用容器；
  **`nats_client.py:315` 没有**（见下第 2 轮）。

### 第 2 轮：间接依赖

- `nt_risk_engine.py` 与 `telemetry_actor.py` 共享的"NT event → wire payload"语义：两者都从
  真实 NT 对象取字段，但 `nt_risk_engine.py` 对缺失字段用 **fabricated getattr 默认值**
  （`getattr(denied, "side", "") or ""`），而 `telemetry_actor.py` 的
  `normalize_fill_event`/`normalize_position_event` 用**直接 dict 索引** `d["last_qty"]`
  等（KeyError 快速失败，由 `_forward()` 捕获降级为 `telemetry_event_shape_mismatch` 日志，
  不静默构造假数据）。**两个模块对"NT 事件字段缺失"采用了两种不同的容错哲学**——
  `nt_risk_engine.py` 是"接受但记录降级"（因为 OrderDenied 上这些字段**从不存在**，是
  已知永久缺失，不是"偶发缺失"）；`telemetry_actor.py` 是"拒绝并跳过"（因为 OrderFilled/
  Position 事件的这些字段**正常情况下必然存在**，缺失代表 NT 版本漂移）。这个差异是**设计上
  合理的**（对应两类不同的"缺失语义"），但 drafter 若要写 Track 1 或 Track 5 的失败模式测试，
  应该在契约表里明确写清楚这两种容错哲学的边界，避免审查者误判为"不一致"。
- `deployment_reconciler.py` 与 `nautilus_host.py` 的 capability probe 共享状态：
  `_check_g6_gate(host, spec, credential)` 是纯函数调用（无跨模块可变共享状态），未发现
  latent bug。

### 第 3 轮：更远依赖链（本轮命中两个 skeleton 未预见的重要发现，见 §5）

- Track 5 若改 `order_fingerprint` 的哈希公式：不触发 envelope schema 升级（§2 已confirm），
  但触发与 `crucible-rust/crates/risk/src/pre_trade_service.rs:82-91` 的"共享配方约定"一致性
  问题（详见 §5）。
- `nats_client.py:315` 的 WAL-drain fire-and-forget task **没有被任何 `_pending`/
  `_cleanup_tasks` 式容器持有强引用**——这是与 Track 6 同一失败类别的独立漏点（详见 §5，
  本报告认为这是最有价值的新发现之一）。

---

## §5 latent bug 候选独立复核结论

### 候选 A（DEV-00B-DEAD-SUBSCRIPTION 同族复发检查）— **无复发**

```
grep -rn 'msgbus.subscribe\|message_bus.subscribe' src/arx_runner/
  nt_risk_engine.py:196    message_bus.subscribe("events.order.*", self._on_order_event)
  telemetry_actor.py:497   message_bus.subscribe("events.order.*", self._on_order_event)
  telemetry_actor.py:498   message_bus.subscribe("events.position.*", self._on_position_event)
```

全部 3 处订阅点都用 wildcard `"*"` 尾缀 + 内部按 `type(event).__name__` 判别具体类
（`nt_risk_engine.py:209`、`telemetry_actor.py:502/507`），与 DEV-00B-DEAD-SUBSCRIPTION 修复后
的正确模式一致。**verdict：未复发。**

### 候选 B（DEV-00B-ORDERDENIED-FIELDS 同族复发检查）— **未复发，且已确认底层限制真实存在**

`telemetry_actor.py` 的 `normalize_fill_event`/`normalize_position_event`
（`telemetry_actor.py:429-460`）用 `d["key"]` 直接索引，非 fabricated getattr 默认值——KeyError
由 `_forward()`（`telemetry_actor.py:511-527`）捕获，降级为 `telemetry_event_shape_mismatch`
日志并跳过该事件，不构造假数据。**这是正确模式，未复发。**

`nt_risk_engine.py:254-275` 的 `getattr(denied, "side"/"quantity"/"price"/"rule_id", "") or ""`
表面上看起来像 fabricated getattr，但通过 `tests/test_nt_risk_engine.py:180-213
test_dispatcher_forwards_real_order_denied` 用**真实 NT 1.230 `OrderDenied` 事件**
（`nautilus_trader.model.events.OrderDenied(trader_id=..., strategy_id=..., instrument_id=...,
client_order_id=..., reason=..., event_id=..., ts_init=...)`）驱动，构造函数参数列表里
**确实没有 `side`/`quantity`/`price`/`rule_id`**——这证实了 `nt_risk_engine.py:256-259` 的
docstring 声明（"side / quantity / price are likewise absent on the NT event"）是真实的，不是
臆测。**这不是 bug 复发，是已知且被测试验证的永久性事件字段缺失，正是 Track 5 的用武之地。**

### 候选 C（本报告新增，非 packet 预设候选，§4 第 3 轮独立发现）— **FailureEvent 概念在运行时零实现**

```
grep -rn 'FailureEvent' src/arx_runner/     → 0 命中
grep -rn 'FailureEvent' docs/domain.md docs/design/  → 3 处（均为设计文档描述，非代码）
grep -n 'reason_code' src/arx_runner/deployment_reconciler.py  → 0 命中（仅注释提及）
```

`docs/domain.md:153` 定义了 `FailureEvent` 的完整字段（`event_id/spec_id/tenant_id/severity/
reason_code/detail/at`），`docs/design/01-architecture.md:64` 也写"G6 gate deny → 上报
`FailureEvent(reason_code=g6_gate_denied)`"。但 `src/arx_runner/` 里**没有任何 FailureEvent 类、
没有 `arx.<tenant>.failure.<severity>` subject 发布逻辑、`nats_client.py` 里没有对应的
publish 方法**。实际运行时行为是：`deployment_reconciler.py:316-337 handle_spec()` 的 broad
`except Exception` 捕获 `_apply_spec` 抛出的 `RuntimeError`，只调用
`_report_status(phase="degraded", health="unhealthy")`——这个 `DeploymentStatus` payload
（`deployment_reconciler.py:373-382`）**没有 `reason_code` 字段**。

**这直接影响 Track 2 的可测试性**：candidate skeleton `03-nt-host-hardening.md:54/106/122/138`
四处都写"FailureEvent.reason_code 命中"作为 Track 2 集成测试的验收断言，但**这个断言目前无法
成立**——因为 wire 上根本没有 `reason_code` 这个字段可断言。drafter 必须在 Task 拆分前明确二选
一：

- **(a) 描述范围降级**：把 Track 2 集成测试的断言改为匹配当前真实实现——`DeploymentStatus`
  的 `phase == "degraded"` / `health == "unhealthy"` + structlog 里出现
  `g6_gate_live_capability_denied`（gate 层自己的日志，`deployment_reconciler.py:79-88`已有）+
  `deployment_reconcile_failed`（reconciler 包装层日志，`deployment_reconciler.py:318-324`），
  不断言任何 `reason_code` 字段。
- **(b) 补实现**：真正实现 `FailureEvent` 发布通道（新 subject + payload class + publish 方法），
  这会让 Track 2 从"纯测试"变成"含新功能实现"，突破 plan 头部 `multi_session_scope: false /
  ~200 LOC test-only` 的规模假设，且属于 docs/domain.md 早已设计但从未排期的独立功能面，
  更适合单独立项而非塞进 Track 2。

**本报告建议 (a)**：Track 2 精细化时把契约表和验收清单里的"FailureEvent reason_code 命中"
改写为"DeploymentStatus phase=degraded/health=unhealthy + structlog 双层 reason 事件命中"，
如需要真正的 FailureEvent uplink，另开 follow-up plan（类似 Track 5 的 04 号候选）。

### 候选 D（本报告新增，§4 第 3 轮独立发现）— **Track 5 命名与目标错位：tamper-evidence 本不该在 custos 侧实现**

两侧代码注释交叉印证（非推测，均为 file:line 实证）：

- custos 侧 `nt_risk_engine.py:122-127`："SHA-256 content digest over
  `symbol|side|qty|price|ts_seconds` — the same canonical recipe the Rust service uses
  (**correlation handle, not the tamper-evidence anchor; that's the audit chain HMAC**)."
- Rust 侧 `crucible-rust/crates/risk/src/pre_trade_service.rs:82-91`（`fn order_fingerprint`
  的 docstring）："The content digest (SHA-256 over `symbol|side|qty|price|ts_seconds`) is a
  correlation handle — **tamper-evidence for the rejection comes from the audit chain's
  per-tenant HMAC (governance), not from this digest**."
- Rust 侧 `crucible-rust/crates/domain/src/events.rs:203-204`："`order_fingerprint` is an
  opaque HMAC over the order identity (kept off the wire as plaintext)"——注意此处用词
  "opaque HMAC" 与实际实现（无密钥的 SHA-256 摘要）不完全精确，但两侧一致同意
  `order_fingerprint` 只是相关性句柄，不是防篡改锚点。

**结论**：Plan 03 候选 skeleton 把 Track 5 命名为"fingerprint tamper-evidence 恢复"，这个提法
本身与两侧代码库自己的设计文档相矛盾——**真正的防篡改锚点（"audit chain 的 per-tenant HMAC，
governance crate"）是 custos 完全没有可见性、也不应该有可见性的云端机制**（custos 是
non-custodial 独立仓库，KEK/HMAC 密钥类材料本就不该出现在这里）。`order_fingerprint` 无论
custos 侧怎么改进，**都不可能"恢复"防篡改能力**，因为这个函数从设计上就不是防篡改机制的载体。

custos 侧能做、且值得做的是**提升相关性句柄的信息量**——目前生产路径上
`side/quantity/price` 恒为空字符串（候选 B 已实证），指纹实质退化为 `(symbol, ts)`。真实 NT
`OrderDenied` 事件（见候选 B 引用的 `test_dispatcher_forwards_real_order_denied`）**确实携带
`client_order_id`**（一个稳定的、按单唯一的字段），把它纳入哈希输入能显著提升相关性句柄的
唯一性，且改动范围很小（`order_fingerprint()` 签名 + 1-2 处调用点 + 测试更新，预估 <60 LOC）。

**建议 drafter 决策**：Q1 选 A（in-scope），但**必须重新命名 Track 5**（例如"pre-trade reject
correlation handle 精度提升"而非"tamper-evidence 恢复"），并在 docs 更新里显式写明"真正的防
篡改锚点属于云端 audit chain HMAC 机制，custos 不实现也不应该实现，本 Track 只提升相关性字段
质量"——避免这个提法在未来被误读为"custos 已经具备防篡改能力"。如果 drafter/CEO 认为改
`client_order_id` 进哈希公式需要与 `crucible-rust` 侧协调"共享配方"约定的一致性（两侧文档都
写"the same canonical recipe"，虽然是各自独立计算、不需要 bit-for-bit 匹配，但改一侧不改另一侧
会造成文档层面的约定漂移），也可以选 B（独立 follow-up plan，跨仓协调）。**两种选择都成立，
但都必须先解决"tamper-evidence"这个错误提法本身。**

### Track 1 现有测试覆盖复核（非 packet 预设候选，写作过程中发现的重要 scope 修正）

candidate skeleton Task 1 要求"3 test 覆盖三层 invariant"作为全新文件。实际现状：

- **invariant #1**（repr(node) 不含 credential）：`tests/test_nt_trading_node_host.py:240-251
  test_deploy_does_not_retain_credential` **已经覆盖**——用真实 `_nt_binance_venue.py` 构造的
  真实 NT `TradingNodeConfig`（含 `BinanceDataClientConfig(api_key=..., api_secret=...)`）存进
  `host._active_nodes`，断言 `repr(host._active_nodes)` 不含 `"test-key"`/`"test-secret"`。
- **invariant #2**（`node.__dict__` 深度 5 递归 walk）：**确认缺失**，是真正新增的测试。
- **invariant #3**（structlog processor 异常场景不 leak）：
  `tests/test_nt_trading_node_host.py:301-319 test_exception_log_redacts_credential_material`
  **已经覆盖**——直接验证 `_sanitize_exception()` 在异常消息含 `"api_key=REAL_SECRET_KEY"` 时
  被整体 redact。`tests/test_credential_vault_sops.py:56-91
  test_decrypt_returns_credential_dict` 在 vault 层也有同类先例（断言 caplog 不含
  plaintext key）。

**建议**：Track 1 的新文件 `test_credential_lifecycle.py` 应聚焦在**invariant #2（真正缺失的
递归 walk 测试）**，对 invariant #1/#3 采用"在新文件里用 docstring 交叉引用已有测试
（`test_nt_trading_node_host.py:240` / `:301`），不重复造轮子"的方式，而不是从零重写 3 个测试。
这会把 Track 1 的净新增 LOC 从 skeleton 估算的 ~120 行降到 ~50-70 行，且避免了
coding-taste 宪法「测试只测行为，一处信息只写一次」对重复断言的隐性扣分。

### Track 2 现有测试覆盖复核

`tests/test_g6_gate_capability_e2e.py:90-110 _CapabilityLessHost` +
`test_undeclared_capability_host_gets_structured_reject` **已经覆盖**了 skeleton Task 2 描述
的"假第三方 host 类（无 supports_live/supports_venue 方法）"场景，但只在 `_check_g6_gate()`
这一层（gate 单层）验证。`tests/test_g6_gate.py:1-14`（docstring）明确写道："Tests drive
`_apply_spec` directly — the gate's guard layer; **`handle_spec`'s broad except would swallow
the raise**, so this layer is where a rejection is observable."——即当前架构**故意**在
`handle_spec()` 这一层吞掉异常（转成 `phase=degraded` 状态上报，不让异常向上传播中断
reconcile loop，这是 红线 0.3"失联≠停止"式设计的自然延伸，不是 bug）。

**这意味着 skeleton Task 2 措辞"结构化 RuntimeError 传递不被吞"需要精确澄清其含义**：不是指
异常本身向上抛出不被吞（现有设计明确让 `handle_spec` 吞掉它），而是指**吞掉之后的降级信号
（structlog 双层日志 + DeploymentStatus degraded 状态）不能丢失**。建议新测试驱动
`DeploymentReconciler.handle_spec()`（而非只测 `_apply_spec()` 或只测 `_check_g6_gate()`）
用 `_CapabilityLessHost` 风格 test double + live spec，断言：① 不抛出到调用方；②
`_report_status` 被调用且 `phase="degraded"`/`health="unhealthy"`；③ structlog 命中
`g6_gate_live_capability_denied`（gate 自己的日志）+ `deployment_reconcile_failed`
（reconciler 包装层日志）。**不要断言 `reason_code` 字段**（候选 C 已证实其在 wire 上不存在）。

### Track 3 现有测试覆盖复核

`tests/test_main_host_selection.py` 只测 2 种 host 选择（默认 NoopHost / `--use-nt-host` 选
NtTradingNodeHost），`tests/test_g6_gate.py` 测了 paper+NoopHost / live+NoopHost（各 mode 大小写
变体）/ live+真 host 三种组合。附录 A 的 6 组合中，`live × NoopHost` 与 `live × NtTradingNodeHost`
已有等价覆盖（分散在两个文件里），真正缺的是 `sandbox × {NoopHost, NtTradingNodeHost}` 与
`testnet × {NoopHost, NtTradingNodeHost}` 共 4 格。**确认"缺"的范围比 skeleton 描述的"6 组合
全缺"要窄**，Task 3 实际净新增覆盖 4 个新组合 + 2 个已有组合的参数化收敛（如需要统一成一个
parametrize 表）。

### Track 6（GC-safety）范围扩展建议 — 本报告最具体的新发现

```
grep -rn 'ensure_future\|create_task\|run_coroutine_threadsafe' src/arx_runner/*.py
  nats_client.py:315      asyncio.create_task(self._drain_wal(), name="arx-wal-drain")
  nautilus_host.py:216    task = asyncio.create_task(node.run_async())          # 存进 _active_nodes，有强引用
  nautilus_host.py:386    cleanup = asyncio.ensure_future(self._safe_stop_actor(actor))  # 存进 _cleanup_tasks
  nt_risk_engine.py:214/216   fut = asyncio.run_coroutine_threadsafe(...) / ensure_future(...)  # 存进 _pending
  telemetry_actor.py:275/276  self._flush_task = ... / self._heartbeat_task = ...  # 实例属性持有
```

`nats_client.py:315` 的 `connect()` 方法内 `asyncio.create_task(self._drain_wal(),
name="arx-wal-drain")` 是**唯一一处没有被任何强引用容器持有的 fire-and-forget task**——既不在
`_pending`/`_cleanup_tasks` 式 set 里，也没有存成实例属性。按 Python 官方
`asyncio.create_task` 文档的警告（"Save a reference to the result of this function, to avoid
a task disappearing mid-execution"），以及本仓库已经在另外两处（`nt_risk_engine.py`/
`nautilus_host.py`）主动防御的同一类问题，这是**同一失败家族里唯一的漏点**。

现有 `tests/test_nats_wal_resilience.py:73` 的
`test_wal_drain_keeps_unsent_rows_on_publish_failure` 直接调用 `client._drain_wal()`（绕过
`create_task` 包装），**没有测试 `connect()` 内调度这个 task 时的 GC 安全性**。

**建议**：Track 6（Q2）无论选 A（独立文件）还是 B（并入 Track 1），测试范围都应该覆盖
**3 个模块**而非 packet 描述的 2 个：`nt_risk_engine.py`（`_pending`）+ `nautilus_host.py`
（`_cleanup_tasks`）+ **`nats_client.py`（当前无容器，需先补上强引用再测，或至少测试记录本
gap）**。如果 drafter 认为 `nats_client.py` 的修复超出 Plan 03 "深化测试覆盖"的范围（这确实
是一个小的代码改动而非纯测试），建议至少在偏离日志里记录这个发现（`DEV-03-WAL-TASK-GC-GAP`），
交给 Task 4 或后续 plan 处理，而不是完全忽略。

---

## §6 drafter 决策辅助 (Q1/Q2/Q3 数据支持)

- **Q1 Track 5 scope estimate**：
  - 推荐 **选项 A（in-scope）**，但必须先解决命名/目标错位问题（候选 D）——重新定义 Track 5
    目标为"correlation handle 精度提升（加入真实存在的 `client_order_id`）"，明确排除
    "tamper-evidence"这个不成立的提法。
  - LOC 估算：`order_fingerprint()` 签名改动 + `on_order_denied()` 调用点更新 + 2-3 个测试
    更新（`test_fingerprint_is_stable_and_hex` 等）+ docs 更新，约 **50-60 LOC**，明显低于
    skeleton 假设的 150 LOC 阈值，不触发 wire schema 升级（§2 已证实）。
  - 唯一需要 CEO/drafter 额外确认的点：是否需要在 PR/commit 里显式通知
    `crucible-rust` 一侧（同仓不同 plan，跨仓协调）文档措辞也要同步更新"the same canonical
    recipe"这句话，避免两侧文档对"配方"的描述出现分歧（功能上不需要同步改代码，因为两侧是
    独立计算，不是互相解码）。

- **Q2 Track 6 独立 vs 并入**：
  - 推荐 **选项 A（独立 `test_gc_safety_invariant.py`）**，理由：涉及的 3 个模块
    （`nt_risk_engine.py` / `nautilus_host.py` / `nats_client.py`）语义上都是"fire-and-forget
    task 生命周期"，比塞进"credential lifecycle"（Track 1）更内聚。
  - **范围建议扩大到 3 个模块**（新发现：`nats_client.py:315` 的 WAL-drain task 目前
    完全没有强引用保护，是本报告发现的最具体的独立 gap，见 §5 Track 6 段）。
  - 如果 drafter 认为修复 `nats_client.py` 的 gap 超出"纯测试深化"范围（需要新增
    `self._wal_drain_task = asyncio.create_task(...)` 这一行代码改动），至少应该在
    Task 清单里显式列一条 fix（1 行代码 + 1 个测试），而非默认排除。

- **Q3 docs/design 更新范围**：
  - `docs/design/nautilus_host.md` 加 "Credential lifecycle invariants" 新段（Track 1）—
    **确认此段目前不存在**。
  - `docs/design/reconcile.md` 加 "Undeclared capability traceability" 新段（Track 2）—
    **确认此段目前不存在**，且应该明确写清楚"结构化拒绝信号走 DeploymentStatus
    degraded + 双层 structlog，而非独立的 FailureEvent"（候选 C 的澄清需要落到文档里，
    否则未来读者会继续以为 FailureEvent 已经实现）。
  - `docs/design/nautilus_host.md` 是否加 "Host mode × trading_mode matrix" 新段（Track 3）—
    **确认目前不存在**，建议加。
  - **新增建议**（本报告发现）：`docs/design/nautilus_host.md:79-80` 的"未来演化路线·短期"
    段落已经过时（仍称 Plan 00b telemetry 桥"未落地"），Track 1/2/3 的文档改动顺手订正这一句，
    成本很低（删一句话），收益是消除一处明显的文档-代码不一致。

---

## §7 verdict

**PASS_WITH_FINDINGS**

本次 Foundation Scan 深化确认了 packet §1 现状清单（14 src 文件 / 28 test 文件 / 5 处
"缺"标注）基本准确，四维方法论均有产出，且发现了 4 项 packet 未预见但对 drafter 精细化有实质
影响的新发现：

1. **候选 C（新）**：`FailureEvent` 概念在 `src/arx_runner/` 零实现，Track 2 的验收断言
   "FailureEvent.reason_code 命中"目前不可能成立，drafter 必须先做描述范围降级决策。
2. **候选 D（新）**：Track 5 的"tamper-evidence 恢复"提法与两侧代码库（custos +
   crucible-rust）自己的设计文档相矛盾，需要重新命名和定义目标才能继续。
3. **Track 1 现有覆盖复核（新）**：3 层 invariant 中有 2 层已被现有测试实质覆盖，真正缺的
   只有 1 层（递归 dict walk），LOC 估算应下修。
4. **Track 6 范围扩展（新）**：`nats_client.py:315` 的 WAL-drain task 是与 `_pending`/
   `_cleanup_tasks` 同一失败家族但完全没有防护的独立 gap，建议纳入 Q2 决策范围。

以上均不构成阻断（BLOCK）——它们是**需要 drafter 在精细化阶段主动消化的 scope 修正**，不影响
Plan 03 的整体可行性。文档漂移（Drift #1/#5）建议顺手修正但同样不阻断。`test_wire_shapes.py`
的已知路径失效（`DEV-01-WIRE-FIXTURES`，`Makefile:34-38` 已排除出 baseline）经核实是**既有
已分诊问题**，与 Plan 03 无关，仅供 drafter 参考"Track 5 新测试不要依赖外部仓库 fixture 路径，
应遵循 `test_nats_wire_contract.py` 的自包含模式"。
