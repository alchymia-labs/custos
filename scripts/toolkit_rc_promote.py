#!/usr/bin/env python3
"""Verify one durable toolkit publication and emit a READY candidate only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Final

from custos_toolkit.contracts import (
    ImmutableToolkitArtifactBindingV1,
    ToolkitRcAuthorityReadyReceiptV1,
    ToolkitRcPublicationReceiptV1,
    ToolkitRcReceiptManifestV1,
)

from scripts.toolkit_rc_publish import (
    ArtifactPublicationError,
    _ArtifactServiceClient,
    _validate_build_evidence,
)

WORKFLOW_IDENTITY: Final = (
    "https://github.com/alchymia-labs/custos/.github/workflows/"
    "release-toolkit-rc.yml@refs/heads/main"
)
OIDC_ISSUER: Final = "https://token.actions.githubusercontent.com"
STABLE_READY_PATH: Final = Path(
    "docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json"
)
PREREQUISITE_PATHS: Final = (
    Path("docs/authority/receipts/custos-plan-18-task-4-extraction-receipt.json"),
    Path("docs/authority/receipts/custos-plan-18-task-4b-typing-closure-receipt.json"),
    Path("docs/authority/receipts/custos-plan-18-task-2-schema-receipt-v2.json"),
)
SIGNED_SUBJECT_FIELDS: Final = (
    "wheel",
    "sbom",
    "contract_schema",
    "contract_asset_index",
    "dependency_lock_evidence",
    "t4_zero_rewrite_receipt",
    "t4b_typing_closure_receipt",
    "t5_pre_import_verifier_receipt",
)
SHARED_EVIDENCE_FIELDS: Final = (
    "contract_schema",
    "contract_asset_index",
    "dependency_lock_evidence",
    "slsa_provenance",
    "sigstore_attestation",
    "t4_zero_rewrite_receipt",
    "t4b_typing_closure_receipt",
    "t5_pre_import_verifier_receipt",
)
BUILD_TYPE: Final = "https://custos.the-alephain-guild/build-types/toolkit-rc/v1"
SOURCE_REPOSITORY: Final = "https://github.com/alchymia-labs/custos"


class ToolkitRcPromotionError(RuntimeError):
    """Durable evidence cannot be promoted without weakening authority."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require_production_publication_receipt(
    receipt: ToolkitRcPublicationReceiptV1,
) -> None:
    if (
        receipt.status != "PENDING_T6E_AUTHORITY_REGISTRATION"
        or receipt.ready
        or receipt.handoff_ready
        or not receipt.production_credentials_used
        or not receipt.production_signature_verified
        or receipt.authority_registered
        or receipt.workflow_identity != WORKFLOW_IDENTITY
        or receipt.oidc_issuer != OIDC_ISSUER
    ):
        raise ToolkitRcPromotionError("publication receipt is not production promotion evidence")


def _binding_for(path: Path, coordinate: str) -> ImmutableToolkitArtifactBindingV1:
    content = path.read_bytes()
    return ImmutableToolkitArtifactBindingV1(
        coordinate=coordinate,
        sha256=_sha256(content),
        size_bytes=len(content),
    )


def _json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolkitRcPromotionError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ToolkitRcPromotionError(f"{label} must be a JSON object")
    return document


def _coordinate_filename(binding: ImmutableToolkitArtifactBindingV1) -> str:
    return binding.coordinate.rsplit("@sha256:", 1)[0].rsplit("/", 1)[-1]


def _shared_binding(
    manifest: ToolkitRcReceiptManifestV1, field_name: str
) -> ImmutableToolkitArtifactBindingV1:
    bindings = tuple(getattr(member, field_name) for member in manifest.members)
    identities = {(value.coordinate, value.sha256, value.size_bytes) for value in bindings}
    if len(identities) != 1:
        raise ToolkitRcPromotionError(
            f"toolkit members do not share one {field_name} authority object"
        )
    return bindings[0]


def _subject_matrix(values: object, label: str) -> dict[str, str]:
    if not isinstance(values, list):
        raise ToolkitRcPromotionError(f"{label} must be an array")
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            raise ToolkitRcPromotionError(f"{label} contains an invalid subject")
        digest = value.get("digest")
        if not isinstance(digest, dict) or set(digest) != {"sha256"}:
            raise ToolkitRcPromotionError(f"{label} contains a non-SHA-256 subject")
        sha256 = digest.get("sha256")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ToolkitRcPromotionError(f"{label} contains an invalid SHA-256 digest")
        name = value["name"]
        if name in result:
            raise ToolkitRcPromotionError(f"{label} contains a duplicate subject name")
        result[name] = sha256
    return result


def _validate_dependency_lock(
    *,
    manifest: ToolkitRcReceiptManifestV1,
    objects: dict[str, bytes],
    source_commit: str,
) -> str:
    binding = _shared_binding(manifest, "dependency_lock_evidence")
    document = _json_object(objects[binding.coordinate], "dependency lock evidence")
    if (
        document.get("candidate_version") != manifest.candidate_version
        or document.get("source_commit") != source_commit
    ):
        raise ToolkitRcPromotionError("dependency lock identity differs")
    uv_lock_sha256 = document.get("uv_lock_sha256")
    if not isinstance(uv_lock_sha256, str) or len(uv_lock_sha256) != 64:
        raise ToolkitRcPromotionError("dependency lock lacks the committed uv.lock digest")
    distributions = document.get("distributions")
    if not isinstance(distributions, dict):
        raise ToolkitRcPromotionError("dependency lock distribution matrix is absent")
    expected_distributions = {member.distribution_name for member in manifest.members}
    if set(distributions) != expected_distributions:
        raise ToolkitRcPromotionError("dependency lock distribution matrix differs")
    for member in manifest.members:
        records = distributions[member.distribution_name]
        if not isinstance(records, list) or not all(isinstance(value, dict) for value in records):
            raise ToolkitRcPromotionError("dependency lock record matrix is invalid")
        actual = {
            (value.get("name"), value.get("version"), value.get("requirement")) for value in records
        }
        expected = {(value.name, value.version, value.requirement) for value in member.dependencies}
        if actual != expected:
            raise ToolkitRcPromotionError(
                f"{member.distribution_name} dependency lock differs from manifest"
            )
    return uv_lock_sha256


def _validate_signed_provenance(
    *,
    manifest: ToolkitRcReceiptManifestV1,
    build: dict[str, Any],
    build_content: bytes,
    objects: dict[str, bytes],
    source_commit: str,
    source_date_epoch: int,
) -> None:
    try:
        _validate_build_evidence(manifest, build)
    except ArtifactPublicationError as exc:
        raise ToolkitRcPromotionError(f"build evidence differs during promotion: {exc}") from exc

    for field_name in SHARED_EVIDENCE_FIELDS:
        _shared_binding(manifest, field_name)
    uv_lock_sha256 = _validate_dependency_lock(
        manifest=manifest,
        objects=objects,
        source_commit=source_commit,
    )
    provenance_binding = _shared_binding(manifest, "slsa_provenance")
    provenance = _json_object(objects[provenance_binding.coordinate], "signed SLSA provenance")
    if (
        provenance.get("_type") != "https://in-toto.io/Statement/v1"
        or provenance.get("predicateType") != "https://slsa.dev/provenance/v1"
    ):
        raise ToolkitRcPromotionError("signed provenance statement type differs")

    expected_subjects: dict[str, str] = {}
    for member in manifest.members:
        for field_name in SIGNED_SUBJECT_FIELDS:
            binding = getattr(member, field_name)
            filename = _coordinate_filename(binding)
            previous = expected_subjects.setdefault(filename, binding.sha256)
            if previous != binding.sha256:
                raise ToolkitRcPromotionError(
                    "manifest maps one signed provenance subject name to different bytes"
                )
    if _subject_matrix(provenance.get("subject"), "signed provenance subjects") != (
        expected_subjects
    ):
        raise ToolkitRcPromotionError("signed provenance subject matrix differs")

    predicate = provenance.get("predicate")
    if not isinstance(predicate, dict):
        raise ToolkitRcPromotionError("signed provenance predicate is absent")
    build_definition = predicate.get("buildDefinition")
    run_details = predicate.get("runDetails")
    if not isinstance(build_definition, dict) or not isinstance(run_details, dict):
        raise ToolkitRcPromotionError("signed provenance build identity is absent")
    expected_external = {
        "candidate_version": manifest.candidate_version,
        "source_commit": source_commit,
        "source_date_epoch": source_date_epoch,
    }
    expected_internal = {
        "build_seam": "scripts/toolkit_rc_build.py",
        "release_readiness_seam": "scripts/toolkit_rc_release_readiness.py",
    }
    if (
        build_definition.get("buildType") != BUILD_TYPE
        or build_definition.get("externalParameters") != expected_external
        or build_definition.get("internalParameters") != expected_internal
    ):
        raise ToolkitRcPromotionError("signed provenance build definition differs")
    dependencies = build_definition.get("resolvedDependencies")
    expected_dependencies = {
        (f"git+{SOURCE_REPOSITORY}@{source_commit}", "gitCommit", source_commit),
        ("file:uv.lock", "sha256", uv_lock_sha256),
    }
    actual_dependencies: set[tuple[object, object, object]] = set()
    if isinstance(dependencies, list):
        for dependency in dependencies:
            if not isinstance(dependency, dict) or not isinstance(dependency.get("digest"), dict):
                continue
            digest = dependency["digest"]
            if len(digest) == 1:
                name, value = next(iter(digest.items()))
                actual_dependencies.add((dependency.get("uri"), name, value))
    if actual_dependencies != expected_dependencies:
        raise ToolkitRcPromotionError("signed provenance resolved dependencies differ")
    if run_details.get("builder") != {"id": WORKFLOW_IDENTITY}:
        raise ToolkitRcPromotionError("signed provenance builder identity differs")
    dependency_binding = _shared_binding(manifest, "dependency_lock_evidence")
    expected_byproducts = {
        "toolkit-rc-build-manifest-input.json": _sha256(build_content),
        _coordinate_filename(dependency_binding): dependency_binding.sha256,
    }
    if (
        _subject_matrix(run_details.get("byproducts"), "signed provenance byproducts")
        != expected_byproducts
    ):
        raise ToolkitRcPromotionError("signed provenance byproduct matrix differs")


def promote_toolkit_rc(
    *,
    repository_root: Path,
    artifact_service_url: str,
    artifact_service_token: str,
    publication_id: str,
    expected_receipt_sha256: str,
    expected_candidate_version: str,
    expected_source_commit: str,
    output_path: Path,
) -> Path:
    repository_root = repository_root.resolve()
    output_path = output_path.resolve()
    stable_ready = (repository_root / STABLE_READY_PATH).resolve()
    if output_path == stable_ready:
        raise ToolkitRcPromotionError("promotion writes a candidate, never the authority path")
    if output_path.exists():
        raise ToolkitRcPromotionError("READY candidate output is immutable and must not exist")
    if not artifact_service_token:
        raise ToolkitRcPromotionError("artifact-service token is required")

    client = _ArtifactServiceClient(
        artifact_service_url,
        authorization=None,
        read_bearer_token=artifact_service_token,
    )
    durable = client.get_publication_receipt(publication_id)
    assert durable is not None
    receipt_content, receipt = durable
    if _sha256(receipt_content) != expected_receipt_sha256:
        raise ToolkitRcPromotionError("durable publication receipt digest differs")
    require_production_publication_receipt(receipt)
    if (
        receipt.publication_id != publication_id
        or receipt.candidate_version != expected_candidate_version
        or receipt.source_commit != expected_source_commit
    ):
        raise ToolkitRcPromotionError("operator expectation differs from publication receipt")

    objects: dict[str, bytes] = {}
    for item in receipt.objects:
        content = client.read_artifact(item.object_id)
        if len(content) != item.size_bytes or _sha256(content) != item.sha256:
            raise ToolkitRcPromotionError("remote object readback differs from publication receipt")
        objects[item.coordinate] = content

    def unique_named(filename: str) -> tuple[str, bytes]:
        matches = [
            (coordinate, content)
            for coordinate, content in objects.items()
            if coordinate.rsplit("@sha256:", 1)[0].rsplit("/", 1)[-1] == filename
        ]
        if len(matches) != 1:
            raise ToolkitRcPromotionError(f"publication must contain one {filename}")
        return matches[0]

    _, manifest_content = unique_named("toolkit-rc-receipt-manifest.json")
    _, build_content = unique_named("toolkit-rc-build-manifest-input.json")
    try:
        manifest = ToolkitRcReceiptManifestV1.model_validate(json.loads(manifest_content))
        build = json.loads(build_content)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ToolkitRcPromotionError(f"publication manifests are invalid: {exc}") from exc
    if (
        manifest.candidate_version != receipt.candidate_version
        or build.get("candidate_version") != receipt.candidate_version
        or build.get("source_commit") != receipt.source_commit
        or build.get("source_date_epoch") != receipt.source_date_epoch
        or build.get("reproducible") is not True
    ):
        raise ToolkitRcPromotionError("manifest/build evidence differs from durable receipt")

    published = set(objects)
    for member in manifest.members:
        if member.source_commit != receipt.source_commit:
            raise ToolkitRcPromotionError("toolkit member source commit differs")
        for binding in (
            member.wheel,
            member.sbom,
            member.contract_schema,
            member.contract_asset_index,
            member.dependency_lock_evidence,
            member.slsa_provenance,
            member.sigstore_attestation,
            member.t4_zero_rewrite_receipt,
            member.t4b_typing_closure_receipt,
            member.t5_pre_import_verifier_receipt,
        ):
            content = objects.get(binding.coordinate)
            if (
                content is None
                or len(content) != binding.size_bytes
                or _sha256(content) != binding.sha256
            ):
                raise ToolkitRcPromotionError("manifest binding differs from remote object matrix")
            if not published:
                raise ToolkitRcPromotionError("empty publication object matrix")

    _validate_signed_provenance(
        manifest=manifest,
        build=build,
        build_content=build_content,
        objects=objects,
        source_commit=receipt.source_commit,
        source_date_epoch=receipt.source_date_epoch,
    )

    first = manifest.members[0]
    prerequisite_bindings = (
        first.t4_zero_rewrite_receipt,
        first.t4b_typing_closure_receipt,
        first.t5_pre_import_verifier_receipt,
    )
    for path, binding in zip(PREREQUISITE_PATHS, prerequisite_bindings, strict=True):
        authoritative = (repository_root / path).read_bytes()
        if _sha256(authoritative) != binding.sha256 or len(authoritative) != binding.size_bytes:
            raise ToolkitRcPromotionError(f"authoritative prerequisite drifted: {path}")

    provenance_path = output_path.parent / f".{output_path.name}.provenance"
    bundle_path = output_path.parent / f".{output_path.name}.sigstore"
    provenance_path.write_bytes(objects[first.slsa_provenance.coordinate])
    bundle_path.write_bytes(objects[first.sigstore_attestation.coordinate])
    try:
        try:
            verification = subprocess.run(
                [
                    "sigstore",
                    "verify",
                    "identity",
                    "--bundle",
                    str(bundle_path),
                    "--cert-identity",
                    WORKFLOW_IDENTITY,
                    "--cert-oidc-issuer",
                    OIDC_ISSUER,
                    str(provenance_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ToolkitRcPromotionError(
                f"Sigstore production identity verification is unavailable: {exc}"
            ) from exc
        if verification.returncode != 0:
            raise ToolkitRcPromotionError(
                f"Sigstore production identity verification failed: {verification.stderr.strip()}"
            )
    finally:
        provenance_path.unlink(missing_ok=True)
        bundle_path.unlink(missing_ok=True)

    receipt_digest = _sha256(receipt_content)
    predecessor = ImmutableToolkitArtifactBindingV1(
        coordinate=(f"{client.publication_receipt_url(publication_id)}@sha256:{receipt_digest}"),
        sha256=receipt_digest,
        size_bytes=len(receipt_content),
    )
    ready = ToolkitRcAuthorityReadyReceiptV1(
        receipt_schema_version=1,
        contract_version="alephain.custos.toolkit-rc-authority-receipt.v1",
        status="READY_TOOLKIT_RC",
        ready=True,
        handoff_ready=True,
        candidate_version=receipt.candidate_version,
        source_repository=receipt.source_repository,
        source_commit=receipt.source_commit,
        source_date_epoch=receipt.source_date_epoch,
        publication_receipt_url=client.publication_receipt_url(publication_id),
        publication_receipt_sha256=_sha256(receipt_content),
        publication_receipt_size_bytes=len(receipt_content),
        publication_receipt=receipt,
        toolkit_manifest=manifest,
        toolkit_manifest_sha256=_sha256(manifest_content),
        build_manifest_sha256=_sha256(build_content),
        predecessor_pending_receipt=predecessor,
        production_credentials_used=True,
        production_signature_verified=True,
        remote_publication_verified=True,
        authority_registered=True,
        final_blockers=(),
        handoff_scope="Custos base and Nautilus toolkit RC only",
        loaded=False,
        engine_ready=False,
        runtime_ready=False,
        production_ready=False,
        strategy_release_bom_created=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as output:
        output.write(
            (json.dumps(ready.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode()
        )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-service-url", required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--expected-candidate-version", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    token = os.environ.get("CUSTOS_TOOLKIT_ARTIFACT_SERVICE_TOKEN", "")
    result = promote_toolkit_rc(
        repository_root=arguments.repository_root,
        artifact_service_url=arguments.artifact_service_url,
        artifact_service_token=token,
        publication_id=arguments.publication_id,
        expected_receipt_sha256=arguments.expected_receipt_sha256,
        expected_candidate_version=arguments.expected_candidate_version,
        expected_source_commit=arguments.expected_source_commit,
        output_path=arguments.output,
    )
    print(
        json.dumps(
            {"ready_candidate": str(result), "status": "READY_CANDIDATE_ONLY"}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
