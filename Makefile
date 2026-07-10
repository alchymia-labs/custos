# custos Makefile
#
# 独立开源仓库自足构建入口. 标准化验证入口, 避免裸 shell 触发权限碎片污染
# .claude/settings.local.json (workspace lesson: 优先 Makefile target 而非裸 uv run).

.PHONY: help install install-nt fmt fmt-check lint check test test-baseline test-nt verify verify-nt clean toolkit-sync-check

# 默认 target: help
.DEFAULT_GOAL := help

help:  ## 列出所有 target 及说明
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## 装依赖 (dev extra) — uv sync --extra dev
	uv sync --extra dev

install-nt:  ## 装依赖 + NT runtime (需 py3.12+) — uv sync --extra dev --extra nautilus
	uv sync --extra dev --extra nautilus

fmt:  ## 格式化代码 (ruff format 改文件)
	uv run ruff format src/ tests/ scripts/

fmt-check:  ## 格式检查 (ruff format --check 不改文件)
	uv run ruff format --check src/ tests/ scripts/

lint:  ## Lint 检查 (ruff check)
	uv run ruff check src/ tests/ scripts/

check: fmt-check lint  ## fmt-check + lint 组合

test:  ## 跑完整 pytest (base, NT 测试自 importorskip; 含已知 fail 的 wire_shapes)
	uv run pytest tests/

test-baseline:  ## 跑可绿测试基线 (base, 排除 test_wire_shapes.py, 见 Plan 01 DEV-01-WIRE-FIXTURES)
	# test_wire_shapes.py 依赖 arx 仓库 fixture 路径, subtree split 后独立 clone 场景失效.
	# 独立 fixture 生成机制未落地前 (Plan 02+), 用本 target 做发布门可绿基线.
	# base 门不强依赖 NT: nautilus 未装时 NT host 测试 pytest.importorskip 自跳过.
	uv run pytest tests/ --ignore=tests/test_wire_shapes.py

test-nt:  ## 跑 NT gate (需 py3.12+): --extra nautilus 下真跑 NT host 测试
	# Preflight hard gate: 若 nautilus 下 NT 仍未装 (py<3.12 / 装失败), NT host 测试会被
	# pytest.importorskip 静默 skip, 使 verify-nt 假绿。此处先硬校验 NT 可导入, 缺失即 fail。
	@uv run --extra nautilus python -c "import nautilus_trader; assert nautilus_trader.__version__" \
		|| (echo "❌ nautilus_trader 未在 nautilus extra 下安装 (需 Python 3.12+); NT gate 无法真跑"; exit 1)
	uv run --extra nautilus pytest tests/ --ignore=tests/test_wire_shapes.py

verify: check test-baseline  ## 发布门 (base): check + test-baseline 全绿
	@echo "✅ make verify passed"

verify-nt: check test-nt  ## 发布门 (NT, 需 py3.12+): check + test-nt 全绿
	@echo "✅ make verify-nt passed"

clean:  ## 清理 pycache / pytest cache / ruff cache
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache

toolkit-sync-check:  ## Print vendored toolkit upstream commits + hint how to diff against upstreams
	@awk '/^- \*\*Upstream commit\*\*:/ {print; found=1} END {if (!found) {print "❌ upstream commit not recorded in TOOLKIT_PROVENANCE.md"; exit 1}}' \
		src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md
	@echo "Hint: to diff vendored subsets against upstream HEAD:"
	@echo "  ps: cd /path/to/philosophers-stone && git log --oneline -5 shared/"
	@echo "  pandas_ta: git clone --depth 1 https://github.com/wukai9203/Technical-Analysis-Indicators---Pandas.git /tmp/pt_check && git -C /tmp/pt_check log --oneline -1"
	@echo "  # Then compare current shas against pinned upstreams in TOOLKIT_PROVENANCE.md"
	@echo "(concrete diff mechanism lands with Plan 07 broader shared curation.)"

# ---- 未来 target (待未来 plan 落地) ----
# typecheck:  ## pyright 类型检查 (待 Plan 02+ 集成)
# 	uv run pyright src/ tests/
#
# docs:  ## 生成 API 文档 (待需要时)
# 	@echo "TODO"
