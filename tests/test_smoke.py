"""Phase 0 冒烟：确认包可导入。"""

import custos


def test_import():
    assert custos.__version__ == "0.0.0"
