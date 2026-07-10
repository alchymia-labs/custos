"""Contract tests for TOOLKIT_PROVENANCE.md schema evolution.

The provenance manifest is more than a pin record — it also carries the
curation decision (which upstream subset custos vends as authority), a
drift-audit log (append-only history of sync-check runs), and pandas_ta
governance criteria. These tests guard that the schema stays parseable and
that new sections do not corrupt the pre-existing pinned-commit content.
"""

from __future__ import annotations

from pathlib import Path

_TOOLKIT_ROOT = (
    Path(__file__).resolve().parents[2].parent
    / "src"
    / "custos"
    / "engines"
    / "nautilus"
    / "toolkit"
)
_PROVENANCE_FILE = _TOOLKIT_ROOT / "TOOLKIT_PROVENANCE.md"


def _provenance_text() -> str:
    return _PROVENANCE_FILE.read_text(encoding="utf-8")


def test_toolkit_provenance_pinned_commit_valid() -> None:
    """Existing pinned-commit + sync-procedure content must survive schema
    evolution — new sections are additive, not destructive."""
    text = _provenance_text()
    assert "**Upstream commit**: `fc4ab1d`" in text, (
        "ps upstream pinned commit must remain parseable after provenance schema evolution"
    )
    assert "**Upstream commit**: `a3a2228`" in text, (
        "pandas_ta upstream pinned commit must remain parseable after provenance schema evolution"
    )
    assert "## Sync procedure" in text, "existing Sync procedure section must not be corrupted"


def test_toolkit_provenance_curation_decision_recorded() -> None:
    """Curation decision (DP1) must be materialized with the ratified option,
    a rationale referencing the no-Hummingbot-host consumer finding, and the
    affected-files count of the current vendored subset. Also covers
    pandas_ta governance (DP4) — status-quo statement + the three trigger
    criteria for future PyPI-package escalation — folded into this test
    rather than a separate NEW test, per plan §Failure-mode coverage
    contract row T4.1 (keeps the grep-verified NEW-test count stable)."""
    text = _provenance_text()
    assert "## Curation decision" in text
    assert "no custos Hummingbot host" in text
    assert "90 files" in text or "90-file" in text

    assert "## pandas_ta governance" in text
    assert "vendored fork" in text
    for trigger_fragment in ("drift events/quarter", "non-Guild", "Rust migration"):
        assert trigger_fragment in text, (
            f"pandas_ta governance must state the '{trigger_fragment}' trigger"
        )


def test_toolkit_provenance_drift_audit_log_appendable() -> None:
    """Drift-audit log section exists with the append-only column schema and
    accepts a landing seed entry without corrupting prior sections."""
    text = _provenance_text()
    assert "## Drift audit log" in text
    for column in (
        "ran_at",
        "ps_upstream_head",
        "ps_drift",
        "pandas_ta_upstream_head",
        "pandas_ta_drift",
        "run_by",
    ):
        assert column in text, f"drift audit log must declare the '{column}' column"
    assert "34b73a2" in text, "landing seed entry must record the as-of ps upstream head"

    # Structural check: the seed entry must live inside the Drift audit log
    # section, not bleed into a neighboring section — a later append is just
    # another row under the same header, so this also guards that appending
    # would not clobber the section boundary.
    seed_index = text.index("34b73a2")
    section_index = text.index("## Drift audit log")
    assert section_index < seed_index, "seed entry must live inside the Drift audit log section"
