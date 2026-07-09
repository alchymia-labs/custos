# 验证命令 (custos)

标准化验证入口清单. 优先使用 Makefile 目标 (稳定 + 免权限碎片污染 settings.local.json),
裸命令仅在 Makefile 目标缺失时手写.

## 快速入口

| 目标 | 用途 | 底层命令 |
|------|------|---------|
| `make help` | 列出所有 target | `awk` 提取 doc |
| `make install` | 装依赖 (dev extra) | `uv sync --extra dev` |
| `make fmt` | 格式化 (改文件) | `uv run ruff format` |
| `make fmt-check` | 格式检查 (不改) | `uv run ruff format --check` |
| `make lint` | Lint 检查 | `uv run ruff check` |
| `make check` | fmt-check + lint | 组合 target |
| `make test` | 跑测试 | `uv run pytest` |
| `make verify` | check + test (发布级) | 组合 target |

## 详细验证策略

### 提交前 (pre-commit)

```bash
make fmt        # 让 ruff format 修改文件
make lint       # 若有 auto-fix 建议, 手动查看后决定
git status --short   # 核对 staged 范围, 拒绝 pre-staged 污染 (lesson #27)
```

### CI / PR 前 (pre-review)

```bash
make verify     # fmt-check + lint + pytest 全绿
```

单独跑 test:

```bash
uv run pytest tests/ -v
uv run pytest tests/test_g6_gate.py -v      # G6 gate 单独
uv run pytest -k "reconcile" -v             # 关键词过滤
```

### Non-Custodial 4 红线专项检查

红线不是自动化门, 但可通过以下 grep 定位漏点 (见 `mandatory-rules.md` §0):

```bash
# 红线 0.1 Key/KEK 出进程 (禁 log/publish/send raw key material)
grep -rnE 'log\.(info|debug|warning).*api[_-]?key' src/ tests/
grep -rnE 'publish.*password|send.*secret' src/

# 红线 0.2 G6 gate 绕过 (禁在 nautilus_host.py 外自建 venue client)
grep -rn 'CEXOMS\|BinanceClient\|OKXClient' src/ --exclude=nautilus_host.py

# 红线 0.3 失联即停止 (禁云端断线时暴力 stop_all)
grep -rn 'stop_all_strategies\|force_shutdown' src/custos/core/reconcile.py

# 红线 0.4 float 用于 money math (禁)
grep -rnE 'float\(.*price|float\(.*amount|float\(.*notional' src/
```

### wire contract 一致性

若改 envelope schema (`docs/design/nats_client.md` §schema versioning):

```bash
uv run python scripts/generate_wire_fixtures.py  # 重新生成参考 fixture
uv run pytest tests/test_wire_shapes.py tests/test_nats_envelope.py -v
```

## 常见失败诊断

| 失败症状 | 可能原因 | 处理 |
|---------|---------|-----|
| `ModuleNotFoundError: nats` | 未跑 `uv sync --extra dev` | `make install` |
| `pytest 报 asyncio_mode` | `pyproject.toml` 未配 `asyncio_mode=auto` | 已配, 若跑不通看 pytest 版本 |
| `ruff check` 大量 UP 报错 | Python 3.11 语法未升级 | `make fmt` + 手动修 |
| G6 gate test fail | `NtTradingNodeHost` 实现缺失 | Plan 00a 之后才应通过 |
| telemetry money contract fail | float 混入 Decimal | 修 `src/custos/core/telemetry_actor.py` |

## 未来验证 target (待落地)

- `make typecheck`: `uv run pyright src/ tests/` (Plan 待定)
- `make docs`: 生成 API 文档 (若需)
- `make wire-check`: 独立跑 wire contract fixture diff (若 wire 迭代频繁)
