# 14 — Clean deployment runtime contract for downstream strategy repositories

> **Status**: ⏳ In Progress
> **Created**: 2026-07-11
> **Project**: custos
> **For Claude**: Use `/forge:execute` to implement this plan.
> **Depends on**: Plan 13 ✅ Completed (`a099a63`)
> **Blocks**: philosophers-stone Plan 49 `.forge/plans/2026-07/01-custos-deploy-target.md`
> **Release target**: `custos-runner 0.3.0` / `ghcr.io/the-alephain-guild/custos:v0.3.0`

---

## 上下文 (Context)

Plan 13 已完成 permission-scope、sandbox runner identity、gateway samples 和示例 CLI
刷新，但下游部署审计仍发现以下上游缺口：

1. 官方 Docker 镜像只安装 base wheel，不含 NautilusTrader、PyYAML、sops、age。
2. Docker `ENTRYPOINT ["arx-runner", "start"]` 导致管理命令必须覆盖 entrypoint。
3. DeploymentSpec informative schema 没有形成真实 consumer runtime contract。
4. 下游必须理解内部 hash 模块、NATS subject 和 envelope。
5. standalone NATS 只启用 JetStream，没有创建 stream。
6. reconciler 初次 subscribe 失败后直接退出，与文档声明的退避重试不一致。
7. runner 没有可供编排方等待的 subscription readiness。
8. `--engine nautilus` 与 `--use-nt-host` 存在双重选择语义；当前只有后者实际启用
   NT host。
9. Plan 13 testnet 示例依赖专用派生 Dockerfile，与“下游消费干净 custos”目标冲突。
10. `make install` 只同步 dev extra，会移除 nautilus extra；base `make verify` 中
    `test_toolkit_import_bootstrap_resolves_shared_and_pandas_ta` 仍无条件导入 `pandas_ta`，
    因 dev 环境没有 `pkg_resources` 而失败，违反独立 clone 的轻量 base 验证契约。

权威依据：

- `.claude/rules/mandatory-rules.md` §0：Non-Custodial 四红线
- `.claude/rules/tech-stack.md`：base wheel 与 `nautilus` extra
- `docs/design/nats_client.md`：subject 与 envelope
- `docs/design/reconcile.md`：失联不停止、subscribe 退避重试
- `docs/design/nautilus_host.md`：NT host 与 G6 gate
- `docs/design/credential_vault.md`：sops+age runtime
- `docs/domain.md`：DeploymentSpec、Runner、engine lifecycle
- `docs/ops/05-deployment.md`：官方 Docker 部署入口

**Foundation Scan as-of**: `a099a63` (Plan 13 close-out, 2026-07-11)。

## 目标 (Goal)

发布一个单一、完整、开箱即用的 custos 0.3.0 官方镜像，恢复干净 dev-only 安装的
base verification contract，并提供稳定的
DeploymentSpec、NATS bootstrap、publication 与 readiness interface，使 PS 等下游仓库
只负责生成策略配置，不再实现 custos runtime 兼容层。

## 架构 (Architecture)

### 1. 单一完整官方镜像

只发布：

```text
ghcr.io/the-alephain-guild/custos:v0.3.0
ghcr.io/the-alephain-guild/custos:latest
```

镜像包含：

- `custos-runner[nautilus]`
- NautilusTrader
- PyYAML
- sops
- age
- 非 root runtime
- `ENTRYPOINT ["arx-runner"]`
- `CMD ["start"]`

Python wheel 仍保留 base/optional-extra 结构；只有官方 Docker 固定为完整生产 runtime。
不发布 `custos-base`，不保留旧 Docker entrypoint 兼容层，不要求下游派生镜像。

### 2. Deployment contract 深模块

新增 `custos.contracts.deployment`，把 spec 校验、strategy hash、subject、envelope 与
consumer parse 收进一个小 interface：

```python
from custos.contracts import DeploymentMessage, DeploymentSpec

spec = DeploymentSpec.model_validate(raw_spec)
message = DeploymentMessage.create(
    tenant_id="acme",
    strategy_id="supertrend-sandbox",
    spec=spec,
)
await publish(message.subject, message.to_bytes())
```

reconciler 与下游 publisher 使用同一 interface，避免 producer/consumer 双重实现。

### 3. 显式 standalone NATS bootstrap

新增：

```bash
arx-runner nats bootstrap \
  --profile standalone \
  --nats-url nats://nats:4222 \
  --tenant-id acme
```

该命令等待 NATS 可达、幂等创建 custos-owned streams、不删除未知 stream，且不由
`arx-runner start` 隐式调用。Production arx 可继续自行管理基础设施；standalone/PS
compose 显式把 bootstrap 作为一次性 init service。

### 4. Subscription readiness

`arx-runner start` 新增：

```bash
--ready-file ~/.arx/state/runner-ready.json
```

runner 只有在 NATS 已连接，且启用 reconciler 时 DeploymentSpec subscription 已成功建立
后才写入 ready file。新增 `arx-runner health --ready-file ...`，供 Docker/Compose/systemd
编排消费，不再依赖固定 sleep。

### 5. Clean-break engine selection

0.3.0 删除 `--use-nt-host`：

```text
--engine nautilus  → NtTradingNodeHost
--engine noop      → NoopHost
```

官方镜像默认 `--engine nautilus`。NoopHost 仅供明确指定的 sandbox/dev contract test。

### 6. Base-only verification contract

`make install` 后的 dev-only 环境必须能直接运行 `make verify`。vendored toolkit bootstrap
测试拆成两层：shared path/bootstrap 属 base contract，始终运行；`pandas_ta` 真导入属于
nautilus runtime contract，仅在 `nautilus_trader` 可导入时运行，并由 `make verify-nt`
强制覆盖。不得为让 base test 假绿而把 setuptools、pandas 或 NautilusTrader 塞入 dev
extra。

新增 `make verify-base-clean`，固定执行 `uv sync --extra dev` 后再运行 `make verify`；release
workflow 必须先过这个门，再 `make install-nt` + `make verify-nt`，证明 base 与 NT 两种安装
形态都真实可用。

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|---|---|---|
| 官方镜像数量 | 单一完整镜像 | 消除“镜像存在但核心 runtime 不可用”的能力歧义 |
| 版本 | `0.3.0` | Docker entrypoint、engine selection 与 consumer contract 是 clean break |
| wheel 依赖 | 保留 `[nautilus]` extra | audit-only Python 用户仍可轻量安装 |
| Docker 依赖 | 固定安装 `[nautilus]` + sops + age | 官方镜像必须开箱即用 |
| base 验证 | dev-only 保持轻量；拆分 toolkit bootstrap 测试 | 修复 `make install` 后失败，不用重依赖掩盖测试边界错误 |
| DeploymentSpec | Pydantic strict consumer model | runtime、schema、publisher 使用同一真理源 |
| 未知 spec 字段 | `extra="forbid"` | clean contract 下拒绝拼写错误；扩展走 schema minor |
| generation | `>= 1` | generation 0 与 reconciler 初始状态冲突 |
| lifecycle | `running/paused/stopped/archived` | 与 trading mode 分离 |
| live 风控判断 | 使用 `trading_mode == "live"` | 修复当前把 lifecycle 当 mode 的语义错误 |
| strategy config | interface 明确定义 `strategy_config` | custos 不理解具体字段，但必须稳定传给 factory |
| registry name | optional contract field | registry-backed strategy 显式使用 |
| envelope | `DeploymentMessage` 统一生成/解析 | 下游不手写半个 envelope |
| deployment envelope payload | `{strategy_id, spec}` wrapper | `parse(bytes, expected_tenant_id)` 必须能从 bytes 恢复 canonical subject；`DeploymentSpec` 保持纯净且 `extra="forbid"` |
| code hash | 从 contracts 公共 seam 导出 | 下游不引用 engine 内部模块 |
| stream 创建 | 显式 bootstrap 命令 | production runner 不应擅自变更控制面基础设施 |
| readiness | 原子 JSON file + health CLI | Compose/systemd/Kubernetes 都能消费 |
| subscribe 失败 | 无限退避重试，stop 可中断 | 与失联不停止红线一致 |
| 过渡兼容 | 无 | PS 只在 0.3.0 完成后开始实施 |

## 承载决策 (Capability Hosting Decision)

| 能力 | plan mode? | hook? | CLAUDE.md? | 现有 skill flag? | 新 skill? | 决策 |
|---|---:|---:|---:|---:|---:|---|
| Deployment contract | 否 | 否 | 导航更新 | 否 | 否 | `custos.contracts` 深模块 |
| standalone stream bootstrap | 否 | 否 | 导航更新 | 否 | 否 | CLI + core module |
| readiness | 否 | 否 | 导航更新 | 否 | 否 | runtime module + health CLI |
| 完整镜像 | 否 | 否 | 导航更新 | 否 | 否 | Docker/release pipeline |

这些都是生产 runtime 能力，不能由文档、hook 或 skill 承载。

## 文件清单 (File Inventory)

### 新增

| 文件 | 描述 |
|---|---|
| `src/custos/contracts/__init__.py` | 公共 deployment interface 导出 |
| `src/custos/contracts/deployment.py` | DeploymentSpec、DeploymentMessage、hash wrapper |
| `src/custos/core/standalone_nats.py` | standalone stream topology 与幂等 bootstrap |
| `src/custos/core/readiness.py` | 原子 ready-state 写入、清理、检查 |
| `src/custos/cli/subcommands/deployment.py` | `deployment validate/publish` |
| `src/custos/cli/subcommands/nats.py` | `nats bootstrap` |
| `src/custos/cli/subcommands/health.py` | readiness health probe |
| `tests/test_deployment_contract.py` | spec/message/consumer contract |
| `tests/test_cli_deployment.py` | validate/publish CLI |
| `tests/test_standalone_nats.py` | stream topology/idempotency/failure modes |
| `tests/test_reconciler_readiness.py` | retry/readiness transitions |
| `tests/test_docker_runtime_contract.py` | NT/YAML/sops/age/CLI image contract |
| `tests/integration/test_standalone_runtime.py` | hermetic NATS→bootstrap→subscribe→publish |
| `.forge/plans/2026-07/14-clean-deployment-runtime-contract.md` | 本计划 |

### 修改

| 文件 | 描述 |
|---|---|
| `src/custos/cli/subcommands/__init__.py` | 注册 deployment/nats/health |
| `src/custos/cli/subcommands/start.py` | engine clean break + ready-file |
| `src/custos/cli/_daemon.py` | 正确 engine 选择与 readiness composition |
| `src/custos/core/deployment_reconciler.py` | message parse、subscribe retry、readiness、live mode 修复 |
| `Dockerfile` | 完整 runtime、sops/age、ENTRYPOINT/CMD、healthcheck |
| `Makefile` | runtime/standalone targets + `verify-base-clean` dev-only 安装门 |
| `pyproject.toml` | 版本 0.3.0 |
| `uv.lock` | 版本与依赖 metadata |
| `.github/workflows/release.yml` | dev-only base gate + 完整 image contract gate |
| `.github/workflows/scripts/verify-release.sh` | post-publish runtime 验证 |
| `tests/test_cli_start.py` | engine/ready-file clean break |
| `tests/test_docker_entrypoint_help.py` | 新 entrypoint command matrix |
| `tests/test_docker_image_size.py` | NT runtime 后重新锁定合理上限 |
| `tests/engines/nautilus/test_toolkit_provenance.py` | 拆分 base shared bootstrap 与 nautilus-only pandas_ta import contract |
| `tests/test_examples_docs_v020_alignment.py` | 升级为 v0.3.0 runtime alignment |
| `docs/gateway-contract/v1/deployment_spec.schema.json` | 从 model 生成并锁定 consumer contract |
| `docs/gateway-contract/v1/samples/deployment_spec_sandbox.json` | 加 strategy_config/registry 示例 |
| `docs/gateway-contract/v1/README.md` | normative consumer contract 说明 |
| `docs/design/nats_client.md` | DeploymentMessage 与 standalone topology |
| `docs/design/reconcile.md` | retry/readiness 契约 |
| `docs/design/nautilus_host.md` | engine selection clean break |
| `docs/domain.md` | mode × lifecycle 真值表 |
| `docs/ops/05-deployment.md` | 0.3.0 Docker/CLI runbook |
| `README.md` | 单一官方镜像 golden path |
| `CHANGELOG.md` | 0.3.0 breaking upgrade notes |
| `examples/supertrend-sandbox/README.md` | 公共 contract 与 bootstrap 流程 |
| `examples/supertrend-sandbox/spec-example.json` | 完整 consumer shape |
| `examples/supertrend-testnet/docker-compose.yaml` | 官方镜像 + bootstrap/init + readiness |
| `examples/supertrend-testnet/README.md` | 删除派生镜像步骤 |
| `examples/supertrend-testnet/spec-example.json` | 0.3.0 contract |
| `.forge/README.md` | Plan 14 索引 |

### 删除

| 文件 | 理由 |
|---|---|
| `examples/supertrend-testnet/Dockerfile` | 官方镜像已完整，不允许示例保留派生 runtime |

## 实现任务 (Tasks)

### Task 1: DeploymentSpec strict consumer contract

**Files**: Create `src/custos/contracts/{__init__,deployment}.py`,
`tests/test_deployment_contract.py`; modify gateway schema/sample、reconciler、domain docs。

**Step 1 — 写失败测试**:

```python
def test_generation_starts_at_one(): ...
def test_lifecycle_vocab_is_closed(): ...
def test_live_requires_code_hash(): ...
def test_unknown_top_level_field_is_rejected(): ...
def test_strategy_config_reaches_factory_unchanged(): ...
def test_registry_name_is_preserved(): ...
def test_risk_live_flag_uses_trading_mode_not_lifecycle(): ...
```

**Step 2 — 验证失败**:

```bash
uv run pytest tests/test_deployment_contract.py -v
```

预期：`custos.contracts` 不存在。

**Step 3 — 实现公共 interface**:

```python
class TradingMode(StrEnum):
    SANDBOX = "sandbox"
    TESTNET = "testnet"
    LIVE = "live"


class LifecycleState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential_id: str = Field(min_length=1)


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starting_balances: list[str] = Field(min_length=1)


class DeploymentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    trading_mode: TradingMode
    lifecycle_state: LifecycleState
    strategy_path: str = Field(min_length=1)
    provenance_ref: ProvenanceRef
    connector: str = Field(min_length=1)
    pairs: list[str] = Field(min_length=1)
    leverage: int = Field(ge=1)
    strategy_config: dict[str, Any] = Field(default_factory=dict)
    strategy_registry_name: str | None = None
    code_hash: str | None = None
    log_level: str = "INFO"
    sandbox: SandboxConfig | None = None
    approved_by: list[str] = Field(default_factory=list)
    risk_config: dict[str, Any] = Field(default_factory=dict)
    nautilus_config: dict[str, Any] = Field(default_factory=dict)
```

model validator 必须保证 live 有 64-hex `code_hash`，sandbox 有 starting balances；
非 live 允许 `code_hash=None`。reconciler 必须先 `DeploymentSpec.model_validate()` 再进入
G6/host，并把 live 风控判断改成 `spec.trading_mode is TradingMode.LIVE`。

**Step 4 — schema 单源**: 由 Pydantic model 生成 DeploymentSpec schema，静态 fixture
与 model schema 做等价测试。

**Step 5 — 验证并提交**:

```bash
uv run pytest tests/test_deployment_contract.py tests/test_deployment_reconciler.py -v
make verify
git add <Task 1 exact files>
git commit -m "feat(custos): add strict deployment consumer contract"
```

### Task 2: DeploymentMessage + publication CLI

**Files**: Modify contracts module; Create deployment CLI/tests; Modify dispatcher 与 NATS
design docs。

**Step 1 — 写失败测试**:

```python
def test_message_builds_canonical_subject(): ...
def test_message_contains_full_envelope(): ...
def test_message_event_id_is_uuid7(): ...
def test_message_tenant_mismatch_is_rejected(): ...
def test_message_parse_validates_payload(): ...
def test_public_hash_matches_internal_loader(): ...
def test_publish_waits_for_jetstream_ack(): ...
```

**Step 2 — 公共 interface**:

```python
@dataclass(frozen=True)
class DeploymentMessage:
    subject: str
    envelope: NatsEnvelope
    spec: DeploymentSpec

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        strategy_id: str,
        spec: DeploymentSpec,
    ) -> "DeploymentMessage": ...

    @classmethod
    def parse(
        cls,
        data: bytes,
        *,
        expected_tenant_id: str,
    ) -> "DeploymentMessage": ...

    def to_bytes(self) -> bytes: ...


def compute_strategy_code_hash(strategy_dir: str | Path) -> str:
    return compute_strategy_dir_hash(Path(strategy_dir))
```

`DeploymentMessage.create()` 必须生成完整 v1 envelope：envelope version、UUIDv7 event id、
tenant、RFC3339 nanoseconds、payload schema version 与 payload。Deployment envelope payload
固定为 `{"strategy_id": <id>, "spec": <DeploymentSpec JSON>}`；`strategy_id` 不塞入
`DeploymentSpec`，使 `parse(data, expected_tenant_id)` 能仅从 bytes 恢复 canonical subject。

**Step 3 — CLI**:

```bash
arx-runner deployment validate --spec-file spec.json

arx-runner deployment publish \
  --spec-file spec.json \
  --tenant-id acme \
  --strategy-id supertrend-sandbox \
  --nats-url nats://nats:4222 \
  --strategy-dir /opt/strategies/supertrend
```

- `validate` 只验证，不联网。
- `publish` 等 JetStream ack 后 exit 0。
- `--strategy-dir` 提供时用公共 hash 覆盖 `code_hash`。
- live 缺 strategy dir/hash 时 fail-fast。
- 不接受手写 subject 或不完整 envelope。

**Step 4 — 验证并提交**:

```bash
uv run pytest tests/test_deployment_contract.py tests/test_cli_deployment.py -v
make verify
git commit -m "feat(custos): add deployment publication interface"
```

### Task 3: Standalone JetStream bootstrap

**Files**: Create standalone NATS module、CLI、tests; Modify dispatcher 与 NATS docs。

**Step 1 — 写失败模式测试**:

```python
def test_bootstrap_creates_desired_state_stream(): ...
def test_bootstrap_creates_observed_state_stream(): ...
def test_bootstrap_is_idempotent(): ...
def test_bootstrap_updates_owned_stream_drift(): ...
def test_bootstrap_never_deletes_unknown_stream(): ...
def test_bootstrap_rejects_invalid_tenant(): ...
def test_bootstrap_times_out_when_nats_unreachable(): ...
```

**Step 2 — stream topology**:

Desired-state stream：

```text
name: CUSTOS_<TENANT_HASH>_DEPLOYMENT
subjects: arx.<tenant>.deployment_spec.>
storage: FILE
max_msgs_per_subject: 1
```

Observed-state stream：

```text
name: CUSTOS_<TENANT_HASH>_OBSERVED
subjects:
  arx.<tenant>.deployment_status.>
  arx.<tenant>.heartbeat.>
  arx.<tenant>.telemetry.>
  arx.<tenant>.snapshot.>
  arx.<tenant>.pre_trade_reject.>
  arx.<tenant>.enrollment.>
storage: FILE
```

stream name 使用 validated tenant 的稳定 hash，避免 NATS stream-name 字符限制。

**Step 3 — CLI**:

```bash
arx-runner nats bootstrap \
  --profile standalone \
  --nats-url nats://localhost:4222 \
  --tenant-id acme \
  --timeout-secs 30
```

只支持显式 `standalone` profile；未来 managed topology 另起版本化 profile。

**Step 4 — 验证并提交**:

```bash
uv run pytest tests/test_standalone_nats.py -v
make verify
git commit -m "feat(custos): add standalone JetStream bootstrap"
```

### Task 4: Reconciler retry、readiness 与 engine clean break

**Files**: Create readiness/health; Modify reconciler、daemon、start CLI 与相关测试。

**Step 1 — 写失败测试**:

```python
async def test_initial_subscribe_failure_retries(): ...
async def test_local_guards_tick_while_subscription_is_down(): ...
async def test_subscription_recovery_marks_ready(): ...
async def test_subscription_loss_clears_ready(): ...
async def test_stop_interrupts_backoff(): ...
def test_engine_nautilus_selects_real_host(): ...
def test_engine_noop_selects_noop_host(): ...
def test_use_nt_host_flag_is_removed(): ...
def test_health_fails_before_ready(): ...
def test_health_passes_after_atomic_ready_write(): ...
```

**Step 2 — retry loop**: 使用有上限指数退避（initial 0.25s、multiplier 2、maximum
5s）。每次失败/恢复必须记录 `deployment_reconciler_subscribe_failed`、
`deployment_reconciler_subscribed`、`deployment_reconciler_subscription_lost`；stop event
必须立即中断退避，本地 guard 在失联期间继续 tick。

**Step 3 — readiness**: 原子 JSON 至少包含：

```json
{
  "ready": true,
  "tenant_id": "acme",
  "runner_id": "runner-1",
  "strategy_id": "supertrend-sandbox",
  "nats_connected": true,
  "deployment_subscription": true
}
```

临时文件 + `os.replace()`，mode `0600`，退出时删除。

**Step 4 — engine clean break**:

```python
if args.engine == "nautilus":
    return NtTradingNodeHost(...)
if args.engine == "noop":
    return NoopHost()
raise SystemExit(...)
```

删除 `--use-nt-host`。

**Step 5 — 验证并提交**:

```bash
uv run pytest tests/test_reconciler_readiness.py tests/test_cli_start.py -v
make verify
git commit -m "fix(custos): make runner subscription resilient and observable"
```

### Task 5: 单一完整官方 Docker runtime

**Files**: Modify Dockerfile、Docker tests、Makefile。

**Step 1 — 写失败 image contract**:

```bash
docker run --rm custos-runner:test --help
docker run --rm custos-runner:test start --help
docker run --rm custos-runner:test vault put --help
docker run --rm custos-runner:test nats bootstrap --help
docker run --rm custos-runner:test deployment publish --help
docker run --rm custos-runner:test health --help

docker run --rm --entrypoint python custos-runner:test \
  -c 'import nautilus_trader, yaml'
docker run --rm --entrypoint sops custos-runner:test --version
docker run --rm --entrypoint age custos-runner:test --version
```

**Step 2 — Dockerfile**:

```dockerfile
FROM python:3.12-slim AS builder

COPY dist/custos_runner-*.whl /tmp/
RUN <install local wheel with nautilus extra>

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends age ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Download pinned sops binary and verify checked-in SHA-256.
# Copy wheel site-packages and arx-runner from builder.

USER 1000:1000
ENTRYPOINT ["arx-runner"]
CMD ["start"]
HEALTHCHECK CMD ["arx-runner", "health"]
```

要求：sops 固定版本并校验 SHA-256；amd64/arm64 显式映射；不引 cloud SDK；age 私钥
只通过 runtime mount/env；非 root 约束不变。

**Step 3 — image size**: 先实测完整 runtime；ceiling 设置为实测值向上取整的安全线，
不得超过 1.5 GiB。

**Step 4 — 验证并提交**:

```bash
make test-docker
git commit -m "feat(custos): ship complete official Nautilus runtime image"
```

### Task 6: Dev-only base verification contract

**Files**: Modify `tests/engines/nautilus/test_toolkit_provenance.py`、`Makefile`、
`.github/workflows/release.yml`。

**Step 1 — 验证现有失败**:

```bash
make install
make verify
```

预期：`uv sync --extra dev` 移除 nautilus extra 后，
`test_toolkit_import_bootstrap_resolves_shared_and_pandas_ta` 因缺少 `pkg_resources` 失败。

**Step 2 — 拆分测试边界**:

```python
def test_toolkit_import_bootstrap_resolves_shared() -> None:
    importlib.import_module("custos.engines.nautilus.toolkit")
    shared_nautilus = importlib.import_module("shared.nautilus")
    assert Path(shared_nautilus.__file__).is_relative_to(
        _TOOLKIT_ROOT / "shared" / "nautilus"
    )


def test_toolkit_import_bootstrap_resolves_pandas_ta_with_nautilus_extra() -> None:
    pytest.importorskip("nautilus_trader")
    importlib.import_module("custos.engines.nautilus.toolkit")
    pandas_ta = importlib.import_module("pandas_ta")
    assert Path(pandas_ta.__file__).is_relative_to(
        _TOOLKIT_ROOT / "vendor" / "pandas_ta"
    )
```

base contract 不得引入 `setuptools`、`packaging`、`pandas` 或 `nautilus-trader` 到 dev
extra；NT import contract 必须在 `verify-nt` 下真实运行，不能永久 skip。

**Step 3 — Makefile/CI gate**:

```makefile
verify-base-clean:
	uv sync --extra dev
	$(MAKE) verify
```

release workflow 使用以下顺序，避免预装 NT 让 base gate 假绿：

```bash
make verify-base-clean
make install-nt
make verify-nt
```

**Step 4 — 验证并提交**:

```bash
make verify-base-clean
make install-nt
make verify-nt
git commit -m "test(custos): restore clean base verification contract"
```

### Task 7: Release pipeline 与 post-publish runtime gate

**Files**: Modify release workflow、verify script、Makefile、release tests。

**Step 1 — 写失败测试**: release workflow 必须执行完整 image command matrix、NT/YAML
import、sops/age、non-root、readiness CLI、cosign，并发布 `v0.3.0` 与 `latest`。

**Step 2 — 新验证 target**:

```makefile
verify-runtime: test-docker
	uv run pytest tests/integration/test_standalone_runtime.py -v
```

release workflow 在 publish 前跑：

```bash
make verify-base-clean
make install-nt
make verify-nt
make verify-runtime
```

**Step 3 — post-publish**: `verify-release.sh` pull `:v${VERSION}` 后重复最小 runtime
contract，不只跑 `--help`。

**Step 4 — 验证并提交**:

```bash
uv run pytest tests/test_release_workflow_shape.py tests/test_docker_runtime_contract.py -v
make verify
git commit -m "ci(custos): gate complete runtime image before publish"
```

### Task 8: Hermetic standalone runtime acceptance

**Files**: Create integration test; Modify reconciler/status and per-key vault decrypt unit tests,
runtime code, and examples; Delete testnet 派生 Dockerfile。

**Step 1 — 集成验收路径**:

```text
fresh nats:2.10-alpine -js
  → arx-runner nats bootstrap
  → provision dummy per-key vault
  → start custos official image with --engine noop
  → wait for arx-runner health
  → arx-runner deployment publish
  → assert generation observed / running status
  → publish stopped generation
  → assert stopped status
```

NoopHost 只用于验证 NATS、vault、reconcile、readiness 与 status contract；真实 NT
capability 由 Task 5 image/host tests 独立验证。验收不依赖 Binance、市场行情、真实 API key、
`order_filled` 或固定 sleep。

**Step 2 — examples**:

- 删除 `build:`，使用 `ghcr.io/the-alephain-guild/custos:v0.3.0`。
- 新增一次性 `nats-bootstrap` service。
- runner 依赖 bootstrap `service_completed_successfully`。
- runner command 显式以 `start` 开头并使用 `--engine nautilus`。
- readiness 使用 health CLI。
- spec publisher 使用 `deployment publish`。
- 删除 `examples/supertrend-testnet/Dockerfile`。

**Step 3 — 验证并提交**:

```bash
make verify-runtime
docker compose -f examples/supertrend-testnet/docker-compose.yaml config
git commit -m "test(custos): add hermetic standalone deployment acceptance"
```

### Task 9: 0.3.0 文档、版本与 clean-break close-in

**Files**: Modify pyproject/lock、README、CHANGELOG、设计文档、ops 文档、examples。

**Step 1 — 版本**: `pyproject.toml` → `version = "0.3.0"`，无旧 entrypoint 兼容逻辑。

**Step 2 — CHANGELOG**: 记录完整 NT runtime、Docker entrypoint、显式 `start`、删除
`--use-nt-host`、engine enum、generation/lifecycle contract、runtime spec validation 与新增
deployment/nats/health CLI。

**Step 3 — 权威文档同步**: 至少更新 `docs/domain.md`、三个受影响 design docs、
`docs/ops/05-deployment.md`、`README.md`、gateway schema/sample；`CLAUDE.md` 仅在导航
指针需要变化时更新。

**Step 4 — 下游 gate 声明**:

```text
PS Plan 49 must not execute against custos < 0.3.0.
PS must consume the official image directly.
PS must not maintain a derived custos Dockerfile.
PS owns strategy_config assembly only.
```

**Step 5 — 验证并提交**:

```bash
make verify-base-clean
make install-nt
make verify-nt
make verify-runtime
git commit -m "docs(custos): document 0.3.0 clean deployment contract"
```

### Task 10: Close-out

**Files**: Modify this plan and `.forge/README.md`。

动作：

1. Plan status 改为 `✅ Completed` 并添加 `Completed: YYYY-MM-DD`。
2. `.forge/README.md` Plan 14 状态改为 completed。
3. 记录实际 commit range、image size、runtime matrix 与全部偏离。
4. 记录 PS 的最低 custos SHA/tag。
5. 完成报告区分 code-level coverage、Docker runtime wire、standalone NATS wire、NT
   capability 与外部 Binance testnet 手工验证 defer。

完成报告红线表：

| red_line | code_coverage | runtime_wire | defer_status | follow_up |
|---|---|---|---|---|
| Key/KEK 不出进程 | vault/image/e2e tests | sops+age official image | none | none |
| G6 不绕过 | NT host tests | official NT runtime | external live session separate | operator acceptance |
| 失联不停止 | retry/guard tests | reconnecting reconciler | none | none |
| Decimal money | existing contract suite | unchanged | none | none |

最后提交：

```bash
git add \
  .forge/plans/2026-07/14-clean-deployment-runtime-contract.md \
  .forge/README.md
git commit -m "docs(custos): mark plan 14 as completed"
```

## 验证清单 (Verification)

- [ ] `make verify-base-clean`（内部执行 `uv sync --extra dev` + `make verify`）
- [ ] dev-only base gate 不安装 setuptools/pandas/NautilusTrader，NT-only import test 正确 skip
- [ ] `make install-nt` 后 NT-only pandas_ta import test 实际运行（非 skip）
- [ ] `make verify-nt`
- [ ] `make test-docker`
- [ ] `make verify-runtime`
- [ ] `arx-runner deployment validate` 对合法/非法 spec 行为正确
- [ ] `arx-runner nats bootstrap` fresh/idempotent/update 三种路径通过
- [ ] subscribe 首次失败不会终止 reconciler
- [ ] readiness 只在 subscription 成功后出现
- [ ] `DeploymentMessage` producer/consumer round-trip
- [ ] factory 能收到完整 `strategy_config`
- [ ] live 判断使用 `trading_mode`，不再使用 lifecycle
- [ ] official image 包含 NT/YAML/sops/age
- [ ] official image 以非 root 运行
- [ ] Docker management 命令无需覆盖 entrypoint
- [ ] testnet example 不再包含派生 Dockerfile
- [ ] release workflow 发布 `v0.3.0`/`latest`
- [ ] Non-Custodial 四红线专项检查通过
- [ ] 所有代码工件使用英文
- [ ] authority docs 与代码一致

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|---|---|---|---|
| T1 DeploymentSpec consumer contract | ✅ | 2026-07-11 | Strict model, generated conditional schema, reconciler validation |
| T2 DeploymentMessage/publication CLI | ✅ | 2026-07-12 | Wrapper round-trip, public hash seam, validate/publish CLI + JetStream ack |
| T3 standalone JetStream bootstrap | ✅ | 2026-07-12 | Idempotent owned topology, drift repair, collision safety, timeout + CLI |
| T4 retry/readiness/engine clean break | ✅ | 2026-07-12 | Bounded retry, guard ticks, atomic health state, clean engine enum |
| T5 complete official Docker runtime | ✅ | 2026-07-12 | NT/YAML + sops/age, clean CLI entrypoint, arm64 1,070,492,907 bytes |
| T6 dev-only base verification contract | ✅ | 2026-07-12 | Base: 468 passed/18 skipped; NT: 532 passed/4 skipped; CI order locked |
| T7 release runtime gate | ✅ | 2026-07-12 | Pre-push verify-runtime; post-publish CLI/NT/vault/cosign contract |
| T8 hermetic standalone acceptance | ✅ | 2026-07-12 | Real NATS/vault/readiness wire; running→stopped; official-image Compose |
| T9 0.3.0 docs/version | 🔲 | — | — |
| T10 close-out | 🔲 | — | — |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|---|---|---|---|
| DECISION | Docker distribution | 单一完整官方镜像，不发布 base image | ✅ 用户 2026-07-11 |
| DECISION | Compatibility | 不做 PS 过渡兼容；custos 完成后 PS 从干净 0.3.0 开始 | ✅ 用户 2026-07-11 |
| IMPROVEMENT | Public seam | 用 DeploymentMessage 深模块替代下游理解多个内部模块 | ✅ T2 |
| IMPROVEMENT | DeploymentMessage wire | envelope payload 使用 `{strategy_id, spec}` wrapper，解决 parse 仅拿 bytes 无法恢复 subject 的信息缺口 | ✅ 用户 2026-07-12 |
| IMPROVEMENT | Runtime truth | schema validation 升级为真实 consumer runtime validation；model 与 JSON Schema 同时锁定 mode 条件 | ✅ T1 |
| IMPROVEMENT | Reliability | subscribe 文档承诺与实际 retry 行为收敛 | ✅ T4 |
| IMPROVEMENT | Base verification | 拆分 shared bootstrap 与 nautilus-only pandas_ta import，并用 `verify-base-clean` 防预装 NT 掩盖 dev-only 失败 | ✅ 用户 2026-07-11 |
| IMPROVEMENT | Terminal status truth | T8 acceptance 暴露成功 stop/archive 仍硬编码上报 running；补充 reconciler phase 映射与单元测试 | ✅ 用户 2026-07-12 |
| IMPROVEMENT | sops JSON decrypt | 官方 sops 3.13.2 对 `.enc` 推断 binary，真实 vault decrypt 失败；显式锁定 JSON input/output type 并保留容器 canary | ✅ 用户 2026-07-12 |

---

*Drafter: Codex @ 2026-07-11*
*Scope: custos-only; PS remains blocked until this plan closes and v0.3.0 is verified.*
