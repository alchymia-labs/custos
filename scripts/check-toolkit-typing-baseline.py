#!/usr/bin/env python3
"""Fail when inventory-extracted toolkit typing debt changes from baseline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs/authority/strategy-toolkit-typing-baseline-v1.json"
ERROR_PATTERN = re.compile(
    r"^(?P<path>packages/.+\.py):(?P<line>\d+): error: "
    r"(?P<message>.+)  \[(?P<code>[^]]+)]$"
)

PROFILES = {
    "platform_neutral": {
        "config": "packages/custos-strategy-toolkit/pyproject.toml",
        "paths": [
            "packages/custos-strategy-toolkit/src/custos_toolkit/config",
            "packages/custos-strategy-toolkit/src/custos_toolkit/filters",
            "packages/custos-strategy-toolkit/src/custos_toolkit/indicators",
            "packages/custos-strategy-toolkit/src/custos_toolkit/position",
            "packages/custos-strategy-toolkit/src/custos_toolkit/protocols",
            "packages/custos-strategy-toolkit/src/custos_toolkit/risk",
            "packages/custos-strategy-toolkit/src/custos_toolkit/signals",
            "packages/custos-strategy-toolkit/src/custos_toolkit/warmup",
        ],
    },
    "nautilus_adapter": {
        "config": "packages/custos-strategy-toolkit-nautilus/pyproject.toml",
        "paths": ["packages/custos-strategy-toolkit-nautilus/src/custos_toolkit_nautilus/adapter"],
    },
}


def _mypy_version() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        profile["config"],
        "--show-error-codes",
        "--no-pretty",
        "--no-color-output",
        "--no-error-summary",
        "--no-incremental",
        *profile["paths"],
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    output = result.stdout + result.stderr
    errors: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = ERROR_PATTERN.match(line)
        if match:
            errors.append(
                {
                    "path": match.group("path"),
                    "line": int(match.group("line")),
                    "code": match.group("code"),
                    "message": match.group("message"),
                }
            )
    errors.sort(key=lambda item: (item["path"], item["line"], item["code"], item["message"]))
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"mypy invocation failed ({result.returncode}):\n{output}")
    if result.returncode == 1 and not errors:
        raise RuntimeError(f"mypy failed without parseable errors:\n{output}")
    return errors


def _current_payload() -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for name, profile in PROFILES.items():
        errors = _run_profile(profile)
        profiles[name] = {
            "config": profile["config"],
            "paths": profile["paths"],
            "expected_error_count": len(errors),
            "errors": errors,
        }
    return {
        "typing_baseline_schema_version": 1,
        "mypy_version": _mypy_version(),
        "scope": "inventory-extracted implementation typing debt; not a strict PASS",
        "closure_requirement": "strict extracted-source typing closure",
        "private_vendor_policy": "excluded third-party source; covered by digest and parity gates",
        "profiles": profiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    current = _current_payload()

    if args.write_baseline:
        BASELINE_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        counts = {
            name: profile["expected_error_count"] for name, profile in current["profiles"].items()
        }
        print(f"wrote toolkit typing baseline: {counts}")
        return 0

    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if current != expected:
        print(
            "toolkit typing debt drifted; review changes and update the typing closure",
            file=sys.stderr,
        )
        return 1

    counts = {
        name: profile["expected_error_count"] for name, profile in current["profiles"].items()
    }
    print(
        "inventory-extracted typing debt: ACK exact baseline "
        f"{counts}; NOT strict, extracted-source typing closure required"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
