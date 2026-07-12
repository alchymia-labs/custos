# 15 — Plan 14 release artifact and authority contract fixes

> **Status**: ⏳ In Progress
> **Created**: 2026-07-12
> **Project**: custos
> **Source**: 2026-07-12 inline Plan 14 audit in the originating conversation
> **For Claude**: Use `/forge:execute` to implement these fixes.
> **Depends on**: Plan 14 ✅ Completed (`0c59e5c`)
> **Blocks**: publishing/promoting `custos-runner v0.3.0`

---

## 修复来源

Plan 14 复核发现：

1. release runtime gate 在下载 `dist-signed` 之前运行，随后又重新构建并 push；测试镜像
   与公开 tag 对应的精确 digest 没有 pre-promotion identity。
2. 权威 `docs/domain.md` 仍声明 Custos 直连 Crucible、不直连 arx，并保留旧 subject 与
   `~/.custos` 路径。
3. Dockerfile 注释声称 `uv.lock` 锁定 `pip install "${wheel}[nautilus]"` 的依赖，事实
   不成立；Docker reproducibility 已明确 defer，应诚实描述当前 digest/cosign 边界。

## 根因分诊

| Finding | Priority | Root Cause | Disposition |
|---|---|---|---|
| exact published image 未经过 pre-promotion runtime gate | P1 | 实现错误 + 测试覆盖不足 | 修 workflow、Makefile 与 executable shape tests |
| `docs/domain.md` 仍保留旧 peer/subject/namespace | P1 | 权威文档过期 | 更新 authority doc + 加 drift contract test |
| Dockerfile 对 `uv.lock` 的说明不真实 | P3 | 误导性说明 + artifact identity 规则缺失 | 同 release 修复一并诚实化并沉淀规则 |

## 修复任务 (Tasks)

### Fix 1: 对同一候选 digest 完成验证后再提升稳定 tag [P1]

**Root Cause**: 实现错误 + 测试覆盖不足。workflow 只锁定“runtime gate 文本出现在 push
之前”，没有锁定 artifact identity 和 digest promotion。

**Files**: Modify `.github/workflows/release.yml`, `Makefile`, Docker/runtime tests,
`tests/test_release_workflow_shape.py`。

**Step 1 — 写失败测试**:

锁定以下顺序和不变量：

1. 下载 `dist-signed`。
2. 构建并 push 仅 SHA-scoped candidate tag，保留 provenance/SBOM。
3. 以 `${IMAGE_NAME}@${digest}` 运行完整 Docker + standalone acceptance。
4. 验证通过后，用 `imagetools create` 把同一 digest 提升为 `v<version>` 与 `latest`。
5. gate 后不存在第二次 build。

```bash
uv run pytest tests/test_release_workflow_shape.py -v
```

预期：当前 workflow 的 runtime gate 早于 `dist-signed` download，且公开 tags 在未经精确
digest 验证的 build-push step 中直接产生，测试失败。

**Step 2 — 参数化被测镜像**:

让 Docker contract 与 standalone acceptance 从 `CUSTOS_TEST_IMAGE` 读取镜像引用，默认仍为
`custos-runner:test`，覆盖：

- `tests/test_docker_non_root.py`
- `tests/test_docker_entrypoint_help.py`
- `tests/test_docker_image_size.py`
- `tests/test_docker_runtime_contract.py`
- `tests/integration/test_standalone_runtime.py`

**Step 3 — 分离 build 与 existing-image verification**:

Makefile 提供不触发 `uv build` / `docker build` 的 existing-image targets；本地
`make verify-runtime` 行为保持“先构建再验证”，CI 对 candidate digest 使用 existing-image
target。

**Step 4 — 单 digest promotion workflow**:

release job 顺序固定为：

```text
download dist-signed
  → build/push candidate-${github.sha} with provenance + SBOM
  → CUSTOS_TEST_IMAGE=<image>@<candidate-digest> verify existing image
  → promote that exact digest to v<version> and latest
  → sign the same digest
```

保持 `image_digest` output 与后续 sign/publish/verify DAG。candidate tag 不是稳定 release tag；
失败时不得创建/移动 `v<version>` 或 `latest`。

**Step 5 — 验证并提交**:

```bash
uv run pytest tests/test_release_workflow_shape.py -v
make verify-runtime
git commit -m "ci(custos): promote only the runtime-verified image digest"
```

### Fix 2: 收敛 domain authority 到当前 arx runtime contract [P1]

**Root Cause**: 权威文档过期。Plan 14 只更新了 DeploymentSpec 段，没有迭代检查同一文档
中的旧拓扑、subject 与 namespace。

**Files**: Modify `docs/domain.md`; Create `tests/test_authority_runtime_alignment.py`; verify
`CLAUDE.md` and affected design docs。

**Step 1 — 写失败测试**:

拒绝以下旧声明/常量：

- `custos 不直接跟 arx 通信`
- `arx.<tenant>.deployment.spec...`
- `arx.<tenant>.deployment.status...`
- `arx.<tenant>.runner.heartbeat`
- `~/.custos/vault`

同时要求 authority doc 包含来自代码真理源的当前 contract。

```bash
uv run pytest tests/test_authority_runtime_alignment.py -v
```

**Step 2 — 更新权威契约**:

从 `build_subject` 调用点和 executable tests 锁定：

```text
desired state  arx.<tenant>.deployment_spec.<strategy_id>
status         arx.<tenant>.deployment_status.<runner_id>.<spec_id>
heartbeat      arx.<tenant>.heartbeat.<runner_id>
telemetry      arx.<tenant>.telemetry.<runner_id>.<session_id>
Vault          ~/.arx/vault/<key-id>.enc
```

Custos 与 arx coordination plane 直接走 NATS；Crucible 位于 arx 后方，不是 Custos 的直接
runtime peer。同步跨系统契约、信任边界文字和 `Last updated`。

**Step 3 — 验证并提交**:

```bash
uv run pytest \
  tests/test_authority_runtime_alignment.py \
  tests/test_subject_builder_contract.py \
  tests/test_nats_wire_contract.py \
  tests/test_gateway_contract_v1_backward_compat.py -v
make verify-base-clean
git commit -m "docs(custos): align domain authority with the arx runtime contract"
```

### Fix 3: 诚实化 Docker dependency/reproducibility 说明并固化防复发规则 [P3]

**Root Cause**: 误导性说明 + release artifact identity 规则缺失。

**Files**: Modify `Dockerfile`, `.claude/rules/verification.md`,
`.claude/rules/historical-lessons.md`。

**Step 1 — 诚实化当前边界**:

删除“Docker pip 解析受 `uv.lock` 锁定”的错误声明。明确 0.3.0 当前边界：wheel 可复现；
Docker Python/apt resolution 尚非 bit-for-bit；镜像审计锚点是 source revision、candidate
digest、cosign 与同 digest promotion。

**Step 2 — 固化规则**:

在 verification rule 加入：稳定 tag 只能从已通过 runtime gate 的同一 digest 提升；gate 与
promotion 之间禁止 rebuild。

在 historical lessons 记录 C3：pre-publish shape gate 不等于 artifact identity gate；检查
顺序字符串不足以证明测试和发布消费同一 artifact。

**Step 3 — 验证并提交**:

```bash
rg -n 'uv.lock|candidate|digest|promotion|rebuild' \
  Dockerfile .claude/rules/verification.md .claude/rules/historical-lessons.md
make verify
git commit -m "docs(custos): document release artifact identity truthfully"
```

### Fix 4: Close-out [P1]

1. 实跑 base、NT、candidate-image runtime 三层 gate。
2. 确认 Non-Custodial 四红线无新增命中。
3. 更新本计划和 `.forge/README.md` 为完成状态，记录 commit range 与精确测试结果。
4. 独立 close-out commit。

## 验证清单 (Verification)

- [ ] signed wheel 下载发生在 candidate image build 之前
- [ ] runtime tests 使用 candidate digest
- [ ] `v0.3.0`/`latest` 只由已验证 digest promotion 产生
- [ ] gate 与 promotion 之间无 rebuild
- [ ] authority docs 不含旧 peer、subject、namespace
- [ ] `make verify-base-clean`
- [ ] `make install-nt && make verify-nt`
- [ ] `make verify-runtime`
- [ ] Non-Custodial 四红线检查通过
- [ ] worktree clean

## 进度追踪 (Progress)

| Fix | Priority | Status | Completed | Notes |
|---|---|---|---|---|
| F1 exact candidate digest promotion | P1 | ✅ | 2026-07-12 | Signed wheel → candidate digest → 13+1 runtime gates → same-digest stable promotion |
| F2 domain authority alignment | P1 | ✅ | 2026-07-12 | 11 drift contracts; 34 focused passed; base 499 passed |
| F3 reproducibility truth + prevention | P3 | ✅ | 2026-07-12 | Docker lock boundary corrected; verification rule + lesson C3; base 501 passed |
| F4 close-out | P1 | 🔲 | — | — |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|---|---|---|---|
| IMPROVEMENT | Release promotion | 使用 registry candidate digest + stable tag promotion 保留 provenance/SBOM，同时保证公开 tag 指向已验证的精确镜像 | ✅ user `/forge:fix` 2026-07-12 |
| IMPROVEMENT | Self-reflect R1 | 补充 gate 后到 build job 结束禁止第二次 image build 的显式回归断言 | ✅ 2026-07-12 |

---

*Drafter: Codex @ 2026-07-12*
