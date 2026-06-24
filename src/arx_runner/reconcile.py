"""声明式 reconcile loop：拉 DeploymentSpec(期望态) → 起/停 NT → 回报 DeploymentStatus(实际态)。

spec≠status 即本地对齐。云宕机不影响本地交易（本地权威态）。
"""
