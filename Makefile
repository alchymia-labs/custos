# custos Makefile
#
# Standalone open-source repository entrypoint. Standardized validation targets
# keep shell execution deterministic and avoid permission drift from ad-hoc commands.

.PHONY: help install install-nt install-lts fmt fmt-check lint check test test-baseline test-nt test-docker test-docker-existing verify verify-base-clean verify-nt verify-runtime verify-runtime-existing verify-local-v030 clean toolkit-sync-check dist sign docker-build docker-build-local-v030 docker-sign verify-release release

# Default target: help
.DEFAULT_GOAL := help

help:  ## List all targets and descriptions
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install dependencies (dev extra) — uv sync --extra dev
	uv sync --extra dev

install-nt:  ## Install dependencies + NT runtime (requires Python 3.12+) — uv sync --extra dev --extra nautilus
	uv sync --extra dev --extra nautilus

install-lts:  ## Install release-engineering LTS toolchain (sigstore + pytest-docker)
	uv sync --extra dev --extra lts

fmt:  ## Format source files (ruff format writes changes)
	uv run ruff format src/ tests/ scripts/

fmt-check:  ## Check formatting (ruff format --check, no file changes)
	uv run ruff format --check src/ tests/ scripts/

lint:  ## Lint check (ruff check)
	uv run ruff check src/ tests/ scripts/

check: fmt-check lint  ## Combined formatting check and lint

test:  ## Run full pytest (base profile; NT tests importorskip; includes known-failing wire_shapes)
	uv run pytest tests/

test-baseline:  ## Run green baseline (base, ignore test_wire_shapes.py, see Plan 01 DEV-01-WIRE-FIXTURES)
	# test_wire_shapes.py depends on an arx fixture path. After subtree split, standalone clone no longer has this path.
	# Until standalone fixture generation is added (Plan 02+), this target provides the release baseline.
	# Base gate does not hard-require NT: if nautilus is missing, NT host tests are skipped by pytest.importorskip.
	uv run pytest tests/ --ignore=tests/test_wire_shapes.py

test-nt:  ## Run NT gate (requires py3.12+): run NT host tests under --extra nautilus
	# Preflight hard gate: if NT is still unavailable in nautilus (py<3.12 or install failure), NT host tests are silently skipped by pytest.importorskip and verify-nt could appear green.
	# Validate NT importability first; fail early if missing.
	@uv run --extra nautilus python -c "import nautilus_trader; assert nautilus_trader.__version__" \
		|| (echo "❌ nautilus_trader is not installed with nautilus extra (requires Python 3.12+); NT gate cannot run"; exit 1)
	uv run --extra nautilus pytest tests/ --ignore=tests/test_wire_shapes.py

verify: check test-baseline  ## Base release gate: check + green test-baseline
	@echo "✅ make verify passed"

verify-base-clean:  ## Clean dev-only sync followed by the base release gate
	uv sync --extra dev
	$(MAKE) verify

verify-nt: check test-nt  ## NT release gate (requires py3.12+): check + green test-nt
	@echo "✅ make verify-nt passed"

clean:  ## Remove pycache / pytest cache / ruff cache
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache

# --- Plan 12 release engineering ---------------------------------------------
# `make dist` produces the signed-artifact input; `docker-build` consumes it.
# `verify-release` is the post-publish smoke gate the CI job invokes after
# uploading to PyPI + GHCR.

LOCAL_IMAGE ?= custos-runner:v0.3.0
SOURCE_REVISION := $(shell git rev-parse HEAD)

dist:  ## Build a reproducible wheel + sdist to dist/ (respects SOURCE_DATE_EPOCH)
	uv build

sign:  ## Sign every wheel under dist/ with sigstore keyless (requires OIDC; runs in CI)
	bash .github/workflows/scripts/sign-wheel.sh

docker-build: dist  ## Build custos-runner:test image from the local dist/*.whl wheel
	docker build \
		--label org.opencontainers.image.revision=$(SOURCE_REVISION) \
		--tag custos-runner:test \
		.

docker-build-local-v030: dist  ## Build the local v0.3.0 consumer image with source provenance
	@dirty="$$(git status --porcelain --untracked-files=normal)"; \
		if [ -n "$$dirty" ]; then \
			echo "local consumer image requires a clean worktree:" >&2; \
			echo "$$dirty" >&2; \
			exit 1; \
		fi
	docker build \
		--label org.opencontainers.image.revision=$(SOURCE_REVISION) \
		--tag $(LOCAL_IMAGE) \
		.

docker-sign:  ## Sign the built docker image with cosign keyless (requires OIDC; runs in CI)
	@echo "docker-sign is exercised by the CI release workflow (needs GHCR + OIDC)." >&2
	@echo "Run cosign manually only for out-of-band re-signing." >&2

test-docker-existing:  ## Run runtime contracts against CUSTOS_TEST_IMAGE (default custos-runner:test)
	uv run pytest -m docker tests/test_docker_non_root.py tests/test_docker_entrypoint_help.py tests/test_docker_image_size.py tests/test_docker_runtime_contract.py -v

test-docker: docker-build test-docker-existing  ## Build local image, then run complete runtime contracts

verify-runtime-existing: test-docker-existing  ## Gate an existing image and standalone deployment wire
	uv run pytest tests/integration/test_standalone_runtime.py -v

verify-runtime: test-docker  ## Gate the complete image and standalone deployment wire
	uv run pytest tests/integration/test_standalone_runtime.py -v

verify-local-v030: docker-build-local-v030  ## Build and gate the local downstream image
	CUSTOS_TEST_IMAGE=$(LOCAL_IMAGE) \
		CUSTOS_EXPECTED_REVISION=$(SOURCE_REVISION) \
		$(MAKE) verify-runtime-existing
	docker image inspect $(LOCAL_IMAGE) \
		--format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'

verify-release:  ## Post-publish smoke: pull wheel + verify sig, pull image + verify sig + smoke run
	@bash .github/workflows/scripts/verify-release.sh $(VERSION)

release: dist sign docker-build docker-sign  ## Full local release rehearsal (real publish still lives in CI)
	@echo "Local release rehearsal complete. Publish to PyPI + GHCR runs in CI." >&2

toolkit-sync-check:  ## Diff vendored toolkit against upstream ps shared/ (+ optional pandas_ta) for drift
	@if [ -z "$$PS_ROOT" ]; then \
		echo "❌ PS_ROOT is required (path to a local philosophers-stone checkout)" >&2; \
		echo "   usage: PS_ROOT=/path/to/philosophers-stone make toolkit-sync-check" >&2; \
		exit 1; \
	fi; \
	PROVENANCE=src/custos/engines/nautilus/toolkit/TOOLKIT_PROVENANCE.md; \
	PS_PINNED=$${PINNED_PS_SHA:-$$(awk -F'`' '/\*\*Upstream commit\*\*/{print $$2; exit}' "$$PROVENANCE")}; \
	if [ -z "$$PS_PINNED" ]; then \
		echo "❌ ps upstream commit not recorded in $$PROVENANCE" >&2; \
		exit 1; \
	fi; \
	echo "- **Upstream commit**: \`$$PS_PINNED\`"; \
	PS_HEAD=$$(git -C "$$PS_ROOT" rev-parse HEAD); \
	echo "ps upstream HEAD: $$PS_HEAD"; \
	PS_COMMITS=$$(git -C "$$PS_ROOT" log --oneline "$$PS_PINNED..$$PS_HEAD" -- shared/ 2>/dev/null); \
	PS_DIFFSTAT=$$(git -C "$$PS_ROOT" diff --stat "$$PS_PINNED..$$PS_HEAD" -- shared/ 2>/dev/null); \
	if [ -z "$$PS_DIFFSTAT" ]; then \
		echo "ps drift: no"; \
	else \
		echo "ps drift: yes"; \
		echo "-- new commits under shared/ --"; \
		echo "$$PS_COMMITS"; \
		echo "-- diff-stat --"; \
		echo "$$PS_DIFFSTAT"; \
	fi; \
	if [ -n "$$PANDAS_TA_ROOT" ]; then \
		PT_PINNED=$$(awk -F'`' '/\*\*Upstream commit\*\*/{print $$2}' "$$PROVENANCE" | sed -n '2p'); \
		PT_HEAD=$$(git -C "$$PANDAS_TA_ROOT" rev-parse HEAD); \
		echo "- **Upstream commit**: \`$$PT_PINNED\`"; \
		echo "pandas_ta upstream HEAD: $$PT_HEAD"; \
		PT_DIFFSTAT=$$(git -C "$$PANDAS_TA_ROOT" diff --stat "$$PT_PINNED..$$PT_HEAD" 2>/dev/null); \
		if [ -z "$$PT_DIFFSTAT" ]; then \
			echo "pandas_ta drift: no"; \
		else \
			echo "pandas_ta drift: yes"; \
			echo "$$PT_DIFFSTAT"; \
		fi; \
	else \
		echo "pandas_ta drift: N/A (PANDAS_TA_ROOT unset — manual check required)"; \
	fi; \
	if [ -n "$$PS_DIFFSTAT" ]; then exit 1; else exit 0; fi

# ---- Future targets (pending plan rollout) ----
# typecheck:  ## pyright type checks (integrate in Plan 02+)
# 	uv run pyright src/ tests/
#
# docs:  ## Generate API docs when needed
# 	@echo "TODO"
