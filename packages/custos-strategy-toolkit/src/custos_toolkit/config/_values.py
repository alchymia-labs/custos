"""Typed views over dynamic configuration mappings."""

from collections.abc import Mapping
from typing import TypeVar, cast

T = TypeVar("T")


def config_value(values: Mapping[str, object], key: str, default: T) -> T:
    """Return a config value with the type established by its canonical default."""
    return cast(T, values.get(key, default))


def config_section(values: Mapping[str, object], key: str) -> dict[str, object]:
    """Return a nested config section without leaking an untyped mapping."""
    return cast(dict[str, object], values.get(key, {}))
