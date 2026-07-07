# 技术栈约束 (custos)

custos 是**独立开源仓库** (Apache-2.0), 单栈 Python daemon. 本文件是仓库自足的技术栈规范,
不假设 monorepo workspace 存在.

## 语言与运行时

| 组件 | 语言 | 最低版本 | 包管理器 |
|------|------|----------|----------|
| custos runner | Python | >=3.11 | uv |

> **脚注 — `nt-runtime` extra 需 Python 3.12+**: base 包 (NoopHost / paper / 审计) 保持
> Python >=3.11 可装 (`requires-python` 不变); `nt-runtime` extra 引入的 NautilusTrader
> 1.227+ 只支持 Python >=3.12,<3.15, 故通过 PEP 508 marker
> (`nautilus-trader>=1.227; python_version >= "3.12"`) 门控: py3.11 装 base 时 NT 被跳过,
> py3.12+ 才拉真 NT. dev/CI 默认解释器 pin 在 `.python-version` (3.13), 使单 venv 既跑
> base 测试 (`make verify`) 又跑真 NT 集成测试 (`make verify-nt`).

## 包管理器强制规则

- **Python**: 使用 `uv`, 禁止直接使用 `pip` / `python -m pip` / `poetry`
  - 运行脚本: `uv run python script.py`
  - 运行测试: `uv run pytest` 或 `make test`
  - 安装依赖 (base + dev): `uv sync --extra dev`
  - 装 NT runtime (需 py3.12+): `uv sync --extra dev --extra nt-runtime`
- 锁文件 `uv.lock` 必须 commit, 保证可复现构建 (对 non-custodial 承重墙至关重要:
  外部审计员必须能确定运行的是哪份代码)

## 生产依赖 (declarative 在 pyproject.toml)

| 库 | 用途 | 备注 |
|----|------|------|
| `nats-py>=2.9` | NATS JetStream client | telemetry uplink + DeploymentSpec pull |
| `pydantic>=2.5` | Envelope schema + DeploymentSpec 数据模型 | wire contract 强类型 |
| `structlog>=24` | 结构化日志 (脱敏 / JSON output) | telemetry_actor 依赖 |
| `uuid6>=2024.1.12` | UUIDv7 for event ID | 事件时序单调 |

生产 NT host 依赖 `nautilus-trader` 是 optional `nt-runtime` extra (需 Python 3.12+),
见下「可选依赖」段 — base 审计/paper 安装不拉取。

## 开发依赖

| 库 | 用途 |
|----|------|
| `pytest>=8` | 测试 runner |
| `pytest-asyncio>=0.24` | async 测试 (asyncio_mode=auto) |

## 可选依赖 (`nt-runtime` extra, 已加)

| 库 | 用途 | 备注 |
|----|------|------|
| `nautilus-trader>=1.227` | 生产 NT host (`NtTradingNodeHost`) | marker 门控 py3.12+; base 审计装不拉 |
| `pyyaml>=6` | 读 strategy config.yaml | nt-runtime 内使用 |

`nt-runtime` 是生产 host 依赖, `pip install custos-runner` 默认不装 (external audit
场景只读代码不跑 NT). 装法: `uv sync --extra nt-runtime` (需 3.12+ 解释器) 或
`pip install "custos-runner[nt-runtime]"`.

## 未来加入

- **pyright** (typecheck): 类型检查; Makefile `typecheck` target 待后续 plan 加

## 禁止引入

- **同步 HTTP 客户端** (`requests` / `urllib.request`): custos 是 async daemon,
  同步网络调用会阻塞 asyncio loop
- **明文密钥库** (`keyring` / 明文文件读 API key): credential_vault 只走 sops+age
  (见 `docs/design/credential_vault.md`)
- **未审计的 NT MessageBus 序列化 sink**: telemetry_actor 是唯一出口
  (脱敏 + 白名单 + envelope schema)
- **cloud SDK** (aws-cli / gcloud / azure): non-custodial 承重墙 — custos daemon 只在
  用户本地跑, 不引 cloud provider SDK

## 类型检查

- **Python**: `pyright` (待未来集成; 当前用 `ruff` 承担 lint 责任)
- **格式化**: `ruff format` (line-length 88, 详见 `code-style.md`)
- **Lint**: `ruff check` (默认规则集 + `E` `W` `F` `I` `B` `UP`)
