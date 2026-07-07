"""Structured logging configuration for the runner.

JSON output to stdout; English event names; snake_case keys. Used by every
silent path the runner has (telemetry drops, NATS disconnection no-ops,
WAL stash / drain failures) so the operator never has to guess whether
the runner "silently" dropped something — every drop emits an event.

The configuration is intentionally a one-shot: ``configure()`` is
idempotent and safe to call from ``__main__`` or test fixtures. Tests
can grab the configured logger and assert event names + keys without
asserting on the JSON format itself.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_CONFIGURED = False


def configure(level: int = logging.INFO) -> None:
    """Configure structlog for JSON output on stdout.

    Idempotent — calling twice is a no-op. Tests can rely on this being
    safe to call inside fixtures.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger; configures on first use so callers don't
    have to remember to call ``configure()`` first."""
    if not _CONFIGURED:
        configure()
    return structlog.get_logger(name, **initial_values)
