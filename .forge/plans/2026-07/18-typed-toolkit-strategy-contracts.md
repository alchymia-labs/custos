# 18 - Publish typed toolkit and strategy execution contracts

> **Status**: ⏳ In progress — 18a / T1-T2 complete; 18b T3-T4b complete, T5 open; T6-T9 open
> **Created**: 2026-07-14
> **Revised**: 2026-07-15 after Task 4b exact-commit receipt publication
> **Project**: Custos
> **Source**: PS Plan 53 strategy/toolkit convergence roadmap and v1.team review
> **For Claude**: Use `/forge:execute` for exactly one canonical slice per session.
> **multi_session_scope**: `true`
> **Depends on**: revised PS Plan 53 authority boundary
> **Hard gates**: Crucible/PS requirements review before schema freeze; PS Plan 54 immutable artifact/BOM receipt; Crucible Plan 88 StrategyRelease acceptance before Custos verifier/runtime cutover
> **Soft depends on**: Custos Plan 19 integration receipt
> **Original plan-first**: `b898ee1`; this live-plan revision supersedes its erroneous decisions
> **Cross-repo dependency name**: external plans must depend on `Custos Plan 18 Task 2 schema receipt`, never on an internal `18a` slice alias
> **Task 2 READY gates**: exact Crucible Plan 88 consumer requirements-review receipt plus exact PS Plan 54 producer requirements-review receipt for the same Custos producer commit and asset-index digest
> **Downstream, not Task 2 READY gates**: PS Plan 54 immutable artifact/BOM production and Crucible Plan 88 StrategyRelease completion consume the READY Task 2 receipt; they cannot be prerequisites of that receipt

## 上下文 (Context)

Custos 当前仍把公共策略实现放在：

```text
src/custos/engines/nautilus/toolkit/
├── shared/              91 deterministic source inputs
└── vendor/pandas_ta/   150 deterministic source inputs
```

当前实现通过 `sys.path` 暴露顶层 `shared.*`，注册伪造的 `pkg_resources`
distribution，并把 vendored pandas-ta 暴露为顶层 `pandas_ta`。PS 和 Custos
存在公共实现权威漂移。

原 Plan 18 的方向正确，但审查确认以下设计不能执行：

1. `deployment_id: str` 与现有 runtime authority 冲突。
2. Plan 自行冻结 `strategy_key/version/ArtifactRef`，形成第二套 StrategyRelease
   authority。
3. 根 package Python 基线被错误提升到 3.12。
4. source-path 与 production wheel 混成同一发布模型。
5. attestation 缺少 issuer、workflow、bundle 和 trust-policy binding。
6. 241 个当前 donor/vendor deterministic source inputs、契约、发布、四仓切换被当作单次原子任务。

本修订直接替换错误决策。旧文本只由 Git history 保留，不作为兼容契约。

## 目标 (Goal)

发布两个独立、typed、不可变且 Python baseline 清晰分离的 distributions，并提供：

- Python 3.11 compatible `custos-strategy-toolkit` base/contracts distribution；
- Python 3.12-only `custos-strategy-toolkit-nautilus` engine distribution；
- Custos-owned strategy execution ABI；
- Custos-owned artifact schema 与本地 fail-closed verifier；
- Nautilus toolkit 的单一 canonical implementation；
- 对现有 NT 策略业务源码的 zero-rewrite 迁移；
- Crucible StrategyRelease authority 下的 exact artifact execution；
- Custos、PS 和 Crucible v1.team artifact chain 的 staged producer/consumer receipts。

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
| Advisory strategy sizing | Toolkit/strategy | 非授权建议，不可放宽 mandatory safety |
| Mandatory local safety | Custos runtime | Plan 19 执行 signed policy |
| Canonical portfolio/risk policy | Crucible | Plan 18 不实现 D2-D4 |

### Independent legacy compatibility lane

现有 PS `build-image.sh` -> Crucible Python image 发布/部署链继续保留为独立
compatibility lane。它不消费或生产 Custos execution ABI、artifact schema 或 receipt，
不属于 v1.team artifact chain，不得作为 team fallback、验收证据或 close-out gate；
Plan 18 也不要求删除、迁移或阻断该链。

`strategy_key` 只能是作者侧 catalog alias。它不是授权 ID、release ID、runtime
address 或幂等 key。

## Runtime Identity

`deployment_instance_id` 是唯一 runtime address。`deployment_spec_id`、
`deployment_spec_digest` 和 `generation` 只提供 provenance/ordering：

```python
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Literal, Protocol, TypeAlias, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
JsonScalar: TypeAlias = None | bool | int | Decimal | str
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
FrozenJsonObject: TypeAlias = Mapping[str, JsonValue]
ConfigT = TypeVar("ConfigT")
StrategyT_co = TypeVar("StrategyT_co", covariant=True)


class StrategyExecutionContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: Literal["nautilus"]
    trading_mode: Literal["sandbox", "testnet", "live"]
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: Sha256Hex
    effective_config_digest: Sha256Hex
    generation: Annotated[int, Field(ge=1)]


class StrategyRuntimeAdapterV1(Protocol[ConfigT, StrategyT_co]):
    def build_config(
        self,
        effective_config: FrozenJsonObject,
        execution_context: StrategyExecutionContextV1,
    ) -> ConfigT: ...

    def build_strategy(self, config: ConfigT) -> StrategyT_co: ...
```

约束：

- strict model 必须拒绝 legacy `deployment_id`。
- ABI 不得把 `strategy_key` 用作 runtime identity。
- effective config 只能来自已验证的 signed Crucible command；JSON number 使用
  `Decimal` 解析，object/list 递归冻结为 read-only mapping/tuple，禁止把 mutable
  `dict`/`list` 或任意 Python object 交给 strategy。
- runner 必须在调用 adapter 前重算 canonical JSON digest 并匹配
  `effective_config_digest`；adapter 不得重新 merge defaults 或改变已签名 config。
- ABI 不宣称建立安全边界；mandatory order enforcement 属于 Plan 19。

固定 entry-point group：

```text
alephain.strategy_runtime.v1
```

## Contract Freeze Rules

本计划不在 plan 文本中提前冻结未经 producer/consumer requirements review 的完整
`StrategyManifestV1` 或 `StrategyArtifactRefV1` 字段表。Task 2 由 Custos 生产
versioned JSON Schema；Crucible 和 PS 必须先确认 requirements。随后
Crucible Plan 88 消费 exact schema bytes/hash，并拥有 StrategyRelease business binding。

不可降级要求：

- Manifest 是 artifact 内的语义/compatibility metadata，不是 release authority。
- Custos `ArtifactRef` 只描述 exact artifact bytes、manifest bytes、required runtime
  artifacts 和 attestation evidence；它不包含 release/spec business state。
- Crucible `StrategyRelease` 消费 ArtifactRef，独立绑定 immutable release BOM；它不
  绑定、创建或依赖任何 `DeploymentSpec`。
- Crucible `DeploymentSpec` 引用 `strategy_release_id`，并独立绑定 effective config、
  config digest 和 canonical policy references。
- signed runner command 绑定 `deployment_instance_id`、spec id/digest、generation、
  `strategy_release_id`、release BOM digest 和 effective config digest。
- Custos verifier receipt 必须无损回显 command 中的 identity/digests，并证明本地
  loaded bytes 与 release BOM 每个成员一致；不得只验证一个笼统 artifact digest。
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

Expected trust roots、issuer、workflow identity 和 trust-policy version/digest 必须来自
runner-local、签名验证通过且 immutable 的 Custos release configuration。Artifact、
manifest 或 Crucible command 只能引用该本地 policy digest，不得提供、替换或选择
trust root。Runner 必须先验证 local release configuration，再读取 artifact metadata。

验证必须在 unpack/import 前完成。安全解包拒绝绝对路径、`..`、symlink escape
和 artifact/manifest mismatch。

### Release BOM and digest semantics

Candidate/final receipts 绑定 canonical `StrategyReleaseBomV1`，至少包含：

- base/contracts wheel SHA-256；
- Nautilus wheel SHA-256；
- strategy wheel SHA-256；
- strategy manifest SHA-256；
- 每个 runtime artifact 的 role、size 和 SHA-256；
- attestation bundle、SBOM 和 contract schema SHA-256；
- PS source repository、exact commit 和 normalized source-tree digest。

`release_bom_digest` 是 canonical BOM bytes 的 SHA-256，只用于完整性索引，不能代替
成员 digest。所有 receipt 必须同时记录 BOM digest 和完整成员表；任一 wheel、manifest、
runtime artifact、attestation、SBOM、schema 或 source revision 改变都会产生新 BOM 并使旧
receipts 失效。禁止使用“一个 candidate digest”代表多制品 release。

## Python and Runtime Baseline

| Surface | Baseline |
|---|---|
| Root Custos and lightweight contracts | Python `>=3.11` |
| `custos_toolkit` platform-neutral modules | Python `>=3.11` |
| `custos-strategy-toolkit` base/contracts distribution | Python `>=3.11` |
| `custos-strategy-toolkit-nautilus` distribution | Python `>=3.12,<3.13`, exact NT `==1.230.0` |
| PS Nautilus artifact acceptance | Python 3.12, exact NT `1.230.0` |

Importing `custos_toolkit.contracts` on Python 3.11 must not load NautilusTrader,
modify `sys.path` or execute strategy code.

Python packaging cannot express an extra-specific `Requires-Python` constraint safely.
Therefore Nautilus is a separate distribution, not a conditional extra. It must declare
`requires-python = ">=3.12,<3.13"`, depend on an exact compatible base/contracts version and
pin `nautilus-trader==1.230.0` without a `python_version` marker. Installing the Nautilus
distribution on Python 3.11 must fail dependency resolution; silently skipping NT is forbidden.

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

packages/custos-strategy-toolkit-nautilus/
└── src/custos_toolkit_nautilus/
    ├── adapter/         # Python >=3.12,<3.13 / NT ==1.230.0
    └── _vendor/
        └── pandas_ta/   # private implementation detail

Custos Task 2 schema/toolkit ─> PS Plan 54 immutable artifact/BOM
PS Plan 54 artifact/BOM ─────> Crucible Plan 88 StrategyRelease acceptance
Crucible StrategyRelease ────> Custos verifier/runtime exact-artifact execution

PS build-image.sh ───────────> Crucible Python image publication/deployment
                               (independent compatibility lane; non-gating)
```

## File Inventory

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `.forge/plans/2026-07/18-typed-toolkit-strategy-contracts.md` | 修改 | 本 live-plan 修订 |
| `.forge/README.md` | 修改 | 修订依赖和说明 |
| `docs/design/strategy-toolkit.md` | 新增 | authority、ABI、risk taxonomy |
| `packages/custos-strategy-toolkit/**` | 新增 | 独立 distribution |
| `packages/custos-strategy-toolkit-nautilus/**` | 新增 | 独立 Python 3.12 NT distribution |
| `src/custos/engines/nautilus/toolkit/**` | 最终删除 | 完成 consumer cutover 后移除旧 authority |
| `tests/test_toolkit_distribution.py` | 新增 | namespace/import/wheel gates |
| `tests/test_toolkit_contracts.py` | 新增 | schema/runtime identity gates |
| `tests/test_toolkit_zero_rewrite.py` | 新增 | semantic/behavior parity |
| `tests/test_toolkit_consumer_receipts.py` | 新增 | v1.team artifact-chain exact receipts |
| `.github/workflows/release-toolkit.yml` | 新增 | reproducible build/sign/release |
| `pyproject.toml`, `uv.lock` | 修改 | workspace 与两个 distribution 的 disjoint Python baselines |
| `CHANGELOG.md` | 修改 | candidate/final release notes |
| `docs/authority/ecosystem-authority.json` | 修改 | 记录 execution ABI/artifact schema authority 和 lifecycle chain |
| `authority-manifest.json` | 修改 | 纳入 toolkit authority/schema artifacts 和 drift inputs |
| `.claude/rules/authority-docs.md` | 修改 | 记录 Task 2 schema receipt 与 precedence |
| `Makefile` / authority checker inputs | 修改 | `make check-authority` 覆盖 schema/BOM/authority drift |

## Canonical Multi-session Slices

本 Plan 是 `multi_session_scope: true`。内部 slice 名只用于 Custos 执行和 handoff；任何
跨仓 plan 必须引用 `Custos Plan 18 Task 2 schema receipt`，不得依赖 `18a` 名称。

| Slice | Tasks | 独立 DoD | Stop gate |
|---|---|---|---|
| 18a Contract authority | T1-T2 | inventory、authority docs、source-generated schemas、lossless lifecycle mapping、Task 2 receipt 和 `make check-authority` 全部 PASS | schema/receipt commit 与 handoff packet 未记录前不得开始 18b |
| 18b Extraction and verification | T3-T5 + T4b | 两个 distributions 可独立构建；3.11 negative install、zero-rewrite、typing closure、deep-frozen config、attestation-before-import gates PASS | 18a exact Task 2 receipt 未锁定，任一 migration batch 未有 parity evidence，或 extracted typing baseline 未清零时停止 production-ready 声明 |
| 18c Immutable RC | T6 | reproducible RC、完整 release BOM、签名、SBOM、local trust-policy binding PASS | RC BOM/成员 digests 未固定前不得请求 consumer receipt |
| 18d Consumer cutover | T7-T9 | PS Plan 54、Crucible Plan 88 和 Custos verifier/runtime candidate/final receipts、final BOM、旧 authority 删除、close-out gates PASS | 仅 v1.team artifact-chain BOM/receipt 不匹配会停止并发布新 RC；不得等待 Speculum |

18b 的 production-ready 声明只在 T3-T5 与 T4b 整体 DoD 全部满足后成立。T3 单独完成只建立
distribution 和 typing boundary，不得标记 18b production-ready，也不得冒充 artifact verifier
或 runtime cutover 已完成。

T4 必须把 canonical implementation **move** 到两个新 distributions。旧
`src/custos/engines/nautilus/toolkit/` 在迁移期间最多保留不含 implementation 的临时 shim；
不得留下第二份 writable canonical source。该 shim 不是 v1.team fallback，并必须在 T8
consumer cutover 后删除。

18d START 只要求 18c immutable RC、PS Plan 54 immutable artifact/BOM receipt 和
Crucible Plan 88 StrategyRelease acceptance。Speculum plan、receipt 或运行结果不是 START、
STOP、candidate/final acceptance 或 Plan 18 close-out 输入。

每个 session 只能推进一个 slice。每个 slice 结束必须提交 handoff packet，至少记录：

1. start base、landed commit 和 touched files；
2. 执行的 exact commands、PASS/FAIL/skip 与环境版本；
3. schema、wheel、BOM、attestation、SBOM 和 source digests；
4. deviations、剩余 blockers 和下一 slice 的 immutable inputs；
5. authority drift 检查结果。
6. 下一 slice 的 START/STOP evidence；只记录 canonical v1.team artifact-chain receipts，
   不把 Speculum 或 legacy compatibility lane 写成 gate。

Slice 可独立 close out，但不能把 slice PASS 冒充整个 Plan 18 Completed。

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

1. 为当前 241 个 donor/vendor deterministic source inputs 生成 machine-readable inventory。
2. 分类为 platform-neutral、Nautilus-specific、private vendor、PS-owned strategy、
   PS-owned Hummingbot 或 delete。
3. 写失败测试，拒绝顶层 `shared`/`pandas_ta`、path mutation 和双 canonical source。
4. 写 `docs/design/strategy-toolkit.md` authority/risk taxonomy。
5. 更新 authority snapshot、manifest、precedence 和 drift-check inputs。
6. 此任务不得移动或重写生产源码。

提交：

```bash
git commit -m "docs(toolkit): freeze extraction inventory and authority"
```

### Task 2: Coordinate and freeze versioned contracts

Hard gate：Crucible Plan 88 和 PS Plan 54 必须分别提交针对同一 Custos producer
commit、asset-index digest 和 schema digest set 的 consumer/producer requirements-review
receipt。Custos 是 execution ABI/artifact schema producer；本 Task 的 READY receipt 是
PS Plan 54 artifact/BOM production 和 Crucible Plan 88 StrategyRelease completion 的输入，
不得反向依赖 Plan 54 final BOM receipt 或 Plan 88 completion。

1. 先写 runtime identity、unknown-field、legacy `deployment_id` 和 Python 3.11
   lightweight-import 失败测试。
2. 定义 recursive JsonValue、deep-freeze/canonical digest、typed runtime adapter、
   Manifest、ArtifactRef 和 `StrategyReleaseBomV1` requirements。
3. 生成 versioned JSON Schema；schema 与实现来自同一 source model。
4. 生成 lossless mapping golden：ArtifactRef → StrategyRelease → DeploymentSpec →
   signed command → Custos verifier receipt；明确 release 独立于 spec。
5. 记录 Custos producer SHA、schema digest 和 Crucible/PS requirements-review receipts；该
   artifact 的 canonical 名称是 `Custos Plan 18 Task 2 schema receipt`。
6. 运行 `make check-authority` 并记录 PASS。
7. 明确 schema 不授予 release/selection authority。

提交：

```bash
git commit -m "feat(toolkit): define coordinated strategy execution contracts"
```

### Task 3: Build the minimal distribution

1. 建立 uv workspace、Python >=3.11 `custos-strategy-toolkit` 和
   Python >=3.12,<3.13 `custos-strategy-toolkit-nautilus` 两个 distributions。
2. platform-neutral/contracts 支持 Python 3.11，Nautilus distribution 依赖 exact
   base version 和 `nautilus-trader==1.230.0`。
3. 禁止用 `python_version` marker 静默跳过 NT；添加 Python 3.11 安装 Nautilus
   distribution 必须失败的 negative integration test。
4. 添加 `py.typed`、strict package mypy、clean-wheel import 和 two-wheel isolation tests。
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
- 独立提交，避免 241 个 source inputs 一次性不可审查迁移。

T4 执行时确认 namespace cutover 必须保持原子性，否则任一中间 commit 都会同时缺失旧路径
和部分新路径。审查粒度因此由 `strategy-toolkit-extraction-v1.json` 的 241 条逐文件
source/target digest records 提供，而不是制造不可运行的 partial-move commits。冻结 parity
golden 绑定 T3 exact commit，独立于迁移后 fixture。

### Task 4b: Close extracted-source typing debt without behavior change

T4 首次把 inventory source 纳入 mypy 后，确认 T3 的 strict PASS 只覆盖当时的 4 个 base
contracts 与 2 个 Nautilus package source，不代表 241 个提取文件 strict。T4b 必须：

1. 保持 Custos-owned contracts/package shell strict PASS；
2. 以 `strategy-toolkit-typing-baseline-v1.json` 逐条锁定 extracted implementation 的
   path、line、error code 和 message，任何未审查变化 fail closed；
3. 当前 baseline 为 platform-neutral 75 errors、Nautilus adapter 289 errors；private vendor
   是第三方 source，排除 mypy 但继续受 digest 与 fixed-input parity gate 约束；
4. 只做 no-behavior-change typing closure；每批必须同时通过 zero-rewrite replacement review、
   fixed-input parity 和 exact debt reduction；
5. baseline 清零前不得宣称整个 distribution strict、18b production-ready 或 runtime-ready。

T4b 使用独立的 `strategy-toolkit-typing-closure-v1.json` 和 receipt 保存版本化证据：
历史 T4 extraction manifest、typing baseline 与 receipt 不修改；closure manifest 必须逐文件
绑定 exact T4 implementation `b5ff7ee9cea0e78f4462a478bafa42f8f6e18805` 的 source digest
到 typed target digest，并单独覆盖 local stubs/support files。Exact standalone T4b
implementation `5a19a816d4f6d90e7d3fbde80d39f562decd8c4b` 已通过 clean exact-HEAD
验证，因此 receipt 为 `READY_TYPING_CLOSURE`、`handoff_ready=true`，但 handoff 仅限
T4b typing closure。T5 public pre-import verifier contract 与 T6 immutable RC 仍阻塞
18b/runtime/production-ready。

T4b 可与 T5 实现并行，但属于 18b close-out hard gate。

### Task 5: Implement artifact verifier and attestation policy

Task 5 is a two-stage handoff and remains open until both stages close:

#### T5a: Public pre-import contract candidate

1. Add `StrategyArtifactPreImportVerificationReceiptV1` as an additive canonical
   contract. It may contain only pre-import evidence: verified entry point, exact
   command/artifact/BOM/member bindings, local policy/root, Sigstore/transparency,
   and archive evidence. `loaded_entry_point`, engine-ready, and runtime activation
   evidence remain exclusive to the existing Plan 19 post-import
   `StrategyArtifactVerificationReceiptV1`.
2. Preserve the Task 2 v1 receipt, v1 asset index, all eight indexed assets, and both
   accepted requirements reviews byte-for-byte. A fixed SHA-256 regression gate must
   fail before generation if any predecessor byte drifts.
3. Generate an independent v2 candidate asset index, pre-import schema, lifecycle
   golden/negative fixtures and SHA-256 sidecars from the canonical Python model.
   Publish `custos-plan-18-task-2-schema-receipt-v2.json` as
   `PENDING_REQUIREMENTS_REVIEWS`, `handoff_ready=false`, with null future commit and
   review evidence and an exact v1 predecessor pin.
4. Map the existing verifier kernel result into the public receipt without exposing
   quarantine paths or claiming import/engine readiness. Register every v2 artifact in
   the authority manifest as an additive candidate; v1 remains canonical.
5. After both exact consumer reviews land, the receipt may advance only to
   `REQUIREMENTS_REVIEWS_ACCEPTED`: bind the reviewed producer/index/schema bytes and
   exact review commits/paths/digests, but keep `handoff_ready`, loaded, engine-ready,
   runtime-ready, production-ready and immutable-toolkit-RC-ready false. This state
   unlocks T5b work only.

#### T5b: Coordinated public-contract handoff and production verifier close-out

1. Consume the exact Crucible and Philosophers-Stone requirements-only reviews of the
   v2 candidate bytes. Review acceptance alone must not change the receipt to handoff
   READY and must not unblock T6.
2. Complete the production Sigstore verifier library, public pre-import receipt return,
   and all failure modes below. Implementation
   `560e9f5b80962df3307f855be7ceef70c3585bd7` composes
   `ProductionSigstoreVerifier` + `ArtifactVerifierKernel`, returns the typed pre-import
   receipt and has focused `49 passed` without importing strategy code.
3. The remaining library-handoff gate is clean exact-HEAD full `make verify`. After it
   passes, the v2 receipt may become scoped `READY_PRE_IMPORT_VERIFIER` with
   `handoff_ready=true`. This means only schema + production verifier library are ready
   for T6/consumers; runtime invocation, import/load, engine readiness and runtime
   lifecycle remain Plan 19 work and do not block T6 toolkit RC.
   Exact verification HEAD `a856455d33b5defd05284183023db6d4320f8101` passed full
   `make verify`: 528 passed, 4 skipped, 1 xfailed; 169 formatted; Ruff, generator,
   authority, 241/241 extraction and strict mypy base 0/40 + adapter 0/59 all PASS.

1. 写失败测试覆盖 forged issuer、wrong workflow、wrong trust policy、digest mismatch、
   unsafe archive、entry-point escape 和 source-path live execution。
2. 从 runner-local signed release configuration 加载 trust roots/policy，先验签该配置，
   再实现 attestation-before-unpack verifier；拒绝 artifact/manifest/command 自选 trust root。
3. production 只接受 signed wheel；source-path 只允许 sandbox/non-promotable。
4. verifier 输入完整 release BOM，逐成员验证并输出无损 typed receipt，不选择
   StrategyRelease，不接受单一 artifact/candidate digest shortcut。

提交：

```bash
git commit -m "feat(toolkit): verify signed strategy artifacts"
```

### Task 6: Publish immutable toolkit RC

START gate is the scoped T5 `READY_PRE_IMPORT_VERIFIER` receipt. It is now open;
Plan 19 runtime invocation and PS Plan 56 are not T6 START gates.

#### T6a: Toolkit RC contract foundation

T6a defines only the Custos-owned immutable toolkit RC receipt/manifest contract and
generated JSON schema. `ToolkitRcReceiptManifestV1` requires exactly one base-contracts
wheel and one Nautilus wheel. Every member binds its immutable coordinate/digest,
SBOM, contract schema/index, Sigstore attestation, source commit, T4b zero-rewrite and
typing-closure receipts, and T5 pre-import verifier receipt. Base is fixed to Python
`>=3.11`; Nautilus is fixed to Python `>=3.12,<3.13` and NT `1.230.0`.

The validator rejects legacy top-level `shared`/`pandas_ta`, editable/path dependencies,
mutable or digest-mismatched coordinates, overwrite, and any loaded/engine/runtime/
production/strategy-BOM claim. The schema is registered as contract-only authority;
T6a does not build or publish wheels, create a READY RC receipt, or modify either
strategy-contract asset index.

RED -> GREEN evidence:

- RED: public `ToolkitRcReceiptManifestV1` import failed; generated schema was absent.
- RED: member types were absent, mutable coordinates were accepted, forbidden legacy
  modules were accepted, and the authority manifest lacked the contract-only entry.
- GREEN close-out: focused public-contract suite `5 passed`; generator `--check`,
  `make check-authority`, Ruff format/lint and JSON schema gates PASS; immutable v1/v2
  strategy-contract indexes remain exactly `d87d6fc2...` / `6fd49708...`.

#### T6b: Reproducible toolkit RC build candidate inputs

T6b adds a dedicated candidate-only build seam and workflow. It archives the exact
source commit into two independent staging roots, applies the same immutable
`0.1.0rcN` metadata transform, fixes `SOURCE_DATE_EPOCH`, and invokes Hatchling through
`uv build --offline`. Base and Nautilus are each built twice; exact wheel bytes and
SHA-256 digests must match before any manifest input is emitted.

The seam validates base Python `>=3.11`, Nautilus Python `>=3.12,<3.13`, exact
`nautilus-trader==1.230.0`, the same-version base dependency, no editable/path
dependencies, and no top-level `shared` or `pandas_ta`. Coordinates include the RC
version, filename and exact digest. Outputs are immutable runner-local files; an
existing output root fails closed. The dedicated read-only workflow uses a
pre-provisioned offline builder and leaves wheels, per-member SBOM inputs and the build
manifest input under `$RUNNER_TEMP` only.

RED -> GREEN evidence:

- RED: the public build seam import failed because `scripts/toolkit_rc_build.py` did
  not exist.
- RED: the first real offline build failed because `--no-build-isolation` exposed that
  Hatchling was absent from the test environment. The correction retained `--offline`
  while allowing uv to create an isolated backend from its local cache.
- RED: the dedicated workflow contract failed because
  `.github/workflows/toolkit-rc-reproducibility.yml` did not exist.
- GREEN: four focused tests PASS in `1.69s`; they perform four real wheel builds and
  prove byte/digest identity, metadata/dependency/top-level/SBOM policy, immutable
  output behavior and workflow authority limits. Ruff format/lint, generated-contract
  drift, `make check-authority`, extraction `241/241`, and T4b strict-zero gates PASS.

T6b creates no committed wheel, registry access, upload, READY toolkit receipt,
Sigstore bundle, final SBOM, strategy artifact, `StrategyReleaseBomV1`, runtime claim or
production authority. Those remain in the open T6 release slices.

1. 对 base contracts 与 Nautilus toolkit distributions 各做两次 reproducible build，
   比较 exact wheel bytes/digests。
2. 发布不可覆盖的 toolkit `0.1.0rcN` artifacts；失败时递增 rc，不覆盖旧制品。
3. 生成 Custos-owned immutable toolkit RC receipt，精确绑定 base/Nautilus wheels、
   distribution digests、SBOM、contract schema/index、Sigstore/source provenance，及
   T4b typing closure 与 T5 production-verifier evidence。
4. Custos 不生成完整 strategy artifact、strategy manifest 或
   `StrategyReleaseBomV1`。PS Plan 54 后续消费 toolkit RC 并生成这些 PS-owned bytes；
   Crucible 再对完整 BOM 建立 StrategyRelease authority。
5. PS Plan 56 不是 T6 START gate。PS legacy `build-image.sh` -> Crucible Python image
   compatibility lane 保持不变，且不得替代 toolkit RC 或 team receipt。

提交：

```bash
git commit -m "build(toolkit): publish strategy toolkit candidate"
```

### Task 7: Collect v1.team artifact-chain receipts

必须全部指向 exact candidate release BOM digest 和完整 BOM member digests：

- PS Plan 54：existing strategy zero-rewrite immutable artifact/BOM producer；
- Crucible Plan 88：StrategyRelease acceptance、manifest digest 和 exact BOM binding；
- Custos verifier/runtime：attestation-before-import 与 exact-artifact execution；
- Custos Plan 19：signed command exact-artifact runner integration。

任一 BOM member 或 canonical BOM bytes 变化使全部 receipt 失效。
Speculum 不生产本 Task receipt，也不 gate candidate、final 或 close-out。PS legacy
`build-image.sh` compatibility lane 不得替代上述任何 receipt。

### Task 8: Final release and consumer cutover

1. 构建 final version 和全新 final release BOM，重新执行完整 receipts，不继承 RC PASS。
2. PS、Crucible 和 Custos 锁定 exact final BOM 和全部 member digests。
3. 确认无 active consumer 后删除 Custos 旧 vendored toolkit 和 in-repo compatibility adapter；
   不以删除或迁移 PS legacy `build-image.sh` compatibility lane 为前提。
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

- [x] Legacy `deployment_id` 被拒绝
- [x] `deployment_instance_id` 是唯一 runtime address
- [x] StrategyRelease 独立于 DeploymentSpec；Spec 只引用 release
- [x] ArtifactRef → release → spec → command → verifier receipt 无损 mapping PASS
- [x] StrategyRelease/artifact selection/effective config 仍由 Crucible 拥有
- [x] `strategy_key` 仅是 catalog alias
- [x] Root/contracts 保持 Python >=3.11
- [x] 独立 Nautilus distribution 使用 Python >=3.12,<3.13 和 exact NT 1.230.0
- [x] Python 3.11 安装 Nautilus distribution fail closed，不静默跳过 NT
- [x] effective config 是 recursive typed/deep-frozen JSON 并匹配 signed digest
- [ ] production 只接受 signed wheel
- [x] source-path contract 仅允许 sandbox、non-promotable、non-live
- [x] attestation schema 绑定 issuer/workflow/bundle/trust policy
- [ ] trust roots/policy 只来自 runner-local signed release configuration
- [ ] candidate/final receipts 绑定 release BOM 和全部 member digests
- [x] schema 由 source model 生成并经 Crucible/PS requirements review
- [x] wheel 不提供顶层 `shared` 或 `pandas_ta`
- [x] lightweight contracts import 不修改 `sys.path`
- [x] existing NT strategy business source zero-rewrite
- [ ] PS Plan 54、Crucible Plan 88 和 Custos verifier/runtime receipts 指向 exact BOM/member digests
- [x] Speculum 不属于 START/STOP、candidate/final acceptance 或 close-out gate
- [x] PS legacy `build-image.sh` -> Crucible Python image 链保留为独立 compatibility lane，且不作为 team fallback 或验收证据
- [x] toolkit advisory risk 不冒充 Custos/Crucible authority
- [ ] final 重新锁定并重新验证
- [x] `make check-authority` 覆盖并通过 toolkit schema/BOM/ownership drift
- [ ] 18a-d 每个 slice 有独立 DoD、stop gate 和 handoff packet

## Progress

| Task | Status | Completed | Notes |
|---|---|---|---|
| T0 Live-plan repair | [x] | 2026-07-14 | `aa843f0` superseded erroneous decisions in `b898ee1` |
| T0R Execution-readiness correction | [x] | 2026-07-14 | `cccf8b2`, `ad49872`, and `bdd516c` corrected review topology, removed the Speculum gate, and reconciled the 241-input baseline |
| T1 Inventory/authority | [x] | 2026-07-14 | inventory/authority baseline landed in `877a52a`; current reviewed candidate `b36e9edf3ce9d2080e0d77b22ae99a65e32aaaf0` passed focused and full authority gates |
| T2 Coordinated contracts | [x] | 2026-07-14 | READY receipt pins candidate `b36e9edf3ce9d2080e0d77b22ae99a65e32aaaf0`, source `71990c6a...`, index `d87d6fc2...`, both exact requirements reviews, and clean verification checkout `f6406ea1...` |
| T3 Minimal distribution | [x] | 2026-07-15 | implementation `efc01da67b432e9b35beee3498415efc1bc46b98`; independent receipt READY; T4b-T5 remain open, so 18b is not production-ready |
| T4 Zero-rewrite extraction | [x] | 2026-07-15 | exact implementation `b5ff7ee9cea0e78f4462a478bafa42f8f6e18805`; clean exact-HEAD focused `91 passed, 1 skipped`; 241/241 extraction、parity、authority、English and lint gates PASS; receipt `VERIFIED_EXTRACTION_ONLY`, handoff false because T4b/T5 remain open |
| T4b Extracted typing closure | [x] | 2026-07-15 | exact implementation `5a19a816d4f6d90e7d3fbde80d39f562decd8c4b`; clean exact-HEAD `make verify` 508 passed, 4 skipped, 1 xfailed; assets/extraction 241/241/authority/closure PASS; strict mypy 0/40 base and 0/59 adapter; receipt `READY_TYPING_CLOSURE`, handoff limited to T4b; T5/T6 still block 18b production readiness |
| T5 Verifier/attestation | [x] | 2026-07-15 | Scoped `READY_PRE_IMPORT_VERIFIER`: producer `f3adde2...`, index `6fd49708...`, schema `d6e21b0a...`, Crucible review `3f41f32...`, PS review `267e23b...`, implementation `560e9f5...`, and exact verification HEAD `a856455...` (528 passed/4 skipped/1 xfailed; all authority/typing/extraction gates PASS); handoff covers schema + verifier library only, while loaded/engine/runtime/production remain false and runtime invocation stays Plan19 |
| T6a Contract foundation | [x] | 2026-07-15 | Single typed immutable toolkit RC receipt/manifest + generated contract-only schema; five RED->GREEN focused behaviors cover exact member/evidence matrix, Python/NT policy, immutable coordinates/dependencies, forbidden claims, authority registration and unchanged v1/v2 indexes; no wheel or READY receipt produced |
| T6b Reproducible build inputs | [x] | 2026-07-15 | Dedicated offline build seam archives one exact source commit into two isolated roots; four real base/Nautilus builds are byte-identical and enforce immutable RC/Python/NT/dependency/top-level/SBOM-input policy; outputs remain ephemeral and candidate-only, with no registry, READY receipt, signing or runtime authority |
| T6 Toolkit candidate | [ ] | — | START gate open; Custos-owned immutable base/Nautilus toolkit RC receipt only; PS54 later owns strategy artifact/manifest/full `StrategyReleaseBomV1`; Plan19 runtime invocation and PS56 are not START gates |
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
| SCOPE | Migration | 241-input migration 改为 inventory-backed reviewable batches | Accepted 2026-07-14 |
| LIFECYCLE | Release/spec | StrategyRelease 独立于 DeploymentSpec；command 才聚合 runtime provenance | Accepted 2026-07-14 |
| PACKAGING | Python split | extra-specific Requires-Python 不可安全表达，改为两个 distributions | Accepted 2026-07-14 |
| SECURITY | Config/trust | effective config deep-freeze；trust root 只来自 local signed release config | Accepted 2026-07-14 |
| EXECUTION | Multi-session | 正式拆为 18a-d canonical slices，逐 slice handoff/stop gate | Accepted 2026-07-14 |
| HISTORY | `b898ee1` | 保留为原 plan-first 历史，不再代表有效 schema approval | Recorded |
| DEPENDENCY | Task 2 READY topology | 将 PS Plan 54 final producer receipt 和 Crucible Plan 88 completion 从 Task 2 READY 前置中移除；两者消费 READY schema receipt，Task 2 只要求各仓 exact requirements-review receipt | Accepted 2026-07-15 |
| PROGRESS | 18a implementation baseline | `877a52a` 已落 T1/T2 static assets，但 failure gates、外部 reviews、fresh verification、READY receipt 和 handoff 尚未完成，因此 T1/T2 统一标记 partial | Recorded 2026-07-15 |
| PROVENANCE | Task 2 candidate refresh | 格式化后的 source/index 以 `b36e9edf3ce9d2080e0d77b22ae99a65e32aaaf0` 重新冻结，并由 Crucible `9085d8d...` 与 PS `7f07c09...` exact-byte requirements reviews 重新接受 | Closed 2026-07-15 |
| SCOPE | Task 2 READY ceiling | READY 仅证明 execution ABI/schema/inventory/golden handoff；不证明 toolkit wheel、BOM、OIDC/signing、runtime verifier、Plan 88 completion 或 production readiness | Recorded 2026-07-15 |
| EXECUTION | 18b production-ready boundary | 明确 T3 单独只建立 distribution boundary；只有 T3-T5 整体 DoD PASS 才可声明 18b production-ready | Accepted 2026-07-15 |
| AUTHORITY | T4 canonical move | 241 个 canonical implementations 必须 move 到新 distributions；旧树只能临时保留无实现 shim，并在 T8 删除 | Accepted 2026-07-15 |
| SAFETY | T5 scoped handoff | Exact reviews, implementation and clean full verification advance only schema + production verifier library to `READY_PRE_IMPORT_VERIFIER`; loaded/engine/runtime/production remain false, while Plan19 runtime invocation does not block T6 | Closed 2026-07-15 |
| OWNERSHIP | T6 toolkit RC | Custos publishes only the immutable toolkit RC receipt; PS54 owns strategy artifact/manifest/full `StrategyReleaseBomV1`, PS56 is not a T6 START gate, and the legacy Python lane is unchanged | Accepted 2026-07-15 |

## Slice 18a handoff and Task 2 READY provenance

- Producer candidate and published contract commit: `b36e9edf3ce9d2080e0d77b22ae99a65e32aaaf0`.
- Producer source SHA-256: `71990c6a4613cb738f6a81be0cc393d79f86eeee8b36166974e4581a3ef934c3`.
- Contract asset-index SHA-256: `d87d6fc2df020e92748058c5577863b83dd6f3b2a0c0f59adbf9b9b7822dae07`.
- Crucible requirements review: source commit `9085d8deb8e78cc17a57c20ae244b48ede08799c`, vendored receipt SHA-256 `09bff539edafa818d1f15b866ae3626600ced90f613da68dd4e14a9385935095`.
- Philosophers-Stone requirements review: source commit `7f07c090ce6d6dd4f2e11986680009a61af0934b`, vendored receipt SHA-256 `0a4d48c9bd1849b8a04b9a72ef6fb97942e0f66bc21b6d7916c2d5eb21650319`.
- Clean verification checkout: `f6406ea1e5f9a902f0c9226e3db78eebc88bcd65` at `2026-07-14T17:17:49Z`.
- Fresh evidence: focused Plan 18 suite `52 passed`; generated-asset drift gate PASS; authority gate PASS; `make verify` PASS with fmt/lint and `443 passed, 4 skipped, 1 xfailed, 1 warning`.
- Scope ceiling: Tasks 3-9 remain open. No toolkit wheel, immutable BOM, OIDC/signature, real artifact/runtime verification, Plan 88 completion, consumer cutover, or production-readiness claim is made by this receipt.

## Quantitative Summary

- Production packages: 2 independent distributions with disjoint Python baselines
- Runtime identities: 1 address + 3 provenance/ordering fields
- Canonical execution slices: 4; migration batches inside 18b: at least 4
- Required v1.team receipts: Custos Task 2 schema, PS Plan 54 artifact/BOM, Crucible Plan 88 StrategyRelease acceptance, Custos verifier/runtime; Speculum receipts: 0
- Release integrity: canonical BOM digest plus every member digest; no single candidate digest
- Release stages: immutable RC and independently reverified final
- Out of scope: StrategyRelease, approvals, portfolio risk, capital, settlement
