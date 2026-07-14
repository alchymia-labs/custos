from __future__ import annotations

import hashlib
import json

import pytest

from custos.artifacts.bom import verify_release_bom_and_members
from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError
from tests._artifact_verifier_fixtures import build_artifact_fixture


def test_full_bom_and_every_command_bound_member_are_verified(tmp_path) -> None:
    fixture = build_artifact_fixture(tmp_path)

    verified = verify_release_bom_and_members(
        bom_bytes=fixture.bom_bytes,
        command_binding=fixture.command,
        member_paths=fixture.member_paths,
    )

    assert verified.release_bom_digest == fixture.command.release_bom_digest
    assert len(verified.members) == len(fixture.command.release_bom_members)
    assert {member.name for member in verified.members} == set(fixture.member_paths)


@pytest.mark.parametrize("case", ["bom_byte", "member_byte", "missing", "extra", "symlink"])
def test_bom_or_member_drift_fails_closed(tmp_path, case: str) -> None:
    fixture = build_artifact_fixture(tmp_path)
    bom_bytes = fixture.bom_bytes
    paths = dict(fixture.member_paths)

    if case == "bom_byte":
        bom_bytes += b"\n"
    elif case == "member_byte":
        path = next(iter(paths.values()))
        path.write_bytes(path.read_bytes() + b"drift")
    elif case == "missing":
        paths.pop(next(iter(paths)))
    elif case == "extra":
        extra = tmp_path / "unexpected.bin"
        extra.write_bytes(b"unexpected")
        paths["unexpected.bin"] = extra
    else:
        name = next(iter(paths))
        target = paths[name]
        link = tmp_path / "member-link"
        link.symlink_to(target)
        paths[name] = link

    with pytest.raises(ArtifactVerificationError):
        verify_release_bom_and_members(
            bom_bytes=bom_bytes,
            command_binding=fixture.command,
            member_paths=paths,
        )


def test_noncanonical_bom_is_rejected_even_when_its_digest_is_command_bound(tmp_path) -> None:
    fixture = build_artifact_fixture(tmp_path)
    pretty = json.dumps(json.loads(fixture.bom_bytes), indent=2).encode()
    command = fixture.command.model_copy(
        update={"release_bom_digest": hashlib.sha256(pretty).hexdigest()}
    )

    with pytest.raises(ArtifactVerificationError) as error:
        verify_release_bom_and_members(
            bom_bytes=pretty,
            command_binding=command,
            member_paths=fixture.member_paths,
        )

    assert error.value.code is ArtifactVerificationCode.BOM_NOT_CANONICAL


def test_artifact_ref_member_cross_link_is_revalidated(tmp_path) -> None:
    fixture = build_artifact_fixture(tmp_path)
    artifact_ref = fixture.command.artifact_ref.model_copy(update={"artifact_sha256": "0" * 64})
    command = fixture.command.model_copy(update={"artifact_ref": artifact_ref})

    with pytest.raises(ArtifactVerificationError) as error:
        verify_release_bom_and_members(
            bom_bytes=fixture.bom_bytes,
            command_binding=command,
            member_paths=fixture.member_paths,
        )

    assert error.value.code is ArtifactVerificationCode.COMMAND_BINDING_INVALID


def test_duplicate_json_keys_in_bom_are_rejected(tmp_path) -> None:
    fixture = build_artifact_fixture(tmp_path)
    duplicate = b'{"schema_version":1,"schema_version":1}'
    command = fixture.command.model_copy(
        update={"release_bom_digest": hashlib.sha256(duplicate).hexdigest()}
    )

    with pytest.raises(ArtifactVerificationError) as error:
        verify_release_bom_and_members(
            bom_bytes=duplicate,
            command_binding=command,
            member_paths=fixture.member_paths,
        )

    assert error.value.code is ArtifactVerificationCode.BOM_INVALID
