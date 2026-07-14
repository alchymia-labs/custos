from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from custos_toolkit.contracts.strategy_execution import (
    ArtifactMemberRole,
    StrategyExecutionCommandBindingV1,
    canonical_json_bytes,
)
from pydantic import ValidationError

from custos.artifacts.errors import ArtifactVerificationCode, ArtifactVerificationError


@dataclass(frozen=True, slots=True)
class VerifiedArtifactMember:
    role: ArtifactMemberRole
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    path: Path


@dataclass(frozen=True, slots=True)
class VerifiedReleaseBom:
    release_bom_digest: str
    members: tuple[VerifiedArtifactMember, ...]


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _verify_canonical_bom(bom_bytes: bytes) -> None:
    try:
        document = json.loads(
            bom_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, _DuplicateJsonKey) as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.BOM_INVALID,
            "release BOM is not strict UTF-8 JSON",
        ) from error
    if not isinstance(document, dict):
        raise ArtifactVerificationError(
            ArtifactVerificationCode.BOM_INVALID,
            "release BOM root must be an object",
        )
    try:
        canonical = canonical_json_bytes(document)
    except (TypeError, ValueError) as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.BOM_INVALID,
            "release BOM cannot be canonicalized",
        ) from error
    if canonical != bom_bytes:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.BOM_NOT_CANONICAL,
            "release BOM bytes do not use the coordinated canonical JSON profile",
        )


def _hash_regular_file(path: Path) -> tuple[int, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_NOT_REGULAR,
            "release member cannot be opened as a no-follow file",
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_NOT_REGULAR,
                "release member is not a regular file",
            )
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or size != after.st_size:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_UNSTABLE,
                "release member changed while being verified",
            )
        return size, digest.hexdigest()
    finally:
        os.close(descriptor)


def verify_release_bom_and_members(
    *,
    bom_bytes: bytes,
    command_binding: StrategyExecutionCommandBindingV1,
    member_paths: Mapping[str, Path],
) -> VerifiedReleaseBom:
    try:
        command = StrategyExecutionCommandBindingV1.model_validate(
            command_binding.model_dump(mode="json")
        )
    except ValidationError as error:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.COMMAND_BINDING_INVALID,
            "strategy artifact command binding failed coordinated cross-link validation",
        ) from error

    actual_bom_digest = hashlib.sha256(bom_bytes).hexdigest()
    if actual_bom_digest != command.release_bom_digest:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.BOM_DIGEST_MISMATCH,
            "release BOM bytes do not match the signed command digest",
        )
    _verify_canonical_bom(bom_bytes)

    expected_names = {member.name for member in command.release_bom_members}
    actual_names = set(member_paths)
    if actual_names != expected_names:
        raise ArtifactVerificationError(
            ArtifactVerificationCode.MEMBER_SET_MISMATCH,
            "provided release member set is not exactly the signed command member set",
        )

    verified: list[VerifiedArtifactMember] = []
    for member in command.release_bom_members:
        path = Path(member_paths[member.name])
        size, digest = _hash_regular_file(path)
        if size != member.size_bytes:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_SIZE_MISMATCH,
                f"release member size mismatch for {member.name}",
            )
        if digest != member.sha256:
            raise ArtifactVerificationError(
                ArtifactVerificationCode.MEMBER_DIGEST_MISMATCH,
                f"release member digest mismatch for {member.name}",
            )
        verified.append(
            VerifiedArtifactMember(
                role=member.role,
                name=member.name,
                media_type=member.media_type,
                size_bytes=member.size_bytes,
                sha256=member.sha256,
                path=path,
            )
        )
    return VerifiedReleaseBom(actual_bom_digest, tuple(verified))
