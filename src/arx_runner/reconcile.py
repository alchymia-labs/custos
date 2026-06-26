"""NT reconciliation result uploader.

Runner-side counterpart to the backend ReconciliationService: take one
comparison NT produces (balance / position / order / fill), wrap it in
the standard NATS envelope, and publish it through the telemetry channel
for the backend to consume.

Why telemetry rather than a dedicated subject? v1 single-strategy
single-runner keeps the wire surface narrow; reconciliation rides the
telemetry stream and the backend demultiplexes by payload kind. If
volume grows the subject can split out in a later plan.

The NT integration (Reconciler / AccountState API) is stubbed in
``run_reconciliation_cycle`` — it returns an empty list rather than fake
data, so downstream tests cannot silently rely on a hard-coded fixture.
"""

from __future__ import annotations

import logging

import uuid6
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from .nats_client import ArxNatsClient, NatsEnvelope, OrderingMeta

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconResult:
    """One reconciliation comparison outcome.

    Field names mirror the backend ``reconciliation::service::ReconResult``
    so the JSON shape can flow without translation. ``Decimal`` here is
    the Python wire form; the backend deserialises into
    ``rust_decimal::Decimal``.
    """

    dimension: Literal["balance", "position", "order", "fill"]
    domain: Literal["cex", "mev"]
    source_amount: Decimal
    source_currency: str
    source_as_of: datetime
    target_amount: Decimal
    target_currency: str
    target_as_of: datetime
    tolerance: Decimal
    in_flight_count: int
    deployment_spec_id: str
    scope: str

    def to_payload(self) -> dict:
        return {
            "dimension": self.dimension,
            "domain": self.domain,
            "source_amount": str(self.source_amount),
            "source_currency": self.source_currency,
            "source_as_of": _rfc3339(self.source_as_of),
            "target_amount": str(self.target_amount),
            "target_currency": self.target_currency,
            "target_as_of": _rfc3339(self.target_as_of),
            "tolerance": str(self.tolerance),
            "in_flight_count": self.in_flight_count,
            "deployment_spec_id": self.deployment_spec_id,
            "scope": self.scope,
        }


def _rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    micros = dt.microsecond
    return f"{base}.{micros:06d}000Z"


def _now_rfc3339() -> str:
    return _rfc3339(datetime.now(tz=timezone.utc))


class ReconcileUploader:
    """Publish reconciliation results onto the telemetry channel.

    One uploader per (tenant, runner_id, session_id). ``seq`` is monotonic
    inside the session — callers advance it so the backend can drop
    stale telemetry deterministically.
    """

    def __init__(
        self,
        nats_client: ArxNatsClient,
        tenant_id: str,
        runner_id: str,
        session_id: str,
    ) -> None:
        self._nats = nats_client
        self._tenant_id = tenant_id
        self._runner_id = runner_id
        self._session_id = session_id

    def build_envelope(self, payload: dict, seq: int) -> NatsEnvelope:
        """Public for testing — wraps a payload into the envelope shape
        the backend ``recon_result`` consumer expects.

        The payload no longer carries a ``kind`` discriminator: the
        dedicated ``recon_result`` subject (plan-index §6) already routes
        the message, so the body is the payload directly.
        """
        return NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self._tenant_id,
            occurred_at=_now_rfc3339(),
            payload=payload,
            ordering=OrderingMeta(session_id=self._session_id, seq=seq),
        )

    def subject(self) -> str:
        """Dedicated ``recon_result`` subject (plan-index §6 — WR-NATS-2
        demux). Keeps reconciliation results off the telemetry stream so
        the consumer dispatch table stays explicit."""
        return (
            f"arx.{self._tenant_id}.recon_result."
            f"{self._runner_id}.{self._session_id}"
        )

    async def upload_recon_result(self, result: ReconResult, seq: int) -> None:
        """Serialise + publish one comparison."""
        env = self.build_envelope(result.to_payload(), seq)
        if self._nats._js is None:  # noqa: SLF001 — Plan 04 will expose publish_telemetry
            raise RuntimeError(
                "ArxNatsClient.upload_recon_result called before connect()"
            )
        await self._nats._js.publish(self.subject(), env.to_bytes())  # noqa: SLF001

    async def run_reconciliation_cycle(self) -> list[ReconResult]:
        """Stub for NT reconciliation API integration.

        Returns ``[]`` deliberately — a stub that lies is worse than a
        stub that does nothing. Real implementation will pull from NT's
        Reconciler / AccountState surfaces and is owned by the NT-host
        integration phase."""
        log.info(
            "recon_cycle_stub",
            extra={
                "tenant_id": self._tenant_id,
                "runner_id": self._runner_id,
                "note": "NT reconciliation API integration pending",
            },
        )
        return []
