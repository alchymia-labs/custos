#!/usr/bin/env python3
"""Small OCI Distribution client used by the toolkit RC release boundary."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

OCI_MANIFEST_MEDIA_TYPE: Final = "application/vnd.oci.image.manifest.v1+json"
OCI_ARTIFACT_TYPE: Final = "application/vnd.alephain.custos.strategy-toolkit.rc.v1"
OCI_CONFIG_MEDIA_TYPE: Final = "application/vnd.alephain.custos.strategy-toolkit.rc.config.v1+json"
OCI_TITLE_ANNOTATION: Final = "org.opencontainers.image.title"
OCI_ROLE_ANNOTATION: Final = "io.alephain.custos.toolkit.role"
OCI_SOURCE_COORDINATE_ANNOTATION: Final = "io.alephain.custos.source.coordinate"


class OciRegistryError(RuntimeError):
    """The registry failed a deterministic OCI Distribution operation."""


class OciManifestConflictError(OciRegistryError):
    """A discovery tag already resolves to a different immutable manifest."""


class OciCommitUnknownError(OciRegistryError):
    """The manifest request lost its response after the commit may have occurred."""


def sha256_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


@dataclass(frozen=True, slots=True)
class OciDescriptor:
    media_type: str
    digest: str
    size: int
    annotations: Mapping[str, str]

    def document(self) -> dict[str, object]:
        return {
            "mediaType": self.media_type,
            "digest": self.digest,
            "size": self.size,
            "annotations": dict(sorted(self.annotations.items())),
        }

    @classmethod
    def parse(cls, value: object, *, label: str) -> OciDescriptor:
        if not isinstance(value, dict):
            raise OciRegistryError(f"{label} descriptor must be an object")
        annotations = value.get("annotations")
        if not isinstance(annotations, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in annotations.items()
        ):
            raise OciRegistryError(f"{label} descriptor annotations differ")
        media_type = value.get("mediaType")
        digest = value.get("digest")
        size = value.get("size")
        if (
            not isinstance(media_type, str)
            or not media_type
            or not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or len(digest) != 71
            or any(character not in "0123456789abcdef" for character in digest[7:])
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            raise OciRegistryError(f"{label} descriptor identity differs")
        return cls(media_type, digest, size, annotations)


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


class OciRegistryClient:
    """Strict subset of OCI Distribution needed for one immutable artifact."""

    def __init__(
        self,
        registry: str,
        repository: str,
        *,
        username: str = "",
        token: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        raw = registry.rstrip("/")
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
            raise OciRegistryError("registry must be one HTTP(S) origin")
        if repository.startswith(("/", ".")) or repository.endswith("/") or ".." in repository:
            raise OciRegistryError("OCI repository path is invalid")
        if bool(username) != bool(token):
            raise OciRegistryError("OCI username and token must be supplied together")
        self.registry = parsed.netloc
        self.repository = repository
        self._origin = f"{parsed.scheme}://{parsed.netloc}"
        self._timeout_seconds = timeout_seconds
        self._authorization = ""
        if token:
            encoded = base64.b64encode(f"{username}:{token}".encode()).decode()
            self._authorization = f"Basic {encoded}"

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            parsed = urlsplit(path_or_url)
            origin = urlsplit(self._origin)
            if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
                raise OciRegistryError("OCI upload Location escaped the registry origin")
            return path_or_url
        return urljoin(f"{self._origin}/", path_or_url.lstrip("/"))

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        allowed_statuses: tuple[int, ...],
        commit_unknown: bool = False,
    ) -> _Response:
        request_headers = dict(headers or {})
        if self._authorization:
            request_headers["Authorization"] = self._authorization
        request = Request(
            self._url(path_or_url),
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                status = response.status
                body = response.read()
                response_headers = {key.lower(): value for key, value in response.headers.items()}
        except HTTPError as exc:
            status = exc.code
            body = exc.read()
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
        except (URLError, OSError) as exc:
            if commit_unknown:
                raise OciCommitUnknownError(
                    f"OCI manifest commit response was lost: {exc}"
                ) from exc
            raise OciRegistryError(f"OCI registry {method} failed: {exc}") from exc
        if status not in allowed_statuses:
            detail = body.decode(errors="replace")[:500]
            if commit_unknown and status >= 500:
                raise OciCommitUnknownError(
                    f"OCI manifest commit returned ambiguous HTTP {status}: {detail}"
                )
            raise OciRegistryError(f"OCI registry {method} returned HTTP {status}: {detail}")
        return _Response(status, response_headers, body)

    def _repository_path(self, suffix: str) -> str:
        repository = quote(self.repository, safe="/")
        return f"/v2/{repository}/{suffix}"

    def resolve_manifest(self, reference: str) -> str | None:
        response = self._request(
            "HEAD",
            self._repository_path(f"manifests/{quote(reference, safe=':')}"),
            headers={"Accept": OCI_MANIFEST_MEDIA_TYPE},
            allowed_statuses=(200, 404),
        )
        if response.status == 404:
            return None
        digest = response.headers.get("docker-content-digest")
        if digest is None or not digest.startswith("sha256:") or len(digest) != 71:
            raise OciRegistryError("registry manifest HEAD omitted Docker-Content-Digest")
        return digest

    def upload_blob(self, descriptor: OciDescriptor, content: bytes) -> None:
        if descriptor.digest != sha256_digest(content) or descriptor.size != len(content):
            raise OciRegistryError("local OCI blob differs from descriptor")
        present = self._request(
            "HEAD",
            self._repository_path(f"blobs/{descriptor.digest}"),
            allowed_statuses=(200, 404),
        )
        if present.status == 200:
            return
        started = self._request(
            "POST",
            self._repository_path("blobs/uploads/"),
            data=b"",
            headers={"Content-Length": "0"},
            allowed_statuses=(202,),
        )
        location = started.headers.get("location")
        if not location:
            raise OciRegistryError("OCI blob upload omitted Location")
        absolute = self._url(location)
        parsed = urlsplit(absolute)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("digest", descriptor.digest))
        target = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )
        committed = self._request(
            "PUT",
            target,
            data=content,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content)),
            },
            allowed_statuses=(201,),
        )
        if committed.headers.get("docker-content-digest") != descriptor.digest:
            raise OciRegistryError("OCI blob commit digest differs")

    def put_manifest(self, tag: str, content: bytes) -> str:
        expected = sha256_digest(content)
        response = self._request(
            "PUT",
            self._repository_path(f"manifests/{quote(tag, safe='')}"),
            data=content,
            headers={
                "Content-Type": OCI_MANIFEST_MEDIA_TYPE,
                "Content-Length": str(len(content)),
            },
            allowed_statuses=(201,),
            commit_unknown=True,
        )
        actual = response.headers.get("docker-content-digest")
        if actual != expected:
            raise OciRegistryError("OCI manifest commit digest differs")
        return actual

    def read_manifest(self, reference: str) -> tuple[bytes, str]:
        response = self._request(
            "GET",
            self._repository_path(f"manifests/{quote(reference, safe=':')}"),
            headers={"Accept": OCI_MANIFEST_MEDIA_TYPE},
            allowed_statuses=(200,),
        )
        digest = response.headers.get("docker-content-digest")
        calculated = sha256_digest(response.body)
        if digest != calculated:
            raise OciRegistryError("OCI manifest readback digest differs")
        return response.body, calculated

    def read_blob(self, digest: str) -> bytes:
        response = self._request(
            "GET",
            self._repository_path(f"blobs/{quote(digest, safe=':')}"),
            allowed_statuses=(200,),
        )
        if sha256_digest(response.body) != digest:
            raise OciRegistryError("OCI blob readback digest differs")
        return response.body

    def verify_release(
        self,
        *,
        tag: str,
        manifest_digest: str,
        manifest_content: bytes,
        descriptors: tuple[OciDescriptor, ...],
    ) -> None:
        digest_content, digest_header = self.read_manifest(manifest_digest)
        tag_content, tag_header = self.read_manifest(tag)
        if (
            digest_header != manifest_digest
            or tag_header != manifest_digest
            or digest_content != manifest_content
            or tag_content != manifest_content
        ):
            raise OciRegistryError("OCI tag or digest manifest readback differs")
        for descriptor in descriptors:
            content = self.read_blob(descriptor.digest)
            if len(content) != descriptor.size:
                raise OciRegistryError("OCI descriptor readback size differs")


def parse_manifest_document(content: bytes) -> tuple[OciDescriptor, tuple[OciDescriptor, ...]]:
    try:
        document: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OciRegistryError(f"OCI manifest is not JSON: {exc}") from exc
    if (
        not isinstance(document, dict)
        or document.get("schemaVersion") != 2
        or document.get("mediaType") != OCI_MANIFEST_MEDIA_TYPE
        or document.get("artifactType") != OCI_ARTIFACT_TYPE
    ):
        raise OciRegistryError("OCI toolkit manifest identity differs")
    config = OciDescriptor.parse(document.get("config"), label="OCI config")
    if config.media_type != OCI_CONFIG_MEDIA_TYPE:
        raise OciRegistryError("OCI toolkit config media type differs")
    raw_layers = document.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise OciRegistryError("OCI toolkit manifest has no layers")
    layers = tuple(
        OciDescriptor.parse(value, label=f"OCI layer {index}")
        for index, value in enumerate(raw_layers)
    )
    return config, layers


__all__ = [
    "OCI_ARTIFACT_TYPE",
    "OCI_CONFIG_MEDIA_TYPE",
    "OCI_MANIFEST_MEDIA_TYPE",
    "OCI_ROLE_ANNOTATION",
    "OCI_SOURCE_COORDINATE_ANNOTATION",
    "OCI_TITLE_ANNOTATION",
    "OciCommitUnknownError",
    "OciDescriptor",
    "OciManifestConflictError",
    "OciRegistryClient",
    "OciRegistryError",
    "canonical_json",
    "parse_manifest_document",
    "sha256_digest",
]
