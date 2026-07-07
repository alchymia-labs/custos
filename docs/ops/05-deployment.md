# 05 — 部署

> custos daemon 部署方式. 涵盖当前可用与未来路径.

## 部署模型

**custos 是自托管 daemon**, 用户在自己基础设施上运行. 云端产品面 (arx) 不 `docker run`
进用户机器 — 它只发 `DeploymentSpec`, custos 本地 pull + reconcile.

## 当前可用部署方式

### 1. 本地开发 / 手动运行

```bash
uv sync --extra dev
python -m arx_runner --tenant-id acme --runner-id runner-7 --nats-url nats://arx.internal:4222
```

参数详见 [`../design/03-implementation.md`](../design/03-implementation.md) §运行方式.

### 2. systemd unit (Linux 服务器长驻)

`/etc/systemd/system/custos.service`:

```ini
[Unit]
Description=Custos self-hosted trading runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=custos
Group=custos
WorkingDirectory=/opt/custos
Environment="SOPS_AGE_KEY_FILE=/home/custos/.custos/vault/age.key"
ExecStart=/opt/custos/.venv/bin/python -m arx_runner \
  --tenant-id ${TENANT_ID} \
  --runner-id ${RUNNER_ID} \
  --nats-url nats://arx.internal:4222 \
  --sops-file /opt/custos/vault.yaml \
  --age-key-file /home/custos/.custos/vault/age.key
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

启用:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now custos.service
sudo journalctl -u custos -f  # 查日志
```

### 3. Docker (示例待 Plan 00c examples/ 落地)

Plan 00c examples/supertrend-testnet/ 将提供:
- 参考 `Dockerfile` (multi-stage build, 显式 `custos-runner` from pip)
- `docker-compose.yml` (custos + NATS local dev stack)
- `.env.example` (`TENANT_ID` / `RUNNER_ID` / vault path 环境变量注入)

未落地前, 生产用户按 systemd 或纯 python 部署.

## 未来部署路径 (README §Not Included Yet)

以下暂未落地, 已列为独立 follow-up plan:

- **CI + 签名 release pipeline**: 签名 wheel (`pip install custos-runner==X.Y.Z`, 校验签名)
  + 签名 docker image (`ghcr.io/the-alephain-guild/custos:X.Y.Z`, cosign 签名) +
  可复现构建 (ADR-012 v4 stage-3)
- **`custos-cli` 一键装脚本**: `curl https://get.custos.dev | sh` 装 binary + 生成
  `.custos/vault/` skeleton + 引导 EnrollmentToken 配对流程

## 部署前检查清单

- [ ] Python 3.11+ 已装
- [ ] `uv` 已装
- [ ] arx NATS endpoint 可达 (`telnet arx.internal 4222` 通)
- [ ] EnrollmentToken 从 arx 已获取 (一次性, 出 arx 只显示一次)
- [ ] `age-keygen` 已生成 age key 对, public key 已提交给 arx 侧配对
- [ ] sops 已用 age public key encrypt 交易所 API key vault
- [ ] `SOPS_AGE_KEY_FILE` 环境变量指向 age private key 文件 (权限 0600)
- [ ] `~/.custos/vault/` 目录权限 0700
- [ ] G6 gate 目标: paper mode (默认) / testnet / live (需 Plan 00c 放行流程)

## 首次启动流程

1. 装 custos: `pip install custos-runner` (未来签名 release; 当前 `uv sync --extra dev` from source)
2. 生成 age key: `age-keygen -o ~/.custos/vault/age.key`
3. 从 arx 获取 EnrollmentToken (arx dashboard)
4. 从 arx 获取 tenant_id
5. 首次启动 (无 runner_id, 走 EnrollmentToken 配对):
   ```bash
   python -m arx_runner --tenant-id acme --enrollment-token <one-time-token>
   ```
6. 配对成功后 `runner_id` 持久到 `~/.custos/state/runner_id`
7. 后续启动: `python -m arx_runner --tenant-id acme --runner-id <persisted-id>`

## 常见部署问题

见 [`runbook.md`](runbook.md) §常见故障排查.
