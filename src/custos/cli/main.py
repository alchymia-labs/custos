"""Legacy entry-point stub — the flat CLI has been removed.

The pre-Plan-11 ``python -m custos --tenant-id X --runner-id Y ...``
command surface was replaced by the ``arx-runner`` subcommand dispatcher
(``arx-runner enroll`` / ``arx-runner vault {put,verify,list}`` /
``arx-runner start``) matching arx ``docs/team-self-hosted-lifecycle.md``
§0.2 verbatim. This stub survives so ``python -m custos`` returns a
clear error rather than ``ModuleNotFoundError``.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print(
        "custos: the `python -m custos` / `custos` entry point has been removed. "
        "Use `arx-runner start` (see arx docs/team-self-hosted-lifecycle.md Phase 0.2).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
