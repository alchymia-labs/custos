"""
Startup validation and runtime provenance for strategy runners.

Provides:
- validate_startup(): preflight check that collects ALL failures before returning
- abort_on_failure(): print failures to stderr and exit non-zero if validation failed
- log_provenance(): emit structured INFO log with runtime identity fields
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

logger = logging.getLogger(__name__)

VALID_PLATFORMS = {"nautilus", "hummingbot"}


class ValidationResult(NamedTuple):
    ok: bool
    failures: list[str]


def _check_strategy_dir(strategy_dir: Path) -> list[str]:
    """Check that the strategy directory exists and is a directory."""
    failures = []
    if not strategy_dir.exists():
        failures.append(f"[MISSING] Strategy directory not found: {strategy_dir}")
    elif not strategy_dir.is_dir():
        failures.append(f"[INVALID] Strategy path is not a directory: {strategy_dir}")
    return failures


def _check_config_yaml(config_path: Path) -> list[str]:
    """Check that config.yaml exists and contains valid non-empty YAML."""
    failures = []
    if not config_path.exists():
        failures.append(f"[MISSING] config.yaml not found at {config_path}")
        return failures  # Cannot parse what doesn't exist
    try:
        with open(config_path, encoding="utf-8") as f:
            result = yaml.safe_load(f.read())
        if result is None:
            failures.append(f"[INVALID] config.yaml is empty at {config_path}")
    except yaml.YAMLError as e:
        failures.append(f"[INVALID] config.yaml is not valid YAML at {config_path}: {e}")
    return failures


def validate_startup(
    strategy_name: str,
    platform: str,
    strategy_root: Path | None = None,
) -> ValidationResult:
    """
    Collect ALL startup failures before returning.

    Args:
        strategy_name: Strategy name (e.g., "supertrend")
        platform:      "nautilus" or "hummingbot"
        strategy_root: Base path to resolve the strategy directory against.
                       Defaults to platform-specific container root.

    Returns:
        ValidationResult with ok=True if all checks pass, or ok=False
        plus a non-empty list of failure messages.
    """
    failures: list[str] = []

    if platform not in VALID_PLATFORMS:
        failures.append(
            f"[INVALID] Unknown platform '{platform}'. Expected: {sorted(VALID_PLATFORMS)}"
        )
        return ValidationResult(ok=False, failures=failures)

    # Resolve strategy directory using platform-specific layout
    if strategy_root is None:
        if platform == "nautilus":
            strategy_root = Path("/app/scripts")
        else:
            strategy_root = Path("/home/hummingbot/scripts")

    strategy_dir = strategy_root / strategy_name
    config_path = strategy_dir / "config.yaml"

    dir_failures = _check_strategy_dir(strategy_dir)
    failures.extend(dir_failures)

    # Only check config.yaml if the directory exists (skip when dir is missing)
    if not dir_failures:
        failures.extend(_check_config_yaml(config_path))

    return ValidationResult(ok=len(failures) == 0, failures=failures)


def abort_on_failure(result: ValidationResult) -> None:
    """Print all failures to stderr and exit if validation failed."""
    if result.ok:
        return
    print("ERROR Startup validation failed:", file=sys.stderr)
    for msg in result.failures:
        print(f"  {msg}", file=sys.stderr)
    print("\nAborting. Fix the above before starting.", file=sys.stderr)
    sys.exit(1)


def log_provenance(
    strategy_name: str,
    platform: str,
    config_path: str,
    mode: str,
) -> None:
    """
    Emit a structured provenance INFO log entry.

    Fields: strategy, platform, config (relative path), version, mode.
    Git revision is intentionally excluded (D-09).

    Args:
        strategy_name: Strategy name (e.g., "supertrend")
        platform:      "nautilus" or "hummingbot"
        config_path:   Relative or absolute path to the config file used
        mode:          Trading mode (e.g., "sandbox", "live", "testnet")
    """
    version = _get_engine_version(platform)
    # Ensure logging is configured — fall back to basicConfig if no handlers
    if not logging.root.handlers:
        logging.basicConfig()
    logger.info(
        "[provenance] strategy=%s platform=%s config=%s version=%s mode=%s",
        strategy_name,
        platform,
        config_path,
        version,
        mode,
    )


def _get_engine_version(platform: str) -> str:
    """Get engine version string for the given platform."""
    if platform == "nautilus":
        try:
            import nautilus_trader  # noqa: PLC0415

            return nautilus_trader.__version__
        except ImportError:
            return "unknown"
    elif platform == "hummingbot":
        try:
            import hummingbot  # noqa: PLC0415

            return getattr(hummingbot, "__version__", "unknown")
        except ImportError:
            return "unknown"
    return "unknown"
