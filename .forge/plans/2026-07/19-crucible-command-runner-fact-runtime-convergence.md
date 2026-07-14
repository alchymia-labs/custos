# 19 - Converge Crucible command, RunnerFact, and local execution runtime

> **Status**: ⏳ In progress
> **Created**: 2026-07-14
> **Project**: Custos
> **Source**: Audit of pre-plan migration commit `324da6e` and PS Plan 53
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Custos `324da6e`; clean landed Crucible producer receipt
> **Soft depends on**: Custos Plan 18 `0.1.0rc1`; PS Plan 56 acceptance

## 上下文 (Context)

`324da6e` 已完成大规模迁移：

- Custos 不再拥有 standalone deployment authority。
- Crucible 发布 runner deployment command。
- Custos 消费 command、执行本地策略并发布 signed RunnerFacts。
- Crucible 验签、投影、结算。
- ARX 只负责授权，不恢复 telemetry gateway。

迁移方向正确，但 current-main 尚存在以下缺口：

1. `make verify` 当前不绿，12 个文件未通过 format。
2. `verify-runtime-existing` 指向已删除测试。
3. `strategy_artifact_digest` 被错误映射为 source `code_hash`。
4. parser 仍接受 legacy `parameters` fallback。
5. reconcile state 只存在内存中，ACK 后进程重启会丢失 desired/applied state。
6. host 在 NT node 真正 ready 前返回成功。
7. top-level `gather(..., return_exceptions=True)` 吞掉长期任务失败。
8. `Position.unrealized_pnl(price)` 被当属性读取，引发 `decimal.ConversionSyntax`。
9. breaker equity 使用 open notional + unrealized 的代理值，不是真实账户 equity。
10. `RunnerNotionalCap` 和 NT risk config 没有生产调用者。
11. OrderDenied/Rejected 没有完整 signed operational fact 覆盖。
12. authority gate 未扫描所有 active docs；旧 telemetry/status 叙述仍存。
13. package 仍标记为 0.3.0，但 command/control-plane 已发生 breaking change。

当前验证基线：

- `make check-authority`：PASS。
- `uv run ruff check src/ tests/ scripts/`：PASS。
- `uv run pytest tests/ -q`：382 passed、4 skipped、1 xfailed、1 warning。
- `make verify`：FAIL，`ruff format --check` 报 12 个文件需要格式化。
- `make -n verify-runtime-existing`：仍引用
  `tests/integration/test_standalone_runtime.py`。
- Custos/Crucible runner-command golden fixture 当前 byte-identical，SHA-256：
  `12b2133822cc5b2608b326263e41cb7b8b34ea6cb5e16ab4973f1be6e41bb465`。

权威参考：

- Crucible runner command producer 和 golden fixture
- Custos `docs/authority/ecosystem-authority.json`
- Custos `docs/authority/runner-deployment-command-golden-v1.json`
- Custos `docs/design/runtime_log_fact.md`
- `.claude/rules/mandatory-rules.md`
- `.claude/rules/verification.md`
- `.claude/rules/deviation-protocol.md`

## 目标 (Goal)

把 `324da6e` 收敛成可恢复、可监督、fail-closed、具有真实本地风控和签名 RunnerFact
观测面的 Custos 0.4 runtime，并用真实 Crucible command acceptance 证明它。

## 架构 (Architecture)

```text
Crucible producer
  │ signed/canonical runner command
  ▼
NATS JetStream consumer
  │ strict schema + exact producer receipt
  ▼
DeploymentStateJournal (SQLite)
  ├── desired command
  ├── applied generation
  ├── pending lifecycle fact
  └── signed fact outbox
  │
  ▼
DeploymentReconciler
  │
  ├── EngineReadyReceipt
  ├── EngineTerminalEvent
  └── bounded restart/reconcile policy
  │
  ▼
NtTradingNodeHost
  ├── exact artifact/source provenance
  ├── NautilusPortfolioSnapshotProvider
  ├── native per-order risk config
  └── runner-wide aggregate cap
  │
  ▼
signed RunnerFacts ──> Crucible verify/project/settle
```

SQLite 只保存 command、状态与 signed fact outbox，不保存 API key/secret。

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| Migration history | `324da6e` 标记 PRE-PLAN | 不伪造 plan-first 历史 |
| Producer authority | exact clean Crucible SHA | dirty checkout 不能作为 receipt |
| Mode naming | outer `mode` / canonical `trading_mode` | 当前 golden 已一致 |
| Runtime schema | `runner_runtime.schema_version == 1` strict | 删除 legacy fallback |
| Artifact provenance | 三类 digest 独立 | 防止 wheel/source 混淆 |
| Desired state | SQLite journal | ACK 后可恢复 |
| ACK ordering | durable desired + ready + durable lifecycle outbox 后 ACK | 避免确认后丢状态 |
| Deploy success | 返回 `EngineReadyReceipt` | create_task 不等于 ready |
| Terminal failure | typed `EngineTerminalEvent` | reconciler 必须知道 node 已死 |
| Supervision | structured concurrency | 不吞 top-level task 异常 |
| Equity | `portfolio.equity(venue)` | 使用 NT 真实账户语义 |
| Unrealized PnL | `position.unrealized_pnl(mark_price)` | NT 1.230.0 API |
| Per-order limit | native `LiveRiskEngineConfig` | 使用公开 NT seam |
| Aggregate cap | engine-boundary interception only | strategy hook 可被绕过 |
| Unsupported cap | capability=false，live fail closed | 不虚假宣称安全能力 |
| Risk telemetry | signed `RunnerRuntimeLogFact.v1` | 不在 Custos 发明 canonical fact |
| Old telemetry | 不恢复 | RunnerFacts 是唯一输出面 |
| Release | `0.4.0rc1` → `0.4.0` | breaking control-plane migration |

## 本地 provenance 模型

```python
class StrategyExecutionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_artifact_digest: Sha256Hex
    strategy_manifest_digest: Sha256Hex
    source_code_hash: Sha256Hex | None = None
    strategy_path: Path | None = None
```

规则：

```text
artifact mode:
  require artifact digest + manifest digest
  verify installed artifact and entry point
  source_code_hash optional

source-path mode:
  require artifact digest + manifest digest
  require strategy_path + source_code_hash
  verify directory with dir-hash-v1

never:
  artifact digest == source directory hash
```

## Runtime lifecycle interface

```python
@dataclass(frozen=True)
class EngineReadyReceipt:
    deployment_instance_id: str
    spec_id: str
    generation: int
    ready_at_ns: int


@dataclass(frozen=True)
class EngineTerminalEvent:
    deployment_instance_id: str
    spec_id: str
    generation: int
    reason: str
    retryable: bool


class ExecutionEngineProtocol(Protocol):
    async def deploy(
        self,
        spec: dict[str, object],
        credential: CredentialMaterial,
    ) -> EngineReadyReceipt: ...

    async def stop(self, deployment_instance_id: str) -> None: ...

    async def terminal_events(self) -> AsyncIterator[EngineTerminalEvent]: ...
```

## 承载决策 (Capability Hosting Decision)

| 能力 | plan mode? | hook? | CLAUDE.md? | 现有 skill flag? | 新 skill? | 决策 |
|---|---:|---:|---:|---:|---:|---|
| Durable reconciliation | 否 | 否 | 否 | 否 | 否 | SQLite deep module |
| NT portfolio snapshot | 否 | 否 | 否 | 否 | 否 | Nautilus adapter |
| Runner-wide risk cap | 否 | 否 | 否 | 否 | 否 | Engine-boundary runtime seam |
| RunnerFact parity | 否 | 否 | 否 | 否 | 否 | Existing signed fact producer |
| Authority drift | 否 | CI/static gate | 否 | 否 | 否 | 扩展现有 authority checker |

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `.forge/plans/2026-07/19-crucible-command-runner-fact-runtime-convergence.md` | 新增 | 本计划 |
| `.forge/README.md` | 修改 | 登记 Plan 19 |
| `src/custos/contracts/deployment.py` | 修改 | Strict runtime/provenance |
| `src/custos/core/deployment_reconciler.py` | 修改 | Durable reconcile |
| `src/custos/core/deployment_state_journal.py` | 新增 | SQLite journal/outbox |
| `src/custos/core/nats_client.py` | 修改 | ACK ordering |
| `src/custos/core/engine_protocol.py` | 修改 | Ready/terminal contracts |
| `src/custos/core/local_cap.py` | 修改 | Production runner cap |
| `src/custos/core/runtime_log_fact.py` | 修改 | Risk operational facts |
| `src/custos/core/runner_deployment_lifecycle_fact.py` | 修改 | Deterministic IDs |
| `src/custos/cli/_daemon.py` | 修改 | Structured supervision |
| `src/custos/engines/nautilus/host.py` | 修改 | Readiness/equity/risk |
| `src/custos/engines/nautilus/risk.py` | 修改 | Native NT risk config |
| `src/custos/engines/nautilus/portfolio_snapshot.py` | 新增 | Shared account snapshot |
| `src/custos/engines/nautilus/strategy_loader.py` | 修改 | Provenance separation |
| `tests/test_deployment_contract.py` | 修改 | Strict command tests |
| `tests/test_deployment_reconciler.py` | 修改 | Journal/restart tests |
| `tests/test_runner_deployment_command_golden.py` | 修改 | Producer receipt |
| `tests/test_runner_fact_parity.py` | 新增 | Fact coverage matrix |
| `tests/integration/test_crucible_runner_runtime.py` | 新增 | Current real acceptance |
| `tests/integration/test_standalone_runtime.py` | 保持删除 | 不恢复旧 authority |
| `docs/authority/**` | 修改 | Receipt/golden/gates |
| `docs/design/00-overview.md` | 修改 | Current ownership |
| `docs/design/01-architecture.md` | 修改 | 删除旧 telemetry/status |
| `docs/design/telemetry_actor.md` | 删除 | Git history 已保留 |
| `docs/ops/05-deployment.md` | 修改 | v0.4 runbook |
| `Makefile` | 修改 | Current verification targets |
| `pyproject.toml` | 修改 | 0.4 prerelease/final |
| `.github/workflows/release.yml` | 修改 | PEP 440/Docker tag mapping |

## 实现任务 (Tasks)

### Task 0: Plan-first 与 PRE-PLAN receipt

**Files**: 本计划、`.forge/README.md`。

1. 写入本计划并更新索引。
2. 在偏离日志登记 `324da6e` 已先行实施。
3. 不把该提交计为 Plan 19 实现 commit。
4. 提交：

```bash
git commit -m "plan(custos): 19 — converge Crucible runner runtime"
```

### Task 1: 恢复 verification floor

**Files**: 12 个 format drift 文件、`Makefile`、current integration target。

1. 固定当前失败：

```bash
make verify
# expected before fix: 12 files would be reformatted
```

2. 对列出的 12 个文件运行项目 formatter；不得夹带语义修改。
3. 更新 `verify-runtime-existing` 指向新的 current integration test，删除已不存在的
   standalone runtime 引用。
4. 验证：

```bash
make verify
make verify-nt
make -n verify-runtime-existing
```

5. 提交：

```bash
git commit -m "style(custos): restore runtime verification floor"
```

### Task 2: 锁定 producer receipt 和 strict command schema

**Files**: deployment contract、golden fixture/receipt、parser tests。

Hard gate：

- Crucible producer 必须 clean、landed。
- 记录 repo、exact SHA、fixture SHA。
- 当前 dirty `53adbca` 只能作审计证据。

先写失败测试：

```python
def test_missing_runner_runtime_is_rejected() -> None:
    command = golden_command()
    del command["payload"]["deployment_spec"]["parameters"]["runner_runtime"]
    with pytest.raises(ValueError, match="runner_runtime"):
        DeploymentSpec.from_runner_command(command)


def test_unknown_runner_runtime_field_is_rejected() -> None:
    command = golden_command()
    command["payload"]["deployment_spec"]["parameters"]["runner_runtime"]["legacy"] = True
    with pytest.raises(ValueError):
        DeploymentSpec.from_runner_command(command)
```

实现约束：

- 要求 `runner_runtime.schema_version == 1`。
- 删除 `parameters.get("runner_runtime", parameters)`。
- 删除 `strategy_config` 回退到整个 parameters。
- 冻结 outer `mode`、canonical `trading_mode`。
- Golden fixture byte-for-byte match producer。

验证并提交：

```bash
uv run pytest tests/test_deployment_contract.py \
  tests/test_runner_deployment_command_golden.py -v
git commit -m "feat(custos): enforce Crucible runner command v1"
```

### Task 3: 拆分 artifact、manifest 与 source digest

**Files**: deployment contract、G6、CLI、host、loader、相关 tests。

1. 写失败测试，证明 artifact digest 不传给 directory verifier；source mode 缺 hash
   时拒绝；artifact mode 不要求 source path；v0.4 拒绝 legacy `code_hash`。
2. 一次原子迁移 `DeploymentSpec.code_hash` 到三个明确字段。
3. 更新 loader、G6、CLI、golden tests；source-path producer 提供真实
   `source_code_hash`，不留歧义 fallback。
4. 验证：

```bash
uv run pytest tests/test_deployment_contract.py \
  tests/test_strategy_loader.py \
  tests/test_g6_gate_capability_e2e.py \
  tests/test_nt_trading_node_host_integration.py -v
```

5. 提交：

```bash
git commit -m "refactor(custos): separate strategy provenance digests"
```

### Task 4: 实现 durable DeploymentStateJournal

**Files**: journal、reconciler、NATS ACK path、journal/restart tests。

SQLite schema 至少包含：

```text
desired_deployments
  spec_id
  generation
  command_id
  canonical_payload
  desired_status
  applied_instance_id
  observed_status
  updated_at_ns

runner_fact_outbox
  fact_id
  spec_id
  generation
  fact_kind
  signed_payload
  delivery_status
  created_at_ns
```

约束：

- 不存 credential material。
- desired command 在 apply 前提交。
- lifecycle fact ID 由 command/spec/generation/status 确定生成。
- ready 后在同一事务记录 applied state 和 pending fact。
- pending fact durable enqueue 后才 ACK。
- restart 恢复 non-terminal desired state 和 fact outbox。
- duplicate delivery 幂等。

失败测试模拟 journal 后崩溃、ready 后 publish 前崩溃、ACK 前重复 delivery、restart
只产生一个 lifecycle fact ID。

提交：

```bash
git commit -m "feat(custos): persist deployment reconcile state"
```

### Task 5: 建立真实 engine readiness 与 terminal events

**Files**: engine protocol、NT host、reconciler、tests。

失败测试：

- node task 尚未 ready 时 `deploy()` 不返回。
- node task 在 ready 前退出时 deploy 失败。
- ready 后 terminal exception 产生 `EngineTerminalEvent`。
- terminal event 清除 active instance 并触发 reconcile。
- stop 与自然退出幂等。

实现 bounded readiness timeout 和 typed terminal event stream；host callback 不再只记录
日志，reconciler 不在 receipt 前写 applied/reported。

提交：

```bash
git commit -m "feat(custos): supervise engine readiness and termination"
```

### Task 6: 改造 daemon structured concurrency

**Files**: `src/custos/cli/_daemon.py`、supervision tests。

替换：

```python
await asyncio.gather(*tasks, return_exceptions=True)
```

为结构化监督：

- 任一长期任务意外退出即取消 siblings。
- 正常 stop event 有独立路径。
- terminal exception 传播到 CLI exit code。
- shutdown 顺序：停止 command intake → stop deployments → flush outbox → close NATS/journal。
- 不留下 orphan tasks。

验证并提交：

```bash
uv run pytest tests/test_cli_start.py tests/test_daemon_supervision.py -v
git commit -m "refactor(custos): use structured daemon supervision"
```

### Task 7: 统一 Nautilus portfolio/equity snapshot

**Files**: portfolio provider、host、breaker/status/fact adapters、tests。

新增：

```python
@dataclass(frozen=True)
class NautilusPortfolioSnapshot:
    equity: Decimal | None
    unrealized_pnl: Decimal | None
    positions: tuple[PositionSnapshot, ...]
    reliable: bool
    failure_reason: str | None
```

Provider 必须：

- 使用 `portfolio.equity(venue)`。
- 获取每个 position 的 mark price。
- 调用 `position.unrealized_pnl(mark_price)`。
- 缺 mark/equity 时保留不可靠状态，breaker fail closed。
- EngineStatus、breaker、position snapshot、RunnerFact 共用同一 provider。
- 不再用 open notional + unrealized 冒充 equity。

回归测试直接覆盖 NT 1.230.0 method shape，消除
`[<class 'decimal.ConversionSyntax'>]`。

提交：

```bash
git commit -m "fix(custos): use reliable Nautilus portfolio equity"
```

### Task 8: 接入 native per-order risk config

**Files**: NT risk config/builder/host、black-box tests。

1. 用 characterization test 验证 NT 1.230.0 公开 API 支持
   `LiveRiskEngineConfig.max_notional_per_order`。
2. 将 signed deployment rule 转换为 Decimal 并接入 node/kernel。
3. 缺失或非法值 fail closed；`build_nt_risk_engine_config` 必须出现生产调用者。
4. 黑盒提交超过单笔上限订单，证明由 NT risk engine 拒绝。
5. 提交：

```bash
git commit -m "feat(custos): enforce native per-order notional limits"
```

### Task 9: 实现 runner-wide aggregate cap

**Files**: local cap、受支持 NT engine seam、capability、concurrency tests。

先建立 seam contract gate：

- 必须拦截所有 NT order intents，包括策略直接调用 NT submit API。
- 两笔单独合法、合计超限的订单必须拒绝第二笔。
- cancel/fill/close 正确释放 reserved notional。
- concurrency 下 reservation 原子。
- config refresh 不清空已占用额度。
- `RunnerNotionalCap.allows()` 必须有生产调用者。

仅允许 NT 1.230.0 公开支持的 custom risk-engine/order-intent seam。禁止 monkey patch
kernel、只改 SuperTrend base、可绕过的 context hook 或 docs-only enforcement。

若无可证明的公开 seam：

- capability 保持 false。
- testnet/live deployment fail closed。
- 记录 HIGH-RISK deviation。
- Plan 19 不得 close-out，另起 NT upstream/adapter plan。

有不可绕过证明后提交：

```bash
git commit -m "feat(custos): enforce runner-wide aggregate notional cap"
```

### Task 10: 完成 RunnerFact parity

**Files**: RunnerFact bridge/runtime logs、parity matrix/tests、legacy residue。

| Runtime event | 新输出 |
|---|---|
| Fill | RunnerFact Fill/ExecutionFill |
| Fee | Fee fact |
| Position closed | PositionClosed |
| Equity/position snapshot | EquitySnapshot/PositionSnapshot |
| Venue ledger | Manifest/Chunk |
| Heartbeat | Heartbeat |
| Deployment lifecycle | `RunnerDeploymentLifecycleFact.v1` |
| Runtime warning/error | `RunnerRuntimeLogFact.v1` |
| OrderDenied/Rejected | sanitized signed RuntimeLog fact |
| Local cap rejection | sanitized signed RuntimeLog fact |

约束：

- 不新增 Custos-owned canonical `RunnerRiskDecisionFact`。
- 不恢复 unsigned `telemetry_actor`、status publisher 或 ARX uplink。
- Runtime logs 不含 secret、raw credential 或完整 order payload。
- 删除或迁移 `tests/test_g6_gate.py` 中假的 `publish_deployment_status` residue。
- 未来 canonical risk fact 由 Crucible 独立计划定义。

提交：

```bash
git commit -m "feat(custos): complete signed RunnerFact observability"
```

### Task 11: 扩大 authority drift gate 并删除冲突文档

**Files**: authority manifest/checker/tests、active design/ops docs。

1. 从 `git ls-files` 获取 tracked source/config/docs；active scopes 默认全部检查。
2. 历史快照必须位于明确 history 路径并显式 allowlist。
3. 新增 sentinel，证明遗漏 active file 会失败。
4. 更新 `docs/design/00-overview.md`、`01-architecture.md`、
   `docs/ops/05-deployment.md`。
5. 删除 `docs/design/telemetry_actor.md`，移除 standalone/status/telemetry active refs。
6. 验证：

```bash
make check-authority
uv run pytest tests/test_authority_runtime_alignment.py -v
```

7. 提交：

```bash
git commit -m "docs(custos): align active authority with Crucible runtime"
```

### Task 12: 发布 0.4 RC 并跑真实 current integration

**Files**: version/release workflow、current integration、runbook、receipt。

版本映射：

```text
Python package: 0.4.0rc1
Git/Docker tag: v0.4.0-rc.1
Final:          0.4.0 / v0.4.0
```

要求：

- 冻结 v0.3.0 历史 tag/digest，不重建。
- release workflow 测试 PEP 440 ↔ OCI tag mapping。
- 新增 `tests/integration/test_crucible_runner_runtime.py`。
- 使用 exact Crucible producer fixture/receipt。
- 真实启动 NATS/runner，发布 desired deployment，等待 ready lifecycle fact。
- 证明 restart 后 reconcile 恢复、terminal node failure 被重新观测、RunnerFact 已签名。
- 使用 Plan 18 candidate toolkit/artifact。
- PS Plan 56 对 RC image 生成 real Docker receipt。
- Final 重新构建、签名、锁定和验收。

验证：

```bash
make verify
make verify-nt
make verify-runtime-existing
```

提交 RC：

```bash
git commit -m "release(custos): publish 0.4 runtime candidate"
```

Final receipt 后：

```bash
git commit -m "release(custos): publish 0.4.0"
```

### Task 13: 文档收尾 (close-out)

**Files**: 本计划、`.forge/README.md`、ROADMAP（若有）、完成报告。

1. Plan 顶部改为 ✅ Completed 并填写日期。
2. 更新索引；ROADMAP 无对应项则 N/A。
3. 完成报告记录 PRE-PLAN `324da6e`、exact producer SHA、golden SHA、journal/ACK
   evidence、NT risk seam evidence、RunnerFact parity、0.4 RC/final digests 和 PS Plan 56
   receipt。
4. aggregate cap 尚未证明时不得 close-out。
5. 提交：

```bash
git add .forge/plans/2026-07/19-crucible-command-runner-fact-runtime-convergence.md \
  .forge/README.md
git commit -m "docs(custos): mark plan 19 as completed"
```

## 验证清单 (Verification)

- [ ] `make verify`：PASS
- [ ] `make verify-nt`：PASS
- [ ] `make check-authority`：PASS
- [ ] Current runtime integration：PASS
- [ ] Exact clean Crucible producer receipt
- [ ] Golden fixture byte-identical
- [ ] 无 legacy runtime parsing fallback
- [ ] 无 legacy `code_hash`
- [ ] Artifact/manifest/source digest 分离
- [ ] Desired state restart 后恢复
- [ ] ACK ordering 有 crash tests
- [ ] lifecycle fact ID 幂等
- [ ] deploy 等待真实 ready
- [ ] terminal task failure 可观测
- [ ] daemon 不吞异常
- [ ] equity 使用 `portfolio.equity`
- [ ] `unrealized_pnl(mark_price)` 正确调用
- [ ] breaker unreliable snapshot fail closed
- [ ] native per-order limit 有黑盒证明
- [ ] aggregate cap 有不可绕过证明
- [ ] OrderDenied/Rejected 有 signed operational fact
- [ ] 无 unsigned telemetry/status 恢复
- [ ] authority gate 扫描全部 active files
- [ ] v0.3 历史 artifacts 未被覆盖
- [ ] `0.4.0rc1` 和 `0.4.0` 均重新构建、签名、验证

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|---|---|---|---|
| T0 Plan-first | [x] | 2026-07-14 | plan-first commit containing this plan; `324da6e` remains PRE-PLAN |
| T1 Verification floor | [ ] | — | 当前 format gate 失败 |
| T2 Strict command | [ ] | — | 等 clean Crucible SHA |
| T3 Provenance digests | [ ] | — | |
| T4 Durable journal | [ ] | — | |
| T5 Engine lifecycle | [ ] | — | |
| T6 Daemon supervision | [ ] | — | |
| T7 Portfolio/equity | [ ] | — | |
| T8 Native per-order risk | [ ] | — | |
| T9 Aggregate cap | [ ] | — | hard live gate |
| T10 RunnerFact parity | [ ] | — | |
| T11 Authority/docs | [ ] | — | |
| T12 0.4 integration/release | [ ] | — | |
| T13 Close-out | [ ] | — | |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|---|---|---|---|
| PRE-PLAN | `324da6e` | 大规模 authority migration 先于 Plan 19 | Yes, 2026-07-14 |
| CORRECTION | mode | outer `mode` 与 canonical `trading_mode` 均正确 | Yes, 2026-07-14 |
| BUG | provenance | artifact digest 被误当 source hash | Yes, 2026-07-14 |
| BUG | equity | NT method 当属性读取且 equity 语义错误 | Yes, 2026-07-14 |
| SAFETY | aggregate cap | 无不可绕过生产 seam 前 capability=false | Yes, 2026-07-14 |
| AUTHORITY | telemetry | 删除旧 standalone telemetry/status，不恢复 | Yes, 2026-07-14 |
| RELEASE | SemVer | breaking migration 发布为 0.4 | Yes, 2026-07-14 |
| HARD-GATE | Crucible receipt | dirty producer checkout 不可充当 authority | Yes, 2026-07-14 |
