#!/usr/bin/env python3
"""
Enforce the "code artifacts must be English" red line from CLAUDE.md.

Scans **newly-added lines** (git staged `+` lines, not existing lines) in
`.py` / `.rs` / `.ts` / `.tsx` files for CJK characters. Existing Chinese
comments / logs are intentionally NOT flagged — the policy is "touch-and-fix"
(rewrite when you edit them), not "big-bang rewrite the world".

Scope aligned with the root `.claude/rules/code-style.md` §6 red line:
- IN scope: source code (`.py`, `.rs`, `.ts`, `.tsx`)
- OUT of scope: Markdown, `.planning/*`, Grimoire, config YAML, user-facing UI
  copy (i18n bundles / message JSON), CJK inside `data:` / URL literals

Exemption: a new line may contain `noqa: language` (or `noqa: lang`) at end of
line to opt out — use sparingly (e.g. a genuine user-facing error message that
must be Chinese for a Chinese-only product surface).

Exit:
  0 = clean
  1 = violations found (commit blocked)
  2 = unexpected internal error
"""

from __future__ import annotations

import re
import subprocess
import sys

CJK_PATTERN = re.compile(r"[一-鿿㐀-䶿豈-﫿　-〿＀-￯]")
NOQA_PATTERN = re.compile(r"noqa:\s*(language|lang|zh)\b", re.IGNORECASE)

TARGET_SUFFIXES = (".py", ".rs", ".ts", ".tsx")

# Paths inside repo that are documentation / planning / i18n bundles — do not
# scan even if they happen to be `.ts`/`.py` (rare but possible for i18n).
EXEMPT_PATH_PREFIXES = (
    ".planning/",
    "docs/",
    "grimoire/",
    "brand-guide/",
)
EXEMPT_PATH_SUBSTRINGS = (
    "/i18n/",
    "/locales/",
    "/messages/",
    "/.planning/",
    "/docs/",
    "/grimoire/",
    # Vendored upstream trees inside custos are byte-identical snapshots and
    # cannot be language-swept without breaking the provenance-sync workflow.
    "/toolkit/shared/",
    "/toolkit/vendor/",
    # This script's own CJK_PATTERN Unicode range literal is a tool
    # implementation detail (defines what counts as CJK), not user-facing
    # text subject to the English-only discipline it enforces.
    "check-code-english.py",
)


def _staged_target_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.endswith(TARGET_SUFFIXES):
            continue
        if any(line.startswith(p) for p in EXEMPT_PATH_PREFIXES):
            continue
        if any(sub in "/" + line for sub in EXEMPT_PATH_SUBSTRINGS):
            continue
        files.append(line)
    return files


def _staged_added_lines(path: str) -> list[tuple[int, str]]:
    """Return list of (new_line_number, content) for lines added by this commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", path],
        capture_output=True,
        text=True,
        check=True,
    )
    added: list[tuple[int, str]] = []
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    current_new_line = 0
    for line in result.stdout.splitlines():
        m = hunk_header_re.match(line)
        if m:
            current_new_line = int(m.group(1))
            continue
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            added.append((current_new_line, line[1:]))
            current_new_line += 1
        elif line.startswith("-"):
            # deletion — new-line pointer does not advance
            pass
        elif line.startswith(" "):
            current_new_line += 1
    return added


def _violates(content: str) -> bool:
    if NOQA_PATTERN.search(content):
        return False
    return bool(CJK_PATTERN.search(content))


def main() -> int:
    try:
        files = _staged_target_files()
    except subprocess.CalledProcessError as e:
        print(f"[check-code-english] git error: {e}", file=sys.stderr)
        return 2

    if not files:
        return 0

    violations: list[tuple[str, int, str]] = []
    for path in files:
        try:
            for line_no, content in _staged_added_lines(path):
                if _violates(content):
                    violations.append((path, line_no, content.rstrip()))
        except subprocess.CalledProcessError as e:
            print(f"[check-code-english] git diff failed for {path}: {e}", file=sys.stderr)
            return 2

    if not violations:
        return 0

    print(
        "\n[check-code-english] BLOCKED: newly-added lines contain Chinese "
        "characters in source code (.py / .rs / .ts / .tsx).\n"
        "Red line: see `.claude/rules/code-style.md` §6 and each subsystem "
        "CLAUDE.md 'Language Policy (Code Artifacts)'.\n"
        "Rewrite these lines in English (comments, log/event names, "
        "error messages). User-facing UI copy belongs in i18n bundles, not "
        "source code strings.\n"
        "Escape hatch (use rarely, with justification): append `noqa: language` "
        "to the end of the offending line.\n",
        file=sys.stderr,
    )
    print(f"Total violations: {len(violations)}\n", file=sys.stderr)
    for path, line_no, content in violations[:50]:
        preview = content if len(content) <= 200 else content[:200] + "…"
        print(f"  {path}:{line_no}: {preview}", file=sys.stderr)
    if len(violations) > 50:
        print(f"  … and {len(violations) - 50} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
