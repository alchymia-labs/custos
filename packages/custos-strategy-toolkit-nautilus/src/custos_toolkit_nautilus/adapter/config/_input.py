"""Typed accessors for schema-validated strategy configuration mappings.

The YAML schema validator establishes the value types before the adapter
builders run. These helpers keep the unavoidable trust assertion at that
boundary instead of leaking ``Any`` through every public builder contract.
They are casts only and therefore preserve the existing runtime behavior.
"""

from __future__ import annotations

from typing import TypeVar, cast, overload

T = TypeVar("T")


def section(data: dict[str, object], key: str) -> dict[str, object]:
    """Return a nested schema-validated mapping without changing its value."""
    return cast(dict[str, object], data.get(key, {}))


@overload
def value(data: dict[str, object], key: str, default: T) -> T: ...


@overload
def value(data: dict[str, object], key: str) -> object | None: ...


def value(data: dict[str, object], key: str, default: object = None) -> object:
    """Read a schema-validated scalar using the fallback's static type."""
    return data.get(key, default)
