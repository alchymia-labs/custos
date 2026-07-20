"""CR100 User NKey/JWT transport enrollment and rotation."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from custos.cli.subcommands.start import DEFAULT_RUNNER_TOML
from custos.cli.validators import validate_backend_url
from custos.core.machine_credential_vault import (
    MachineCredentialError,
    MachineCredentialTransportError,
    MachineCredentialVault,
    resolve_age_recipient,
)
from custos.core.nats_transport import (
    RunnerNatsRevocationObservation,
    RunnerNatsTransportAuthorityClient,
    RunnerNatsTransportBundle,
    RunnerNatsTransportConnectionProfile,
    RunnerNatsTransportError,
    RunnerNatsTransportVault,
    assert_old_generation_reconnect_denied,
)
from custos.core.runner_toml import RunnerToml

DEFAULT_TRANSPORT_VAULT = Path.home() / ".arx" / "vault" / "runner-nats-transport.enc"
DEFAULT_NATS_CA = Path.home() / ".arx" / "certs" / "crucible-nats-ca.pem"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "nats-transport",
        help="Enroll, rotate, activate or verify the CR100 runner NATS credential.",
    )
    actions = parser.add_subparsers(
        dest="transport_action",
        metavar="{enroll,rotate,activate,verify}",
    )
    for action in ("enroll", "rotate", "activate"):
        child = actions.add_parser(action)
        _add_authority_arguments(child)
        child.set_defaults(handler=run)
    verify = actions.add_parser("verify")
    _add_local_arguments(verify)
    verify.set_defaults(handler=run)


def _add_authority_arguments(parser: argparse.ArgumentParser) -> None:
    _add_identity_arguments(parser)
    _add_nats_connection_arguments(parser)
    parser.add_argument("--crucible-url", required=True, type=validate_backend_url)
    parser.add_argument(
        "--age-recipient",
        default=None,
        help="age public recipient; defaults to SOPS_AGE_RECIPIENT.",
    )


def _add_local_arguments(parser: argparse.ArgumentParser) -> None:
    _add_identity_arguments(parser)
    _add_nats_connection_arguments(parser)


def _add_nats_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--nats-url", required=True)
    parser.add_argument("--nats-ca", type=Path, default=DEFAULT_NATS_CA)
    parser.add_argument("--nats-server-name", required=True)
    parser.add_argument(
        "--revocation-timeout-secs",
        type=float,
        default=300.0,
        help="Bounded wait for forced disconnect and explicit old-JWT denial.",
    )
    parser.add_argument(
        "--issuer-account-public-nkey",
        default=os.environ.get("CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY", ""),
        help="Pinned CR100 NATS Account public NKey.",
    )


def _add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runner-toml", type=Path, default=DEFAULT_RUNNER_TOML)
    parser.add_argument(
        "--machine-vault",
        type=Path,
        default=None,
        help="Optional exact override; must equal runner.toml machine_vault_path.",
    )
    parser.add_argument(
        "--transport-vault",
        type=Path,
        default=DEFAULT_TRANSPORT_VAULT,
    )


def run(args: argparse.Namespace) -> int:
    try:
        metadata = RunnerToml.read(args.runner_toml)
        machine_vault_path = Path(metadata.machine_vault_path).expanduser().resolve()
        if (
            args.machine_vault is not None
            and args.machine_vault.expanduser().resolve() != machine_vault_path
        ):
            raise RunnerNatsTransportError(
                "--machine-vault differs from runner.toml authority binding"
            )
        machine_credential = MachineCredentialVault(machine_vault_path).load()
        machine_credential.assert_binding(metadata)
        vault = RunnerNatsTransportVault(args.transport_vault)
        if args.transport_action == "verify":
            bundle = vault.load()
            if bundle.active is None:
                raise RunnerNatsTransportError(
                    "NATS transport has no active generation; run activate"
                )
            if bundle.retiring is not None:
                raise RunnerNatsTransportError(
                    "NATS transport has unresolved retiring-generation evidence"
                )
            RunnerNatsTransportConnectionProfile(
                credential=bundle.active,
                nats_url=args.nats_url,
                ca_path=args.nats_ca,
                server_name=args.nats_server_name,
                pinned_issuer_account_public_nkey=_required_issuer(args.issuer_account_public_nkey),
            )
            print(
                "NATS transport verified: "
                f"tenant_id={bundle.active.tenant_id} "
                f"runner_id={bundle.active.runner_id} "
                f"generation={bundle.active.transport_generation}"
            )
            return 0

        age_recipient = resolve_age_recipient(args.age_recipient)
        authority = RunnerNatsTransportAuthorityClient(
            args.crucible_url,
            machine_credential,
        )
        if args.transport_action == "enroll":
            if vault.path.exists():
                raise RunnerNatsTransportError("NATS transport vault already exists; use rotate")
            pending = authority.issue_initial(
                expected_issuer_account_public_nkey=_required_issuer(
                    args.issuer_account_public_nkey
                )
            )
            bundle = RunnerNatsTransportBundle(active=None, pending=pending)
        elif args.transport_action == "rotate":
            bundle = vault.load()
            if bundle.active is None:
                raise RunnerNatsTransportError("cannot rotate without an active generation")
            if bundle.pending is not None:
                raise RunnerNatsTransportError(
                    "pending generation must be activated before another rotation"
                )
            if bundle.retiring is not None:
                raise RunnerNatsTransportError(
                    "retiring generation must complete before another rotation"
                )
            if (
                args.issuer_account_public_nkey
                and args.issuer_account_public_nkey != bundle.active.issuer_account_public_nkey
            ):
                raise RunnerNatsTransportError("rotation issuer pin differs from active authority")
            pending = authority.issue_rotation(bundle.active)
            bundle = RunnerNatsTransportBundle(active=bundle.active, pending=pending)
        elif args.transport_action == "activate":
            bundle = vault.load()
            if bundle.pending is None and bundle.retiring is None:
                raise RunnerNatsTransportError(
                    "NATS transport has no pending or retiring generation"
                )
        else:
            raise RunnerNatsTransportError("a nats-transport action is required")

        vault.persist(bundle, age_recipient=age_recipient)
        promoted = asyncio.run(
            _activate_and_complete_retirement(
                args=args,
                authority=authority,
                vault=vault,
                bundle=bundle,
                age_recipient=age_recipient,
            )
        )
        assert promoted.active is not None
        print(
            "NATS transport active: "
            f"tenant_id={promoted.active.tenant_id} "
            f"runner_id={promoted.active.runner_id} "
            f"generation={promoted.active.transport_generation}"
        )
        return 0
    except (MachineCredentialError, RunnerNatsTransportError, OSError, ValueError) as exc:
        print(f"NATS transport operation failed closed: {exc}", file=sys.stderr)
        return 1


def _connection_profile(
    args: argparse.Namespace,
    credential: Any,
) -> RunnerNatsTransportConnectionProfile:
    return RunnerNatsTransportConnectionProfile(
        credential=credential,
        nats_url=args.nats_url,
        ca_path=args.nats_ca,
        server_name=args.nats_server_name,
        pinned_issuer_account_public_nkey=_required_issuer(args.issuer_account_public_nkey),
    )


async def _connect(
    profile: RunnerNatsTransportConnectionProfile,
    *,
    name: str,
    allow_reconnect: bool,
    max_reconnect_attempts: int,
) -> Any:
    try:
        return await profile.connect(
            name=name,
            allow_reconnect=allow_reconnect,
            max_reconnect_attempts=max_reconnect_attempts,
        )
    except RunnerNatsTransportError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize NATS client implementation errors
        raise RunnerNatsTransportError("cannot establish pinned runner NATS session") from exc


async def _close(connection: Any | None) -> None:
    if connection is not None and not connection.is_closed:
        await connection.close()


def _remaining_timeout(args: argparse.Namespace, expires_at: datetime) -> float:
    configured = float(args.revocation_timeout_secs)
    if configured <= 0:
        raise RunnerNatsTransportError("revocation timeout must be positive")
    remaining = (expires_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise RunnerNatsTransportError("CR100 revocation challenge expired")
    return min(configured, remaining)


async def _activate_and_complete_retirement(
    *,
    args: argparse.Namespace,
    authority: RunnerNatsTransportAuthorityClient,
    vault: RunnerNatsTransportVault,
    bundle: RunnerNatsTransportBundle,
    age_recipient: str,
) -> RunnerNatsTransportBundle:
    pending_connection: Any | None = None
    retiring_connection: Any | None = None
    retiring_profile: RunnerNatsTransportConnectionProfile | None = None
    replacement_connected_at: datetime | None = None
    try:
        if bundle.pending is not None:
            pending_profile = _connection_profile(args, bundle.pending)
            pending_connection = await _connect(
                pending_profile,
                name=f"custos-transport-activate-{bundle.pending.runner_id}",
                allow_reconnect=False,
                max_reconnect_attempts=0,
            )
            replacement_connected_at = datetime.now(UTC)
            if bundle.active is not None:
                retiring_profile = _connection_profile(args, bundle.active)
                retiring_connection = await _connect(
                    retiring_profile,
                    name=f"custos-transport-retire-{bundle.active.runner_id}",
                    allow_reconnect=True,
                    max_reconnect_attempts=1,
                )
            activation = authority.activate(bundle.pending)
            bundle = bundle.promote_pending()
            vault.persist(bundle, age_recipient=age_recipient)
            await _close(pending_connection)
            pending_connection = None
            if bundle.retiring is None:
                return bundle
            expected_active_revision = activation["revision"]
        elif bundle.retiring is not None:
            if bundle.active is None:
                raise RunnerNatsTransportError(
                    "retiring NATS generation has no replacement active generation"
                )
            expected_active_revision = (
                bundle.revocation.challenge.expected_binding_revision
                if bundle.revocation is not None
                else authority.activate(bundle.active)["revision"]
            )
            if bundle.revocation is None:
                active_profile = _connection_profile(args, bundle.active)
                pending_connection = await _connect(
                    active_profile,
                    name=f"custos-transport-resume-{bundle.active.runner_id}",
                    allow_reconnect=False,
                    max_reconnect_attempts=0,
                )
                replacement_connected_at = datetime.now(UTC)
                retiring_profile = _connection_profile(args, bundle.retiring)
                retiring_connection = await _connect(
                    retiring_profile,
                    name=f"custos-transport-retire-{bundle.retiring.runner_id}",
                    allow_reconnect=True,
                    max_reconnect_attempts=1,
                )
        else:
            raise RunnerNatsTransportError("NATS transport has no pending or retiring generation")

        assert bundle.retiring is not None
        retiring = bundle.retiring
        observation = bundle.revocation
        if observation is None:
            if retiring_profile is None or retiring_connection is None:
                raise RunnerNatsTransportError(
                    "old-generation session is required before broker revocation"
                )
            try:
                challenge = authority.revoke_superseded(
                    retiring,
                    expected_active_revision=expected_active_revision,
                    reason="Custos replacement generation activated",
                )
            except MachineCredentialTransportError:
                challenge = authority.read_revocation_challenge(retiring)
            if bundle.active is None or replacement_connected_at is None:
                raise RunnerNatsTransportError(
                    "replacement generation connectivity was not observed"
                )
            bundle = bundle.with_revocation(
                RunnerNatsRevocationObservation(
                    challenge=challenge,
                    replacement_transport_credential_id=(bundle.active.transport_credential_id),
                    replacement_generation=bundle.active.transport_generation,
                    replacement_connected_at=replacement_connected_at,
                    challenge_validated_at=datetime.now(UTC),
                )
            )
            observation = bundle.revocation
            assert observation is not None
            vault.persist(bundle, age_recipient=age_recipient)
            try:
                await asyncio.wait_for(
                    retiring_profile.wait_disconnected(),
                    timeout=_remaining_timeout(args, challenge.expires_at),
                )
            except TimeoutError as exc:
                raise RunnerNatsTransportError(
                    "old NATS generation did not report forced disconnect"
                ) from exc
            bundle = bundle.with_revocation(observation.mark_forced_disconnect(datetime.now(UTC)))
            observation = bundle.revocation
            assert observation is not None
            vault.persist(bundle, age_recipient=age_recipient)
        else:
            current = authority.read_revocation_challenge(retiring)
            if current != observation.challenge:
                raise RunnerNatsTransportError(
                    "persisted revocation challenge differs from Crucible"
                )
            if observation.forced_disconnect_observed_at is None:
                raise RunnerNatsTransportError(
                    "forced-disconnect observation was not durable before restart"
                )

        if observation.old_generation_reconnect_denied_at is None:
            await _close(retiring_connection)
            retiring_connection = None
            denial_profile = _connection_profile(args, retiring)
            await assert_old_generation_reconnect_denied(
                denial_profile,
                name=f"custos-transport-denial-{retiring.runner_id}",
                timeout_seconds=_remaining_timeout(args, observation.challenge.expires_at),
            )
            bundle = bundle.with_revocation(observation.mark_reconnect_denied(datetime.now(UTC)))
            observation = bundle.revocation
            assert observation is not None
            vault.persist(bundle, age_recipient=age_recipient)

        current = authority.read_revocation_challenge(retiring)
        if current != observation.challenge:
            raise RunnerNatsTransportError(
                "revocation challenge changed before evidence submission"
            )
        completed_at = authority.submit_revocation_evidence(
            observation,
            reason="Custos observed forced disconnect and exact old-JWT denial",
        )
        bundle = bundle.complete_retirement(completed_at)
        vault.persist(bundle, age_recipient=age_recipient)
        return bundle
    finally:
        await _close(pending_connection)
        await _close(retiring_connection)


def _required_issuer(value: str) -> str:
    issuer = value.strip()
    if not issuer:
        raise RunnerNatsTransportError(
            "--issuer-account-public-nkey or CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY is required"
        )
    return issuer
