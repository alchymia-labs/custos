from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXTRACTION = ROOT / "docs/authority/strategy-toolkit-extraction-v1.json"


def test_extraction_manifest_binds_source_and_target_digests() -> None:
    payload = json.loads(EXTRACTION.read_text(encoding="utf-8"))

    assert len(payload["source_commit"]) == 40
    assert payload["file_count"] == len(payload["files"]) == 241
    assert len(payload["inventory_sha256"]) == 64
    for record in payload["files"]:
        assert len(record["legacy_sha256"]) == 64
        assert len(record["target_sha256"]) == 64
        assert record["legacy_path"]
        assert record["target_path"]
