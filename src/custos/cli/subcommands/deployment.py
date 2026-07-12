"""``arx-runner deployment {validate,publish}`` handlers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import nats
from pydantic import ValidationError

from custos.cli.validators import validate_id
from custos.contracts import DeploymentMessage, DeploymentSpec, compute_strategy_code_hash


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "deployment",
        help="Validate or publish a DeploymentSpec.",
    )
    actions = parser.add_subparsers(dest="action", metavar="{validate,publish}")
    _register_validate(actions)
    _register_publish(actions)
    parser.set_defaults(handler=_dispatch)


def _register_validate(actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser("validate", help="Validate a DeploymentSpec without connecting.")
    parser.add_argument("--spec-file", required=True, type=Path)
    parser.set_defaults(action_handler=_validate)


def _register_publish(actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser("publish", help="Publish a validated DeploymentSpec.")
    parser.add_argument("--spec-file", required=True, type=Path)
    parser.add_argument(
        "--tenant-id",
        required=True,
        type=lambda value: validate_id("tenant_id", value),
    )
    parser.add_argument(
        "--strategy-id",
        required=True,
        type=lambda value: validate_id("strategy_id", value),
    )
    parser.add_argument("--nats-url", default="nats://localhost:4222")
    parser.add_argument("--strategy-dir", type=Path, default=None)
    parser.set_defaults(action_handler=_publish)


def _dispatch(args: argparse.Namespace):
    action_handler = getattr(args, "action_handler", None)
    if action_handler is None:
        raise SystemExit("deployment requires an action ({validate,publish})")
    return action_handler(args)


def _load_spec(spec_file: Path, strategy_dir: Path | None = None) -> DeploymentSpec | None:
    try:
        raw = json.loads(spec_file.read_text())
    except OSError as exc:
        print(f"unable to read deployment spec {spec_file}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"deployment spec {spec_file} is not valid JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(raw, dict):
        print("deployment spec root must be a JSON object", file=sys.stderr)
        return None
    if strategy_dir is not None:
        try:
            raw["code_hash"] = compute_strategy_code_hash(strategy_dir)
        except OSError as exc:
            print(f"unable to hash strategy directory {strategy_dir}: {exc}", file=sys.stderr)
            return None
    try:
        return DeploymentSpec.model_validate(raw)
    except ValidationError as exc:
        print(f"deployment spec validation failed: {exc}", file=sys.stderr)
        return None


def _validate(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec_file)
    if spec is None:
        return 1
    print(f"valid DeploymentSpec: {spec.spec_id} generation {spec.generation}")
    return 0


async def _publish(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec_file, args.strategy_dir)
    if spec is None:
        return 1
    try:
        message = DeploymentMessage.create(
            tenant_id=args.tenant_id,
            strategy_id=args.strategy_id,
            spec=spec,
        )
    except ValidationError as exc:
        print(f"deployment message validation failed: {exc}", file=sys.stderr)
        return 1

    connection = None
    try:
        connection = await nats.connect(args.nats_url)
        ack = await connection.jetstream().publish(message.subject, message.to_bytes())
        if ack is None:
            raise RuntimeError("JetStream publish returned no acknowledgement")
    except Exception as exc:  # noqa: BLE001 - CLI reports transport failure and exits non-zero
        print(f"deployment publish failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            await connection.drain()

    print(f"published DeploymentSpec {spec.spec_id} generation {spec.generation}")
    return 0
