"""Vendored dependency resolve bootstrap.

The ps supertrend closure and its pandas_ta dependency were both vendored in
verbatim to keep custos a single-clone audit-able repo (non-custodial red line +
mandatory-rules §7). Neither is pip-installable in this tree — resolving them
means putting two paths on sys.path exactly once, before any strategy loader
tries to import them:

- ``shared/`` — ps snapshot; imported inside itself as ``shared.<pkg>`` and
  from ps strategy files as ``from shared.nautilus import ...``. So the
  parent of ``shared/`` (i.e. this directory) has to be on sys.path.
- ``vendor/pandas_ta/`` — third-party MIT-licensed indicator library; ps
  vendored code does ``import pandas_ta as ta`` at module top. So the parent
  of ``pandas_ta`` (i.e. ``vendor/``) has to be on sys.path.

Doing this at package import time (rather than a per-caller hack) makes the
resolution deterministic and lets the strategy loader stay ignorant of the
toolkit layout. Sorted, prepended, and idempotent — running it twice does not
duplicate entries.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLKIT_ROOT = Path(__file__).resolve().parent
_VENDOR_ROOT = _TOOLKIT_ROOT / "vendor"


def _prepend_if_missing(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


# ``shared/*`` is imported bare (``from shared.nautilus import ...``) so its
# parent — this directory — has to be on sys.path.
_prepend_if_missing(_TOOLKIT_ROOT)

# ``pandas_ta`` is imported bare (``import pandas_ta as ta``) so its parent —
# ``vendor/`` — has to be on sys.path.
_prepend_if_missing(_VENDOR_ROOT)


def _install_pandas_ta_distribution_shim() -> None:
    """Register the vendored pandas_ta as a fake pkg_resources Distribution.

    pandas_ta's own ``__init__.py`` calls ``pkg_resources.get_distribution(
    "pandas_ta")`` at import time to look up its version. That call assumes the
    package was pip-installed; a bare-copied vendored tree never registers a
    Distribution, so the call raises ``DistributionNotFound`` and the module
    fails to import. Patching the vendored code would violate the sync
    invariant (see TOOLKIT_PROVENANCE.md), so instead we teach
    ``pkg_resources`` about our vendored copy up front. The shim runs once and
    is safe to import twice — an existing entry short-circuits registration.
    """
    try:
        import pkg_resources
    except ImportError:  # pragma: no cover - guarded by nt-runtime extra
        return

    try:
        pkg_resources.get_distribution("pandas_ta")
        return  # A real installation is present; leave it alone.
    except pkg_resources.DistributionNotFound:
        pass

    dist = pkg_resources.Distribution(
        location=str(_VENDOR_ROOT),
        project_name="pandas_ta",
        version="0.0.0+vendored",
    )
    pkg_resources.working_set.add(dist)


_install_pandas_ta_distribution_shim()
