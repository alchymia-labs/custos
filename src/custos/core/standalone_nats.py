"""Idempotent JetStream topology bootstrap for standalone deployments."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

import nats
from nats.js.api import StorageType, StreamConfig
from nats.js.errors import NotFoundError

from custos.core.log import get_logger

_log = get_logger("custos.standalone_nats")
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_OWNER_METADATA = {"owner": "custos", "profile": "standalone"}
_CONNECT_RETRY_SECS = 0.1

ConnectFactory = Callable[[str], Awaitable[Any]]


def _validate_tenant_id(tenant_id: str) -> str:
    if not _SAFE_ID.fullmatch(tenant_id):
        raise ValueError("tenant_id must match ^[a-zA-Z0-9_-]{1,64}$")
    return tenant_id


def _tenant_hash(tenant_id: str) -> str:
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12].upper()


def standalone_stream_configs(tenant_id: str) -> tuple[StreamConfig, StreamConfig]:
    """Return the complete Custos-owned standalone topology for a tenant."""

    tenant = _validate_tenant_id(tenant_id)
    tenant_hash = _tenant_hash(tenant)
    metadata = {**_OWNER_METADATA, "tenant_hash": tenant_hash}
    deployment = StreamConfig(
        name=f"CUSTOS_{tenant_hash}_DEPLOYMENT",
        description="Custos standalone DeploymentSpec desired state",
        subjects=[f"arx.{tenant}.deployment_spec.>"],
        storage=StorageType.FILE,
        max_msgs_per_subject=1,
        metadata=metadata,
    )
    observed = StreamConfig(
        name=f"CUSTOS_{tenant_hash}_OBSERVED",
        description="Custos standalone observed state and telemetry",
        subjects=[
            f"arx.{tenant}.deployment_status.>",
            f"arx.{tenant}.heartbeat.>",
            f"arx.{tenant}.telemetry.>",
            f"arx.{tenant}.snapshot.>",
            f"arx.{tenant}.pre_trade_reject.>",
            f"arx.{tenant}.enrollment.>",
        ],
        storage=StorageType.FILE,
        metadata=metadata,
    )
    return deployment, observed


def _is_owned(config: StreamConfig, desired: StreamConfig) -> bool:
    current = config.metadata or {}
    expected = desired.metadata or {}
    return all(current.get(key) == value for key, value in expected.items())


def _managed_shape(config: StreamConfig) -> tuple[Any, ...]:
    metadata = config.metadata or {}
    return (
        config.description,
        tuple(config.subjects or ()),
        config.storage,
        config.max_msgs_per_subject,
        tuple(sorted((key, metadata.get(key)) for key in (*_OWNER_METADATA, "tenant_hash"))),
    )


async def ensure_standalone_streams(jetstream: Any, tenant_id: str) -> None:
    """Create missing streams and reconcile drift only for owned stream names."""

    for desired in standalone_stream_configs(tenant_id):
        assert desired.name is not None
        try:
            current_info = await jetstream.stream_info(desired.name)
        except NotFoundError:
            await jetstream.add_stream(config=desired)
            _log.info("standalone_nats_stream_created", stream=desired.name)
            continue

        current = current_info.config
        if not _is_owned(current, desired):
            _log.error("standalone_nats_stream_not_owned", stream=desired.name)
            raise RuntimeError(
                f"stream {desired.name!r} exists but is not owned by Custos standalone profile"
            )
        if _managed_shape(current) == _managed_shape(desired):
            continue
        await jetstream.update_stream(config=desired)
        _log.info("standalone_nats_stream_updated", stream=desired.name)


async def bootstrap_standalone_nats(
    *,
    nats_url: str,
    tenant_id: str,
    timeout_secs: float = 30.0,
    connect_factory: ConnectFactory | None = None,
) -> None:
    """Wait for NATS, reconcile the standalone topology, then drain cleanly."""

    standalone_stream_configs(tenant_id)
    if timeout_secs <= 0:
        raise ValueError("timeout_secs must be greater than zero")
    connect = connect_factory or nats.connect

    async def run() -> None:
        attempt = 0
        connection = None
        while connection is None:
            attempt += 1
            try:
                connection = await connect(nats_url)
            except Exception as exc:  # noqa: BLE001 - retry until the explicit timeout
                _log.warning(
                    "standalone_nats_connect_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(_CONNECT_RETRY_SECS)
        try:
            await ensure_standalone_streams(connection.jetstream(), tenant_id)
        finally:
            await connection.drain()

    try:
        await asyncio.wait_for(run(), timeout=timeout_secs)
    except TimeoutError as exc:
        raise TimeoutError(
            f"NATS at {nats_url!r} did not become ready within {timeout_secs:g} seconds"
        ) from exc
