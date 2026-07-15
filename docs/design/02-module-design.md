# 02 — 模块设计索引

> 六模块 (六件套) 设计文档索引. 各模块细节在同目录同名 `.md`.

## 六模块导航

| 顺序 | 模块 | 一句话职责 | 承担红线 | 状态机 | 详细文档 |
|------|------|-----------|---------|-------|---------|
| 1 | `enrollment` | 一次性 `EnrollmentToken` 配对 + `runner_id` 签发 + `paper_only` 默认 | Token 一次性 (防重放) | offline → online / draining | [`enrollment.md`](enrollment.md) |
| 2 | `credential_vault` | sops+age 本地 KEK vault + `trade_no_withdraw` scope + 明文永不出进程 | 红线 0.1 Key / KEK 不出进程 | derived → active → cleared (TTL) | [`credential_vault.md`](credential_vault.md) |
| 3 | `nats_client` | JetStream client + subject naming + envelope schema 版本化 | Wire schema 版本化 + 契约防漂移 | connected → reconnecting (auto) | [`nats_client.md`](nats_client.md) |
| 4 | `reconcile` | Declarative loop: pull `DeploymentSpec` → start/stop NT → report `DeploymentStatus` | 红线 0.3 失联 ≠ 停止 | pending → running → degraded → stopped | [`reconcile.md`](reconcile.md) |
| 5 | `nautilus_host` | NT `TradingNode` 进程监督 + `ExecutionEngineAdapter` (CEX/NT) + **G6 host gate** | **红线 0.2 G6 gate 不绕过** | INITIALIZED → STARTED → STOPPED → DISPOSED | [`nautilus_host.md`](nautilus_host.md) |
| 6 | `runner_fact` | NT observations → closed typed facts → signed SQLite outbox → Crucible | 红线 0.1 + 0.4 (脱敏 + canonical decimal wire) | durable sequence/outbox | [`runner_fact.md`](runner_fact.md) |

## 依赖顺序 (启动)

模块启动初始化顺序 (`__main__.py` 编排):

```
1. credential_vault  (加载 age key + 派生 MasterKey, 可能需 user prompt)
2. enrollment        (读取本地 runner_id 或走 EnrollmentToken 首次配对)
3. nats_client       (建立 JetStream 连接; connected 后)
4. runner_fact producer (打开 sole SQLite state/outbox；准备 typed signed publication)
5. reconcile         (启 ReconcileLoop; 拉 DeploymentSpec 前置准备好)
6. nautilus_host     (由 reconcile 按 spec 触发 start; G6 gate 在此判定)
```

## 关键跨模块契约

### enrollment ↔ credential_vault

- `runner_id` (UUIDv7) 由 enrollment 生成 (一次性), 用作 `VaultNamespace` 的
  `namespace_id` 索引
- `HostIdentity.pubkey` (ed25519) 由 enrollment 本地生成, 私钥只在 credential_vault
  管理

### reconcile ↔ nautilus_host

- reconcile 拉 `DeploymentSpec` 后组装 `TradingNodeConfig` (`venues[].api_key =
  VaultRef(key_id)`), 传给 `nautilus_host.start(spec)`
- `nautilus_host.start()` 内部走 **G6 host gate**; `NoopHost` 拒 live
- reconcile 探测 `ActualState` 通过 `nautilus_host.probe(spec_id)` 获取 NT 进程状态

### nautilus_host ↔ runner_fact

- `NtTradingNodeHost` 只把明确支持的 local observations 交给 typed adapters；
  generic MessageBus topic 不得直接进入 NATS。
- OrderDenied / OrderRejected 等本地拒绝映射为脱敏的
  `RunnerRuntimeLogFact.v1`，再进入同一 signed outbox。

### runner_fact ↔ nats_client

- runner_fact 生成 closed `RunnerFactBatchV1`，subject 固定为
  `crucible.runner_fact.{mode}.{tenant}.{runner}.{deployment_instance_id}`。
- nats_client 只负责 exact subject 的 publish/PubAck；不得生成 ARX telemetry subject
  (legacy 契约测试文件名如保留，只能验证历史边界
  `subject_builder` 是 python module 命名习惯, 实际是函数不是类)
- envelope schema 版本化 (`payload_schema_version`) 由 nats_client 声明契约

## Wire contract 测试

- `test_wire_shapes.py` — 跨语言 wire fixture (arx 侧 Rust 生成参考, custos Python 消费;
  独立 clone 场景失效, 见 Plan 01 DEV-01-WIRE-FIXTURES)
- `test_nats_envelope.py` — envelope schema 单元测试
- `test_subject_builder_contract.py` — subject naming 契约
- `test_telemetry_money_contract.py` — Decimal 序列化契约 (红线 0.4)

## 失败模式测试分层

每模块的失败模式测试独立文件 (lesson #17 契约):

- `test_runner_fact*.py` — unknown kind/float reject、sequence、签名、PubAck 与 recovery
- `test_nats_wal_resilience.py` — NATS 断线 WAL 暂存 + 重连 drain
- (未来) `test_credential_vault_failure_modes.py` — vault_locked / age_key_missing / sops_decrypt_fail

## 未来模块 (待独立 plan)

- **native order interception**: engine-boundary deny/reject 直接映射 typed RunnerFact；不得恢复 ARX telemetry bridge
- **checkpoint**: 本地持久 + 重启幂等 (`docs/domain.md` §1.6 声明, 实现待 Plan 02+)
- **audit_log**: Vault 解密审计 (fs append-only log) (Plan 02+)
