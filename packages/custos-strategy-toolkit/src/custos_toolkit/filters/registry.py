# shared/filters/registry.py
"""
Filter registry for dynamic filter creation.

Provides decorator-based registration and factory functions
for creating filters by name.
"""

from collections.abc import Callable

from .base import BaseFilter

# Global filter registry
_FILTER_REGISTRY: dict[str, type[BaseFilter]] = {}


def register_filter(name: str) -> Callable[[type[BaseFilter]], type[BaseFilter]]:
    """
    Decorator to register a filter class.

    Usage:
        @register_filter("time")
        class TimeFilter(BaseFilter):
            ...

    Args:
        name: Unique name for the filter

    Returns:
        Decorator function
    """

    def decorator(cls: type[BaseFilter]) -> type[BaseFilter]:
        if name in _FILTER_REGISTRY:
            raise ValueError(f"Filter '{name}' is already registered")
        _FILTER_REGISTRY[name] = cls
        return cls

    return decorator


def create_filter(name: str, config: dict) -> BaseFilter:
    """
    Create filter instance by name.

    Args:
        name: Registered filter name
        config: Filter configuration dictionary

    Returns:
        Filter instance

    Raises:
        ValueError: If filter name is not registered
    """
    if name not in _FILTER_REGISTRY:
        available = ", ".join(_FILTER_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown filter: '{name}'. Available: {available}")
    return _FILTER_REGISTRY[name](config)


def list_filters() -> list[str]:
    """
    List all registered filter names.

    Returns:
        List of filter names
    """
    return list(_FILTER_REGISTRY.keys())


def is_filter_registered(name: str) -> bool:
    """
    Check if a filter is registered.

    Args:
        name: Filter name to check

    Returns:
        True if registered
    """
    return name in _FILTER_REGISTRY


def clear_registry() -> None:
    """
    Clear all registered filters.

    Primarily for testing purposes.
    """
    _FILTER_REGISTRY.clear()
