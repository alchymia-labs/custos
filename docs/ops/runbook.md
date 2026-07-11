# Runbook — 运维手册

> custos daemon 生产运维手册骨架. 常见故障排查 + 恢复流程 + 日志 pattern.

## 日志基础

- **格式**: structlog JSON output (可 pipe 到 jq / Loki / Datadog)
- **事件名约定**: 动词过去时 / 状态名词, 英文 snake_case
- **红线**: 日志字段严禁含 `api_key` / `password` / `secret` / `age_key` / `kek` 原文
  (红线 0.1); 若需引用, 用 `key_hash` (sha256 first 8) 或 `credential_hint`

## 常见故障排查

### 1. `vault_locked`

**症状**: 启动或热重载后 `log.error("vault_locked", reason=...)`; 交易操作失败

**可能原因**:
- `SOPS_AGE_KEY_FILE` 环境变量未设 / 指向不存在文件
- age private key 权限不对 (需 0600)
- age private key 与 sops encrypt 时用的 age public key 不匹配

**排查步骤**:
```bash
# 1. 检查 env
echo $SOPS_AGE_KEY_FILE
ls -la $SOPS_AGE_KEY_FILE  # 权限应 -rw-------

# 2. 手动 sops 解密某 key (0.2.0 起 per-key .enc 模型, 每 credential 一个文件)
ls -la ~/.arx/vault/         # 权限应 drwx------ (0700), 每 .enc 应 -rw------- (0600)
sops --decrypt ~/.arx/vault/binance-paper.enc | head -5

# 3. 检查该 .enc 的 age recipients (sops encrypt 时用的 public key)
grep -A 3 'age:' ~/.arx/vault/binance-paper.enc | head -10

# 4. 对比本地 age key 的 pubkey
age-keygen -y $SOPS_AGE_KEY_FILE

# 5. 一键复合校验 (arx-runner 内置, 复用 credential_vault._verify_permission_scope)
arx-runner vault verify --key-id binance-paper
```

**修复**: 见 [`../design/credential_vault.md`](../design/credential_vault.md) §KEK provisioning +
`arx-runner vault put --key-id <key-id>` 重新加密该 credential.

### 2. `venue_auth_failed`

**症状**: NT `TradingNode` start 后 log `log.error("venue_auth_failed", venue=..., reason=...)`;
`DeploymentStatus.phase=error`

**可能原因**:
- API key 已过期 / 已在交易所侧撤销
- `trade_no_withdraw` scope 缺失 (若交易所要求)
- 网络问题 (IP 白名单未加)
- 时钟不同步 (Binance HMAC 签名对时钟敏感)

**排查步骤**:
```bash
# 1. NTP 检查
timedatectl status
sudo systemctl status systemd-timesyncd  # 或 chronyd

# 2. IP 白名单 (curl 交易所 ping endpoint)
curl -s https://api.binance.com/api/v3/ping
# OK 表示网络 + IP 白名单没问题

# 3. 手动测 API key (Binance 例子)
API_KEY=... uv run python -c "
from binance.spot import Spot
c = Spot(api_key='...', api_secret='...')
print(c.account())
"
```

**修复**: 更新 sops+age vault, hot reload 无需重启 daemon (credential_vault 支持
`reload()`).

### 3. `code_hash_mismatch`

**症状**: `DeploymentStatus.health.reason=code_hash_mismatch`; NT 拒 start

**可能原因**:
- `DeploymentSpec.code_hash` 与本地策略镜像 sha256 不一致
- 本地策略未升级 (arx 发了新 code_hash 但 custos 端策略 pip 未升级)
- 本地策略被篡改 (安全事件, 立即调查)

**排查步骤**:
```bash
# 1. 定位策略 pip 包 + 计算 hash (0.2.0 起策略走 register_strategy 装饰器 + pip 分发,
#    非 filesystem 存放; 定位方式 = pip show <strategy-package> → Location + 目录 sha256sum)
uv pip show <strategy-package> | grep '^Location:'
sha256sum "$(uv pip show <strategy-package> | awk '/^Location:/ {print $2}')/<strategy_module>/*.py"

# 2. 从 arx 拉 spec 看 code_hash
# (arx dashboard 或 nats-cli 订阅 spec subject)

# 3. 对比
```

**修复**: `pip install --upgrade <strategy-package>` 或从 arx 手动同步.

### 4. NATS 断线 (`nats_disconnected`)

**症状**: `log.warning("nats_disconnected", reason=...)`; 上报 telemetry 暂存 WAL

**可能原因**:
- arx NATS server 重启 / 维护
- 网络中断
- 认证 token 过期

**处理**: **custos 设计上失联 ≠ 停止** (红线 0.3). NT 继续跑, 本地 fallback breaker
守护, telemetry WAL 暂存. 恢复连接后 drain (见 `test_nats_wal_resilience.py`).

**排查步骤**:
```bash
# 1. 检查 arx NATS 可达
telnet arx.internal 4222

# 2. 检查 custos telemetry WAL 大小 (若过大接近 disk 满)
du -sh ~/.arx/state/telemetry-wal.db

# 3. 手动触发重连 (通常 nats-py auto reconnect, 无需)
```

### 5. G6 gate deny

**症状**: `log.error("g6_gate_denied", spec_id=..., trading_mode="live")`; live 部署被拒

**可能原因**:
- `nautilus_host` 使用 `NoopHost` (仅 paper/sandbox 支持)
- `LIVE_MODE=true` env 未设 (双守之一)
- Plan 00a `NtTradingNodeHost` 尚未落地 (v0.0.x)

**处理**: 生产用户先跑 Plan 00a; 或降级 spec 到 `trading_mode=testnet` / `paper`.

**永不绕过 G6 gate** (红线 0.2).

## 恢复流程

### daemon 崩溃

1. `systemctl status custos` 看退出码 + last log
2. `journalctl -u custos -n 100` 看崩溃前 100 行
3. 如涉及 NT panic / segfault → 上报 issue + rollback NT 版本
4. `systemctl restart custos` 重启 (systemd unit 已配 `Restart=on-failure`)
5. NT 通过 checkpoint (`~/.arx/state/`) 幂等恢复; `runner_id` + `long_term_credential`
   从 `~/.arx/runner.toml` 恢复无需重新 enroll

### 云端 (arx) 长时间失联

- **本地 fallback breaker 独立守**: 每策略 drawdown + `max_notional_per_runner` cap
- **不主动 stop_all_strategies** (违反红线 0.3)
- **保留最后一次 DeploymentSpec 缓存**: 按此运行, 直到 arx 恢复
- **上报事件缓冲 WAL 中**: arx 恢复后 drain uplink

### 用户主动降级到 paper

紧急事故通用预案 (红线松动的替代):

```bash
# 停 daemon
sudo systemctl stop custos

# 修改配置强制 paper_only
export CUSTOS_FORCE_PAPER_ONLY=1

# 重启
sudo systemctl start custos
```

## 日志 pattern (常见事件)

| 事件名 | 级别 | 含义 |
|--------|------|------|
| `runner_started` | info | daemon 主启动 |
| `enrollment_completed` | info | EnrollmentToken 配对成功, runner_id 持久 |
| `vault_unlocked` | info | credential_vault MasterKey 派生完成 |
| `nats_connected` | info | JetStream 建连 |
| `reconcile_loop_iteration` | debug | 每轮 reconcile 循环 (可 rate-limit) |
| `deployment_started` | info | NT `start()` 成功 |
| `deployment_stopped` | info | NT `stop()` 完成 |
| `heartbeat_published` | debug | 心跳发送 |
| `telemetry_snapshot_uplinked` | debug | 遥测摘要发送 |
| `g6_gate_denied` | error | G6 gate 拒 live (红线 0.2 守住) |
| `venue_auth_failed` | error | 交易所 API 认证失败 |
| `code_hash_mismatch` | error | 策略 hash 不匹配 |
| `nats_disconnected` | warning | NATS 断线 (WAL 暂存) |
| `wal_drain_completed` | info | NATS 重连后 WAL drain |

## 监控与告警 (未来)

- **Prometheus metrics**: 待未来 plan 加 exporter
- **健康检查 endpoint**: 待未来 plan (custos 目前无 HTTP 面, 状态通过 arx heartbeat)
- **告警接入**: arx 侧 `AlertEvent` 消费 custos `FailureEvent` uplink

## 参考

- 六模块故障详情: [`../design/`](../design/) 各模块文档
- 部署方式: [`05-deployment.md`](05-deployment.md)
- 常见 Python 错误: [`../../.claude/rules/common-errors.md`](../../.claude/rules/common-errors.md)
