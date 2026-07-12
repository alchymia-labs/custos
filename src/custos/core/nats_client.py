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
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import uuid6

from custos.core.log import get_logger

_log = get_logger("custos.nats_client")

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
    uptime_secs: int,
    active_deployments: int,
) -> NatsEnvelope:
    """Construct a heartbeat envelope with ordering metadata attached.

    Payload shape pinned by plan-index §6 and the Rust ``HeartbeatPayload``
    struct in ``domain::execution::telemetry_envelope`` — all four fields
    (runner_id / uptime_secs / active_deployments / health) are required.
    """
    return NatsEnvelope(
        event_id=str(uuid6.uuid7()),
        tenant_id=tenant_id,
        occurred_at=_now_rfc3339_nanos(),
        payload={
            "runner_id": runner_id,
            "uptime_secs": uptime_secs,
            "active_deployments": active_deployments,
            "health": health,
        },
        ordering=OrderingMeta(session_id=session_id, seq=seq),
    )


def heartbeat_subject(tenant_id: str, runner_id: str) -> str:
    """Canonical heartbeat subject (plan-index §6). Routes through
    :func:`build_subject` so empty tenant/runner ids raise instead of
    silently producing ``arx..heartbeat.`` (F4/IN-NATS-1)."""
    return build_subject(tenant_id, "heartbeat", runner_id)


def build_subject(tenant: str, kind: str, *path_parts: str) -> str:
    """Plan-index §6 subject builder. Used by the telemetry actor + adapter
    to keep subject naming in one place. Raises on empty path parts so a
    typo can't silently route to ``arx.{tenant}.telemetry..`` (NATS
    forbids empty tokens)."""
    if not tenant or not kind:
        raise ValueError("tenant and kind are required")
    parts = [tenant, kind, *path_parts]
    if any(not p for p in parts):
        raise ValueError("subject path parts must be non-empty")
    return "arx." + ".".join(parts)


class _OfflineWal:
    """Local SQLite store of messages that couldn't be published because
    NATS was disconnected. FIFO drained on reconnect — at-least-once
    semantics for telemetry require we don't lose buffered events on a
    transient outage. Heartbeats are not WAL-buffered (at-most-once,
    plan-index §6 delivery).

    Size and age caps prevent the WAL from growing unbounded during long
    outages — when ``max_rows`` is exceeded the oldest rows are trimmed
    and the trim is reported through a structured event so the operator
    can decide whether to extend capacity.
    """

    _DEFAULT_MAX_ROWS: int = 100_000
    _DEFAULT_MAX_AGE_SECS: int = 7 * 86400

    def __init__(
        self,
        db_path: Path,
        max_rows: int = _DEFAULT_MAX_ROWS,
        max_age_secs: int = _DEFAULT_MAX_AGE_SECS,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be >= 1")
        if max_age_secs < 1:
            raise ValueError("max_age_secs must be >= 1")
        self.db_path = db_path
        self.max_rows = max_rows
        self.max_age_secs = max_age_secs
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_telemetry ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "subject TEXT NOT NULL, "
            "payload BLOB NOT NULL, "
            "queued_at TEXT NOT NULL, "
            "queued_at_ns INTEGER NOT NULL DEFAULT 0)"
        )
        self._conn.commit()

    def stash(self, subject: str, payload: bytes) -> None:
        now_ns = time.time_ns()
        self._conn.execute(
            "INSERT INTO pending_telemetry "
            "(subject, payload, queued_at, queued_at_ns) VALUES (?, ?, ?, ?)",
            (subject, payload, _now_rfc3339_nanos(), now_ns),
        )
        self._conn.commit()
        _log.info(
            "wal_stash",
            subject=subject,
            payload_bytes=len(payload),
            depth=self.depth(),
        )
        self._trim(now_ns)

    def drain(self) -> list[tuple[int, str, bytes]]:
        cur = self._conn.execute(
            "SELECT id, subject, payload FROM pending_telemetry ORDER BY id ASC"
        )
        return [(int(row[0]), str(row[1]), bytes(row[2])) for row in cur.fetchall()]

    def forget(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"DELETE FROM pending_telemetry WHERE id IN ({placeholders})",
            ids,
        )
        self._conn.commit()

    def depth(self) -> int:
        """Current number of buffered rows. Hook for ops metrics."""
        cur = self._conn.execute("SELECT COUNT(*) FROM pending_telemetry")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def _trim(self, now_ns: int) -> None:
        """Enforce ``max_rows`` (drop oldest) and ``max_age_secs`` (drop
        anything older than the cutoff). Reports the count dropped via a
        structured event so silent loss never escapes notice."""
        cutoff_ns = now_ns - self.max_age_secs * 1_000_000_000
        aged_cur = self._conn.execute(
            "DELETE FROM pending_telemetry WHERE queued_at_ns < ? AND queued_at_ns > 0",
            (cutoff_ns,),
        )
        aged = aged_cur.rowcount or 0
        if aged > 0:
            self._conn.commit()
            _log.warning(
                "wal_trim_aged",
                dropped=aged,
                cutoff_ns=cutoff_ns,
                max_age_secs=self.max_age_secs,
            )

        depth = self.depth()
        if depth > self.max_rows:
            overflow = depth - self.max_rows
            # Trim from the head (oldest id) — keep the most recent ``max_rows``
            # to preserve fresh telemetry at the expense of the oldest.
            self._conn.execute(
                "DELETE FROM pending_telemetry WHERE id IN ("
                "SELECT id FROM pending_telemetry ORDER BY id ASC LIMIT ?)",
                (overflow,),
            )
            self._conn.commit()
            _log.warning(
                "wal_trim_overflow",
                dropped=overflow,
                max_rows=self.max_rows,
            )

    def close(self) -> None:
        self._conn.close()


@dataclass
class ArxNatsClient:
    """Minimal phone-home client. Owns the NATS connection + JetStream context,
    exposes one publish method per kind. Designed for extension — later
    telemetry actors reuse the same connection without re-instantiating.

    `wal_path` enables an offline write-ahead log for at-least-once
    telemetry: if `publish_telemetry_envelope` finds the JetStream context
    is missing (disconnected), the message is stashed and the local queue
    is drained on the next successful connect()."""

    nats_url: str
    tenant_id: str
    runner_id: str
    wal_path: Path | None = None
    wal_max_rows: int = _OfflineWal._DEFAULT_MAX_ROWS
    wal_max_age_secs: int = _OfflineWal._DEFAULT_MAX_AGE_SECS
    _nc: Any = field(default=None, init=False, repr=False)
    _js: Any = field(default=None, init=False, repr=False)
    _wal: _OfflineWal | None = field(default=None, init=False, repr=False)
    _wal_drain_task: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.wal_path is not None:
            self._wal = _OfflineWal(
                self.wal_path,
                max_rows=self.wal_max_rows,
                max_age_secs=self.wal_max_age_secs,
            )

    async def connect(self) -> None:
        if nats is None:  # pragma: no cover
            raise RuntimeError(f"nats-py is not installed: {_IMPORT_ERROR}")
        self._nc = await nats.connect(self.nats_url)
        self._js = self._nc.jetstream()
        # Replay anything stashed while we were disconnected. FIFO order
        # preserves the producer-side seq monotonicity the consumer
        # watermark relies on. We don't block connect() on the full drain
        # — a large WAL backlog would defer healthy publish indefinitely;
        # the background task forgets each row immediately on success so
        # progress is visible even if drain doesn't reach the tail.
        import asyncio

        # Hold a strong reference so the loop can't GC the drain task mid-flight —
        # dropped WAL replay silently losing buffered telemetry violates the
        # reconciliation-visibility red line.
        self._wal_drain_task = asyncio.create_task(self._drain_wal(), name="arx-wal-drain")

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None
        if self._wal is not None:
            self._wal.close()
            self._wal = None

    async def publish_heartbeat(
        self,
        *,
        health: str,
        seq: int,
        session_id: str,
        uptime_secs: int,
        active_deployments: int,
    ) -> None:
        """Publish a heartbeat envelope via core NATS (at-most-once,
        plan-index §6 delivery). Heartbeats are not JetStream-acked —
        the next interval will arrive on schedule and that's enough.

        ``uptime_secs`` / ``active_deployments`` are required by the
        Rust ``HeartbeatPayload`` consumer struct (plan-index §6).
        """
        env = build_heartbeat_envelope(
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
            session_id=session_id,
            seq=seq,
            health=health,
            uptime_secs=uptime_secs,
            active_deployments=active_deployments,
        )
        subject = heartbeat_subject(self.tenant_id, self.runner_id)
        await self.publish_fire_and_forget(subject, env.to_bytes())

    async def publish_fire_and_forget(self, subject: str, payload: bytes) -> None:
        """At-most-once publish via core NATS (not JetStream — no ack wait).
        Used for heartbeat and other liveness signals where redelivery
        would be louder than the loss. Drops silently when disconnected
        (the next heartbeat will arrive on schedule and that's enough) but
        the drop is reported through a structured event so the runner is
        never silent about lost liveness signals."""
        if self._nc is None:
            _log.warning(
                "nats_fire_and_forget_noop_disconnected",
                subject=subject,
                payload_bytes=len(payload),
            )
            return
        await self._nc.publish(subject, payload)

    async def publish_telemetry_envelope(self, subject: str, envelope: NatsEnvelope) -> None:
        """At-least-once publish via JetStream. When disconnected, stash
        in the offline WAL for replay on next connect()."""
        payload = envelope.to_bytes()
        if self._js is None:
            if self._wal is None:
                raise RuntimeError(
                    "publish_telemetry_envelope called without a connection and no WAL configured"
                )
            self._wal.stash(subject, payload)
            return
        await self._js.publish(subject, payload)

    async def subscribe_deployment_spec(
        self,
        *,
        strategy_id: str,
    ) -> Any:
        """Subscribe to ``arx.{tenant}.deployment_spec.{strategy_id}``.

        Returns the underlying nats subscription so the caller can iterate
        ``async for msg in sub.messages``. Spec stream is level-triggered by
        generation — each message is a full DeploymentSpec snapshot, not a
        delta (plan-index §6: "no ordering, level-triggered by generation").
        """
        if self._js is None:
            raise RuntimeError("subscribe_deployment_spec called before connect()")
        subject = build_subject(self.tenant_id, "deployment_spec", strategy_id)
        return await self._js.subscribe(subject)

    async def publish_deployment_status(
        self,
        *,
        spec_id: str,
        payload: dict,
    ) -> None:
        """At-least-once publish DeploymentStatus to
        ``arx.{tenant}.deployment_status.{runner_id}.{spec_id}``.

        Runner-reported observed state. Body wrapped in NatsEnvelope (no
        ordering metadata — level-triggered, plan-index §6)."""
        if self._js is None:
            _log.warning(
                "deployment_status_skipped_disconnected",
                spec_id=spec_id,
                runner_id=self.runner_id,
            )
            return
        env = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload,
        )
        subject = build_subject(
            self.tenant_id,
            "deployment_status",
            self.runner_id,
            spec_id,
        )
        await self._js.publish(subject, env.to_bytes())

    async def publish_enrollment(self, *, payload: dict) -> None:
        """At-least-once publish enrollment request to
        ``arx.{tenant}.enrollment.{runner_id}`` (plan-index §6)."""
        if self._js is None:
            raise RuntimeError("publish_enrollment called before connect()")
        env = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload,
        )
        subject = build_subject(self.tenant_id, "enrollment", self.runner_id)
        await self._js.publish(subject, env.to_bytes())

    async def _drain_wal(self) -> None:
        """Replay buffered messages one row at a time, forgetting each on
        successful publish. If any publish raises, log + break so the
        remaining rows stay buffered for the next reconnect — at-least-once
        semantics demand we don't drop unsent telemetry on a transient
        broker error."""
        if self._wal is None or self._js is None:
            return
        pending = self._wal.drain()
        if not pending:
            return
        _log.info("wal_drain_start", pending=len(pending))
        sent = 0
        for pid, subject, payload in pending:
            try:
                await self._js.publish(subject, payload)
            except Exception as exc:  # noqa: BLE001 — survive broker hiccups
                _log.error(
                    "wal_drain_failed",
                    subject=subject,
                    sent_before_failure=sent,
                    error=str(exc),
                )
                break
            self._wal.forget([pid])
            sent += 1
        _log.info("wal_drain_finish", sent=sent, remaining=self._wal.depth())
