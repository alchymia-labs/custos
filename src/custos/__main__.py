"""Entry point for ``python -m custos``."""

from __future__ import annotations

import sys

from custos.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
