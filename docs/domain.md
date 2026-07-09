# custos — 子系统实施 domain（Non-Custodial 守护者视角）

> **定位**：本文档是 **custos 子系统内部实施 domain 的纸面 spec**——覆盖 custos 承担的实体细节 + 状态机 + 事件契约 + Non-Custodial 分层信任边界的技术兑现方式。
>
> **拆分背景**：custos 前身是 arx 的 `runner/` 目录（Python，NT 执行宿主）。[ADR-012 v4](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-012-arx-coordinator-shift.md) 决策将其抽出为独立 **公开开源** 仓库（Apache-2.0，day 1 public），作为"Key/策略只在本地"红线从**设计声明**升级为**工程可验证**的唯一路径。
>
> **与生态视角互补**：
> - 生态 12 BC 概念视角：`codex/projects/arx/00-core/domain-model.md`
> - 跨子系统边界与其他子系统实体清单：`codex/projects/ecosystem-entity-catalog.md`
> - custos 独立开源纪律：[ADR-012 v4](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-012-arx-coordinator-shift.md) §Custos + [ADR-014 v6](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-014-ecosystem-open-source-boundary.md)（Tier A · 完全开源）

## Status

**DRAFT v1** · Date: 2026-07-04 · Decider: wukai · Ecosystem Option B 分层 domain 治理 P1（custos 仓库尚未初始化，本文档为奠基 spec）

---

## 0. custos 在生态中的角色

**custos** 是**自托管 NT 执行宿主 + 声明式 reconcile 循环 + 本地 Vault**——是 Non-Custodial 承诺的技术锚点：用户交易 Key 与执行进程只在用户本地基础设施，云端 arx / Crucible / Speculum 永不持有。

### 0.1 生态角色定位

- **数据面承担者**：交易 Key 明文、NT 引擎进程、订单簿明细快照、Fill 事件、账户余额都只经过 custos 本地
- **控制面消费者**：从 arx / Crucible 拉期望态（DeploymentSpec）在本地对齐，回报实际态（DeploymentStatus）+ 遥测摘要
- **承重墙定位**：custos 不可被 arx 或 Crucible 替代——正因它跑在用户机器上、由用户审计代码、持自己的 Key，任何"云端替代 custos"的路径都直接击穿 non-custodial 红线

### 0.2 上下游图

```
    ┌────────────────────────────────────────────┐
    │  云端控制面（闭源，档 D 商业许可）             │
    │  ┌─────────┐   ┌────────────┐              │
    │  │  arx    │──▶│  Crucible  │  发布 Spec    │
    │  │ (SaaS)  │   │  (改造后)  │              │
    │  └─────────┘   └────────────┘              │
    │        ▲                │                   │
    └────────┼────────────────┼───────────────────┘
             │                │
   NATS      │                │  NATS Spec + EnrollmentToken 配对
   Status/   │                ▼
   遥测摘要   │       ┌────────────────────────────┐
             │       │  用户本地基础设施             │
             │       │  ┌──────────────────────┐   │
             └───────│──│      custos          │   │
                     │  │  ┌────────────────┐  │   │
                     │  │  │  Vault (Key)   │  │   │
                     │  │  ├────────────────┤  │   │
                     │  │  │  ReconcileLoop │  │   │
                     │  │  ├────────────────┤  │   │
                     │  │  │  NT Adapter    │  │   │
                     │  │  └───────┬────────┘  │   │
                     │  └──────────┼───────────┘   │
                     │             ▼                │
                     │       NautilusTrader         │
                     │       (Rust/Python)          │
                     │             │                │
                     │             ▼                │
                     │      交易所 (Binance/OKX)    │
                     └──────────────────────────────┘
```

**关键流向**：
- Spec 下行：Crucible 发布 `DeploymentSpec` → NATS → custos ReconcileLoop 拉取 → 本地 NT 启动
- Status 上行：custos 观察 NT 实际态 → 生成 `DeploymentStatus` → NATS → Crucible DB 更新
- 遥测上行：custos telemetry_actor 采集 Fill/Position/Balance 摘要 → NATS → Crucible 观测副本
- Key 边界：ExchangeCredential 密文 + KEK 只在 custos 本地 Vault，**不越过用户机器边界**

### 0.3 前身：arx runner/ 六模块对应

抽出前（现 `tesseract-trading/arx/runner/src/arx_runner/`）→ 抽出后（custos 独立 repo）：

| arx 现有模块 | custos 承担 BC | 说明 |
|-------------|--------------|------|
| `enrollment.py` | Runner 宿主 | EnrollmentToken 配对协议 |
| `deployment_reconciler.py` / `reconcile.py` | 声明式 reconcile | Spec 拉取 + 期望态本地对齐 |
| `credential_vault.py` | 本地 Vault | ExchangeCredential 加密存储 + KEK 派生 |
| `nautilus_host.py` / `nt_risk_engine.py` | NT 执行适配 | TradingNode 启停 + strategy mirror |
| `telemetry_actor.py` | 上报事件 | 遥测采集 + NATS 发布 |
| `nats_client.py` | 消息传输 | JetStream 订阅 + 发布骨架 |
| `config.py` / `log.py` | 本地持久 | Checkpoint + 恢复 |

---

## 1. 限界上下文（6 BC）

### 1.1 Runner 宿主（Runner / EnrollmentToken / HostIdentity）

**职责**：把一台用户机器注册为一个 tenant 的执行宿主，签发身份，跟 Crucible 云端建立信任通道。

| 实体 | 关键字段 | 不变量 |
|------|---------|-------|
| **Runner** | `runner_id` (UUIDv7) · `tenant_id` · `enrollment_id` · `host_identity_id` · `agent_version` · `capabilities`(JSON: engines/features/OS/arch) · `trust_boundary`(managed/self-hosted) · `status`(online/draining/offline) · `last_heartbeat_at` · `enrolled_at` | 一 `runner_id` 至多一个 `tenant_id`；`trust_boundary=self-hosted` 时 KEK 材料不可导出；`agent_version` 与发布签名一致 |
| **EnrollmentToken** | `token_id` · `tenant_id` · `token_hash`(sha256, 明文只在配对时可见一次) · `scope_bitmap` · `paper_only`(bool) · `issued_by` · `expires_at` · `used_at` · `revoked_at` | 一次性使用；`used_at` 后置立即失效；`paper_only=true` 的 token 配对出的 Runner 永远不发放 live scope |
| **HostIdentity** | `host_identity_id` · `runner_id` · `pubkey`(ed25519, 本地生成) · `hardware_fingerprint`(可选, 用户可关) · `created_at` | `pubkey` 私钥永远不出本地；配对协议基于此 pubkey 建立 mTLS 或 NATS auth |

### 1.2 声明式 reconcile（Spec / Status / Loop）

**职责**：拉云端期望态（DeploymentSpec），本地对齐（NT 启停 / 参数变更），回报实际态（DeploymentStatus）。对齐 ArgoCD level-triggered 模式——失联 ≠ 停止，停止必经显式 spec 变更。

| 实体 | 关键字段 | 不变量 |
|------|---------|-------|
| **DeploymentSpec**（本地缓存的云端权威）| `spec_id` · `tenant_id` · `strategy_id` · `version` · `parameters`(JSON) · `execution_engine_binding_id` · `trading_mode`(testnet/sandbox/live) · `target_runner_id`（必等于本机 `runner_id`）· `generation`(单调递增) · `code_hash`(live 必持 provenance) · `pulled_at` | 只读（云端权威）；`target_runner_id ≠ 本机 runner_id` 时忽略；`trading_mode=live` 时 `code_hash` 必与本地 image sha 匹配 |
| **DeploymentStatus**（本地生成，回报云端）| `status_id` · `spec_id` · `tenant_id` · `container_id` · `phase`(pending/running/degraded/stopped) · `observed_generation` · `health`(healthy/warning/error + reason) · `started_at` · `stopped_at` · `last_reconcile_at` · `reported_by_runner_id` · `reported_at` | `observed_generation` 单调（不倒退）；`reported_by_runner_id` 必等于本机；phase 变化必伴随 timestamp 更新 |
| **DesiredState**（内部聚合）| `spec_id` · `target_state`(RUN/STOP)· `expected_parameters`(JSON) | 由 spec 派生；驱动 reconcile 动作 |
| **ActualState**（内部聚合）| `spec_id` · `current_state`(RUN/DEGRADED/STOP)· `nt_process_pid`(可选) · `observed_at` | 由 NT 运行时探测；与 DesiredState 差异触发 reconcile |
| **ReconcileLoop**（进程内单例）| `loop_id` · `tenant_id` · `poll_interval_ms` · `last_pass_at` · `pending_specs[]` · `error_backoff_state` | 单例（同一 runner 一 loop）；异常必带指数退避；不能 blocking 其他 spec |

**关键不变量**：
- **level-triggered**：reconcile 每轮扫全部 spec，不依赖事件顺序
- **失联 ≠ 停止**：Crucible 云端失联时 custos 继续按上次 spec 运行 NT（Key 本地 + Spec 已缓存）
- **单调 generation**：`spec.generation > status.observed_generation` 触发 reconcile；`<` 说明云端回退，需人工介入

### 1.3 本地 Vault（VaultNamespace / EncryptedKey / MasterKey）

**职责**：ExchangeCredential 密文 + KEK 在本地加密存储，用户主密码派生 MasterKey；进程运行时只在内存解密单笔请求所需。

| 实体 | 关键字段 | 不变量 |
|------|---------|-------|
| **VaultNamespace** | `namespace_id` · `tenant_id` · `vault_path`(fs) · `created_at` · `algorithm`(argon2id + aes-256-gcm) | 一 tenant 一 namespace；跨 namespace 无法解密；`vault_path` 权限 0600 |
| **EncryptedKey** | `key_id` · `namespace_id` · `resource_type`(exchange_credential/api_token/session_key) · `resource_ref` · `ciphertext` · `nonce` · `wrapped_by_kek_id` · `created_at` · `last_accessed_at` | 密文永不解密到磁盘；解密只在 request-scoped 内存；`last_accessed_at` 更新触发 AuditLog |
| **MasterKey**（进程内瞬态）| `derived_at` · `expires_at`(TTL 短) · `source`(user_prompt/HSM/keyring) | 永不落盘；进程重启需重新派生；空闲超时清零 |
| **KEK**（Key Encryption Key）| `kek_id` · `namespace_id` · `wrapped_by_master_key`(密文) · `algorithm` · `rotated_at` · `previous_kek_ids[]`(用于 rotate 期间解密旧数据) | KEK 只在内存解密；rotate 后旧 KEK 保留过渡期 |

**红线**：
- **ExchangeCredential 明文永不离开 custos 进程内存**——即使给 Crucible 上报 `AlertEvent` 或 `AuditLog`，敏感值必脱敏（如 `api_key=<sha256_first_8>...`）
- **MasterKey 派生源用户可选**：CLI prompt / 系统 keyring（Keychain/Secret Service）/ 外接 HSM——custos 不做决策，只提供 pluggable 接口
- **KEK rotate 不影响运行 NT**：旧 KEK 在过渡期内解密旧密文，新写入用新 KEK

### 1.4 NT 执行适配（NTAdapter / TradingNodeConfig / StrategyMirror）

**职责**：把 `DeploymentSpec` 翻译成 NautilusTrader 的 `TradingNodeConfig`，启停 TradingNode 进程，镜像 arx `Strategy` 概念到 NT 的 `Strategy` 实例。

| 实体 | 关键字段 | 不变量 |
|------|---------|-------|
| **NTAdapter** | `adapter_id` · `runner_id` · `nt_version` · `active_trading_nodes[]`(pid + spec_id) · `started_at` | 一 adapter 一 runner；一 spec 至多一个 active TradingNode |
| **TradingNodeConfig** | `config_id` · `spec_id` · `venues[]`(exchange config, 引用 Vault Key) · `strategy_configs[]` · `data_engine_config` · `risk_engine_config` · `cache_config` | 由 Spec + Vault 引用组装；不落盘（内存构造后传给 NT）；venues 中的 API key 是 Vault 引用 handle，非明文 |
| **StrategyMirror** | `mirror_id` · `spec_id` · `arx_strategy_id` · `nt_strategy_id`(NT 内部)· `code_hash` · `state_snapshot_at` · `state_snapshot_ref` | `code_hash` 与 DeploymentSpec.code_hash 校验一致；`state_snapshot_ref` 指向本地 checkpoint（见 §1.6） |

**关键不变量**：
- **NT 启动必先校验 code_hash**：spec 里的 `code_hash` 与本地策略镜像的 sha256 不一致 → 拒绝启动，回报 `DeploymentStatus.phase=error, health.reason=code_hash_mismatch`
- **Vault 引用而非明文**：`TradingNodeConfig.venues[].api_key = VaultRef(key_id)`，NT 侧调用时通过 custos Vault 接口即时解密
- **strategy 隔离**：多个 strategy 跑同一 TradingNode 时，每 strategy 独立子进程或独立 asyncio task，异常不互相污染

### 1.5 上报事件（HeartbeatEvent / StatusReport / FailureEvent）

**职责**：定期心跳、状态回报、失败上报——是 Crucible 云端观察 custos 的唯一窗口。

| 实体 | 关键字段 | 用途 |
|------|---------|------|
| **HeartbeatEvent** | `event_id` · `runner_id` · `tenant_id` · `at`(monotonic + wall clock) · `agent_version` · `nt_version` · `active_spec_ids[]` · `resource_usage`(cpu/mem/disk 摘要) | 云端 Runner 存活探针（Crucible 失去心跳 N 分钟后 mark offline，但 **不下达 stop**） |
| **StatusReport** | `report_id` · `spec_id` · `tenant_id` · `deployment_status`(§1.2 完整快照) · `at` | Spec-Status reconcile 完成后的一次快照上报 |
| **FailureEvent** | `event_id` · `spec_id` · `tenant_id` · `severity`(warning/error/critical)· `reason_code`(枚举: nt_startup_failure / vault_locked / venue_auth_failed / code_hash_mismatch / …) · `detail`(脱敏) · `at` | 关键故障立即上报 → Crucible AlertEvent 生成 → arx 用户告警 |
| **TelemetrySnapshot**（摘要）| `snapshot_id` · `spec_id` · `session_id` · `orders_count` · `fills_count` · `pnl_summary`(不含明细) · `at` | 定期采样；不包含订单簿明细或 Fill 事件明文（明细太重且含敏感），只回报摘要 |

> **实现状态（FailureEvent）**：上表 `FailureEvent`（含 `reason_code` 枚举）是纸面
> 设计；`src/arx_runner/` 尚未 first-class 实现——`_report_status()` 发布的
> `DeploymentStatus` payload 无 `reason_code` 字段。当前结构化拒绝信号走
> `DeploymentStatus` `phase=degraded` + 双层 structlog 事件名，详见
> [`docs/design/reconcile.md` §Undeclared capability traceability](design/reconcile.md)。
> first-class `FailureEvent` uplink 是独立功能面 follow-up plan 候选。

**红线**：
- **上报事件不含 Key 明文**：任何 event payload 涉及敏感字段必脱敏（`api_key_sha8` / `credential_hint`）
- **上报事件不含策略源码**：策略在 custos 本地（策略仓库通过其他通道分发），事件里只带 `code_hash` 引用
- **NATS subject 按 tenant scope**：`arx.<tenant_id>.telemetry.<session_id>` / `arx.<tenant_id>.deployment.status.<spec_id>` / `arx.<tenant_id>.runner.heartbeat`

### 1.6 本地持久（Checkpoint / RestartRecovery）

**职责**：Runner 重启幂等——从本地 checkpoint 恢复 + Spec 复读云端，NT 继续运行不丢单。

| 实体 | 关键字段 | 不变量 |
|------|---------|-------|
| **Checkpoint** | `checkpoint_id` · `runner_id` · `spec_id` · `nt_state_snapshot_ref`(fs path) · `last_processed_fill_id` · `at` | 原子写（write-then-rename）；损坏时回退到上一个有效 checkpoint |
| **RestartRecovery**（进程启动流程）| `recovery_id` · `runner_id` · `started_at` · `phases[]`(vault_unlock / checkpoint_load / spec_refetch / nt_reattach) · `completed_at` · `failed_phase`(可选) | phase 顺序不可跳；`vault_unlock` 失败即整体退出（等待用户 prompt MasterKey）；`nt_reattach` 失败重新按 Spec 启动 |
| **LocalEventJournal**（append-only）| `journal_id` · `records[]`(reconcile decisions / vault access log / nt lifecycle) · `rotated_at` | append-only；本地审计用途；不上云（隐私边界）；rotate 按大小或时间 |

**关键不变量**：
- **重启幂等**：Runner 重启不重复处理已确认的 spec；`observed_generation` 从 checkpoint 恢复
- **NT 无状态时重启从 Spec 重建**：checkpoint 主要用于加速，即便丢失，从 Crucible 拉最新 Spec + NT 冷启动即可
- **LocalEventJournal 不上云**：用户本地审计权归用户；custos 只回报聚合摘要，不上传明细

---

## 2. Non-Custodial 分层信任边界（专章 · 最关键）

**这是 custos 存在的核心理由**。ADR-012 v4 §Rationale #5 的关键洞察：**只要数据面（NT + custos）开源可审计，控制面（arx / Crucible / 其他所有闭源子系统）即使被完全攻破，用户 Key 依然安全——因为 Key 根本不在控制面。**

### 2.1 数据面 vs 控制面切分

| 面 | 组成 | 开源状态 | 持有的敏感数据 |
|----|------|---------|---------------|
| **数据面** | custos + NautilusTrader | **全部开源**（Apache-2.0）| Key 明文 · 订单簿明细 · Fill 事件明文 · 账户余额明细 |
| **控制面** | arx · Crucible · Speculum · Athanor · Synedrion · Argus · Aletheia | 全部闭源（档 D）| Key 引用 handle · DeploymentSpec · StatusReport · 遥测摘要 · 治理决策 · RBAC |

### 2.2 Key 永不上云的技术锚点

- **ExchangeCredential 密文在 custos Vault 本地文件系统**（`~/.custos/vault/<tenant>/…`）
- **KEK / MasterKey 派生只在 custos 进程内存**——磁盘只有密文，进程重启后需重新派生
- **NT 调用交易所 API 时通过 custos Vault 接口即时解密**——密文不复制，明文只在单次请求 lifetime
- **上报事件 payload 强制脱敏**——`AlertEvent` / `AuditLog` 里的 credential 字段永远是 `sha8` 或 `hint`

### 2.3 用户验证路径极简

用户只需审计 **两个开源 repo** 即可确认信任模型：
1. **NautilusTrader upstream**（`nautilus-trader/nautilus_trader`，Rust + Python，MIT）——确认 NT 不有偷 Key 或代下单路径
2. **custos**（`the-alephain-guild/custos`，Apache-2.0）——确认 custos 不有以下反模式：
   - 不上传 Key 明文到 arx / Crucible / 任何云端
   - 不接收云端下发的"代解密"指令
   - 不接收云端下发的"直接下单"绕过策略指令
   - Vault 密文格式与算法与文档声明一致

不需要审计 arx / Crucible / Speculum / Athanor / Synedrion / Argus / Aletheia——即使它们全被攻破，用户的 Key 依然不在攻击范围。

**类比**：Vault agent-server 模型 · Snowflake control plane vs data plane · Terraform Cloud 分层信任。

### 2.4 承重墙原则

custos **不能被 arx 替代**——任何"云端替代 custos 直接下单"的架构提案都直接击穿 non-custodial 红线。这在 [ADR-012 v4](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-012-arx-coordinator-shift.md) §Custos 明文钉死：

> Runner 是用户装到自己基础设施上、持自己 Key 的守护进程；用户必须能审计代码才敢信任 Key 交给它。这是"Key/策略只在本地"红线从设计声明升级为工程可验证的唯一路径。

---

## 3. 跨系统契约

### 3.1 custos ↔ Crucible

| 契约 | 方向 | 传输 | Schema |
|------|------|------|--------|
| **DeploymentSpec 拉取** | Crucible → custos | NATS JetStream · subject `arx.<tenant>.deployment.spec.<runner_id>` | OpenAPI versioned schema |
| **DeploymentStatus 回报** | custos → Crucible | NATS JetStream · subject `arx.<tenant>.deployment.status.<spec_id>` | OpenAPI versioned schema |
| **HeartbeatEvent** | custos → Crucible | NATS · subject `arx.<tenant>.runner.heartbeat` | JSON Schema |
| **TelemetrySnapshot** | custos → Crucible | NATS · subject `arx.<tenant>.telemetry.<session_id>` | JSON Schema |
| **FailureEvent** | custos → Crucible | NATS · subject `arx.<tenant>.failure.<severity>` | JSON Schema |
| **EnrollmentToken 配对** | Crucible → custos | HTTP outbound · custos 主动拉 `POST /v1/enrollment/consume` | OpenAPI |

**契约版本化纪律**：所有 schema 用 `major.minor` 版本号；`major` 变更需要 custos ↔ Crucible 双方版本对齐窗口（∈ [3 月, 12 月]）——外部用户装的 custos 版本可能滞后 Crucible 半年。

### 3.2 custos ↔ arx（间接）

custos **不直接跟 arx 通信**——所有 arx 需要的数据都通过 Crucible 中转。arx 侧 UI 展示的 Runner 列表 / DeploymentStatus / 遥测都是 arx 从 Crucible DB 查询的观测副本，custos 不直连 arx。

**理由**：控制面收敛在 Crucible（自托管改造承担者），arx 作为协调器不重复承担运行时通信责任。这也降低 custos 需信任的云端组件数量（只需信任 Crucible schema，不需要额外信任 arx）。

### 3.3 custos ↔ Speculum（间接）

回测结果作为 DeploymentSpec 的**输入 provenance**，Speculum 生成的回测 report 通过 arx / Crucible 流转到 custos——但 custos 只消费最终 DeploymentSpec（含 `code_hash` + `parameters`），**不直连 Speculum**。

### 3.4 承接 Crucible 原 supervisor 迁移

原 Crucible `supervisor.py` 是**命令式直控 Docker**——custos 承接后改为**声明式 reconcile**。迁移灰度策略见 [Crucible domain.md §4.4](https://github.com/the-alephain-guild/tesseract-trading/blob/main/the-crucible/docs/domain.md)：

- **Phase 1（v1 内部）**：Crucible 侧保留 supervisor + 新增 spec/status 路径（双写、单读 supervisor）；custos 侧作为 `trust_boundary=managed` 部署（跟 Crucible 同机塌缩）
- **Phase 2**：切换到 spec/status 为权威；custos 独立进程但仍与 Crucible 同基础设施
- **Phase 3**：删除 Crucible supervisor 直接控容器代码；custos 纯声明式
- **Phase 4**：`trust_boundary=self-hosted` 全面启用；custos 迁移到用户自己的基础设施

---

## 4. Apache-2.0 开源治理

### 4.1 单点信任风险讨论

[ADR-012 v4](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-012-arx-coordinator-shift.md) §Rationale #5 明确：**custos 开源本身就是 non-custodial 红线的兑现方式**——但**"开源"不等于"自动可信"**。开源 repo 若被后门 commit 或恶意 release 也可能击穿信任。

**缓释措施**（写入 custos repo 治理文档）：
1. **可复现构建**（reproducible build）：wheel + docker image 需支持第三方独立复现；构建 recipe 公开；hash 与官方 release 一致
2. **签名 release artifact**：所有 wheel + docker image 用 GPG / cosign 签名；公钥公开；签名不匹配则视为不可信
3. **供应链 SBOM**：每 release 附 Software Bill of Materials（依赖清单 + 版本 + 哈希），便于用户审计
4. **多人 commit review**：`main` 分支强制 code review + 2 名 maintainer 签核；无单人 push 权限
5. **SECURITY.md 明确报告渠道**：漏洞报告流程 + 响应 SLA + 公开披露时间线

### 4.2 审计流程

- **每 release 前**：内部 code review + 外部安全审计（P4 商业化前至少一次）
- **升级审计**：`major` 版本 bump + 涉及 Vault / Key 处理路径的变更需要外部审计
- **社区 issue 优先响应**：用户提出"这行代码看起来会泄 Key"类 issue → 24h 内响应；确认漏洞 → CVE + 修复 + 用户通知

### 4.3 License 边界

- **本 repo**：Apache-2.0（含专利授权 + 允许闭源上层调用）
- **上游依赖**：NautilusTrader 是 MIT（宽松兼容），其他依赖必须是 Apache-2.0 / MIT / BSD（禁 GPL / AGPL / LGPL 避免传染）
- **下游调用者**：允许闭源 Crucible / arx 通过 NATS / HTTP 契约调用 custos——契约是 network boundary，不构成 derivative work

---

## 5. 演进要点

### 5.1 与 arx tenancy 的边界

- **custos 不做多租户**：一 host 一 user 是纪律——每个用户装自己的 custos 实例，`tenant_id` 只用于 NATS subject 路由和 Vault namespace 隔离，不做多租户资源隔离
- **多租户复杂度归 arx 云端**：租户 RBAC / 计费 / 限流 / 授权网关都在 arx 侧承担（[arx domain.md §2 coordination crate](https://github.com/the-alephain-guild/tesseract-trading/blob/main/arx/docs/domain.md)）
- **理由**：多租户混部与 non-custodial 红线冲突——多个用户的 Key 塌缩到同一进程会破坏隔离；一 host 一 user 是承重墙的自然形态

### 5.2 多引擎 flavour 前景

vision 支柱一"设计 for 3、实现 1"落到 custos 侧是三个 flavour：
- **custos-nt**（当前）：NautilusTrader 宿主
- **custos-hummingbot**（未来）：Hummingbot 宿主
- **custos-freqtrade**（未来）：Freqtrade 宿主

三 flavour 共享 Runner 宿主 / Vault / reconcile / 上报事件 5 个 BC，只有 NT 执行适配 BC 因引擎而异——可用 crate feature flag 或 monorepo workspace 拆分。

### 5.3 与 Crucible 自托管迁移的灰度策略

- **Phase 1（v1 内部）**：custos + Crucible + arx 同基础设施部署（`trust_boundary=managed`）——Non-Custodial 红线在架构上就位，但物理隔离度低（信任模型是"信团队"）
- **Phase 2-3**：Crucible 侧完成声明式 reconcile 改造，custos 侧签名 release + 可复现构建到位
- **Phase 4（对外）**：`trust_boundary=self-hosted` 全面启用——用户 `pip install custos-cli` / `docker pull ghcr.io/the-alephain-guild/custos:vX.Y.Z` 在自己基础设施装 custos，Non-Custodial 红线达到最完整形态

### 5.4 与生态其他子系统的关系变化

- **不承担 Crucible 治理**：custos 不做 RBAC / 策略角色 / 分润——那些在 Crucible 侧
- **不承担 arx 协调**：custos 不知道 Speculum / Athanor / Synedrion / Argus / Aletheia 的存在——只知道 Crucible 一个云端对端
- **不承担 nummus 支付**：custos 完全不涉及计费——支付订阅通过 arx 完成，custos 只在 tenant enrollment 时消费 EnrollmentToken 校验订阅有效

### 5.5 后续 spec 演进锚点

本文档定稿后，custos repo 初始化时的**首份 domain.md** 即从本文件迁入；后续 spec 演进（如 hummingbot flavour、per-strategy sub-vault、hardware key 集成）在 repo 内独立 ADR 记录，同步反哺生态 `codex/decisions/`。

---

## References

- Ecosystem 生态视角：`codex/projects/arx/00-core/domain-model.md`（12 BC）
- Ecosystem 子系统清单：`codex/projects/ecosystem-entity-catalog.md`
- arx 收缩为协调器决策：[ADR-012 v4](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-012-arx-coordinator-shift.md) §Custos 独立开源纪律
- 生态开源边界：[ADR-014 v6](https://github.com/the-alephain-guild/codex/blob/main/decisions/ADR-014-ecosystem-open-source-boundary.md) §Tier A · custos day 1 public
- arx 内部实施 domain：`tesseract-trading/arx/docs/domain.md`
- Crucible 改造 spec：`tesseract-trading/the-crucible/docs/domain.md` §自托管三件套 + §supervisor 声明式 reconcile 迁移
- arx runner 现有代码（抽出源头）：`tesseract-trading/arx/runner/src/arx_runner/`（enrollment / deployment_reconciler / credential_vault / nautilus_host / telemetry_actor / nats_client）

---

*Last updated: 2026-07-04（DRAFT v1 — custos 仓库未初始化，本文档为奠基纸面 spec。覆盖 6 BC 完整实体清单 + Non-Custodial 分层信任边界专章 + 与 arx / Crucible / Speculum 契约 + Apache-2.0 开源治理 + 演进要点。承重墙原则钉死：custos 不可被 arx 替代，Key/策略只在用户本地是唯一 non-custodial 兑现方式。抽出源头 arx `runner/` 六模块（enrollment / deployment_reconciler / credential_vault / nautilus_host / telemetry_actor / nats_client）映射到 6 BC。契约通过 versioned OpenAPI / JSON Schema 与 Crucible 对齐，允许 custos ↔ Crucible 版本滞后窗口。未来 flavour：custos-nt / custos-hummingbot / custos-freqtrade。）*
