# custos Makefile
#
# 独立开源仓库自足构建入口. 标准化验证入口, 避免裸 shell 触发权限碎片污染
# .claude/settings.local.json (workspace lesson: 优先 Makefile target 而非裸 uv run).

.PHONY: help install fmt fmt-check lint check test test-baseline verify clean

# 默认 target: help
.DEFAULT_GOAL := help

help:  ## 列出所有 target 及说明
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## 装依赖 (dev extra) — uv sync --extra dev
	uv sync --extra dev

fmt:  ## 格式化代码 (ruff format 改文件)
	uv run ruff format src/ tests/ scripts/

fmt-check:  ## 格式检查 (ruff format --check 不改文件)
	uv run ruff format --check src/ tests/ scripts/

lint:  ## Lint 检查 (ruff check)
	uv run ruff check src/ tests/ scripts/

check: fmt-check lint  ## fmt-check + lint 组合

test:  ## 跑完整 pytest (含已知 fail 的 wire_shapes, 反映现实基线)
	uv run pytest tests/

test-baseline:  ## 跑可绿测试基线 (排除 test_wire_shapes.py, 见 Plan 01 DEV-01-WIRE-FIXTURES)
	# test_wire_shapes.py 依赖 arx 仓库 fixture 路径, subtree split 后独立 clone 场景失效.
	# 独立 fixture 生成机制未落地前 (Plan 02+), 用本 target 做发布门可绿基线.
	uv run pytest tests/ --ignore=tests/test_wire_shapes.py

verify: check test-baseline  ## 发布门: check + test-baseline 全绿
	@echo "✅ make verify passed"

clean:  ## 清理 pycache / pytest cache / ruff cache
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache

# ---- 未来 target (待未来 plan 落地) ----
# typecheck:  ## pyright 类型检查 (待 Plan 02+ 集成)
# 	uv run pyright src/ tests/
#
# install-nt:  ## 装 NT runtime extra (待 Plan 00a 加 nt-runtime optional-dep)
# 	uv sync --extra dev --extra nt-runtime
#
# docs:  ## 生成 API 文档 (待需要时)
# 	@echo "TODO"
