# 16 - Harden local v0.3.0 consumer readiness

> **Status**: ✅ Completed
> **Created**: 2026-07-12
> **Completed**: 2026-07-12
> **Project**: custos
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Plan 14 ✅, Plan 15 ✅
> **Blocks**: Philosophers-Stone Plan 49
> **Local image contract**: `custos-runner:v0.3.0`
> **Remote release**: Deferred; no Git tag, GHCR push, PyPI publish, or namespace decision in this plan.

## 上下文 (Context)

Plan 14/15 已完成 custos 0.3.0 runtime contract，并通过 dev-only base、Nautilus、
Docker runtime 和 standalone NATS wire 验证。2026-07-12 独立复核重跑得到：

- `make verify-base-clean`: 502 passed / 18 skipped / 1 xfailed
- `make verify-nt`: 566 passed / 4 skipped / 1 xfailed
- Docker runtime: 13 passed
- standalone NATS wire: 1 passed (`running → stopped → running`)

复核仍发现以下下游阻断或质量问题：

1. `DeploymentSpec.provenance_ref.credential_id` 只要求非空，但会进入本地 vault 文件路径。
2. `DeploymentSpec.spec_id` 只要求非空，但会进入 NATS status subject。
3. `deployment validate` 不支持 `--strategy-dir`，导致 live spec 无法通过公共 CLI 在发布前计算 hash 并验证。
4. 当前没有稳定的 `custos-runner:v0.3.0` 本机 build + verify target。
5. `publish-ghcr` job 使用 `needs.build-wheel.outputs.version`，却没有声明 `build-wheel` dependency。
6. README、ops 和 examples 把尚未发布的 GHCR image 描述为可直接拉取。
7. `the-alephain-guild/custos` 与当前 GitHub repository namespace 的最终归属尚未决定。

权威依据：

- `.claude/rules/mandatory-rules.md` §0.1：Key/KEK 不出进程
- `src/custos/cli/validators.py`：安全 ID 规则
- `docs/design/credential_vault.md`：per-key vault 路径
- `docs/design/nats_client.md`：subject contract
- `.claude/rules/verification.md`：artifact identity 与 runtime gate
- Plan 14 close-out：PS 原本等待发布 artifact；本计划把本地已验证 image 设为新的下游门

## 目标 (Goal)

提供经过完整 runtime gate 的本机 `custos-runner:v0.3.0` 镜像，并补齐
DeploymentSpec 边界校验和公共 validate/hash interface，使 PS 可以在不依赖 GHCR、
不派生镜像、不引用 custos 内部模块的前提下开始集成。

## 架构 (Architecture)

本计划不发布远端 artifact。custos 仓库负责：

```text
custos source checkout
  → wheel
  → custos-runner:v0.3.0
  → Docker runtime contracts
  → standalone NATS acceptance
  → local image revision evidence
```

PS 只消费同一本机 Docker daemon 中已通过上述 gate 的 image。

`DeploymentSpec` 的文件路径和 NATS subject 边界统一使用：

```text
^[a-zA-Z0-9_-]{1,64}$
```

live spec 的 hash 由公共 CLI 处理：

```bash
arx-runner deployment validate \
  --spec-file deployment.json \
  --strategy-dir /opt/ps/trend/supertrend/refinement/nautilus
```

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| 本地镜像名 | `custos-runner:v0.3.0` | 不冒充尚未发布的 registry artifact |
| GHCR/PyPI | 递延 | 当前目标是本机 PS 集成，不扩大到外部发布 |
| Git tag | 不创建 | Docker image tag 与 Git release tag 明确分离 |
| 最终 GHCR namespace | 本计划不决定 | 等正式 release plan 统一仓库归属、签名身份和 package namespace |
| `credential_id` | 使用 safe-ID contract | 防 path traversal 和异常 vault 路径 |
| `spec_id` | 使用 safe-ID contract | 防 NATS token 注入和 status subject 漂移 |
| live hash | `deployment validate/publish --strategy-dir` | 下游不导入内部 hash 模块 |
| 本地镜像 revision | build 时写 OCI revision label | PS 可识别镜像来源，而不只看可伪造 tag |
| 兼容层 | 无 | 只支持 0.3.0 clean contract |

## 承载决策 (Capability Hosting Decision)

| 能力 | plan mode? | hook? | CLAUDE.md? | 现有 skill flag? | 新 skill? | 决策 |
|---|---:|---:|---:|---:|---:|---|
| Deployment boundary validation | 否 | 否 | 否 | 否 | 否 | `custos.contracts.DeploymentSpec` |
| validate-time hash | 否 | 否 | 否 | 否 | 否 | `arx-runner deployment validate` |
| 本地镜像构建门 | 否 | 否 | 导航无需变化 | 否 | 否 | Makefile + Docker tests |
| 远端发布递延 | 否 | 否 | 否 | 否 | 否 | ops/release 文档 |

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|---|---|---|
| `src/custos/contracts/deployment.py` | Modify | safe ID 用于 spec/credential/tenant/strategy |
| `src/custos/cli/subcommands/deployment.py` | Modify | validate 支持 `--strategy-dir` |
| `tests/test_deployment_contract.py` | Modify | path/NATS boundary failure modes |
| `tests/test_cli_deployment.py` | Modify | validate-time hash contract |
| `docs/gateway-contract/v1/deployment_spec.schema.json` | Modify | 由 normative model 同步生成 |
| `docs/domain.md` | Modify | DeploymentSpec ID 约束 |
| `docs/design/credential_vault.md` | Modify | provenance ID → vault path contract |
| `docs/design/nats_client.md` | Modify | spec ID → subject token contract |
| `Makefile` | Modify | local image build/verify targets |
| `tests/test_local_image_contract.py` | Create | local image Makefile/metadata contract |
| `tests/test_docker_runtime_contract.py` | Modify | version + OCI revision |
| `.github/workflows/release.yml` | Modify | 修正 publish-ghcr DAG |
| `tests/test_release_workflow_shape.py` | Modify | 锁定 declared dependency |
| `README.md` | Modify | 当前本地 build 路径；远端发布标为 deferred |
| `CHANGELOG.md` | Modify | 区分 0.3.0 code version 与 remote publication |
| `docs/ops/05-deployment.md` | Modify | 本地 image golden path |
| `docs/reproducible-build.md` | Modify | 本地 image revision evidence |
| `docs/upgrade-path.md` | Modify | 当前阶段使用 local image |
| `examples/supertrend-testnet/docker-compose.yaml` | Modify | local tag + `pull_policy: never` |
| `examples/supertrend-testnet/README.md` | Modify | 先执行本地 image gate |
| `tests/test_examples_docs_v020_alignment.py` | Modify | 不再断言不存在的 GHCR artifact |
| `.claude/rules/verification.md` | Modify | 登记 local consumer gate |
| `.forge/plans/2026-07/14-clean-deployment-runtime-contract.md` | Modify | 添加本地 artifact gate amendment |
| `.forge/plans/2026-07/16-local-v030-consumer-readiness.md` | Create | 本计划 |
| `.forge/README.md` | Modify | 登记 Plan 16 |

## 实现任务 (Tasks)

### Task 1: 收紧 DeploymentSpec 边界 ID

**Files**: Modify deployment model、tests、static schema、domain/design docs。

**Step 1 — 写失败测试**:

```python
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spec_id", "../status"),
        ("spec_id", "spec.with.dot"),
        ("spec_id", "x" * 65),
        ("credential_id", "../../age"),
        ("credential_id", "key.with.dot"),
        ("credential_id", "凭证"),
    ],
)
def test_deployment_boundary_ids_reject_unsafe_values(
    field: str,
    value: str,
) -> None:
    raw = _sandbox_spec()
    if field == "credential_id":
        raw["provenance_ref"]["credential_id"] = value
    else:
        raw[field] = value

    with pytest.raises(ValidationError):
        DeploymentSpec.model_validate(raw)
```

正向测试覆盖 `supertrend-sandbox`、`runner_01`、`BTCUSDT`。

**Step 2 — 验证失败**:

```bash
uv run pytest tests/test_deployment_contract.py -v
```

预期：unsafe `spec_id` / `credential_id` 当前被接受。

**Step 3 — 最小实现**:

```python
SafeId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,64}$"),
]

class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential_id: SafeId

class DeploymentSpec(BaseModel):
    spec_id: SafeId
```

`tenant_id` 和 `strategy_id` 复用同一个内部 alias，消除重复边界常量；同步 static schema
以及 domain、vault、NATS 文档。

**Step 4 — 验证通过**:

```bash
uv run pytest \
  tests/test_deployment_contract.py \
  tests/test_gateway_contract_v1_samples.py \
  tests/test_authority_runtime_alignment.py -v
```

**Step 5 — 提交**:

```bash
git commit -m "fix(custos): validate deployment filesystem and subject identifiers"
```

### Task 2: `deployment validate` 支持公共 strategy hash

**Files**: Modify CLI and CLI tests。

**Step 1 — 写失败测试**: live spec 的 `code_hash=None`，传入存在的 strategy directory，
`deployment validate --strategy-dir` 必须返回 0；目录不存在、hash 后仍有未知字段必须返回 1；
原始 JSON 文件不得被修改。

```python
def test_validate_live_spec_accepts_strategy_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "strategy.py").write_text("VALUE = 1\n")
    spec_path = tmp_path / "deployment.json"
    spec_path.write_text(json.dumps(_live_spec(code_hash=None)))

    result = main([
        "deployment", "validate",
        "--spec-file", str(spec_path),
        "--strategy-dir", str(strategy_dir),
    ])

    assert result == 0
    assert "valid DeploymentSpec" in capsys.readouterr().out
```

**Step 2 — 验证失败**:

```bash
uv run pytest tests/test_cli_deployment.py -v
```

**Step 3 — 最小实现**:

```python
def _register_validate(actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser(
        "validate",
        help="Validate a DeploymentSpec without connecting.",
    )
    parser.add_argument("--spec-file", required=True, type=Path)
    parser.add_argument("--strategy-dir", type=Path, default=None)
    parser.set_defaults(action_handler=_validate)

def _validate(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec_file, args.strategy_dir)
    if spec is None:
        return 1
    print(f"valid DeploymentSpec: {spec.spec_id} generation {spec.generation}")
    return 0
```

**Step 4 — 验证通过**:

```bash
uv run pytest tests/test_cli_deployment.py tests/test_deployment_contract.py -v
```

**Step 5 — 提交**:

```bash
git commit -m "feat(custos): validate live specs through the public hash interface"
```

### Task 3: 本机 `custos-runner:v0.3.0` build 与 runtime gate

**Files**: Modify Makefile、Docker runtime tests；Create local image contract test。

**Step 1 — 写失败测试**:

```python
def test_makefile_defines_local_v030_image_contract() -> None:
    text = MAKEFILE.read_text()
    assert "LOCAL_IMAGE ?= custos-runner:v0.3.0" in text
    assert "docker-build-local-v030:" in text
    assert "verify-local-v030:" in text
    assert "org.opencontainers.image.revision" in text
    assert "CUSTOS_TEST_IMAGE=$(LOCAL_IMAGE)" in text
    assert "verify-runtime-existing" in text
```

Docker test 断言 package version 为 `0.3.0`，revision label 为 40 字符 SHA。

**Step 2 — 验证失败**:

```bash
uv run pytest tests/test_local_image_contract.py -v
```

**Step 3 — 最小 Makefile contract**:

```makefile
LOCAL_IMAGE ?= custos-runner:v0.3.0
SOURCE_REVISION := $(shell git rev-parse HEAD)

docker-build-local-v030: dist
	docker build \
		--label org.opencontainers.image.revision=$(SOURCE_REVISION) \
		--tag $(LOCAL_IMAGE) \
		.

verify-local-v030: docker-build-local-v030
	CUSTOS_TEST_IMAGE=$(LOCAL_IMAGE) $(MAKE) verify-runtime-existing
	docker image inspect $(LOCAL_IMAGE) \
		--format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

**2026-07-12 approved amendment**: `docker-build` must inject the same
`org.opencontainers.image.revision=$(SOURCE_REVISION)` label. Otherwise
`verify-runtime` builds `custos-runner:test` and immediately violates the shared Docker runtime
contract that requires a 40-character source revision.

**2026-07-12 self-reflection amendment**: the downstream local-image target must reject a dirty
worktree before Docker build and pass `CUSTOS_EXPECTED_REVISION=$(SOURCE_REVISION)` into the
runtime contract. This prevents uncommitted source from being attributed to an older HEAD and
upgrades revision verification from shape-only to exact equality for the consumer gate.

不创建 `custos-base`，不创建 Git tag，不 push registry。

**Step 4 — 验证通过**:

```bash
make verify-local-v030
```

预期 Docker runtime 13 passed、standalone wire 1 passed、image package version 0.3.0、
revision label 等于当前 source SHA。

**Step 5 — 提交**:

```bash
git commit -m "feat(custos): add verified local v0.3.0 image contract"
```

### Task 4: 修正 release workflow 静态 DAG

**Files**: Modify workflow and shape tests。本任务只修代码质量，不执行发布。

**Step 1 — 写失败测试**:

```python
def test_publish_ghcr_declares_every_needs_output_source() -> None:
    text = WORKFLOW.read_text()
    start = text.index("  publish-ghcr:")
    end = text.index("  verify-release:", start)
    block = text[start:end]
    assert "needs: [build-wheel, build-docker, sign-docker]" in block
    assert "${{ needs.build-wheel.outputs.version }}" in block
```

**Step 2 — 验证失败**:

```bash
uv run pytest tests/test_release_workflow_shape.py -v
```

**Step 3 — 最小实现**:

```yaml
publish-ghcr:
  needs: [build-wheel, build-docker, sign-docker]
```

不创建 tag、不运行 workflow、不决定最终 GHCR namespace。

**Step 4 — 验证通过**:

```bash
uv run pytest tests/test_release_workflow_shape.py -v
make verify
```

**Step 5 — 提交**:

```bash
git commit -m "fix(custos): declare release workflow output dependencies"
```

### Task 5: 对外文档收敛到本地 image truth

**Files**: README、CHANGELOG、ops、upgrade/reproducible docs、examples、Plan 14 amendment、tests。

要求：

1. 当前可执行命令使用 `custos-runner:v0.3.0`。
2. Compose 中 custos service 使用 `image: custos-runner:v0.3.0` 与 `pull_policy: never`。
3. Quick Start 先执行 `make verify-local-v030`。
4. 明确 0.3.0 code/local Docker contract 已完成，signed GitHub/PyPI/GHCR release 递延。
5. Plan 14 添加 amendment：包含 Plan 16 的 verified local image 满足 PS local-development gate。
6. 正式 release follow-up 必须决定 GitHub repo、GHCR namespace、cosign identity、tag
   ownership 与 PyPI trusted publisher identity。

**验证**:

```bash
uv run pytest \
  tests/test_examples_docs_v020_alignment.py \
  tests/test_local_image_contract.py \
  tests/test_release_workflow_shape.py -v

rg -n "custos-runner:v0.3.0|Remote release.*deferred|pull_policy: never" \
  README.md docs examples CHANGELOG.md
```

**提交**:

```bash
git commit -m "docs(custos): make local v0.3.0 the downstream development gate"
```

### Task 6: 文档收尾 (close-out)

1. Plan 16 状态改为 `✅ Completed` 并写完成日期。
2. `.forge/README.md` 更新状态。
3. 记录最终 image ID、revision SHA 和测试矩阵。
4. 记录 PS 最低门为 Plan 16 close-out commit。
5. 明确 remote publication 仍 deferred。
6. 添加完成报告。
7. 独立提交：

```bash
git add \
  .forge/plans/2026-07/16-local-v030-consumer-readiness.md \
  .forge/README.md
git commit -m "docs(custos): mark plan 16 as completed"
```

## 验证清单 (Verification)

- [x] `make verify-base-clean`
- [x] `make install-nt && make verify-nt`
- [x] `make verify-local-v030`
- [x] unsafe `spec_id` / `credential_id` 全部拒绝
- [x] live spec 可通过 `deployment validate --strategy-dir`
- [x] local image version 为 0.3.0
- [x] local image 带当前 source revision
- [x] generic `custos-runner:test` build 同样带 source revision
- [x] local consumer build 拒绝 dirty worktree
- [x] local runtime revision 精确等于当前 HEAD
- [x] Docker runtime 15 项通过
- [x] standalone NATS wire 通过
- [x] docs/examples 不再假定 GHCR v0.3.0 已发布
- [x] workflow DAG 不再读取未声明的 `needs` output
- [x] 不创建 Git tag
- [x] 不 push GitHub/GHCR/PyPI
- [x] Non-Custodial 四红线无新增命中
- [x] worktree clean

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|---|---|---|---|
| T1 Deployment boundary IDs | ✅ | 2026-07-12 | safe ID enforced in model/schema/docs |
| T2 validate-time public hash | ✅ | 2026-07-12 | validate and publish share `_load_spec` hash seam |
| T3 local v0.3.0 image gate | ✅ | 2026-07-12 | dirty tree rejected; consumer runtime revision checked exactly against HEAD |
| T4 release workflow DAG | ✅ | 2026-07-12 | declared `build-wheel` output dependency; no publication |
| T5 local artifact truth docs | ✅ | 2026-07-12 | local tag + pull_policy never; remote release identity decisions deferred |
| T6 close-out | ✅ | 2026-07-12 | final image identity, verification matrix, red-line boundaries, and downstream gate recorded |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|---|---|---|---|
| DECISION | Distribution | 本轮只构建本机 `custos-runner:v0.3.0` | ✅ 用户 2026-07-12 |
| DEFERRED | Remote release | Git tag、GHCR、PyPI、cosign publication 后续单独处理 | ✅ 用户 2026-07-12 |
| DEFERRED | Namespace | 不在本计划决定最终 GitHub/GHCR owner | ✅ 用户 2026-07-12 |
| IMPROVEMENT | Contract validation | spec/vault/NATS 边界统一 safe ID | ✅ Plan 16 T1 |
| IMPROVEMENT | Public CLI | validate 与 publish 共享 strategy hash seam | ✅ Plan 16 T2 |
| IMPROVEMENT | Local provenance | `docker-build` 与 v0.3.0 target 统一注入 source revision | ✅ 用户 2026-07-12 |
| IMPROVEMENT | Exact provenance | local consumer gate 拒绝 dirty tree 并精确校验 revision=HEAD | ✅ 用户 2026-07-12 |

## 完成报告 (Close-out Report)

- **完成日期**: 2026-07-12
- **Task**: 6/6 完成
- **实施提交**: 7 个 atomic commits，`61d2d43` through `89b31a1`
- **变更规模**: 22 个 non-forge files，407 additions / 89 deletions
- **偏离与改进**: 7 项（1 decision + 2 deferred + 4 improvements），无未处理偏离
- **远端发布**: 仍然 deferred；本计划未创建 Git tag，未 push GitHub/GHCR/PyPI，未执行 cosign publication

### 最终本地镜像身份

| 字段 | 值 |
|---|---|
| Image | `custos-runner:v0.3.0` |
| Image ID | `sha256:b47ff765ed1c49cc982b5b93650e40fa84953e5d37b80dee1bbccdb2f89111bf` |
| OCI source revision | `89b31a163df83fd3959f4c8ccfa2c956e294a7ef` |
| Revision contract | build 拒绝 dirty worktree，runtime 精确校验 label = source HEAD |

### 最终验证矩阵

| Gate | 结果 |
|---|---|
| Dev-only base (`make verify-base-clean`) | 506 passed / 34 skipped / 1 xfailed |
| Nautilus (`make install-nt && make verify-nt`) | 570 passed / 20 skipped / 1 xfailed |
| Docker runtime contracts | 15 passed |
| Standalone NATS acceptance | 1 passed; `running → stopped → running` |
| Docs / local image / workflow focused contracts | 43 passed |
| Compose rendering | passed |

Base/NT 跳过数包含当前执行环境不可见的 Docker 用例；同一源码 revision
已在可访问 Docker socket 的本地会话中通过独立 15 + 1 runtime gates。

### Non-Custodial 红线边界

| Red line | Code coverage | Runtime wire | Deferred status | Follow-up |
|---|---|---|---|---|
| Key/KEK 不出进程 | vault 边界与 safe credential ID 覆盖 | official local image 通过 vault toolchain/runtime contract | 无 | 无 |
| G6 不可绕过 | 既有 host/gate suites 保持通过 | local image 中 Nautilus runtime 通过 | external live session 不在本计划 | 由 operator live acceptance 承接 |
| 失联即停止 | 既有 reconciler/chaos/retry suites 保持通过 | standalone NATS `running → stopped → running` 通过 | 无 | 无 |
| Money math 不用 float | 既有 telemetry/money contracts 保持通过 | 本计划未新增 money wire | 无 | 无 |

红线扫描无新增命中。仅有 5 处未改动的 vendored OHLCV warmup float，不属于
money-wire contract。

### 失败模式与自省

已覆盖 unsafe deployment IDs、缺失 strategy directory、unknown live-spec field、未声明
workflow dependency、本地/远端文档漂移、generic image 缺失 revision，以及 dirty
worktree 误标旧 HEAD 的 provenance 风险。

- Self-reflect round 1 审查 22 个 non-forge files，发现 dirty worktree 可能生成错误
  provenance；已由 `89b31a1` 修复并增加回归契约。
- Self-reflect round 2 未发现新问题，`git diff --check` 通过。

### 下游最低门槛

Philosophers-Stone 本地开发必须使用本 Plan 16 close-out commit 或之后的 custos
checkout，并消费 source revision 为 `89b31a163df83fd3959f4c8ccfa2c956e294a7ef`
的已验证本地 image。正式 GitHub/GHCR/PyPI/cosign 发布与 namespace identity
决策仍属后续 release plan。

---

*Drafter: Codex @ 2026-07-12*
