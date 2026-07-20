"""Plan 19 T7C real-NATS revocation protocol acceptance."""

from __future__ import annotations

import asyncio
import os
import shutil
import ssl
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import nats
import nkeys  # type: ignore[import-untyped]
import pytest
from nats.errors import Error as NatsError

from custos.core.nats_transport import _is_explicit_nats_authorization_rejection

_IMAGE = os.environ.get("CUSTOS_NATS_TEST_IMAGE", "nats:2.10-alpine")
_ENABLED = os.environ.get("CUSTOS_RUN_REAL_NATS_REVOCATION") == "1"


def _require_local_gate() -> None:
    if not _ENABLED:
        pytest.skip("set CUSTOS_RUN_REAL_NATS_REVOCATION=1 to run the real NATS gate")
    for binary in ("docker", "openssl"):
        if shutil.which(binary) is None:
            pytest.fail(f"{binary} is required by the real NATS revocation gate")
    inspected = subprocess.run(
        ["docker", "image", "inspect", _IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0:
        pytest.fail(
            f"immutable test image {_IMAGE} is unavailable; preload it before running the gate"
        )


def _run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _nkey() -> tuple[str, str]:
    seed = nkeys.encode_seed(os.urandom(32), nkeys.PREFIX_BYTE_USER)
    pair = nkeys.from_seed(bytearray(seed))
    try:
        return seed.decode("ascii"), pair.public_key.decode("ascii")
    finally:
        pair.wipe()


def _server_config(*, old_public: str | None, new_public: str) -> str:
    users = [f'{{ nkey: "{new_public}" }}']
    if old_public is not None:
        users.insert(0, f'{{ nkey: "{old_public}" }}')
    return (
        'port: 4222\nserver_name: "custos-t7c-real-nats"\n'
        f"authorization {{ users = [ {', '.join(users)} ] }}\n"
        'tls { cert_file: "/config/server.crt"; '
        'key_file: "/config/server.key"; timeout: 2 }\n'
    )


def _write_tls_material(root: Path) -> Path:
    openssl_config = root / "openssl.cnf"
    openssl_config.write_text(
        """\
[req]
distinguished_name=dn
x509_extensions=v3_req
prompt=no
[dn]
CN=localhost
[v3_req]
subjectAltName=@alt_names
[alt_names]
DNS.1=localhost
IP.1=127.0.0.1
"""
    )
    certificate = root / "server.crt"
    _run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-keyout",
        str(root / "server.key"),
        "-out",
        str(certificate),
        "-config",
        str(openssl_config),
    )
    return certificate


def _wait_ready(container: str) -> None:
    for _ in range(50):
        logs = _run("docker", "logs", container, check=False)
        if "Server is ready" in f"{logs.stdout}\n{logs.stderr}":
            return
        time.sleep(0.1)
    logs = _run("docker", "logs", container, check=False)
    pytest.fail(f"NATS did not become ready:\n{logs.stdout}\n{logs.stderr}")


async def _exercise_revocation(
    *,
    port: int,
    certificate: Path,
    old_seed: str,
    new_seed: str,
    container: str,
    active_config: Path,
    revoked_config: str,
) -> None:
    context = ssl.create_default_context(cafile=str(certificate))
    disconnected = asyncio.Event()

    async def record_disconnect() -> None:
        disconnected.set()

    async def ignore_expected_error(_error: Exception) -> None:
        return

    url = f"tls://localhost:{port}"
    old = await nats.connect(
        url,
        nkeys_seed_str=old_seed,
        tls=context,
        tls_hostname="localhost",
        disconnected_cb=record_disconnect,
        error_cb=ignore_expected_error,
        reconnect_time_wait=0.1,
        max_reconnect_attempts=1,
    )
    replacement = await nats.connect(
        url,
        nkeys_seed_str=new_seed,
        tls=context,
        tls_hostname="localhost",
        allow_reconnect=False,
    )
    try:
        active_config.write_text(revoked_config)
        _run("docker", "kill", "--signal", "HUP", container)
        await asyncio.wait_for(disconnected.wait(), timeout=8)
        await asyncio.sleep(0.3)

        with pytest.raises(NatsError) as rejected:
            await nats.connect(
                url,
                nkeys_seed_str=old_seed,
                tls=context,
                tls_hostname="localhost",
                allow_reconnect=False,
                connect_timeout=1,
                error_cb=ignore_expected_error,
            )
        assert _is_explicit_nats_authorization_rejection(rejected.value)

        await replacement.publish("custos.t7c.revocation-gate", b"replacement-active")
        await replacement.flush(timeout=2)
        assert replacement.is_connected
    finally:
        await replacement.close()
        if not old.is_closed:
            await old.close()


@pytest.mark.integration
@pytest.mark.docker
def test_real_nats_forces_old_disconnect_and_denies_exact_reconnect(
    tmp_path: Path,
) -> None:
    _require_local_gate()
    old_seed, old_public = _nkey()
    new_seed, new_public = _nkey()
    certificate = _write_tls_material(tmp_path)
    active_config = tmp_path / "nats.conf"
    active_config.write_text(_server_config(old_public=old_public, new_public=new_public))
    revoked_config = _server_config(old_public=None, new_public=new_public)
    tmp_path.chmod(0o755)
    certificate.chmod(0o644)
    active_config.chmod(0o644)

    container = f"custos-t7c-{uuid4().hex}"
    started = _run(
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        container,
        "-p",
        "127.0.0.1::4222",
        "-v",
        f"{tmp_path}:/config",
        _IMAGE,
        "-c",
        "/config/nats.conf",
    )
    assert started.stdout.strip()
    try:
        _wait_ready(container)
        port_output = _run("docker", "port", container, "4222/tcp").stdout.strip()
        port = int(port_output.rsplit(":", 1)[1])
        asyncio.run(
            _exercise_revocation(
                port=port,
                certificate=certificate,
                old_seed=old_seed,
                new_seed=new_seed,
                container=container,
                active_config=active_config,
                revoked_config=revoked_config,
            )
        )
        logs = _run("docker", "logs", container, check=False)
        combined = f"{logs.stdout}\n{logs.stderr}"
        assert "Reloaded: authorization nkey users" in combined
        assert "Reloaded server configuration" in combined
    finally:
        _run("docker", "stop", "-t", "1", container, check=False)
