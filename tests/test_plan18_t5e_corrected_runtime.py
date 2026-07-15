from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from custos_toolkit.contracts.strategy_execution import canonical_json_bytes

from custos.artifacts.archive import QuarantinedWheel
from custos.artifacts.corrected_runtime import (
    ArtifactRuntimeActivationError,
    ArtifactRuntimeBlocked,
    CorrectedArtifactRuntime,
    CorrectedArtifactRuntimeConfig,
    CorrectedRuntimeCapability,
    CorrectedVerifiedMember,
    verify_full_bom_member_files,
)
from custos.artifacts.errors import ArtifactVerificationError
from custos.artifacts.policy import (
    ArchiveLimitsV1,
    ReleaseTrustPolicyV1,
    SignedReleaseTrustPolicyEnvelopeV1,
    SigstoreIdentityV1,
    canonical_policy_bytes,
    release_policy_signature_message,
)
from custos.artifacts.production_pre_import import RunnerLocalArtifactVerificationConfig
from custos.artifacts.verifier import SigstoreVerificationEvidence
from custos.contracts.crucible_runner_command import CrucibleRunnerDeploymentCommandV1

ROOT = Path(__file__).resolve().parents[1]
COMMAND_GOLDEN = (
    ROOT
    / "docs/authority/vendor/crucible-plan-89/docs/authority/golden/"
    "crucible-runner-deployment-command-v1.json"
)
NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _command_and_statement(bundle_bytes: bytes) -> tuple[object, bytes]:
    fixture = json.loads(COMMAND_GOLDEN.read_text(encoding="utf-8"))
    envelope = fixture["signed_envelope"]
    event = json.loads(_decode(envelope["event_bytes"]))
    command = CrucibleRunnerDeploymentCommandV1.model_validate(event["payload"])
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://the-alephain-guild.dev/attestation/strategy-release/v1",
        "subject": [
            {
                "name": "strategy-release-bom-v1",
                "digest": {"sha256": command.release_bom_digest},
            },
            {
                "name": "strategy-artifact",
                "digest": {"sha256": command.artifact_ref.artifact_sha256},
            },
            {
                "name": "strategy-manifest-v1",
                "digest": {"sha256": command.artifact_ref.manifest_sha256},
            },
        ],
        "predicate": {
            "producer_repository": command.artifact_ref.source_repository,
            "producer_commit": command.artifact_ref.source_commit,
        },
    }
    statement_bytes = canonical_json_bytes(statement)
    statement_digest = hashlib.sha256(statement_bytes).hexdigest()
    bundle_digest = hashlib.sha256(bundle_bytes).hexdigest()
    attestation = copy.deepcopy(command.artifact_attestation_ref)
    attestation.update(
        {
            "statement_coordinate": f"fixture://statement@sha256:{statement_digest}",
            "statement_sha256": statement_digest,
            "bundle_coordinate": f"fixture://bundle@sha256:{bundle_digest}",
            "bundle_sha256": bundle_digest,
        }
    )
    evidence_digest = "e" * 64
    evidence = copy.deepcopy(command.artifact_evidence)
    evidence.update(
        {
            "statement_digest": statement_digest,
            "attestation_ref_digest": hashlib.sha256(
                canonical_json_bytes(attestation)
            ).hexdigest(),
            "bundle_sha256": bundle_digest,
            "artifact_evidence_digest": evidence_digest,
        }
    )
    evidence["sigstore_proof"]["bundle_sha256"] = bundle_digest
    acceptance = copy.deepcopy(command.artifact_acceptance_receipt)
    acceptance.update(
        {
            "artifact_evidence_digest": evidence_digest,
            "receipt_digest": "f" * 64,
        }
    )
    command = command.model_copy(
        update={
            "artifact_attestation_ref": attestation,
            "artifact_evidence": evidence,
            "artifact_acceptance_receipt": acceptance,
            "artifact_evidence_digest": evidence_digest,
        }
    )
    return command, statement_bytes


def _signed_policy(
    *,
    command,
    trusted_root_bytes: bytes,
    authority_key: Ed25519PrivateKey,
) -> tuple[bytes, str]:
    claims = command.artifact_evidence["signed_producer_claims"]
    proof = command.artifact_evidence["sigstore_proof"]
    policy = ReleaseTrustPolicyV1(
        policy_id="runner-local-release-policy",
        version=7,
        not_before=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        sigstore_trusted_root_sha256=hashlib.sha256(trusted_root_bytes).hexdigest(),
        accepted_identities=(
            SigstoreIdentityV1(
                issuer=proof["issuer"],
                workflow_identity=claims["workflow_identity"],
                source_repository=claims["producer_repository"],
            ),
        ),
        require_transparency_log=True,
        archive_limits=ArchiveLimitsV1(),
    )
    policy_bytes = canonical_policy_bytes(policy)
    envelope = SignedReleaseTrustPolicyEnvelopeV1(
        policy_bytes=_encode(policy_bytes),
        signature_key_id="runner-policy-authority",
        signature=_encode(authority_key.sign(release_policy_signature_message(policy_bytes))),
    )
    envelope_bytes = json.dumps(
        envelope.model_dump(mode="json"), separators=(",", ":")
    ).encode()
    return envelope_bytes, hashlib.sha256(policy_bytes).hexdigest()


class _State:
    def __init__(self, command, events: list[str]) -> None:
        self.command = command
        self.events = events
        self.fail_active = False

    async def load_durable_desired_command(self, deployment_instance_id: UUID):
        self.events.append("load_desired")
        if self.command is None:
            raise KeyError(str(deployment_instance_id))
        return SimpleNamespace(command=self.command)

    async def stage_artifact_activation(self, **kwargs) -> None:
        del kwargs
        self.events.append("stage_activation")

    async def mark_artifact_activation_active(self, **kwargs) -> None:
        del kwargs
        self.events.append("commit_activation")
        if self.fail_active:
            raise OSError("simulated SQLite commit failure")

    async def quarantine_artifact_activation(self, **kwargs) -> None:
        del kwargs
        self.events.append("quarantine_activation")


class _Members:
    def __init__(self, root: Path, events: list[str]) -> None:
        self.root = root
        self.events = events

    def verify(self, release_bom, member_paths):
        self.events.append("verify_members")
        assert isinstance(release_bom, dict)
        assert "members" in release_bom
        wheel = self.root / "strategy.whl"
        wheel.write_bytes(b"verified-wheel")
        return (
            CorrectedVerifiedMember(
                role="strategy_wheel",
                name="strategy.whl",
                media_type="application/zip",
                size_bytes=wheel.stat().st_size,
                sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
                path=wheel,
            ),
        )


class _Sigstore:
    capability_id = "test-corrected-sigstore"

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def verify(self, request):
        self.events.append("verify_sigstore")
        identity = request.accepted_identities[0]
        return SigstoreVerificationEvidence(
            verifier_capability_id=self.capability_id,
            bundle_sha256=hashlib.sha256(request.bundle_path.read_bytes()).hexdigest(),
            trusted_root_sha256=hashlib.sha256(request.trusted_root_bytes).hexdigest(),
            issuer=identity.issuer,
            workflow_identity=identity.workflow_identity,
            source_repository=identity.source_repository,
            verified_subjects=request.required_subjects,
            transparency_log_verified=True,
        )


class _Quarantiner:
    def __init__(self, root: Path, events: list[str]) -> None:
        self.root = root
        self.events = events

    def quarantine(self, **kwargs) -> QuarantinedWheel:
        del kwargs
        self.events.append("quarantine")
        self.root.mkdir(parents=True)
        (self.root / "team").mkdir()
        (self.root / "team" / "adapter.py").write_text("class Runtime: pass\n")
        return QuarantinedWheel(
            root=self.root,
            verified_entry_point="team.adapter:Runtime",
            archive_member_count=2,
            total_uncompressed_bytes=20,
        )


class _Loader:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.config = None

    def load(self, *, activation_root, entry_point, effective_config, execution_context):
        assert activation_root.is_dir()
        assert entry_point == "team.adapter:Runtime"
        assert execution_context.deployment_instance_id
        self.config = effective_config
        self.events.append("import")
        return object()


def _runtime(tmp_path: Path, *, command, capability, events: list[str]):
    bundle = tmp_path / "bundle.sigstore.json"
    bundle.write_bytes(b"detached-bundle")
    if command is None:
        command, statement_bytes = _command_and_statement(bundle.read_bytes())
    else:
        _, statement_bytes = _command_and_statement(bundle.read_bytes())
    authority_key = Ed25519PrivateKey.generate()
    trusted_root = b'{"trusted-root":"runner-local"}'
    policy_envelope, policy_digest = _signed_policy(
        command=command,
        trusted_root_bytes=trusted_root,
        authority_key=authority_key,
    )
    config = CorrectedArtifactRuntimeConfig(
        local_verification=RunnerLocalArtifactVerificationConfig(
            signed_policy_envelope_bytes=policy_envelope,
            policy_authority_key_id="runner-policy-authority",
            policy_authority_public_key=authority_key.public_key(),
            sigstore_trusted_root_bytes=trusted_root,
            quarantine_parent=(tmp_path / "quarantine").resolve(),
        ),
        activation_parent=(tmp_path / "active").resolve(),
        capability=capability,
    )
    state = _State(command, events)
    runtime = CorrectedArtifactRuntime(
        state=state,
        config=config,
        member_verifier=_Members(tmp_path, events),
        sigstore_verifier=_Sigstore(events),
        quarantiner=_Quarantiner(tmp_path / "quarantine" / "prepared", events),
    )
    return runtime, state, bundle, statement_bytes, policy_digest


@pytest.mark.asyncio
async def test_prepare_requires_t4_durable_desired_before_verification_or_import(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, state, bundle, statement, _ = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.prepared_blocked(),
        events=events,
    )
    state.command = None

    with pytest.raises(KeyError):
        await runtime.prepare(
            deployment_instance_id=command.deployment_instance_id,
            release_statement_bytes=statement,
            detached_bundle_path=bundle,
            member_paths={},
            verified_at=NOW,
        )

    assert events == ["load_desired"]


@pytest.mark.asyncio
async def test_prepare_verifies_corrected_owner_objects_and_deep_freezes_context(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, _, bundle, statement, _ = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.prepared_blocked(),
        events=events,
    )

    prepared = await runtime.prepare(
        deployment_instance_id=command.deployment_instance_id,
        release_statement_bytes=statement,
        detached_bundle_path=bundle,
        member_paths={},
        verified_at=NOW,
    )

    assert prepared.receipt.schema_version == 2
    assert prepared.receipt.release_bom == command.release_bom
    assert prepared.receipt.artifact_ref.schema_version == 2
    assert isinstance(prepared.effective_config, MappingProxyType)
    assert isinstance(prepared.effective_config["risk"], MappingProxyType)
    assert events == ["load_desired", "verify_members", "verify_sigstore", "quarantine"]


@pytest.mark.asyncio
async def test_runner_local_policy_reuse_is_rejected_before_bundle_verification(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, state, bundle, statement, policy_digest = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.prepared_blocked(),
        events=events,
    )
    evidence = copy.deepcopy(command.artifact_evidence)
    evidence["local_policy_evaluation"]["policy_digest"] = policy_digest
    state.command = command.model_copy(update={"artifact_evidence": evidence})

    with pytest.raises(ArtifactVerificationError, match="independent"):
        await runtime.prepare(
            deployment_instance_id=command.deployment_instance_id,
            release_statement_bytes=statement,
            detached_bundle_path=bundle,
            member_paths={},
            verified_at=NOW,
        )

    assert events == ["load_desired"]


def test_full_bom_member_verifier_rejects_member_mismatch(tmp_path: Path) -> None:
    command, _ = _command_and_statement(b"detached-bundle")
    first = command.release_bom["members"][0]
    path = tmp_path / first["name"]
    path.write_bytes(b"wrong-member-bytes")

    with pytest.raises(ArtifactVerificationError, match="member"):
        verify_full_bom_member_files(command.release_bom, {first["name"]: path})


@pytest.mark.asyncio
async def test_blocked_external_receipts_never_activate_or_import(tmp_path: Path) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, _, bundle, statement, _ = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.prepared_blocked(),
        events=events,
    )
    prepared = await runtime.prepare(
        deployment_instance_id=command.deployment_instance_id,
        release_statement_bytes=statement,
        detached_bundle_path=bundle,
        member_paths={},
        verified_at=NOW,
    )
    loader = _Loader(events)

    with pytest.raises(ArtifactRuntimeBlocked, match="PS-specific bundle"):
        await runtime.activate(prepared, loader=loader)

    assert "stage_activation" not in events
    assert "import" not in events


@pytest.mark.asyncio
async def test_activation_commit_crash_never_imports_and_quarantines(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, state, bundle, statement, _ = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.from_external_receipts(
            ps_bundle_receipt_digest="1" * 64,
            crucible_c6_receipt_digest="2" * 64,
        ),
        events=events,
    )
    prepared = await runtime.prepare(
        deployment_instance_id=command.deployment_instance_id,
        release_statement_bytes=statement,
        detached_bundle_path=bundle,
        member_paths={},
        verified_at=NOW,
    )
    state.fail_active = True
    loader = _Loader(events)

    with pytest.raises(ArtifactRuntimeActivationError, match="durable activation"):
        await runtime.activate(prepared, loader=loader)

    assert events[-3:] == [
        "stage_activation",
        "commit_activation",
        "quarantine_activation",
    ]
    assert "import" not in events


@pytest.mark.asyncio
async def test_verified_activation_imports_only_after_durable_active_commit(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    command, _ = _command_and_statement(b"detached-bundle")
    runtime, _, bundle, statement, _ = _runtime(
        tmp_path,
        command=command,
        capability=CorrectedRuntimeCapability.from_external_receipts(
            ps_bundle_receipt_digest="1" * 64,
            crucible_c6_receipt_digest="2" * 64,
        ),
        events=events,
    )
    prepared = await runtime.prepare(
        deployment_instance_id=command.deployment_instance_id,
        release_statement_bytes=statement,
        detached_bundle_path=bundle,
        member_paths={},
        verified_at=NOW,
    )
    loader = _Loader(events)

    activated = await runtime.activate(prepared, loader=loader)

    assert activated.strategy is not None
    assert events[-3:] == ["stage_activation", "commit_activation", "import"]
    assert isinstance(loader.config, MappingProxyType)
