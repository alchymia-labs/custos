"""``arx-runner nats bootstrap`` handler."""

from __future__ import annotations

import argparse
import sys

from custos.cli.validators import validate_id
from custos.core.standalone_nats import bootstrap_standalone_nats


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("nats", help="Manage Custos-owned NATS infrastructure.")
    actions = parser.add_subparsers(dest="action", metavar="{bootstrap}")
    bootstrap = actions.add_parser("bootstrap", help="Create standalone JetStream topology.")
    bootstrap.add_argument("--profile", required=True, choices=["standalone"])
    bootstrap.add_argument("--nats-url", default="nats://localhost:4222")
    bootstrap.add_argument(
        "--tenant-id",
        required=True,
        type=lambda value: validate_id("tenant_id", value),
    )
    bootstrap.add_argument("--timeout-secs", type=float, default=30.0)
    bootstrap.set_defaults(action_handler=_bootstrap)
    parser.set_defaults(handler=_dispatch)


def _dispatch(args: argparse.Namespace):
    action_handler = getattr(args, "action_handler", None)
    if action_handler is None:
        raise SystemExit("nats requires an action ({bootstrap})")
    return action_handler(args)


async def _bootstrap(args: argparse.Namespace) -> int:
    try:
        await bootstrap_standalone_nats(
            nats_url=args.nats_url,
            tenant_id=args.tenant_id,
            timeout_secs=args.timeout_secs,
        )
    except Exception as exc:  # noqa: BLE001 - CLI converts infrastructure errors to exit 1
        print(f"NATS bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(f"standalone NATS topology ready for tenant {args.tenant_id}")
    return 0
