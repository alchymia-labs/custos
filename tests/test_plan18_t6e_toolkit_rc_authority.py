from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from custos_toolkit.contracts import (
    ImmutableToolkitArtifactBindingV1,
    LockedToolkitDependencyV1,
    ToolkitRcAuthorityReceiptV1,
    ToolkitRcAuthorityReceiptV2,
    ToolkitRcMemberRole,
    ToolkitRcMemberV1,
    ToolkitRcOciDescriptorV1,
    ToolkitRcOciPublicationReceiptV1,
    ToolkitRcReceiptManifestV1,
)

from scripts.toolkit_rc_oci import (
    OCI_ARTIFACT_TYPE,
    OCI_CONFIG_MEDIA_TYPE,
    OCI_MANIFEST_MEDIA_TYPE,
    OCI_ROLE_ANNOTATION,
    OCI_SOURCE_COORDINATE_ANNOTATION,
    OCI_TITLE_ANNOTATION,
    OciDescriptor,
    OciRegistryError,
    canonical_json,
    sha256_digest,
)
from scripts.toolkit_rc_promote import (
    OIDC_ISSUER,
    WORKFLOW_IDENTITY,
    ToolkitRcPromotionError,
    promote_toolkit_rc,
    require_production_publication_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_V1 = ROOT / "docs/gateway-contract/v1/toolkit_rc_authority_receipt_v1.schema.json"
SCHEMA = ROOT / "docs/gateway-contract/v2/toolkit_rc_authority_receipt_v2.schema.json"
READY = ROOT / "docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json"
SOURCE_COMMIT = "a" * 40
SOURCE_DATE_EPOCH = 1_704_067_200
VERSION = "0.1.0rc1"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _binding(category: str, filename: str, content: bytes) -> ImmutableToolkitArtifactBindingV1:
    digest = _sha256(content)
    return ImmutableToolkitArtifactBindingV1(
        coordinate=(
            f"artifact://custos/toolkit-rc/{VERSION}/{category}/{filename}@sha256:{digest}"
        ),
        sha256=digest,
        size_bytes=len(content),
    )


def _subject(binding: ImmutableToolkitArtifactBindingV1) -> dict[str, object]:
    filename = binding.coordinate.rsplit("@sha256:", 1)[0].rsplit("/", 1)[-1]
    return {"name": filename, "digest": {"sha256": binding.sha256}}


@dataclass(slots=True)
class FakePromotionClient:
    registry: str
    repository: str
    blobs: dict[str, bytes]
    manifests: dict[str, tuple[str, bytes]]

    def resolve_manifest(self, reference: str) -> str | None:
        value = self.manifests.get(reference)
        return None if value is None else value[0]

    def read_manifest(self, reference: str) -> tuple[bytes, str]:
        value = self.manifests.get(reference)
        if value is None:
            raise OciRegistryError("manifest missing")
        return value[1], value[0]

    def read_blob(self, digest: str) -> bytes:
        try:
            return self.blobs[digest]
        except KeyError as exc:
            raise OciRegistryError("blob missing") from exc


def _promotion_case(
    *, omit_signed_subject: bool = False, drift_build_policy: bool = False
) -> tuple[FakePromotionClient, str]:
    prerequisite_paths = (
        ROOT / "docs/authority/receipts/custos-plan-18-task-4-extraction-receipt.json",
        ROOT / "docs/authority/receipts/custos-plan-18-task-4b-typing-closure-receipt.json",
        ROOT / "docs/authority/receipts/custos-plan-18-task-2-schema-receipt-v2.json",
    )
    dependency_document = {
        "schema_version": "alephain.custos.toolkit-rc-dependency-locks.v1",
        "candidate_version": VERSION,
        "source_commit": SOURCE_COMMIT,
        "uv_lock_sha256": "b" * 64,
        "distributions": {
            "custos-strategy-toolkit": [
                {
                    "name": "pydantic",
                    "version": "2.13.4",
                    "requirement": "pydantic==2.13.4",
                }
            ],
            "custos-strategy-toolkit-nautilus": [
                {
                    "name": "custos-strategy-toolkit",
                    "version": VERSION,
                    "requirement": f"custos-strategy-toolkit=={VERSION}",
                },
                {
                    "name": "nautilus-trader",
                    "version": "1.230.0",
                    "requirement": "nautilus-trader==1.230.0",
                },
            ],
        },
    }
    shared_contents = {
        "contract_schema": b"contract schema\n",
        "contract_asset_index": b"contract index\n",
        "dependency_lock_evidence": _json_bytes(dependency_document),
        "t4_zero_rewrite_receipt": prerequisite_paths[0].read_bytes(),
        "t4b_typing_closure_receipt": prerequisite_paths[1].read_bytes(),
        "t5_pre_import_verifier_receipt": prerequisite_paths[2].read_bytes(),
    }
    shared_bindings = {
        name: _binding(
            "dependencies" if name == "dependency_lock_evidence" else "prerequisites",
            {
                "contract_schema": "toolkit_rc_receipt_manifest_v1.schema.json",
                "contract_asset_index": "strategy-contract-assets-v2.json",
                "dependency_lock_evidence": "toolkit-rc-dependency-locks.json",
                "t4_zero_rewrite_receipt": prerequisite_paths[0].name,
                "t4b_typing_closure_receipt": prerequisite_paths[1].name,
                "t5_pre_import_verifier_receipt": prerequisite_paths[2].name,
            }[name],
            content,
        )
        for name, content in shared_contents.items()
    }
    wheel_contents = {
        ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL: b"base wheel\n",
        ToolkitRcMemberRole.NAUTILUS_WHEEL: b"nautilus wheel\n",
    }
    sbom_contents = {
        ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL: b"base sbom\n",
        ToolkitRcMemberRole.NAUTILUS_WHEEL: b"nautilus sbom\n",
    }
    wheel_bindings = {
        role: _binding("wheels", f"{role.value}.whl", content)
        for role, content in wheel_contents.items()
    }
    sbom_bindings = {
        role: _binding("sbom", f"{role.value}.cdx.json", content)
        for role, content in sbom_contents.items()
    }
    build_wheels: dict[str, dict[str, Any]] = {}
    member_arguments: list[dict[str, Any]] = []
    for role in ToolkitRcMemberRole:
        is_base = role is ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL
        distribution = "custos-strategy-toolkit" if is_base else "custos-strategy-toolkit-nautilus"
        dependencies = (
            (
                LockedToolkitDependencyV1(
                    name="pydantic", version="2.13.4", requirement="pydantic==2.13.4"
                ),
            )
            if is_base
            else (
                LockedToolkitDependencyV1(
                    name="custos-strategy-toolkit",
                    version=VERSION,
                    requirement=f"custos-strategy-toolkit=={VERSION}",
                ),
                LockedToolkitDependencyV1(
                    name="nautilus-trader",
                    version="1.230.0",
                    requirement="nautilus-trader==1.230.0",
                ),
            )
        )
        requires_dist = [dependency.requirement for dependency in dependencies]
        python_requires = ">=3.11" if is_base else "<3.13,>=3.12"
        if drift_build_policy and is_base:
            python_requires = ">=3.12"
        wheel = wheel_bindings[role]
        build_wheels[distribution] = {
            "distribution_name": distribution,
            "version": VERSION,
            "filename": wheel.coordinate.rsplit("@sha256:", 1)[0].rsplit("/", 1)[-1],
            "coordinate": wheel.coordinate,
            "sha256": wheel.sha256,
            "size_bytes": wheel.size_bytes,
            "requires_python": python_requires,
            "requires_dist": requires_dist,
            "top_level_modules": ["custos_toolkit" if is_base else "custos_toolkit_nautilus"],
            "sbom_input": {"path": "ephemeral.json", "sha256": "f" * 64},
        }
        member_arguments.append(
            {
                "role": role,
                "distribution_name": distribution,
                "version": VERSION,
                "python_requires": ">=3.11" if is_base else ">=3.12,<3.13",
                "nautilus_version": None if is_base else "1.230.0",
                "top_level_modules": ("custos_toolkit" if is_base else "custos_toolkit_nautilus",),
                "dependencies": dependencies,
                "wheel": wheel,
                "sbom": sbom_bindings[role],
                "source_repository": "https://github.com/alchymia-labs/custos",
                "source_commit": SOURCE_COMMIT,
            }
        )
    build_document = {
        "schema_version": "alephain.custos.toolkit-rc-build-candidate.v1",
        "status": "BUILD_CANDIDATE_ONLY",
        "source_commit": SOURCE_COMMIT,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "candidate_version": VERSION,
        "builds": {"build-1": build_wheels, "build-2": build_wheels},
        "reproducible": True,
        "registry_accessed": False,
        "ready_receipt_created": False,
        "strategy_release_bom_created": False,
    }
    build_content = _json_bytes(build_document)

    signed_bindings = [*wheel_bindings.values(), *sbom_bindings.values(), *shared_bindings.values()]
    subjects = [_subject(binding) for binding in signed_bindings]
    subjects = list({item["name"]: item for item in subjects}.values())
    subjects.sort(key=lambda item: str(item["name"]))
    if omit_signed_subject:
        subjects.pop()
    dependency_binding = shared_bindings["dependency_lock_evidence"]
    provenance_document = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://custos.the-alephain-guild/build-types/toolkit-rc/v1",
                "externalParameters": {
                    "candidate_version": VERSION,
                    "source_commit": SOURCE_COMMIT,
                    "source_date_epoch": SOURCE_DATE_EPOCH,
                },
                "internalParameters": {
                    "build_seam": "scripts/toolkit_rc_build.py",
                    "release_readiness_seam": "scripts/toolkit_rc_release_readiness.py",
                },
                "resolvedDependencies": [
                    {
                        "uri": (f"git+https://github.com/alchymia-labs/custos@{SOURCE_COMMIT}"),
                        "digest": {"gitCommit": SOURCE_COMMIT},
                    },
                    {"uri": "file:uv.lock", "digest": {"sha256": "b" * 64}},
                ],
            },
            "runDetails": {
                "builder": {"id": WORKFLOW_IDENTITY},
                "metadata": {},
                "byproducts": [
                    {
                        "name": "toolkit-rc-build-manifest-input.json",
                        "digest": {"sha256": _sha256(build_content)},
                    },
                    _subject(dependency_binding),
                ],
            },
        },
    }
    provenance_content = _json_bytes(provenance_document)
    bundle_content = b"production sigstore bundle\n"
    shared_bindings.update(
        {
            "slsa_provenance": _binding("provenance", "toolkit-rc.intoto.json", provenance_content),
            "sigstore_attestation": _binding(
                "attestations", "toolkit-rc-provenance.sigstore.json", bundle_content
            ),
        }
    )
    manifest = ToolkitRcReceiptManifestV1(
        candidate_version=VERSION,
        members=tuple(
            ToolkitRcMemberV1(**arguments, **shared_bindings) for arguments in member_arguments
        ),
    )
    manifest_content = _json_bytes(manifest.model_dump(mode="json"))
    remote_objects: dict[str, bytes] = {
        **{
            binding.coordinate: content
            for binding, content in zip(
                wheel_bindings.values(), wheel_contents.values(), strict=True
            )
        },
        **{
            binding.coordinate: content
            for binding, content in zip(sbom_bindings.values(), sbom_contents.values(), strict=True)
        },
        **{shared_bindings[name].coordinate: content for name, content in shared_contents.items()},
        shared_bindings["slsa_provenance"].coordinate: provenance_content,
        shared_bindings["sigstore_attestation"].coordinate: bundle_content,
    }
    manifest_object = _binding("provenance", "toolkit-rc-receipt-manifest.json", manifest_content)
    build_object = _binding("provenance", "toolkit-rc-build-manifest-input.json", build_content)
    remote_objects[manifest_object.coordinate] = manifest_content
    remote_objects[build_object.coordinate] = build_content
    blobs: dict[str, bytes] = {}
    layers: list[OciDescriptor] = []
    for index, (coordinate, content) in enumerate(sorted(remote_objects.items())):
        filename = coordinate.rsplit("@sha256:", 1)[0].rsplit("/", 1)[-1]
        role = (
            "t6a_manifest"
            if filename == "toolkit-rc-receipt-manifest.json"
            else "t6b_build_manifest"
            if filename == "toolkit-rc-build-manifest-input.json"
            else f"release_object_{index}"
        )
        descriptor = OciDescriptor(
            media_type="application/json",
            digest=sha256_digest(content),
            size=len(content),
            annotations={
                OCI_TITLE_ANNOTATION: filename,
                OCI_ROLE_ANNOTATION: role,
                OCI_SOURCE_COORDINATE_ANNOTATION: coordinate,
            },
        )
        blobs[descriptor.digest] = content
        layers.append(descriptor)
    registry = "registry.example"
    repository = "custos/toolkit"
    config_content = canonical_json(
        {
            "schema_version": "alephain.custos.toolkit-rc-oci-config.v1",
            "candidate_version": VERSION,
            "source_repository": "https://github.com/alchymia-labs/custos",
            "source_commit": SOURCE_COMMIT,
            "source_date_epoch": SOURCE_DATE_EPOCH,
            "registry": registry,
            "repository": repository,
            "tag": VERSION,
            "toolkit_manifest_sha256": _sha256(manifest_content),
            "build_manifest_sha256": _sha256(build_content),
            "production_credentials_used": True,
            "production_signature_verified": True,
            "production_context": {
                "workflow_ref": (
                    "alchymia-labs/custos/.github/workflows/release-toolkit-rc.yml@refs/heads/main"
                ),
                "workflow_identity": WORKFLOW_IDENTITY,
                "oidc_issuer": OIDC_ISSUER,
                "release_environment": "toolkit-rc-release",
                "workflow_run_id": 123,
                "workflow_run_attempt": 1,
            },
        }
    )
    config = OciDescriptor(
        media_type=OCI_CONFIG_MEDIA_TYPE,
        digest=sha256_digest(config_content),
        size=len(config_content),
        annotations={
            OCI_TITLE_ANNOTATION: "toolkit-rc-config.json",
            OCI_ROLE_ANNOTATION: "release_config",
        },
    )
    blobs[config.digest] = config_content
    oci_manifest = canonical_json(
        {
            "schemaVersion": 2,
            "mediaType": OCI_MANIFEST_MEDIA_TYPE,
            "artifactType": OCI_ARTIFACT_TYPE,
            "config": config.document(),
            "layers": [descriptor.document() for descriptor in layers],
            "annotations": {
                "org.opencontainers.image.source": "https://github.com/alchymia-labs/custos",
                "org.opencontainers.image.revision": SOURCE_COMMIT,
                "org.opencontainers.image.version": VERSION,
            },
        }
    )
    digest = sha256_digest(oci_manifest)
    return (
        FakePromotionClient(
            registry=registry,
            repository=repository,
            blobs=blobs,
            manifests={
                VERSION: (digest, oci_manifest),
                digest: (digest, oci_manifest),
            },
        ),
        digest,
    )


def _run_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    omit_signed_subject: bool = False,
    drift_build_policy: bool = False,
) -> Path:
    client, manifest_digest = _promotion_case(
        omit_signed_subject=omit_signed_subject,
        drift_build_policy=drift_build_policy,
    )

    monkeypatch.setattr(
        "scripts.toolkit_rc_promote.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    output = tmp_path / "ready-candidate.json"
    promote_toolkit_rc(
        repository_root=ROOT,
        registry=client.registry,
        repository=client.repository,
        manifest_digest=manifest_digest,
        expected_candidate_version=VERSION,
        expected_source_commit=SOURCE_COMMIT,
        output_path=output,
        registry_client=client,
    )
    return output


def test_v1_stays_historical_and_v2_schema_is_source_generated() -> None:
    historical = json.loads(SCHEMA_V1.read_text(encoding="utf-8"))
    assert historical == ToolkitRcAuthorityReceiptV1.model_json_schema(mode="validation")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema == ToolkitRcAuthorityReceiptV2.model_json_schema(mode="validation")

    assert not READY.exists()


def test_unknown_or_mutated_pending_state_fails_closed() -> None:
    document = {"status": "PENDING_T6E_EXTERNAL_RELEASE", "ready": False}
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV2.model_validate(document)
    document["status"] = "READY_BY_TEST"
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV2.model_validate(document)


def test_nonproduction_publication_cannot_enter_promotion() -> None:
    config = ToolkitRcOciDescriptorV1(
        media_type=OCI_CONFIG_MEDIA_TYPE,
        digest="sha256:" + "a" * 64,
        size_bytes=1,
        title="config.json",
        role="release_config",
        source_coordinate=None,
    )
    layer = ToolkitRcOciDescriptorV1(
        media_type="application/json",
        digest="sha256:" + "b" * 64,
        size_bytes=1,
        title="manifest.json",
        role="t6a_manifest",
        source_coordinate=(
            "artifact://custos/toolkit-rc/0.1.0rc1/provenance/manifest.json@sha256:" + "b" * 64
        ),
    )
    publication = ToolkitRcOciPublicationReceiptV1(
        status="PENDING_T6D_RELEASE_RUNNER",
        candidate_version="0.1.0rc1",
        source_commit="a" * 40,
        source_date_epoch=1_704_067_200,
        registry="registry.example",
        repository="custos/toolkit",
        tag="0.1.0rc1",
        oci_coordinate="registry.example/custos/toolkit@sha256:" + "c" * 64,
        manifest_digest="sha256:" + "c" * 64,
        manifest_size_bytes=1,
        config=config,
        layers=(layer,),
        production_credentials_used=False,
        production_signature_verified=False,
        workflow_ref=None,
        workflow_identity=None,
        oidc_issuer=None,
        release_environment=None,
        workflow_run_id=None,
        workflow_run_attempt=None,
    )
    with pytest.raises(ToolkitRcPromotionError, match="not production"):
        require_production_publication_receipt(publication)


def test_workflow_has_single_candidate_concurrency_and_digest_output() -> None:
    workflow = (ROOT / ".github/workflows/release-toolkit-rc.yml").read_text(encoding="utf-8")
    assert "group: toolkit-rc-${{ inputs.candidate_version }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "oci_coordinate=${{ steps.publish.outputs.oci_coordinate }}" in workflow
    assert "manifest_digest=${{ steps.publish.outputs.manifest_digest }}" in workflow
    assert "packages: write" in workflow
    assert "ARTIFACT_SERVICE" not in workflow
    assert "actions/upload-artifact" not in workflow


def test_independent_promotion_emits_only_a_digest_bound_ready_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _run_promotion(tmp_path, monkeypatch)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["status"] == "READY_TOOLKIT_RC"
    assert document["receipt_schema_version"] == 2
    assert (
        document["predecessor_oci_manifest"]["coordinate"]
        == document["publication_receipt"]["oci_coordinate"]
    )
    assert output != READY
    assert not READY.exists()


def test_promotion_rejects_signed_provenance_with_an_omitted_release_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ToolkitRcPromotionError, match="provenance subject matrix"):
        _run_promotion(tmp_path, monkeypatch, omit_signed_subject=True)


def test_promotion_revalidates_build_policy_instead_of_trusting_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ToolkitRcPromotionError, match="build evidence"):
        _run_promotion(tmp_path, monkeypatch, drift_build_policy=True)
