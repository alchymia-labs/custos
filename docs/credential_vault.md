# credential_vault — sops+age 本地金库

> Custos 六件套之一。源码：`src/arx_runner/credential_vault.py`。**Key 本地金库承重墙**
> —— 生态 non-custodial 兑现载体核心。

## 模块职责

`credential_vault` 是 Custos 持有 operator 交易所凭证的本地金库。它把加密的凭证在
runner 本地解密成交易所 API key，交给 `nautilus_host` 下单——**KEK（age 私钥）永不
出主机，云端产品面 schema 永不持有 key**。这是 CLAUDE.md「Key/策略逻辑只在 runner
本地」红线的工程兑现点，也是 custos 必须开源的根本原因：operator 能审计这段代码，才
敢把 key 交给 daemon。

V1 实现：

- **`CredentialVault`（Mock）**：返回占位凭证 dict + emit 审计事件，供 test / dev。
- **`SopsAgeVault`**：shell out 到 `sops --decrypt`（age 私钥经 `SOPS_AGE_KEY_FILE`
  定位），读解密后的 secret + emit 审计事件，**永不日志 plaintext**。
- **未来**：Hashicorp Vault provider（team tier）——Vault token 也只在 runner。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块**绝不**对任何外部方暴露 key
> 或解密接口；`decrypt` 只被本地 `DeploymentReconciler` 调用。runner 出网只有遥测 +
> 状态，plaintext 永不上 NATS / HTTP。*This module's API surface is consumed
> exclusively by the arx coordination layer (audit signals only); no direct external
> client access, and credentials never leave the host.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `CredentialVaultProtocol` | `decrypt(credential_id: str) -> dict` | 金库接口；实现必须在每次成功 decrypt 时 emit 审计事件 + 校验 `permission_scope` 非提币 |
| `CredentialVault` | `decrypt(credential_id) -> dict` | Mock 金库（test/dev） |
| `SopsAgeVault` | `__init__(*, sops_file, age_key_file, tenant_id, initiator)` + `decrypt(...)` | sops+age CLI 集成 |
| `AuditEvent` | `enum`（`CREDENTIAL_DECRYPTED = "CredentialDecrypted"`） | 闭枚举，防 rename 静默破坏审计 writer 的 pattern match |

`_verify_permission_scope` 拒收 `permission_scope != "trade_no_withdraw"` 的凭证；
`_emit_decrypt_audit` 发 `CredentialDecrypted` 审计事件（只带 `credential_id` 引用，
**plaintext 永不进审计日志**）。

## 红线契约

- **KEK 不出本地**：age 私钥 / Vault token 永不离开 runner 主机；云端 schema 永不
  持有 key。
- **`permission_scope = trade_no_withdraw` 强制**：金库拒收任何允许提币的凭证
  （`_verify_permission_scope`），从 key 权限层堵死资金外流。
- **每次 decrypt 必发审计事件**：`CredentialDecrypted` 审计事件供下游 audit writer
  构建不可变链（audit 三件套）；「对账不静默」在凭证层的体现。
- **plaintext 零泄露**：不日志 plaintext、不写 NATS plaintext、不写 HTTP plaintext；
  `age_key_file` 默认 `0600`，sops stderr 不含 plaintext（sops 设计如此）。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G7-legal**（辖区 pre-flight / KYC / 豁免链） | 持有他人资金对应凭证前需过 KYC + 辖区豁免链；非直系亲属 non-founder 出资人扩围前须补 licensed counsel 意见 | 出资人 CapitalContribution 入库前 / 扩大出资人范围时 |
| **G-SoD**（高敏感动作双人审批） | 凭证的新增 / 轮换 / 提币 scope 变更属承重动作，approver ≠ applicant | 云端 arx 侧凭证生命周期操作时 |

## 未来演化路线

- **短期**：Hashicorp Vault provider（team tier），统一 KEK 管理但 token 仍只在 runner。
- **中期**：凭证轮换（rotation）+ 短时租约（lease）机制，减小 key 静态暴露面。
- **长期**：HSM / 硬件签名器集成，把 KEK 从软件金库进一步下沉到硬件不可导出边界，
  强化 agentic capital 底座的信任叙事（vision 支柱四）。
