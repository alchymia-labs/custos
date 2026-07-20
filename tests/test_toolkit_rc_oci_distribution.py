from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from scripts.toolkit_rc_oci import (
    OCI_MANIFEST_MEDIA_TYPE,
    OciCommitUnknownError,
    OciDescriptor,
    OciRegistryClient,
    OciRegistryError,
    sha256_digest,
)


@dataclass(slots=True)
class RegistryState:
    blobs: dict[str, bytes] = field(default_factory=dict)
    manifests: dict[str, tuple[str, bytes]] = field(default_factory=dict)
    authorizations: list[str] = field(default_factory=list)
    next_manifest_status: int | None = None
    foreign_upload_location: bool = False
    require_bearer: bool = False


class RegistryHandler(BaseHTTPRequestHandler):
    server: RegistryServer

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _record_authorization(self) -> None:
        self.server.state.authorizations.append(self.headers.get("Authorization", ""))

    def _response(
        self,
        status: int,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _challenge(self) -> bool:
        if (
            self.server.state.require_bearer
            and self.headers.get("Authorization") != "Bearer registry-token"
        ):
            realm = f"http://{self.headers['Host']}/token"
            self._response(
                401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer realm="{realm}",service="test-registry",'
                        'scope="repository:custos/toolkit:pull,push"'
                    )
                },
            )
            return True
        return False

    def do_HEAD(self) -> None:  # noqa: N802
        self._record_authorization()
        if self._challenge():
            return
        path = unquote(urlsplit(self.path).path)
        if "/blobs/" in path:
            digest = path.rsplit("/", 1)[-1]
            self._response(200 if digest in self.server.state.blobs else 404)
            return
        reference = path.rsplit("/", 1)[-1]
        manifest = self.server.state.manifests.get(reference)
        self._response(
            200 if manifest else 404,
            headers=({"Docker-Content-Digest": manifest[0]} if manifest is not None else None),
        )

    def do_POST(self) -> None:  # noqa: N802
        self._record_authorization()
        if self._challenge():
            return
        location = (
            "https://foreign.example/upload"
            if self.server.state.foreign_upload_location
            else "/v2/custos/toolkit/blobs/uploads/upload-1"
        )
        self._response(202, headers={"Location": location})

    def do_PUT(self) -> None:  # noqa: N802
        self._record_authorization()
        if self._challenge():
            return
        parsed = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        content = self.rfile.read(length)
        if "/blobs/uploads/" in parsed.path:
            digest = parse_qs(parsed.query)["digest"][0]
            self.server.state.blobs[digest] = content
            self._response(201, headers={"Docker-Content-Digest": digest})
            return
        status = self.server.state.next_manifest_status
        self.server.state.next_manifest_status = None
        if status is not None:
            self._response(status)
            return
        reference = unquote(parsed.path.rsplit("/", 1)[-1])
        digest = sha256_digest(content)
        self.server.state.manifests[reference] = (digest, content)
        self.server.state.manifests[digest] = (digest, content)
        self._response(201, headers={"Docker-Content-Digest": digest})

    def do_GET(self) -> None:  # noqa: N802
        self._record_authorization()
        path = unquote(urlsplit(self.path).path)
        if path == "/token":
            self._response(
                200,
                body=json.dumps({"token": "registry-token"}).encode(),
                headers={"Content-Type": "application/json"},
            )
            return
        if self._challenge():
            return
        if "/blobs/" in path:
            digest = path.rsplit("/", 1)[-1]
            self._response(200, body=self.server.state.blobs[digest])
            return
        reference = path.rsplit("/", 1)[-1]
        digest, content = self.server.state.manifests[reference]
        self._response(
            200,
            body=content,
            headers={
                "Content-Type": OCI_MANIFEST_MEDIA_TYPE,
                "Docker-Content-Digest": digest,
            },
        )


class RegistryServer(ThreadingHTTPServer):
    state: RegistryState


@contextmanager
def _registry(
    state: RegistryState | None = None,
) -> Iterator[tuple[str, RegistryState]]:
    active = state or RegistryState()
    server = RegistryServer(("127.0.0.1", 0), RegistryHandler)
    server.state = active
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", active
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_distribution_client_uploads_commits_and_reads_every_digest() -> None:
    with _registry() as (registry, state):
        client = OciRegistryClient(
            registry,
            "custos/toolkit",
            username="publisher",
            token="workflow-token",
        )
        blob = b"immutable layer"
        descriptor = OciDescriptor(
            media_type="application/octet-stream",
            digest=sha256_digest(blob),
            size=len(blob),
            annotations={"org.opencontainers.image.title": "layer.bin"},
        )
        client.upload_blob(descriptor, blob)
        manifest = b'{"schemaVersion":2}'
        digest = client.put_manifest("0.1.0rc1", manifest)
        client.verify_release(
            tag="0.1.0rc1",
            manifest_digest=digest,
            manifest_content=manifest,
            descriptors=(descriptor,),
        )

    assert state.blobs[descriptor.digest] == blob
    assert state.manifests["0.1.0rc1"] == (digest, manifest)
    assert state.authorizations
    assert all(value.startswith("Basic ") for value in state.authorizations)


def test_manifest_server_error_is_an_unknown_commit_outcome() -> None:
    state = RegistryState(next_manifest_status=503)
    with _registry(state) as (registry, _):
        client = OciRegistryClient(registry, "custos/toolkit")
        with pytest.raises(OciCommitUnknownError, match="ambiguous HTTP 503"):
            client.put_manifest("0.1.0rc1", b'{"schemaVersion":2}')


def test_distribution_client_exchanges_and_reuses_bearer_scope() -> None:
    state = RegistryState(require_bearer=True)
    with _registry(state) as (registry, _):
        client = OciRegistryClient(
            registry,
            "custos/toolkit",
            username="publisher",
            token="workflow-token",
        )
        assert client.resolve_manifest("0.1.0rc1") is None
        content = b"layer"
        descriptor = OciDescriptor(
            media_type="application/octet-stream",
            digest=sha256_digest(content),
            size=len(content),
            annotations={"org.opencontainers.image.title": "layer.bin"},
        )
        client.upload_blob(descriptor, content)

    assert any(value.startswith("Basic ") for value in state.authorizations)
    assert "Bearer registry-token" in state.authorizations


def test_blob_upload_location_cannot_escape_with_registry_credentials() -> None:
    state = RegistryState(foreign_upload_location=True)
    with _registry(state) as (registry, _):
        client = OciRegistryClient(
            registry,
            "custos/toolkit",
            username="publisher",
            token="workflow-token",
        )
        content = b"layer"
        descriptor = OciDescriptor(
            media_type="application/octet-stream",
            digest=sha256_digest(content),
            size=len(content),
            annotations={"org.opencontainers.image.title": "layer.bin"},
        )
        with pytest.raises(OciRegistryError, match="escaped the registry origin"):
            client.upload_blob(descriptor, content)
