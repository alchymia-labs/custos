from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from custos_toolkit.contracts import (
    ImmutableToolkitArtifactBindingV1,
    LockedToolkitDependencyV1,
    ToolkitRcMemberRole,
    ToolkitRcMemberV1,
    ToolkitRcReceiptManifestV1,
)

from scripts.toolkit_rc_publish import (
    ArtifactCoordinateExistsError,
    ArtifactPublicationError,
    publish_toolkit_rc_candidate,
)

SOURCE_COMMIT = "a" * 40
SOURCE_DATE_EPOCH = 1_704_067_200
OBJECT_FIELDS = (
    "wheel",
    "sbom",
    "contract_schema",
    "contract_asset_index",
    "dependency_lock_evidence",
    "slsa_provenance",
    "sigstore_attestation",
    "t4_zero_rewrite_receipt",
    "t4b_typing_closure_receipt",
    "t5_pre_import_verifier_receipt",
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateInputs:
    manifest_path: Path
    build_manifest_path: Path
    object_sources: dict[str, Path]
    candidate_version: str


def _binding(
    *,
    root: Path,
    version: str,
    role: ToolkitRcMemberRole,
    field_name: str,
    content: bytes,
) -> tuple[ImmutableToolkitArtifactBindingV1, Path]:
    path = root / "objects" / f"{role.value}-{field_name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    digest = _sha256(content)
    coordinate = f"artifact://custos/toolkit-rc/{version}/{role.value}/{field_name}@sha256:{digest}"
    return (
        ImmutableToolkitArtifactBindingV1(
            coordinate=coordinate,
            sha256=digest,
            size_bytes=len(content),
        ),
        path,
    )


def _candidate_inputs(root: Path, version: str) -> CandidateInputs:
    root.mkdir(parents=True, exist_ok=True)
    members: list[ToolkitRcMemberV1] = []
    object_sources: dict[str, Path] = {}
    wheel_documents: dict[str, dict[str, Any]] = {}

    for role in ToolkitRcMemberRole:
        is_base = role is ToolkitRcMemberRole.BASE_CONTRACTS_WHEEL
        distribution = "custos-strategy-toolkit" if is_base else "custos-strategy-toolkit-nautilus"
        bindings: dict[str, ImmutableToolkitArtifactBindingV1] = {}
        for field_name in OBJECT_FIELDS:
            content = f"{version}:{role.value}:{field_name}\n".encode()
            binding, path = _binding(
                root=root,
                version=version,
                role=role,
                field_name=field_name,
                content=content,
            )
            bindings[field_name] = binding
            object_sources[binding.coordinate] = path

        wheel = bindings["wheel"]
        requires_dist = (
            ["pydantic==2.12.5"]
            if is_base
            else [
                f"custos-strategy-toolkit=={version}",
                "nautilus-trader==1.230.0",
            ]
        )
        wheel_documents[distribution] = {
            "distribution_name": distribution,
            "version": version,
            "filename": Path(object_sources[wheel.coordinate]).name,
            "coordinate": wheel.coordinate,
            "sha256": wheel.sha256,
            "size_bytes": wheel.size_bytes,
            "requires_python": ">=3.11" if is_base else "<3.13,>=3.12",
            "requires_dist": requires_dist,
            "top_level_modules": ["custos_toolkit" if is_base else "custos_toolkit_nautilus"],
            "sbom_input": {"path": "ephemeral.json", "sha256": "f" * 64},
        }
        dependencies = (
            (
                LockedToolkitDependencyV1(
                    name="pydantic",
                    version="2.12.5",
                    requirement="pydantic==2.12.5",
                ),
            )
            if is_base
            else (
                LockedToolkitDependencyV1(
                    name="custos-strategy-toolkit",
                    version=version,
                    requirement=f"custos-strategy-toolkit=={version}",
                ),
                LockedToolkitDependencyV1(
                    name="nautilus-trader",
                    version="1.230.0",
                    requirement="nautilus-trader==1.230.0",
                ),
            )
        )
        members.append(
            ToolkitRcMemberV1(
                role=role,
                distribution_name=distribution,
                version=version,
                python_requires=">=3.11" if is_base else ">=3.12,<3.13",
                nautilus_version=None if is_base else "1.230.0",
                top_level_modules=("custos_toolkit" if is_base else "custos_toolkit_nautilus",),
                dependencies=dependencies,
                source_repository="https://github.com/alchymia-labs/custos",
                source_commit=SOURCE_COMMIT,
                **bindings,
            )
        )

    manifest = ToolkitRcReceiptManifestV1(
        candidate_version=version,
        members=tuple(members),
    )
    manifest_path = root / "toolkit-rc-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    build_manifest_path = root / "toolkit-rc-build-manifest-input.json"
    build_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "alephain.custos.toolkit-rc-build-candidate.v1",
                "status": "BUILD_CANDIDATE_ONLY",
                "source_commit": SOURCE_COMMIT,
                "source_date_epoch": SOURCE_DATE_EPOCH,
                "candidate_version": version,
                "builds": {
                    "build-1": wheel_documents,
                    "build-2": wheel_documents,
                },
                "reproducible": True,
                "registry_accessed": False,
                "ready_receipt_created": False,
                "strategy_release_bom_created": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return CandidateInputs(
        manifest_path=manifest_path,
        build_manifest_path=build_manifest_path,
        object_sources=object_sources,
        candidate_version=version,
    )


@dataclass(slots=True)
class FakeArtifactState:
    objects: dict[str, tuple[str, str, bytes]] = field(default_factory=dict)
    transactions: dict[str, dict[str, Any]] = field(default_factory=dict)
    transaction_count: int = 0
    put_count: int = 0
    fail_put_at: int | None = None
    omit_puback: bool = False
    drift_readback: bool = False
    drop_commit_response: bool = False
    drift_receipt: bool = False
    receipts: dict[str, bytes] = field(default_factory=dict)


class FakeArtifactHandler(BaseHTTPRequestHandler):
    server: FakeArtifactServer

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def _response(self, status: int, document: dict[str, Any] | None = None) -> None:
        content = b"" if document is None else json.dumps(document).encode()
        self.send_response(status)
        if content:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if content:
            self.wfile.write(content)

    def do_HEAD(self) -> None:  # noqa: N802
        object_id = self.path.rsplit("/", 1)[-1]
        self._response(200 if object_id in self.server.state.objects else 404)

    def do_GET(self) -> None:  # noqa: N802
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["v1", "publications"] and parts[3] == "receipt":
            content = self.server.state.receipts.get(parts[2])
            if content is None:
                self._response(404)
                return
            if self.server.state.drift_receipt:
                document = json.loads(content)
                document["source_commit"] = "0" * 40
                content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        object_id = self.path.rsplit("/", 1)[-1]
        stored = self.server.state.objects.get(object_id)
        if stored is None:
            self._response(404)
            return
        content = b"digest drift" if self.server.state.drift_readback else stored[2]
        self.send_response(200)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        state = self.server.state
        if self.path == "/v1/publications":
            request = self._json_body()
            state.transaction_count += 1
            transaction_id = f"tx-{state.transaction_count}"
            publication_id = f"publication-{transaction_id}"
            state.transactions[transaction_id] = {
                "expected": {item["object_id"]: item for item in request["objects"]},
                "staged": {},
                "request": request,
                "publication_id": publication_id,
            }
            self._response(
                201,
                {
                    "accepted": True,
                    "atomic": True,
                    "transaction_id": transaction_id,
                    "publication_id": publication_id,
                },
            )
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["v1", "publications"]:
            transaction_id = parts[2]
            transaction = state.transactions[transaction_id]
            if set(transaction["staged"]) != set(transaction["expected"]):
                self._response(409, {"error": "partial transaction"})
                return
            committed = dict(state.objects)
            committed.update(transaction["staged"])
            state.objects = committed
            objects = [
                {
                    "coordinate": coordinate,
                    "object_id": object_id,
                    "sha256": digest,
                }
                for object_id, (coordinate, digest, _) in sorted(transaction["staged"].items())
            ]
            response: dict[str, Any] = {
                "publication_id": transaction["publication_id"],
                "objects": objects,
            }
            if not state.omit_puback:
                response["puback"] = True
            request = transaction["request"]
            context = request["production_context"]
            receipt = {
                "schema_version": "alephain.custos.toolkit-rc-publication-receipt.v1",
                "status": (
                    "PENDING_T6E_AUTHORITY_REGISTRATION"
                    if context is not None
                    else "PENDING_T6C_PUBLICATION_VERIFIED"
                ),
                "ready": False,
                "handoff_ready": False,
                "candidate_version": request["candidate_version"],
                "source_repository": request["source_repository"],
                "source_commit": request["source_commit"],
                "source_date_epoch": request["source_date_epoch"],
                "publication_id": transaction["publication_id"],
                "transaction_id": transaction_id,
                "publication_atomic": True,
                "puback_verified": True,
                "readback_verified": True,
                "production_credentials_used": context is not None,
                "production_signature_verified": context is not None,
                "workflow_ref": None if context is None else context["workflow_ref"],
                "workflow_identity": None if context is None else context["workflow_identity"],
                "oidc_issuer": None if context is None else context["oidc_issuer"],
                "release_environment": None if context is None else context["release_environment"],
                "workflow_run_id": None if context is None else context["workflow_run_id"],
                "workflow_run_attempt": (
                    None if context is None else context["workflow_run_attempt"]
                ),
                "objects": [
                    {**item, "size_bytes": transaction["expected"][item["object_id"]]["size_bytes"]}
                    for item in objects
                ],
                "authority_registered": False,
            }
            state.receipts[transaction["publication_id"]] = (
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            ).encode()
            if state.drop_commit_response:
                state.drop_commit_response = False
                self.close_connection = True
                return
            self._response(200, response)
            return
        self._response(404)

    def do_PUT(self) -> None:  # noqa: N802
        state = self.server.state
        state.put_count += 1
        if state.fail_put_at == state.put_count:
            state.fail_put_at = None
            self._response(503, {"error": "injected partial failure"})
            return
        parts = self.path.strip("/").split("/")
        if len(parts) != 5 or parts[:2] != ["v1", "publications"]:
            self._response(404)
            return
        transaction = state.transactions[parts[2]]
        object_id = parts[4]
        expected = transaction["expected"][object_id]
        length = int(self.headers["Content-Length"])
        content = self.rfile.read(length)
        transaction["staged"][object_id] = (
            expected["coordinate"],
            expected["sha256"],
            content,
        )
        self._response(
            201,
            {
                "ack": True,
                "coordinate": expected["coordinate"],
                "object_id": object_id,
                "sha256": expected["sha256"],
            },
        )


class FakeArtifactServer(ThreadingHTTPServer):
    state: FakeArtifactState


@contextmanager
def _artifact_service(
    state: FakeArtifactState | None = None,
) -> Iterator[tuple[str, FakeArtifactState]]:
    active_state = state or FakeArtifactState()
    server = FakeArtifactServer(("127.0.0.1", 0), FakeArtifactHandler)
    server.state = active_state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", active_state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _publish(
    inputs: CandidateInputs,
    service_url: str,
    pending_path: Path,
):
    return publish_toolkit_rc_candidate(
        manifest_path=inputs.manifest_path,
        build_manifest_path=inputs.build_manifest_path,
        object_sources=inputs.object_sources,
        artifact_service_url=service_url,
        pending_receipt_path=pending_path,
    )


def test_atomic_publication_is_pending_only_and_rc_coordinate_cannot_overwrite(
    tmp_path: Path,
) -> None:
    rc1 = _candidate_inputs(tmp_path / "rc1", "0.1.0rc1")
    rc2 = _candidate_inputs(tmp_path / "rc2", "0.1.0rc2")
    with _artifact_service() as (service_url, state):
        pending_rc1 = tmp_path / "pending-rc1.json"
        evidence = _publish(rc1, service_url, pending_rc1)

        document = json.loads(pending_rc1.read_text(encoding="utf-8"))
        assert evidence.candidate_version == "0.1.0rc1"
        assert document["status"] == "PENDING_T6D_RELEASE_RUNNER"
        assert document["ready"] is False
        assert document["publication_atomic"] is True
        assert document["puback_verified"] is True
        assert document["readback_verified"] is True
        assert document["production_credentials_used"] is False
        assert document["production_attestation_verified"] is False
        assert document["durable_receipt_url"].endswith(
            f"/v1/publications/{evidence.publication_id}/receipt"
        )
        assert document["durable_receipt_sha256"] == _sha256(
            state.receipts[evidence.publication_id]
        )
        assert state.objects

        with pytest.raises(ArtifactCoordinateExistsError):
            _publish(rc1, service_url, tmp_path / "must-not-exist.json")
        assert not (tmp_path / "must-not-exist.json").exists()

        rc2_evidence = _publish(rc2, service_url, tmp_path / "pending-rc2.json")
        assert rc2_evidence.candidate_version == "0.1.0rc2"


def test_partial_failure_is_invisible_and_same_candidate_can_retry(tmp_path: Path) -> None:
    inputs = _candidate_inputs(tmp_path / "inputs", "0.1.0rc1")
    state = FakeArtifactState(fail_put_at=2)
    with _artifact_service(state) as (service_url, _):
        failed_pending = tmp_path / "failed-pending.json"
        with pytest.raises(ArtifactPublicationError, match="stage"):
            _publish(inputs, service_url, failed_pending)
        assert state.objects == {}
        assert not failed_pending.exists()

        retried = _publish(inputs, service_url, tmp_path / "retry-pending.json")
        assert retried.candidate_version == "0.1.0rc1"
        assert state.objects


@pytest.mark.parametrize("failure", ["missing_attestation", "missing_puback", "digest_drift"])
def test_incomplete_or_unverified_publication_never_writes_pending_or_ready_receipt(
    tmp_path: Path,
    failure: str,
) -> None:
    inputs = _candidate_inputs(tmp_path / failure, "0.1.0rc1")
    state = FakeArtifactState(
        omit_puback=failure == "missing_puback",
        drift_readback=failure == "digest_drift",
    )
    if failure == "missing_attestation":
        attestation = next(
            coordinate
            for coordinate in inputs.object_sources
            if "/sigstore_attestation@sha256:" in coordinate
        )
        del inputs.object_sources[attestation]

    pending_path = tmp_path / f"{failure}-pending.json"
    with _artifact_service(state) as (service_url, _):
        with pytest.raises(ArtifactPublicationError):
            _publish(inputs, service_url, pending_path)
    assert not pending_path.exists()
    assert not (tmp_path / "custos-plan-18-task-6-toolkit-rc-receipt.json").exists()


def test_contract_cli_is_local_only(tmp_path: Path) -> None:
    inputs = _candidate_inputs(tmp_path / "inputs", "0.1.0rc1")
    with pytest.raises(ArtifactPublicationError, match="loopback"):
        _publish(
            inputs,
            "https://registry.example.invalid",
            tmp_path / "must-not-exist.json",
        )


def test_commit_unknown_recovers_from_immutable_publication_receipt(tmp_path: Path) -> None:
    inputs = _candidate_inputs(tmp_path / "inputs", "0.1.0rc1")
    state = FakeArtifactState(drop_commit_response=True)
    with _artifact_service(state) as (service_url, _):
        pending = tmp_path / "recovered.json"
        evidence = _publish(inputs, service_url, pending)
    assert pending.is_file()
    assert evidence.publication_id in state.receipts


def test_durable_receipt_drift_fails_before_pending_evidence(tmp_path: Path) -> None:
    inputs = _candidate_inputs(tmp_path / "inputs", "0.1.0rc1")
    state = FakeArtifactState(drift_receipt=True)
    pending = tmp_path / "must-not-exist.json"
    with _artifact_service(state) as (service_url, _):
        with pytest.raises(ArtifactPublicationError, match="durable publication receipt"):
            _publish(inputs, service_url, pending)
    assert not pending.exists()
