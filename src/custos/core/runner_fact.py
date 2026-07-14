"""Durable, signed RunnerFact production and JetStream delivery.

This module is the only Custos boundary allowed to construct RunnerFact batches.
Engine adapters provide raw facts; this module owns stream sequencing, canonical
digests, signatures, durable retry, and the exact NATS subject.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final
from uuid import UUID, uuid4, uuid5

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.core.log import get_logger

RUNNER_FACT_SCHEMA_VERSION: Final = 1
RUNNER_FACT_SIGNING_DOMAIN: Final = b"CRUCIBLE-RUNNER-FACT-BATCH-V1\0"
REGISTRATION_SIGNING_DOMAIN: Final = "arx.runner_verification_key.register.v1"
ONBOARDING_SIGNING_DOMAIN: Final = "crucible.runner_capability.onboard.v1"
RUNNER_FACT_EVENT_NAMESPACE: Final = UUID("834c6f30-4d2c-5f91-a2c4-5e8358fe6be4")
SUPPORTED_CURRENCIES: Final = frozenset({"USD", "USDT", "USDC", "BTC", "ETH"})
MAX_FACTS_PER_BATCH: Final = 512
MAX_BATCH_BYTES: Final = 768 * 1024
MAX_VENUE_LEDGER_CHUNKS: Final = 4096
MAX_VENUE_LEDGER_ITEMS_PER_CHUNK: Final = 512
MAX_VENUE_LEDGER_CHUNK_BYTES: Final = 262_144
_NATS_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")
_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_log = get_logger("custos.runner_fact")


class RunnerFactError(RuntimeError):
    """Base error for RunnerFact production."""


class RunnerFactContractError(RunnerFactError):
    """A fact or authority value violates the wire contract."""


class RunnerFactIdentityError(RunnerFactError):
    """The local signing identity is absent, unsafe, or corrupt."""


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunnerFactContractError(f"value is not canonical JSON: {exc}") from exc


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc_now() -> str:
    return _render_utc(datetime.now(UTC))


def _render_utc(value: datetime) -> str:
    """Render like chrono's RFC3339 AutoSi serializer used by Crucible."""
    value = value.astimezone(UTC)
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    micros = value.microsecond
    if micros == 0:
        return f"{base}Z"
    if micros % 1000 == 0:
        return f"{base}.{micros // 1000:03d}Z"
    return f"{base}.{micros:06d}Z"


def _uuid(value: UUID | str, field: str) -> str:
    try:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RunnerFactContractError(f"{field} must be a UUID") from exc
    if parsed.int == 0:
        raise RunnerFactContractError(f"{field} must not be nil")
    return str(parsed)


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunnerFactContractError(f"{field} must be a non-empty string")
    return value.strip()


def _decimal(value: Decimal | str | int, field: str, *, positive: bool = False) -> str:
    if isinstance(value, float):
        raise RunnerFactContractError(f"{field} must not be a binary float")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RunnerFactContractError(f"{field} must be a decimal") from exc
    if not parsed.is_finite():
        raise RunnerFactContractError(f"{field} must be finite")
    if positive and parsed <= 0:
        raise RunnerFactContractError(f"{field} must be greater than zero")
    if not positive and parsed < 0:
        raise RunnerFactContractError(f"{field} must not be negative")
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _signed_decimal(value: Decimal | str | int, field: str) -> str:
    if isinstance(value, float):
        raise RunnerFactContractError(f"{field} must not be a binary float")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RunnerFactContractError(f"{field} must be a decimal") from exc
    if not parsed.is_finite():
        raise RunnerFactContractError(f"{field} must be finite")
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _timestamp(value: datetime | str, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise RunnerFactContractError(f"{field} must include a timezone")
        return _render_utc(value)
    text = _non_empty(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunnerFactContractError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise RunnerFactContractError(f"{field} must include a timezone")
    return _render_utc(parsed)


def _currency(value: str) -> str:
    """Return the exact v1 Currency wire; object compatibility is forbidden."""
    currency = _non_empty(value, "currency")
    if currency != currency.upper() or currency not in SUPPORTED_CURRENCIES:
        raise RunnerFactContractError("currency must be one of USD, USDT, USDC, BTC, or ETH")
    return currency


def _side(value: str) -> str:
    normalized = value.lower().strip()
    if normalized not in {"buy", "sell"}:
        raise RunnerFactContractError("side must be buy or sell")
    return normalized


@dataclass(frozen=True, slots=True)
class RunnerFactAuthority:
    tenant_id: str
    trading_mode: str
    runner_id: UUID
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: str
    strategy_id: UUID
    capability_version_id: UUID
    capability_version: int
    capability_manifest_digest: str

    def __post_init__(self) -> None:
        _non_empty(self.tenant_id, "tenant_id")
        if not _NATS_TOKEN.fullmatch(self.tenant_id):
            raise RunnerFactContractError("tenant_id must be one safe NATS subject token")
        if self.trading_mode not in {"live", "sandbox", "testnet"}:
            raise RunnerFactContractError("trading_mode must be live, sandbox, or testnet")
        _uuid(self.runner_id, "runner_id")
        _uuid(self.deployment_instance_id, "deployment_instance_id")
        _uuid(self.deployment_spec_id, "deployment_spec_id")
        _uuid(self.strategy_id, "strategy_id")
        _uuid(self.capability_version_id, "capability_version_id")
        if self.capability_version < 1:
            raise RunnerFactContractError("capability_version must be positive")
        if not _LOWER_HEX_64.fullmatch(self.capability_manifest_digest):
            raise RunnerFactContractError(
                "capability_manifest_digest must be 64 lowercase hexadecimal characters"
            )
        if not _LOWER_HEX_64.fullmatch(self.deployment_spec_digest):
            raise RunnerFactContractError(
                "deployment_spec_digest must be 64 lowercase hexadecimal characters"
            )

    @property
    def stream_key(self) -> str:
        return (
            f"{self.tenant_id}:{self.trading_mode}:{self.runner_id}:"
            f"{self.deployment_instance_id}:{self.deployment_spec_id}:"
            f"{self.deployment_spec_digest}"
        )

    @property
    def subject(self) -> str:
        return (
            f"crucible.runner_fact.{self.trading_mode}."
            f"{self.tenant_id}.{self.runner_id}.{self.deployment_instance_id}."
            f"{self.deployment_spec_id}.{self.deployment_spec_digest}"
        )


@dataclass(frozen=True, slots=True)
class RunnerFactRegistrationRequest:
    idempotency_key: UUID
    body: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RunnerCapabilityOnboardingRequest:
    idempotency_key: UUID
    capability_version_id: UUID
    manifest_digest: str
    body: Mapping[str, Any]


class RunnerFactIdentity:
    """An Ed25519 signer loaded only from the encrypted machine vault."""

    def __init__(self, private_key: Ed25519PrivateKey, key_id: str) -> None:
        self._private_key = private_key
        self.key_id = _non_empty(key_id, "key_id")

    @classmethod
    def from_private_bytes(cls, private_bytes: bytes, key_id: str) -> RunnerFactIdentity:
        if len(private_bytes) != 32:
            raise RunnerFactIdentityError("Ed25519 private key must contain 32 bytes")
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        public_digest = _sha256_hex(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        expected_key_id = f"ed25519-{public_digest[:32]}"
        if key_id != expected_key_id:
            raise RunnerFactIdentityError("machine key id does not match Ed25519 private key")
        return cls(private_key, key_id)

    @property
    def public_key_bytes(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign_batch_payload(self, canonical_payload: bytes) -> str:
        signature = self._private_key.sign(RUNNER_FACT_SIGNING_DOMAIN + canonical_payload)
        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def registration_request(
        self,
        *,
        tenant_id: str,
        runner_id: UUID,
        capability_version_id: UUID,
        capability_version: int,
        manifest_digest: str,
        idempotency_key: UUID | None = None,
    ) -> RunnerFactRegistrationRequest:
        tenant = _non_empty(tenant_id, "tenant_id")
        runner = _uuid(runner_id, "runner_id")
        capability_id = _uuid(capability_version_id, "capability_version_id")
        if capability_version < 1:
            raise RunnerFactContractError("capability_version must be positive")
        if not _LOWER_HEX_64.fullmatch(manifest_digest):
            raise RunnerFactContractError("manifest_digest must be lowercase SHA-256")
        idempotency = idempotency_key or uuid4()
        public_key_digest = _sha256_hex(self.public_key_bytes)
        proof = "\n".join(
            (
                REGISTRATION_SIGNING_DOMAIN,
                f"tenant_id={tenant}",
                f"runner_id={runner}",
                f"capability_version_id={capability_id}",
                f"capability_version={capability_version}",
                f"manifest_digest={manifest_digest}",
                f"key_id={self.key_id}",
                "algorithm=ed25519",
                f"public_key_sha256={public_key_digest}",
                f"idempotency_key={idempotency}",
            )
        )
        return RunnerFactRegistrationRequest(
            idempotency_key=idempotency,
            body={
                "capability_version_id": capability_id,
                "capability_version": capability_version,
                "manifest_digest": manifest_digest,
                "key_id": self.key_id,
                "public_key_base64": base64.b64encode(self.public_key_bytes).decode("ascii"),
                "proof_signature_base64": base64.b64encode(
                    self._private_key.sign(proof.encode("utf-8"))
                ).decode("ascii"),
            },
        )

    def onboarding_request(
        self,
        *,
        tenant_id: str,
        runner_id: UUID,
        capability_manifest: Mapping[str, Any],
        capability_version_id: UUID | None = None,
        idempotency_key: UUID | None = None,
    ) -> RunnerCapabilityOnboardingRequest:
        """Create the exact ADR-018 capability-v1 plus key-v1 PoP request."""
        tenant = _non_empty(tenant_id, "tenant_id")
        runner = _uuid(runner_id, "runner_id")
        capability_id_value = capability_version_id or uuid4()
        capability_id = _uuid(capability_id_value, "capability_version_id")
        idempotency = idempotency_key or uuid4()
        if idempotency.int == 0:
            raise RunnerFactContractError("idempotency_key must not be nil")
        manifest = dict(capability_manifest)
        manifest_digest = _sha256_hex(_canonical_json_bytes(manifest))
        public_key_digest = _sha256_hex(self.public_key_bytes)
        proof = "\n".join(
            (
                ONBOARDING_SIGNING_DOMAIN,
                f"tenant_id={tenant}",
                f"runner_id={runner}",
                f"capability_version_id={capability_id}",
                "capability_version=1",
                f"manifest_digest={manifest_digest}",
                f"key_id={self.key_id}",
                "algorithm=ed25519",
                f"public_key_sha256={public_key_digest}",
                f"idempotency_key={idempotency}",
            )
        )
        body = {
            "capability_version_id": capability_id,
            "capability_version": 1,
            "capability_manifest": manifest,
            "manifest_digest": manifest_digest,
            "key_id": self.key_id,
            "public_key_base64": base64.b64encode(self.public_key_bytes).decode("ascii"),
            "proof_signature_base64": base64.b64encode(
                self._private_key.sign(proof.encode("utf-8"))
            ).decode("ascii"),
        }
        return RunnerCapabilityOnboardingRequest(
            idempotency_key=idempotency,
            capability_version_id=capability_id_value,
            manifest_digest=manifest_digest,
            body=body,
        )


def execution_fill(
    *,
    venue: str,
    venue_trade_id: str,
    venue_order_id: str,
    instrument: str,
    side: str,
    quantity: Decimal | str | int,
    price: Decimal | str | int,
    fee: Decimal | str | int,
    currency: str,
    occurred_at: datetime | str,
    client_order_id: str | None = None,
    event_id: UUID | str,
) -> dict[str, Any]:
    return {
        "kind": "execution_fill",
        "event_id": _uuid(event_id, "event_id"),
        "venue": _non_empty(venue, "venue"),
        "venue_trade_id": _non_empty(venue_trade_id, "venue_trade_id"),
        "client_order_id": (
            _non_empty(client_order_id, "client_order_id") if client_order_id else None
        ),
        "venue_order_id": _non_empty(venue_order_id, "venue_order_id"),
        "instrument": _non_empty(instrument, "instrument"),
        "side": _side(side),
        "quantity": _decimal(quantity, "quantity", positive=True),
        "price": _decimal(price, "price"),
        "fee": _decimal(fee, "fee"),
        "currency": _currency(currency),
        "occurred_at": _timestamp(occurred_at, "occurred_at"),
    }


def runner_fact_event_id(*parts: object) -> UUID:
    rendered = [str(part).strip() for part in parts]
    if not rendered or any(not part for part in rendered):
        raise RunnerFactContractError("deterministic event identity parts must be non-empty")
    return uuid5(RUNNER_FACT_EVENT_NAMESPACE, "\0".join(rendered))


def settlement_fill(
    *,
    event_id: UUID | str,
    fill_id: UUID | str,
    order_type: str,
    category: str,
    price: Decimal | str | int,
    avg_fill_price: Decimal | str | int,
    currency: str,
    filled_at: datetime | str,
) -> dict[str, Any]:
    return {
        "kind": "fill",
        "event_id": _uuid(event_id, "event_id"),
        "fill_id": _uuid(fill_id, "fill_id"),
        "order_type": _non_empty(order_type, "order_type"),
        "category": _non_empty(category, "category"),
        "price": _decimal(price, "price"),
        "avg_fill_price": _decimal(avg_fill_price, "avg_fill_price"),
        "currency": _currency(currency),
        "filled_at": _timestamp(filled_at, "filled_at"),
    }


def position_closed(
    *,
    event_id: UUID | str,
    position_id: UUID | str,
    realized_pnl: Decimal | str | int,
    currency: str,
    opened_at: datetime | str,
    closed_at: datetime | str,
) -> dict[str, Any]:
    opened = _timestamp(opened_at, "opened_at")
    closed = _timestamp(closed_at, "closed_at")
    if datetime.fromisoformat(closed.replace("Z", "+00:00")) < datetime.fromisoformat(
        opened.replace("Z", "+00:00")
    ):
        raise RunnerFactContractError("closed_at must not precede opened_at")
    return {
        "kind": "position_closed",
        "event_id": _uuid(event_id, "event_id"),
        "position_id": _uuid(position_id, "position_id"),
        "realized_pnl": _signed_decimal(realized_pnl, "realized_pnl"),
        "currency": _currency(currency),
        "opened_at": opened,
        "closed_at": closed,
    }


def settlement_fee(
    *,
    event_id: UUID | str,
    fill_id: UUID | str,
    amount: Decimal | str | int,
    currency: str,
    assessed_at: datetime | str,
) -> dict[str, Any]:
    return {
        "kind": "fee",
        "event_id": _uuid(event_id, "event_id"),
        "fill_id": _uuid(fill_id, "fill_id"),
        "amount": _decimal(amount, "amount"),
        "currency": _currency(currency),
        "assessed_at": _timestamp(assessed_at, "assessed_at"),
    }


def equity_snapshot(
    *,
    event_id: UUID | str,
    amount: Decimal | str | int,
    currency: str,
    observed_at: datetime | str,
) -> dict[str, Any]:
    return {
        "kind": "equity_snapshot",
        "event_id": _uuid(event_id, "event_id"),
        "amount": _signed_decimal(amount, "amount"),
        "currency": _currency(currency),
        "observed_at": _timestamp(observed_at, "observed_at"),
    }


def position_snapshot(
    *,
    event_id: UUID | str,
    positions: Sequence[Mapping[str, Any]],
    observed_at: datetime | str,
) -> dict[str, Any]:
    normalized = [
        {
            "instrument": _non_empty(row.get("instrument"), "positions.instrument"),
            "quantity": _signed_decimal(row.get("quantity"), "positions.quantity"),
            "mark_price": _decimal(row.get("mark_price"), "positions.mark_price"),
            "currency": _currency(row.get("currency")),
        }
        for row in positions
    ]
    normalized.sort(key=lambda row: str(row["instrument"]))
    _require_unique(normalized, "instrument", "positions")
    return {
        "kind": "position_snapshot",
        "event_id": _uuid(event_id, "event_id"),
        "positions": normalized,
        "observed_at": _timestamp(observed_at, "observed_at"),
    }


def heartbeat(
    *,
    event_id: UUID | str,
    status: str,
    observed_at: datetime | str,
) -> dict[str, Any]:
    normalized = _non_empty(status, "status").lower()
    if normalized not in {"online", "degraded", "offline"}:
        raise RunnerFactContractError("heartbeat status must be online, degraded, or offline")
    return {
        "kind": "heartbeat",
        "event_id": _uuid(event_id, "event_id"),
        "status": normalized,
        "observed_at": _timestamp(observed_at, "observed_at"),
    }


def settlement_period_closed(
    *,
    event_id: UUID | str,
    period: str,
    closed_at: datetime | str,
) -> dict[str, Any]:
    return {
        "kind": "period_closed",
        "event_id": _uuid(event_id, "event_id"),
        "period": _non_empty(period, "period"),
        "closed_at": _timestamp(closed_at, "closed_at"),
    }


def venue_ledger_snapshot_facts(
    *,
    snapshot_id: UUID | str,
    venue: str,
    source: str,
    watermark: str,
    coverage_from: datetime | str,
    observed_through: datetime | str,
    completeness: Mapping[str, Any],
    balances: Sequence[Mapping[str, Any]],
    positions: Sequence[Mapping[str, Any]],
    fills: Sequence[Mapping[str, Any]],
    fees: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    snapshot = _uuid(snapshot_id, "snapshot_id")
    venue_value = _non_empty(venue, "venue")
    source_value = _non_empty(source, "source")
    if source_value not in {"venue_api", "drop_copy"}:
        raise RunnerFactContractError("venue ledger source must be venue_api or drop_copy")
    watermark_value = _non_empty(watermark, "watermark")
    coverage = _timestamp(coverage_from, "coverage_from")
    observed = _timestamp(observed_through, "observed_through")
    if datetime.fromisoformat(coverage.replace("Z", "+00:00")) > datetime.fromisoformat(
        observed.replace("Z", "+00:00")
    ):
        raise RunnerFactContractError("coverage_from must not follow observed_through")
    normalized_balances = [
        {
            "asset": _non_empty(row.get("asset"), "balances.asset"),
            "currency": _currency(row.get("currency")),
            "total": _decimal(row.get("total"), "balances.total"),
            "available": _decimal(row.get("available"), "balances.available"),
        }
        for row in balances
    ]
    normalized_positions = [
        {
            "venue_position_id": _non_empty(
                row.get("venue_position_id"), "positions.venue_position_id"
            ),
            "instrument": _non_empty(row.get("instrument"), "positions.instrument"),
            "side": _side(row.get("side", "")),
            "quantity": _decimal(row.get("quantity"), "positions.quantity"),
            "avg_entry_price": (
                _decimal(row["avg_entry_price"], "positions.avg_entry_price")
                if row.get("avg_entry_price") is not None
                else None
            ),
            "currency": _currency(row.get("currency")),
        }
        for row in positions
    ]
    normalized_fills = [
        {
            "venue_trade_id": _non_empty(row.get("venue_trade_id"), "fills.venue_trade_id"),
            "venue_order_id": _non_empty(row.get("venue_order_id"), "fills.venue_order_id"),
            "instrument": _non_empty(row.get("instrument"), "fills.instrument"),
            "side": _side(row.get("side", "")),
            "quantity": _decimal(row.get("quantity"), "fills.quantity", positive=True),
            "price": _decimal(row.get("price"), "fills.price"),
            "fee": _decimal(row.get("fee"), "fills.fee"),
            "currency": _currency(row.get("currency")),
            "occurred_at": _timestamp(row.get("occurred_at"), "fills.occurred_at"),
        }
        for row in fills
    ]
    normalized_fees = [
        {
            "fee_id": _non_empty(row.get("fee_id"), "fees.fee_id"),
            "kind": _non_empty(row.get("kind"), "fees.kind"),
            "currency": _currency(row.get("currency")),
            "amount": _decimal(row.get("amount"), "fees.amount"),
            "occurred_at": _timestamp(row.get("occurred_at"), "fees.occurred_at"),
        }
        for row in fees
    ]
    normalized_balances.sort(key=lambda row: (str(row["asset"]), str(row["currency"])))
    normalized_positions.sort(
        key=lambda row: (str(row["instrument"]), str(row["side"]), str(row["venue_position_id"]))
    )
    normalized_fills.sort(
        key=lambda row: (
            str(row["occurred_at"]),
            str(row["instrument"]),
            str(row["venue_trade_id"]),
            str(row["venue_order_id"]),
        )
    )
    normalized_fees.sort(
        key=lambda row: (str(row["occurred_at"]), str(row["kind"]), str(row["fee_id"]))
    )
    balance_keys = [(str(row["asset"]), str(row["currency"])) for row in normalized_balances]
    if len(balance_keys) != len(set(balance_keys)):
        raise RunnerFactContractError("balances contains duplicate asset/currency")
    _require_unique(normalized_positions, "venue_position_id", "positions")
    fill_keys = [(str(row["instrument"]), str(row["venue_trade_id"])) for row in normalized_fills]
    if len(fill_keys) != len(set(fill_keys)):
        raise RunnerFactContractError("fills contains duplicate instrument/venue_trade_id")
    _require_unique(normalized_fees, "fee_id", "fees")
    completeness_value = {
        field: _required_bool(completeness.get(field), f"completeness.{field}")
        for field in (
            "balances_complete",
            "positions_complete",
            "fills_complete",
            "fees_complete",
        )
    }
    ordered_items: list[tuple[str, dict[str, Any]]] = []
    for label, rows in (
        ("balances", normalized_balances),
        ("positions", normalized_positions),
        ("fills", normalized_fills),
        ("fees", normalized_fees),
    ):
        ordered_items.extend((label, row) for row in rows)
    chunk_rows: list[dict[str, list[dict[str, Any]]]] = []
    current = {"balances": [], "positions": [], "fills": [], "fees": []}
    for label, row in ordered_items:
        candidate = {key: list(values) for key, values in current.items()}
        candidate[label].append(row)
        candidate_value = {
            "snapshot_id": snapshot,
            "chunk_index": len(chunk_rows),
            "chunk_count": MAX_VENUE_LEDGER_CHUNKS,
            **candidate,
        }
        item_count = sum(len(values) for values in candidate.values())
        if (
            item_count > MAX_VENUE_LEDGER_ITEMS_PER_CHUNK
            or len(_canonical_json_bytes(candidate_value)) > MAX_VENUE_LEDGER_CHUNK_BYTES
        ):
            if not any(current.values()):
                raise RunnerFactContractError("one venue ledger item exceeds the chunk byte limit")
            chunk_rows.append(current)
            current = {"balances": [], "positions": [], "fills": [], "fees": []}
            current[label].append(row)
        else:
            current = candidate
    if any(current.values()) or not chunk_rows:
        chunk_rows.append(current)
    if len(chunk_rows) > MAX_VENUE_LEDGER_CHUNKS:
        raise RunnerFactContractError("venue ledger snapshot exceeds 4096 chunks")
    chunk_count = len(chunk_rows)
    chunks: list[dict[str, Any]] = []
    chunk_digests: list[str] = []
    for index, rows in enumerate(chunk_rows):
        canonical_chunk = {
            "snapshot_id": snapshot,
            "chunk_index": index,
            "chunk_count": chunk_count,
            **rows,
        }
        canonical_bytes = _canonical_json_bytes(canonical_chunk)
        if len(canonical_bytes) > MAX_VENUE_LEDGER_CHUNK_BYTES:
            raise RunnerFactContractError("venue ledger chunk exceeds 262144 canonical bytes")
        chunk_digest = _sha256_hex(canonical_bytes)
        chunk_digests.append(chunk_digest)
        chunks.append(
            {
                "kind": "venue_ledger_snapshot_chunk",
                "event_id": str(runner_fact_event_id("venue_chunk", snapshot, index)),
                **canonical_chunk,
                "chunk_digest": chunk_digest,
            }
        )
    counts = {
        "balances": len(normalized_balances),
        "positions": len(normalized_positions),
        "fills": len(normalized_fills),
        "fees": len(normalized_fees),
    }
    digest_payload = {
        "schema_version": 1,
        "snapshot_id": snapshot,
        "venue": venue_value,
        "source": source_value,
        "watermark": watermark_value,
        "coverage_from": coverage,
        "observed_through": observed,
        "completeness": completeness_value,
        "counts": counts,
        "chunk_count": chunk_count,
        "chunk_digests": chunk_digests,
    }
    manifest = {
        "kind": "venue_ledger_snapshot_manifest",
        "event_id": str(runner_fact_event_id("venue_manifest", snapshot)),
        "snapshot_id": snapshot,
        "venue": venue_value,
        "source": source_value,
        "watermark": watermark_value,
        "coverage_from": coverage,
        "observed_through": observed,
        "completeness": completeness_value,
        "balances_count": counts["balances"],
        "positions_count": counts["positions"],
        "fills_count": counts["fills"],
        "fees_count": counts["fees"],
        "chunk_count": chunk_count,
        "content_digest": _sha256_hex(_canonical_json_bytes(digest_payload)),
    }
    return [manifest, *chunks]


def reconciliation_period_closed(
    *,
    event_id: UUID | str,
    period: str,
    period_started_at: datetime | str,
    closed_at: datetime | str,
    venue_snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    started = _timestamp(period_started_at, "period_started_at")
    closed = _timestamp(closed_at, "closed_at")
    if datetime.fromisoformat(started.replace("Z", "+00:00")) >= datetime.fromisoformat(
        closed.replace("Z", "+00:00")
    ):
        raise RunnerFactContractError("reconciliation period must have positive duration")
    references = [
        {
            "venue": _non_empty(row.get("venue"), "venue_snapshots.venue"),
            "snapshot_id": _uuid(row.get("snapshot_id"), "venue_snapshots.snapshot_id"),
        }
        for row in venue_snapshots
    ]
    references.sort(key=lambda row: (str(row["venue"]), str(row["snapshot_id"])))
    _require_unique(references, "venue", "venue_snapshots")
    _require_unique(references, "snapshot_id", "venue_snapshots")
    if not references:
        raise RunnerFactContractError("venue_snapshots must not be empty")
    return {
        "kind": "reconciliation_period_closed",
        "event_id": _uuid(event_id, "event_id"),
        "period": _non_empty(period, "period"),
        "period_started_at": started,
        "closed_at": closed,
        "venue_snapshots": references,
    }


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise RunnerFactContractError(f"{field} must be a boolean")
    return value


def _require_unique(rows: Sequence[Mapping[str, Any]], field: str, label: str) -> None:
    values = [str(row[field]) for row in rows]
    if len(values) != len(set(values)):
        raise RunnerFactContractError(f"{label} contains duplicate {field}")


@dataclass(frozen=True, slots=True)
class PendingRunnerFactBatch:
    batch_id: UUID
    stream_key: str
    subject: str
    payload: bytes
    attempts: int


class RunnerFactOutbox:
    """SQLite-backed sequence allocator, event deduper, and durable outbox."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runner_fact_stream (
                    stream_key TEXT PRIMARY KEY,
                    next_sequence INTEGER NOT NULL CHECK (next_sequence > 0),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runner_fact_seen_event (
                    event_id TEXT PRIMARY KEY,
                    stream_key TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL CHECK (source_sequence > 0),
                    batch_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runner_fact_seen_event_stream_sequence
                    ON runner_fact_seen_event(stream_key, source_sequence);
                CREATE TABLE IF NOT EXISTS runner_fact_outbox (
                    batch_id TEXT PRIMARY KEY,
                    stream_key TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    source_seq_start INTEGER NOT NULL CHECK (source_seq_start > 0),
                    source_seq_end INTEGER NOT NULL CHECK (source_seq_end >= source_seq_start),
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    UNIQUE(stream_key, source_seq_start, source_seq_end)
                );
                CREATE INDEX IF NOT EXISTS runner_fact_outbox_delivery_order
                    ON runner_fact_outbox(stream_key, source_seq_start);
                """
            )
        os.chmod(self.path, 0o600)

    async def enqueue(
        self,
        authority: RunnerFactAuthority,
        identity: RunnerFactIdentity,
        facts: Sequence[Mapping[str, Any]],
    ) -> UUID | None:
        return await asyncio.to_thread(self._enqueue, authority, identity, facts)

    def enqueue_sync(
        self,
        authority: RunnerFactAuthority,
        identity: RunnerFactIdentity,
        facts: Sequence[Mapping[str, Any]],
    ) -> UUID | None:
        return self._enqueue(authority, identity, facts)

    def _enqueue(
        self,
        authority: RunnerFactAuthority,
        identity: RunnerFactIdentity,
        facts: Sequence[Mapping[str, Any]],
    ) -> UUID | None:
        if not facts:
            return None
        if len(facts) > MAX_FACTS_PER_BATCH:
            raise RunnerFactContractError(f"batch exceeds {MAX_FACTS_PER_BATCH} facts")
        candidates: list[dict[str, Any]] = []
        event_ids: set[str] = set()
        for value in facts:
            fact = dict(value)
            if "seq" in fact:
                raise RunnerFactContractError("fact seq is allocated only by RunnerFactOutbox")
            event_id = _uuid(fact.get("event_id"), "event_id")
            if event_id in event_ids:
                raise RunnerFactContractError("batch contains duplicate event_id")
            event_ids.add(event_id)
            fact["event_id"] = event_id
            candidates.append(fact)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in event_ids)
            seen = {
                row[0]
                for row in connection.execute(
                    f"SELECT event_id FROM runner_fact_seen_event WHERE event_id IN ({placeholders})",
                    tuple(event_ids),
                )
            }
            candidates = [fact for fact in candidates if fact["event_id"] not in seen]
            if not candidates:
                connection.rollback()
                return None
            row = connection.execute(
                "SELECT next_sequence FROM runner_fact_stream WHERE stream_key = ?",
                (authority.stream_key,),
            ).fetchone()
            source_seq_start = int(row[0]) if row else 1
            sequenced: list[dict[str, Any]] = []
            for offset, fact in enumerate(candidates):
                sequenced.append({**fact, "seq": source_seq_start + offset})
            source_seq_end = source_seq_start + len(sequenced) - 1
            batch_id = uuid4()
            emitted_at = _utc_now()
            payload_digest = _sha256_hex(_canonical_json_bytes(sequenced))
            signing_payload = {
                "schema_version": RUNNER_FACT_SCHEMA_VERSION,
                "batch_id": str(batch_id),
                "tenant_id": authority.tenant_id,
                "trading_mode": authority.trading_mode,
                "runner_id": str(authority.runner_id),
                "deployment_instance_id": str(authority.deployment_instance_id),
                "deployment_spec_id": str(authority.deployment_spec_id),
                "deployment_spec_digest": authority.deployment_spec_digest,
                "strategy_id": str(authority.strategy_id),
                "capability_version_id": str(authority.capability_version_id),
                "capability_version": authority.capability_version,
                "capability_manifest_digest": authority.capability_manifest_digest,
                "key_id": identity.key_id,
                "emitted_at": emitted_at,
                "source_seq_start": source_seq_start,
                "source_seq_end": source_seq_end,
                "payload_digest": payload_digest,
            }
            batch = {
                **signing_payload,
                "facts": sequenced,
                "signature": identity.sign_batch_payload(_canonical_json_bytes(signing_payload)),
            }
            payload = _canonical_json_bytes(batch)
            if len(payload) > MAX_BATCH_BYTES:
                raise RunnerFactContractError(f"batch exceeds {MAX_BATCH_BYTES} bytes")
            connection.execute(
                """
                INSERT INTO runner_fact_outbox (
                    batch_id, stream_key, subject, source_seq_start, source_seq_end,
                    payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(batch_id),
                    authority.stream_key,
                    authority.subject,
                    source_seq_start,
                    source_seq_end,
                    payload,
                    emitted_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO runner_fact_seen_event (
                    event_id, stream_key, source_sequence, batch_id, recorded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        fact["event_id"],
                        authority.stream_key,
                        fact["seq"],
                        str(batch_id),
                        emitted_at,
                    )
                    for fact in sequenced
                ],
            )
            connection.execute(
                """
                INSERT INTO runner_fact_stream (stream_key, next_sequence, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(stream_key) DO UPDATE SET
                    next_sequence = excluded.next_sequence,
                    updated_at = excluded.updated_at
                """,
                (authority.stream_key, source_seq_end + 1, emitted_at),
            )
            connection.commit()
            return batch_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def pending(self, limit: int = 64) -> list[PendingRunnerFactBatch]:
        return await asyncio.to_thread(self._pending, limit)

    def _pending(self, limit: int) -> list[PendingRunnerFactBatch]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT batch_id, stream_key, subject, payload, attempts
                FROM runner_fact_outbox
                ORDER BY stream_key, source_seq_start
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            PendingRunnerFactBatch(
                batch_id=UUID(row["batch_id"]),
                stream_key=row["stream_key"],
                subject=row["subject"],
                payload=bytes(row["payload"]),
                attempts=int(row["attempts"]),
            )
            for row in rows
        ]

    async def acknowledge(self, batch_id: UUID) -> None:
        await asyncio.to_thread(self._acknowledge, batch_id)

    def _acknowledge(self, batch_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM runner_fact_outbox WHERE batch_id = ?", (str(batch_id),)
            )

    async def record_failure(self, batch_id: UUID, error: BaseException) -> None:
        await asyncio.to_thread(self._record_failure, batch_id, type(error).__name__)

    def _record_failure(self, batch_id: UUID, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runner_fact_outbox
                SET attempts = attempts + 1, last_error = ?
                WHERE batch_id = ?
                """,
                (error[:2048], str(batch_id)),
            )


class RunnerFactJetStreamPublisher:
    """Drain a RunnerFactOutbox only after a JetStream PubAck."""

    def __init__(
        self,
        *,
        servers: Sequence[str],
        outbox: RunnerFactOutbox,
        runner_id: UUID,
        authority_guard: Any,
        publish_timeout: float = 5.0,
    ) -> None:
        self._servers = tuple(servers)
        self._outbox = outbox
        self._runner_id = runner_id
        self._authority_guard = authority_guard
        self._publish_timeout = publish_timeout
        self._nats: Any = None
        self._jetstream: Any = None

    async def connect(self) -> None:
        import nats

        if self._nats is not None and self._nats.is_connected:
            return
        self._nats = await nats.connect(
            servers=list(self._servers),
            name=f"custos-runner-fact-{self._runner_id}",
            allow_reconnect=True,
            max_reconnect_attempts=-1,
        )
        self._jetstream = self._nats.jetstream()

    async def drain_once(self) -> int:
        self._authority_guard()
        await self.connect()
        delivered = 0
        blocked_streams: set[str] = set()
        for batch in await self._outbox.pending():
            if batch.stream_key in blocked_streams:
                continue
            try:
                ack = await self._jetstream.publish(
                    batch.subject,
                    batch.payload,
                    headers={"Nats-Msg-Id": str(batch.batch_id)},
                    timeout=self._publish_timeout,
                )
                if not getattr(ack, "stream", None):
                    raise RunnerFactError("JetStream publish returned no stream acknowledgement")
            except Exception as exc:
                await self._outbox.record_failure(batch.batch_id, exc)
                blocked_streams.add(batch.stream_key)
                continue
            await self._outbox.acknowledge(batch.batch_id)
            delivered += 1
        return delivered

    async def run(self, stop: asyncio.Event, idle_seconds: float = 0.5) -> None:
        while not stop.is_set():
            try:
                delivered = await self.drain_once()
            except Exception as exc:  # broker/connect failures must never kill durable retry
                delivered = 0
                _log.error(
                    "runner_fact_publisher_failed",
                    error_type=type(exc).__name__,
                )
            if delivered == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
                except TimeoutError:
                    pass

    async def close(self) -> None:
        if self._nats is not None:
            await self._nats.drain()
        self._nats = None
        self._jetstream = None


class RunnerFactEmitter:
    """Small engine-facing facade; all durable mechanics stay behind it."""

    def __init__(
        self,
        outbox: RunnerFactOutbox,
        identity: RunnerFactIdentity,
        authority_guard: Any,
    ) -> None:
        self._outbox = outbox
        self._identity = identity
        self._authority_guard = authority_guard

    async def emit(
        self,
        authority: RunnerFactAuthority,
        facts: Iterable[Mapping[str, Any]],
    ) -> UUID | None:
        self._authority_guard()
        return await self._outbox.enqueue(authority, self._identity, tuple(facts))

    def emit_sync(
        self,
        authority: RunnerFactAuthority,
        facts: Iterable[Mapping[str, Any]],
    ) -> UUID | None:
        self._authority_guard()
        return self._outbox.enqueue_sync(authority, self._identity, tuple(facts))


@dataclass(frozen=True, slots=True)
class RunnerCapabilityScopeBinding:
    projector: str
    trading_mode: str
    deployment_instance_id: str
    deployment_spec_id: str
    deployment_spec_digest: str
    strategy_id: str
    source_policy_digest: str | None
    required_venues: tuple[tuple[str, str], ...]

    def evidence_value(self) -> dict[str, Any]:
        return {
            "projector": self.projector,
            "trading_mode": self.trading_mode,
            "deployment_instance_id": self.deployment_instance_id,
            "deployment_spec_id": self.deployment_spec_id,
            "deployment_spec_digest": self.deployment_spec_digest,
            "strategy_id": self.strategy_id,
            "source_policy_digest": self.source_policy_digest,
            "required_venues": [
                {"venue": venue, "ledger_source": ledger_source}
                for venue, ledger_source in self.required_venues
            ],
        }


def _canonical_uuid_value(value: object, field: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RunnerFactContractError(f"{field} must be a UUID") from exc
    if parsed.int == 0:
        raise RunnerFactContractError(f"{field} must not be nil")
    return str(parsed)


def normalize_capability_scope_bindings(
    manifest: Mapping[str, Any],
) -> tuple[RunnerCapabilityScopeBinding, ...]:
    """Reproduce Crucible's declared_bindings order and normalized JSON shape."""

    base_fields = {
        "trading_mode",
        "deployment_instance_id",
        "deployment_spec_id",
        "deployment_spec_digest",
        "strategy_id",
    }
    declarations = (
        ("settlement", "settlement_scope_bindings", set()),
        ("risk", "risk_scope_bindings", {"resource_type", "resource_id"}),
        (
            "reconciliation",
            "reconciliation_scope_bindings",
            {"source_policy_digest", "required_venues"},
        ),
        (
            "health",
            "health_scope_bindings",
            {"expected_cadence_seconds", "grace_seconds"},
        ),
    )
    result: list[RunnerCapabilityScopeBinding] = []
    identities: set[tuple[str, str]] = set()
    for projector, field, extra_fields in declarations:
        rows = manifest.get(field, [])
        if not isinstance(rows, list):
            raise RunnerFactContractError(f"{field} must be a list")
        for index, raw in enumerate(rows):
            label = f"{field}[{index}]"
            if not isinstance(raw, dict) or set(raw) != base_fields | extra_fields:
                raise RunnerFactContractError(f"{label} has an invalid field set")
            mode = raw["trading_mode"]
            if mode not in {"live", "sandbox", "testnet"}:
                raise RunnerFactContractError(f"{label}.trading_mode is invalid")
            instance_id = _canonical_uuid_value(
                raw["deployment_instance_id"], f"{label}.deployment_instance_id"
            )
            spec_id = _canonical_uuid_value(
                raw["deployment_spec_id"], f"{label}.deployment_spec_id"
            )
            strategy_id = _canonical_uuid_value(raw["strategy_id"], f"{label}.strategy_id")
            spec_digest = raw["deployment_spec_digest"]
            if not _is_lower_sha256(spec_digest):
                raise RunnerFactContractError(
                    f"{label}.deployment_spec_digest must be lowercase SHA-256"
                )
            identity = (projector, instance_id)
            if identity in identities:
                raise RunnerFactContractError(
                    f"{projector} repeats deployment_instance_id {instance_id}"
                )
            identities.add(identity)

            source_policy_digest: str | None = None
            required_venues: tuple[tuple[str, str], ...] = ()
            if projector == "risk":
                _non_empty(raw["resource_type"], f"{label}.resource_type")
                _canonical_uuid_value(raw["resource_id"], f"{label}.resource_id")
            elif projector == "reconciliation":
                source_policy_digest = raw["source_policy_digest"]
                if not _is_lower_sha256(source_policy_digest):
                    raise RunnerFactContractError(
                        f"{label}.source_policy_digest must be lowercase SHA-256"
                    )
                venues = raw["required_venues"]
                if not isinstance(venues, list) or not venues:
                    raise RunnerFactContractError(f"{label}.required_venues must be non-empty")
                normalized_venues: list[tuple[str, str]] = []
                for venue_index, venue_source in enumerate(venues):
                    venue_label = f"{label}.required_venues[{venue_index}]"
                    if not isinstance(venue_source, dict) or set(venue_source) != {
                        "venue",
                        "ledger_source",
                    }:
                        raise RunnerFactContractError(f"{venue_label} has an invalid field set")
                    venue = _non_empty(venue_source["venue"], f"{venue_label}.venue")
                    ledger_source = venue_source["ledger_source"]
                    if ledger_source not in {"venue_api", "drop_copy"}:
                        raise RunnerFactContractError(
                            f"{venue_label}.ledger_source is not independently authoritative"
                        )
                    normalized_venues.append((venue, ledger_source))
                if len(normalized_venues) != len(set(normalized_venues)):
                    raise RunnerFactContractError(f"{label}.required_venues contains duplicates")
                required_venues = tuple(normalized_venues)
            elif projector == "health":
                cadence = raw["expected_cadence_seconds"]
                grace = raw["grace_seconds"]
                if type(cadence) is not int or cadence <= 0 or type(grace) is not int or grace < 0:
                    raise RunnerFactContractError(f"{label} cadence/grace values are invalid")

            result.append(
                RunnerCapabilityScopeBinding(
                    projector=projector,
                    trading_mode=mode,
                    deployment_instance_id=instance_id,
                    deployment_spec_id=spec_id,
                    deployment_spec_digest=spec_digest,
                    strategy_id=strategy_id,
                    source_policy_digest=source_policy_digest,
                    required_venues=required_venues,
                )
            )
    return tuple(result)


def capability_scope_binding_values(
    bindings: Iterable[RunnerCapabilityScopeBinding],
) -> list[dict[str, Any]]:
    return [binding.evidence_value() for binding in bindings]


def capability_binding_evidence_digest(
    tenant_id: str,
    runner_id: UUID | str,
    bindings: Iterable[RunnerCapabilityScopeBinding],
) -> str:
    evidence = {
        "schema_version": 1,
        "tenant_id": _non_empty(tenant_id, "tenant_id"),
        "runner_id": _canonical_uuid_value(runner_id, "runner_id"),
        "bindings": capability_scope_binding_values(bindings),
    }
    return _sha256_hex(_canonical_json_bytes(evidence))


@dataclass(frozen=True, slots=True)
class RunnerCapabilityReceipt:
    """Public, non-secret authority returned by atomic Runner onboarding."""

    tenant_id: str
    runner_id: UUID
    capability_version_id: UUID
    capability_version: int
    manifest_digest: str
    key_id: str
    key_version: int
    algorithm: str
    public_key_digest: str
    binding_status: str
    binding_evidence_digest: str
    capability_manifest: Mapping[str, Any]
    scope_bindings: tuple[RunnerCapabilityScopeBinding, ...]

    def require_scope_bindings(
        self,
        *,
        projectors: Iterable[str],
        trading_mode: str,
        deployment_instance_id: UUID | str,
        deployment_spec_id: UUID | str,
        deployment_spec_digest: str,
        strategy_id: UUID | str,
    ) -> None:
        instance_id = _canonical_uuid_value(deployment_instance_id, "deployment_instance_id")
        spec_id = _canonical_uuid_value(deployment_spec_id, "deployment_spec_id")
        strategy = _canonical_uuid_value(strategy_id, "strategy_id")
        if trading_mode not in {"live", "sandbox", "testnet"} or not _is_lower_sha256(
            deployment_spec_digest
        ):
            raise RunnerFactContractError("runtime DeploymentInstance scope is invalid")
        required = tuple(projectors)
        if not required or len(required) != len(set(required)):
            raise RunnerFactContractError("required projector set is empty or duplicated")
        for projector in required:
            candidates = [
                binding
                for binding in self.scope_bindings
                if binding.projector == projector and binding.deployment_instance_id == instance_id
            ]
            if len(candidates) != 1:
                raise RunnerFactContractError(
                    f"capability has no unique {projector} binding for DeploymentInstance"
                )
            binding = candidates[0]
            if (
                binding.trading_mode != trading_mode
                or binding.deployment_spec_id != spec_id
                or binding.deployment_spec_digest != deployment_spec_digest
                or binding.strategy_id != strategy
            ):
                raise RunnerFactContractError(
                    f"capability {projector} binding does not match runtime DeploymentInstance"
                )

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> RunnerCapabilityReceipt:
        from pathlib import Path

        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunnerFactContractError("Runner capability receipt is unreadable") from exc
        if not isinstance(document, dict):
            raise RunnerFactContractError("Runner capability receipt must be a JSON object")
        required = {
            "tenant_id",
            "schema_version",
            "runner_id",
            "capability_version_id",
            "capability_version",
            "manifest_digest",
            "key_id",
            "key_version",
            "algorithm",
            "public_key_digest",
            "binding_status",
            "binding_evidence_digest",
            "capability_manifest",
            "scope_bindings",
        }
        if not required.issubset(document):
            raise RunnerFactContractError("Runner capability receipt is incomplete")
        manifest_digest = document["manifest_digest"]
        public_key_digest = document["public_key_digest"]
        binding_status = document["binding_status"]
        evidence_digest = document.get("binding_evidence_digest")
        manifest = document["capability_manifest"]
        if not isinstance(manifest, dict):
            raise RunnerFactContractError("receipt capability_manifest must be an object")
        bindings = normalize_capability_scope_bindings(manifest)
        binding_values = capability_scope_binding_values(bindings)
        if (
            document["schema_version"] != 1
            or not _is_lower_sha256(manifest_digest)
            or not _is_lower_sha256(public_key_digest)
            or binding_status != "validated"
            or not _is_lower_sha256(evidence_digest)
            or document["algorithm"] != "ed25519"
            or type(document["capability_version"]) is not int
            or document["capability_version"] != 1
            or type(document["key_version"]) is not int
            or document["key_version"] != 1
        ):
            raise RunnerFactContractError(
                "Runner capability receipt violates the v1 authority contract"
            )
        if _sha256_hex(_canonical_json_bytes(manifest)) != manifest_digest:
            raise RunnerFactContractError("receipt capability_manifest digest mismatch")
        if document["scope_bindings"] != binding_values:
            raise RunnerFactContractError("receipt normalized scope_bindings mismatch")
        calculated_evidence_digest = capability_binding_evidence_digest(
            document["tenant_id"], document["runner_id"], bindings
        )
        if calculated_evidence_digest != evidence_digest:
            raise RunnerFactContractError("receipt binding evidence digest mismatch")
        try:
            return cls(
                tenant_id=_non_empty(document["tenant_id"], "tenant_id"),
                runner_id=UUID(str(document["runner_id"])),
                capability_version_id=UUID(str(document["capability_version_id"])),
                capability_version=document["capability_version"],
                manifest_digest=manifest_digest,
                key_id=_non_empty(document["key_id"], "key_id"),
                key_version=document["key_version"],
                algorithm=document["algorithm"],
                public_key_digest=public_key_digest,
                binding_status=binding_status,
                binding_evidence_digest=evidence_digest,
                capability_manifest=manifest,
                scope_bindings=bindings,
            )
        except (TypeError, ValueError, AttributeError) as exc:
            raise RunnerFactContractError("Runner capability receipt identity is invalid") from exc


def _is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
