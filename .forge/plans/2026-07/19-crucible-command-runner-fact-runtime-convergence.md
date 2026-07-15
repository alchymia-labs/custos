# 19 - Converge Crucible command, RunnerFact, and local execution runtime

> **Status**: ⏳ In progress
> **Created**: 2026-07-14
> **Revised**: 2026-07-15 after Plan 19 T3 intake-policy PREPARED checkpoint
> **Project**: Custos
> **Source**: Audit of pre-plan migration `324da6e`, PS Plan 53, and v1.team review
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Immediately executable**: Task 4 after the Task 3 intake-policy PREPARED checkpoint; no runtime readiness is implied
> **19d-T8a gate**: 19c STOP only; it produces the immutable RunnerFact candidate before Crucible Plan 90 Phase A
> **Runtime RC gates**: Crucible Plan 89 migration 0116 signed command producer and `CR89-0116-GENERATION-STORAGE`; Crucible Plan 90 Phase-A schema/golden compatibility receipt; Crucible Plan 99 runner-safety-policy-authority; Custos Plan 18 staged candidate and exact final required by the selected RC/final-candidate BOM
> **Close-out gates**: Crucible Plan 90 Phase-B real runtime round-trip receipt; PS Plan 56 exact final-candidate acceptance
> **Original plan-first**: `3ce4048`; this live-plan revision supersedes its erroneous decisions

## 上下文 (Context)

`324da6e` 已把 Custos 从 standalone deployment authority 迁移为：

- Crucible 发布 signed runner deployment command；
- Custos 消费 command、执行本地策略并发布 signed RunnerFacts；
- Crucible 验签、投影和结算；
- ARX 只负责授权，不恢复 telemetry gateway。

方向正确，但 original Plan 19 存在五个架构错误：

1. 计划新建第二套 `runner_fact_outbox`，与现有 SQLite `RunnerFactOutbox`
   的 seq、dedup、签名和 PubAck 删除语义冲突。
2. journal 以 `spec_id` 为中心，而 runtime address 必须是
   `deployment_instance_id`。
3. strict command/schema 被当作 Custos 单仓任务，但 Crucible 尚未生产完整字段。
4. runner-wide cap 没有独立 authority，多实例下当前行为是最后一个 spec 覆盖。
5. 计划缩减现有 engine protocol、删除已经描述 typed RunnerFact 的
   `telemetry_actor.md`，并缺少 ACK deadline、poison message、restart budget
   和 generation fingerprint。

本修订直接替换错误设计。不得通过兼容 fallback、第二个 database/outbox 或
Custos-only fixture 修改绕过 producer 缺口。

## 当前验证基线

- `make check-authority`: PASS。
- focused command/reconcile/lifecycle tests: 14 passed。
- 当前测试未覆盖 single-transaction journal、same-generation conflict、
  restart recovery、多实例 cap、ready lifecycle 或 DLQ。
- Crucible clean HEAD `abbd3fc` 的 golden fixture 仍缺完整 versioned
  runner-runtime/code-provenance producer contract。

Task 1 可立即执行。Task 2 以后受 cross-repo hard gates 约束。

### 19a/T1 characterization checkpoint (2026-07-15)

`R-C19-T1-CHARACTERIZATION` is **READY_CHARACTERIZATION** at
`docs/authority/receipts/custos-plan-19-task-1-characterization-receipt.json`.
The test-only implementation is commit
`c567f1dc7ee974acda31f042a48e3fb2833241ed`; the exact full-repository
verification head is `f3adde2870a53a4bb52cc2a260d2c7c1c852eee2`.

- Direct RunnerFact outbox and EngineProtocol characterization: 7 passed.
- Full `make verify`: 522 passed, 4 skipped, 1 xfailed; formatter, Ruff, assets,
  extraction, typing, authority and mypy gates passed.
- The checkpoint changes no production behavior. It freezes current per-stream sequence,
  event deduplication, signed pending-batch reopen durability, failure retention, outbound
  PubAck deletion, and the complete existing EngineProtocol method/async boundary.
- This receipt is not a T2 producer-contract receipt, does not activate desired/applied runtime
  state, and is not a runtime RC, image, promotion or production-readiness receipt.

The receipt's historical `T1 characterization` label is a characterization sub-checkpoint of
19a. It does not silently replace the numbered Task 1 verification-floor command set below;
unrecorded commands remain open until separately evidenced.

### 19b/T3 intake-policy checkpoint (2026-07-15)

Task 3 is **PREPARED_FOR_T4_DURABILITY**, not complete runtime wiring. The
production intake module freezes the Plan 19 command fingerprint separately
from the CR89 producer fingerprint, verifies exact subject/event bytes and all
T2 schema/evidence/acceptance bindings before any disposition, and exposes only
typed inbound ACK/NAK/TERM/in-progress plus a T4 durability port.

- same-generation/same-exact-bytes is idempotent; different exact bytes is a
  terminal conflict;
- poison commands TERM only after a typed untrusted-rejection receipt;
- transient failures use bounded NAK/backoff; exhausted retries TERM only after
  a typed terminal receipt;
- long operations renew only the inbound command ACK lease;
- JetStream subscription now pins ack wait, max deliveries and backoff;
- no SQLite table, second database/outbox, daemon/reconciler/engine apply or
  outbound PubAck path is added by T3.

The durability port is intentionally unimplemented in production until Task 4
adapts it to the sole existing RunnerFact SQLite deep module and its atomic
RunnerFact lifecycle transaction. Therefore this checkpoint does not claim
durable outcome, runtime, handoff or production readiness.

## 目标 (Goal)

把 current-main 收敛为可恢复、可监督、fail-closed 的 Custos runtime：

- exact signed Crucible command consumption；
- success/conflict/stale/retry-exhausted/invalid-command outcome 在 ACK/TERM 前 durable；
- applied state 与 lifecycle fact 的单事务提交；
- 唯一 RunnerFact outbox、stream sequence 和 PubAck path；
- 所有 deployment-scoped RunnerFact 受 signed generation fencing；
- additive engine readiness/terminal lifecycle；
- 真实 Nautilus portfolio/equity；
- signed canonical policy 的本地 mandatory enforcement；
- 完整 RunnerFact/capability/projector receipts；
- sandbox、testnet、live 的 mode/capability isolation。

Custos 不接管 StrategyRelease、DeploymentSpec authority、组合风险、审批、资本、
canonical reconciliation 或结算。

## Authority Boundary

| Surface | Canonical owner | Custos responsibility |
|---|---|---|
| DeploymentSpec/Instance and command payload | Crucible | verify and execute exact signed command |
| StrategyRelease/artifact selection/effective config | Crucible | execute exact bound artifact/config |
| Runtime address | `deployment_instance_id` | key all desired/applied/runtime state |
| Local credentials and venue interaction | Custos | keep secrets local and execute |
| RunnerFact sequence/signing/outbox/generation fence | Custos | existing SQLite deep module；generation 进入 signed header，但不切分 stream |
| RunnerFact verification/projector/settlement | Crucible | provide compatibility receipt |
| Runner-level cap policy | Crucible Plan 99 signed versioned policy | enforce locally without loosening；不得内嵌到某个 DeploymentSpec |
| Advisory strategy sizing | Toolkit/strategy | never substitutes mandatory safety |
| Portfolio risk, approvals, capital, settlement | Crucible | out of scope |

## Single Durable State Deep Module

Custos 已有 `RunnerFactOutbox`，负责：

- per-stream sequence allocation；
- event deduplication；
- `facts[].seq` injection；
- signed batch construction；
- durable pending batches；
- JetStream PubAck 后删除。

Plan 19 禁止创建第二套 outbox。desired/applied journal tables 必须纳入同一
SQLite deep module、connection 和 transaction boundary。实现可以内部重构文件，
但 public surface 保持单一：

```python
class RunnerStateStore(Protocol):
    def record_desired_command(
        self,
        command: VerifiedRunnerCommand,
        command_fingerprint: str,
        verification_receipt: CommandVerificationReceipt,
    ) -> DesiredRecord: ...

    def commit_verified_command_outcome_and_enqueue_fact(
        self,
        *,
        deployment_instance_id: UUID,
        deployment_spec_id: UUID,
        deployment_spec_digest: str,
        generation: int,
        command_fingerprint: str,
        outcome: Literal["applied", "conflict", "stale", "retry_exhausted"],
        engine_handle: str | None,
        outcome_fact: RunnerFact,
    ) -> CommandOutcomeCommitResult: ...

    def commit_untrusted_command_rejection(
        self,
        *,
        delivery_id: str,
        exact_subject: str,
        raw_envelope_digest: str,
        reason_code: Literal["invalid_signature", "invalid_schema", "unsupported_version"],
    ) -> UntrustedCommandRejectionResult: ...
```

`commit_applied_and_enqueue_lifecycle()` 保留为
`commit_verified_command_outcome_and_enqueue_fact(outcome="applied")` 的 typed wrapper。
verified command 的四种 terminal/success outcome 必须在一个 SQLite transaction 中：

1. 校验 desired instance/generation/fingerprint；
2. 写 applied state；
3. 写 immutable command outcome；
4. 使用现有 event dedup；
5. 分配现有 stream sequence；
6. 注入 `facts[].seq`；
7. 构造并签名 batch；
8. 写入现有 `runner_fact_outbox`；
9. commit。

禁止先提交 applied 再调用另一个 outbox transaction。
invalid signature/schema/version 无法建立可信 instance authority，因此不得伪造 lifecycle
fact；`commit_untrusted_command_rejection()` 必须先把 runner-scoped security/DLQ receipt
durably 写入同一 SQLite deep module，再允许 consumer `term()`。如果任何 durable commit
失败，只能 NAK，不得 ACK/TERM。

最小 tables：

```text
desired_deployments
  deployment_instance_id PRIMARY KEY
  tenant_id
  trading_mode
  runner_id
  deployment_spec_id
  deployment_spec_digest
  generation
  command_event_id
  exact_subject
  command_fingerprint
  verified_event_bytes_digest
  signer_key_id
  signature_profile
  verification_receipt
  canonical_command
  desired_status
  updated_at_ns

applied_deployments
  deployment_instance_id PRIMARY KEY
  deployment_spec_id
  deployment_spec_digest
  generation
  command_fingerprint
  engine_handle
  observed_status
  restart_count
  quarantine_reason
  updated_at_ns

command_outcomes
  outcome_id PRIMARY KEY
  delivery_id
  deployment_instance_id NULLABLE
  generation NULLABLE
  command_fingerprint NULLABLE
  outcome
  reason_code
  durable_disposition
  recorded_at_ns

runner_cap_policy
  policy_id PRIMARY KEY
  policy_revision
  policy_digest
  tenant_scope
  trading_mode
  max_notional
  effective_at_ns
  expires_at_ns
  signer_key_id
  signed_policy

order_reservation
  deployment_instance_id
  client_order_id
  policy_id
  reserved_notional
  filled_exposure
  state
  updated_at_ns
  PRIMARY KEY (deployment_instance_id, client_order_id)

runner_exposure_checkpoint
  policy_id PRIMARY KEY
  open_exposure
  reconstructed_at_ns
  source_digest

existing tables, retained as the only fact path
  runner_fact_stream
  runner_fact_seen_event
  runner_fact_outbox
```

`deployment_spec_id` 和 digest 是 provenance，不是 journal primary key。
SQLite 不得保存 credential material。

Lifecycle event ID 必须由 instance/spec/generation/state/fingerprint 的稳定输入
确定生成，不能在 crash replay 时随机生成新 UUID。

`RunnerFactAuthority` 与 signed batch header 必须增加 `generation`。generation 不得进入
`stream_key`、NATS subject 或 sequence allocator key；同一 instance/spec stream 在 generation
变化时继续单调递增。fill/order/position/equity/log/lifecycle 等所有 deployment-scoped fact
都必须带当前 generation，Crucible projector 必须拒绝或隔离旧 generation fact。

## Command Identity, ACK, and Poison Handling

Command fingerprint 冻结为：

```text
SHA256(
  b"CRUCIBLE-RUNNER-COMMAND-FINGERPRINT-V1\0" ||
  u32be(len(exact_subject_utf8)) || exact_subject_utf8 ||
  u64be(len(verified_exact_event_bytes)) || verified_exact_event_bytes
)
```

`verified_exact_event_bytes` 是通过 Crucible signature 验证的原始 event bytes，不是重编码
JSON。fingerprint 明确排除外层 signature bytes，避免同一 event 合法重签/换钥产生 false
conflict；signer key id、signature profile 和 verification receipt 必须单独持久化。subject
属于 fingerprint，因为它属于签名 authority binding。

| Delivery | Behavior |
|---|---|
| same instance + generation + same fingerprint | idempotent replay |
| same instance + generation + different fingerprint | terminal conflict, quarantine, no apply |
| newer generation | apply after authority/mode/capability checks |
| older generation | terminal stale command |
| invalid signature/schema/version | terminal/DLQ poison message |
| retryable local dependency failure | bounded NAK/backoff |
| long deploy waiting for ready | periodic JetStream `in_progress()` |

必须区分：

- **Inbound command ACK**：Custos 对 Crucible command delivery 的
  ACK/NAK/term/in-progress。
- **Outbound fact PubAck**：JetStream 确认 signed RunnerFact batch 后，
  existing outbox 才删除 pending batch。

两者不能共享状态字段或被称为同一个 ACK。

Consumer 必须显式配置 `ack_wait`、`max_deliver`、backoff 和 DLQ/quarantine
策略。poison message 不得无限 NAK；等待 engine ready 不得静默超过 ack deadline。

Disposition 时序固定如下：

| Outcome | Durable boundary | Delivery disposition |
|---|---|---|
| applied | applied state + signed lifecycle batch 同事务 commit | ACK |
| verified conflict/stale | immutable outcome + signed terminal fact 同事务 commit | TERM/ACK per producer contract |
| retryable local failure | desired record 已 durable；未写 terminal outcome | bounded NAK/backoff |
| retry budget exhausted | terminal outcome + signed terminal fact 同事务 commit | TERM |
| invalid signature/schema/version | untrusted rejection + pending security/DLQ receipt commit | TERM |
| durable commit failure | none | NAK；禁止 ACK/TERM |

Outbound fact publisher 只有收到 PubAck 才删除 existing outbox row。Inbound disposition 与
outbound PubAck 不能复用字段、watermark 或状态枚举。

## Crucible Producer-First Contract

Custos 不得自行修改 parser/golden 后宣称 strict command 完成。前置 producer slice
必须由 **Crucible Plan 89** 独立 plan-first 实现。Custos `19d-T8a` 必须先独立发布
RunnerFact schema/golden/capability candidate；**Crucible Plan 90** 随后在 Custos runtime RC
前提供 Phase-A compatibility receipt，并在该 RC/final-candidate 之后提供 Phase-B real
runtime round-trip receipt：

1. 定义 public、versioned `runner_runtime` 和 `code_provenance` schema。
2. CreateDeploymentSpec/control producer 从 typed model 生成 command。
3. 分离 artifact digest、manifest digest 和 optional source hash。
4. 生成新的 canonical golden fixture。
5. 在 clean landed commit 上记录 repo、SHA、schema digest 和 fixture digest。
6. Custos byte-identical 消费 fixture。
7. Custos `19d-T8a` 发布 immutable RunnerFact schema/golden/capability candidate；此步不依赖 Plan 90。
8. Crucible Plan 90 Phase A 证明该 candidate 的双仓 schema/digest/projector compatibility。
   Phase A must also consume `CR89-0116-GENERATION-STORAGE`; fixture-only compatibility cannot replace the durable generation-storage receipt.
9. Crucible Plan 90 Phase B 消费 exact Custos runtime RC/final-candidate，证明真实
   command → execution → RunnerFact projector round trip。

在 producer receipt 到达前：

- Task 1 可执行；
- journal/engine characterization tests 可起草；
- 不得冻结 strict parser、发布 RC 或声称 runtime contract complete。

## Additive Engine Lifecycle

现有 engine protocol 的以下能力必须保留：

- deploy；
- reconfigure；
- stop；
- supports live/venue；
- open notional；
- connectivity state；
- flatten；
- positions/open orders/status snapshots。

Plan 19 只做 additive extension：

```python
@dataclass(frozen=True)
class EngineReadyReceipt:
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: str
    generation: int
    ready_at_ns: int


@dataclass(frozen=True)
class EngineTerminalEvent:
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    generation: int
    reason_code: str
    retryable: bool
```

Readiness 至少证明：

- node task alive；
- required data connectivity ready；
- required execution connectivity ready；
- portfolio/account initialization complete；
- reconciliation initialization complete；
- strategy registered and accepting runtime lifecycle；
- mode-specific mandatory capabilities active。

`create_task()` 不等于 ready。长期 task 的异常必须传播到 supervisor。

每个 instance 必须有 bounded restart budget、exponential backoff 和 quarantine。
超过预算后发布 deterministic terminal lifecycle fact，不得无限 crash loop。

## Nautilus Portfolio and Local Safety

Portfolio snapshot 必须使用 NT 1.230.0 的真实 API：

- `portfolio.equity(venue)`；
- 每个 position 的可信 mark price；
- `position.unrealized_pnl(mark_price)`；
- 缺失数据时标记 unreliable，breaker fail closed；
- EngineStatus、breaker、position/equity facts 使用同一个 snapshot provider。

禁止用 open notional + unrealized PnL 冒充 equity。

### Risk taxonomy

| Layer | Meaning |
|---|---|
| Toolkit advisory sizing | strategy-local recommendation, non-authoritative |
| Custos mandatory local safety | exact enforcement of signed policy |
| Crucible canonical risk policy | portfolio/risk authority, approvals and limits |

### Runner-level cap

Final live architecture 必须消费 **Crucible Plan 99 runner-safety-policy-authority** 生产的
独立、签名、版本化 runner-level cap policy。不得从“最后收到的 deployment command”推断
全 runner authority，也不得把 runner policy 塞回某个 DeploymentSpec 的 `risk_config`。

在 producer policy 未完成前，唯一允许的临时行为是：

- sandbox/testnet only；
- effective cap 取所有 active desired instances 中最严格值；
- capability 明确为 provisional/false for live；
- live fail closed。

Reservation contract：

- key: `(deployment_instance_id, client_order_id)`；
- 原子 reserve；
- reject/cancel 释放全部 reservation；
- replace 原子调整差额；
- partial fill 将 reserved 转为 filled exposure；
- fill/close 更新 exposure；
- duplicate event 幂等；
- policy revision、reservation 和 exposure checkpoint 与 desired/applied state 使用同一
  SQLite deep module；
- restart 从 durable reservation/checkpoint 恢复，并用可信 engine/venue state 对账重建；
- flatten、close 和 reduce-only exit 永远不得被 cap 阻止。

必须在不可绕过的 engine/order-intent boundary 证明覆盖所有策略提交路径。
禁止 monkey patch、SuperTrend-only hook 或 docs-only enforcement。

## RunnerFact Compatibility

现有 signed RunnerFact stream 是唯一 runtime output。不得恢复 unsigned
telemetry/status uplink。

新 lifecycle/log/fact type 必须同时具备：

- capability manifest revision；
- Custos schema/version registration；
- Crucible verifier/projector compatibility；
- onboarding/fixture receipt；
- deterministic event identity；
- redaction tests。

在 Crucible 定义 canonical risk-decision fact 前，local deny/reject 使用已有
`RunnerRuntimeLogFact.v1` 的 sanitized structured event，不新增 Custos-owned
canonical business fact。

`docs/design/telemetry_actor.md` 已描述 typed RunnerFact。应原子 rename 为
`docs/design/runner_fact.md`，同步更新 CLAUDE、authority manifest/checker 和 active
references；清晰标记的 historical plan references 可以保留。

## Mode and Capability Isolation

必须增加 negative tests：

- sandbox credential/policy 不能启动 testnet/live；
- source-path 不能启动 live；
- missing signed cap policy 不能启动 live；
- unsupported engine capability 不能被 spec 参数打开；
- reduce-only/flatten 即使 cap exhausted 仍可执行；
- mode mismatch、tenant mismatch、instance mismatch terminal reject；
- secret/raw credential/full order payload 不进入 journal、facts 或 logs。

## Architecture

```text
Crucible typed producer
  │ signed canonical command + exact artifact/policy bindings
  ▼
JetStream command consumer
  │ verify + fingerprint + term/NAK/in_progress policy
  ▼
single RunnerStateStore / SQLite transaction boundary
  ├── desired_deployments
  ├── applied_deployments
  ├── existing stream sequence + event dedup
  └── existing signed RunnerFact outbox
  │
  ▼
DeploymentReconciler
  ├── additive EngineReadyReceipt
  ├── EngineTerminalEvent
  ├── restart budget/backoff/quarantine
  └── signed policy enforcement
  │
  ▼
NtTradingNodeHost
  ├── exact artifact verification
  ├── reliable portfolio snapshot
  ├── native per-order safety
  └── runner-level cap at engine boundary
  │
  ▼
signed RunnerFacts ──PubAck──> existing outbox deletion
```

## File Inventory

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `.forge/plans/2026-07/19-crucible-command-runner-fact-runtime-convergence.md` | 修改 | 本 live-plan 修订 |
| `.forge/README.md` | 修改 | 修订 hard gates 和说明 |
| `src/custos/contracts/deployment.py` | 修改 | producer-backed strict contract |
| `src/custos/core/runner_fact.py` | 修改/内部重构 | 唯一 state/outbox transaction boundary |
| `src/custos/core/deployment_reconciler.py` | 修改 | fingerprint/durable reconcile/restart |
| `src/custos/core/nats_client.py` | 修改 | ACK deadline, bounded retry, term/DLQ |
| `src/custos/core/engine_protocol.py` | additive 修改 | ready/terminal without protocol shrink |
| `src/custos/core/local_cap.py` | 修改 | signed policy/reservation semantics |
| `src/custos/core/runner_deployment_lifecycle_fact.py` | 修改 | deterministic IDs |
| `src/custos/core/runtime_log_fact.py` | 修改 | sanitized local safety events |
| `src/custos/cli/_daemon.py` | 修改 | structured supervision |
| `src/custos/engines/nautilus/host.py` | 修改 | readiness/equity/risk |
| `src/custos/engines/nautilus/risk.py` | 修改 | native per-order config |
| `src/custos/engines/nautilus/portfolio_snapshot.py` | 新增 | shared reliable snapshot |
| `src/custos/engines/nautilus/strategy_loader.py` | 修改 | exact artifact provenance |
| `tests/test_runner_fact_outbox.py` | 新增 | direct characterization + transaction tests |
| `tests/test_deployment_contract.py` | 修改 | producer schema/fingerprint tests |
| `tests/test_deployment_reconciler.py` | 修改 | restart/conflict/quarantine tests |
| `tests/test_runner_deployment_command_golden.py` | 修改 | exact Crucible receipt |
| `tests/test_runner_fact_parity.py` | 新增 | capability/projector matrix |
| `tests/integration/test_crucible_runner_runtime.py` | 新增 | current real acceptance |
| `docs/design/telemetry_actor.md` | rename | `docs/design/runner_fact.md` |
| `docs/authority/**`, `CLAUDE.md` | 修改 | producer/projector receipts and active references |
| `docs/ops/05-deployment.md` | 修改 | v0.4 mode/policy runbook |
| `Makefile` | 修改 | current verification targets |
| `pyproject.toml`, release workflow | 修改 | RC/final version and gates |

明确禁止新增第二个 `runner_fact_outbox` table 或独立 journal database。

## Approved production roadmap and normative stop gates

This section amends Tasks 2-10 and is part of the DoD for existing slices 19a-d.
It does not create Plan 20, a second journal or a second outbox. Desired state,
applied state, command outcomes, lifecycle enqueue, policy/reservations and the
existing RunnerFact outbox remain one SQLite deep module and one transactional
authority boundary.

### Receipt DAG

```text
R-C18-T5C-PRESIGN -> R-C18-TOOLKIT-RC -> R-PS54-ARTIFACT-BOM
  -> R-CR88-STRATEGY-RELEASE -> R-C18-T5D-A-EVIDENCE-CONSUMER
  -> R-CR89-DEPLOYMENT-COMMAND -> R-C18-T5D-B-C19-T2-COMMAND-CONSUMER
  -> C19-T3-COMMAND-INGRESS -> C19-T4-DURABLE-RECONCILE -> C19-T5-ENGINE-ADAPTER
  -> Crucible Plan 99 migration 0117 -> R-CR99-RUNNER-POLICY -> C19-T7-RUNNER-SAFETY
  -> R-C19-RUNNER-FACT-CANDIDATE -> CR89-0116-GENERATION-STORAGE -> R-CR90A-FACT-COMPAT
  -> R-C19-RUNTIME-RC -> R-CR90B-RUNTIME-ROUNDTRIP
  -> R-PS56-EXACT-IMAGE -> R-C19-SAME-DIGEST-PROMOTION
```

Crucible Plan 99 migration 0117 is the first Plan 99 runtime slice after the
signed-command receipt. It must be applied and verified in each physical mode
database before policy publication or Custos live-policy consumption. Its receipt
ID is `R-CR99-M0117`; the completed signed policy receipt is
`R-CR99-RUNNER-POLICY`.

### Slice integration

| Slice | Additional mandatory scope | Deliverable | Production stop gate |
|---|---|---|---|
| 19a command and provenance | Consume `R-CR89-DEPLOYMENT-COMMAND`; install a runner-local signed trust bundle for command keys with monotonic version, overlap rotation, revocation, expiry and rollback protection; acquire artifacts into a content-addressed cache; verify complete BOM/signature/attestation before making bytes eligible | Command/fingerprint vectors, durable rejection receipt, trust-bundle receipt, verified cache object receipt | Unknown/revoked/expired key, trust-version rollback, digest/BOM mismatch, non-content-addressed path or ACK before durable outcome stops apply and live execution |
| 19b durable reconcile and lifecycle | Extend the existing SQLite deep module for desired/applied/outcome and artifact activation metadata; atomically activate verified cache content, persist prior generation for rollback, support offline restart and bounded GC; freeze risk-increasing execution and enter quarantine if lifecycle/RunnerFact enqueue is not durable; harden SQLite migration/version, WAL/checkpoint, permissions, disk-full, corruption, backup/restore and power-loss recovery | `commit_applied_and_enqueue_lifecycle()` receipt, atomic activation/rollback receipt, offline restart/GC receipt, crash/power-loss matrix and restored-state receipt | No second journal; disk-full/corrupt/schema mismatch/WAL failure means no ACK and no new apply; enqueue failure freezes and quarantines rather than logging and continuing |
| 19c portfolio and local safety | Require `R-CR99-M0117` and `R-CR99-RUNNER-POLICY`; verify policy-key trust with the same rotation/revocation/rollback discipline; enforce runner-level cap on every risk-increasing order path; keep live fail closed when policy is absent, expired, revoked or mode-mismatched | Real marked portfolio receipt, signed-policy receipt, order-boundary allow/deny matrix, restart persistence receipt | DeploymentSpec mutable risk config cannot define runner aggregate cap; missing migration/policy or unenforced cap blocks live |
| 19d facts, runtime RC and promotion | Exercise enqueue-freeze/quarantine and SQLite recovery with real RunnerFacts; pin Docker base image by digest and install dependencies from the committed lock without live transitive resolution; emit metrics for command lag/outcome, desired/applied drift, SQLite/WAL/disk, cache/activation, outbox age, fact PubAck, policy expiry and restart/quarantine; define SLOs, alerts and operator runbook; promote the exact tested and signed digest | RunnerFact candidate, runtime RC with complete BOM/SBOM/signatures/OCI provenance, metrics/SLO/alert evidence, recovery runbook, Phase B/PS56 receipts and same-digest promotion receipt | Unpinned base/dependency, missing observability/runbook, skipped recovery, changed digest, rebuild or stable-tag promotion before CR90B/PS56 stops release and close-out |

### Artifact cache and activation invariants

1. Cache keys are cryptographic content digests, never strategy names, mutable
   tags, filesystem paths or DeploymentSpec IDs.
2. Download/stage occurs outside the active slot. Signature, attestation, complete
   BOM and every member digest are verified before atomic activation.
3. Activation and applied-generation metadata commit through the existing SQLite
   authority; a crash exposes either the old complete generation or the new
   complete generation, never a mixed directory.
4. Rollback selects a previously verified immutable generation and records a new
   lifecycle fact. It never rewrites history or bypasses generation fencing.
5. Offline restart may load only an already verified, non-revoked cache object
   bound to durable desired/applied state and a valid local trust/policy snapshot.
6. GC is bounded and cannot remove the active generation, rollback generation,
   pending desired generation or any object referenced by an un-PubAcked fact.

### SQLite and fact-durability invariants

1. Migration version and schema fingerprint are checked before subscription
   readiness. Unknown or partial migration is fail closed.
2. WAL/checkpoint policy, fsync behavior, file/directory permissions and free-disk
   thresholds are explicit and observable.
3. Disk-full, I/O error, corrupt page, failed checkpoint or failed lifecycle/fact
   enqueue prevents command ACK and new risk-increasing execution.
4. Backup/restore proves desired/applied/outcome, activation, policy/reservation,
   stream sequence, dedup and outbox consistency. Power-loss tests cover every
   transaction boundary.
5. The RunnerFact bridge may not catch, log and continue after a durability
   failure. It freezes risk-increasing work, records readiness failure when
   possible and moves the affected runner to quarantine for operator recovery.
6. `deployment_instance_id` is the sole runtime stream identity. The durable
   stream key and NATS subject identity are tenant + mode + runner + instance;
   `deployment_spec_id`, `deployment_spec_digest` and `generation` are signed
   fencing/provenance fields only and MUST NOT allocate a new stream or reset
   sequence.
7. The old spec/digest-keyed stream migration freezes command intake, drains every
   old un-PubAcked batch, computes an explicit per-instance sequence continuation,
   then activates the instance-keyed stream. It MUST NOT rewrite, delete or
   silently orphan an old signed pending batch.

### Observability and release acceptance

- Metrics and alerts cover oldest command age, outcome counts, desired/applied
  generation drift, restart budget, quarantine age, policy expiry, SQLite/WAL/disk,
  artifact cache/activation, RunnerFact outbox depth/age and PubAck latency.
- SLOs state thresholds and paging conditions; the runbook identifies safe retry,
  restore, rollback, re-enrollment and quarantine-release procedures.
- Docker base image and every runtime dependency are locked. BuildKit provenance,
  SBOM and signatures bind the complete runtime BOM.
- Candidate, CR90B, PS56 and stable promotion all use the same image digest. Any
  rebuild or digest change creates a new candidate and invalidates old receipts.
- Speculum is not a runtime, release or close-out gate. The PS legacy
  `build-image.sh` to Crucible Python image lane remains independent compatibility
  only and cannot satisfy a Custos schema, runtime or acceptance receipt.

## Canonical Slices and Stop Gates

Plan 19 是 `multi_session_scope: true`，只允许按以下四个 slice 顺序推进。每个 STOP gate
未满足时不得进入下一 slice，不得用本地 fixture 或 provisional capability 宣称完成。

| Slice | Tasks | START gate | STOP gate |
|---|---|---|---|
| **19a command/provenance** | T1-T3 | T1 可立即执行；T2/T3 等 Crucible Plan 89 clean landed producer | exact producer SHA/schema/golden；冻结 fingerprint；所有 command outcomes commit-before-ACK/TERM |
| **19b durable reconcile/lifecycle** | T4-T5 | 19a STOP | 单一 SQLite deep module；success/terminal outcome 原子；RunnerFact signed generation fence；additive engine readiness/restart/quarantine |
| **19c portfolio/local safety** | T6-T7 | 19b STOP；Plan 99 policy schema 可用 | reliable portfolio；signed policy + durable reservation/exposure recovery；live non-bypass proof |
| **19d facts/release acceptance** | T8-T10 | 19c STOP；T8a 无 Plan 90 依赖 | T8a candidate → Plan 90 Phase A → runtime RC/final-candidate → Plan 90 Phase B → PS Plan 56 exact-candidate acceptance → unchanged promotion/close-out |

无环 release graph：

```text
Custos Plan 18 T5c StrategyArtifactRefV2
  -> PS Plan 54 BOM/statement/detached attestation
  -> Crucible Plan 88 ArtifactEvidence/acceptance
  -> Custos Plan 18 T5d-A producer-owned evidence consumption
  -> Crucible Plan 89 signed command producer
  -> Custos Plan 18 T5d-B == Custos Plan 19 T2 command consumption
  -> Custos Plan 19 T3 fingerprint/ACK
  -> Custos Plan 19 T4 single durable store + instance-only stream migration
  -> Custos Plan 19 T5 engine readiness/supervision
  -> Crucible Plan 99 runner-safety-policy-authority
  -> Custos Plan 19 T7 signed local safety
  -> Custos 19d-T8a immutable RunnerFact schema/golden/capability candidate
  -> Crucible Plan 90 Phase-A compatibility receipt
  -> Custos Plan 18 staged candidate + exact final selected in the release BOM
  -> Custos Plan 19 runtime RC / exact final-candidate image
  -> Crucible Plan 90 Phase-B real runtime round-trip receipt
  -> PS Plan 56 exact final-candidate image acceptance
  -> promote the same Custos bytes unchanged
  -> Custos Plan 19 close-out
```

Handoff 不得倒置：Plan 90 Phase A 不是 19d START gate，而只是 runtime RC gate；
Plan 90 Phase B 不是 runtime RC prerequisite，而是该 exact RC/final-candidate 的 consumer；
PS Plan 56 依赖 exact final-candidate digest，不依赖 Plan 19 `Completed` 状态。任何失败都
递增 candidate coordinate 并从 Phase A 起重跑受影响 receipts，禁止验收后重建或 repoint。

## Tasks

### Task 0: Repair the live plan

1. 用本修订替换 second-outbox、spec-keyed journal、Custos-only schema、
   last-command cap 和 protocol shrink。
2. 更新 Custos index。
3. 同步修订 PS Plan 53 的 T4、dependency graph 和 consumer requirements。
4. 只 stage 计划和索引，提交：

```bash
git commit -m "docs(custos): repair plan 19 runtime convergence design"
```

### Task 1: Restore verification floor

这是当前唯一无外部契约依赖、可立即执行的 implementation task。

1. 固定当前 formatter/Makefile failure。
2. 只做机械 formatting，不夹带语义修改。
3. 把 `verify-runtime-existing` 改到 current integration target。
4. 验证：

```bash
make verify
make verify-nt
make -n verify-runtime-existing
```

提交：

```bash
git commit -m "style(custos): restore runtime verification floor"
```

### Task 2: Land and consume the Crucible Plan 89 producer contract

Hard gate：Custos Plan 18 T5d-A STOP；Crucible Plan 89 独立 plan-first、typed
producer、new golden、clean landed SHA；Crucible Plan 90 预先登记 schema/golden
compatibility receipt owner。

1. 仅在 Crucible 生成 versioned runner-runtime/code-provenance schema 和 golden；
   Custos 不生成、不重定义、不发布 command schema。
2. 记录 producer SHA、schema digest、fixture digest。
3. Command 必须绑定完整 PS `StrategyReleaseBomV1` object、
   `StrategyArtifactRefV2`、detached `ArtifactAttestationRefV1`、Crucible
   完整 `ArtifactEvidenceV1`、`ArtifactAcceptanceReceiptV1` /
   `artifact_evidence_digest`、effective config digest 与完整
   instance/spec/generation provenance；禁止
   `release_bom_members` 第二真相。
4. Custos 先写 byte-identical、unknown version、missing field、V1 fallback、
   BOM-as-array、acceptance mismatch 和 digest mismatch tests。
5. 删除 legacy `parameters`/`code_hash`/command-provided `strategy_path`
   fallback；显式 sandbox `DevelopmentSourceRefV1` 不是 production fallback。
6. 双仓 compatibility gate 必须从同一 fixture/schema 计算。
7. 本 Task 与 Plan 18 T5d-B 是同一 implementation slice、consumer model 和
   receipt；禁止各自实现一套 DTO 或验收链。

> **Execution status (2026-07-15)**: Task 2 STOP is
> `READY_COMMAND_CONSUMER_CONTRACT_ONLY` and is exactly the Plan 18 T5d-B
> receipt. Corrected CR89 contract commit `51d23eba8aaefb30e936fc9fae1eac0e791164aa`
> and publication commit `06b2cbc0bafc0eda2b92fc2bc3f36ba1626abc3d`
> are pinned byte-for-byte. Old `fe7be511...`, `56743f09...`, and `a20f7116...`
> producer slices are `NON_CURRENT`. The sole Custos consumer retains exact event
> bytes and computes the CR producer fingerprint, but does not alter subscription,
> ACK, daemon, reconciler, SQLite or runtime composition. Those remain Task 3+.

Custos 提交：

```bash
git commit -m "feat(custos): consume Crucible runner command contract"
```

### Task 3: Implement command fingerprint and bounded ACK policy

1. 按冻结的 domain+subject+exact-event-bytes 算法写 cross-language vectors。
2. 写 same-generation/different-payload terminal conflict tests。
3. 写 invalid signature/schema poison durable-rejection-before-term tests。
4. 写 stale/retry-exhausted durable terminal outcome tests。
5. 写 long readiness `in_progress()` 和 bounded retry tests。
6. 显式配置 ack wait、max deliveries、backoff 和 quarantine。
7. inbound ACK 状态不得与 outbound PubAck 混用。

> **Execution status (2026-07-15)**: `PREPARED_FOR_T4_DURABILITY`.
> Fingerprint/authentication/intake/disposition policy and the focused
> crash/restart/redelivery matrix are implemented. The production durability
> adapter remains Task 4; T3 does not ACK a newly prepared command and cannot
> claim durable/runtime readiness before that adapter exists.

提交：

```bash
git commit -m "feat(custos): enforce command identity and delivery policy"
```

### Task 4: Extend the existing RunnerFact SQLite deep module

先写 direct `RunnerFactOutbox` characterization tests，锁定 seq、dedup、sign、
pending 和 PubAck deletion。

然后：

1. 在同一 store/connection 增加 desired/applied tables。
2. primary key 使用 `deployment_instance_id`。
3. 增加 command outcome、runner policy、reservation 和 exposure checkpoint tables。
4. 实现 verified/untrusted durable outcome APIs；`commit_applied_and_enqueue_lifecycle()`
   作为 success typed wrapper。
5. 将 `RunnerFactAuthority` stream identity 收敛为 tenant + mode + runner +
   `deployment_instance_id`。`deployment_spec_id`、`deployment_spec_digest`、
   `generation` 只进入 signed fencing/provenance header；任一 generation/spec
   变化都不得重置 stream sequence。
6. 实现旧 spec/digest-keyed stream 的显式迁移：冻结 intake，先 drain 全部旧
   pending PubAck，计算 per-instance sequence continuation，再启用新 stream；
   禁止重写、删除或遗失旧 signed batch。
7. lifecycle event ID deterministic。
8. 覆盖 desired 后 crash、ready 后 commit 前 crash、commit 后 publish 前 crash、
   duplicate delivery 和 restart replay。
9. 验证没有第二个 outbox/database；artifact activation、desired/applied、
   command outcome、policy/reservation 和 fact outbox 全部共享这一 SQLite
   authority 与 migration ledger。

提交：

```bash
git commit -m "feat(custos): persist reconcile state in runner fact store"
```

### Task 5: Add engine readiness, terminal lifecycle, and supervision

1. characterization tests 锁定全部现有 engine protocol methods。
2. additive 增加 ready/terminal APIs。
3. readiness 覆盖 task/connectivity/portfolio/reconciliation/strategy/capabilities。
4. 实现 timeout、restart budget、backoff 和 quarantine。
5. daemon 任一长期 task 意外退出时取消 siblings 并返回非零。
6. shutdown 顺序：停止 intake → stop deployments → flush fact outbox →
   close NATS/store。

提交：

```bash
git commit -m "feat(custos): supervise engine readiness and termination"
```

### Task 6: Use reliable Nautilus portfolio semantics

1. 回归测试复现 `decimal.ConversionSyntax`。
2. 实现单一 `NautilusPortfolioSnapshotProvider`。
3. 使用 `portfolio.equity(venue)` 和
   `position.unrealized_pnl(mark_price)`。
4. 缺可信 mark/equity 时标记 unreliable，breaker fail closed。
5. status、breaker 和 RunnerFacts 共用同一 snapshot。

提交：

```bash
git commit -m "fix(custos): use reliable Nautilus portfolio equity"
```

### Task 7: Enforce signed local safety policy

#### 7A Native per-order safety

1. 从 signed Crucible policy 构建 NT public risk config。
2. 黑盒证明超过单笔上限的 order intent 在 engine boundary 被拒。
3. missing/invalid live policy fail closed。

#### 7B Runner-level aggregate cap

Hard gate：Crucible Plan 99 runner-safety-policy-authority 的 clean landed signed policy receipt。

1. 覆盖多 active instances 和 policy revision。
2. 独立验证并 durable 保存 policy；禁止从 DeploymentSpec `risk_config` 派生正式 runner cap。
3. 实现 instance+client-order durable reservation contract。
4. 覆盖 reject/cancel/replace/partial-fill/fill/close/restart/reconciliation rebuild。
5. 证明 strategy direct submit 不能绕过。
6. 证明 flatten/close/reduce-only 不被阻止。
7. policy 未落地时仅 sandbox/testnet strictest-cap fallback；live capability=false。

如 NT 1.230.0 无公开不可绕过 seam，Plan 19 保持未完成并另起 upstream adapter
实现；不得 monkey patch。

提交：

```bash
git commit -m "feat(custos): enforce signed local notional policy"
```

### Task 8: Complete RunnerFact and documentation compatibility

#### 19d-T8a: Produce the immutable RunnerFact contract candidate

此 subtask 的 START gate 只有 19c STOP，**不得等待 Crucible Plan 90 Phase A**。

1. 建立 runtime-event → existing fact/log parity matrix。
2. 冻结带 signed generation fence 的 RunnerFact schema、golden 和 capability
   manifest revision。schema 必须声明 `deployment_instance_id` 是唯一 runtime
   stream identity，spec id/digest/generation 只作 signed fencing/provenance。
3. 生成 immutable candidate coordinate、clean producer commit、schema/golden/capability digests
   和 verification command receipt。
4. local deny/reject 使用 sanitized `RunnerRuntimeLogFact.v1`。
5. 原子 rename `telemetry_actor.md` → `runner_fact.md`。
6. 同步 CLAUDE、authority manifest/checker 和 active docs。
7. 不恢复 unsigned telemetry/status。
8. 证明新 generation/spec 不会重置 sequence，并提供旧 spec/digest-keyed stream
   drain + sequence-continuation migration fixture；Crucible Plan 90 projector 必须
   对同一规则出 compatibility receipt。

`19d-T8a` STOP 是 exact candidate receipt 已可被外部仓库消费；它不宣称 Crucible
projector compatible，也不允许发布 runtime RC。

#### 19d-T8b: Consume Crucible Plan 90 Phase-A compatibility receipt

1. 把 `19d-T8a` exact candidate bytes/digests 交给 Crucible Plan 90 Phase A。
2. 取得 verifier/inbox/projector compatibility receipt，必须引用同一 candidate coordinate、
   Custos clean commit 和全部 schema/golden/capability digests。
3. candidate 变化使 Phase-A receipt 失效并回到 `19d-T8a`。
4. `19d-T8b` STOP 只放行 Task 9 runtime RC/final-candidate，不代表 real runtime acceptance。

提交：

```bash
git commit -m "feat(custos): complete RunnerFact runtime compatibility"
```

### Task 9: Publish the immutable runtime RC / final-candidate

前置：

- Crucible Plan 89 producer contract receipt；
- Crucible Plan 99 signed cap policy receipt；
- Plan 18 exact staged candidate artifact；
- selected Plan 18 exact final bytes recorded in the release BOM；
- Crucible Plan 90 schema/golden compatibility receipt；
- all mode/capability negative tests。

1. 发布 immutable `0.4.0rcN` wheel/image，并把它声明为本轮 exact final-candidate；
   此时 Plan 19 仍未 Completed。
2. 把 exact candidate coordinate、image digest、SBOM/signature 和 release BOM 交给
   Crucible Plan 90 Phase B。
3. Phase B 运行真实 Crucible command → Custos execute → RunnerFact projector acceptance。
4. 任一 bytes/BOM 变化递增 RC，重新执行 Plan 90 Phase A 和 Phase B；不得覆盖旧 candidate。

### Task 10: Accept, promote unchanged, and close out

Hard gate：Crucible Plan 90 Phase-B real runtime round-trip receipt + PS Plan 56 对 Task 9
exact final-candidate image 的 acceptance receipt。PS Plan 56 不能依赖 Plan 19 Completed；
Plan 19 必须保持 open 直到该 receipt 到达。

1. 验证 Plan 90 Phase B 与 PS Plan 56 都引用 Task 9 的同一 coordinate/image digest/BOM。
2. PS Plan 56 锁 exact final-candidate digest，运行 Docker、mode/capability、durable-state
   recovery 和 operator acceptance。
3. 不重建、不覆盖、不 repoint；把 Task 9 已验收的同一 bytes 原样 promote 为 final。
4. promotion 后重新验证坐标和 digest 未变，再更新 docs、changelog、plan/index 和 receipts。
5. 标记 Completed 并提交：

```bash
git commit -m "docs(custos): mark plan 19 as completed"
```

## Verification

- [ ] verification floor 全绿
- [ ] command schema 来自 clean landed Crucible producer
- [ ] schema/golden/digest 双仓 compatibility gate
- [ ] same generation + different fingerprint terminal reject
- [ ] fingerprint 与 domain+exact subject+verified exact event bytes cross-language vector 一致
- [ ] signer/profile/verification receipt durable；signature bytes 不进入 fingerprint
- [ ] poison message term/DLQ，不无限 NAK
- [ ] success/conflict/stale/retry-exhausted/invalid command 均 commit-before-ACK/TERM
- [ ] long deploy 使用 `in_progress()`
- [ ] desired/applied primary key 为 `deployment_instance_id`
- [ ] 只有一个 SQLite state/outbox deep module
- [ ] applied state 与 lifecycle batch 单事务提交
- [ ] existing seq/dedup/sign/PubAck semantics 保持
- [ ] stream identity 只有 tenant + mode + runner + `deployment_instance_id`
- [ ] spec id/digest/generation 只作 signed fencing/provenance，generation 不重置 sequence
- [ ] 旧 spec/digest-keyed streams 全部 drain 后显式 sequence continuation，无 pending batch 丢失或重写
- [ ] lifecycle event ID deterministic
- [ ] signed RunnerFact header 带 generation，stream key/sequence 不按 generation 重置
- [ ] Crucible projector 拒绝或隔离 old-generation facts
- [ ] engine protocol 只 additive、不 shrink
- [ ] readiness 覆盖 task/connectivity/portfolio/reconciliation/strategy
- [ ] restart budget/backoff/quarantine
- [ ] equity/unrealized 使用真实 NT API
- [ ] runner cap 来自 Crucible Plan 99 signed versioned policy，且不在 DeploymentSpec 内
- [ ] policy/reservation/exposure checkpoint durable 并可 restart reconcile
- [ ] multi-instance reservation/release/recovery semantics 完整
- [ ] flatten/close/reduce-only 不被 cap 阻止
- [ ] unsupported live capability fail closed
- [ ] RunnerFact capability revision + Crucible projector receipt
- [ ] `telemetry_actor.md` 原子 rename，不删除 typed RunnerFact authority
- [ ] sandbox/testnet/live negative matrix
- [ ] journal/facts/logs 无 credential 或 secret
- [ ] `19d-T8a` candidate 在 Plan 90 Phase A 前独立生成并可消费
- [ ] Plan 90 Phase A receipt 只 gate runtime RC，不 gate 19d/T8a START
- [ ] runtime RC/exact final-candidate 后已有 Plan 90 Phase-B real round-trip receipt
- [ ] PS Plan 56 消费 exact final-candidate，不依赖 Plan 19 Completed
- [ ] Phase-B + PS 56 receipts 到达后原 bytes unchanged promotion，再 close-out

## Progress

| Task | Status | Completed | Notes |
|---|---|---|---|
| T0 Live-plan repair | [~] | — | supersedes erroneous decisions in `3ce4048` |
| T1 Verification floor | [~] | 2026-07-15 | characterization sub-checkpoint READY at `c567f1d`; full `make verify` green at `f3adde2`; remaining verification-floor commands require separate evidence |
| T2 Crucible producer/consumer | [x] | 2026-07-15 | Same STOP as Plan 18 T5d-B: corrected CR89 A2/B2 bytes, sole consumer parser, full evidence/acceptance bindings and frozen producer fingerprint; contract-only, runtime false |
| T3 Fingerprint/ACK | [~] | 2026-07-15 | PREPARED_FOR_T4_DURABILITY: frozen algorithm + bounded inbound policy; real durable outcomes remain T4 |
| T4 Single durable store | [ ] | — | outcomes, generation fence, cap/reservation tables |
| T5 Engine lifecycle | [ ] | — | additive protocol |
| T6 Portfolio/equity | [ ] | — | NT 1.230.0 regression |
| T7 Signed local safety | [ ] | — | live blocked on Crucible Plan 99 |
| T8a RunnerFact candidate | [ ] | — | 19c STOP 后独立生产；不得等待 Plan 90 |
| T8b Plan 90 Phase A | [ ] | — | exact T8a candidate compatibility；gate Task 9 only |
| T9 Runtime RC/final-candidate | [ ] | — | Plan 18 BOM + Plan 89/90A/99 receipts；交给 Plan 90B |
| T10 Accept/promote/close-out | [ ] | — | Plan 90B + PS 56 exact-candidate receipts；unchanged promotion |

## Deviations and Improvements

| 类型 | 位置 | 描述 | 状态 |
|---|---|---|---|
| PRE-PLAN | `324da6e` | authority migration landed before Plan 19 | Recorded |
| PLAN-REPAIR | Durable store | 撤回第二套 outbox；journal 合入 existing RunnerFact SQLite deep module | Accepted 2026-07-14 |
| IDENTITY | Journal | primary key 改为 `deployment_instance_id`；spec/digest 只作 provenance | Accepted 2026-07-14 |
| CONTRACT | Command | Custos-only schema freeze 改为 Crucible producer-first | Accepted 2026-07-14 |
| SAFETY | Runner cap | last-command overwrite 改为 signed runner-level policy | Accepted 2026-07-14 |
| LIFECYCLE | Engine | 保留全部 protocol，ready/terminal additive | Accepted 2026-07-14 |
| DOCUMENTATION | RunnerFact | `telemetry_actor.md` 改为 atomic rename，不直接删除 | Accepted 2026-07-14 |
| DURABILITY | Command outcomes | success/terminal/untrusted paths 全部改为 commit-before-ACK/TERM | Accepted 2026-07-14 |
| FINGERPRINT | Command | 冻结 domain+subject+exact-event-bytes，排除 signature bytes | Accepted 2026-07-14 |
| TASK-BOUNDARY | T3/T4 | T3 只落 intake policy + durability port；SQLite/outcome/fact transaction 保留给 T4，状态诚实降级 PREPARED | Accepted 2026-07-15 |
| FENCING | RunnerFact | generation 进入 signed header，但不改变 stream key/sequence | Accepted 2026-07-14 |
| POLICY | Runner cap | owner 锁定 Crucible Plan 99；policy/reservation/exposure durable | Accepted 2026-07-14 |
| DAG | Cross-repo release | T8a 先产 candidate；Plan 90A 只 gate RC；Plan 90B + PS56 gate unchanged promotion/close-out | Accepted 2026-07-14 |
| HISTORY | `3ce4048` | 保留为 original plan-first，不再代表有效 runtime design approval | Recorded |

## v1.team Scope

| v1.team capability | Plan 19 coverage |
|---|---|
| A2/A3 deploy/reconcile | core scope |
| B3 health/status | ready/terminal/lifecycle facts |
| C1-C3 reconciliation | Custos emits facts; Crucible remains canonical |
| D1 local pre-trade safety | exact signed policy enforcement |
| D2-D4 portfolio risk | out of scope; Crucible-owned |
| E1/E2 buffering/retry/seq | existing RunnerFactOutbox, extended transactionally |
| H1/H2 mode/credential isolation | negative acceptance matrix |
| I1/I2 runner trust boundary | signed command and runtime acceptance |
| A4, G1/G2/G4, J1-J6 | out of scope; Crucible/ARX-owned |

## Quantitative Summary

- Durable stores/outboxes: exactly 1
- Runtime primary key: `deployment_instance_id`
- Canonical slices: 19a command/provenance → 19b durable lifecycle → 19c safety → 19d-T8a candidate → Plan 90A → runtime RC/final-candidate → Plan 90B → PS56 → close-out
- External producer gates: Crucible Plan 89 command schema + Plan 90 receipts + Plan 99 runner policy
- Engine change: additive lifecycle only
- Implementation tasks: 10 after live-plan repair
- Release acceptance: Crucible producer/projector + PS Docker consumer
