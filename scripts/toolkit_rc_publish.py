#!/usr/bin/env python3
"""Local-only atomic publication protocol for Custos toolkit RC candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from custos_toolkit.contracts import (
    ImmutableToolkitArtifactBindingV1,
    ToolkitRcMemberV1,
    ToolkitRcReceiptManifestV1,
)
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

BINDING_FIELDS: Final = (
    "wheel",
    "sbom",
    "contract_schema",
    "contract_asset_index",
    "sigstore_attestation",
    "t4b_zero_rewrite_receipt",
    "t4b_typing_closure_receipt",
    "t5_pre_import_verifier_receipt",
)
BUILD_DISTRIBUTIONS: Final = frozenset(
    {"custos-strategy-toolkit", "custos-strategy-toolkit-nautilus"}
)
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})


class ArtifactPublicationError(RuntimeError):
    """The candidate failed closed before a T6d release receipt could exist."""


class ArtifactCoordinateExistsError(ArtifactPublicationError):
    """An immutable artifact coordinate already exists."""


@dataclass(frozen=True, slots=True)
class PublicationObject:
    label: str
    coordinate: str
    sha256: str
    content: bytes

    @property
    def object_id(self) -> str:
        return hashlib.sha256(self.coordinate.encode()).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class PendingPublicationEvidence:
    candidate_version: str
    publication_id: str
    manifest_sha256: str
    build_manifest_sha256: str
    pending_receipt_path: Path


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        content = path.read_bytes()
        document = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactPublicationError(f"{label} is not readable canonical input: {exc}") from exc
    if not isinstance(document, dict):
        raise ArtifactPublicationError(f"{label} must be a JSON object")
    return content, document


def _contains_exact_version(coordinate: str, candidate_version: str) -> bool:
    prefix = coordinate.rsplit("@sha256:", 1)[0]
    tokens = prefix.replace(":", "/").split("/")
    return candidate_version in tokens


def _validate_locked_dependencies(
    member: ToolkitRcMemberV1, build_document: Mapping[str, Any]
) -> None:
    locked = {canonicalize_name(dependency.name): dependency for dependency in member.dependencies}
    raw_requirements = build_document.get("requires_dist")
    if not isinstance(raw_requirements, list) or not all(
        isinstance(value, str) for value in raw_requirements
    ):
        raise ArtifactPublicationError("T6b wheel dependency evidence is invalid")
    for value in raw_requirements:
        try:
            requirement = Requirement(value)
        except InvalidRequirement as exc:
            raise ArtifactPublicationError(
                f"T6b wheel dependency is not a valid requirement: {value}"
            ) from exc
        dependency = locked.get(canonicalize_name(requirement.name))
        if dependency is None:
            raise ArtifactPublicationError(
                f"T6a manifest does not lock T6b dependency {requirement.name}"
            )
        try:
            version = Version(dependency.version)
        except InvalidVersion as exc:
            raise ArtifactPublicationError(
                f"T6a dependency version is invalid: {dependency.version}"
            ) from exc
        if requirement.url is not None or (
            requirement.specifier and version not in requirement.specifier
        ):
            raise ArtifactPublicationError(
                f"T6a dependency lock does not satisfy T6b requirement {value}"
            )


def _validate_build_evidence(
    manifest: ToolkitRcReceiptManifestV1,
    build_document: Mapping[str, Any],
) -> None:
    required_flags = {
        "status": "BUILD_CANDIDATE_ONLY",
        "candidate_version": manifest.candidate_version,
        "reproducible": True,
        "registry_accessed": False,
        "ready_receipt_created": False,
        "strategy_release_bom_created": False,
    }
    for name, expected in required_flags.items():
        if build_document.get(name) != expected:
            raise ArtifactPublicationError(f"T6b build evidence has invalid {name}")

    source_commit = build_document.get("source_commit")
    if not isinstance(source_commit, str) or any(
        member.source_commit != source_commit for member in manifest.members
    ):
        raise ArtifactPublicationError("T6a and T6b source commits differ")
    builds = build_document.get("builds")
    if not isinstance(builds, dict):
        raise ArtifactPublicationError("T6b build evidence has no isolated builds")
    first = builds.get("build-1")
    second = builds.get("build-2")
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ArtifactPublicationError("T6b build evidence requires build-1 and build-2")
    if set(first) != BUILD_DISTRIBUTIONS or set(second) != BUILD_DISTRIBUTIONS:
        raise ArtifactPublicationError("T6b build evidence distribution matrix differs")

    members = {member.distribution_name: member for member in manifest.members}
    for distribution in sorted(BUILD_DISTRIBUTIONS):
        first_wheel = first[distribution]
        second_wheel = second[distribution]
        if not isinstance(first_wheel, dict) or first_wheel != second_wheel:
            raise ArtifactPublicationError(f"T6b {distribution} build records are not reproducible")
        member = members[distribution]
        expected = {
            "distribution_name": member.distribution_name,
            "version": member.version,
            "sha256": member.wheel.sha256,
            "size_bytes": member.wheel.size_bytes,
        }
        for name, value in expected.items():
            if first_wheel.get(name) != value:
                raise ArtifactPublicationError(f"T6a manifest and T6b {distribution} {name} differ")
        try:
            python_policy_matches = SpecifierSet(
                str(first_wheel.get("requires_python", ""))
            ) == SpecifierSet(member.python_requires)
        except InvalidSpecifier as exc:
            raise ArtifactPublicationError(f"T6b {distribution} Python policy is invalid") from exc
        if not python_policy_matches:
            raise ArtifactPublicationError(
                f"T6a manifest and T6b {distribution} requires_python differ"
            )
        if set(first_wheel.get("top_level_modules", ())) != set(member.top_level_modules):
            raise ArtifactPublicationError(
                f"T6a manifest and T6b {distribution} top-level modules differ"
            )
        _validate_locked_dependencies(member, first_wheel)


def _binding_objects(
    *,
    manifest: ToolkitRcReceiptManifestV1,
    object_sources: Mapping[str, Path],
) -> list[PublicationObject]:
    expected_coordinates: set[str] = set()
    objects: dict[str, PublicationObject] = {}
    for member in manifest.members:
        for field_name in BINDING_FIELDS:
            binding = getattr(member, field_name)
            if not isinstance(binding, ImmutableToolkitArtifactBindingV1):
                raise ArtifactPublicationError(f"invalid T6a binding {field_name}")
            coordinate = binding.coordinate
            expected_coordinates.add(coordinate)
            if not _contains_exact_version(coordinate, manifest.candidate_version):
                raise ArtifactPublicationError(
                    f"artifact coordinate does not contain exact {manifest.candidate_version}"
                )
            source = object_sources.get(coordinate)
            if source is None:
                raise ArtifactPublicationError(
                    f"missing local source for {member.role.value}.{field_name}"
                )
            try:
                content = Path(source).read_bytes()
            except OSError as exc:
                raise ArtifactPublicationError(
                    f"cannot read local source for {member.role.value}.{field_name}: {exc}"
                ) from exc
            if _sha256(content) != binding.sha256 or len(content) != binding.size_bytes:
                raise ArtifactPublicationError(
                    f"local source digest or size differs for {member.role.value}.{field_name}"
                )
            candidate = PublicationObject(
                label=f"{member.role.value}.{field_name}",
                coordinate=coordinate,
                sha256=binding.sha256,
                content=content,
            )
            existing = objects.get(coordinate)
            if existing is not None and existing != candidate:
                raise ArtifactPublicationError("one coordinate binds different local objects")
            objects[coordinate] = candidate

    supplied_coordinates = set(object_sources)
    if supplied_coordinates != expected_coordinates:
        unexpected = sorted(supplied_coordinates - expected_coordinates)
        missing = sorted(expected_coordinates - supplied_coordinates)
        raise ArtifactPublicationError(
            f"object source matrix differs; missing={missing}, unexpected={unexpected}"
        )
    return list(objects.values())


class _LocalArtifactServiceClient:
    def __init__(self, base_url: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
            raise ArtifactPublicationError("T6c artifact service must be a loopback HTTP endpoint")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ArtifactPublicationError("artifact service URL must contain only its origin")
        self._base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        expected_statuses: set[int],
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, bytes]:
        headers = {} if content_type is None else {"Content-Type": content_type}
        request = Request(
            f"{self._base_url}{path}",
            data=content,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:  # noqa: S310 - loopback only.
                status = response.status
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            body = exc.read()
        except (OSError, URLError) as exc:
            raise ArtifactPublicationError(f"artifact service {operation} failed: {exc}") from exc
        if status not in expected_statuses:
            detail = body.decode(errors="replace")
            raise ArtifactPublicationError(
                f"artifact service {operation} failed with HTTP {status}: {detail}"
            )
        return status, body

    @staticmethod
    def _document(body: bytes, operation: str) -> dict[str, Any]:
        try:
            document = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ArtifactPublicationError(
                f"artifact service {operation} returned invalid JSON"
            ) from exc
        if not isinstance(document, dict):
            raise ArtifactPublicationError(
                f"artifact service {operation} returned a non-object response"
            )
        return document

    def require_absent(self, artifact: PublicationObject) -> None:
        status, _ = self._request(
            "HEAD",
            f"/v1/artifacts/{artifact.object_id}",
            operation=f"preflight {artifact.label}",
            expected_statuses={200, 404},
        )
        if status == 200:
            raise ArtifactCoordinateExistsError(
                f"immutable coordinate already exists: {artifact.coordinate}"
            )

    def begin(self, candidate_version: str, objects: list[PublicationObject]) -> str:
        request = _canonical_json(
            {
                "candidate_version": candidate_version,
                "objects": [
                    {
                        "coordinate": artifact.coordinate,
                        "object_id": artifact.object_id,
                        "sha256": artifact.sha256,
                        "size_bytes": artifact.size_bytes,
                    }
                    for artifact in objects
                ],
            }
        )
        _, body = self._request(
            "POST",
            "/v1/publications",
            operation="begin",
            expected_statuses={201},
            content=request,
            content_type="application/json",
        )
        response = self._document(body, "begin")
        transaction_id = response.get("transaction_id")
        if (
            response.get("accepted") is not True
            or response.get("atomic") is not True
            or not isinstance(transaction_id, str)
            or not transaction_id
        ):
            raise ArtifactPublicationError(
                "artifact service did not accept an atomic publication transaction"
            )
        return transaction_id

    def stage(self, transaction_id: str, artifact: PublicationObject) -> None:
        _, body = self._request(
            "PUT",
            (f"/v1/publications/{quote(transaction_id, safe='')}/artifacts/{artifact.object_id}"),
            operation=f"stage {artifact.label}",
            expected_statuses={201},
            content=artifact.content,
            content_type="application/octet-stream",
        )
        response = self._document(body, f"stage {artifact.label}")
        expected = {
            "ack": True,
            "coordinate": artifact.coordinate,
            "object_id": artifact.object_id,
            "sha256": artifact.sha256,
        }
        if any(response.get(name) != value for name, value in expected.items()):
            raise ArtifactPublicationError(
                f"artifact service stage ACK differs for {artifact.label}"
            )

    def commit(self, transaction_id: str, objects: list[PublicationObject]) -> str:
        _, body = self._request(
            "POST",
            f"/v1/publications/{quote(transaction_id, safe='')}/commit",
            operation="commit",
            expected_statuses={200},
            content=_canonical_json({"commit": True}),
            content_type="application/json",
        )
        response = self._document(body, "commit")
        publication_id = response.get("publication_id")
        expected_objects = {
            (artifact.coordinate, artifact.object_id, artifact.sha256) for artifact in objects
        }
        actual_objects = {
            (item.get("coordinate"), item.get("object_id"), item.get("sha256"))
            for item in response.get("objects", ())
            if isinstance(item, dict)
        }
        if (
            response.get("puback") is not True
            or not isinstance(publication_id, str)
            or not publication_id
            or actual_objects != expected_objects
        ):
            raise ArtifactPublicationError("artifact service commit returned no complete PubAck")
        return publication_id

    def require_exact_readback(self, artifact: PublicationObject) -> None:
        _, content = self._request(
            "GET",
            f"/v1/artifacts/{artifact.object_id}",
            operation=f"readback {artifact.label}",
            expected_statuses={200},
        )
        if content != artifact.content or _sha256(content) != artifact.sha256:
            raise ArtifactPublicationError(
                f"artifact service readback digest differs for {artifact.label}"
            )


def _provenance_object(
    *, label: str, candidate_version: str, filename: str, content: bytes
) -> PublicationObject:
    digest = _sha256(content)
    return PublicationObject(
        label=label,
        coordinate=(
            f"artifact://custos/toolkit-rc/{candidate_version}/provenance/{filename}"
            f"@sha256:{digest}"
        ),
        sha256=digest,
        content=content,
    )


def publish_toolkit_rc_candidate(
    *,
    manifest_path: Path,
    build_manifest_path: Path,
    object_sources: Mapping[str, Path],
    artifact_service_url: str,
    pending_receipt_path: Path,
) -> PendingPublicationEvidence:
    """Publish one candidate atomically to a loopback service and emit PENDING evidence."""

    pending_receipt_path = pending_receipt_path.resolve()
    if pending_receipt_path.exists():
        raise ArtifactPublicationError("pending publication evidence must not be overwritten")
    client = _LocalArtifactServiceClient(artifact_service_url)
    manifest_content, manifest_document = _read_json(manifest_path, "T6a manifest")
    try:
        manifest = ToolkitRcReceiptManifestV1.model_validate(manifest_document)
    except ValueError as exc:
        raise ArtifactPublicationError(f"T6a manifest contract differs: {exc}") from exc
    build_content, build_document = _read_json(build_manifest_path, "T6b build manifest")
    _validate_build_evidence(manifest, build_document)
    objects = _binding_objects(manifest=manifest, object_sources=object_sources)
    objects.extend(
        (
            _provenance_object(
                label="t6a_manifest",
                candidate_version=manifest.candidate_version,
                filename="toolkit-rc-receipt-manifest.json",
                content=manifest_content,
            ),
            _provenance_object(
                label="t6b_build_manifest",
                candidate_version=manifest.candidate_version,
                filename="toolkit-rc-build-manifest-input.json",
                content=build_content,
            ),
        )
    )
    objects.sort(key=lambda artifact: artifact.coordinate)
    object_ids = [artifact.object_id for artifact in objects]
    if len(object_ids) != len(set(object_ids)):
        raise ArtifactPublicationError("artifact coordinate identity collision")

    for artifact in objects:
        client.require_absent(artifact)
    transaction_id = client.begin(manifest.candidate_version, objects)
    for artifact in objects:
        client.stage(transaction_id, artifact)
    publication_id = client.commit(transaction_id, objects)
    for artifact in objects:
        client.require_exact_readback(artifact)

    pending_document = {
        "schema_version": "alephain.custos.toolkit-rc-publication-pending.v1",
        "status": "PENDING_T6D_RELEASE_RUNNER",
        "ready": False,
        "candidate_version": manifest.candidate_version,
        "publication_id": publication_id,
        "manifest_sha256": _sha256(manifest_content),
        "build_manifest_sha256": _sha256(build_content),
        "source_commit": build_document["source_commit"],
        "source_date_epoch": build_document["source_date_epoch"],
        "publication_atomic": True,
        "puback_verified": True,
        "readback_verified": True,
        "production_credentials_used": False,
        "production_attestation_verified": False,
        "objects": [
            {
                "coordinate": artifact.coordinate,
                "object_id": artifact.object_id,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            }
            for artifact in objects
        ],
        "t6d_required_gates": [
            "credentialed production artifact-service runner",
            "production Sigstore identity and attestation verification",
            "final deterministic SPDX or CycloneDX SBOMs",
            "remote immutable-coordinate and digest readback",
            "final authority receipt registration",
        ],
    }
    pending_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pending_receipt_path.open("xb") as output:
            output.write(_canonical_json(pending_document))
    except FileExistsError as exc:
        raise ArtifactPublicationError(
            "pending publication evidence must not be overwritten"
        ) from exc
    return PendingPublicationEvidence(
        candidate_version=manifest.candidate_version,
        publication_id=publication_id,
        manifest_sha256=_sha256(manifest_content),
        build_manifest_sha256=_sha256(build_content),
        pending_receipt_path=pending_receipt_path,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise the local-only atomic toolkit RC publication contract without "
            "creating release authority."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--build-manifest", required=True, type=Path)
    parser.add_argument(
        "--object-sources",
        required=True,
        type=Path,
        help="JSON object mapping each T6a coordinate to one local source path.",
    )
    parser.add_argument("--artifact-service-url", required=True)
    parser.add_argument("--pending-receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the local contract CLI."""

    arguments = _parser().parse_args(argv)
    _, source_document = _read_json(arguments.object_sources, "object source map")
    source_root = arguments.object_sources.resolve().parent
    object_sources = {
        coordinate: (Path(path) if Path(path).is_absolute() else source_root / Path(path))
        for coordinate, path in source_document.items()
        if isinstance(coordinate, str) and isinstance(path, str)
    }
    if len(object_sources) != len(source_document):
        raise ArtifactPublicationError("object source map must contain string paths")
    evidence = publish_toolkit_rc_candidate(
        manifest_path=arguments.manifest,
        build_manifest_path=arguments.build_manifest,
        object_sources=object_sources,
        artifact_service_url=arguments.artifact_service_url,
        pending_receipt_path=arguments.pending_receipt,
    )
    print(
        json.dumps(
            {
                "candidate_version": evidence.candidate_version,
                "pending_receipt_path": str(evidence.pending_receipt_path),
                "publication_id": evidence.publication_id,
                "status": "PENDING_T6D_RELEASE_RUNNER",
            },
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "ArtifactCoordinateExistsError",
    "ArtifactPublicationError",
    "PendingPublicationEvidence",
    "publish_toolkit_rc_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
