"""NT 进程监管 + ExecutionEngineAdapter 的 CEX/NT 实现（设计 for 3、实现 1）。"""

from __future__ import annotations

from arx_runner.log import get_logger

__all__ = ["NoopHost"]

_log = get_logger("arx_runner.nautilus_host")


class NoopHost:
    """Stub NautilusHost — 不真起 NT 进程，只记结构化日志后返回占位。

    仅供 paper / dev / sim mode 让 reconcile 流程跑通；live mode 由 G6 gate
    （deployment_reconciler._check_g6_gate）拒绝，因为 stub 会静默接受 live
    execution spec 却不实际执行。真实 NT host（NtTradingNodeHost）由后续
    adapter 落地后替换本 stub。

    方法签名与 NautilusHostProtocol（deployment_reconciler.py）逐字一致，
    使 reconciler 可 ducktype 依赖，G6 gate 可 isinstance 命中。
    """

    async def deploy(self, spec: dict, credential: dict) -> str:
        spec_id = spec.get("spec_id")
        _log.info("nautilus_host_deploy_stub", spec_id=spec_id)
        return f"container-{spec_id}"

    async def reconfigure(self, spec: dict) -> None:
        _log.info("nautilus_host_reconfigure_stub", spec_id=spec.get("spec_id"))

    async def stop(self, spec_id: str) -> None:
        _log.info("nautilus_host_stop_stub", spec_id=spec_id)
