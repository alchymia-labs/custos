"""Structured logging configuration smoke tests.

Asserts ``configure()`` is idempotent and ``get_logger()`` returns a
working bound logger that can emit structured events without raising.
The JSON output format itself is not asserted here — tests that care
about specific event names assert via ``structlog.testing.capture_logs``.
"""

from __future__ import annotations

import structlog

from custos.core import log as runner_log


def test_configure_is_idempotent():
    runner_log.configure()
    runner_log.configure()  # second call must not raise


def test_get_logger_returns_bound_logger():
    logger = runner_log.get_logger("test")
    # Bind a key and emit; the wrapper should accept positional event + kwargs.
    with structlog.testing.capture_logs() as cap:
        logger.info("smoke_event", key="value")
    assert any(entry["event"] == "smoke_event" for entry in cap)


def test_event_keys_use_english_snake_case():
    logger = runner_log.get_logger("test")
    with structlog.testing.capture_logs() as cap:
        logger.warning(
            "telemetry_event_dropped_whitelist",
            event_type="UnknownEvent",
            reason="not_in_allowlist",
        )
    matched = [e for e in cap if e["event"] == "telemetry_event_dropped_whitelist"]
    assert len(matched) == 1
    assert matched[0]["event_type"] == "UnknownEvent"
    assert matched[0]["reason"] == "not_in_allowlist"
