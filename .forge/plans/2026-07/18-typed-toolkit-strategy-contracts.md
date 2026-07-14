# 18 - Publish typed toolkit and strategy contracts

> **Status**: ⏳ In progress
> **Created**: 2026-07-14
> **Project**: Custos
> **Source**: PS Plan 53 strategy/toolkit convergence roadmap
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Custos baseline `324da6e`; approved PS Plan 53 amendment
> **Soft depends on**: PS Plan 54, Speculum Plan 01, Custos Plan 19 consumer receipts

## 上下文 (Context)

Custos 当前仍把公共策略实现放在：

```text
src/custos/engines/nautilus/toolkit/
├── shared/             160 files
└── vendor/pandas_ta/   299 files
```

当前问题：

- `toolkit/__init__.py` 修改 `sys.path`，暴露顶层 `shared.*`。
- 它还注册伪造的 `pkg_resources` distribution。
- vendored pandas-ta 暴露顶层 `pandas_ta`。
- Toolkit 与 `custos-runner` wheel、runner lifecycle 和控制面耦合。
- PS 与 Custos 存在公共实现权威漂移。
- Speculum 通过 sibling PS checkout 动态导入策略。
- Custos 使用 NT 1.230.0，PS 1.228.0，Speculum 1.221/1.222。
- PS `shared/` mypy 问题已经正式递延给 PS Plan 54；本计划不得通过 blanket ignore
  制造假绿。

权威参考：

- PS Plan 53
- Custos `TOOLKIT_PROVENANCE.md`
- Custos Plans 06/07/17
- `.claude/rules/mandatory-rules.md`
- `.claude/rules/verification.md`
- `.claude/rules/historical-lessons.md`

## 目标 (Goal)

发布独立、typed、不可变的 `custos-strategy-toolkit` distribution，并冻结
`StrategyManifestV1`、`StrategyArtifactRefV1` 和 `StrategyRuntimeV1`，供 Custos、
Philosophers-Stone 与 Speculum 使用。

## 架构 (Architecture)

```text
packages/custos-strategy-toolkit/
└── src/custos_toolkit/
    ├── contracts/       # lightweight Pydantic models + JSON Schema
    ├── strategy/        # runtime protocol and entry-point loader
    ├── config/
    ├── filters/
    ├── indicators/
    ├── risk/
    ├── nautilus/        # NT-specific implementation
    └── _vendor/
        └── pandas_ta/   # private implementation detail

PS strategy wheel ──depends──> custos-strategy-toolkit
Speculum backend  ──depends──> contracts/toolkit wheel
Custos runner     ──depends──> toolkit wheel
```

Contracts import 不得加载 NautilusTrader、修改 `sys.path` 或执行策略代码。

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| Distribution | `custos-strategy-toolkit` | Consumer 不安装完整 runner |
| Import namespace | `custos_toolkit.*` | 消除裸 `shared` 冲突 |
| Python | `>=3.12` | 与目标运行栈一致 |
| NautilusTrader | exact `1.230.0` | 当前 Custos 已安装且行为已核验 |
| Candidate | `0.1.0rc1` | 供三仓验收 |
| Final | `0.1.0` | receipt 后重新构建发布 |
| Catalog identity | `strategy_key` SafeId | 不复用 Crucible UUID `strategy_id` |
| Manifest | wheel 内无 digest | 避免自引用 |
| ArtifactRef | wheel 外 detached sidecar | 绑定 wheel、manifest、runtime artifacts |
| Source hash | optional | 只用于 source-path execution |
| Runtime discovery | fixed entry-point group | 禁止任意 import string |
| pandas-ta | `custos_toolkit._vendor.pandas_ta` | 不暴露第二个顶层包 |
| Hummingbot glue | PS-owned | 不污染 Nautilus toolkit |
| Compatibility | 静态 re-export，禁止 path mutation | 支持受控迁移 |
| Typing | package strict mypy=0 + `py.typed` | 不继承 PS 当前 mypy 债务 |
| Release | source SHA + wheel SHA + Sigstore | candidate/final 都不可覆盖 |

## 冻结接口

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

SafeId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StrategyDisplayV1(StrictModel):
    name: str
    description: str
    category: SafeId
    tags: tuple[SafeId, ...] = ()


class ToolkitRequirementV1(StrictModel):
    interface: Literal["custos_toolkit.strategy.v1"]
    distribution: Literal["custos-strategy-toolkit"]
    version: str


class EngineRuntimeV1(StrictModel):
    entry_point: SafeId
    python_requires: str
    runtime_requires: tuple[str, ...]
    config_schema: dict[str, object]
    default_config: dict[str, object]


class StrategyManifestV1(StrictModel):
    schema_: Literal["urn:alephain:strategy-manifest:v1"] = Field(alias="$schema")
    schema_version: Literal[1]
    strategy_key: SafeId
    strategy_version: str
    display: StrategyDisplayV1
    toolkit: ToolkitRequirementV1
    engines: dict[SafeId, EngineRuntimeV1]


class ArtifactPayloadV1(StrictModel):
    distribution: SafeId
    version: str
    filename: str
    media_type: Literal["application/vnd.python.wheel"]
    sha256: Sha256Hex
    size_bytes: Annotated[int, Field(gt=0)]
    manifest_path: str
    manifest_sha256: Sha256Hex
    payload_root: str
    source_code_hash: Sha256Hex | None = None


class RuntimeArtifactV1(StrictModel):
    role: SafeId
    distribution: SafeId
    version: str
    filename: str
    sha256: Sha256Hex


class StrategyArtifactRefV1(StrictModel):
    schema_: Literal["urn:alephain:strategy-artifact-ref:v1"] = Field(alias="$schema")
    schema_version: Literal[1]
    artifact: ArtifactPayloadV1
    runtime_artifacts: tuple[RuntimeArtifactV1, ...]


class StrategyExecutionContextV1(StrictModel):
    engine: Literal["nautilus"]
    trading_mode: Literal["sandbox", "testnet", "live"]
    deployment_id: str
    strategy_key: SafeId


class StrategyRuntimeV1(Protocol):
    strategy_class: type

    def build_config(
        self,
        effective_config: Mapping[str, object],
        execution_context: StrategyExecutionContextV1,
    ) -> object: ...
```

固定 entry-point group：

```text
alephain.strategy_runtime.v1
```

`StrategyExecutionContextV1` 不宣称提供安全边界。真正的 runner-wide order enforcement
属于 Custos Plan 19。

## 承载决策 (Capability Hosting Decision)

| 能力 | plan mode? | hook? | CLAUDE.md? | 现有 skill flag? | 新 skill? | 决策 |
|---|---:|---:|---:|---:|---:|---|
| Typed toolkit | 否 | 否 | 否 | 否 | 否 | 独立 Python distribution |
| Manifest/ArtifactRef | 否 | 否 | 否 | 否 | 否 | `custos_toolkit.contracts` |
| Runtime discovery | 否 | 否 | 否 | 否 | 否 | fixed entry-point API |
| Namespace/release gates | 否 | CI 二次 gate | 否 | 否 | 否 | pytest + release workflow |

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `.forge/plans/2026-07/18-typed-toolkit-strategy-contracts.md` | 新增 | 本计划 |
| `.forge/README.md` | 修改 | 登记 Plan 18 |
| `pyproject.toml` | 修改 | uv workspace、开发依赖 |
| `uv.lock` | 修改 | 锁 toolkit/NT 依赖 |
| `packages/custos-strategy-toolkit/pyproject.toml` | 新增 | 独立 distribution |
| `packages/custos-strategy-toolkit/src/custos_toolkit/**` | 新增/迁移 | Canonical toolkit |
| `packages/custos-strategy-toolkit/src/custos_toolkit/py.typed` | 新增 | PEP 561 |
| `packages/custos-strategy-toolkit/tests/**` | 新增 | Unit/type/contract tests |
| `src/custos/engines/nautilus/toolkit/**` | 迁移/最终删除 | 移除旧 vendored authority |
| `tests/test_toolkit_distribution.py` | 新增 | Wheel/namespace/import gate |
| `tests/test_toolkit_consumer_receipts.py` | 新增 | Exact downstream receipts |
| `.github/workflows/release-toolkit.yml` | 新增 | Candidate/final build/sign |
| `docs/design/strategy-toolkit.md` | 新增 | 权威边界 |
| `CHANGELOG.md` | 修改 | Toolkit release notes |

## 实现任务 (Tasks)

### Task 0: Plan-first

**Files**: 本计划、`.forge/README.md`。

1. 写入本计划并更新索引为 ⏳。
2. 确认只 stage 计划和索引。
3. 提交：

```bash
git commit -m "plan(custos): 18 — typed toolkit and strategy contracts"
```

### Task 1: 冻结 migration inventory 与边界

**Files**: `docs/design/strategy-toolkit.md`、migration inventory、
`tests/test_toolkit_distribution.py`。

1. 写失败测试，要求每个旧 toolkit 文件都有目标分类，且 Hummingbot glue、PS strategy
   source 不进入 toolkit。
2. 要求 `shared`、`pandas_ta` 不得成为最终顶层包，canonical source 只能位于新 package。
3. 运行并确认失败：

```bash
uv run pytest tests/test_toolkit_distribution.py -v
```

4. 写权威边界文档和 machine-readable inventory。
5. 重跑通过并提交：

```bash
git commit -m "docs(toolkit): freeze extraction boundaries"
```

### Task 2: 建立 uv workspace 和最小 wheel

**Files**: root/package `pyproject.toml`、`uv.lock`、package skeleton、distribution test。

1. 写失败测试：

```python
def test_contract_import_is_lightweight() -> None:
    before = tuple(sys.path)
    import custos_toolkit.contracts  # noqa: PLC0415
    assert tuple(sys.path) == before
    assert "nautilus_trader" not in sys.modules
```

2. 创建独立 distribution，Python `>=3.12`，基础 contracts 不依赖 NT；
   `nautilus` extra 精确锁定 `nautilus-trader==1.230.0`，添加 `py.typed`。
3. 验证：

```bash
uv build --package custos-strategy-toolkit
uv run pytest tests/test_toolkit_distribution.py -v
```

4. 提交：

```bash
git commit -m "build(toolkit): create typed workspace distribution"
```

### Task 3: 实现 StrategyManifestV1

**Files**: contracts models/schema/tests。

1. 写失败测试覆盖 `strategy_key` SafeId、unknown fields、UUID identity 分离、
   schema/model round-trip 和 discovery 不执行 entry point。
2. 实现冻结接口并导出 JSON Schema。
3. 验证：

```bash
uv run pytest packages/custos-strategy-toolkit/tests/test_manifest.py -v
```

4. 提交：

```bash
git commit -m "feat(toolkit): add strategy manifest v1"
```

### Task 4: 实现 StrategyArtifactRefV1 和 verifier

**Files**: artifact models/verifier/schema/tests。

1. 写失败测试覆盖 attestation-before-unpack、size/SHA mismatch、absolute path、`..`、
   symlink escape、manifest digest、runtime digest 和 source-mode hash requirement。
2. 实现 detached ArtifactRef；禁止自包含 digest/signature。
3. 验证：

```bash
uv run pytest packages/custos-strategy-toolkit/tests/test_artifact_ref.py -v
```

4. 提交：

```bash
git commit -m "feat(toolkit): verify detached strategy artifacts"
```

### Task 5: 实现 StrategyRuntimeV1 与固定 entry-point loader

**Files**: strategy protocol/loader/tests。

1. 写失败测试，要求只接受 `alephain.strategy_runtime.v1`，entry point 属于已验证
   distribution，拒绝 name hijack，discovery 不 load，import 前后 `sys.path` 不变。
2. 实现最小 protocol 和 loader。
3. 验证：

```bash
uv run pytest packages/custos-strategy-toolkit/tests/test_runtime_entrypoint.py -v
```

4. 提交：

```bash
git commit -m "feat(toolkit): define strategy runtime v1"
```

### Task 6: 迁移 platform-neutral 模块

**Files**: config/protocols/signals/warmup/position modules、compatibility tests。

1. 建立 public-symbol identity tests。
2. 使用 `git mv` 迁入 `custos_toolkit.*`。
3. 旧路径只保留静态 compatibility import：不复制实现、不修改 `sys.path`、不注册伪
   distribution，并发出 deprecation warning。
4. 验证 `old_symbol is new_symbol`。
5. 提交：

```bash
git commit -m "refactor(toolkit): move platform-neutral strategy modules"
```

### Task 7: 迁移 filters、indicators 与 risk domain

**Files**: filters/indicators/sizing/risk/equity/order modules and tests。

1. 为 public symbols 建 behavior characterization tests。
2. 迁移实现，禁止带入 runner lifecycle、vault、NATS 或 Hummingbot glue。
3. 运行 package tests 和 root no-regression tests。
4. 提交：

```bash
git commit -m "refactor(toolkit): migrate strategy risk and indicator modules"
```

### Task 8: 迁移 Nautilus-specific toolkit

**Files**: Nautilus config/coordinators/registry/strategy base/execution helpers。

1. 为 NT 1.230.0 API 建 characterization tests。
2. 迁移实现；contracts-only import 仍不得加载 NT。
3. 禁止把 Custos daemon/reconciler 放入 toolkit。
4. 验证：

```bash
uv run --extra nautilus pytest packages/custos-strategy-toolkit/tests/nautilus -v
```

5. 提交：

```bash
git commit -m "refactor(toolkit): migrate Nautilus strategy runtime"
```

### Task 9: 私有化 pandas-ta vendor

**Files**: `custos_toolkit/_vendor/pandas_ta/**`、license/provenance、tests。

1. 写 wheel-content 和 indicator parity 失败测试。
2. 迁移并重写所有 vendor absolute imports。
3. 删除顶层 `pandas_ta` 暴露，保留 license/provenance。
4. 验证常用 indicators 与迁移前输出一致，wheel 无顶层 `pandas_ta/__init__.py`。
5. 提交：

```bash
git commit -m "refactor(toolkit): namespace private pandas-ta vendor"
```

### Task 10: 建立 strict typing 与 packaging gates

**Files**: typing config、distribution tests、CI。

1. 新增 clean-venv wheel-only gate，验证 `py.typed`、无顶层 `shared`/`pandas_ta`、
   无 sibling checkout、import 不修改 `sys.path`。
2. 运行：

```bash
uv run ruff check packages/custos-strategy-toolkit
uv run ruff format --check packages/custos-strategy-toolkit
uv run mypy --strict \
  packages/custos-strategy-toolkit/src \
  packages/custos-strategy-toolkit/tests
uv build --package custos-strategy-toolkit
uv run pytest tests/test_toolkit_distribution.py -v
```

3. 所有 gate 必须真实 PASS，不加 blanket waiver。
4. 提交：

```bash
git commit -m "test(toolkit): gate typing and wheel isolation"
```

### Task 11: 发布不可变 0.1.0rc1

**Files**: `.github/workflows/release-toolkit.yml`、release tests、CHANGELOG。

1. 写失败 contract tests，要求 reproducible wheel、SHA256SUMS、Sigstore bundle、source
   SHA、Python 3.12、NT 1.230.0 和 schema hashes。
2. 实现 dedicated workflow；candidate 不可覆盖。
3. 本地验证：

```bash
uv build --package custos-strategy-toolkit
uv run pytest tests/test_toolkit_release_contract.py -v
```

4. 提交：

```bash
git commit -m "build(toolkit): publish immutable release candidate"
```

### Task 12: 收集三方 candidate receipts

**Files**: receipt fixtures/tests。

Receipt 必须记录 toolkit version、Custos source commit、wheel SHA、Sigstore bundle SHA、
Python、NT、consumer repo/commit 和 PASS command。

强制 consumer：

- PS Plan 54：artifact build + strategy runtime。
- Speculum Plan 01：manifest discovery + real backtest + Docker。
- Custos Plan 19：runner integration。

任一新 RC 使旧 receipts 全部失效。验证 exact match 后提交：

```bash
git commit -m "docs(toolkit): record candidate consumer receipts"
```

### Task 13: 切换 runner 并发布 0.1.0

**Files**: Custos runner dependency/imports、旧 toolkit tree、release metadata。

仅在三方 receipts 通过后：

1. Runner 锁 toolkit final。
2. 删除旧 `src/custos/engines/nautilus/toolkit/` compatibility tree。
3. 删除 sys.path/pkg_resources hacks。
4. 重新构建 final，不复用 RC wheel。
5. 重跑 clean-wheel、NT 和 consumer gates并发布新签名。
6. 提交：

```bash
git commit -m "release(toolkit): publish 0.1.0"
```

### Task 14: 文档收尾 (close-out)

**Files**: 本计划、`.forge/README.md`、ROADMAP（若有）、完成报告。

1. Plan 状态改为 ✅ Completed 并填写日期。
2. 更新索引；ROADMAP 无对应项则记录 N/A。
3. 完成报告记录 candidate/final SHA、三方 receipts、删除的 compatibility path。
4. 验证没有 blanket typing waiver。
5. 提交：

```bash
git add .forge/plans/2026-07/18-typed-toolkit-strategy-contracts.md .forge/README.md
git commit -m "docs(custos): mark plan 18 as completed"
```

## 验证清单 (Verification)

- [ ] Toolkit strict mypy：0 errors
- [ ] Toolkit ruff check/format：PASS
- [ ] Toolkit unit tests：PASS
- [ ] `py.typed` 存在
- [ ] Python exact baseline：3.12
- [ ] NautilusTrader exact baseline：1.230.0
- [ ] wheel 无顶层 `shared`
- [ ] wheel 无顶层 `pandas_ta`
- [ ] contracts import 不加载 NT
- [ ] import 不改变 `sys.path`
- [ ] Manifest discovery 不执行策略 Python
- [ ] Artifact validation fail closed
- [ ] RC/final 均有 source SHA、wheel SHA、signature
- [ ] PS/Speculum/Custos 三方 receipts
- [ ] Final 重新构建和重测
- [ ] `make verify`：PASS
- [ ] `make verify-nt`：PASS

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|---|---|---|---|
| T0 Plan-first | [x] | 2026-07-14 | plan-first commit containing this plan |
| T1 Boundary inventory | [ ] | — | |
| T2 Workspace distribution | [ ] | — | |
| T3 ManifestV1 | [ ] | — | |
| T4 ArtifactRefV1 | [ ] | — | |
| T5 RuntimeV1 | [ ] | — | |
| T6 Neutral modules | [ ] | — | |
| T7 Risk/indicator modules | [ ] | — | |
| T8 Nautilus runtime | [ ] | — | |
| T9 pandas-ta vendor | [ ] | — | |
| T10 Type/wheel gates | [ ] | — | |
| T11 Candidate | [ ] | — | |
| T12 Consumer receipts | [ ] | — | |
| T13 Final/cutover | [ ] | — | |
| T14 Close-out | [ ] | — | |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|---|---|---|---|
| ARCHITECTURE | Distribution | Toolkit 从 runner wheel 拆为独立 distribution | Yes, 2026-07-14 |
| BREAKING | Namespace | `shared.*` → `custos_toolkit.*` | Yes, 2026-07-14 |
| COMPATIBILITY | Old toolkit path | 临时静态 re-export，receipts 后删除 | Yes, 2026-07-14 |
| VERSION | NautilusTrader | 三仓目标锁定 1.230.0 | Yes, 2026-07-14 |
| OUT-OF-SCOPE | Hummingbot | 继续由 PS Plan 54 拥有 | N/A |
| OUT-OF-SCOPE | Runner safety | 由 Custos Plan 19 实现 | N/A |
