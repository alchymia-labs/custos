"""CR100 User NKey/JWT transport enrollment and rotation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from custos.cli.subcommands.start import DEFAULT_RUNNER_TOML
from custos.cli.validators import validate_backend_url
from custos.core.machine_credential_vault import (
    MachineCredentialError,
    MachineCredentialVault,
    resolve_age_recipient,
)
from custos.core.nats_transport import (
    RunnerNatsTransportAuthorityClient,
    RunnerNatsTransportBundle,
    RunnerNatsTransportConnectionProfile,
    RunnerNatsTransportError,
    RunnerNatsTransportVault,
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
    parser.add_argument("--crucible-url", required=True, type=validate_backend_url)
    parser.add_argument(
        "--age-recipient",
        default=None,
        help="age public recipient; defaults to SOPS_AGE_RECIPIENT.",
    )
    parser.add_argument(
        "--issuer-account-public-nkey",
        default=os.environ.get("CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY", ""),
        help="Pinned CR100 NATS Account public NKey.",
    )


def _add_local_arguments(parser: argparse.ArgumentParser) -> None:
    _add_identity_arguments(parser)
    parser.add_argument("--nats-url", required=True)
    parser.add_argument("--nats-ca", type=Path, default=DEFAULT_NATS_CA)
    parser.add_argument("--nats-server-name", required=True)
    parser.add_argument(
        "--issuer-account-public-nkey",
        default=os.environ.get("CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY", ""),
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
            RunnerNatsTransportConnectionProfile(
                credential=bundle.active,
                nats_url=args.nats_url,
                ca_path=args.nats_ca,
                server_name=args.nats_server_name,
                pinned_issuer_account_public_nkey=_required_issuer(
                    args.issuer_account_public_nkey
                ),
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
                raise RunnerNatsTransportError(
                    "NATS transport vault already exists; use rotate"
                )
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
            if (
                args.issuer_account_public_nkey
                and args.issuer_account_public_nkey
                != bundle.active.issuer_account_public_nkey
            ):
                raise RunnerNatsTransportError("rotation issuer pin differs from active authority")
            pending = authority.issue_rotation(bundle.active)
            bundle = RunnerNatsTransportBundle(active=bundle.active, pending=pending)
        elif args.transport_action == "activate":
            bundle = vault.load()
            if bundle.pending is None:
                raise RunnerNatsTransportError("NATS transport has no pending generation")
        else:
            raise RunnerNatsTransportError("a nats-transport action is required")

        vault.persist(bundle, age_recipient=age_recipient)
        assert bundle.pending is not None
        authority.activate(bundle.pending)
        promoted = bundle.promote_pending()
        vault.persist(promoted, age_recipient=age_recipient)
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


def _required_issuer(value: str) -> str:
    issuer = value.strip()
    if not issuer:
        raise RunnerNatsTransportError(
            "--issuer-account-public-nkey or CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY is required"
        )
    return issuer
