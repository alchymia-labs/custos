# enrollment — EnrollmentToken 配对协议

> Custos 六件套之一。源码：`src/arx_runner/enrollment.py`。

## 模块职责

`enrollment` 负责把一台 Custos runner 经**一次性 / 可吊销的 EnrollmentToken**
注册到某个 tenant（租户），并把注册结果持久化到本地 `enrollment.json`。这是
runner 生命周期的第一步：注册之前 runner 不被云端（arx 协调层）识别，注册之后
才能以已知 `runner_id` 上报 heartbeat / 遥测。

配对流程（云端 issue → 本地 enroll）：

1. 云端（arx）签发 token，只把 **sha256 hash 落库**（明文不落库）。
2. 用户把 token 明文拷贝给自己机器上的 runner。
3. `EnrollmentClient.enroll(plaintext_token)` 计算 hash → 经 NATS
   publish 到 enrollment subject → 等云端确认 → 持久化 `runner_id`。
4. **`paper_only=True` 是默认值**：实盘（live mode）需要用户在云端单独签发一张
   `paper_only=False` 的 token 作为显式升级路径，不能靠 runner 自行提权。

主要抽象：`EnrollmentClient`（dataclass），状态落在 `enrollment.json`（0600 权限）。

## 关键接口

> **对外暴露口径（DEV-60-R3-ARX-SINGLE-EXIT）**：本模块的 API surface 只被 arx
> 协调层消费，不对外部用户 / API 客户端 / dashboard 直接暴露。runner 通过 NATS
> 向 arx（gateway）发 enrollment，云端确认与 RBAC 校验由 arx tenancy crate 的
> gatekeeper 承担。*This module's API surface is consumed exclusively by the arx
> coordination layer; no direct external client access.*

| 符号 | 签名 | 说明 |
|------|------|------|
| `hash_token` | `hash_token(token: str) -> str` | token 明文的 SHA-256 hex digest |
| `EnrollmentClient` | dataclass(`nats_client`, `tenant_id`, `runner_id`, `enrollment_path`, `confirm_timeout_secs=30.0`) | 配对客户端 |
| `EnrollmentClient.enroll` | `async enroll(token, agent_version="", capabilities=None) -> bool` | 发布 hash + 等确认 + 持久化 |
| `EnrollmentClient.is_enrolled` | `is_enrolled() -> bool` | 检查本地 `enrollment.json` 是否已存在且 `runner_id` 匹配 |

```python
client = EnrollmentClient(
    nats_client=nats,
    tenant_id="acme",
    runner_id="runner-7",
    enrollment_path=Path("~/.custos/enrollment.json").expanduser(),
)
ok = await client.enroll(plaintext_token, agent_version="1.0.0")
```

确认语义（v1）：确认是 out-of-band 的（HTTP API ack 或 NATS reply subject），v1
简化为固定超时 sleep + 本地记录，云端再经 `/api/v1/runners/enroll` 对齐。即便
publish 从未到达 broker，本地持久化仍让 runner 可用；云端会拒绝未对齐 runner 的
heartbeat，直到 enrollment 被 reconcile。

## 红线契约

- **token 明文不落云端库**：云端只存 sha256 hash（`hash_token`），明文只在用户
  手上和 runner 本地内存里出现一次。
- **paper_only 默认承重墙**：`paper_only=True` 是默认；实盘升级必须由云端单独签发
  `paper_only=False` token（对应 CLAUDE.md「paper 默认」+ paper/live 物理隔离红线的
  入口一侧）。runner 不能自我提权到 live。
- **tenant 隔离**：`runner_id` 与 `tenant_id` 一起持久化；一台 runner 只属于一个
  tenant，跨 tenant 上报由 subject 命名空间（`arx.{tenant}.…`）与 gatekeeper 拒绝。
- **enrollment.json 敏感文件权限**：持久化文件用 `0600`（含 token_hash 这一敏感
  凭证引用），与 credential_vault 的本地金库红线同源。

## 相关 gate

| gate | 与本模块的关系 | 触发时机 |
|------|----------------|----------|
| **G-SoD**（高敏感动作双人审批） | token issue 属经济/权限承重动作；云端签发 token 时 approver ≠ applicant | 云端 arx 签发 EnrollmentToken 时（不在 runner 侧执行，runner 只消费 token） |
| **G7-legal**（辖区 pre-flight） | 非直系亲属 non-founder 出资人对应的 runner enrollment 需先过 KYC / 豁免链 | 扩大出资人范围时；v1·team dogfood 保持 internal-first 亲友例外 |
| **G6**（live host 真实实现） | enrollment 只决定 paper/live 授权位（`paper_only`）；live 单实际执行仍受 G6 约束 | live mode spec 到达 nautilus_host 时（见 [nautilus_host.md](nautilus_host.md)） |

## 未来演化路线

- **短期**：云端 reply pattern 落地（NATS reply subject 精确确认），替换 v1 的固定
  超时 sleep（源码注释标 Phase 2 加 RBAC 后落地）。
- **中期**：token 过期语义（v1 无过期）+ 主动吊销广播（云端标记 revoked → runner
  下次 heartbeat 被拒 + 本地 enrollment.json 失效）。
- **长期**：多引擎 flavour（`custos-nt` / `custos-hummingbot` / `custos-freqtrade`）
  各自 `capabilities` 声明，enrollment 时上报引擎能力集供 arx 编排匹配。
