"""Sanity checks for the recon-result envelope shape."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from custos.core.nats_client import ArxNatsClient
from custos.core.reconcile import ReconcileUploader, ReconResult


def sample_result() -> ReconResult:
    now = datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    return ReconResult(
        dimension="balance",
        domain="cex",
        source_amount=Decimal("100.00000000"),
        source_currency="USD",
        source_as_of=now,
        target_amount=Decimal("110.00000000"),
        target_currency="USD",
        target_as_of=now,
        tolerance=Decimal("0.05"),
        in_flight_count=0,
        deployment_spec_id="00000000-0000-0000-0000-000000000000",
        scope="account-1",
    )


def test_payload_shape_round_trips_through_json() -> None:
    payload = sample_result().to_payload()
    blob = json.dumps(payload)
    back = json.loads(blob)
    assert back["dimension"] == "balance"
    assert back["domain"] == "cex"
    # Decimals are wire-encoded as strings so backend rust_decimal can
    # parse them losslessly.
    assert back["source_amount"] == "100.00000000"
    assert back["tolerance"] == "0.05"
    assert back["scope"] == "account-1"


def test_envelope_carries_ordering_metadata() -> None:
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r-001",
    )
    uploader = ReconcileUploader(
        nats_client=client,
        tenant_id="acme",
        runner_id="r-001",
        session_id="11111111-1111-1111-1111-111111111111",
    )
    env = uploader.build_envelope(sample_result().to_payload(), seq=42)

    assert env.tenant_id == "acme"
    # Subject demux (plan-index §6) routes recon_result; payload no
    # longer carries a "kind" discriminator.
    assert env.payload["dimension"] == "balance"
    assert env.ordering is not None
    assert env.ordering.seq == 42
    assert env.ordering.session_id == "11111111-1111-1111-1111-111111111111"


def test_event_id_is_uuid_v7() -> None:
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r-001",
    )
    uploader = ReconcileUploader(
        nats_client=client,
        tenant_id="acme",
        runner_id="r-001",
        session_id="11111111-1111-1111-1111-111111111111",
    )
    env = uploader.build_envelope(sample_result().to_payload(), seq=1)
    # UUIDv7 sets the version nibble (13th hex char) to '7'.
    assert env.event_id[14] == "7", env.event_id


def test_subject_routes_to_recon_result_kind() -> None:
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r-001",
    )
    uploader = ReconcileUploader(
        nats_client=client,
        tenant_id="acme",
        runner_id="r-001",
        session_id="sess-1",
    )
    assert uploader.subject() == "arx.acme.recon_result.r-001.sess-1"
