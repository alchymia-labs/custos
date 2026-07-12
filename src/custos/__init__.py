"""Arx self-hosted execution host (Runner / ExecutionHost).

This maps architecture §1 trust-boundary policy:
- Key material and strategy logic stay local.
- Network egress is limited to telemetry and status reporting.
- control = declarative reconciliation to align local state with desired state.
"""

__version__ = "0.0.0"
