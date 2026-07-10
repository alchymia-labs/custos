# 12 — custos distribution: signed wheel + docker image + SEMVER/LTS + gateway contract v1

> **Status**: 🔲 Not started
> **Created**: 2026-07-10
> **Project**: custos (`tesseract-trading/custos/`)
> **Wave**: v1-team-full-loop
> **For Claude**: `/forge:execute` 单会话可完成（中粒度 6-10h，多 track 但每 track 独立）
> **Depends on**: Plan 05 ✅ Completed (2026-07-10 `e82825d`) — `arx_runner`→`custos` rename 已收敛；Plan 04 ✅ Completed (2026-07-10) — runtime-wire live；**custos-11 (CLI clean-break) — hard dep**：Plan 11 已 lock 单一 `[project.scripts].arx-runner` entry + 删除 legacy `python -m custos` / `SopsAgeVault` / `~/.custos/` 命名空间（CEO clean-break directive 2026-07-10, docket 1，无 migration command）；Plan 12 消费 Plan 11 已 lock 的 script name + namespace，DP5 fanout gate 已 resolved
> **Blocks**: 首次公开发布 (`custos-runner 1.0.0` 或 `0.x` LTS 起始版本，具体 by DP4)
> **multi_session_scope**: false（9 Task，CI 首次接入是主要风险，但 wheel/docker 各 track 可独立分割）

---

## 起源 (Origin)

三条独立信号汇合：

1. **README.md:98-105 §"Not Included Yet"** 已把 Plan 12 job description 逐字预声明：
   ```
   README.md:100-101: CI + signed release pipeline — signed wheel + signed docker image
     (ghcr.io/...) + reproducible build (ADR-012 v4 stage-3 action items)
   README.md:102-103: Contract versioning mechanism — custos ↔ arx OpenAPI/JSON Schema
     registry + SemVer tagging
   README.md:104: CONTRIBUTING.md + SECURITY.md — public-repo façade completion
   ```
2. **ADR-014 v6 §Non-Custodial Trust Model** 要求 custos 公共开源 + 可审计签名兑现 non-custodial 红线 —— 未签名 wheel / 无 provenance 的 image = 承诺留白。
3. **Wave v1-team-full-loop** 需要「团队自托管完整闭环」，distribution 面（wheel + image）+ LTS 承诺 + gateway 契约版本化 是运营 v1 的必备门槛。

Evidence-scout §L3 实证（`arx/.forge/handoff/2026-07-team-full-loop/evidence-scout-custos.md:220-297`）已确认所有 §"Not Included Yet" 条目均**当前不存在**：
- `[project.scripts]` — pyproject.toml grep 零命中
- 仓根 `Dockerfile` — 只有 `examples/supertrend-testnet/Dockerfile`
- `.github/` — 目录不存在
- `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md` — 均不存在
- `docs/lts-commitment.md` — 不存在；LTS 仅 README.md:103-104 单句 prose claim

## 上下文 (Context)

### 现状实证（as-of 2026-07-10 Plan 04/05 close-out 后）

| 契约面 | 现状 | 证据锚 |
|--------|------|--------|
| 分发名 | `name = "custos-runner"` | pyproject.toml:2 |
| Python import 名 | `custos`（`packages = ["src/custos"]`） | pyproject.toml:56 |
| Version | `0.1.0`（pre-1.0） | pyproject.toml:3 |
| Requires-python | `>=3.11`（`nautilus` extra 收 3.12+ gate） | pyproject.toml:4, 27 |
| Build backend | hatchling（`[tool.hatch.build.targets.wheel]` 已配） | pyproject.toml:49-56 |
| `[project.scripts]` | **零**（无 console_script entry） | pyproject.toml grep 零命中 |
| Optional extras | `dev` + `nautilus`（3.12+ gated）+ 4 空槽（`hummingbot/freqtrade/athanor/nt-rust`）+ `all-engines` | pyproject.toml:13-47 |

### 契约证据锚（Step 1.5 gate）

**arx-side CustosGateway trait**（Plan 12 契约 spec 目标对齐面）：

- 文件 `arx/backend/crates/coordination/src/custos.rs:9-30`
- Trait 定义：`pub trait CustosGateway: BackendClient` — 4 typed async method + `raw_call`（继承 `BackendClient` supertrait `custos.rs:9`）
- 4 typed method 逐字：
  - `validate_enrollment(&self, token: &str) -> Result<TenantId, CoordinationError>` — `custos.rs:11`
  - `record_deployment_status(&self, tenant: &TenantId, spec_id: &str, status: &str)` — `custos.rs:13-18`
  - `ingest_telemetry(&self, tenant: &TenantId, snapshot_json: &str)` — `custos.rs:20-24`
  - `handle_heartbeat(&self, tenant: &TenantId, runner_id: &str)` — `custos.rs:26-30`
- **未 wire 状态**：`CustosGatewayImpl` 结构声明在 `custos.rs:35`（docstring 在 `custos.rs:33-34` 明说「真实装配（NATS 消费 + 持久化）在 api/server 消费改造阶段接线，此处方法体为占位」）；`impl CustosGateway for CustosGatewayImpl` 每个 method body 返 `Err(CoordinationError::Unavailable("custos gateway not wired"))` — `custos.rs:45-79`。arx-79 wire 后 method body 真跑；Plan 12 **只出契约 spec**，不阻塞 arx-side wire。
- `FakeCustosGateway`（测试 double）—— `custos.rs:79-110`（struct 声明 + `BackendClient` impl `custos.rs:81-86` + `CustosGateway` impl `custos.rs:87-110`），语义 = 返 `Ok(())` / `Ok(TenantId::from_trusted("test"))`。

**contract v1 语义定位**：CustosGateway 4 typed method 是 arx 内部 trait 而非公开 HTTP endpoint。真正跨仓边界 = custos → arx 的 NATS envelope schema（`custos/src/custos/core/nats_client.py`）+ enrollment/deployment/telemetry/heartbeat payload。Plan 12 契约 spec 目标：**为这 4 类 payload 定义 JSON Schema v1**（与 Rust trait signature 对齐），锚定为 backward-compat baseline。

### plan-to-plan 引用清单（lesson #29 强制）

| plan-id | commit-hash | 引用的文件/章节 | 用途 |
|---------|-------------|-----------------|------|
| 05 | `e82825d` | `pyproject.toml` § extras + `[tool.hatch.build.targets.wheel]` | 分发结构基线（`packages = ["src/custos"]`）；Plan 12 在此基线上加 `[project.scripts]` + version scheme |
| 04 | `d0dd537` | `src/custos/core/nats_client.py` § envelope | Plan 12 gateway contract v1 需要引用 NATS envelope schema 作为 payload container spec |
| 11 | *(draft locked 2026-07-10, untracked)* | `[project.scripts].arx-runner` 单一 entry (Plan 11 §File Inventory pyproject.toml 行) + `SopsAgeVault` 删除 (`credential_vault.py:121-206`) + `~/.custos/` namespace 退休 | Plan 12 直接 hard-code `arx-runner` script name + `~/.arx/` namespace，DP5 从占位升级为 resolved；Plan 11 clean-break 落地后 Plan 12 execute 才能启动 |

三元组表实证（Step 1.5 gate）：
- `git log --oneline e82825d` 命中（Plan 05 05b squash，Task list 已固化）
- `git log --oneline d0dd537` 命中（Plan 04 04b squash）
- Plan 11 已 draft 落定 clean-break 方向 (2026-07-10 untracked) — hard dep，Plan 12 直接引用 Plan 11 已 lock 的 `arx-runner` script name + `~/.arx/` namespace，DP5 resolved

## 目标 (Goal)

把 custos 从「Apache-2.0 源码公开可读」升级为「Apache-2.0 源码公开可读 + 可验证签名 wheel + 可验证签名 docker image + 显式 LTS 承诺 + 版本化契约 spec」——让外部审计员单仓 clone 后能验证「运行时二进制 = 已审计源码」，兑现 ADR-014 v6 §Non-Custodial 承诺的**可验证**面。

## 架构 (Architecture)

三层 fail-fast + provenance 链（lesson #22 multi-layer 独立可测）：

1. **构建层**：hatchling wheel + multi-stage Dockerfile（non-root USER）+ `uv lock` 复现锁；每层独立可跑（`make dist` / `make docker-build`）
2. **签名层**：sigstore keyless signing（GitHub Actions OIDC attestation）为 wheel + image 各出独立 signature bundle；不引 GPG（key ceremony 与 custos non-custodial 定位冲突，且 sigstore 生态已成熟）
3. **契约层**：`docs/gateway-contract/v1/` 定义 CustosGateway 4 payload JSON Schema + `CHANGELOG.md` 记录 additive-only rule + `docs/lts-commitment.md` 承诺 EOL ≥ 12 months / security patch SLA 30d

CI（`.github/workflows/release.yml`）在 tag push 触发时：wheel build → sign → publish to PyPI（optional）+ docker build → sign → publish to GHCR + release notes gen from CHANGELOG。

## 关键设计决策 (Key Design Decisions)

| # | 问题 | 决策 | 理由 |
|---|------|------|------|
| DP1 | Wheel 签名方式：sigstore vs GPG | **sigstore keyless (via GH Actions OIDC)** for wheel; **cosign keyless (via GH Actions OIDC)** for docker image | Sigstore 生态已成熟（`sigstore` PyPA 官方推荐），keyless 无 key ceremony 负担；GPG 需要长期 key management，与 custos non-custodial 走 age 的定位有工具面冲突。sigstore verification bundle 独立文件 `.whl.sigstore`，审计员单命令 `sigstore verify` 即可；docker image 用 cosign（sigstore 生态的容器签名工具），签名产物落 OCI referrers API 或 rekor 透明日志 |
| DP2 | Docker image registry | **GHCR `ghcr.io/the-alephain-guild/custos`** | ADR-014 v6 声明生态公开开源；GHCR public image 匹配 Apache-2.0 day-1 public 定位；不需要额外 registry 账号（GH Actions 原生支持） |
| DP3 | Contract spec 格式 | **JSON Schema (`gateway-contract/v1/*.schema.json`) + 索引 README** | 不用 OpenAPI —— CustosGateway 传输面是 NATS + coordination trait，非 REST HTTP，OpenAPI HTTP-shape 不匹配；JSON Schema 可直接被 msgspec / pydantic validator 消费，与 custos 现有 Pydantic v2 model 契合 |
| DP4 | SEMVER 起点：0.x pre-1.0 还是 1.0.0 | **保持 0.x LTS 起点直到 arx-side wire ready**（下一个 minor `0.2.0` 作为 Plan 12 交付版）；1.0.0 promote 时机由后续 plan 决定 | arx-79 wire 未完成前 `CustosGatewayImpl` 生产实现是 stub（`custos.rs:45-79`），提前 1.0.0 会把「未 wire 的 gateway 契约」冻死。0.x LTS 期间承诺 additive-only + security patch，允许契约小幅演进 |
| DP5 (**RESOLVED**) | Console script entry name | **`arx-runner` (Plan 11 clean-break lock, 2026-07-10)**。Plan 12 直接 hard-code：`[project.scripts].arx-runner = "custos.cli.subcommands:main"` + `Dockerfile ENTRYPOINT ["arx-runner", "start"]` + `docs/lts-commitment.md` 引用 `arx-runner` verbatim。无 provisional name，无 fanout 二次核对。 | Plan 11 clean-break CEO directive (2026-07-10) 消除了 DP5 的占位状态。lesson #35 boundary-constant single-source 规则满足：script name 只有一个真理源在 Plan 11 pyproject.toml，Plan 12 消费方向下游流。前置 gate：Plan 11 必须先 execute + land，Plan 12 才能启动（避免"Plan 12 先落 `arx-runner` 但 Plan 11 未删 legacy `custos` 入口"的双源窗口）。 |
| DP6 | Reproducible build 强度 | **`SOURCE_DATE_EPOCH` pin + `uv.lock` freeze + hatchling deterministic + docker `--label org.opencontainers.image.source=<sha>`**；不引 Nix flake | Nix 与生态其他 Python 子系统（uv-based）路线冲突；`SOURCE_DATE_EPOCH` + `uv.lock` 已可满足 wheel bit-for-bit 复现（bytes-identical rebuild）。docker image 层暂不追求 bit-for-bit（buildkit timestamp 复现是独立 workstream），只承诺 label + digest 追溯 |
| DP7 | LTS window 数值 | **EOL ≥ 12 months per minor release line；security patch SLA 30 days；release cadence best-effort quarterly** | README.md:104 已 prose 声明 EOL ≥ 12 months，本 plan 只做 doc 兑现；不引入 automated LTS status page（v1 阶段过度），改为手写 `docs/lts-commitment.md` 表 + follow-up plan hook |
| DP8 | Contract v1 breaking change 保护 | **JSON Schema snapshot golden file** + pytest `test_gateway_contract_v1_backward_compat.py` diff：新增 field OK / 修改 required 或删除 field → FAIL；v2 breaking → 新目录 `gateway-contract/v2/` | 与 lesson #22 multi-layer 独立可测对齐（snapshot 是运行时 layer，非仅 schema layer） |

### SEMVER 承诺表（DP4 + DP7 展开，正式契约）

| 版本段 | 允许变更 | 禁止变更 | 记录位置 |
|--------|---------|---------|---------|
| **MAJOR** (`X.0.0`) | breaking：gateway-contract 目录切 `v2/` 独立索引；`[project.scripts]` entry name 变更；Python `>=3.12` 收紧；`ExecutionEngineProtocol` Tier-1 契约 field/method rename 或 remove；`~/.custos/` / `~/.arx/` 状态目录 layout 破坏性演化 | 非 breaking 改动 | `CHANGELOG.md` § Removed / Changed（含迁移脚本 pointer 到 `docs/upgrade-path.md`） |
| **MINOR** (`0.Y.0` / `X.Y.0`) | additive-only：新增 `[project.scripts]` entry；新增 gateway-contract v1 field（`additionalProperties: false` 例外须 major）；新 `[project.optional-dependencies]` extra 槽位；新 subcommand；新 CI job（不撤旧 job） | 修改现有 field 的 required；删除 field；rename entry point；缩紧 requires-python | `CHANGELOG.md` § Added / Deprecated（deprecated field 保留至少 1 minor 周期 + 显式警告） |
| **PATCH** (`X.Y.Z`) | fix + security patch + doc 修正 + 内部重构（无外部 observable 变化） | 任何 field / entry / schema / doc 语义变化 | `CHANGELOG.md` § Fixed / Security |
| **PRE-RELEASE** (`X.Y.Z-rc.N`) | rc 阶段允许 breaking 回滚（未 stable release），配 CHANGELOG 显式 `## [X.Y.Z-rc.N]` 段 | stable 后不追溯改 rc | 同 minor / major 分类，加 `-rc.N` 后缀 |

**arx-side client version pin 策略**（arx-77 + arx-79 侧 client 消费）：arx `Cargo.toml` 内 custos wheel 依赖用 `~=0.2` 语义（PEP 440 compatible release）—— 允许 patch + minor additive，禁自动升 major。arx-79 wire ready 后 gateway-contract v2 承接需 arx 侧 client crate 显式 bump 至 `~=1.0` / `~=2.0` + fanout（lesson #35 boundary-constant 双源联动）；本 plan 只出契约，不 fanout 到 arx client（arx-79 承接）。

### LTS 承诺表（DP7 展开，正式契约）

| 承诺项 | 数值 / 定义 | 兑现载体 | audit-non-silence 挂钩 |
|--------|-------------|---------|-----------------------|
| **EOL Window** | 每个 minor line ≥ 12 months from release | `docs/lts-commitment.md` § EOL Window 表 + `CHANGELOG.md` § Deprecated 段 | EOL 前 30d 必发 GH Release notes + CHANGELOG § Deprecated 段（不静默 EOL） |
| **Security Patch SLA** | CVE 公开 → patch release ≤ 30 days（best-effort） | `docs/lts-commitment.md` § Security Patch SLA + `SECURITY.md` reporting 入口 | patch release 后 24h 内 GH Security Advisory 公开 |
| **Release Cadence** | quarterly best-effort（minor line） | `docs/lts-commitment.md` § Release Cadence + `docs/upgrade-path.md` roadmap 段 | miss cadence 归 `docs/lts-commitment.md` § Deviations log，需 CEO 复核 |
| **Deprecation Grace** | 任何 field / entry / behavior deprecate 后至少保留 1 minor line 周期（≥ 3 months）| `CHANGELOG.md` § Deprecated + gateway-contract v1 schema 内 `deprecated: true` 注解 | deprecation 生效周期内每次 minor release notes 复述 |
| **Backport Policy** | Security fix → 所有 active LTS lines；Critical bug → CEO override 判定 | `docs/lts-commitment.md` § Backport Policy 表 + git tag `v0.2.1-lts` 命名约定 | backport miss → `docs/lts-commitment.md` § Deviations log |
| **arx-side wire ready gate** | 1.0.0 promote 判据：arx-79 wire 落地 + 3 consecutive minor 无 breaking change + gateway-contract v1 覆盖率 100% | `docs/upgrade-path.md` § 0.x → 1.0 promote checklist | promote 前必发 RFC + Wave 级 Council 辩论（ADR-014 v6 §Custos 兑现门） |

**红线兑现**（本 plan 与 CLAUDE.md 红线段直接映射）：
- **Non-Custodial**（`CLAUDE.md § 5` red line 1）：sigstore wheel + cosign docker → supply chain 不悄变；无 key ceremony 也无 key 泄漏面。
- **audit-non-silence**（`CLAUDE.md § 5` red line）：LTS 承诺变更（deprecation / EOL / miss cadence）必显式公告（CHANGELOG + Release notes + Security Advisory），本表所有承诺项均有 audit-non-silence 挂钩。
- **SEMVER 契约**：major bump 必列 breaking change → arx client version pin 强制升级（本表 arx-side 段）。

## 承载决策 (Capability Hosting Decision)

| 能力 | plan mode? | hook? | CLAUDE.md? | 现有 skill flag? | 新 skill? | 决策 |
|------|-----------|-------|-----------|-----------------|----------|------|
| CI release workflow | ❌ | ❌ | ❌ | ❌ | ❌ | **纯 CI 工件**（`.github/workflows/`），不需要 skill 承载 |
| wheel signing | ❌ | ❌ | ❌ | ❌ | ❌ | **sigstore CLI + `.github/workflows/scripts/sign-wheel.sh`**，工具 CLI 已成熟不需要 forge skill 抽象 |
| LTS 承诺 | ❌ | ❌ | ✅ 引用 | ❌ | ❌ | 承诺文档 `docs/lts-commitment.md`；CLAUDE.md § 6 常用命令段加一行 `make release` 指针 |
| gateway contract spec | ❌ | ❌ | ✅ 引用 | ❌ | ❌ | 静态 JSON Schema 文件；CLAUDE.md § 2 子系统边界段加一行「契约 v1 冻结于 `docs/gateway-contract/v1/`」 |

结论：**无新 skill / hook / plan-mode**。Plan 12 全部产出 = CI + docs + schema + test，纯静态 artifact。

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|----------|------|------|
| `pyproject.toml` | Modify | ① 加 `[project.scripts]`：**Plan 11 已 lock 单一 entry `arx-runner = "custos.cli.subcommands:main"`**（Plan 12 直接读 Plan 11 landed 状态，无占位）；② 版本 bump `0.1.0` → `0.2.0`（LTS 起点 + Plan 11 breaking release 同版）；③ `[project.optional-dependencies].lts` 新增（含 `sigstore`, `pytest-docker`）；④ `[tool.hatch.build.hooks.custom]` 加 SOURCE_DATE_EPOCH 支持。**依赖 Plan 11 先 landed**（Plan 11 `pyproject.toml` 已注册 `arx-runner` + 删除 legacy `custos` entry，Plan 12 消费此状态）。 |
| `Dockerfile` | Create | 多阶段 build（builder + runtime）；`FROM python:3.12-slim` runtime；`USER 1000:1000` non-root；`WORKDIR /opt/custos`；**`ENTRYPOINT ["arx-runner", "start"]` (Plan 11 lock, 无占位)**。runtime stage 装 `pip install custos-runner[nautilus]`（含 Plan 11 注册的 `arx-runner` console script）。 |
| `.dockerignore` | Create | 排除 `.git/` / `.forge/` / `.venv/` / `tests/` / `examples/` / `docs/`（keep build context slim） |
| `.github/workflows/release.yml` | Create | tag `v*` 触发；jobs: `build-wheel` → `sign-wheel`（sigstore keyless）→ `publish-pypi`（optional flag）→ `build-docker` → `sign-docker`（cosign keyless）→ `publish-ghcr` → `release-notes`（gen from CHANGELOG） |
| `.github/workflows/scripts/sign-wheel.sh` | Create | sigstore CLI wrapper：input `dist/*.whl` → output `dist/*.whl.sigstore`；verify step 内嵌 |
| `.github/workflows/scripts/verify-release.sh` | Create | post-publish smoke test：pull wheel + verify sig，pull image + verify sig + docker run `--rm` `--help`（health probe） |
| `CHANGELOG.md` | Create | Keep-a-Changelog 格式；`## [0.2.0] - 2026-07-10` 首个 entry；explicit `### Added / ### Changed / ### Deprecated / ### Removed / ### Fixed / ### Security` 分节 |
| `docs/lts-commitment.md` | Create | LTS window (EOL ≥ 12 months per minor line) + security patch SLA (30d) + release cadence (quarterly best-effort) + upgrade path pointer + follow-up plan hook |
| `docs/gateway-contract/v1/README.md` | Create | contract v1 索引；引用 arx `custos.rs:9-30` 作契约来源；additive-only 规则；v2 breaking-change protocol |
| `docs/gateway-contract/v1/enrollment.schema.json` | Create | `validate_enrollment` payload JSON Schema（token: str hash, tenant_id: str） |
| `docs/gateway-contract/v1/deployment_status.schema.json` | Create | `record_deployment_status` payload（tenant, spec_id, status enum） |
| `docs/gateway-contract/v1/telemetry_snapshot.schema.json` | Create | `ingest_telemetry` snapshot_json envelope（对齐 `nats_client.py` envelope + payload） |
| `docs/gateway-contract/v1/heartbeat.schema.json` | Create | `handle_heartbeat` payload（tenant, runner_id, ts） |
| `docs/upgrade-path.md` | Create | 0.x → 1.0 promote 判据 + minor line 之间 upgrade 步骤 + config migration 表模板 |
| `docs/reproducible-build.md` | Create | `SOURCE_DATE_EPOCH` 用法 + `uv.lock` freeze 说明 + rebuild verification 步骤（`sha256sum dist/*.whl` 二次 build 应一致） |
| `CONTRIBUTING.md` | Create | 面向外部审计员/贡献者；测试运行 + coding style pointer + PR 流程 |
| `SECURITY.md` | Create | vuln 上报入口（GH Security Advisories）+ SLA + PGP contact（optional，v1 阶段可省） |
| `tests/test_wheel_signature.py` | Create | Task 3 断言：build wheel 后 `dist/*.whl.sigstore` 存在 + sigstore verify 通过；CI 环境跑（本地 skip via marker） |
| `tests/test_docker_non_root.py` | Create | Task 2 断言：`docker inspect` USER != root/0/"" |
| `tests/test_gateway_contract_v1_backward_compat.py` | Create | Task 7 断言：`docs/gateway-contract/v1/*.schema.json` snapshot diff vs golden；additive OK / breaking FAIL |
| `tests/test_lts_commitment_doc.py` | Create | Task 6 断言：`docs/lts-commitment.md` 存在 + 含 EOL / SLA / cadence 三 section |
| `tests/test_reproducible_build.py` | Create | Task 8 断言：双 build wheel bytes-identical（`SOURCE_DATE_EPOCH` 固定）；本地 slow marker |
| `tests/test_docker_image_size.py` | Create | Task 2 断言（FM11）：`docker inspect` image size < 500MB（防明显 multi-stage 泄漏）；docker marker gated |
| `Makefile` | Modify | 加 `make dist` / `make sign` / `make docker-build` / `make docker-sign` / `make verify-release` target；`make release` = 组合 |
| `CLAUDE.md` | Modify | § 2 子系统边界段加一行「契约 v1 冻结于 `docs/gateway-contract/v1/`」；§ 6 常用命令段加 `make release` 与 `make verify-release` 指针 |
| `README.md` | Modify | § "Not Included Yet" 移除已交付项（wheel sig + docker + SEMVER + LTS + contract v1 + CONTRIBUTING + SECURITY）；替换为「见 CHANGELOG.md / docs/lts-commitment.md」引用 |

**统计**：25 新增 + 4 修改 = 29 文件。

## 失败模式覆盖契约 (Failure-Mode Coverage) — lesson #17 强制

| # | 失败模式 | 覆盖测试 | Layer（lesson #22 独立可测）|
|---|---------|---------|---------|
| FM1 | Wheel unsigned 意外发布 | `test_wheel_signature.py` + CI job `sign-wheel` 前置 gate | Layer 2 (CI) + Layer 3 (post-publish smoke via `verify-release.sh`) |
| FM2 | Docker root user 泄露 | `test_docker_non_root.py` + Dockerfile `USER` 指令 + CI docker inspect gate | Layer 1 (Dockerfile) + Layer 2 (CI) + Layer 3 (smoke) |
| FM3 | Contract v1 breaking change 静默 | `test_gateway_contract_v1_backward_compat.py`（snapshot golden diff）+ pre-commit hook（changelog stub） | Layer 1 (schema snapshot) + Layer 2 (pytest CI gate) |
| FM4 | LTS 承诺文档缺失 / 陈旧 | `test_lts_commitment_doc.py`（doc 存在 + 3 section 存在） | Layer 1 (doc) + Layer 2 (test gate) |
| FM5 | Reproducible build drift（build 二次不一致） | `test_reproducible_build.py`（本地 slow marker，CI nightly job） | Layer 1 (build config) + Layer 2 (test) |
| FM6 | CHANGELOG entry 缺失 tag 时 | pre-commit hook（tag push 前检 `## [<version>]` section 存在） | Layer 2 (hook) — 本 plan 只出 hook stub，wire 由 **Plan 09 hook infra 正式化 plan (Batch 2)** 承载。（注：原 draft 此处 mis-referenced 为 Plan 11；hook infra 归 Plan 09，Plan 11 是 CLI clean-break，两条独立线。） |
| FM7 | GHCR / PyPI publish 失败静默 | CI job 失败即 FAIL；`verify-release.sh` post-publish 拉取实体 | Layer 3 (post-publish smoke) |
| FM8 | sigstore / cosign key rotation drift（OIDC identity trust chain 破裂） | `verify-release.sh` post-publish 断言 `--cert-identity` 匹配 tag-driven repo URL；每次 verify 失败即回滚 tag 并新起 patch release | Layer 2 (verify) + Layer 3 (rollback protocol doc `docs/lts-commitment.md` § Key Rotation Protocol) |
| FM9 | SEMVER minor 隐性破坏 arx client（`~=0.2` pin 内新增 required field） | `test_gateway_contract_v1_backward_compat.py` golden diff 阻断（DP8）；CI job `contract-drift-check` 单独 gate | Layer 1 (schema snapshot) + Layer 2 (pytest) + Layer 3 (arx client integration smoke，defer 到 arx-79 wire follow-up) |
| FM10 | LTS EOL 未公告（audit-non-silence 红线破线） | `tests/test_lts_commitment_doc.py` 加 assert：每个 minor line 的 EOL 日期在 `docs/lts-commitment.md` 表内显式列出，未列即 FAIL | Layer 1 (doc) + Layer 2 (test) |
| FM11 | Docker image size 膨胀（multi-stage builder 泄漏到 runtime） | `tests/test_docker_image_size.py` 断言 image size < 500MB（宽泛上限，防明显泄漏）；CI `docker-inspect` size gate | Layer 1 (Dockerfile) + Layer 2 (test) |

**Multi-layer 独立可测验证**（lesson #22 + lesson #28）：FM1/FM2 均有 Layer 1（config）与 Layer 3（smoke）独立测；FM3 有 schema snapshot + pytest 两侧独立可测；FM9 SEMVER drift 有 schema + pytest + arx client 三层独立测（第三层 defer）；relaxed-double test **不适用** —— distribution/CI/docs 无 "上层 shadow 下层" 结构。

## 实现任务 (Tasks)

### Task 1: pyproject.toml SEMVER + [project.scripts] + LTS extras

**Files**: Modify `pyproject.toml`；Create `tests/test_pyproject_scripts_declared.py`

**Step 1 · 证伪**：跑 `grep -n '^\[project\.scripts\]' pyproject.toml`；预期零命中（现状）。跑 `grep -n 'version = "0.1.0"' pyproject.toml`；预期命中一行（`:3`）。

**Step 2 · 写失败测试**：`tests/test_pyproject_scripts_declared.py` 断言 `tomllib.load()` 后 `data["project"]["scripts"]["arx-runner"] == "custos.cli.subcommands:main"` (Plan 11 lock) + `"custos" not in data["project"]["scripts"]` (legacy entry 已由 Plan 11 删) + `data["project"]["version"] == "0.2.0"`。跑 `uv run pytest tests/test_pyproject_scripts_declared.py -v`，预期 FAIL（Plan 12 未执行时 script 表内容与 Plan 11 landed 后不同 / version 仍是 0.1.0）。

**Step 3 · 实现**（依赖 Plan 11 已 landed —— Plan 11 执行时已加 `arx-runner` entry；Plan 12 此处只 add optional-dependencies + hatch build hook）：
- **pyproject.toml `[project.scripts]` 已由 Plan 11 lock**（`arx-runner = "custos.cli.subcommands:main"` 单一 entry），Plan 12 不改 script 表本身；版本 `0.2.0` 也由 Plan 11 已 bump（Plan 11 clean-break = breaking release，与 Plan 12 LTS 起点同版）
- `[project.optional-dependencies]` 加 `lts = ["sigstore>=3", "pytest-docker>=3"]`（signing + docker test 用）
- `[tool.hatch.build.hooks.custom]` 加 SOURCE_DATE_EPOCH 支持

**Step 4 · 证实**：`uv run pytest tests/test_pyproject_scripts_declared.py -v` 全绿；`uv sync --extra lts` 无 error；`uv build` 产出 `dist/custos_runner-0.2.0-py3-none-any.whl` + `dist/custos_runner-0.2.0.tar.gz`。

**Step 5 · 提交**：`git add pyproject.toml tests/test_pyproject_scripts_declared.py && git commit -m "feat(custos): plan-12-t1 pyproject SEMVER 0.2.0 + [project.scripts] + lts extras"`

---

### Task 2: Dockerfile 多阶段 + non-root

**Files**: Create `Dockerfile`, `.dockerignore`, `tests/test_docker_non_root.py`；Modify `Makefile`

**Step 1 · 证伪**：`ls Dockerfile` 报 not exist（仓根）；`docker build . 2>&1 | head -3` 报 Dockerfile 不存在。

**Step 2 · 写失败测试**：`tests/test_docker_non_root.py` 用 `subprocess.run(["docker", "inspect", "--format", "{{.Config.User}}", "custos-runner:test"])` 断言 output != "" 且 != "root" 且 != "0"。跑 `uv run pytest tests/test_docker_non_root.py -v -m docker`，预期 FAIL（image not exist）。

**Step 3 · 实现**：
- `Dockerfile` 多阶段：`FROM python:3.12-slim AS builder` + `uv sync --extra nautilus` + `FROM python:3.12-slim AS runtime` + `USER 1000:1000` + `WORKDIR /opt/custos` + `ENTRYPOINT ["python", "-m", "custos"]`
- `.dockerignore` 排除 `.git/` / `.forge/` / `.venv/` / `tests/` / `examples/` / `docs/`
- `Makefile` 加 `docker-build: docker build -t custos-runner:test .`

**Step 4 · 证实**：`make docker-build && uv run pytest tests/test_docker_non_root.py -v -m docker` 全绿。

**Step 5 · 提交**：`git add Dockerfile .dockerignore Makefile tests/test_docker_non_root.py && git commit -m "feat(custos): plan-12-t2 multi-stage Dockerfile + non-root USER 1000"`

---

### Task 3: Wheel signing (sigstore keyless)

**Files**: Create `.github/workflows/scripts/sign-wheel.sh`, `tests/test_wheel_signature.py`；Modify `Makefile`

**Step 1 · 证伪**：`ls .github/workflows/scripts/sign-wheel.sh` 报 not exist；`sigstore --version` 检查工具存在（若无则加进 lts extras）。

**Step 2 · 写失败测试**：`tests/test_wheel_signature.py` 断言 `dist/*.whl.sigstore` 存在 + `sigstore verify identity` 通过（本地环境 skip via marker `@pytest.mark.ci_only`；CI 环境跑）。跑 `uv run pytest tests/test_wheel_signature.py -v -m ci_only`（本地 skip），CI 跑预期 FAIL。

**Step 3 · 实现**：`sign-wheel.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail
for whl in dist/*.whl; do
  sigstore sign --output-signature "${whl}.sigstore" "${whl}"
done
```
`Makefile` 加 `sign: sign-wheel.sh` target。

**Step 4 · 证实**：本地 `make dist && bash .github/workflows/scripts/sign-wheel.sh`（需 sigstore 交互 OIDC token，CI 跑）；CI 上 pytest 全绿。

**Step 5 · 提交**：`git add .github/workflows/scripts/sign-wheel.sh tests/test_wheel_signature.py Makefile && git commit -m "feat(custos): plan-12-t3 sigstore keyless wheel signing"`

---

### Task 4: CI release workflow

**Files**: Create `.github/workflows/release.yml`, `.github/workflows/scripts/verify-release.sh`

**Step 1 · 证伪**：`ls .github/workflows/release.yml` 报 not exist；`ls .github/workflows/scripts/verify-release.sh` 报 not exist。

**Step 2 · 契约验证**：写 job DAG（build-wheel → sign-wheel → build-docker → sign-docker → publish-pypi[optional flag]→ publish-ghcr → verify-release → release-notes），本 Task 走 doc/schema 契约验证，不写运行时 test（CI workflow 只能在 CI 环境跑）。写 `docs/release-workflow.md`（占位或内联到 `docs/reproducible-build.md`）说明 job DAG + trigger。

**Step 3 · 实现**：`.github/workflows/release.yml`：
- trigger: `on.push.tags = ['v*']`
- permission: `id-token: write`（sigstore OIDC）+ `packages: write`（GHCR）+ `contents: write`（release notes）
- 6 job 串行 DAG（DP2/DP1 决策落地）
- 环境 `python-version: 3.12`（`nautilus` extra 要求）

`verify-release.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:?version required}"
pip download custos-runner==$VERSION --no-deps -d /tmp/verify
sigstore verify identity /tmp/verify/*.whl \
  --cert-identity "https://github.com/the-alephain-guild/custos/.github/workflows/release.yml@refs/tags/v${VERSION}" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com"
docker pull ghcr.io/the-alephain-guild/custos:v${VERSION}
cosign verify ghcr.io/the-alephain-guild/custos:v${VERSION} \
  --certificate-identity "https://github.com/the-alephain-guild/custos/.github/workflows/release.yml@refs/tags/v${VERSION}" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

**Step 4 · 证实**：本地 `actionlint .github/workflows/release.yml` 无 error（如工具可用）；CI 真跑推迟到第一次 tag push（部分交付：workflow 定义 land 即算 T4 完成，实跑成功归 T9 close-out gate）。

**Step 5 · 提交**：`git add .github/workflows/release.yml .github/workflows/scripts/verify-release.sh && git commit -m "feat(custos): plan-12-t4 CI release workflow (wheel + docker + sig + verify)"`

---

### Task 5: CHANGELOG.md scaffold

**Files**: Create `CHANGELOG.md`；Modify `README.md`

**Step 1 · 证伪**：`ls CHANGELOG.md` 报 not exist；`grep -n "Not Included Yet" README.md` 命中 `:106-108`。

**Step 2 · 写失败测试**：`tests/test_lts_commitment_doc.py`（Task 6 覆盖）间接依赖 CHANGELOG.md 存在 —— 独立 assertion 于 Task 6，本 Task 只需 doc structural check。可选 `tests/test_changelog_exists.py`：断言 `CHANGELOG.md` 存在且含 `## [0.2.0]` section。

**Step 3 · 实现**：
- `CHANGELOG.md` Keep-a-Changelog 格式；顶部 `## [Unreleased]` + `## [0.2.0] - 2026-07-10`（首个 entry，含 `### Added`：sigstore wheel signing, non-root Dockerfile, LTS commitment, gateway contract v1）
- `README.md` § "Not Included Yet" 移除已交付项（wheel sig + docker + SEMVER + LTS + contract v1 + CONTRIBUTING + SECURITY），替换为「见 CHANGELOG.md / docs/lts-commitment.md」引用

**Step 4 · 证实**：`grep -n '^## \[0\.2\.0\]' CHANGELOG.md` 命中一行；`grep -n "Not Included Yet" README.md` 命中缩减到剩余项（Telemetry uplink bridge 仍留）。

**Step 5 · 提交**：`git add CHANGELOG.md README.md && git commit -m "docs(custos): plan-12-t5 CHANGELOG.md scaffold + README trim Not Included Yet"`

---

### Task 6: LTS commitment + upgrade path docs

**Files**: Create `docs/lts-commitment.md`, `docs/upgrade-path.md`, `tests/test_lts_commitment_doc.py`

**Step 1 · 证伪**：`ls docs/lts-commitment.md` 报 not exist；`ls docs/upgrade-path.md` 报 not exist。

**Step 2 · 写失败测试**：`tests/test_lts_commitment_doc.py`：
```python
def test_lts_doc_has_required_sections():
    text = Path("docs/lts-commitment.md").read_text()
    assert "## EOL Window" in text
    assert "## Security Patch SLA" in text
    assert "## Release Cadence" in text
    assert "12 months" in text  # EOL commitment (DP7)
    assert "30 days" in text  # security patch SLA (DP7)
```
跑 `uv run pytest tests/test_lts_commitment_doc.py -v`，预期 FAIL（file not exist）。

**Step 3 · 实现**：
- `docs/lts-commitment.md`：
  - `## EOL Window`：每个 minor line EOL ≥ 12 months from release
  - `## Security Patch SLA`：CVE 公开后 30 days 内 patch release（best-effort）
  - `## Release Cadence`：quarterly best-effort
  - `## Upgrade Path` → 指向 `docs/upgrade-path.md`
  - `## Follow-up`：自动化 LTS status page 归 v1.x follow-up plan hook（未起草）
- `docs/upgrade-path.md`：0.x → 1.0 promote 判据（arx-79 wire ready + 3 consecutive minor 无 breaking change）+ minor line 升级步骤模板

**Step 4 · 证实**：`uv run pytest tests/test_lts_commitment_doc.py -v` 全绿。

**Step 5 · 提交**：`git add docs/lts-commitment.md docs/upgrade-path.md tests/test_lts_commitment_doc.py && git commit -m "docs(custos): plan-12-t6 LTS commitment (EOL 12mo + SLA 30d) + upgrade path"`

---

### Task 7: Gateway contract v1 spec + backward-compat gate

**Files**: Create `docs/gateway-contract/v1/README.md`, `docs/gateway-contract/v1/enrollment.schema.json`, `docs/gateway-contract/v1/deployment_status.schema.json`, `docs/gateway-contract/v1/telemetry_snapshot.schema.json`, `docs/gateway-contract/v1/heartbeat.schema.json`, `tests/test_gateway_contract_v1_backward_compat.py`, `tests/fixtures/gateway_contract_v1_golden/*.schema.json`

**Step 1 · 证伪**：`ls docs/gateway-contract/` 报 not exist；grep 实证契约来源 `grep -n "async fn validate_enrollment\|async fn record_deployment_status\|async fn ingest_telemetry\|async fn handle_heartbeat" ../arx/backend/crates/coordination/src/custos.rs`，预期 4 method 各命中（第 11 / 13 / 20 / 26 行），Step 1.5 gate 契约锚点已在上下文段落固化。

**Step 2 · 写失败测试**：`tests/test_gateway_contract_v1_backward_compat.py`：
```python
def test_schemas_present():
    for name in ("enrollment", "deployment_status", "telemetry_snapshot", "heartbeat"):
        assert Path(f"docs/gateway-contract/v1/{name}.schema.json").exists()

def test_schemas_backward_compat_vs_golden():
    for name in ("enrollment", "deployment_status", "telemetry_snapshot", "heartbeat"):
        current = json.loads(Path(f"docs/gateway-contract/v1/{name}.schema.json").read_text())
        golden = json.loads(Path(f"tests/fixtures/gateway_contract_v1_golden/{name}.schema.json").read_text())
        # additive-only: golden required must be subset of current required
        assert set(golden.get("required", [])) <= set(current.get("required", []))
        # additive-only: golden properties must all still exist
        for key in golden.get("properties", {}):
            assert key in current.get("properties", {}), f"removed property: {key}"
```
跑 `uv run pytest tests/test_gateway_contract_v1_backward_compat.py -v`，预期 FAIL（schema 与 golden 均不存在）。

**Step 3 · 实现**：4 JSON Schema 文件 + `README.md`（索引 + additive-only rule + v2 breaking protocol）+ `tests/fixtures/gateway_contract_v1_golden/*.schema.json`（首次 land 时 golden = schema copy，作为 baseline）

Enrollment schema 示例：
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://custos.the-alephain-guild/gateway-contract/v1/enrollment.schema.json",
  "title": "EnrollmentPayload v1",
  "type": "object",
  "required": ["token_sha256", "runner_id"],
  "properties": {
    "token_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "runner_id": { "type": "string", "maxLength": 128 },
    "capabilities": { "type": "array", "items": { "type": "string" } }
  },
  "additionalProperties": false
}
```
其余 3 schema 逐一对齐 `custos.rs:13-30` typed method 参数 + 现有 `nats_client.py` envelope。

**Step 4 · 证实**：`uv run pytest tests/test_gateway_contract_v1_backward_compat.py -v` 全绿；`jsonschema` CLI 或 `check-jsonschema` 校验 4 schema syntactic valid。

**Step 5 · 提交**：`git add docs/gateway-contract/ tests/test_gateway_contract_v1_backward_compat.py tests/fixtures/gateway_contract_v1_golden/ && git commit -m "feat(custos): plan-12-t7 gateway contract v1 JSON Schema + backward-compat golden gate"`

---

### Task 8: Reproducible build doc + verification test

**Files**: Create `docs/reproducible-build.md`, `tests/test_reproducible_build.py`

**Step 1 · 证伪**：`ls docs/reproducible-build.md` 报 not exist；`env | grep SOURCE_DATE_EPOCH` 未设。

**Step 2 · 写失败测试**：`tests/test_reproducible_build.py`：
```python
@pytest.mark.slow
def test_wheel_bytes_identical_across_rebuild():
    epoch = "1704067200"  # 2024-01-01 UTC fixed
    env = {**os.environ, "SOURCE_DATE_EPOCH": epoch}
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        subprocess.run(["uv", "build", "--out-dir", d1], check=True, env=env)
        subprocess.run(["uv", "build", "--out-dir", d2], check=True, env=env)
        h1 = sha256(sorted(Path(d1).glob("*.whl"))[0].read_bytes()).hexdigest()
        h2 = sha256(sorted(Path(d2).glob("*.whl"))[0].read_bytes()).hexdigest()
        assert h1 == h2
```
跑 `uv run pytest tests/test_reproducible_build.py -v -m slow`，预期 FAIL（无 build hook 保 epoch）。

**Step 3 · 实现**：
- `docs/reproducible-build.md`：`SOURCE_DATE_EPOCH` 用法 + `uv.lock` freeze + 二次 build verification 步骤
- pyproject.toml `[tool.hatch.build.hooks.custom]` 或 env 传递保 SOURCE_DATE_EPOCH 影响 zip entry mtime（hatchling ≥ 1.20 已 native 支持）

**Step 4 · 证实**：`SOURCE_DATE_EPOCH=1704067200 uv run pytest tests/test_reproducible_build.py -v -m slow` 全绿（本地 slow，CI nightly job）。

**Step 5 · 提交**：`git add docs/reproducible-build.md tests/test_reproducible_build.py pyproject.toml && git commit -m "feat(custos): plan-12-t8 reproducible build (SOURCE_DATE_EPOCH + bytes-identical rebuild test)"`

---

### Task 9: 文档收尾 (close-out) — 强制末尾任务

**Files**: Create `CONTRIBUTING.md`, `SECURITY.md`；Modify `.forge/README.md`, `CLAUDE.md`, `README.md`, `docs/lts-commitment.md`（引用 Plan 11 已 lock 的 `arx-runner` script name — 无占位、无联动核对，Plan 11 已 landed 是硬前置）

**动作清单**：

1. **顶部 status flip**：`.forge/plans/2026-07/12-custos-distribution-signed-wheel-docker-lts.md` 顶部 `Status: 🔲 → ✅ Completed` + `Completed: YYYY-MM-DD`
2. **索引更新**：`.forge/README.md` 现有 plan 索引表加 Plan 12 行；`.forge/README.md:63-72` 执行顺序段加 Plan 12 描述
3. **权威文档同步**：
   - `CLAUDE.md` § 2 子系统边界段末加一行「契约 v1 冻结于 `docs/gateway-contract/v1/`（Plan 12 close-out 落地）」
   - `CLAUDE.md` § 6 常用命令表加 `make release` / `make verify-release` 两行
   - `README.md` § "Not Included Yet" 剩余项精简（已在 T5 处理）
   - `docs/lts-commitment.md` 直接引用 `arx-runner` (Plan 11 landed lock)，无联动核对分支；`CHANGELOG.md` §0.2.0 breaking note 已在 T5 landing 时包含 Plan 11 clean-break 项（legacy `python -m custos` 删除 + SopsAgeVault 删除 + `~/.custos/` 退休）+ Plan 12 distribution 项（signed wheel + docker + SEMVER + gateway contract v1）—— 两 plan 同版发布
4. **CONTRIBUTING.md + SECURITY.md 补齐**：本 Task 承载（原 T5 只 CHANGELOG，本 T9 补面向外部审计员/贡献者的公开仓门面）
   - `CONTRIBUTING.md`：测试运行 (`make verify`) + coding style (`code-style.md` pointer) + PR 流程 + DCO / CLA 说明
   - `SECURITY.md`：vuln 上报入口（GitHub Security Advisories）+ 30d SLA（对齐 `docs/lts-commitment.md`）
5. **版本升级**：pyproject.toml version 已在 T1 → `0.2.0`；本 Task 无需再升
6. **完成报告章节**（plan 文件末尾）：简要说明实际产出 / IMPROVEMENT 兑现位置 / 跨仓库同步动作
7. **commit**：`git add .forge/plans/2026-07/12-*.md .forge/README.md CLAUDE.md README.md CONTRIBUTING.md SECURITY.md && git commit -m "docs(custos): mark plan 12 as completed + CONTRIBUTING/SECURITY + CLAUDE.md sync"`

**验证**：
- `grep -c '## \[0\.2\.0\]' CHANGELOG.md` 命中 1
- `ls Dockerfile CHANGELOG.md CONTRIBUTING.md SECURITY.md docs/lts-commitment.md docs/upgrade-path.md docs/reproducible-build.md docs/gateway-contract/v1/README.md` 全存在
- `uv run pytest tests/test_pyproject_scripts_declared.py tests/test_docker_non_root.py tests/test_lts_commitment_doc.py tests/test_gateway_contract_v1_backward_compat.py -v` 全绿（跳过 ci_only / slow marker）
- `make verify` 全绿

## 验证清单 (Verification)

- [ ] `make verify` 全绿（含 T1/T2/T3/T6/T7/T8 新增 test）
- [ ] `make dist` 产出 `dist/custos_runner-0.2.0-py3-none-any.whl` + `.tar.gz`
- [ ] `make docker-build` 产出 `custos-runner:test` image，`docker inspect USER` != root
- [ ] `.github/workflows/release.yml` `actionlint` 无 error（如工具可用）
- [ ] `docs/gateway-contract/v1/` 4 schema JSON syntactic valid + 与 golden fixture backward-compat
- [ ] `docs/lts-commitment.md` 含 EOL Window + Security Patch SLA + Release Cadence 三 section
- [ ] `CHANGELOG.md` 首个 `## [0.2.0]` entry 完整
- [ ] Step 1.5 gate 所有引用的前置原语契约（CustosGateway trait / pyproject.toml 现状 / arx custos.rs 4 method）均有 file:line 证据锚（上下文段已列）
- [ ] Language Policy: 所有 `.py` / `.sh` / `Dockerfile` / `.yml` 注释 + log + error msg 全英文（CLAUDE.md § Language Policy Red Line）
- [ ] 无死代码 / 未使用配置字段
- [ ] **Plan 11 已 landed on main** (breaking release 0.2.0, `arx-runner` single entry) 前置 gate 通过 —— Plan 12 execute 启动前 team-lead 独立 grep `git log --oneline | grep 'plan 11'` 命中 squash commit + `grep '"arx-runner"' pyproject.toml` 命中 1 + `grep 'SopsAgeVault' src/custos/core/credential_vault.py` 命中 0 (Plan 11 已删)

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|------|--------|-----------|-------|
| T1 pyproject SEMVER + scripts + lts extras | 🔲 | | DP4 (0.x LTS 起点) + DP5 **RESOLVED** (Plan 11 lock `arx-runner`) — T1 只加 `[project.optional-dependencies].lts` + hatch build hook；`[project.scripts]` + version bump 已由 Plan 11 落地 |
| T2 Dockerfile 多阶段 + non-root | 🔲 | | DP2 (GHCR target) |
| T3 Wheel signing (sigstore) | 🔲 | | DP1 (sigstore keyless) |
| T4 CI release workflow | 🔲 | | DP2 + DP1 组合；实跑推迟 T9 gate |
| T5 CHANGELOG scaffold | 🔲 | | Keep-a-Changelog 格式 |
| T6 LTS commitment + upgrade path | 🔲 | | DP7 (EOL 12mo + SLA 30d) |
| T7 Gateway contract v1 spec | 🔲 | | DP3 (JSON Schema) + DP8 (snapshot golden) |
| T8 Reproducible build | 🔲 | | DP6 (SOURCE_DATE_EPOCH + uv.lock) |
| T9 Close-out (CONTRIBUTING + SECURITY + index sync) | 🔲 | | lesson #35 script name fanout 联动检 |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|------|------|------|--------|
| （待实施填充） | — | — | — |

## 完成报告 (Close-out Report)

*(执行完成后在此填写)*

- **完成日期**: {YYYY-MM-DD}
- **总 Task 数**: 9
- **偏离数**: {N}（详见偏离日志）
- **验证结果**: 全部通过 / 部分通过
- **遗留项**:
  - ~~Plan 11 script name lock 联动~~ **RESOLVED** — Plan 11 clean-break 已 lock `arx-runner` 单一 entry (2026-07-10 CEO directive)
  - arx-79 CustosGateway wire ready 后 1.0.0 promote 判据触发 (upgrade-path.md 规则)
  - 自动化 LTS status page（follow-up plan）
  - Docker image bit-for-bit 复现（buildkit timestamp workstream，follow-up plan）

---

## Foundation Scan iteration log (lesson #33b)

- **Iteration 1 · 直接引用（空间维 lesson #14）**：读 evidence-scout §L3 verbatim + custos README.md + pyproject.toml；确认 `[project.scripts]` 零 / `Dockerfile` 只 example / `.github/` 不存在 / 无 CHANGELOG.md / 无 LTS 文档。
- **Iteration 2 · 命名空间维（lesson #30）**：grep arx `coordination/src/custos.rs` CustosGateway trait 4 typed method 逐字锚点 + `raw_call` supertrait；分发名 `custos-runner` vs import name `custos` 分离固化；确认 contract v1 语义是 NATS payload + Rust trait 双面（非 REST HTTP）→ DP3 JSON Schema 而非 OpenAPI。
- **Iteration 3 · 时间维 + 影响面维（lesson #33 / #33b）**：as-of 2026-07-10 Plan 05 close-out `e82825d` + Plan 04 close-out `d0dd537`；上游依赖 Plan 11 script name（soft dep，DP5 占位保护 lesson #35 fanout）+ arx-79 wire（Plan 12 只出契约，不 block arx-side wire）；停扫判据 —— 3 iteration 覆盖空间 / 命名空间 / 时间 / 影响面四维，deliverable 全部 file:line 锚定，无更深层。

## Applicable lessons (self-audit)

- **lesson #14 / #30 / #33 / #33b Foundation Scan 四维**：已 3 iteration 覆盖，上下文段 file:line 锚点完整
- **lesson #17 failure-mode ≥4**：FM1-FM11 共 11 条覆盖，multi-layer 独立可测（含 FM8 sigstore/cosign key rotation / FM9 SEMVER minor 隐性破坏 arx client / FM10 LTS EOL 未公告 audit-non-silence / FM11 docker image size 膨胀）
- **lesson #22 multi-layer 独立可测**：FM1/FM2/FM3 均 ≥2 layer 独立测；relaxed-double 不适用（无 shadow 结构）
- **lesson #28 复合契约分句 → guard 对照**：目标段「signed wheel + docker image + SEMVER + LTS + gateway contract」5 分句 → T3 / T2+T4 / T1+T5 / T6 / T7 逐句映射 file:line
- **lesson #31 multi_session_scope**：false（9 Task，中粒度 6-10h）；CI 首跑失败风险登记
- **lesson #35 boundary constant rename fanout**：script name（DP5）+ contract v1 field name（T7 golden snapshot）双 fanout gate；rename 时 T9 联动检 pyproject.toml + Dockerfile + docs + README
- **lesson #37 grep 权威源实证**：CustosGateway trait 逐字 grep `arx custos.rs:9-30`；pyproject.toml 现状 grep 实证；对称推理陷阱 —— DP1 sigstore vs GPG / DP3 JSON Schema vs OpenAPI 均基于契约实证决策，非对称直觉
- **lesson #38 CEO override**：不适用（Plan 12 无 CLAUDE.md 红线全域触发 / 无 触发条件框架 override）
- **lesson #40 close-out 声明精确化**：T9 close-out 报告显式区分 code-level test coverage / runtime wire / defer scope（CI 首跑 defer 到 T9 gate + arx-79 wire defer 到 follow-up）
