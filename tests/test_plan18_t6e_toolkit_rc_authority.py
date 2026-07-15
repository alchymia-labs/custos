from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from custos_toolkit.contracts import (
    ImmutableToolkitArtifactBindingV1,
    LockedToolkitDependencyV1,
    ToolkitRcAuthorityReceiptV1,
    ToolkitRcMemberRole,
    ToolkitRcMemberV1,
    ToolkitRcPublicationObjectV1,
    ToolkitRcPublicationReceiptV1,
    ToolkitRcReceiptManifestV1,
)

from scripts.toolkit_rc_promote import (
    OIDC_ISSUER,
    WORKFLOW_IDENTITY,
    ToolkitRcPromotionError,
    promote_toolkit_rc,
    require_production_publication_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/gateway-contract/v1/toolkit_rc_authority_receipt_v1.schema.json"
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


def _promotion_case(
    *, omit_signed_subject: bool = False, drift_build_policy: bool = False
) -> tuple[bytes, ToolkitRcPublicationReceiptV1, dict[str, bytes]]:
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
    publication_objects = tuple(
        ToolkitRcPublicationObjectV1(
            coordinate=coordinate,
            object_id=_sha256(coordinate.encode()),
            sha256=_sha256(content),
            size_bytes=len(content),
        )
        for coordinate, content in sorted(remote_objects.items())
    )
    receipt = ToolkitRcPublicationReceiptV1(
        schema_version="alephain.custos.toolkit-rc-publication-receipt.v1",
        status="PENDING_T6E_AUTHORITY_REGISTRATION",
        ready=False,
        handoff_ready=False,
        candidate_version=VERSION,
        source_repository="https://github.com/alchymia-labs/custos",
        source_commit=SOURCE_COMMIT,
        source_date_epoch=SOURCE_DATE_EPOCH,
        publication_id="publication-production",
        transaction_id="transaction-production",
        publication_atomic=True,
        puback_verified=True,
        readback_verified=True,
        production_credentials_used=True,
        production_signature_verified=True,
        workflow_ref=(
            "alchymia-labs/custos/.github/workflows/release-toolkit-rc.yml@refs/heads/main"
        ),
        workflow_identity=WORKFLOW_IDENTITY,
        oidc_issuer=OIDC_ISSUER,
        release_environment="toolkit-rc-release",
        workflow_run_id=123,
        workflow_run_attempt=1,
        objects=publication_objects,
        authority_registered=False,
    )
    receipt_content = _json_bytes(receipt.model_dump(mode="json"))
    by_object_id = {item.object_id: remote_objects[item.coordinate] for item in publication_objects}
    return receipt_content, receipt, by_object_id


def _run_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    omit_signed_subject: bool = False,
    drift_build_policy: bool = False,
) -> Path:
    receipt_content, receipt, remote_objects = _promotion_case(
        omit_signed_subject=omit_signed_subject,
        drift_build_policy=drift_build_policy,
    )

    class FakePromotionClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def get_publication_receipt(
            self, publication_id: str
        ) -> tuple[bytes, ToolkitRcPublicationReceiptV1]:
            assert publication_id == receipt.publication_id
            return receipt_content, receipt

        def read_artifact(self, object_id: str) -> bytes:
            return remote_objects[object_id]

        def publication_receipt_url(self, publication_id: str) -> str:
            return f"https://artifacts.example/v1/publications/{publication_id}/receipt"

    monkeypatch.setattr("scripts.toolkit_rc_promote._ArtifactServiceClient", FakePromotionClient)
    monkeypatch.setattr(
        "scripts.toolkit_rc_promote.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    output = tmp_path / "ready-candidate.json"
    promote_toolkit_rc(
        repository_root=ROOT,
        artifact_service_url="https://artifacts.example",
        artifact_service_token="production-reader",
        publication_id=receipt.publication_id,
        expected_receipt_sha256=_sha256(receipt_content),
        expected_candidate_version=VERSION,
        expected_source_commit=SOURCE_COMMIT,
        output_path=output,
    )
    return output


def test_authority_union_schema_is_source_generated_without_repo_receipt() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema == ToolkitRcAuthorityReceiptV1.model_json_schema(mode="validation")
    assert schema["discriminator"]["propertyName"] == "status"

    assert not READY.exists()


def test_unknown_or_mutated_pending_state_fails_closed() -> None:
    document = {"status": "PENDING_T6E_EXTERNAL_RELEASE", "ready": False}
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV1.model_validate(document)
    document["status"] = "READY_BY_TEST"
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV1.model_validate(document)


def test_nonproduction_publication_cannot_enter_promotion() -> None:
    coordinate = "artifact://custos/toolkit-rc/0.1.0rc1/wheels/base@sha256:" + "a" * 64
    publication = ToolkitRcPublicationReceiptV1(
        schema_version="alephain.custos.toolkit-rc-publication-receipt.v1",
        status="PENDING_T6C_PUBLICATION_VERIFIED",
        ready=False,
        handoff_ready=False,
        candidate_version="0.1.0rc1",
        source_repository="https://github.com/alchymia-labs/custos",
        source_commit="a" * 40,
        source_date_epoch=1_704_067_200,
        publication_id="publication-local",
        transaction_id="transaction-local",
        publication_atomic=True,
        puback_verified=True,
        readback_verified=True,
        production_credentials_used=False,
        production_signature_verified=False,
        workflow_ref=None,
        workflow_identity=None,
        oidc_issuer=None,
        release_environment=None,
        workflow_run_id=None,
        workflow_run_attempt=None,
        objects=(
            ToolkitRcPublicationObjectV1(
                coordinate=coordinate,
                object_id=__import__("hashlib").sha256(coordinate.encode()).hexdigest(),
                sha256="a" * 64,
                size_bytes=1,
            ),
        ),
        authority_registered=False,
    )
    with pytest.raises(ToolkitRcPromotionError, match="not production"):
        require_production_publication_receipt(publication)


def test_workflow_has_single_candidate_concurrency_and_durable_locator_output() -> None:
    workflow = (ROOT / ".github/workflows/release-toolkit-rc.yml").read_text(encoding="utf-8")
    assert "group: toolkit-rc-${{ inputs.candidate_version }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "durable_receipt_url=${{ steps.publish.outputs.durable_receipt_url }}" in workflow
    assert "actions/upload-artifact" not in workflow


def test_independent_promotion_emits_only_a_digest_bound_ready_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _run_promotion(tmp_path, monkeypatch)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["status"] == "READY_TOOLKIT_RC"
    assert document["predecessor_pending_receipt"]["coordinate"].endswith(
        "@sha256:" + document["publication_receipt_sha256"]
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
