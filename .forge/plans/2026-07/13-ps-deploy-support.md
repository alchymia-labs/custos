# 13 — custos 支撑 ps `deploy/custos/` 目标 (permission-scope flag + sandbox runner.toml sanctioned + spec samples + example 刷新)

> **Status**: ⏳ In Progress
> **Created**: 2026-07-11
> **Project**: custos (`tesseract-trading/custos/`)
> **Wave**: independent (CEO 2026-07-11 提出, 支撑 ps 侧 Plan 49 `deploy/custos/` target)
> **For Claude**: `/forge:execute` 单会话可完成 (中粒度 4-6h, 5 Task, 无 heavy 依赖)
> **Depends on**: Plan 11 ✅ Completed (2026-07-11 `62a155a`) — CLI subcommand 契约 lock; Plan 12 ✅ Completed (2026-07-11 `3b85111`) — signed image + gateway-contract v1 已 freeze
> **Blocks**: ps `philosophers-stone/.forge/plans/2026-07/01-custos-deploy-target.md` T3 (bootstrap-vault.sh 需要 `--permission-scope` flag) + T3 (publish-spec.py code_hash 算法对齐样例) + T6 (端到端冒烟依赖 sanctioned runner.toml 手工构造 pattern)
> **multi_session_scope**: false (5 Task, 每 Task ~30-60 min, 无 heavy async/wire changes)

---

## 起源 (Origin)

三条独立信号汇合:

1. **ps 侧 Plan 49 起草 (2026-07-11)** — `philosophers-stone/.forge/plans/2026-07/01-custos-deploy-target.md` 声明四项 hard/soft deps:
   - `arx-runner vault put --permission-scope trade_no_withdraw` flag (T3 bootstrap-vault.sh 期望 explicit flag; 起步用默认硬编码兜底但需正式支持)
   - `runner.toml` sandbox 手工构造 pattern **sanctioned** (T6 端到端冒烟依赖非 arx-enroll 路径 legit 化)
   - `docs/gateway-contract/v1/` sample fixture (T3 publish-spec.py code_hash 算法对齐 + 测试 fixture 参考)
   - custos `examples/supertrend-{sandbox,testnet}/` 刷新到 v0.2.0 CLI (Plan 12 遗留项 `DEV-12-T9-PLAN-11-T9-DOCS-OPS-GAP` 同源问题, 用 v0.1.x 风格 `--sops-file` flag 已 Plan 11 clean-break)

2. **Plan 12 遗留项 DEV-12-T9-PLAN-11-T9-DOCS-OPS-GAP** (`.forge/plans/2026-07/12-*.md:667`) — 起草时 `docs/ops/05-deployment.md` 与 `examples/supertrend-{sandbox,testnet}/` 均未刷新。执行前者已由 `88769e5` 独立解决，examples 仍保留 v0.1.x 风格；本 plan 只完成剩余 examples gap。

3. **Plan 11 CEO clean-break directive (2026-07-10)** — clean-break 时删了 `SopsAgeVault` + `--sops-file` + `--age-key-file` + legacy `python -m custos` 入口; `permission_scope` 默认走隐含值 (per-key vault put 时未 explicit)。ps 侧 bootstrap 想 explicit 传 scope 时无 flag 承接。

## 上下文 (Context)

**权威文档引用 (含具体章节号)**:

- custos `CLAUDE.md` §5 Non-Custodial 4 红线 — item 1 (KEK 永不出进程) + item 3 (Reconcile 失联 ≠ 停止); 本 plan 强化 item 1 兑现 (`--permission-scope` 是 KEK 使用契约的一部分)
- custos `docs/design/credential_vault.md` — vault 设计权威, 本 plan T1 修改 (`--permission-scope` flag 契约); Plan 11 T9 已改写为 per-key `~/.arx/vault/<key-id>.enc` 单一模型
- custos `docs/design/enrollment.md` — enrollment 设计权威, 本 plan T2 追加"sandbox 手工构造 runner.toml"章节 (sanctioned pattern 明说)
- custos `docs/gateway-contract/v1/enrollment.schema.json:19` (Plan 12 T7 R2-C1 fix landed 2026-07-11) — 4 字段 required, additionalProperties: false; 本 plan T3 加 `samples/` 目录
- custos `src/custos/core/strategy_loader.py:33-50 compute_strategy_dir_hash` — code_hash 计算算法权威, 本 plan T3 sample fixture 展示同款算法输出格式
- ps `philosophers-stone/.forge/plans/2026-07/01-custos-deploy-target.md` — 消费本 plan 产出 (permission-scope flag / sandbox runner.toml pattern / spec samples)

**契约证据 (Step 1.5 anchors, 2026-07-11 grep-verified)**:

- `src/custos/cli/subcommands/vault.py:37 _log = logging.getLogger("custos.credential_vault")` — audit event 落点
- `src/custos/cli/subcommands/vault.py` — `vault put` 当前 argparse: `--key-id / --tenant-id / --api-key / (--api-secret-stdin|--api-secret-env|--api-secret) / --age-recipient / --vault-dir` 共 7 flag, **无 `--permission-scope`**
- `src/custos/cli/subcommands/vault.py:157-163` — encrypted payload **硬编码** `"permission_scope": "trade_no_withdraw"` 到 `payload[key_id]` 字典 (2026-07-11 grep 实证)
- `src/custos/core/credential_vault.py:83-97 _verify_permission_scope` — 在 `_BaseVault` 层执行, 拒非 `trade_no_withdraw` 抛 ValueError
- `src/custos/core/credential_vault.py:112` + `src/custos/cli/subcommands/vault.py:161` — 两处硬编码字符串 `"trade_no_withdraw"` 分布, 本 plan T1 收敛为 CLI flag 单源
- `tests/test_cli_vault_put_verify.py:109 test_vault_put_writes_permission_scope` — 已 lock 契约 "payload 含 permission_scope == trade_no_withdraw", 本 plan T1 test 扩展但保留此断言
- `src/custos/core/runner_toml.py:41-46 RunnerToml @dataclass` — 5 字段签名 lock (`tenant_id / runner_id / backend_url / long_term_credential / enrolled_at_ns`); sandbox 手工构造要遵循此 dataclass
- `examples/supertrend-sandbox/README.md` + `examples/supertrend-testnet/{README,docker-compose.yaml,.env.example}` — 全部 v0.1.x 风格, 引用已删除的 `--sops-file` / `--age-key-file` flag
- `docs/gateway-contract/v1/` — 4 schema 已 land, 但无 samples/ 目录 (grep `ls docs/gateway-contract/v1/samples/` = ENOENT)

**Foundation Scan iteration log (lesson #14/#30/#33/#33b)**:

- **Iter 1 空间维**: `ls src/custos/cli/subcommands/vault.py + src/custos/core/{credential_vault,runner_toml,per_key_vault,strategy_loader}.py + docs/design/{credential_vault,enrollment}.md + examples/` 覆盖直接引用面
- **Iter 2 命名空间维**: `grep -rn 'permission_scope' src/` 找现有语义分布 (硬编码 vs config)
- **Iter 3 时间维**: as-of Plan 11 close-out `62a155a` + Plan 12 close-out `3b85111` (2026-07-11 landed)
- **Iter 4 影响面维**: 消费者面 = ps Plan 49 T3 (bootstrap-vault) + T3 (publish-spec code_hash 参照) + T6 (端到端), 不外溢到其他 custos 计划

## 目标 (Goal)

打开 ps 侧 `deploy/custos/` 目标落地路径, 消除四个 gap:
1. `arx-runner vault put --permission-scope SCOPE` explicit flag (default `trade_no_withdraw`, 非法值 fail-fast)
2. `docs/design/enrollment.md` 追加 "Sandbox: 手工构造 runner.toml sanctioned pattern" 章节, 明说 build-runner-toml.py-style script 是官方 legit 路径 (非 hack)
3. `docs/gateway-contract/v1/samples/{enrollment,deployment_status,telemetry_snapshot,heartbeat}.json` 4 份 payload 样例 + 1 份 sandbox deployment_spec sample (供 ps publish-spec.py 对照)
4. `examples/supertrend-sandbox/` + `examples/supertrend-testnet/` 刷新到 v0.2.0 CLI (删 `--sops-file` / `--age-key-file` 引用, 换 `arx-runner vault put` + `arx-runner start`, docker-compose command 对齐 Plan 11 subcommand shape)

**不做**: sidecar 集成 (Plan 49 Stage 5 defer) / arx backend mock / live G6 gate 真过 (Plan 49 Stage 4 defer)。

## 关键设计决策 (Key Design Decisions)

| 问题 | 决策 | 理由 |
|------|------|------|
| `--permission-scope` 默认值 | `trade_no_withdraw` (与 `_verify_permission_scope` 拒它以外值的现有语义一致) | 单源真理; 非托管红线兑现 |
| `--permission-scope` 非法值处理 | fail-fast, argparse `choices=["trade_no_withdraw"]` (仅一个合法值), stderr 明确 | 未来加值时是 minor version bump, 加值前 choices 硬门槛 |
| sandbox runner.toml 手工构造是否文档化 | 是, 明说 sanctioned pattern; `docs/design/enrollment.md` 加"Sandbox mode: manually-constructed runner.toml is a legitimate path" 章节 | 避免 ps 侧 build-runner-toml.py 被误判为 hack; 明说 backend_url = "http://mock-<mode>:8000" 允许 mock scheme |
| samples/ 位置 | `docs/gateway-contract/v1/samples/*.json`, 与 schema 同层 | 消费者 (ps publish-spec.py + 未来 arx-79 wire) grep sample vs schema 关联清晰 |
| samples role: normative vs informative | **L4 fix (R1 self-review 2026-07-11)** — 4 wire samples (enrollment/deployment_status/telemetry_snapshot/heartbeat) = **normative** (对应 Plan 12 T7 schema, jsonschema.validate 双向锁); `deployment_spec_sandbox.json` = **informative** (等 arx-79 wire close-out 时若与 arx-side 定义分歧, 收敛以 arx authoritative), M1 fix 的 `deployment_spec.schema.json` 起步 informative, arx-79 landed 后升级 normative | 契约诚实性: 单侧起草的 schema 是 "consumer 期望" 非 producer 契约 |
| deployment_spec sample 是不是本 plan 首次落 + 有无对应 schema | 是 — Plan 12 只落 4 wire payload schema 无 deployment_spec。**M1 fix (R1 self-review 2026-07-11)**: 本 plan T3 顺手加 `deployment_spec.schema.json` (与 4 wire schema 同级, 从 `deployment_spec_sandbox.json` 反推最小 required fields: `spec_id / generation / trading_mode / lifecycle_state / strategy_path / provenance_ref`; sandbox 特有字段如 `sandbox.starting_balances` optional; live 特有 `code_hash` 用 conditional 加成 required 需要 draft-2020-12 `if/then`, 起步简化为 optional 并在 description 注明 "live mode requires non-null"), sample validation test 同 pattern 加对应断言 | sample + schema 双源, 未来 spec 结构漂移有契约兜底 |
| deployment_spec.schema 与 arx 侧同源 | 起步 informative (custos 单侧起草), 明说待 arx-79 wire close-out 时若与 arx-side 定义分歧, 收敛以 arx 侧 authoritative (arx 是 spec producer, custos 是 consumer) | 契约诚实性: custos 单侧起草的 schema 是 "consumer 期望", 非 producer 契约 |
| examples/ 刷新是否 batch 到本 plan | 是, 与 T1/T2/T3 强关联 (用户读 example 学 v0.2.0 CLI, 与本 plan 三处支撑同源) | 完成 DEV-12-T9-PLAN-11-T9-DOCS-OPS-GAP 在 `88769e5` 后剩余的 examples 部分 |
| examples/ 是否用 make 或 docker-compose | 保持 docker-compose 惯例 (与 Plan 12 T2 Dockerfile ENTRYPOINT arx-runner start 对齐), 但 command 语法改新 CLI shape (三命令组合而非单一 --sops-file) | 用户已熟悉 docker-compose UX, 不引入新概念 |

## 承载决策 (Capability Hosting Decision)

不适用 (无新增能力, 只是 CLI flag 表面 + 文档 + 样例 + example 刷新)。

## 文件清单 (File Inventory)

| 文件路径 | 操作 | 描述 |
|----------|------|------|
| `src/custos/cli/subcommands/vault.py` | Modify | `vault put` 加 `--permission-scope` argparse flag (choices=["trade_no_withdraw"], default 同值); 落到 encrypted payload / audit event |
| `src/custos/core/credential_vault.py` | Modify | `_verify_permission_scope` 保持不变; `credential_vault.py:112` `CredentialVault` mock 里的硬编码 `"trade_no_withdraw"` 保留 (只 mock 内部, 不影响 CLI 收敛决策); 无 write path change (vault.py 侧承担) |
| `docs/design/credential_vault.md` | Modify | 追加 "Permission scope" 段, 明说 `trade_no_withdraw` 是唯一 v0.2.x 合法值, 加值需 minor bump + 双侧 update |
| `docs/design/enrollment.md` | Modify | 追加 "Sandbox mode: manually-constructed runner.toml" 章节, 展示 `RunnerToml` dataclass 5 字段 + `backend_url = "http://mock-<mode>:8000"` 示例 + `enrolled_at_ns = time.time_ns()` 允许 |
| `docs/domain.md` | Modify | 在 Runner / EnrollmentToken domain 中记录 sandbox/testnet 无控制面时可手工构造 runner.toml 的受限 sanctioned path |
| `docs/gateway-contract/v1/samples/enrollment.json` | Create | 4 字段 valid payload sample (对应 Plan 12 T7 schema) |
| `docs/gateway-contract/v1/samples/deployment_status.json` | Create | phase=`running` sample |
| `docs/gateway-contract/v1/samples/telemetry_snapshot.json` | Create | 4 money 字段 str-decimal 示例 |
| `docs/gateway-contract/v1/samples/heartbeat.json` | Create | 基础 sample |
| `docs/gateway-contract/v1/samples/deployment_spec_sandbox.json` | Create | supertrend sandbox spec 完整示例, 供 ps publish-spec.py 对照 (含 `provenance_ref.credential_id` 命名); **M1 fix**: informative role (custos consumer 期望), 明说与 arx 侧待 arx-79 wire close-out 时收敛以 arx authoritative |
| `docs/gateway-contract/v1/deployment_spec.schema.json` | Create | **M1 fix (R1 review)** — 与 4 wire schema 同级; 最小 required fields (`spec_id / generation / trading_mode / lifecycle_state / strategy_path / provenance_ref`); `code_hash` optional + description 注 "live mode requires non-null"; sandbox 特有 `sandbox.starting_balances` optional |
| `docs/gateway-contract/v1/README.md` | Modify | 区分 4 份 normative wire schema/sample 与 informative deployment spec consumer shape |
| `pyproject.toml` | Modify | dev extra 增加 `jsonschema>=4.20`, 用于 sample/schema 契约测试 |
| `uv.lock` | Modify | 锁定新增 jsonschema dev 依赖及其传递依赖 |
| `examples/supertrend-sandbox/README.md` | Rewrite | v0.1.x → v0.2.0 CLI 三命令流程; 与 `docs/gateway-contract/v1/samples/deployment_spec_sandbox.json` cross-link |
| `examples/supertrend-sandbox/spec-example.json` | Modify | 命名/结构对齐 sample (软链或复制); 无 v0.1.x 特有字段 |
| `examples/supertrend-testnet/README.md` | Rewrite | 同 sandbox: 换 v0.2.0 三命令; 交易所 testnet 场景说明 permission-scope 强制 trade_no_withdraw |
| `examples/supertrend-testnet/docker-compose.yaml` | Rewrite | command 从 `--sops-file` → `arx-runner start --nats-url ... --reconcile-strategy-id ...`; vault 挂载改 per-key .enc 目录 |
| `examples/supertrend-testnet/.env.example` | Modify | 删掉隐式 sops-file 引用; 只保留 tenant/runner/nats 变量 |
| `examples/supertrend-testnet/vault-fixture/credentials.example.json` | Modify | 结构改 per-key 单文件示范 (非 multi-credential JSON, Plan 11 已删) |
| `examples/supertrend-testnet/Dockerfile` | Modify | 保留 testnet 专用 image：继续安装 NautilusTrader + sops + age，入口迁移为 `ENTRYPOINT ["uv", "run", "arx-runner"]` + `CMD ["start"]`；官方 Plan 12 image 当前缺这三项 runtime 能力，不能承载本示例 |
| `pyproject.toml` | Modify | dev extra 同步加入现有 `pyyaml>=6`，确保 alignment test 在干净 dev 环境可解析 compose YAML |
| `uv.lock` | Modify | 同步 dev extra metadata（PyYAML 已由 nautilus extra 锁定，无新增 package） |
| `tests/test_vault_put_permission_scope.py` | Create | 5 test: default trade_no_withdraw / explicit trade_no_withdraw 通过 / --permission-scope withdraw fail (choices 拦) / --permission-scope 缺省 default 落到 encrypted payload / audit event 含 scope |
| `tests/test_gateway_contract_v1_samples.py` | Create | 5 test: 4 samples 通过对应 schema validation + 1 deployment_spec sample syntactic valid JSON |
| `tests/test_examples_docs_v020_alignment.py` | Create | **H1 fix (R1 self-review 2026-07-11)** — 改用 file-parse (yaml/json parse) 而非 grep-based, 减少未来编码 / 大小写 / pattern rename 脆性: `pytest.mark.parametrize` 遍历 `examples/*/{README.md,docker-compose.yaml,Dockerfile,.env.example}`, 对 yaml/json 文件 parse 后断言 command list 无 `--sops-file` / `--age-key-file`, 对 markdown / Dockerfile 用 `Path.read_text()` + `assert "--sops-file" not in text` + `assert "-m custos" not in text` (完整 token 匹配, 不用 regex) |
| `.forge/plans/2026-07/13-ps-deploy-support.md` | Create | 本计划 |
| `.forge/README.md` | Modify | 索引追加 Plan 13 |

## 实现任务 (Tasks)

### Task 1: `vault put --permission-scope` flag

**Files**: Modify `src/custos/cli/subcommands/vault.py` + `src/custos/core/credential_vault.py` + Create `tests/test_vault_put_permission_scope.py`

**Step 1 (证伪)**: `uv run pytest tests/test_vault_put_permission_scope.py` 红 (module 不存在); `arx-runner vault put --permission-scope trade_no_withdraw --help` 应识别 flag → 当前失败 (unrecognized argument)。

**Step 1.5 Foundation Scan 结论 (2026-07-11 起草时补齐)**: 现状 = `src/custos/cli/subcommands/vault.py:161` 硬编码 `"permission_scope": "trade_no_withdraw"` 到 encrypted payload; `src/custos/core/credential_vault.py:112` 另有一处硬编码 (`CredentialVault` mock)。T1 实现方向确定: **"新增 CLI flag → 收敛 CLI write path 为 args.permission_scope 单源"** (非"表面新增 flag + 底层已有写入")。`CredentialVault` mock 的安全 fixture 默认值保留, 不属于 CLI write path。

**Step 2 (写失败测试)**: 5 test 覆盖 KDT 决策:
- `test_default_permission_scope_is_trade_no_withdraw`: 不传 --permission-scope, 生成的 .enc 解密后 payload `permission_scope == "trade_no_withdraw"`
- `test_explicit_trade_no_withdraw_ok`: `--permission-scope trade_no_withdraw` 明确传, 通过
- `test_illegal_permission_scope_rejected_by_choices`: `--permission-scope withdraw` argparse choices 拒, exit 2, stderr 明确
- `test_permission_scope_written_to_encrypted_payload`: sops 解密后 JSON 含 `permission_scope` 字段
- `test_permission_scope_in_audit_event`: `credential_encrypted` audit event 的 `extra` 含 scope 值 (脱敏日志契约: scope 是 metadata 非 secret, 可 log)。**L1 fix (R1 self-review 2026-07-11, grep 实证)**: 当前 `credential_encrypted` extra 字段 = `{audit_event, key_id, tenant_id, timestamp}` 4 项无 permission_scope; T1 加为**新字段** `extra["permission_scope"] = args.permission_scope`, 落到 `src/custos/cli/subcommands/vault.py:266-272` `_emit_encrypt_audit` 签名扩展 (加 `permission_scope: str` 参数)

**Step 3 (实现)**: 
- vault.py argparse 加 `parser.add_argument("--permission-scope", choices=["trade_no_withdraw"], default="trade_no_withdraw")`
- put 逻辑写入 encrypted payload 时把 `args.permission_scope` 落到 JSON body 的 `permission_scope` 字段
- audit event `_log.info("credential_encrypted", extra={"key_id": ..., "permission_scope": args.permission_scope})`
- 若 Step 1.5 发现底层原本硬编码, 改为使用 args.permission_scope; 若原本已有隐式配置, 收敛为 CLI flag 单源

**Step 4 (验)**: 
- `uv run pytest tests/test_vault_put_permission_scope.py -v` 全绿
- `make verify` 保持绿 (441+5=446 passed)
- `arx-runner vault put --help` 显示 `--permission-scope` flag

**Step 5 (提交)**: `git add src/custos/cli/subcommands/vault.py src/custos/core/credential_vault.py tests/test_vault_put_permission_scope.py`, commit `feat(custos): plan-13-t1 vault put --permission-scope flag (default trade_no_withdraw)`。

### Task 2: `docs/design/enrollment.md` 追加 sandbox runner.toml sanctioned pattern

**Files**: Modify `docs/design/enrollment.md` + `docs/design/credential_vault.md` + `docs/domain.md`

**Step 1 (证伪)**: `grep 'sandbox' docs/design/enrollment.md` 命中 0 或极少 (当前仅描述真 enroll HTTP 流程)。

**Step 2 (章节起草)**: 追加两章:
- `docs/design/enrollment.md` §"Sandbox mode: manually-constructed runner.toml (sanctioned pattern)":
  - 明说: sandbox/testnet 场景无真 arx backend 时, 手工构造 `~/.arx/runner.toml` 是官方 legit 路径 (非 hack)
  - 5 字段清单: `tenant_id / runner_id / backend_url / long_term_credential / enrolled_at_ns`
  - `backend_url = "http://mock-<mode>:8000"` allowed for sandbox/testnet (mock scheme, no wire call)
  - `enrolled_at_ns = time.time_ns()` allowed
  - mode 0600 + parent 0700 硬约束不变
  - cross-link `RunnerToml` dataclass in `src/custos/core/runner_toml.py:41`
- `docs/design/credential_vault.md` §"Permission scope":
  - 明说 `trade_no_withdraw` 是 v0.2.x 唯一合法值
  - 加值需 minor version bump + 双侧 (custos + arx) update
  - `--permission-scope` CLI flag 为 explicit 传, default 与硬约束一致
- `docs/domain.md` Runner / EnrollmentToken domain:
  - 补充 sandbox/testnet 无真实 arx backend 时可手工构造 runner.toml 的受限 operational path
  - 明确该路径不签发 live scope, 不放宽 production enrollment 的一次性 token 契约

**Step 3 (验)**: grep 章节标题命中; 手工过一遍章节可读性 (对策略作者友好)。

**Step 4 (提交)**: `git add docs/design/enrollment.md docs/design/credential_vault.md docs/domain.md`, commit `docs(custos): plan-13-t2 enrollment sandbox pattern + vault permission_scope sanctioned`。

### Task 3: gateway-contract v1 samples/ 目录

**Files**: Create `docs/gateway-contract/v1/samples/{enrollment,deployment_status,telemetry_snapshot,heartbeat,deployment_spec_sandbox}.json` + `docs/gateway-contract/v1/deployment_spec.schema.json` + `tests/test_gateway_contract_v1_samples.py`; Modify `docs/gateway-contract/v1/README.md` + `pyproject.toml` + `uv.lock`

**Step 1 (证伪)**: `ls docs/gateway-contract/v1/samples/` → ENOENT; `pytest tests/test_gateway_contract_v1_samples.py` 红。

**Step 2 (samples 落地 + 失败测试)**:
- 5 sample JSON (4 covers 已有 schema, 1 是 deployment_spec 新样例):
  - `enrollment.json`: `{"token_hash": "a"*64, "runner_id": "runner-sandbox-1", "agent_version": "0.2.0", "capabilities": []}`
  - `deployment_status.json`: 7 required fields (spec_id / container_id / phase="running" / observed_generation / reported_by_runner_id / reported_at / status_id)
  - `telemetry_snapshot.json`: 4 money 字段用 Decimal-string 格式 (`open_notional: "1500.5"` etc.)
  - `heartbeat.json`: 4 required fields
  - `deployment_spec_sandbox.json`: supertrend sandbox 完整 spec (参考 `examples/supertrend-sandbox/spec-example.json` 但对齐 Plan 11 后命名)
- Tests: 5 sample loads 通过对应 `jsonschema.validate` (4 wire + 1 deployment_spec 现有 schema 覆盖); **L3 fix (R1 self-review 2026-07-11, grep 实证)**: `custos/pyproject.toml` 当前 dev extra 无 `jsonschema` (grep 命中 0), T3 Step 3 pyproject 加 `[project.optional-dependencies].dev` 追加 `"jsonschema>=4.20"` + `make install` 重装; 或 T3 test 用 `check-jsonschema` CLI subprocess call 避免 python dep (但 python 库更 test-native)

**Step 3 (实现)**: 落 5 JSON + deployment spec informative schema + test; dev extra 加 `jsonschema>=4.20` 并更新 `uv.lock`。测试用 `pytest.mark.parametrize` 覆盖 5 个 schema-validated samples。

**Step 4 (验)**: 
- `uv run pytest tests/test_gateway_contract_v1_samples.py -v` 全绿
- `jq . docs/gateway-contract/v1/samples/*.json` 每个都 valid

**Step 5 (提交)**: `git add docs/gateway-contract/v1/README.md docs/gateway-contract/v1/deployment_spec.schema.json docs/gateway-contract/v1/samples/ tests/test_gateway_contract_v1_samples.py pyproject.toml uv.lock`, commit `feat(custos): plan-13-t3 gateway contract v1 samples (4 wire + 1 deployment_spec sandbox)`。

### Task 4: examples/supertrend-{sandbox,testnet}/ 刷新到 v0.2.0 CLI

**Files**: Rewrite `examples/supertrend-sandbox/{README.md,spec-example.json}` + `examples/supertrend-testnet/{README.md,docker-compose.yaml,.env.example,vault-fixture/credentials.example.json,Dockerfile}`; Modify `pyproject.toml` + `uv.lock`; Create `tests/test_examples_docs_v020_alignment.py`

**Step 1 (证伪)**: `grep -rn 'sops-file\|age-key-file\|python -m custos' examples/` 命中 (需迁移); `pytest tests/test_examples_docs_v020_alignment.py` 红。

**Step 2 (刷新)**:
- `examples/supertrend-sandbox/README.md`: 三命令流程 (`arx-runner vault put ...` → `python scripts/build-runner-toml.py ...` [引用 ps side 或 inline] → `arx-runner start ...`); 明说 sandbox 手工构造 runner.toml (cross-link T2 章节)
- `examples/supertrend-testnet/docker-compose.yaml`: command 从 v0.1.x `--sops-file` 换 Plan 11 subcommand shape:
  ```yaml
  command: ["start", "--nats-url", "${ARX_NATS_URL}", "--reconcile-strategy-id", "${ARX_STRATEGY_ID}", "--use-nt-host", "--vault-dir", "/home/custos/.arx/vault"]
  ```
- `examples/supertrend-testnet/Dockerfile`: 保留 testnet 专用 build（官方 image 当前不含 nautilus/sops/age），入口从 legacy `python -m custos` 改为 `ENTRYPOINT ["uv", "run", "arx-runner"]` + `CMD ["start"]`
- `examples/supertrend-testnet/.env.example`: 删 sops-file 引用, 增 `ARX_TENANT_ID / ARX_RUNNER_ID / ARX_NATS_URL / ARX_STRATEGY_ID` (与 Plan 11 CLI 对齐)
- `examples/supertrend-testnet/vault-fixture/credentials.example.json`: 从 multi-credential 改单 key-id 结构示范
- `examples/supertrend-sandbox/spec-example.json`: **M3 fix (R1 review)** — 起步用 verbatim copy from `docs/gateway-contract/v1/samples/deployment_spec_sandbox.json` (同仓 across dirs 软链 git 技术可行但增加路径解析复杂度); 未来若两处频繁 drift 再软链化; 一处 test (`test_examples_sandbox_spec_matches_sample`) 断言两文件内容 byte-identical
- Test: grep `examples/*/README.md examples/*/docker-compose.yaml` 无 `--sops-file` / `--age-key-file` / `python -m custos` 命中 (0 hits)

**Step 3 (验)**: 
- `uv run pytest tests/test_examples_docs_v020_alignment.py -v` 绿
- `grep -rn 'sops-file\|age-key-file\|python -m custos' examples/` 0 命中
- 手工过一遍 README (第三方读者视角) 步骤可跑

**Step 4 (提交)**: `git add examples/supertrend-sandbox/ examples/supertrend-testnet/ tests/test_examples_docs_v020_alignment.py pyproject.toml uv.lock`, commit `refactor(custos): plan-13-t4 examples refresh to v0.2.0 CLI (偿还 DEV-12-T9-PLAN-11-T9 examples/ 部分)`。

### Task 5: close-out + 索引 + 红线 gate 表

**Files**: Modify `.forge/README.md` (追加 Plan 13 索引) + 本 plan 末尾追加"完成报告"

**Step 1 (索引 update)**: `.forge/README.md` 追加 Plan 13 row (与 Plan 11/12 breaking-change 注解风格对齐, 但本 plan 无 breaking, 标 minor feat)。**L2 fix (R1 self-review 2026-07-11, grep 实证)**: 现 README 索引条目 Plan 09 (planned/draft-deferred) + Plan 11 ✅ + Plan 12 ✅, 下一 available 编号确认 = 13 (Plan 10 已作为占位跳过, Plan 09 仍是 planning). 执行前 grep 一次 `grep -nE "^\| \[?1[0-4]" .forge/README.md` 兜底避免中间起草其他 draft 造成编号偏移。

**Step 2 (close-out)**: 本 plan 末尾追加 "完成报告 (Close-out Report)":
- 完成日期 / Task 数 (5) / 偏离数
- 验证结果 (`make verify` 447 passed 或类似, +6 tests from Plan 12 baseline 441)
- 契约影响: `docs/design/enrollment.md` + `docs/design/credential_vault.md` + `docs/gateway-contract/v1/samples/` + `examples/`
- 红线守护 grep 记录
- 遗留项: official Plan 12 image 尚不含 NautilusTrader + sops + age，testnet example 暂保留专用 Dockerfile；distribution follow-up 决定是否扩充 official runtime image

**Step 3 (红线 gate 满足度 table, lesson #40)**:
| red_line | code_coverage | runtime_wire | defer_status | follow_up_plan_ref |
|----------|---------------|--------------|--------------|--------------------|
| 0.1 Key/KEK 永不出进程 | `test_permission_scope_written_to_encrypted_payload` + `test_permission_scope_in_audit_event` | vault.py CLI flag → put 逻辑 → encrypted payload | in-scope, fully wired | none |
| 0.2 G6 host gate 不绕过 | 本 plan 不触碰; regression sanity | 保持 Plan 03 + Plan 11 wire | in-scope, preserved | none |
| 0.3 Reconcile 失联 ≠ 停止 | 本 plan 不触碰 | Plan 04 wire 不变 | in-scope, preserved | none |
| 0.4 Money math Decimal / wire str | telemetry_snapshot.json sample 演示 Decimal-string 契约; schema 层 (Plan 12 T7) 已 pin | 无 runtime 触碰 | out-of-scope | none |

**Step 4 (提交)**: `git add .forge/README.md .forge/plans/2026-07/13-ps-deploy-support.md`, commit `docs(custos): plan 13 close-out — ps deploy/custos/ support (permission-scope + sandbox pattern + samples + examples)`。

## 验证清单 (Verification)

- [ ] `uv run pytest tests/test_vault_put_permission_scope.py tests/test_gateway_contract_v1_samples.py tests/test_examples_docs_v020_alignment.py -v` 全绿 (5+5+多=~15 tests)
- [ ] `make verify` 全绿 (441 → 447+ passed, 1 xfailed 不变)
- [ ] `arx-runner vault put --help` 显示 `--permission-scope` flag + `choices=["trade_no_withdraw"]`
- [ ] `arx-runner vault put --permission-scope withdraw ...` exit 2 (argparse choices 拒)
- [ ] `docs/design/enrollment.md` 含 "Sandbox mode: manually-constructed runner.toml" 章节标题
- [ ] `docs/design/credential_vault.md` 含 "Permission scope" 章节标题
- [ ] `ls docs/gateway-contract/v1/samples/` 有 5 files (4 wire + 1 deployment_spec_sandbox)
- [ ] `jsonschema` validate 4 samples vs corresponding schema 全 pass
- [ ] `grep -rn 'sops-file\|age-key-file\|python -m custos' examples/` 0 命中
- [ ] Non-Custodial 红线 grep (对齐 verification.md §红线专项检查): 
  - `permission_scope` 从 CLI flag 单源, 不硬编码 (grep 无残留硬编码 fallback)
  - examples/ 无 `.env` 引用 raw API secret (与 nautilus deploy/conf/.env 明文对照, 本 plan 后 example 明说 vault put)

## 进度追踪 (Progress)

| Task | Status | Completed | Notes |
|------|--------|-----------|-------|
| T1 vault put --permission-scope flag | ✅ | 2026-07-11 | 5 tests; explicit choices/default wired to encrypted payload and audit event; `make verify` 446 passed |
| T2 enrollment.md sandbox pattern + credential_vault.md permission scope 章节 | ✅ | 2026-07-11 | Synced enrollment, credential vault, and domain authorities; `make verify` 446 passed |
| T3 gateway-contract v1 samples/ | ✅ | 2026-07-11 | 5 samples + Draft 2020-12 validation; jsonschema dev dependency; `make verify` 451 passed in dev+nautilus environment |
| T4 examples/supertrend-{sandbox,testnet}/ 刷新 v0.2.0 CLI | ✅ | 2026-07-11 | 12 alignment tests; compose config parses; legacy CLI scan 0 hits; `make verify` 463 passed |
| T5 close-out + 索引 + 红线 gate 表 | 🔲 | | |

## 偏离与改进日志 (Deviations & Improvements)

| 类型 | 位置 | 描述 | 已批准 |
|------|------|------|--------|
| IMPROVEMENT | `docs/ops/05-deployment.md` 遗留已由并行提交解决 | 起草时记录的 systemd/manual-install gap 已在本 plan 执行前由 `88769e5` 刷新；T4 只处理仍存在的 examples gap。 | ✅ `88769e5` |
| DEVIATION | `--permission-scope` choices 只 1 值 | 目前 choices=["trade_no_withdraw"] 只 1 合法值, 为未来加 scope (e.g. `spot_only`) 预留结构。加值需 minor bump + arx 侧同步。 | ✅ CEO 2026-07-11 |
| IMPROVEMENT | audit event 含 scope | scope 是 metadata 非 secret, log 是 audit 兑现 (对账不静默); Plan 11 lesson #21 精神 | — |
| IMPROVEMENT | sample fixture 与 schema 同层 | 单源真理, 消费者 grep sample vs schema 关联清晰 | — |
| IMPROVEMENT | 执行前计划一致性修正 | T2 按 mandatory-rules 补 `docs/domain.md`; T3 补 deployment spec schema + jsonschema dependency/lockfile 的文件与 commit scope; T4 补齐 sandbox spec 文件清单。 | ✅ 用户 2026-07-11 |
| IMPROVEMENT | gateway contract role 文档同步 | 新增 informative deployment spec schema 后同步 `docs/gateway-contract/v1/README.md`, 明确它不进入 4 份 normative arx wire schema 的 backward-compat freeze。 | ✅ 用户 2026-07-11 修正授权 |
| DEVIATION | `make install` 后 base verify 的既有 extra 漂移 | `make install` (`uv sync --extra dev`) 会移除 nautilus extra；未 skip 的 `test_toolkit_import_bootstrap_resolves_shared_and_pandas_ta` 随后因 dev 环境无 `pkg_resources` 失败（387 passed, 1 failed）。本 plan 不扩 scope 修改既有 toolkit/test 依赖契约；恢复规则允许的 `uv sync --extra dev --extra nautilus` 后 `make verify` 451 passed。需由独立 infra plan 决定让该测试在 base 环境 skip，或补足其轻量依赖。 | ⚠️ 待后续 plan |
| DEVIATION | T4 保留 testnet 专用 Dockerfile | 执行时实证 Plan 12 official image 的 ENTRYPOINT 已含 `start`，且 image 未安装 nautilus extra、sops、age；直接消费会使 compose 重复 `start` 且 testnet/vault runtime 不可用。经用户批准，保留并现代化 example Dockerfile；official image 能力缺口 defer 到 distribution follow-up。 | ✅ 用户 2026-07-11 |
| IMPROVEMENT | T4 YAML test 依赖闭环 | alignment test 使用结构化 YAML parse；把项目已有的 `pyyaml>=6` 同时加入 dev extra，避免干净 dev 环境 collection fail。 | ✅ 用户 2026-07-11 继续授权 |

## 关联文档 (Related Documents)

- ps `philosophers-stone/.forge/plans/2026-07/01-custos-deploy-target.md` — 消费本 plan 产出 (permission-scope + sandbox pattern + samples + examples 刷新)
- custos Plan 11 (`11-custos-cli-subcommand-align-lifecycle.md`) — CLI clean-break 上游 (permission-scope 隐含决策来自此)
- custos Plan 12 (`12-custos-distribution-signed-wheel-docker-lts.md`) — 遗留项 DEV-12-T9-PLAN-11-T9-DOCS-OPS-GAP 本 plan 偿还 examples/ 部分
- custos `docs/design/enrollment.md` + `docs/design/credential_vault.md` — 权威文档 modify 目标
- custos `docs/gateway-contract/v1/*.schema.json` — Plan 12 T7 wire 契约, 本 plan 加 samples

---

*Drafter: Claude (opus-4-7[1m]) @ 2026-07-11*
*Wave: independent (支撑 ps Plan 49)*
