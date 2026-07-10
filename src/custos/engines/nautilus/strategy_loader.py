"""Strategy source loading + code_hash verification.

The runner must run exactly the strategy code that was reviewed and pinned in
the DeploymentSpec. Before importing a strategy module we hash its source
directory and compare against the spec's ``code_hash``; a mismatch is refused
(non-custodial red line: NT 启动必先校验 code_hash). Sandbox specs may omit the
hash (``expected_code_hash=None``) — the check is skipped but the skip is
audited so it is never silent.

No NautilusTrader dependency here — this is pure hashing + importlib so it can
be unit-tested without the nautilus extra.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path

from custos.core.log import get_logger

_log = get_logger("custos.strategy_loader")

# Directory entries that are build artifacts, not source — excluded from the
# code hash so a stale .pyc can't change (or stabilise) the pinned identity.
_HASH_EXCLUDE_DIRS = {"__pycache__"}
_HASH_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


class CodeHashMismatch(Exception):
    """On-disk strategy source does not match the spec's pinned code_hash."""


def compute_strategy_dir_hash(strategy_dir: Path) -> str:
    """Deterministic sha256 over the strategy source directory.

    Files are hashed in sorted relative-path order; each contributes its path
    and byte content, so both a content edit and a rename change the digest.
    Build artifacts (__pycache__, *.pyc) are excluded.
    """
    digest = hashlib.sha256()
    for file_path in sorted(strategy_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if any(part in _HASH_EXCLUDE_DIRS for part in file_path.relative_to(strategy_dir).parts):
            continue
        if file_path.suffix in _HASH_EXCLUDE_SUFFIXES:
            continue
        rel = file_path.relative_to(strategy_dir).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_strategy_class(
    strategy_path: Path,
    expected_code_hash: str | None,
    expected_registry_name: str | None = None,
) -> type:
    """Verify code_hash then dynamically import the strategy class.

    ``expected_code_hash=None`` (sandbox) skips verification but audits the
    skip. A mismatch raises ``CodeHashMismatch`` before any code is imported —
    untrusted source is never executed.

    ``expected_registry_name`` (optional) turns on a second-line check: after
    the strategy module is imported and its ``register_strategy`` decorators
    have run, ask the ps toolkit registry which class is bound to the name
    and require the answer to equal the class the loader picked. The
    heuristic (single ``*Strategy`` class per module) is deliberately lenient
    so tests can ship stubs; the registry check is the deliberate guardrail
    for production specs where the operator knows the strategy's registered
    identity and can pin it.

    Any ``ModuleNotFoundError`` during the strategy import — including the
    ps ``shared.*`` dependency graph reaching outside the vendored toolkit's
    supported closure — surfaces as a structured
    ``strategy_toolkit_import_failed`` event before it propagates, so it
    isn't a silent degradation.
    """
    strategy_path = Path(strategy_path)
    if not strategy_path.exists():
        raise FileNotFoundError(f"strategy source not found: {strategy_path}")

    if expected_code_hash is None:
        _log.info("code_hash_skipped_sandbox", strategy_path=str(strategy_path))
    else:
        actual = compute_strategy_dir_hash(strategy_path.parent)
        if actual != expected_code_hash:
            _log.error(
                "code_hash_mismatch",
                strategy_path=str(strategy_path),
                expected_prefix=expected_code_hash[:12],
                actual_prefix=actual[:12],
            )
            raise CodeHashMismatch(
                f"strategy {strategy_path} code_hash mismatch "
                f"(expected {expected_code_hash[:12]}…, got {actual[:12]}…)"
            )

    try:
        module = _import_module_from_path(strategy_path)
    except ModuleNotFoundError as exc:
        _log.error(
            "strategy_toolkit_import_failed",
            strategy_path=str(strategy_path),
            missing_module=exc.name,
        )
        raise

    strategy_cls = _find_strategy_class(module, strategy_path)

    if expected_registry_name is not None:
        _verify_registry_binding(expected_registry_name, strategy_cls, strategy_path)

    return strategy_cls


def _verify_registry_binding(name: str, strategy_cls: type, strategy_path: Path) -> None:
    """Assert the ps toolkit registry binds ``name`` to ``strategy_cls``.

    Called as a deliberate second look after the loader's heuristic picks a
    class: the registry is the ground truth for "which class does the
    operator mean by this name," and disagreeing with it is worth refusing
    rather than shipping a wrong-class load. The registry itself lives in the
    vendored toolkit (``toolkit/shared/nautilus/registry.py``); importing it
    lazily keeps the loader usable when the toolkit isn't required (unit
    tests with a stub strategy).
    """
    # Bootstrap the vendored toolkit's sys.path shim first; without this the
    # bare ``shared.nautilus`` import on the following line has nowhere to
    # resolve to. Ordering here is load-bearing.
    import custos.engines.nautilus.toolkit  # noqa: F401, I001 — sys.path bootstrap must precede shared.*
    from shared.nautilus import registry as ps_registry

    if not ps_registry.is_registered(name):
        available = ps_registry.list_strategies()
        _log.error(
            "strategy_registry_name_unknown",
            strategy_path=str(strategy_path),
            requested_name=name,
            available=available,
        )
        raise ValueError(
            f"strategy_registry_name={name!r} is not registered in the ps toolkit; "
            f"available: {available}"
        )

    info = ps_registry.get_strategy_info(name)
    registered_cls = info["strategy_class"]
    if registered_cls is not strategy_cls:
        _log.error(
            "strategy_registry_name_class_mismatch",
            strategy_path=str(strategy_path),
            requested_name=name,
            registered_class=registered_cls.__name__,
            loaded_class=strategy_cls.__name__,
        )
        raise ValueError(
            f"strategy_registry_name={name!r} maps to {registered_cls.__name__!r}, "
            f"which does not match the loaded strategy class {strategy_cls.__name__!r}"
        )


def _import_module_from_path(strategy_path: Path):
    # Unique per absolute path so two strategy dirs sharing a name don't collide
    # in sys.modules, and so the class's __module__ resolves back to this module.
    path_tag = hashlib.sha256(str(strategy_path.resolve()).encode("utf-8")).hexdigest()[:8]
    module_name = f"custos_strategy_{strategy_path.stem}_{path_tag}"
    # Reuse a previously loaded copy — re-executing the same path drops us into
    # module-level side effects (ps ``register_strategy`` decorators, indicator
    # class definitions) that either raise on the second run or hand out a new
    # class object the toolkit registry no longer knows about. code_hash is
    # checked in load_strategy_class before we reach here, so a hit on
    # sys.modules is safe: the on-disk source can't have drifted from the last
    # time we imported it without the hash check catching it.
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build import spec for {strategy_path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the class's __module__ is retrievable via sys.modules
    # (inspect.getmodule returns None for these dynamically-loaded modules).
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # If module execution failed we mustn't leave the empty shell behind —
        # a later attempt would return the empty cached module and silently
        # succeed instead of surfacing the real load error.
        sys.modules.pop(module_name, None)
        raise
    return module


def _find_strategy_class(module, strategy_path: Path) -> type:
    """Locate the strategy class: explicit STRATEGY_CLASS wins, else the single
    module-defined class whose name ends with 'Strategy'."""
    explicit = getattr(module, "STRATEGY_CLASS", None)
    if inspect.isclass(explicit):
        return explicit

    defined = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__
    ]
    candidates = [cls for cls in defined if cls.__name__.endswith("Strategy")]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            f"no strategy class found in {strategy_path} "
            "(define one class ending in 'Strategy' or set STRATEGY_CLASS)"
        )
    raise ValueError(
        f"ambiguous strategy class in {strategy_path}: {[c.__name__ for c in candidates]} "
        "— set STRATEGY_CLASS to disambiguate"
    )
