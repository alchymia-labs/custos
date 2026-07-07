# 代码风格 (custos)

---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
  - "scripts/**/*.py"
---

Python 单栈项目, ruff 承担格式化 + lint 双职. custos 特化风格约束以 non-custodial
承重墙为出发点 (脱敏日志 / 英文字段 / async 优先 / Decimal money math).

## 格式化 (ruff format)

- `line-length = 88`
- `indent-width = 4`
- 字符串默认双引号 (ruff 默认)
- 保留 trailing comma (function call / list literal / dict literal 多行)

## Lint (ruff check)

启用规则集:

- `E` — pycodestyle 错误
- `W` — pycodestyle 警告
- `F` — pyflakes (未使用 import / 变量)
- `I` — isort (import 排序)
- `B` — flake8-bugbear (常见 bug)
- `UP` — pyupgrade (Python 3.11 语法)

## 命名约定

- 模块: `snake_case` (对应 6 module: `enrollment.py` / `reconcile.py` / etc)
- 类: `PascalCase` (`DeploymentSpec` / `EnrollmentToken` / `CredentialVault`)
- 函数 / 变量: `snake_case`
- 常量: `UPPER_SNAKE`
- Pydantic 模型: `PascalCase`, 字段 `snake_case` (wire 协议保持 snake_case)

## 日志规范 (custos 特化)

- **统一用 structlog**, 禁用裸 `print()` 和 `logging.getLogger()`
  ```python
  import structlog
  log = structlog.get_logger()
  log.info("enrollment_completed", runner_id=runner_id, paper_only=True)
  ```
- **字段名**: 全英文 snake_case (非中文, 便于 arx / 生态其他系统消费)
- **事件名**: 动词过去时 / 状态名词, 如 `enrollment_completed` / `g6_gate_denied` /
  `reconcile_loop_iteration` / `nats_disconnected`
- **禁字段**: `api_key`, `secret`, `password`, `token` (原文), `age_key`, `kek`,
  `venue_credentials` (原文) — 红线 0.1
- 若必须记录 key 相关事件, 用哈希 / prefix: `log.info("key_loaded", key_hash=sha256_first8(key))`

## async 规范

- 主流程走 asyncio (nats-py / structlog 均 async 友好)
- 阻塞调用 (文件 I/O / subprocess) 用 `asyncio.to_thread`
- **禁**: `requests.get()` / `time.sleep()` (asyncio loop 里阻塞)
- 允许: `asyncio.sleep()` / `aiofiles` (若加依赖) / async subprocess

## Money math 规范 (红线 0.4)

- 所有价格 / 数量 / notional 用 `decimal.Decimal`
- 从字符串 / API 响应构造: `Decimal(str(raw_value))` (禁 `Decimal(float_value)`)
- 序列化 wire: `str(decimal_value)` (禁 `float(decimal_value)`)
- Pydantic 字段: `Decimal` type + `json_encoders={Decimal: str}` 或用 v2 的
  `field_serializer`
- 参考: `test_telemetry_money_contract.py`

## Pydantic 惯例

- Pydantic v2 (`>=2.5`)
- Envelope / DeploymentSpec / DeploymentStatus 用 `pydantic.BaseModel`
- 字段类型注解显式 (禁裸 `dict` / `list`)
- 用 `ConfigDict(extra="forbid")` 拒绝未声明字段 (wire 契约防御)

## 测试风格

- pytest fixture: `snake_case`, 前缀语义 (`vault_with_test_key` / `nats_mock_connected`)
- 参数化: `@pytest.mark.parametrize` 优于循环 assert
- async 测试: 依赖 `asyncio_mode=auto` (pyproject.toml 已配), 无需 `@pytest.mark.asyncio`
- 失败模式测试单独文件: `test_<module>_failure_modes.py`
- Money contract test: `test_*_money_contract.py`
- Wire contract test: `test_wire_*.py` (跨语言 fixture)

## 禁止的模式

- **裸 `except:`** (至少 `except Exception:` + 显式 log 或 re-raise)
- **`except: pass`** silent drop (违反生态 lesson #21 "对账不静默")
- **循环里同步 sleep** (阻塞 asyncio loop)
- **magic number in trading path** (用命名常量 + 注释来源)
- **module 级 side effect** (禁模块 import 时读 vault / 连 NATS)

## 注释规范

- 默认不写注释, 命名清楚即可
- 需写注释的场景:
  - 红线约束 (`# non-custodial 红线 0.1: 禁 log raw key`)
  - 非直觉 workaround (`# NT lifecycle 需 stop 后 wait_for=STOPPED 才能重启`)
  - Wire contract 版本约束 (`# schema v2 起加此字段; v1 消费者需 dual-read`)
- **禁**: 编号追踪引用 (Plan 00a / task N / lesson #M 出现在源码注释, 生态 lesson #15)
