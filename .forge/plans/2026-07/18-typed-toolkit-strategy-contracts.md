# 18 - Publish typed toolkit and strategy execution contracts

> **Status**: ⏳ In progress
> **Created**: 2026-07-14
> **Revised**: 2026-07-14 after v1.team authority review
> **Project**: Custos
> **Source**: PS Plan 53 strategy/toolkit convergence roadmap and v1.team review
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: revised PS Plan 53 authority boundary
> **Hard gates**: cross-repo requirements review before schema freeze; Crucible StrategyRelease receipt before final release
> **Soft depends on**: PS Plan 54, Speculum Plan 01, Custos Plan 19 integration receipt
> **Original plan-first**: `b898ee1`; this live-plan revision supersedes its erroneous decisions

## 上下文 (Context)

Custos 当前仍把公共策略实现放在：

```text
src/custos/engines/nautilus/toolkit/
├── shared/             160 files
└── vendor/pandas_ta/   299 files
```

当前实现通过 `sys.path` 暴露顶层 `shared.*`，注册伪造的 `pkg_resources`
distribution，并把 vendored pandas-ta 暴露为顶层 `pandas_ta`。PS 和 Custos
存在公共实现权威漂移，Speculum 还通过 sibling PS checkout 动态加载策略。

原 Plan 18 的方向正确，但审查确认以下设计不能执行：

1. `deployment_id: str` 与现有 runtime authority 冲突。
2. Plan 自行冻结 `strategy_key/version/ArtifactRef`，形成第二套 StrategyRelease
   authority。
3. 根 package Python 基线被错误提升到 3.12。
4. source-path 与 production wheel 混成同一发布模型。
5. attestation 缺少 issuer、workflow、bundle 和 trust-policy binding。
6. 459 个 donor/vendor 文件、契约、发布、四仓切换被当作单次原子任务。

本修订直接替换错误决策。旧文本只由 Git history 保留，不作为兼容契约。

## 目标 (Goal)

发布独立、typed、不可变的 `custos-strategy-toolkit` distribution，并提供：

- Custos-owned strategy execution ABI；
- Custos-owned artifact schema 与本地 fail-closed verifier；
- Nautilus toolkit 的单一 canonical implementation；
- 对现有 NT 策略业务源码的 zero-rewrite 迁移；
- Crucible StrategyRelease authority 下的 exact artifact execution；
- PS、Speculum、Crucible 和 Custos 的 producer/consumer receipts。

本计划不拥有 StrategyRelease、artifact selection、最终 effective config、部署审批、
组合风控、资本分配或结算。

## Authority Boundary

| 能力 | Canonical owner | Plan 18 职责 |
|---|---|---|
| Strategy source and build input | Philosophers-Stone | 消费 build receipt，不接管策略研究源码 |
| Execution ABI and toolkit implementation | Custos | 定义、实现并版本化 |
| Artifact schema and local verifier | Custos | 生产 schema/receipt，验证 exact bytes、attestation 和 compatibility |
| StrategyRelease lifecycle | Crucible | 消费 Custos schema receipt，生产 released artifact binding |
| Artifact selection and manifest digest | Crucible | 不根据 `strategy_key` 自行选择 artifact |
| Final effective config | Crucible | ABI 仅接收已签名命令绑定的 config |
| Backtest catalog and policy | Speculum | 提供只读 manifest/artifact consumer contract |
| Advisory strategy sizing | Toolkit/strategy | 非授权建议，不可放宽 mandatory safety |
| Mandatory local safety | Custos runtime | Plan 19 执行 signed policy |
| Canonical portfolio/risk policy | Crucible | Plan 18 不实现 D2-D4 |

`strategy_key` 只能是作者侧 catalog alias。它不是授权 ID、release ID、runtime
address 或幂等 key。

## Runtime Identity

`deployment_instance_id` 是唯一 runtime address。`deployment_spec_id`、
`deployment_spec_digest` 和 `generation` 只提供 provenance/ordering：

```python
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrategyExecutionContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: Literal["nautilus"]
    trading_mode: Literal["sandbox", "testnet", "live"]
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: Sha256Hex
    generation: Annotated[int, Field(ge=1)]


class StrategyRuntimeV1(Protocol):
    strategy_class: type

    def build_config(
        self,
        effective_config: dict[str, object],
        execution_context: StrategyExecutionContextV1,
    ) -> object: ...
```

约束：

- strict model 必须拒绝 legacy `deployment_id`。
- ABI 不得把 `strategy_key` 用作 runtime identity。
- effective config 只能来自已验证的 signed Crucible command。
- ABI 不宣称建立安全边界；mandatory order enforcement 属于 Plan 19。

固定 entry-point group：

```text
alephain.strategy_runtime.v1
```

## Contract Freeze Rules

本计划不在 plan 文本中提前冻结未经 producer/consumer requirements review 的完整
`StrategyManifestV1` 或 `StrategyArtifactRefV1` 字段表。Task 2 由 Custos 生产
versioned JSON Schema；Crucible、PS 和 Speculum 必须先确认 requirements。随后
Crucible Plan 88 消费 exact schema bytes/hash，并拥有 StrategyRelease business binding。

不可降级要求：

- Manifest 是 artifact 内的语义/compatibility metadata，不是 release authority。
- ArtifactRef 绑定 exact artifact bytes、manifest bytes 和 required runtime artifacts。
- Crucible StrategyRelease 绑定 canonical artifact digest、manifest digest 和
  DeploymentSpec provenance。
- Custos 只执行 signed command 绑定的 exact artifact/digests。
- unknown fields 和 unknown schema versions fail closed。
- live/testnet production path 只接受签名 wheel/artifact。
- source-path 仅允许 sandbox development，必须携带 source hash，并明确
  non-promotable、non-live。
- artifact digest、manifest digest、source hash 不得互相代用。

Attestation 至少绑定：

- artifact digest、manifest digest 和 bundle digest；
- source repository 和 exact commit；
- expected issuer、workflow identity/subject；
- trust-policy identifier、version 和 digest；
- build inputs、Python version 和 exact engine/toolkit versions。

验证必须在 unpack/import 前完成。安全解包拒绝绝对路径、`..`、symlink escape
和 artifact/manifest mismatch。

## Python and Runtime Baseline

| Surface | Baseline |
|---|---|
| Root Custos and lightweight contracts | Python `>=3.11` |
| `custos_toolkit` platform-neutral modules | Python `>=3.11` |
| Nautilus implementation extra | Python `>=3.12`, exact NT `1.230.0` |
| PS/Speculum Nautilus acceptance | Python 3.12, exact NT `1.230.0` |

Importing `custos_toolkit.contracts` on Python 3.11 must not load NautilusTrader,
modify `sys.path` or execute strategy code.

## Zero-Rewrite Acceptance

迁移必须证明现有 NT 策略的业务信号、indicator、position sizing 和 order intent
源码无需重写。允许的变更仅限：

- package/import namespace；
- manifest/build metadata；
- entry-point wrapper；
- thin engine adapter；
- 因公开 ABI 引入的类型适配。

验收必须包含：

1. 迁移前后的 strategy business-source semantic diff。
2. 固定输入下的 signal/order-intent characterization parity。
3. clean venv wheel-only import。
4. 不依赖 sibling checkout 或顶层 `shared`/`pandas_ta`。

如业务逻辑必须改变，必须移出本计划并由 PS 独立 strategy change plan 审批。

## Architecture

```text
packages/custos-strategy-toolkit/
└── src/custos_toolkit/
    ├── contracts/       # lightweight models + generated JSON Schema
    ├── strategy/        # execution ABI and fixed entry-point loader
    ├── config/
    ├── filters/
    ├── indicators/
    ├── advisory_risk/   # strategy advisory helpers, never canonical policy
    ├── nautilus/        # Python >=3.12 / NT-specific implementation
    └── _vendor/
        └── pandas_ta/   # private implementation detail

PS build ───────────────> signed strategy artifact
Crucible StrategyRelease ─> exact selected artifact/digests/effective config
Custos verifier ─────────> verify then load fixed entry point
Speculum ─────────────────> verified artifact backtest consumer
```

## File Inventory

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `.forge/plans/2026-07/18-typed-toolkit-strategy-contracts.md` | 修改 | 本 live-plan 修订 |
| `.forge/README.md` | 修改 | 修订依赖和说明 |
| `docs/design/strategy-toolkit.md` | 新增 | authority、ABI、risk taxonomy |
| `packages/custos-strategy-toolkit/**` | 新增 | 独立 distribution |
| `src/custos/engines/nautilus/toolkit/**` | 最终删除 | 完成 consumer cutover 后移除旧 authority |
| `tests/test_toolkit_distribution.py` | 新增 | namespace/import/wheel gates |
| `tests/test_toolkit_contracts.py` | 新增 | schema/runtime identity gates |
| `tests/test_toolkit_zero_rewrite.py` | 新增 | semantic/behavior parity |
| `tests/test_toolkit_consumer_receipts.py` | 新增 | 四仓 exact receipts |
| `.github/workflows/release-toolkit.yml` | 新增 | reproducible build/sign/release |
| `pyproject.toml`, `uv.lock` | 修改 | workspace 与 conditional runtime extras |
| `CHANGELOG.md` | 修改 | candidate/final release notes |

## Tasks

### Task 0: Repair the live plan

1. 用本修订替换错误 schema、identity、authority 和 Python 决策。
2. 更新 Custos index。
3. 同步修订 PS Plan 53，不把旧 `b898ee1` 当作最终 contract approval。
4. 只 stage 计划和索引，提交：

```bash
git commit -m "docs(custos): repair plan 18 authority and execution contracts"
```

### Task 1: Freeze read-only migration inventory and ownership

1. 为 459 个 donor/vendor 文件生成 machine-readable inventory。
2. 分类为 platform-neutral、Nautilus-specific、private vendor、PS-owned strategy、
   PS-owned Hummingbot 或 delete。
3. 写失败测试，拒绝顶层 `shared`/`pandas_ta`、path mutation 和双 canonical source。
4. 写 `docs/design/strategy-toolkit.md` authority/risk taxonomy。
5. 此任务不得移动或重写生产源码。

提交：

```bash
git commit -m "docs(toolkit): freeze extraction inventory and authority"
```

### Task 2: Coordinate and freeze versioned contracts

Hard gate：Crucible、PS 和 Speculum 必须分别确认 producer/consumer requirements。
Custos 是 execution ABI/artifact schema producer；本 Task 的 receipt 是 Crucible
Plan 88 的输入，而不是反向依赖 Plan 88 完成。

1. 先写 runtime identity、unknown-field、legacy `deployment_id` 和 Python 3.11
   lightweight-import 失败测试。
2. 定义 execution ABI、Manifest 和 ArtifactRef requirements。
3. 生成 versioned JSON Schema；schema 与实现来自同一 source model。
4. 记录 Custos producer SHA、schema digest 和三方 requirements-review receipts。
5. 明确 schema 不授予 release/selection authority。

提交：

```bash
git commit -m "feat(toolkit): define coordinated strategy execution contracts"
```

### Task 3: Build the minimal distribution

1. 建立 uv workspace 和 `custos-strategy-toolkit` package。
2. platform-neutral/contracts 支持 Python 3.11。
3. Nautilus extra 仅在 Python 3.12+ 安装并 pin NT 1.230.0。
4. 添加 `py.typed`、strict package mypy 和 clean-wheel import tests。
5. 不迁移 donor implementation。

提交：

```bash
git commit -m "feat(toolkit): create typed strategy toolkit distribution"
```

### Task 4: Extract toolkit with zero-rewrite proof

按 inventory 分批迁移：

1. config/protocol/filter/indicator/platform-neutral helpers；
2. Nautilus-specific adapters；
3. private `pandas_ta` vendor；
4. advisory sizing/risk helpers。

每批必须：

- 先写 characterization/typing tests；
- 保持 strategy business source unchanged；
- 禁止 `sys.path` mutation 和 fake distribution；
- 记录 semantic diff 与 fixed-input behavior parity；
- 独立提交，避免 459 文件一次性不可审查迁移。

### Task 5: Implement artifact verifier and attestation policy

1. 写失败测试覆盖 forged issuer、wrong workflow、wrong trust policy、digest mismatch、
   unsafe archive、entry-point escape 和 source-path live execution。
2. 实现 attestation-before-unpack verifier。
3. production 只接受 signed wheel；source-path 只允许 sandbox/non-promotable。
4. verifier 输出 typed receipt，不选择 StrategyRelease。

提交：

```bash
git commit -m "feat(toolkit): verify signed strategy artifacts"
```

### Task 6: Publish immutable candidate

1. reproducible build 两次并比较 wheel bytes/digest。
2. 发布不可覆盖的 `0.1.0rcN` candidate。
3. 记录 source SHA、wheel SHA、schema digest、attestation bundle 和 SBOM。
4. candidate 失败时递增 rc，不覆盖旧制品。

提交：

```bash
git commit -m "build(toolkit): publish strategy toolkit candidate"
```

### Task 7: Collect four-party receipts

必须全部指向 exact candidate digest：

- Crucible：StrategyRelease selection、manifest digest、DeploymentSpec provenance producer；
- PS：existing strategy zero-rewrite build/consumer；
- Speculum：verified discovery and backtest；
- Custos Plan 19：signed command exact-artifact runner integration。

任一 candidate 变化使全部 receipt 失效。

### Task 8: Final release and consumer cutover

1. 构建 final version，重新执行完整 receipts，不继承 RC PASS。
2. PS/Speculum/Custos 锁定 exact final digest。
3. 确认无 active consumer 后删除旧 vendored toolkit 和 compatibility adapter。
4. 禁止重建或重指向历史 Custos image/tag。

提交：

```bash
git commit -m "release(toolkit): publish verified strategy toolkit"
```

### Task 9: Close out

1. 运行全部 package、typing、wheel、attestation、zero-rewrite 和 consumer gates。
2. 回填 exact commits/digests/receipts。
3. 更新状态和 index。
4. 提交：

```bash
git commit -m "docs(custos): mark plan 18 as completed"
```

## Verification

- [ ] Legacy `deployment_id` 被拒绝
- [ ] `deployment_instance_id` 是唯一 runtime address
- [ ] StrategyRelease/artifact selection/effective config 仍由 Crucible 拥有
- [ ] `strategy_key` 仅是 catalog alias
- [ ] Root/contracts 保持 Python >=3.11
- [ ] Nautilus extra 使用 Python >=3.12 和 exact NT 1.230.0
- [ ] production 只接受 signed wheel
- [ ] source-path 仅 sandbox、non-promotable、non-live
- [ ] attestation 绑定 issuer/workflow/bundle/trust policy
- [ ] schema 由 source model 生成并经四方 review
- [ ] wheel 不提供顶层 `shared` 或 `pandas_ta`
- [ ] import 不修改 `sys.path`
- [ ] existing NT strategy business source zero-rewrite
- [ ] Crucible、PS、Speculum、Custos receipts 指向 exact digest
- [ ] toolkit advisory risk 不冒充 Custos/Crucible authority
- [ ] final 重新锁定并重新验证

## Progress

| Task | Status | Completed | Notes |
|---|---|---|---|
| T0 Live-plan repair | [~] | — | supersedes erroneous decisions in `b898ee1` |
| T1 Inventory/authority | [ ] | — | only immediately executable implementation task |
| T2 Coordinated contracts | [ ] | — | Custos producer; needs cross-repo requirements review |
| T3 Minimal distribution | [ ] | — | after T2 interface boundary |
| T4 Zero-rewrite extraction | [ ] | — | batch commits required |
| T5 Verifier/attestation | [ ] | — | production wheel only |
| T6 Candidate | [ ] | — | immutable rc |
| T7 Receipts | [ ] | — | four parties |
| T8 Final/cutover | [ ] | — | all receipts rerun |
| T9 Close-out | [ ] | — | |

## Deviations and Improvements

| 类型 | 位置 | 描述 | 状态 |
|---|---|---|---|
| PLAN-REPAIR | Original interface | 撤回 `deployment_id: str`，改用 UUID instance/spec identity | Accepted 2026-07-14 |
| AUTHORITY | StrategyRelease | 撤回 Custos-owned selection/release implication，恢复 Crucible authority | Accepted 2026-07-14 |
| BASELINE | Python | 撤回全 package >=3.12；contracts/core >=3.11，NT extra >=3.12 | Accepted 2026-07-14 |
| SECURITY | Artifact mode | production signed wheel 与 sandbox source-path 分离 | Accepted 2026-07-14 |
| SCOPE | Migration | 459-file migration 改为 inventory-backed reviewable batches | Accepted 2026-07-14 |
| HISTORY | `b898ee1` | 保留为原 plan-first 历史，不再代表有效 schema approval | Recorded |

## Quantitative Summary

- Production packages: 1 new independent distribution
- Runtime identities: 1 address + 3 provenance/ordering fields
- Migration batches: at least 4
- Required external receipts: Crucible, PS, Speculum, Custos
- Release stages: immutable RC and independently reverified final
- Out of scope: StrategyRelease, approvals, portfolio risk, capital, settlement
