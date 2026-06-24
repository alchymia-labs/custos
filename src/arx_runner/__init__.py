"""Arx 自托管执行宿主（Runner / ExecutionHost）。

承载 architecture §1 信任边界那条线：Key 与策略逻辑只在本地，出网只有遥测 + 状态回报。
控制 = 声明式 reconciliation（拉期望态本地对齐），非命令式直控容器。
"""

__version__ = "0.0.0"
