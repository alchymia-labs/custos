# 03 — 实现细节

> 技术栈 · 依赖 · 项目结构 · 运行方式.

## 技术栈

- **语言**: Python >=3.11 (async 优先)
- **包管理**: `uv` (禁 pip / poetry)
- **格式化 / lint**: `ruff` (format + check, line-length=100)
- **测试**: `pytest` + `pytest-asyncio` (`asyncio_mode=auto`)
- **未来**: `pyright` 类型检查 (待 Plan 02+ 集成)

详见 [`../../.claude/rules/tech-stack.md`](../../.claude/rules/tech-stack.md).

## 生产依赖 (`pyproject.toml`)

| 库 | 版本 | 用途 |
|----|------|------|
| `nats-py` | >=2.9 | NATS JetStream client (telemetry uplink + spec pull) |
| `pydantic` | >=2.5 | Envelope schema + DeploymentSpec 数据模型 |
| `structlog` | >=24 | 结构化日志 (脱敏 + JSON output) |
| `uuid6` | >=2024.1.12 | UUIDv7 for event ID (时序单调) |

## 开发依赖 (`optional-dependencies.dev`)

| 库 | 版本 | 用途 |
|----|------|------|
| `pytest` | >=8 | 测试 runner |
| `pytest-asyncio` | >=0.24 | async 测试 |
| `ruff` | >=0.6 | format + lint |

## 未来依赖 (待独立 plan)

- `nautilus-trader` — NT runtime, 作为 `nt-runtime` optional-dep 加入 (Plan 00a)
- `pyright` — 类型检查, dev 加 (未来独立 style plan)

## 项目结构

```
custos/
├── src/arx_runner/           ← Python 模块 (导入名保留 arx_runner, pip 名 custos-runner)
│   ├── __init__.py
│   ├── __main__.py            ← daemon 入口 (asyncio 编排 6 模块)
│   ├── config.py              ← DeploymentSpec / TransportEnvelope Pydantic 模型
│   ├── enrollment.py          ← EnrollmentToken 配对 + runner_id 持久
│   ├── credential_vault.py    ← sops+age 本地 KEK vault
│   ├── nats_client.py         ← JetStream client + build_subject() 函数
│   ├── reconcile.py           ← ReconcileLoop (level-triggered)
│   ├── deployment_reconciler.py ← reconcile 高层编排
│   ├── nautilus_host.py       ← NoopHost + NtTradingNodeHost + G6 gate
│   ├── nt_risk_engine.py      ← 本地 fallback breaker (drawdown + max_notional)
│   ├── telemetry_actor.py     ← NT MessageBus → NATS uplink (脱敏 + Decimal wire)
│   └── log.py                 ← structlog 配置
│
├── tests/                     ← pytest 测试 (115 pass baseline, 9 wire_shapes fail known)
├── scripts/
│   └── generate_wire_fixtures.py  ← 跨语言 wire fixture 生成 (arx 侧参照)
├── docs/
│   ├── domain.md              ← 顶层纸面 spec (6 BC + 分层信任边界)
│   ├── design/                ← 本目录 (架构 + 模块设计)
│   ├── ops/                   ← 部署 + runbook
│   └── guides/                ← 测试策略 + 开发上手
├── .claude/                   ← Claude Code 独立规则集
├── .forge/                    ← forge 工作流 plan + teams 配置
├── pyproject.toml
├── uv.lock                    ← 依赖锁 (必 commit, 保证可复现构建)
├── Makefile                   ← check / test / verify 等 target
├── CLAUDE.md                  ← AI 助手导航图
├── README.md                  ← 门面 (对外)
├── LICENSE                    ← Apache-2.0
└── NOTICE                     ← 归属声明
```

## Python 模块命名

- **pip 分发名**: `custos-runner` (`pyproject.toml` `[project].name`)
- **Python 导入名**: `arx_runner` (`src/arx_runner/`)
- **原因**: subtree split from arx 保留 import 兼容; rename `arx_runner` → `custos_runner`
  是独立 follow-up plan (boundary constant fanout ~40 import site)
- **hatchling 桥接**: `[tool.hatch.build.targets.wheel] packages = ["src/arx_runner"]`
  显式声明 (Plan 01 DEV-01-PYPROJECT-HATCH)

## 运行方式

### 装依赖

```bash
uv sync --extra dev
```

### 跑 daemon (paper mode 默认)

```bash
python -m arx_runner --tenant-id acme --runner-id runner-7 --nats-url nats://localhost:4222
```

参数:
- `--tenant-id` — 用户 tenant 标识 (必)
- `--runner-id` — Runner 标识 (可省, 走 EnrollmentToken 首次配对)
- `--nats-url` — arx NATS endpoint (默认 `nats://localhost:4222`)
- `--sops-file` + `--age-key-file` — sops+age 凭据 (可省, 走 CLI prompt)
- `--paper-only` — 强制 paper 模式 (默认 True, live 需 G6 gate 显式放行)

### 跑测试

```bash
make verify         # check (fmt-check + lint) + test-baseline (115 pass)
make test           # 完整 pytest (含 wire_shapes 9 known fail)
make test-baseline  # 可绿基线 (排除 wire_shapes)
```

### Non-Custodial 4 红线专项 grep

```bash
# 见 .claude/rules/verification.md §Non-Custodial 4 红线专项检查
grep -rnE 'log\.(info|debug|warning).*api[_-]?key' src/ tests/
grep -rn 'CEXOMS\|BinanceClient\|OKXClient' src/ --exclude=nautilus_host.py
grep -rn 'stop_all_strategies\|force_shutdown' src/arx_runner/reconcile.py
grep -rnE 'float\(.*price|float\(.*amount' src/
```

## 关键设计约束

- **async 优先**: 主流程 asyncio, 阻塞调用 `asyncio.to_thread`
- **Pydantic v2 wire 契约**: `ConfigDict(extra="forbid")` 拒未声明字段
- **Decimal money math**: 所有价格/金额路径 (红线 0.4)
- **structlog 事件名**: 动词过去时 / 状态名词 (英文 snake_case)
- **UUIDv7 event ID**: 时序单调 (`uuid6.uuid7()`)

## 依赖参考

- 顶层技术栈: [`../../.claude/rules/tech-stack.md`](../../.claude/rules/tech-stack.md)
- 代码风格: [`../../.claude/rules/code-style.md`](../../.claude/rules/code-style.md)
- 常见错误: [`../../.claude/rules/common-errors.md`](../../.claude/rules/common-errors.md)
