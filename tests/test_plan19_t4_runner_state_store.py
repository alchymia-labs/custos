from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from custos.core.runner_fact import (
    RUNNER_STATE_SCHEMA_VERSION,
    RunnerFactAuthority,
    RunnerFactIdentity,
    RunnerFactOutbox,
    RunnerFactPendingPubAckError,
    RunnerFactStreamCutoverFrozen,
    RunnerFactStreamCutoverRequired,
    RunnerStateAuthorityError,
    RunnerStateMigrationError,
)

RUNNER_ID = UUID("10000000-0000-4000-8000-000000000001")
INSTANCE_ID = UUID("20000000-0000-4000-8000-000000000002")
SPEC_ID = UUID("30000000-0000-4000-8000-000000000003")
STRATEGY_ID = UUID("40000000-0000-4000-8000-000000000004")
CAPABILITY_ID = UUID("50000000-0000-4000-8000-000000000005")
SHA_A = "a" * 64
SHA_B = "b" * 64


def _authority() -> RunnerFactAuthority:
    return RunnerFactAuthority(
        tenant_id="acme",
        trading_mode="sandbox",
        runner_id=RUNNER_ID,
        deployment_instance_id=INSTANCE_ID,
        deployment_spec_id=SPEC_ID,
        deployment_spec_digest=SHA_A,
        generation=1,
        strategy_id=STRATEGY_ID,
        capability_version_id=CAPABILITY_ID,
        capability_version=1,
        capability_manifest_digest=SHA_B,
    )


def _identity() -> RunnerFactIdentity:
    return RunnerFactIdentity(Ed25519PrivateKey.generate(), "plan19-t4-test-key")


def _fact(label: str) -> dict[str, str]:
    return {"kind": "test_fact", "event_id": str(uuid4()), "label": label}


def _document(payload: bytes) -> dict:
    value = json.loads(payload)
    assert isinstance(value, dict)
    return value


def test_existing_outbox_database_upgrades_in_place_to_single_state_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runner-facts.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE runner_fact_stream (
                stream_key TEXT PRIMARY KEY,
                next_sequence INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE runner_fact_seen_event (
                event_id TEXT PRIMARY KEY,
                stream_key TEXT NOT NULL,
                source_sequence INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE runner_fact_outbox (
                batch_id TEXT PRIMARY KEY,
                stream_key TEXT NOT NULL,
                subject TEXT NOT NULL,
                source_seq_start INTEGER NOT NULL,
                source_seq_end INTEGER NOT NULL,
                payload BLOB NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                UNIQUE(stream_key, source_seq_start, source_seq_end)
            );
            """
        )

    RunnerFactOutbox(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = connection.execute(
            "SELECT schema_version FROM runner_state_schema WHERE singleton = 1"
        ).fetchone()[0]
    assert version == RUNNER_STATE_SCHEMA_VERSION
    assert {
        "desired_deployments",
        "applied_deployments",
        "command_outcomes",
        "command_in_progress_lease",
        "artifact_activation",
        "runner_cap_policy",
        "order_reservation",
        "runner_exposure_checkpoint",
        "runner_stream_cutover",
        "runner_fact_outbox",
    } <= tables


def test_newer_database_schema_is_never_silently_downgraded(tmp_path: Path) -> None:
    database = tmp_path / "runner-facts.sqlite3"
    RunnerFactOutbox(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE runner_state_schema SET schema_version = ? WHERE singleton = 1",
            (RUNNER_STATE_SCHEMA_VERSION + 1,),
        )

    with pytest.raises(RunnerStateMigrationError, match="newer Custos schema"):
        RunnerFactOutbox(database)


@pytest.mark.asyncio
async def test_instance_stream_continues_across_spec_and_generation_changes(
    tmp_path: Path,
) -> None:
    outbox = RunnerFactOutbox(tmp_path / "runner-facts.sqlite3")
    identity = _identity()
    first = _authority()
    second = replace(
        first,
        deployment_spec_id=UUID("30000000-0000-4000-8000-000000000099"),
        deployment_spec_digest="c" * 64,
        generation=2,
    )

    await outbox.enqueue(first, identity, [_fact("first")])
    await outbox.enqueue(second, identity, [_fact("second")])
    pending = await outbox.pending()
    documents = [_document(batch.payload) for batch in pending]

    assert first.stream_key == second.stream_key
    assert first.subject == second.subject
    assert str(first.deployment_spec_id) not in first.stream_key
    assert first.deployment_spec_digest not in first.subject
    assert [document["source_seq_start"] for document in documents] == [1, 2]
    assert [document["generation"] for document in documents] == [1, 2]
    assert [document["deployment_spec_id"] for document in documents] == [
        str(first.deployment_spec_id),
        str(second.deployment_spec_id),
    ]


def _seed_legacy_streams(database: Path, authority: RunnerFactAuthority) -> UUID:
    first = (
        f"{authority.stream_key}:{authority.deployment_spec_id}:{authority.deployment_spec_digest}"
    )
    second = f"{authority.stream_key}:30000000-0000-4000-8000-000000000099:{'c' * 64}"
    pending_batch_id = uuid4()
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO runner_fact_stream (stream_key, next_sequence, updated_at) VALUES (?, ?, ?)",
            [(first, 3, "2026-07-15T00:00:00Z"), (second, 4, "2026-07-15T00:00:00Z")],
        )
        connection.execute(
            """
            INSERT INTO runner_fact_outbox (
                batch_id, stream_key, subject, source_seq_start, source_seq_end,
                payload, created_at
            ) VALUES (?, ?, ?, 1, 2, ?, ?)
            """,
            (
                str(pending_batch_id),
                first,
                "legacy.subject",
                b"immutable-signed-legacy-payload",
                "2026-07-15T00:00:00Z",
            ),
        )
    return pending_batch_id


@pytest.mark.asyncio
async def test_cutover_freezes_intake_refuses_pending_puback_and_continues_sequence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runner-facts.sqlite3"
    outbox = RunnerFactOutbox(database)
    authority = _authority()
    pending_batch_id = _seed_legacy_streams(database, authority)

    frozen = await outbox.freeze_stream_cutover(authority)
    assert frozen.state == "frozen"
    assert len(frozen.legacy_stream_keys) == 2
    with pytest.raises(RunnerFactStreamCutoverFrozen):
        await outbox.enqueue(authority, _identity(), [_fact("blocked")])
    before = (await outbox.pending())[0]
    assert before.payload == b"immutable-signed-legacy-payload"
    with pytest.raises(RunnerFactPendingPubAckError, match="pending PubAck"):
        await outbox.activate_stream_cutover(authority)
    after_refusal = (await outbox.pending())[0]
    assert after_refusal == before

    await outbox.acknowledge(pending_batch_id)
    active = await outbox.activate_stream_cutover(authority)
    assert active.state == "active"
    assert active.continuation_sequence == 6
    await outbox.enqueue(authority, _identity(), [_fact("continued")])
    continued = (await outbox.pending())[0]
    assert _document(continued.payload)["source_seq_start"] == 6

    with sqlite3.connect(database) as connection:
        retained_legacy_streams = connection.execute(
            "SELECT COUNT(*) FROM runner_fact_stream WHERE stream_key IN (?, ?)",
            active.legacy_stream_keys,
        ).fetchone()[0]
    assert retained_legacy_streams == 2


@pytest.mark.asyncio
async def test_legacy_stream_requires_explicit_cutover_before_new_intake(tmp_path: Path) -> None:
    database = tmp_path / "runner-facts.sqlite3"
    outbox = RunnerFactOutbox(database)
    authority = _authority()
    _seed_legacy_streams(database, authority)

    with pytest.raises(RunnerFactStreamCutoverRequired):
        await outbox.enqueue(authority, _identity(), [_fact("blocked")])


@pytest.mark.asyncio
async def test_cutover_rejects_cross_tenant_instance_rebinding(tmp_path: Path) -> None:
    outbox = RunnerFactOutbox(tmp_path / "runner-facts.sqlite3")
    authority = _authority()
    await outbox.freeze_stream_cutover(authority)

    with pytest.raises(RunnerStateAuthorityError, match="different authority"):
        await outbox.freeze_stream_cutover(replace(authority, tenant_id="other-tenant"))
