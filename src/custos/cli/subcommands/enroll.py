"""``arx-runner enroll`` handler.

Matches arx ``docs/team-self-hosted-lifecycle.md`` §0.2.2 verbatim:

    arx-runner enroll --token <T> --backend http://team-server:8000 \\
        --tenant-id <id> --runner-id <id>

Persists the backend-issued long-term credential to ``~/.arx/runner.toml``
(0600) via ``custos.core.runner_toml``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import urllib.request
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError, URLError

from custos.cli.validators import validate_backend_url, validate_id
from custos.core.runner_toml import RunnerToml

# Stdlib logger — the audit event contract in credential_vault also uses
# stdlib logging so caplog assertions work uniformly across vault + enroll.
_log = logging.getLogger("custos.enrollment")

# Same 30s ceiling as the sops subprocess call in credential_vault; keeps
# all zero-dep external I/O boundaries on the same invariant.
_HTTP_TIMEOUT_SECS = 30
_ENROLLMENT_PATH = "/api/v1/enrollments"


def _validate_redirect_url(newurl: str) -> None:
    """Re-run the backend URL validator on a 3xx Location header.

    Called by the default ``HTTPRedirectHandler`` path in tests via
    monkey-patching; production code re-checks any Location that comes
    back through ``urlopen`` before following it.
    """
    try:
        validate_backend_url(newurl)
    except argparse.ArgumentTypeError as exc:
        raise HTTPError(newurl, 502, str(exc), None, None) from exc


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "enroll",
        help="Pair the runner with the backend and persist the long-term credential.",
    )
    parser.add_argument(
        "--token",
        required=True,
        type=_validate_token,
        help="One-shot enrollment token (plaintext).",
    )
    parser.add_argument(
        "--backend",
        required=True,
        type=validate_backend_url,
        help="Backend base URL, e.g. http://team-server:8000",
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        type=lambda v: validate_id("tenant_id", v),
    )
    parser.add_argument(
        "--runner-id",
        required=True,
        type=lambda v: validate_id("runner_id", v),
    )
    parser.add_argument(
        "--runner-toml",
        type=Path,
        default=Path.home() / ".arx" / "runner.toml",
        help="Where to persist the long-term credential (default: ~/.arx/runner.toml).",
    )
    parser.add_argument(
        "--agent-version",
        default="",
        help="Runner agent version string sent to the backend.",
    )
    parser.add_argument(
        "--capabilities",
        action="append",
        default=[],
        help="Runner capability advertised to the backend; repeat for multiple.",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    """Post enroll payload; persist runner.toml on 2xx; leave nothing on error."""
    token_hash = hashlib.sha256(args.token.encode("utf-8")).hexdigest()
    payload = {
        "token_hash": token_hash,
        "runner_id": args.runner_id,
        "agent_version": args.agent_version,
        "capabilities": list(args.capabilities),
    }
    url = f"{args.backend.rstrip('/')}{_ENROLLMENT_PATH}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECS) as response:
            body = response.read()
            status = getattr(response, "status", HTTPStatus.OK)
            final_url = getattr(response, "url", None)
            if isinstance(final_url, str) and final_url != url:
                _validate_redirect_url(final_url)
    except HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        message = body.decode("utf-8", errors="replace") if body else exc.reason
        if exc.code == HTTPStatus.CONFLICT:
            print(f"enrollment refused: {message}", file=sys.stderr)
        else:
            print(
                f"enrollment failed with HTTP {exc.code}: {message}",
                file=sys.stderr,
            )
        _log.error(
            "enrollment_http_error",
            extra={"status": exc.code, "runner_id": args.runner_id},
        )
        return 1
    except URLError as exc:
        print(f"enrollment failed: connection error ({exc.reason})", file=sys.stderr)
        _log.error("enrollment_connection_error", extra={"runner_id": args.runner_id})
        return 1

    if status >= 300:
        # Successful response but non-2xx (opener.open with a plain 3xx that
        # our safe redirect handler already covered — belt+suspenders).
        print(f"enrollment failed with HTTP {status}", file=sys.stderr)
        return 1

    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError:
        print("enrollment response was not valid JSON", file=sys.stderr)
        return 1

    long_term = response_payload.get("long_term_credential")
    enrolled_ns = response_payload.get("enrolled_at_ns")
    if not isinstance(long_term, str) or not isinstance(enrolled_ns, int):
        print(
            "enrollment response missing long_term_credential / enrolled_at_ns",
            file=sys.stderr,
        )
        return 1

    record = RunnerToml(
        tenant_id=args.tenant_id,
        runner_id=args.runner_id,
        backend_url=args.backend,
        long_term_credential=long_term,
        enrolled_at_ns=enrolled_ns,
    )
    RunnerToml.write(args.runner_toml, record)
    _log.info(
        "enrollment_completed",
        extra={
            "runner_id": args.runner_id,
            "tenant_id": args.tenant_id,
            "runner_toml": str(args.runner_toml),
        },
    )
    print(f"enrollment persisted to {args.runner_toml}")
    return 0


def _validate_token(value: str) -> str:
    """Reject tokens with NUL / control bytes at parse time.

    The token itself is not a filesystem path segment, but a NUL byte or
    control character in the plaintext is a sign of stdin corruption or
    intentional smuggling. Also reject empty tokens.
    """
    if not value:
        raise argparse.ArgumentTypeError("--token must be non-empty")
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise argparse.ArgumentTypeError("--token must not contain control characters")
    return value
