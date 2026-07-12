"""Phase 0 smoke: verify package is importable."""

import custos


def test_import():
    assert custos.__version__ == "0.0.0"
