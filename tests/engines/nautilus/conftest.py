"""Shared isolation helpers for dynamically loaded Nautilus strategies."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

StrategyModuleCacheCleaner = Callable[[Path], tuple[str, ...]]


def _strategy_module_name(strategy_path: Path) -> str:
    """Mirror the product loader's deterministic module identity."""
    path_tag = hashlib.sha256(str(strategy_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"custos_strategy_{strategy_path.stem}_{path_tag}"


def _clear_strategy_module_cache(strategy_path: Path) -> tuple[str, ...]:
    """Remove one dynamic strategy module and only its namespaced children."""
    module_name = _strategy_module_name(strategy_path)
    child_prefix = f"{module_name}."
    removed = tuple(
        sorted(name for name in sys.modules if name == module_name or name.startswith(child_prefix))
    )
    for name in removed:
        sys.modules.pop(name, None)
    return removed


@pytest.fixture(scope="session")
def clear_strategy_module_cache() -> StrategyModuleCacheCleaner:
    """Provide the exact dynamic-module cleanup used by e2e teardowns."""
    return _clear_strategy_module_cache
