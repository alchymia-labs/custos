# 05 — 部署

> custos daemon 部署方式. 涵盖当前可用与未来路径.

## 部署模型

**custos 是自托管 daemon**, 用户在自己基础设施上运行. 云端产品面 (arx) 不 `docker run`
进用户机器 — 它只发 `DeploymentSpec`, custos 本地 pull + reconcile.

## 当前可用部署方式

### 1. 本地开发 / 手动运行

自 0.2.0 起, custos 通过 `arx-runner` console script 分三步操作 (Plan 11 clean-break):

```bash
uv sync --extra dev

# a. 一次性 enroll — 从 arx 拿 long-term credential, 落 ~/.arx/runner.toml (mode 0600)
arx-runner enroll \
  --token <one-time-enrollment-token> \
  --backend https://arx.internal:8000 \
  --tenant-id acme \
  --runner-id runner-7

# b. 每个交易所 credential 单独 sops+age 加密, 落 ~/.arx/vault/<key-id>.enc (mode 0600)
export SOPS_AGE_RECIPIENT=age1...    # 用于 encrypt 的 age public key
arx-runner vault put --key-id binance-paper \
  --api-key-stdin --api-secret-stdin

# c. 日常启动 (读 ~/.arx/runner.toml + ~/.arx/vault/*.enc)
export SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key   # 用于 decrypt 的 age private key
arx-runner start --nats-url nats://arx.internal:4222
```

参数详见 [`../design/03-implementation.md`](../design/03-implementation.md) §运行方式.

`~/.custos/` 命名空间在 0.2.0 已退休; 从 0.1.x 升级需按 [CHANGELOG.md 0.2.0
Upgrade Notes](../../CHANGELOG.md) 手动迁移 `~/.custos/{enrollment.json,state}` →
`~/.arx/`, 并按 `arx-runner vault put` 逐 credential 重新加密 (`SopsAgeVault`
多 credential JSON 模型已删除).

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
Environment="SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key"
ExecStart=/opt/custos/.venv/bin/arx-runner start \
  --nats-url nats://arx.internal:4222
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

`tenant_id` / `runner_id` / `long_term_credential` 在 `arx-runner enroll` 时已持久化到
`~/.arx/runner.toml`, 无需 systemd unit 再显式传参. `SOPS_AGE_KEY_FILE` 是
`PerKeyVault` 解密 `~/.arx/vault/*.enc` 时 sops 需要的 age private key (红线 0.1
mode 0600), 保留为 env var 不落 CLI 明文.

启用:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now custos.service
sudo journalctl -u custos -f  # 查日志
```

### 3. Docker (v0.2.0 起 official image)

Plan 12 落地 multi-stage Dockerfile + 签名 image, GHCR 发布:

```bash
docker pull ghcr.io/the-alephain-guild/custos:v0.2.0
```

启动命令见下 §"Docker Runtime Volume Mount" (非 root user + `~/.arx` bind mount +
OCI provenance labels + sigstore 签名验证).

## 未来部署路径 (README §Not Included Yet)

以下暂未落地, 已列为独立 follow-up plan:

- **CI + 签名 release pipeline**: 签名 wheel (`pip install custos-runner==X.Y.Z`, 校验签名)
  + 签名 docker image (`ghcr.io/the-alephain-guild/custos:X.Y.Z`, cosign 签名) +
  可复现构建 (ADR-012 v4 stage-3)
- **`custos-cli` 一键装脚本**: `curl https://get.custos.dev | sh` 装 binary + 生成
  `.custos/vault/` skeleton + 引导 EnrollmentToken 配对流程

## 部署前检查清单

- [ ] Python 3.11+ 已装 (Docker image 内自带 3.12-slim)
- [ ] `uv` 已装 (仅源码路径需要)
- [ ] arx NATS endpoint 可达 (`telnet arx.internal 4222` 通)
- [ ] EnrollmentToken 从 arx 已获取 (一次性, 出 arx 只显示一次)
- [ ] `age-keygen` 已生成 age key 对, public key 用于 `arx-runner vault put` encrypt
- [ ] `SOPS_AGE_KEY_FILE` 环境变量指向 age private key (权限 0600, `PerKeyVault` 解密用)
- [ ] `~/.arx/` 目录已建 (权限 0700, `arx-runner enroll` 首次自动创建)
- [ ] G6 gate 目标: paper mode (默认) / testnet / live (Plan 00c capability-based 放行流程 landed)

## 首次启动流程

1. 装 custos: `pip install custos-runner==0.2.0` (0.2.0 起签名 wheel + docker image;
   本地开发 `uv sync --extra dev` from source)
2. 生成 age key 对: `age-keygen -o ~/.arx/age.key && chmod 600 ~/.arx/age.key`;
   记录输出的 public key (`age1...`), export 为 `SOPS_AGE_RECIPIENT`
3. 从 arx 获取 EnrollmentToken (arx dashboard, 一次性)
4. 从 arx 获取 tenant_id 与 runner_id (人工分配)
5. `arx-runner enroll` 交换 long-term credential + 落 `~/.arx/runner.toml` (mode 0600):
   ```bash
   arx-runner enroll \
     --token <one-time-enrollment-token> \
     --backend https://arx.internal:8000 \
     --tenant-id acme \
     --runner-id runner-7
   ```
6. `arx-runner vault put` 逐 credential 加密到 `~/.arx/vault/<key-id>.enc` (mode 0600):
   ```bash
   arx-runner vault put --key-id binance-paper --api-key-stdin --api-secret-stdin
   ```
   可跑 `arx-runner vault verify --key-id binance-paper` 确认 decrypt 通过 +
   `trade_no_withdraw` scope 校验通过.
7. 后续启动 (读 `~/.arx/runner.toml` 恢复所有身份 + `~/.arx/vault/*.enc` per-key):
   ```bash
   export SOPS_AGE_KEY_FILE=~/.arx/age.key
   arx-runner start --nats-url nats://arx.internal:4222
   ```

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

