# 05 — 部署

> custos daemon 部署方式. 涵盖当前可用与未来路径.

## 部署模型

**custos 是自托管 daemon**, 用户在自己基础设施上运行. 云端产品面 (arx) 不 `docker run`
进用户机器 — 它只发 `DeploymentSpec`, custos 本地 pull + reconcile.

## 当前可用部署方式

### 1. 本地开发 / 手动运行

```bash
uv sync --extra dev
python -m custos --tenant-id acme --runner-id runner-7 --nats-url nats://arx.internal:4222
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
ExecStart=/opt/custos/.venv/bin/python -m custos \
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
   python -m custos --tenant-id acme --enrollment-token <one-time-token>
   ```
6. 配对成功后 `runner_id` 持久到 `~/.custos/state/runner_id`
7. 后续启动: `python -m custos --tenant-id acme --runner-id <persisted-id>`

## 常见部署问题

见 [`runbook.md`](runbook.md) §常见故障排查.

## Docker Runtime Volume Mount

Since 0.2.0 the runtime image
(`ghcr.io/the-alephain-guild/custos:v0.2.0`) is a multi-stage build
that runs as UID/GID 1000 with `HOME=/home/custos` and declares
`VOLUME ["/home/custos/.arx"]` for persistent state. Operators bind
the container's `~/.arx` to the host `~/.arx` so per-key `.enc`
vault files and the `runner.toml` enrollment record survive
container restarts.

Recommended invocation:

```bash
docker run --rm \
    --name custos \
    -v "$HOME/.arx:/home/custos/.arx" \
    --user "$(id -u):$(id -g)" \
    ghcr.io/the-alephain-guild/custos:v0.2.0 start \
    --tenant-id acme \
    --runner-id "$(cat ~/.arx/runner.toml.runner_id)"
```

Notes:

- `--user "$(id -u):$(id -g)"` aligns the container process with the
  host user's UID/GID so bind-mounted files stay owned by the operator
  outside the container. Without this override the container writes as
  UID 1000, which on a host where the operator has a different UID
  results in files that read as `1000:1000` at rest — safe (correct
  ownership inside the container) but inconvenient (`chown -R`
  needed on the host to edit them).
- The image bakes `mkdir -p ~/.arx{,/vault,/state} && chown -R custos:custos ~/`
  during build (Plan 12 R2-M2 fix). A bind mount of an existing
  host `~/.arx` overrides those in-image directories, so the operator
  is responsible for ensuring the host directory exists and is
  readable by the mapped UID. Missing directory + missing volume =
  the first `arx-runner enroll` inside the container fails with
  `PermissionError: [Errno 13] Permission denied: '/home/custos/.arx/runner.toml'`
  — the daemon's structured log surfaces this fail-loud rather than
  silently degrading, so an operator sees the mount misconfiguration
  in the first reconcile iteration.
- OCI provenance labels
  (`org.opencontainers.image.revision` / `.source` / `.version`) are
  baked into the image at CI build time. Auditors can trace back to
  the exact tag + commit via `docker inspect --format
  '{{index .Config.Labels "org.opencontainers.image.revision"}}'
  ghcr.io/the-alephain-guild/custos:v0.2.0`.
- Signature verification lives in
  [`../../.github/workflows/scripts/verify-release.sh`](../../.github/workflows/scripts/verify-release.sh) —
  operators paranoid about supply-chain provenance can re-run it
  locally after `docker pull`.

