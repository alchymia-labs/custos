"""NATS JetStream client + transport envelope models.

Transport envelope (every NATS message):

    {
      "envelope_version": 1,
      "event_id": "<uuid>",
      "tenant_id": "<tenant>",
      "occurred_at": "<RFC3339 nanoseconds>",
      "payload_schema_version": 1,
      "payload": { ... },
      "ordering": { "session_id": "<uuid>", "seq": <int> }   # optional
    }

Heartbeat publishes to ``arx.{tenant}.heartbeat.{runner_id}`` with at-most-once
fire-and-forget semantics — we do not block on ack. Telemetry / spec / status
flows extend the same envelope with their own subjects and delivery semantics
(see the deployment plan index for the full table).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

try:  # pragma: no cover — exercised in production, mocked in unit tests
    import nats
    from nats.js import JetStreamContext
except ImportError as exc:  # pragma: no cover
    nats = None  # type: ignore[assignment]
    JetStreamContext = Any  # type: ignore[misc, assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@dataclass(frozen=True)
class OrderingMeta:
    """Telemetry-only ordering: session_id is the runner-restart boundary,
    seq is monotonic within a session. Sequences are not comparable across
    sessions (plan-index §6)."""

    session_id: str
    seq: int

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError(f"OrderingMeta.seq must be >= 0, got {self.seq}")


@dataclass
class NatsEnvelope:
    """Transport envelope wrapper. Use :func:`to_bytes` to serialise for
    publish; we never accept untrusted bytes on the runner side so there is
    no symmetric :func:`from_bytes` helper here."""

    event_id: str
    tenant_id: str
    occurred_at: str
    payload: dict
    envelope_version: int = 1
    payload_schema_version: int = 1
    ordering: OrderingMeta | None = None

    def to_dict(self) -> dict:
        body = {
            "envelope_version": self.envelope_version,
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "occurred_at": self.occurred_at,
            "payload_schema_version": self.payload_schema_version,
            "payload": self.payload,
        }
        if self.ordering is not None:
            body["ordering"] = asdict(self.ordering)
        return body

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8")


def _now_rfc3339_nanos() -> str:
    """RFC3339 with nanosecond precision (plan-index §6 occurred_at format).

    ``time.time_ns()`` gives us full nanosecond resolution; Python's
    ``datetime`` truncates to microseconds, so we format manually.
    """
    ns = time.time_ns()
    secs, ns_rem = divmod(ns, 1_000_000_000)
    tm = time.gmtime(secs)
    return f"{tm.tm_year:04d}-{tm.tm_mon:02d}-{tm.tm_mday:02d}T{tm.tm_hour:02d}:{tm.tm_min:02d}:{tm.tm_sec:02d}.{ns_rem:09d}Z"


def build_heartbeat_envelope(
    *,
    tenant_id: str,
    runner_id: str,
    session_id: str,
    seq: int,
    health: str,
) -> NatsEnvelope:
    """Construct a heartbeat envelope with ordering metadata attached."""
    return NatsEnvelope(
        event_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        occurred_at=_now_rfc3339_nanos(),
        payload={"runner_id": runner_id, "health": health},
        ordering=OrderingMeta(session_id=session_id, seq=seq),
    )


def heartbeat_subject(tenant_id: str, runner_id: str) -> str:
    """Canonical heartbeat subject (plan-index §6)."""
    return f"arx.{tenant_id}.heartbeat.{runner_id}"


@dataclass
class ArxNatsClient:
    """Minimal phone-home client. Owns the NATS connection + JetStream context,
    exposes one publish method per kind. Designed for extension — later
    telemetry actors will reuse the same connection without re-instantiating."""

    nats_url: str
    tenant_id: str
    runner_id: str
    _nc: Any = field(default=None, init=False, repr=False)
    _js: Any = field(default=None, init=False, repr=False)

    async def connect(self) -> None:
        if nats is None:  # pragma: no cover
            raise RuntimeError(f"nats-py is not installed: {_IMPORT_ERROR}")
        self._nc = await nats.connect(self.nats_url)
        self._js = self._nc.jetstream()

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None

    async def publish_heartbeat(self, *, health: str, seq: int, session_id: str) -> None:
        """Publish a heartbeat envelope. Fire-and-forget: we do not await ack."""
        if self._js is None:
            raise RuntimeError("ArxNatsClient.publish_heartbeat called before connect()")
        env = build_heartbeat_envelope(
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
            session_id=session_id,
            seq=seq,
            health=health,
        )
        subject = heartbeat_subject(self.tenant_id, self.runner_id)
        await self._js.publish(subject, env.to_bytes())
