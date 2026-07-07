# 强制规则 (custos)

以下规则在 custos 仓库中必须遵守, 无例外. 本仓库是独立开源 Apache-2.0 项目,
外部审计员会 clone 单仓查代码; 规则集自足, 不依赖 workspace root.

## 0. Non-Custodial 4 红线 (承重墙, 违反=CRITICAL)

custos 是 "Key 和策略只在用户本地" 红线从设计声明升级为工程可验证的唯一路径.
以下 4 条不可绕过:

### 0.1 Key / KEK 永不出进程

- 用户交易所 API Key + credential_vault KEK **永不**通过网络出进程边界
- **禁止**: telemetry payload / 日志 / DeploymentStatus / heartbeat 携带 raw key material
- **禁止**: cloud SDK 依赖 (aws-cli / gcloud / azure) — 引入即视为 non-custodial 承重墙裂缝
- 审计入口: `docs/design/credential_vault.md` §KEK 生命周期
- 违反判定: 任何 `send` / `publish` / `log.info` 调用 payload 含 vault 解密后的原文

### 0.2 G6 host gate 不绕过

- Live venue 部署前必须通过 `NtTradingNodeHost` 的 G6 gate; `NoopHost` 仅限 paper/sim
- **禁止**: 在 `nautilus_host.py` 之外自建 venue client 直接下单
- 检查点: `docs/design/nautilus_host.md` §G6 gate 契约
- Plan 00c 是 G6 live release 的正式落地 plan

### 0.3 Reconcile 失联 ≠ 停止 (local fallback breaker)

- 云端 (arx) 断线时, custos runner **本地**继续运行:
  - 保留每策略/每账户 drawdown breaker
  - 保留结构性 `max_notional_per_runner` cap
- **禁止**: `reconcile.py` 在云端断线时暴力 `stop_all_strategies()` (除非本地 breaker 触发)
- 审计入口: `docs/design/reconcile.md` §失联降级

### 0.4 Money math 用 `Decimal` (str 化 wire), 禁 float

- 所有价格 / 金额 / notional 计算路径必须 `decimal.Decimal`
- Wire (NATS envelope / DeploymentStatus / telemetry) 序列化为 `str` 而非 float
- **禁止**: `float(price)` / `price * qty` 隐式转 float / `json.dumps(Decimal)` 直接调
- 审计入口: `docs/design/telemetry_actor.md` §money contract + `test_telemetry_money_contract.py`

## 1. 源码与运行时分离

| 路径 | 类型 | 可修改 |
|------|------|--------|
| `src/arx_runner/` | 源码 (Python module 名保留 `arx_runner`) | ✅ |
| `tests/` | 测试源码 | ✅ |
| `docs/` | 设计文档 | ✅ (需同步代码时) |
| `~/.custos/vault/` | 用户机器上的 KEK / age key | ❌ (**永不入 git**) |
| `~/.custos/state/` | 运行时状态 (runner_id / paper flag) | ❌ (运行时管理) |

## 2. Python 包命名保留

- Python 导入名: `arx_runner` (subtree split from arx 保留, 未来 rename 单独 plan)
- pip 分发名: `custos-runner` (`pyproject.toml`)
- 二者不一致是**已知**且**故意**的, README.md §Quick Start 已声明

## 3. 依赖引入

引入新依赖前:

1. **技术栈一致性**: 不得与 `tech-stack.md` 冲突
2. **许可证**: 仅允许 MIT / Apache-2.0 / BSD 依赖
3. **红线 0.1 检查**: 新依赖若引入 cloud SDK / 明文密钥库 / 同步 HTTP → 拒绝
4. **anchor commit**: `uv.lock` 必须同步 commit

## 4. Git 规范

- **Commit message**: Conventional Commits, scope 为 `custos`
  ```
  feat(custos): add G6 gate check to NtTradingNodeHost.start()
  fix(custos): correct decimal precision in telemetry payload
  docs(custos): update reconcile design for local fallback breaker
  ```
- **跨仓库 commit**: 本仓库独立, 但若 workspace 内工作时同时改 custos + arx, 仅
  `git add <specific-file>`, 禁 `git add .` / `-A` (workspace lesson #3 + custos 独立继承)
- **原子提交**: 一个逻辑变更一个 commit

## 5. 安全规则

- **secrets 不入 git**: `.gitignore` 已覆盖 `.env`, `*.age`, `.custos/`, `custos-vault/`
- **API Key 通过 credential_vault + sops+age 注入**, 禁硬编码
- **测试用 API Key**: 必须使用 mock 或 pytest fixture 生成的一次性 sandbox key,
  绝不 commit 真实交易所 key

## 6. 文档同步

- 触及 6 模块任一时, 必须同步更新 `docs/design/<module>.md`
- 触及 domain 概念 (Deployment / Runner / Enrollment) 时, 同步更新 `docs/domain.md`
- 引入新 plan 时, 更新 `.forge/README.md` 索引

## 7. 独立开源仓库自足纪律

- 规则集 / 权威文档 / verification 命令**不引用** workspace root 路径
- 生态参照 (`../../.claude/rules/*`) 仅供 workspace 场景开发者参考; clone 独立场景失效不阻塞
- 独立场景验证入口: `make verify` 应仅需 `uv sync --extra dev` 后即可跑通
