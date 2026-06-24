"""Phase 0 冒烟：确认包可导入。"""
import arx_runner


def test_import():
    assert arx_runner.__version__ == "0.0.0"
