# 17 - Fix vault CLI JSON format symmetry

> **Status**: 🔲 Todo
> **Created**: 2026-07-12
> **Project**: custos
> **Source**: downstream real Docker smoke failure on `arx-runner vault verify`
> **For Claude**: Use `/forge:execute` to implement these fixes.
> **Depends on**: Plan 16 ✅ (`a2effb2` close-out; source revision `89b31a1` or later)
> **Local image contract**: retain `custos-runner:v0.3.0`; remote publication remains deferred

## 修复来源

Philosophers-Stone opt-in Docker smoke 在真实执行 `vault put → vault verify` 时失败：

```text
sops decrypt failed: Error dumping file:
error emitting binary store: no binary data found in tree

This is likely not an encrypted binary file?
```

代码实证：

- `vault put` 用 `--input-type json --output-type json` 写入 `~/.arx/vault/<key-id>.enc`
- `PerKeyVault.decrypt()` 用显式 JSON type 正确读取同一文件
- public `vault verify` 只执行 `sops --decrypt <file.enc>`
- SOPS 根据 `.enc` 后缀误判为 binary store
- `tests/test_cli_vault_put_verify.py` mock subprocess 输出但未断言真实 argv
- `tests/integration/test_standalone_runtime.py` 绕过 `vault verify`，直接调用带正确 JSON flags 的 `sops`

## 根因分诊

| Finding | Priority | Root Cause | 处置 |
|---|---|---|---|
| F1 public verify 与 runtime decrypt 不对称 | P0 | 实现错误：verify 依赖文件后缀自动推断 | 所有 `.enc` decrypt 边界统一使用显式 JSON command contract |
| F2 mocked unit test 假绿 | P0 | 测试门缺口：只伪造 stdout，不检查 subprocess argv | 精确断言 JSON flags、路径和 env |
| F3 real integration 绕过 public CLI | P0 | 验证路径错误：底层工具通过被误当成 public surface 通过 | standalone integration 必须执行 `arx-runner vault verify` |
| F4 runbook 复现同一错误命令 | P1 | 权威文档漂移 | 手工 decrypt 命令显式指定 JSON type |
| F5 同类问题缺少历史教训 | P1 | 规则缺失 | 记录“mock subprocess + 绕过 public surface”双重假绿 lesson |

## 关键决策

| 问题 | 决策 | 理由 |
|---|---|---|
| Vault 文件扩展名 | 保留 `.enc` | 已是 0.2.0+ public storage contract，不做 boundary rename |
| SOPS 格式 | encrypt/decrypt 全部显式 JSON | 禁止依赖 `.enc` 后缀自动推断 |
| 实现收敛 | 增加单一 JSON decrypt argv helper，CLI/runtime 共用 | 防止 verify 与 runtime 再次漂移 |
| 验收入口 | public `arx-runner vault verify` | 底层 `sops` 成功不能替代 public CLI 成功 |
| 版本 | 保持本机 0.3.0 contract | 0.3.0 尚未 remote publish；修复后以新 source revision 重建同一 local development tag |
| 红线影响 | 不改变 key/KEK 边界 | plaintext 仍只在本地 subprocess stdin/stdout 内；日志/NATS/HTTP 不新增字段 |

## 文件清单

### 新增

- `.forge/plans/2026-07/17-vault-cli-json-format-symmetry-fix.md`

### 修改

- `.forge/README.md`
- `src/custos/cli/subcommands/vault.py`
- `src/custos/core/per_key_vault.py`
- `tests/test_cli_vault_put_verify.py`
- `tests/test_per_key_vault.py`
- `tests/integration/test_standalone_runtime.py`
- `docs/design/credential_vault.md`
- `docs/ops/runbook.md`
- `.claude/rules/historical-lessons.md`

## 修复任务 (Tasks)

### Fix 1: 统一 public verify 与 runtime JSON decrypt contract [P0]

**Root Cause**: 实现错误。`vault verify` 依赖 SOPS 根据 `.enc` 后缀自动推断格式，而 runtime 已显式指定 JSON。

**Files**: `src/custos/cli/subcommands/vault.py`、`src/custos/core/per_key_vault.py`、两个 unit test 文件。

**Step 1**: 新增失败测试：

- `test_vault_verify_uses_explicit_json_sops_types_for_enc_suffix`
- `test_cli_verify_and_runtime_share_json_decrypt_command`
- 精确断言 argv 为：

```python
[
    "sops",
    "--decrypt",
    "--input-type",
    "json",
    "--output-type",
    "json",
    str(enc_path),
]
```

**Step 2**: 运行 focused unit tests，确认当前 CLI test 因缺 flags 失败。

**Step 3**: 在 `per_key_vault.py` 收敛单一 JSON decrypt argv helper；`PerKeyVault.decrypt()` 与 CLI `_verify()` 共用。保留 CLI 的文件存在、0600 mode、清晰 stderr 和 permission-scope fail-closed 行为。

**Step 4**: focused unit tests全绿；确认 secret 不进入日志、异常输出或命令参数新增位置。

**Step 5**: 提交：

```bash
git commit -m "fix(custos): pin vault decrypts to JSON format"
```

### Fix 2: 用真实 public CLI roundtrip 关闭 integration 假绿 [P0]

**Root Cause**: 验证路径错误。standalone integration 的 put 后校验直接执行底层 `sops`，没有验证用户实际调用的 `arx-runner vault verify`。

**Files**: `tests/integration/test_standalone_runtime.py`。

**Step 1**: 将 integration 中 put 后的直接 SOPS probe 改为真实：

```text
arx-runner vault put
→ arx-runner vault verify
→ arx-runner start / PerKeyVault.decrypt
```

verify 必须挂载同一 `.arx` volume，设置 `SOPS_AGE_KEY_FILE`，传入真实 tenant/key/vault-dir。

**Step 2**: 用修复前镜像/代码确认 verify reproduces binary-store failure。

**Step 3**: 使用 Fix 1 实现运行 integration，断言 verify 返回 0 且输出 `OK`；随后 runner lifecycle 继续通过，证明 CLI 与 runtime 消费同一 artifact。

**Step 4**: 运行：

```bash
make test-docker-existing
make verify-runtime-existing
```

**Step 5**: 提交：

```bash
git commit -m "test(custos): exercise public vault verify in standalone runtime"
```

### Fix 3: 同步 authority、runbook 和防复发规则 [P1]

**Root Cause**: 权威文档与验证纪律不完整。设计文档只明确 runtime 的显式 type；runbook 的手工命令仍依赖自动推断；历史规则没有要求 mocked subprocess test 检查 argv，也没有禁止 integration 绕过 public surface。

**Files**: credential vault design、ops runbook、historical lessons、Plan 17、forge index。

**Step 1**: 更新 `docs/design/credential_vault.md`：

- 明确 put、verify、runtime 三条路径共享 JSON format contract
- `.enc` 是 storage naming，不是 SOPS binary format
- public verify 是 operator acceptance surface

**Step 2**: 更新 runbook：

```bash
sops --decrypt \
  --input-type json \
  --output-type json \
  ~/.arx/vault/binance-paper.enc
```

并保留 `arx-runner vault verify` 为推荐复合校验。

**Step 3**: 新增历史教训：

> mock subprocess 只伪造 stdout 而不检查 argv，加上 integration 直接调用底层工具，会让 public CLI 的参数漂移形成双重假绿。

绑定要求：

- subprocess mock 必须断言关键 argv/env/stdin
- integration 必须经过用户公开入口
- 底层工具 smoke 只能作为补充，不能替代 public surface

**Step 4**: 运行完整验证并重建 local image：

```bash
make verify
make verify-nt
make verify-local-v030
```

然后在 Philosophers-Stone 重跑真实 Docker smoke。只有 downstream smoke 通过才能 close-out Plan 17。

**Step 5**: 提交文档与最终 close-out：

```bash
git commit -m "docs(custos): document vault JSON format contract"
git commit -m "docs(custos): mark plan 17 as completed"
```

## 失败模式覆盖

| Failure mode | Gate |
|---|---|
| `.enc` 被 SOPS 误判为 binary | unit exact argv + real public CLI roundtrip |
| verify 与 runtime flags 再次漂移 | shared command helper + dual-call-site assertion |
| mock 返回合法 JSON 掩盖错误命令 | subprocess argv assertion |
| integration 绕过 public CLI | standalone test 明确调用 `vault verify` |
| bad age identity / corrupted ciphertext | 保留现有 CalledProcessError non-zero gate |
| permission scope 非 `trade_no_withdraw` | 保留现有 CLI/runtime 双层拒绝 |
| plaintext 泄露 | 现有 secret log scan + Non-Custodial 0.1 gate |

## 验证清单 (Verification)

- [ ] Plan 17 first commit 严格早于所有实现 commit
- [ ] CLI verify 与 runtime 使用同一 JSON decrypt command helper
- [ ] `.enc` 不依赖 SOPS auto-detection
- [ ] public put → verify roundtrip 通过
- [ ] public put → runner runtime decrypt 通过
- [ ] existing missing-file/mode/scope/SOPS failure tests 保持通过
- [ ] secret 不进入日志、NATS、HTTP 或新增 argv
- [ ] `make verify` 通过
- [ ] `make verify-nt` 通过
- [ ] `make test-docker-existing` 通过
- [ ] `make verify-runtime-existing` 通过
- [ ] `make verify-local-v030` 重建新 revision 的本地镜像
- [ ] Philosophers-Stone opt-in Docker smoke 通过
- [ ] credential_vault authority 与 runbook 同步
- [ ] historical lesson 已记录
- [ ] 偏离标注完整

## 进度追踪 (Progress)

| Fix | Priority | Status | Completed | Notes |
|---|---|---|---|---|
| F1 JSON decrypt symmetry | P0 | [ ] | — | — |
| F2 public CLI integration | P0 | [ ] | — | — |
| F3 authority/lesson/close-out | P1 | [ ] | — | — |

## 偏离与改进日志

| 类型 | 位置 | 描述 | 状态 |
|---|---|---|---|
| BUG-FIX | vault verify | `.enc` naming 被错误当成 binary format signal | planned |
| IMPROVEMENT | SOPS command | CLI/runtime 共用单一 JSON decrypt command helper | planned |
| IMPROVEMENT | integration | direct sops probe 改为 public CLI acceptance | planned |
| DECISION | versioning | remote 0.3.0 未发布，本轮保持 local v0.3.0 tag 并更新 revision | planned |
| NO-DEVIATION | red lines | 不改变 key/KEK、G6、fallback、money math contract | confirmed |
