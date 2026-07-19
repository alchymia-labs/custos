"""Fail-closed ``arx-runner start`` composition."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from custos.core.machine_credential_vault import (
    MachineCredentialError,
    MachineCredentialVault,
)
from custos.core.nats_transport import RunnerNatsTransportError
from custos.core.runner_toml import RunnerToml

DEFAULT_RUNNER_TOML = Path.home() / ".arx" / "runner.toml"
DEFAULT_VAULT_DIR = Path.home() / ".arx" / "vault"
DEFAULT_READY_FILE = Path.home() / ".arx" / "state" / "runner-ready.json"
DEFAULT_RUNNER_CAPABILITY = Path.home() / ".arx" / "runner-capability.json"
DEFAULT_RUNNER_FACT_OUTBOX = Path.home() / ".arx" / "state" / "runner-fact-outbox.db"
DEFAULT_CRUCIBLE_DOMAIN_PUBLIC_KEY = Path.home() / ".arx" / "crucible-domain-event.pub"
DEFAULT_NATS_TRANSPORT_VAULT = (
    Path.home() / ".arx" / "vault" / "runner-nats-transport.enc"
)
DEFAULT_NATS_CA = Path.home() / ".arx" / "certs" / "crucible-nats-ca.pem"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "start", help="Start only after machine authority passes fail-closed verification."
    )
    parser.add_argument(
        "--runner-toml", dest="runner_toml_path", type=Path, default=DEFAULT_RUNNER_TOML
    )
    parser.add_argument(
        "--machine-vault",
        type=Path,
        default=None,
        help="Optional exact override; must equal runner.toml machine_vault_path.",
    )
    parser.add_argument("--nats-url", default="tls://localhost:4222")
    parser.add_argument(
        "--nats-transport-vault",
        type=Path,
        default=DEFAULT_NATS_TRANSPORT_VAULT,
    )
    parser.add_argument("--nats-ca", type=Path, default=DEFAULT_NATS_CA)
    parser.add_argument(
        "--nats-server-name",
        default=os.environ.get("CRUCIBLE_NATS_SERVER_NAME", ""),
    )
    parser.add_argument(
        "--nats-issuer-account-public-nkey",
        default=os.environ.get("CRUCIBLE_NATS_ISSUER_ACCOUNT_NKEY", ""),
    )
    parser.add_argument("--vault-dir", type=Path, default=DEFAULT_VAULT_DIR)
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument(
        "--crucible-domain-public-key",
        type=Path,
        default=DEFAULT_CRUCIBLE_DOMAIN_PUBLIC_KEY,
    )
    parser.add_argument(
        "--crucible-domain-key-id",
        default=os.environ.get("CRUCIBLE_DOMAIN_EVENT_KEY_ID", ""),
    )
    parser.add_argument("--engine", choices=["nautilus", "noop"], default="nautilus")
    parser.add_argument("--ready-file", type=Path, default=DEFAULT_READY_FILE)
    parser.add_argument("--runner-capability", type=Path, default=DEFAULT_RUNNER_CAPABILITY)
    parser.add_argument("--runner-fact-outbox", type=Path, default=DEFAULT_RUNNER_FACT_OUTBOX)
    parser.add_argument("--runner-fact-snapshot-interval-secs", type=float, default=10.0)
    parser.add_argument("--runner-fact-period-secs", type=int, default=86_400)
    parser.add_argument("--runner-fact-period-retry-secs", type=float, default=30.0)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    args.ready_file.expanduser().resolve().unlink(missing_ok=True)
    try:
        metadata = RunnerToml.read(args.runner_toml_path)
        bound_vault_path = Path(metadata.machine_vault_path).expanduser().resolve()
        if (
            args.machine_vault is not None
            and args.machine_vault.expanduser().resolve() != bound_vault_path
        ):
            raise MachineCredentialError(
                "--machine-vault differs from runner.toml authority binding"
            )
        credential = MachineCredentialVault(bound_vault_path).load()
        credential.assert_binding(metadata)
    except (OSError, ValueError, MachineCredentialError) as exc:
        print(f"Runner startup authority check failed: {exc}", file=sys.stderr)
        return 1

    namespace = argparse.Namespace(
        tenant_id=metadata.tenant_id,
        runner_id=metadata.runner_id,
        runner_toml_path=args.runner_toml_path.expanduser().resolve(),
        machine_vault=bound_vault_path,
        nats_url=args.nats_url,
        nats_transport_vault=args.nats_transport_vault,
        nats_ca=args.nats_ca,
        nats_server_name=args.nats_server_name,
        nats_issuer_account_public_nkey=args.nats_issuer_account_public_nkey,
        vault_dir=args.vault_dir,
        reconcile=args.reconcile,
        crucible_domain_public_key=args.crucible_domain_public_key,
        crucible_domain_key_id=args.crucible_domain_key_id,
        engine=args.engine,
        ready_file=args.ready_file,
        runner_capability=args.runner_capability,
        runner_fact_outbox=args.runner_fact_outbox,
        runner_fact_snapshot_interval_secs=args.runner_fact_snapshot_interval_secs,
        runner_fact_period_secs=args.runner_fact_period_secs,
        runner_fact_period_retry_secs=args.runner_fact_period_retry_secs,
    )
    from custos.cli._daemon import run_daemon

    try:
        return asyncio.run(run_daemon(namespace))
    except (
        OSError,
        ValueError,
        MachineCredentialError,
        RunnerNatsTransportError,
        RuntimeError,
    ) as exc:
        args.ready_file.expanduser().resolve().unlink(missing_ok=True)
        print(f"Runner startup failed closed: {exc}", file=sys.stderr)
        return 1
