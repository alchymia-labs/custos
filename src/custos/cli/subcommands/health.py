"""``arx-runner health`` readiness probe."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from custos.core.readiness import is_ready_file

DEFAULT_READY_FILE = Path.home() / ".arx" / "state" / "runner-ready.json"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("health", help="Check runner readiness state.")
    parser.add_argument("--ready-file", type=Path, default=DEFAULT_READY_FILE)
    parser.set_defaults(handler=_health)


def _health(args: argparse.Namespace) -> int:
    if not is_ready_file(args.ready_file):
        print(f"runner is not ready: {args.ready_file}", file=sys.stderr)
        return 1
    print(f"runner is ready: {args.ready_file}")
    return 0
