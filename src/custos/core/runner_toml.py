"""Long-term runner credential persistence at ``~/.arx/runner.toml``.

Written by ``arx-runner enroll`` after the backend returns a long-term
credential; consumed by ``arx-runner start`` to build a runtime namespace.

Invariants (non-custodial red line 0.1 — Key/KEK never leaves the runner
host; the long-term credential is authentication material, not decrypted
key material, but still sensitive enough to warrant 0600):

- File mode is 0600 on write and refused on read if world-readable.
- Parent directory (``~/.arx/``) is auto-created at mode 0700.
- Write is atomic: tmpfile + fsync + rename; a mid-rename crash leaves the
  prior file (or nothing) intact rather than a partial write.
- Read raises ``FileNotFoundError`` with a clear ``arx-runner enroll`` hint
  rather than a silent ``None``.
"""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_WORLD_GROUP_BITS = 0o077


@dataclass(frozen=True)
class RunnerToml:
    """The long-term credential envelope returned by the backend at enroll time.

    ``long_term_credential`` is the authentication token used by subsequent
    ``arx-runner start`` invocations to open the backend connection. It is
    sensitive but is *not* the exchange API key (that stays in the per-key
    ``~/.arx/vault/<key-id>.enc`` files).
    """

    tenant_id: str
    runner_id: str
    backend_url: str
    long_term_credential: str
    enrolled_at_ns: int

    @staticmethod
    def write(path: Path, record: RunnerToml) -> None:
        """Atomically persist ``record`` to ``path`` at mode 0600.

        Creates ``path.parent`` at mode 0700 if missing, then writes a
        ``.<name>.tmp`` sibling, fsyncs it, chmods to 0600, and renames it
        onto ``path``. If any step fails after tmpfile creation the tmpfile
        is unlinked before the exception propagates.
        """
        path.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        # ``mkdir(mode=)`` is masked by umask on some platforms; explicit
        # chmod ensures the invariant regardless of caller umask.
        os.chmod(path.parent, _DIR_MODE)

        tmp = path.parent / f".{path.name}.tmp"
        payload = _serialise(record)
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
            try:
                os.write(fd, payload.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(tmp, _FILE_MODE)
            os.rename(tmp, path)
        except BaseException:
            # Best-effort tmpfile cleanup — the caller sees the original error
            # untouched; the pre-existing ``path`` remains intact because we
            # only ever wrote through the tmp sibling.
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def read(path: Path) -> RunnerToml:
        """Load a previously-written record, enforcing 0600 on the file.

        Raises:
            FileNotFoundError: when ``path`` does not exist; the message
                points the operator at ``arx-runner enroll``.
            PermissionError: when the file mode is world- or group-readable.
            ValueError: when a required field is missing.
        """
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found; run `arx-runner enroll` first "
                "(see arx docs/team-self-hosted-lifecycle.md Phase 0.2)"
            )
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & _WORLD_GROUP_BITS:
            raise PermissionError(
                f"{path} mode {oct(mode)} is world/group-readable; "
                "expected 0600. Fix with `chmod 600 {path}` and re-run."
            )
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        missing = [f for f in _REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValueError(
                f"{path} is missing required field(s): {', '.join(missing)}. "
                "Re-run `arx-runner enroll` to regenerate."
            )
        return RunnerToml(
            tenant_id=data["tenant_id"],
            runner_id=data["runner_id"],
            backend_url=data["backend_url"],
            long_term_credential=data["long_term_credential"],
            enrolled_at_ns=int(data["enrolled_at_ns"]),
        )


_REQUIRED_FIELDS = (
    "tenant_id",
    "runner_id",
    "backend_url",
    "long_term_credential",
    "enrolled_at_ns",
)


def _serialise(record: RunnerToml) -> str:
    """Emit a minimal, deterministic TOML document.

    We hand-roll rather than pull ``tomli-w`` in to keep the base install
    zero-dep beyond ``tomllib`` (stdlib). All fields are scalar strings and
    a single int — nothing exotic to escape beyond backslash and quote.
    """
    data = asdict(record)
    lines = []
    for field in _REQUIRED_FIELDS:
        value = data[field]
        if isinstance(value, int):
            lines.append(f"{field} = {value}")
        else:
            lines.append(f'{field} = "{_escape(value)}"')
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
