# Plan 12 review (claude, custos)

- **Plan**: `.forge/plans/2026-07/12-custos-distribution-signed-wheel-docker-lts.md`
- **Reviewer**: claude (opus-4-7[1m], Plan-team reviewer role)
- **Base**: as-of 2026-07-10 pyproject.toml / README / Makefile / docs 现状 grep 实证
- **Depends on**: Plan 11 (co-drafted, hard dep)
- **Verdict**: **REQUEST_CHANGES** — 存在 2 处 CRITICAL 逻辑/契约错误 (Task 7 backward-compat 断言方向反转; Task 2 Step 3 与 File Inventory 冲突, ENTRYPOINT 混用 Plan 11 已删的 `python -m custos`), 6 处 HIGH 需修正 (Dockerfile pip install 源、GitHub Actions `permission` 拼写、Plan 11↔12 payload 字段名 `token_hash` vs `token_sha256` 漂移、arx-side `~=0.2` PEP 440 语义 vs 意图不符、CI 6-job vs 实列 8-job、T4 sigstore CLI flag 未 grep 实证), 7 处 MEDIUM, 4 处 LOW。修正后可通过。

**计数**: 2 Critical / 6 High / 7 Medium / 4 Low / 3 Positive

---

## CRITICAL findings

### C1 — Task 7 `test_schemas_backward_compat_vs_golden` 断言方向反转, additive-only 保护完全失效

**位置**: Plan 12 line 362

```python
# additive-only: golden required must be subset of current required
assert set(golden.get("required", [])) <= set(current.get("required", []))
```

**问题**: 断言方向反了。Additive-only 语义 = `current` (新版) **不能新增** required 字段 (新增 required = 老 producer 不发新字段 → validation fail = **breaking**)。

正确断言应为:
```python
# additive-only: current required must be subset of golden required (禁止新增 required)
assert set(current.get("required", [])) <= set(golden.get("required", []))
```

反例 (Plan 12 当前断言下会误放行):
- Golden `required = ["token_hash", "runner_id"]`
- Current `required = ["token_hash", "runner_id", "capabilities"]` (新增了 `capabilities` 为 required)
- Plan 12 断言: `{"token_hash","runner_id"} <= {"token_hash","runner_id","capabilities"}` = True → **通过**
- 但这是 breaking change (老 producer 不发 capabilities → arx 侧 validation fail)

**影响**: DP8 声称 "修改 required 或删除 field → FAIL" 但 Plan 12 落地的 test 事实上**允许新增 required = breaking**。FM3 (contract v1 breaking change 静默) 与 FM9 (SEMVER minor 隐性破坏 arx client) 的核心 gate 失守; Plan 12 全部 "additive-only" 承诺无实际执行力。

**修法**: 断言方向反转 + 加 properties 覆盖检 (golden 里存在的 property key 必须仍在 current 内, 用于抓 "删除 field" 情况; Plan 12 line 364-365 已写此半, 保留)。追加 negative test 证明 (a) 新增 optional field 通过, (b) 新增 required field 阻断, (c) 删除 property 阻断。

---

### C2 — Task 2 Step 3 与 File Inventory 冲突: Dockerfile `ENTRYPOINT ["python", "-m", "custos"]` 与 DP5 resolved 状态相悖, 且指向 Plan 11 已删的 stub

**位置对照**:
- Plan 12 line 149 (File Inventory): `` `ENTRYPOINT ["arx-runner", "start"]` (Plan 11 lock, 无占位)``
- Plan 12 line 225 (Task 2 Step 3): ``+ `ENTRYPOINT ["python", "-m", "custos"]` ``

**问题**: DP5 已 RESOLVED (Plan 11 clean-break) 后, `python -m custos` 入口被 Plan 11 Task 8 **删除**且替换为 5 行 stub `sys.exit(2)` + stderr pointer (Plan 11 line 399-421)。Plan 12 Task 2 Step 3 若照抄 `ENTRYPOINT ["python", "-m", "custos"]`, docker container 启动即 exit 2, image 全然不可用。

**且 `test_docker_non_root.py` (line 222) 只查 USER 字段, 不查 ENTRYPOINT 是否可跑** → 单元测试全绿但 image 实际启动失败, 是典型 lesson #17 (happy-path 测试全绿 ≠ 失败模式覆盖) 复发 pattern。

**关联 T2 test 缺口**: 无 `test_docker_entrypoint_runs_arx_runner_help_returns_zero` 类 smoke。

**修法**:
1. Task 2 Step 3 更新为 `ENTRYPOINT ["arx-runner", "start"]` 对齐 File Inventory + DP5 resolved
2. 追加 T2 test: 至少 `docker run --rm <image> arx-runner --help` exit 0 (smoke)
3. verify-release.sh 已有 `docker run --rm ... --help` (line 285 隐含) — 明说 image entrypoint 契约

---

## HIGH findings

### H1 — Task 2 Dockerfile `pip install custos-runner[nautilus]` 首次 build 会 fail (PyPI 未发布)

**位置**: Plan 12 line 149

**问题**: File Inventory 描述 runtime stage `pip install custos-runner[nautilus]`。但 `custos-runner` 是本 plan 才首次准备发布的 wheel; PyPI 上 0.2.0 还未发布, 而 CI 里 `build-docker` job 早于 `publish-pypi` 执行 → 首次 CI run 拿不到 wheel, docker build fail。

**且这是鸡生蛋**: 甚至 tag land 前本地 `make docker-build` 也 fail (`0.2.0` 未上 PyPI)。

**修法**: Docker builder stage 直接消费本地 wheel:
```dockerfile
FROM python:3.12-slim AS builder
COPY --from=build-artifacts dist/custos_runner-*.whl /tmp/
RUN pip install --no-index --find-links=/tmp /tmp/custos_runner-*.whl[nautilus]
```
或用 `uv sync --extra nautilus --frozen` on source tree copy。CI 里 job DAG 保 `build-wheel` → `build-docker` (wheel artifact 作 input) 顺序。Plan 12 Task 2 Step 3 需补此细节。

---

### H2 — GitHub Actions permission YAML key 拼写错误 (`permission` vs `permissions`)

**位置**: Plan 12 line 269

```
permission: `id-token: write`（sigstore OIDC）+ `packages: write`（GHCR）+ `contents: write`（release notes）
```

**问题**: GitHub Actions workflow YAML 顶级 key 是 **`permissions`** (复数); `permission` (单数) 是无效 key, 会被 YAML parser 静默忽略, workflow 使用默认 permission set → sigstore OIDC token 无 write scope → `id-token` 获取失败 → **sigstore signing 静默降级为 fail**。

**FM7 "GHCR / PyPI publish 失败静默"** 本应抓 workflow 失败, 但 permission 缺失导致的 sigstore fail 会在 pipeline 更下游 job 才炸, 可能 partial-publish 已发生 (packages 已 push 但 sig 未签)。

**修法**: 该 workflow 落地为 `.yml` 时明确 `permissions:` (复数)。plan 文本此处修辞澄清即可; 但强调 plan 12 T4 Step 3 里需要 executor 落地 workflow 时用正确 key。

**关联 verify-release.sh 契约再复检**: 若 permission 缺失, sig bundle 根本不存在, `sigstore verify` 会因 `.sigstore` 文件 not found 立即 fail — Layer 3 兜底存在但发生在 publish 之后。

---

### H3 — Plan 11 ↔ Plan 12 enrollment payload 字段名漂移: `token_hash` vs `token_sha256` (lesson #35 boundary constant fanout)

**证据锚点对照**:
- Plan 11 Task 4 Step 3 (line 275): `Compute token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()`
- Plan 11 Task 4 test (line 265): `assert mocked call payload = {"token_hash": <sha256 hex>, "runner_id": <id>, ...}`
- Plan 12 Task 7 enrollment.schema.json 示例 (line 378): `"required": ["token_sha256", "runner_id"], "properties": {"token_sha256": {...}}`

**问题**: 两 plan 共同起草 (同一 wave), 但对同一 wire field 用了两个不同名字。若 Plan 11 landed 后 arx-78 接受的 payload key 是 `token_hash`, 而 Plan 12 落地的 v1 契约 schema 声明 `token_sha256` 为 required, arx 侧或 runner 侧的实际 payload 与契约永久不一致 → **v1 从落地日起就 broken**。

**lesson #35 boundary constant fanout 精髓** = "跨模块 wire 字段名必须 single-source", Plan 12 self-audit line 515 明说 "contract v1 field name 单 fanout gate", 但此漂移证明 fanout 未做。

**修法**:
1. 判定单一真理源 (推荐 `token_hash` — 更泛用, `_sha256` 可能对下游算法演化留死结构)
2. Plan 12 Task 7 enrollment.schema.json required 字段 rename 为 `token_hash` + `pattern` 保 `^[a-f0-9]{64}$`
3. 若最终定为 `token_sha256`, Plan 11 Task 4 Step 3 + test payload 同步 rename (Plan 11 尚未 land, 可编辑)
4. Plan 12 Foundation Scan iteration log 补 iteration 4 "跨 plan wire 字段名 fanout 核对"

---

### H4 — arx-side `~=0.2` PEP 440 语义与 "禁自动升 major" 意图不符

**位置**: Plan 12 line 115

**问题**: PEP 440 `~=` compatible release specifier 含义:
- `~=X.Y` 展开为 `>=X.Y, <(X+1).0`
- `~=X.Y.Z` 展开为 `>=X.Y.Z, <X.(Y+1).0`

所以 `~=0.2` = `>=0.2, <1.0`, 允许所有 0.x minor 升级。但按 SemVer §4 (0.x pre-1.0), **minor bump 允许 breaking change** (Plan 12 DP4 也承认: "允许契约小幅演进"), 且 Plan 12 SEMVER 承诺表 (line 110) 明说 MAJOR 允许 breaking。

对 arx-side client 而言, `~=0.2` 允许 0.2.x → 0.3.x → 0.9.x 自动 pip resolve, 而 0.x minor bump 内可以 breaking → 意图 "禁自动升 major" 与实际 "允许自动过 0.x 所有 minor 含 breaking" 不匹配。

**修法**: 
- 若目标是 "只允许 patch 自动升": 用 `~=0.2.0` (即 `>=0.2.0, <0.3.0`)
- Plan 12 SEMVER 承诺表 line 115 明写具体 spec 与展开范围, 避免歧义
- 补 CHANGELOG.md 首个 entry 说明本项建议给 arx 侧 client 采用哪种 pin

---

### H5 — CI job DAG 计数不一致 (T4 Step 2 "6 job" vs 实列 8 job)

**位置**:
- Plan 12 line 91 (架构段): 未点明数字, "wheel build → sign → publish to PyPI + docker build → sign → publish to GHCR + release notes gen"
- Plan 12 line 265 (T4 Step 2): "写 job DAG (build-wheel → sign-wheel → build-docker → sign-docker → publish-pypi[optional flag] → publish-ghcr → verify-release → release-notes)" = **8 job**
- Plan 12 line 271 (T4 Step 3): "6 job 串行 DAG (DP2/DP1 决策落地)"

**问题**: 6 vs 8 内部矛盾。若合并某些 job (如 sign 与 publish 合一), Plan 12 应明说合并规则; 否则 executor 无法确定是 6 job 还是 8 job workflow 结构。

**关联**: `verify-release` 是 post-publish smoke, 与 publish-pypi/ghcr 是不同 job; `release-notes` 也是独立 job。8 job 更接近实描述。

**修法**: T4 Step 3 更新为 "8 job 串行 DAG"; 或若确要合并, 显式描述合并原则 (如 "build-wheel + sign-wheel 合 job" 因两者共 artifact + workspace)。

---

### H6 — sigstore-python 3.x CLI flag `--output-signature` 未 grep 实证 (lesson #37 spawner 元层)

**位置**: Plan 12 line 248 (T3 Step 3):
```bash
sigstore sign --output-signature "${whl}.sigstore" "${whl}"
```

**问题**: sigstore-python 3.x CLI `sign` command 在 3.x 中默认输出 bundle 到 `<artifact>.sigstore`, flag 名可能是 `--bundle` (3.0+) 或 `--output-signature` (2.x legacy)。**Plan 12 未 grep 实证 sigstore-python 3.x 实际 flag**, 是 lesson #37 (spawner 元层编辑 spec 前必 grep 实证 API 名) 在 CLI 引用场景的复现。

同样 line 279-286 verify-release.sh 中 `sigstore verify identity <artifact> --cert-identity ...` — sigstore-python 3.x subcommand 排布 (`verify` 下有 `identity` / `github-actions` 等 subcommand) 需实证。

**修法**:
1. `pip install sigstore` (或 uv extra) 后 `sigstore sign --help` grep 实证正确 flag
2. Plan 12 明说 sigstore 版本 pin (Plan 12 line 208 只说 `sigstore>=3`, 未 pin 具体 minor); 记录 `sigstore==X.Y.Z` 到 lts extra, 避免 sigstore 自身 major bump 破坏 workflow
3. cosign 同理需 pin 版本 (Plan 12 全文未提 cosign 版本)

**UNVERIFIED from claude side**: 我未运行 `sigstore --help`; 建议 executor 落地时先 grep 实证。

---

## MEDIUM findings

### M1 — SEMVER MINOR 承诺内部矛盾: `additionalProperties: false` 例外与 "additive-only" 冲突

**位置**: Plan 12 line 111
> MINOR: additive-only: 新增 gateway-contract v1 field (`additionalProperties: false` 例外须 major)

**问题**: 例外句表述不清。既然所有 v1 schema 都写了 `additionalProperties: false` (line 384), 那么按此规则任何新增 field 都算 breaking 需 major bump → **v1 minor bump 事实上不能新增 field**。这与 DP8 "新增 field OK" 直接矛盾。

**修法**: 
- 澄清语义: 是否 `additionalProperties: false` schema 只做 v2 时才允许新增 field?
- 或补 producer/consumer 视角: 从 arx 消费视角 additive; 从新 field 未同步到旧 consumer 视角 breaking
- 建议弱化为: "新增 optional field: MINOR (需两侧同步部署); 新增 required field: MAJOR"

### M2 — SEMVER PATCH "内部重构 (无外部 observable 变化)" 与 uv.lock 变化冲突

**位置**: Plan 12 line 112

**问题**: 若 patch 升级依赖 (如 nats-py 2.9.1 → 2.9.2), uv.lock 变化, arx 或其他消费方 pip resolve 会拿到不同 transitive deps → 存在 observable 变化风险。SEMVER PATCH 定义应明确 pyproject.toml `[project]` 依赖版本 pin 是否允许升 (含 lock file 增减)。

**修法**: PATCH 允许项补一行: "依赖 patch/minor 版本升级 (uv.lock 同步 commit); 不允许依赖 major 版本升级 (归 MINOR)"。

### M3 — hatchling SOURCE_DATE_EPOCH 原生支持 UNVERIFIED

**位置**: Plan 12 line 418

**问题**: Plan 12 声称 "hatchling ≥ 1.20 已 native 支持" SOURCE_DATE_EPOCH。但 File Inventory line 148 又列出 `[tool.hatch.build.hooks.custom]` 加 SOURCE_DATE_EPOCH — 若 native 支持存在, 无需 custom hook。表面矛盾。

**修法**: executor 落地 T8 前 grep hatchling 版本 changelog + 官方 docs 实证 SOURCE_DATE_EPOCH 支持路径; 若 native 支持存在, 只需 CI 里 `export SOURCE_DATE_EPOCH=<epoch>` 即可, 不需 custom hook; 若不存在, 明写 custom hook 代码。**UNVERIFIED from claude side**。

### M4 — T8 test 只测正例, 缺证伪对照

**位置**: Plan 12 line 402-412

**问题**: `test_wheel_bytes_identical_across_rebuild` 只在 `SOURCE_DATE_EPOCH` 固定时测 sha256 一致, 但未跑对照 (无 epoch 时 sha256 不同) 证明 reproducible 机制真的靠 epoch 发挥作用。若 hatchling native 就 deterministic (不需 epoch), test 全绿 = false positive, 未来 hatchling 版本变化导致失去 determinism 时 test 也检不出。

**修法**: 补对照测试:
```python
@pytest.mark.slow
def test_wheel_bytes_differ_without_epoch():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
        subprocess.run(["uv", "build", "--out-dir", d1], env=env, check=True)
        time.sleep(2)  # ensure mtime differs
        subprocess.run(["uv", "build", "--out-dir", d2], env=env, check=True)
        # 期待不同 (或跳过若 hatchling native 就 deterministic 无需 epoch)
```

### M5 — Docker image size < 500MB (FM11) 阈值过严, 高 false-positive 风险

**位置**: Plan 12 line 191

**问题**: python:3.12-slim base ~150MB + `[nautilus]` extra 拉 pandas + numpy + pandas_ta vendored + nautilus_trader wheel → 保守估计 400-550MB。500MB 阈值紧, CI 会 flaky-fail (pandas 或 numpy 一次 minor 升级即超阈)。

**修法**: 放宽到 700-800MB, 或改为 "监控阈" (warning at 500MB, fail at 800MB); FM11 目标是抓 "明显 multi-stage builder 泄漏", 不是限制正常增长。

### M6 — CI trigger `v*` tag 含 rc, rc 是否自动 publish 未明说

**位置**: Plan 12 line 268: `on.push.tags = ['v*']`

**问题**: `v*` 匹配所有 v 前缀 tag 含 `v0.2.0-rc.1`。SEMVER 承诺表 (line 113) 明说 "rc 阶段允许 breaking 回滚", 若 rc 也自动 publish 到 PyPI/GHCR 会污染稳定 tag 序列 (rc release 后回滚 stable release 有版本号连续性问题)。

**修法**: 
- 改 tag pattern 为 `v[0-9]+.[0-9]+.[0-9]+` (只匹配 stable)
- 或分 workflow: `on.push.tags: ['v[0-9]+.[0-9]+.[0-9]+']` 跑 stable release, `on.push.tags: ['v[0-9]+.[0-9]+.[0-9]+-rc.*']` 跑 pre-release (publish 到 PyPI 的 pre-release channel)
- 明说 publish-pypi 的 optional flag 何时从 `false` 转 `true` (Plan 12 未说 optional 从哪读: workflow_dispatch input? env var? 需明确)

### M7 — arx 侧 CustosGateway trait 契约 anchor UNVERIFIED from custos side (跨仓 dep)

**位置**: Plan 12 line 54-60

**问题**: Plan 12 声称 arx `backend/crates/coordination/src/custos.rs:9-30` 有 4 typed async method + `raw_call` supertrait, 逐字方法签名列在 line 57-60。但 custos 独立仓库 clone 后**无法 grep arx 源码**, 无法本地实证。若 arx 侧 trait 签名 (方法名 / 参数顺序 / return type) 与 Plan 12 声称不符, v1 schema 契约与 trait "对齐" 承诺失守。

**修法**: 
- Task 7 Step 1 补 evidence anchor 声明: "arx-side trait 签名以 arx-Plan 78 (in-flight) close-out marker 为准; Plan 12 落地时 CI 或 executor 需 fetch arx repo 侧 grep 复核"
- 或在 arx-79 wire ready follow-up plan 里补契约反射对齐检 (Foundation Scan 影响面维 lesson #33b)
- Foundation Scan iteration log 补 iteration 4: "arx-side wire UNVERIFIED; contract 层单侧声明, 待 arx-79 wire close-out 补对齐检"

---

## LOW findings

### L1 — FM10 test 只查 doc 3 section 存在, 不查 EOL 日期表内容 (lesson #25 反 fabricated)

**位置**: Plan 12 line 320-327

**问题**: `test_lts_commitment_doc.py` 只查 `"## EOL Window" in text` + `"12 months" in text` + `"30 days" in text`, 未查具体的 EOL 日期表条目 (如 "0.2.x line EOL 2027-Q3")。若未来 doc 内 EOL 表被 accidentally 空掉但 header 还在, test 仍然全绿 → 承诺失守但检不出。

**修法**: 追加断言 doc 内有形如 `| 0.\d+.x | \d{4}-\d{2}-\d{2}` 的 EOL 表行 (regex 抓一行以上)。

### L2 — SECURITY.md 缺 "no legal warranty" 免责声明

**位置**: Plan 12 line 164 + line 441

**问题**: DP7 SLA 是 "best-effort", 但对外 SECURITY.md 若不含 Apache-2.0 免责声明, 未来 miss SLA 可能引法律争议。custos 独立开源仓 audit-facing 建议在 SECURITY.md 内 explicit 附上 "provided as-is, no warranty per LICENSE" 引用。

### L3 — Applicable lessons self-audit 未提 lesson C1 / #38 (虽然 Plan 11 CEO clean-break 是 Plan 12 DP5 resolve 的上游)

**位置**: Plan 12 line 517
> lesson #38 CEO override: 不适用

**问题**: Plan 12 自身不发起 CEO override, 但 DP5 resolved 状态 (line 101) 是**继承** Plan 11 CEO clean-break directive (custos lesson C1 记录)。Applicable lessons 应明说 "lesson #38 / C1 通过 Plan 11 继承适用, DP5 resolve 归属 Plan 11 承担四件套完整登记, 本 plan 不重复 override 但依此前置"。

### L4 — Plan 12 Task 5 CHANGELOG scaffold "0.2.0" 首个 entry 与 Plan 11 clean-break 同版共载

**位置**: Plan 12 line 438 (T9 描述): CHANGELOG §0.2.0 包含 Plan 11 clean-break + Plan 12 distribution 两 plan 项 "同版发布"

**问题**: 一次 minor bump 里塞两 plan 是 acceptable, 但 lesson #32 (worktree-merge SHA gate) 精髓 = 两 plan 落地必须严格 land 顺序 (Plan 11 先, Plan 12 后), CHANGELOG 应显式区分两段以便审计员追溯:
```
## [0.2.0] - 2026-07-10
### Added (Plan 12)
- signed wheel via sigstore
- ...
### Changed (Plan 11 - BREAKING)
- ~/.custos/ retired to ~/.arx/
- python -m custos entry removed
```
避免 SHA gate 复检时看不清哪些项来自哪 plan。

---

## Positive findings

### P1 — Foundation Scan iteration log (lesson #33b) 落地充分, 三 iteration 各覆盖不同维

Plan 12 line 502-506 三 iteration 明确空间 (evidence-scout §L3) / 命名空间 (arx trait grep) / 时间 + 影响面 (as-of Plan 05/04/11 close-out) 各一维, 停扫判据明说 "3 iteration 覆盖 4 维"。虽然对 arx-side wire 影响面缺 iteration 4 (见 M7), 主体符合 lesson #33b 分层展开精神。

### P2 — Failure-Mode Coverage 11 条 (FM1-FM11), 覆盖 multi-layer 独立可测 (lesson #17 + #22)

FM1/FM2/FM3 均 ≥2 layer 独立测; FM8 (sigstore/cosign key rotation) + FM9 (SEMVER minor 隐性破坏 arx client) 抓到 supply chain + boundary contract 双面 subtle failure, 是 lesson #17 的教科书式应用。relaxed-double test "不适用" 声明 (line 193) 逻辑合理 (distribution 无 shadow 结构)。

### P3 — 与 Plan 11 clean-break 前置 gate 联动机制清晰 (line 464)

Verification checklist 明说 team-lead 独立 grep 三条件: (a) Plan 11 squash commit 命中 (b) `arx-runner` 单一 entry 命中 (c) `SopsAgeVault` 命中 0 — 三条件之一不满足则阻断 Plan 12 execute 启动。是 lesson #35 boundary constant fanout 双源风险的主动兜底。

---

## Cross-plan handoff notes

### 给 Plan 11 reviewer + Plan 11 executor

1. **H3 payload 字段名漂移**: Plan 11 Task 4 test payload `token_hash` vs Plan 12 T7 enrollment.schema.json `token_sha256` — 两 plan 需先协调命名再各自 land。建议 Plan 11 侧作为 wire 定义源, Plan 12 schema follow。
2. **Plan 12 DP5 resolve 依赖 Plan 11 land 成功**: 若 Plan 11 review 有 REQUEST_CHANGES 需返工, Plan 12 execute 不得启动 (line 464 gate)。

### 给 arx-79 wire ready follow-up plan

1. **M7 UNVERIFIED contract anchor**: arx-79 wire close-out 需补 "gateway contract v1 schema vs arx trait 双向反射对齐检" test, 补上 custos 侧无法完成的 arx-side grep 实证。
2. **H4 `~=0.2.0` pin**: arx 侧 client crate 引 custos wheel 时用 `~=0.2.0` (禁自动升 minor); 若确要允许 0.x 内所有 minor 升级, 需与 Plan 12 SEMVER 承诺表 line 115 意图对齐后再定。

### 给 Plan 12 executor (若 Verdict 修 CRITICAL 后 approve)

1. **C1** 修断言方向 + 追 3 negative test (新增 optional / 新增 required / 删除 property 三例)
2. **C2** T2 Step 3 ENTRYPOINT 更新为 `["arx-runner", "start"]`, 追 smoke test `docker run --rm <image> arx-runner --help` exit 0
3. **H1** Dockerfile 用 `COPY --from=... dist/*.whl` + `pip install --no-index --find-links=/tmp` 避免依赖未发布的 PyPI
4. **H2** `.github/workflows/release.yml` 落地时严格用 `permissions:` (复数) 顶级 key
5. **H3** enrollment.schema.json required 字段与 Plan 11 Task 4 payload 名对齐 (`token_hash`)
6. **H4** SEMVER 承诺表 line 115 澄清 arx-side pin 具体 spec
7. **H5** T4 Step 3 job DAG 计数改 "8 job" (或明说合并规则)
8. **H6** T3 落地时先 `sigstore --help` grep 实证 flag; pin sigstore + cosign 具体版本
9. **M1-M7** 按修法逐条澄清 (M1/M2 属 SEMVER 表内部矛盾, M3/M4 属 T8 reproducible 未 grep 实证 + 缺证伪, M5 阈值放宽, M6 rc tag 处理, M7 arx-side anchor UNVERIFIED 补 iteration 4)

---

**Reviewer sign-off**: claude (Plan-team reviewer, opus-4-7[1m])
**Report file**: `.forge/reviews/2026-07/12-plan-review-claude.md`
