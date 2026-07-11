"""``arx-runner start`` handler.

Reads ``~/.arx/runner.toml``, builds a runtime namespace with per-key
vault + WAL + reconciler defaults, then delegates to the extracted
``custos.cli._daemon.run_daemon`` coroutine.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from custos.core.runner_toml import RunnerToml

DEFAULT_RUNNER_TOML = Path.home() / ".arx" / "runner.toml"
DEFAULT_WAL_PATH = Path.home() / ".arx" / "state" / "telemetry-wal.db"
DEFAULT_ENROLLMENT_PATH = Path.home() / ".arx" / "enrollment.json"
DEFAULT_VAULT_DIR = Path.home() / ".arx" / "vault"


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "start",
        help="Start the reconcile / telemetry / heartbeat runtime loop.",
    )
    parser.add_argument(
        "--runner-toml",
        dest="runner_toml_path",
        type=Path,
        default=DEFAULT_RUNNER_TOML,
        help="Long-term credential envelope written by `arx-runner enroll`.",
    )
    parser.add_argument("--nats-url", default="nats://localhost:4222")
    parser.add_argument("--heartbeat-interval", type=float, default=10.0)
    parser.add_argument(
        "--enrollment-path",
        type=Path,
        default=DEFAULT_ENROLLMENT_PATH,
    )
    parser.add_argument("--enrollment-token", default=None)
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=DEFAULT_VAULT_DIR,
        help="Per-key vault directory (default: ~/.arx/vault/).",
    )
    parser.add_argument(
        "--reconcile-strategy-id",
        default=None,
        help="Enable deployment reconciler bound to this strategy_id.",
    )
    parser.add_argument("--use-nt-host", action="store_true")
    parser.add_argument("--engine", default="nautilus")
    parser.add_argument(
        "--wal-path",
        type=Path,
        default=DEFAULT_WAL_PATH,
    )
    parser.add_argument("--snapshot-interval-secs", type=float, default=10.0)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    """Read runner.toml → build runtime namespace → delegate to run_daemon.

    On any missing / partial / world-readable runner.toml this fails fast
    with a clear stderr message and non-zero exit, never opening the
    daemon path. The caller (subcommand dispatcher) unwraps a coroutine
    return via ``asyncio.run``; keeping this handler synchronous means
    the daemon coroutine gets its own event loop and the parser stays
    testable without asyncio machinery.
    """
    try:
        record = RunnerToml.read(args.runner_toml_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    ns = argparse.Namespace(
        tenant_id=record.tenant_id,
        runner_id=record.runner_id,
        nats_url=args.nats_url,
        heartbeat_interval=args.heartbeat_interval,
        enrollment_path=args.enrollment_path,
        enrollment_token=args.enrollment_token,
        vault_dir=args.vault_dir,
        reconcile_strategy_id=args.reconcile_strategy_id,
        use_nt_host=args.use_nt_host,
        engine=args.engine,
        wal_path=args.wal_path,
        snapshot_interval_secs=args.snapshot_interval_secs,
    )
    from custos.cli._daemon import run_daemon

    return asyncio.run(run_daemon(ns))
