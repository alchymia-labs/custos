# 04 — 测试策略

> custos 测试分层 + pytest 惯例 + fixture / mock 模式 + 失败模式测试.

## 测试基线 (as-of Plan 01 close-out)

- **总 test 数**: 124 collected
- **可绿基线**: 115 pass (`make test-baseline` / `make verify`)
- **Known fail**: 9 tests in `test_wire_shapes.py` (依赖 arx 仓库 fixture 路径,
  subtree split 后独立 clone 场景失效, 见 Plan 01 DEV-01-WIRE-FIXTURES)

## 测试分层

| 类型 | 命名 | 目的 | 数量 (~) |
|------|------|------|---------|
| 单元测试 | `test_<module>.py` | 单模块行为 (mock 依赖) | 6 files |
| 契约测试 | `test_<module>_contract.py` | Wire contract / API 契约 | 3 files |
| 失败模式测试 | `test_<module>_failure_modes.py` | silent drop / retry / breaker / timeout | 2 files |
| 集成测试 | `test_smoke.py` | 端到端 smoke (最小可跑) | 1 file |
| Wire shape | `test_wire_shapes.py` | 跨语言 wire fixture 校验 (跨仓库) | 1 file (know fail) |

## 每模块测试文件

| 模块 | 测试文件 | 覆盖点 |
|------|---------|-------|
| enrollment | `test_enrollment.py` | 一次性 token / paper_only 默认 |
| credential_vault | `test_credential_vault.py` + `test_credential_vault_sops.py` | 加密/解密 / sops CLI 集成 |
| nats_client | `test_nats_client_telemetry.py` + `test_nats_envelope.py` + `test_nats_wal_resilience.py` | telemetry uplink / envelope schema / WAL 断线暂存 |
| reconcile | `test_reconcile.py` + `test_deployment_reconciler.py` | ReconcileLoop level-triggered / spec 匹配 |
| nautilus_host | `test_g6_gate.py` + `test_heartbeat.py` + `test_nt_risk_engine.py` | G6 gate 逻辑 / 心跳 / 本地 breaker |
| telemetry_actor | `test_telemetry_actor.py` + `test_telemetry_actor_failure_modes.py` + `test_telemetry_money_contract.py` | 白名单 / 脱敏 / silent drop / Decimal wire (红线 0.4) |
| 跨模块 | `test_subject_builder_contract.py` + `test_log.py` + `test_smoke.py` | subject naming 契约 / structlog / 端到端 |

## pytest 惯例

### async 测试

`pyproject.toml` 已配 `asyncio_mode = "auto"`, 无需 `@pytest.mark.asyncio` 装饰:

```python
async def test_reconcile_loop_iterates(reconcile_env):
    result = await reconcile_env.loop.iterate()
    assert result.next_action == "start_nt"
```

### fixture 命名

`snake_case`, 前缀语义:

- `vault_with_test_key` — 已注入 test API key 的 vault fixture
- `nats_mock_connected` — 已连接的 mocked NATS client
- `deployment_spec_paper` / `deployment_spec_live` — 语义化 spec fixture
- `temp_vault_dir` — `mktemp -d` 临时 vault 目录 (lesson #29 不碰用户 `~/.custos/`)

### 参数化

`@pytest.mark.parametrize` 优于循环 assert (报告清晰):

```python
@pytest.mark.parametrize("trading_mode,expected_gate", [
    ("paper", "allow"),
    ("sandbox", "allow"),
    ("testnet", "allow"),
    ("live", "deny"),  # NoopHost 拒 live (G6 gate 红线 0.2)
])
def test_g6_gate(noop_host, trading_mode, expected_gate):
    assert noop_host.gate_check(trading_mode) == expected_gate
```

## 失败模式测试 (lesson #17 契约)

**happy-path 测试全绿 ≠ 失败模式覆盖**. 每个含 wire / async / persistence / concurrency
/ money math 的模块必须并行加失败模式 test:

- **NATS down**: WAL 暂存 → 重连 → drain (see `test_nats_wal_resilience.py`)
- **vault_locked**: age key 不匹配 / 权限错 / sops decrypt 失败
- **G6 gate deny**: NoopHost 拒 live / LIVE_MODE=false
- **queue overflow**: telemetry 事件积压超阈值 → drop policy (see `test_telemetry_actor_failure_modes.py`)
- **wire schema drift**: v1 消费者遇 v2 envelope (双 schema 兼容)
- **async task silent drop**: `create_task` 异常 → callback 检查 (lesson #21 零静默)
- **Decimal 精度丢失**: `float(price)` 混入 → contract test 拒 (red 线 0.4)

## Wire fixture 现状 (Plan 01 DEV-01-WIRE-FIXTURES)

`test_wire_shapes.py` 引用 `tesseract-trading/backend/crates/telemetry/tests/wire_shapes/*.json`
— 这是 arx 仓库路径, custos 独立 clone 场景失效.

**当前处理**:
- `make test` 会看到 9 fail (反映现实)
- `make test-baseline` 排除该文件 (可绿基线 115 pass)
- `make verify` = `check + test-baseline` (发布门)

**未来 plan** (Plan 02+):
- 独立 wire fixture 生成机制 (custos 自跑 `scripts/generate_wire_fixtures.py`)
- 或 cross-repo submodule / vendored fixture

## Money contract 测试 (红线 0.4)

`test_telemetry_money_contract.py` (18 test) 守 Decimal wire 契约:

- `Decimal(str)` 构造精度对齐
- `str(Decimal)` 序列化 wire (禁 `float(Decimal)`)
- Pydantic v2 `field_serializer` for Decimal → str
- 精度尾巴一致性 (`Decimal("100.00")` → `"100.00"`)

## Mock 惯例

- **NATS mock**: 用 `aiofiles` mock 或 mock `nats.aio.client.Client` 而非跑真 NATS
- **sops mock**: mock `subprocess.run` 拦 `sops --decrypt` 命令
- **NT mock**: 用 `NoopHost` (production 也是 v0.0.x 默认) 而非 mock NT lifecycle
- **交易所 API mock**: 用 `pytest-httpx` 或 `respx` 拦 HTTP (若未来加同步 HTTP)

## 覆盖率 (未来)

当前无自动覆盖率报告, 未来 plan 可加:

```bash
uv run pytest --cov=arx_runner --cov-report=term-missing tests/
```

## 参考

- 代码风格 (测试也遵守): [`../../.claude/rules/code-style.md`](../../.claude/rules/code-style.md) §测试风格
- 常见错误 (async silent drop / uv 混用): [`../../.claude/rules/common-errors.md`](../../.claude/rules/common-errors.md)
- 验证入口: [`../../.claude/rules/verification.md`](../../.claude/rules/verification.md)
