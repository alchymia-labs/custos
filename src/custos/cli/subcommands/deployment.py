"""Offline DeploymentSpec diagnostics.

Production commands are published only by Crucible's transactional outbox. The
runner CLI intentionally has no command-publish operation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from custos.contracts import DeploymentSpec, compute_strategy_code_hash


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "deployment",
        help="Validate a local execution view; production publication is Crucible-owned.",
    )
    actions = parser.add_subparsers(dest="action", metavar="{validate}")
    validate = actions.add_parser("validate", help="Validate a DeploymentSpec offline.")
    validate.add_argument("--spec-file", required=True, type=Path)
    validate.add_argument("--strategy-dir", type=Path, default=None)
    validate.set_defaults(action_handler=_validate)
    parser.set_defaults(handler=_dispatch)


def _dispatch(args: argparse.Namespace) -> int:
    handler = getattr(args, "action_handler", None)
    if handler is None:
        print("deployment requires the validate action", file=sys.stderr)
        return 2
    return int(handler(args))


def _validate(args: argparse.Namespace) -> int:
    try:
        spec = DeploymentSpec.model_validate_json(args.spec_file.read_bytes())
        if args.strategy_dir is not None:
            actual = compute_strategy_code_hash(args.strategy_dir)
            if actual != spec.code_hash:
                raise ValueError("strategy directory digest differs from DeploymentSpec code_hash")
    except (OSError, ValueError, ValidationError) as exc:
        print(f"DeploymentSpec validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "DeploymentSpec valid: "
        f"instance={spec.deployment_instance_id} spec={spec.spec_id} mode={spec.trading_mode.value}"
    )
    return 0
