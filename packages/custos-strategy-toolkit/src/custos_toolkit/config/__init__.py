"""
Configuration loading utilities.

Provides YAML configuration loading functions that work across platforms.
Supports the unified config format with embedded schema metadata.

Config is split into:
- base_config.yaml: General settings (trading, position, risk, filters, platforms)
- {strategy}/config.yaml: Strategy-specific settings (strategy, parameters, overrides)

Platform-specific configuration models are in:
- custos_toolkit.hummingbot.config (Pydantic models for Hummingbot)
- custos_toolkit_nautilus.adapter.config (msgspec.Struct for NautilusTrader)
"""

from .loader import (
    ConfigWrapper,
    deep_merge,
    extract_value,
    load_config,
    load_yaml_file,
    to_hummingbot_config,
)
from .validator import ValidationResult, abort_on_failure, log_provenance, validate_startup

__all__ = [
    "ConfigWrapper",
    "deep_merge",
    "extract_value",
    "load_config",
    "load_yaml_file",
    "to_hummingbot_config",
    "ValidationResult",
    "abort_on_failure",
    "log_provenance",
    "validate_startup",
]
