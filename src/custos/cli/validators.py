"""CLI-layer boundary-string validators shared by every subcommand.

Guards two filesystem/URL boundaries where a raw user string reaches a
sensitive sink:

- ``validate_id`` — for tenant_id / runner_id / key-id, which are joined
  into paths like ``~/.arx/vault/<key-id>.enc`` and NATS subjects. Rejects
  path traversal, null bytes, control characters, oversize, empty, and
  non-ASCII characters at parse time before the string is joined.
- ``validate_backend_url`` — for ``--backend`` on ``arx-runner enroll``.
  Restricts scheme to ``{http, https}`` and rejects userinfo / fragment /
  empty netloc before the URL reaches ``urllib.request.urlopen``.

Both raise ``argparse.ArgumentTypeError`` so argparse converts the failure
into a user-facing usage error rather than a stack trace.
"""

from __future__ import annotations

import argparse
import re
import urllib.parse

_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def validate_id(name: str, value: str) -> str:
    """Return ``value`` if it matches the safe-id regex, else raise.

    ``name`` is only used for the error message so the operator sees which
    flag was rejected (``tenant_id`` / ``runner_id`` / ``key_id``).
    """
    if not _ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{name!r} must match ^[a-zA-Z0-9_-]{{1,64}}$ (got {value!r})"
        )
    return value


def validate_backend_url(value: str) -> str:
    """Reject non-http(s) schemes and unsafe URL shapes at parse time.

    ``urllib.request.urlopen`` accepts ``file://`` / ``gopher://`` etc,
    which would let a hostile ``--backend`` value read local files or hit
    arbitrary services. Blocking at parse time keeps the enroll handler's
    body free of ad-hoc scheme checks.
    """
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--backend {value!r} is not a valid URL: {exc}") from exc
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise argparse.ArgumentTypeError(
            f"--backend scheme must be http or https (got {parsed.scheme!r} from {value!r})"
        )
    if not parsed.netloc:
        raise argparse.ArgumentTypeError(f"--backend must have a non-empty host (got {value!r})")
    if parsed.username or parsed.password:
        raise argparse.ArgumentTypeError(
            f"--backend must not embed userinfo (got user in {value!r})"
        )
    if parsed.fragment:
        raise argparse.ArgumentTypeError(f"--backend must not carry a fragment (got {value!r})")
    return value
