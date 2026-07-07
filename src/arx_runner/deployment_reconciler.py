"""Declarative deployment reconcile loop.

云端 NATS-发 DeploymentSpec → runner 本地比对 generation → 调
nautilus_host 起停 NT → NATS-发 DeploymentStatus 回报。

声明式 + level-triggered (plan-index §6):
- generation 比对幂等：同 generation 多次到达不重复执行。
- 失联≠停止 (domain-model L229)：NATS 断连时 reconcile loop 继续运行，
  本地 NT 不停。重连后补报最新 status。
- 主动观测：silent path 必接 structlog (lesson #21)。

新文件，不扩展 reconcile.py (后者是对账上传 ReconcileUploader, 职责不同)。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from arx_runner._strategy_loader import compute_strategy_dir_hash
from arx_runner.log import get_logger
from arx_runner.nats_client import ArxNatsClient

_log = get_logger("arx_runner.deployment_reconciler")

# The only credential permission scope allowed to reach a live venue. The vault
# enforces this on decrypt; the gate re-checks it as defence in depth.
_LIVE_SAFE_SCOPE = "trade_no_withdraw"


def _check_g6_gate(host: object, spec: dict, credential: dict | None) -> None:
    """G6 host gate — a live deployment must clear every layer or it is refused.

    live 是唯一强校验模式: paper / sandbox / testnet 各自的 host 通道自洽, 而
    live 单子一旦落到不具备执行能力的 host 上就进了黑洞 (承重墙: live 通道不能
    落到 stub 上)。live 下四层 fail-fast 缺一不可, 任一层拒绝立即 raise + 结构化
    error 日志 (reason_code = event 名):
      层 1  host 显式声明支持 live (NoopHost stub 声明 False → 拒)
      层 2  host 声明支持 spec 的 venue (connector)
      层 3  spec 钉住 code_hash 且与本地 strategy 源目录哈希一致 (provenance 红线)
      层 4  credential 的 permission_scope 是 trade_no_withdraw (vault 已守, 兜底)

    层 4 只在 credential 提供时校验 (deploy 路径); reconfigure 已在 deploy 时验过
    scope, 不重复解密。每层各有 relaxed-double 测试证明是 live guard 而非 dead branch。

    trading_mode 大小写不敏感: Rust `TradingMode` 默认 serde 序列化为 PascalCase
    (`"Live"`), Python 侧用小写 (`"live"`); 两侧 wire 表示都要命中否则 gate 沦为
    dead gate。
    """
    mode = str(spec.get("trading_mode") or "").lower()
    if mode != "live":
        return
    _g6_require_live_capable_host(host, spec)
    _g6_require_supported_venue(host, spec)
    _g6_require_code_hash_match(spec)
    if credential is not None:
        _g6_require_safe_credential_scope(credential, spec)


def _host_capability(host: object, method: str, *args: object) -> bool:
    """Query a host capability method, treating an undeclared one as False.

    Shipped hosts (NoopHost / NtTradingNodeHost) implement the capability
    contract explicitly; this fallback is only for a third-party host that failed
    to — it converts that programming error into a fail-safe structured G6
    rejection instead of an AttributeError. It does not weaken the explicit
    Protocol contract (both shipped hosts still declare their capabilities).
    """
    fn = getattr(host, method, None)
    return bool(fn(*args)) if callable(fn) else False


def _g6_require_live_capable_host(host: object, spec: dict) -> None:
    if not _host_capability(host, "supports_live"):
        _log.error(
            "g6_gate_live_capability_denied",
            spec_id=spec.get("spec_id"),
            trading_mode=spec.get("trading_mode"),
            host=type(host).__name__,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} requests live but host "
            f"{type(host).__name__} does not declare live capability"
        )


def _g6_require_supported_venue(host: object, spec: dict) -> None:
    venue = spec.get("connector")
    if not _host_capability(host, "supports_venue", str(venue)):
        _log.error(
            "g6_gate_venue_unsupported",
            spec_id=spec.get("spec_id"),
            venue=venue,
            host=type(host).__name__,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} venue {venue!r} not supported "
            f"by host {type(host).__name__}"
        )


def _g6_require_code_hash_match(spec: dict) -> None:
    code_hash = spec.get("code_hash")
    if not code_hash:
        _log.error("g6_gate_code_hash_mismatch", spec_id=spec.get("spec_id"), reason="missing")
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} live deploy requires a pinned "
            "code_hash (none provided)"
        )
    strategy_path = spec.get("strategy_path")
    if not strategy_path:
        # Without a strategy_path there is nothing to hash — refuse rather than
        # fall back to hashing the process CWD (Path("").parent == ".").
        _log.error(
            "g6_gate_code_hash_mismatch",
            spec_id=spec.get("spec_id"),
            reason="missing_strategy_path",
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} live deploy has a code_hash but no "
            "strategy_path to verify it against"
        )
    actual = compute_strategy_dir_hash(Path(strategy_path).parent)
    if actual != code_hash:
        _log.error(
            "g6_gate_code_hash_mismatch",
            spec_id=spec.get("spec_id"),
            reason="mismatch",
            expected_prefix=str(code_hash)[:12],
            actual_prefix=actual[:12],
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} code_hash mismatch "
            f"(expected {str(code_hash)[:12]}…, got {actual[:12]}…)"
        )


def _g6_require_safe_credential_scope(credential: dict, spec: dict) -> None:
    scope = credential.get("permission_scope")
    if scope != _LIVE_SAFE_SCOPE:
        _log.error(
            "g6_gate_credential_scope_violation",
            spec_id=spec.get("spec_id"),
            got_scope=scope,
        )
        raise RuntimeError(
            f"G6 gate: spec {spec.get('spec_id')!r} credential scope {scope!r} is not "
            f"{_LIVE_SAFE_SCOPE!r}"
        )


class NautilusHostProtocol(Protocol):
    """NT 进程监管接口 (skeleton: nautilus_host.py 真实现; runner 此处仅依赖签名)。

    supports_live / supports_venue are the explicit capability contract the G6
    gate queries (sync, so the gate decides without awaiting): a host declares
    up front whether it can execute live and which venues it wires. Both hosts
    implement them, so the gate calls them directly (no hasattr fallback); the
    paper stub declares False for both, keeping it fail-safe off live venues.
    """

    async def deploy(self, spec: dict, credential: dict) -> str: ...

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool: ...

    def supports_venue(self, venue: str) -> bool: ...


class CredentialVaultProtocol(Protocol):
    def decrypt(self, credential_id: str) -> dict: ...


@dataclass
class _ReconcileState:
    """Per-spec_id reconcile bookkeeping。observed_generation 是本地观测到
    runner 真正 reconcile 完成 的 generation; drift_strikes 累计连续观测
    spec.generation > observed_generation 的次数, 超阈值标 drift。"""

    observed_generation: int = 0
    container_id: str | None = None
    drift_strikes: int = 0


@dataclass
class DeploymentReconciler:
    """声明式 reconcile loop。"""

    nats_client: ArxNatsClient
    tenant_id: str
    runner_id: str
    nautilus_host: NautilusHostProtocol
    credential_vault: CredentialVaultProtocol
    drift_threshold: int = 3
    poll_interval_secs: float = 0.5
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _state: dict[str, _ReconcileState] = field(default_factory=dict)

    async def reconcile_loop(
        self,
        stop: asyncio.Event,
        strategy_id: str,
    ) -> None:
        """Main loop: subscribe deployment_spec → process → report status.

        失联安全 (CLAUDE.md 红线 '失联≠停止'):
        - subscribe/connect 异常时记 log + 退避重试; 本地 NT 不停。
        - publish_deployment_status 失败时记 log + 跳过; 下一次 reconcile 重报。
        """
        _log.info(
            "deployment_reconciler_started",
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
            session_id=self.session_id,
            strategy_id=strategy_id,
        )
        try:
            sub = await self.nats_client.subscribe_deployment_spec(strategy_id=strategy_id)
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "deployment_reconciler_subscribe_failed",
                strategy_id=strategy_id,
                error=str(exc),
            )
            return

        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(
                    sub.next_msg(timeout=self.poll_interval_secs),
                    timeout=self.poll_interval_secs * 2,
                )
            except TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001 — NATS 抖动不停止 loop
                _log.warning(
                    "deployment_reconciler_recv_failed",
                    strategy_id=strategy_id,
                    error=str(exc),
                )
                await asyncio.sleep(self.poll_interval_secs)
                continue

            try:
                envelope = json.loads(msg.data)
            except (json.JSONDecodeError, AttributeError) as exc:
                _log.error(
                    "deployment_spec_decode_failed",
                    error=str(exc),
                )
                continue
            spec = envelope.get("payload", {})
            await self.handle_spec(spec)

        _log.info(
            "deployment_reconciler_stopped",
            session_id=self.session_id,
        )

    async def handle_spec(self, spec: dict) -> None:
        """Process one DeploymentSpec snapshot. Generation 幂等 + drift 检测。"""
        spec_id = spec.get("spec_id")
        if not spec_id:
            _log.error("deployment_spec_missing_spec_id", payload_keys=list(spec.keys()))
            return
        try:
            generation = int(spec.get("generation", 0))
        except (TypeError, ValueError):
            _log.error(
                "deployment_spec_invalid_generation",
                spec_id=spec_id,
                raw=spec.get("generation"),
            )
            return

        state = self._state.setdefault(spec_id, _ReconcileState())

        if generation == state.observed_generation:
            # No-op — 同 generation 再来一次不重复 (幂等)。
            _log.debug(
                "deployment_spec_noop",
                spec_id=spec_id,
                generation=generation,
            )
            return

        if generation < state.observed_generation:
            _log.warning(
                "deployment_spec_stale",
                spec_id=spec_id,
                spec_generation=generation,
                observed_generation=state.observed_generation,
            )
            return

        # 需要 reconcile: generation > observed_generation。
        try:
            container_id = await self._apply_spec(spec, state)
            state.container_id = container_id
            state.observed_generation = generation
            state.drift_strikes = 0
            await self._report_status(
                spec_id=spec_id,
                spec=spec,
                state=state,
                phase="running",
                health="healthy",
            )
        except Exception as exc:  # noqa: BLE001
            state.drift_strikes += 1
            _log.error(
                "deployment_reconcile_failed",
                spec_id=spec_id,
                error=str(exc),
                drift_strikes=state.drift_strikes,
                threshold=self.drift_threshold,
            )
            await self._report_status(
                spec_id=spec_id,
                spec=spec,
                state=state,
                phase="degraded",
                health="unhealthy",
            )
            if state.drift_strikes >= self.drift_threshold:
                _log.error(
                    "deployment_drift_detected",
                    spec_id=spec_id,
                    drift_strikes=state.drift_strikes,
                )

    async def _apply_spec(self, spec: dict, state: _ReconcileState) -> str:
        """Apply spec to NT: new deploy / reconfigure / stop."""
        lifecycle = spec.get("lifecycle_state")
        spec_id = spec["spec_id"]
        if lifecycle in ("stopped", "archived"):
            await self.nautilus_host.stop(spec_id)
            return ""
        # 新部署: 解密 credential → 过完整 G6 gate (含 scope 兜底层) → deploy。
        if state.container_id is None:
            cred = self.credential_vault.decrypt(self._credential_ref(spec, spec_id))
            _check_g6_gate(self.nautilus_host, spec, cred)
            return await self.nautilus_host.deploy(spec, cred)
        # 已有部署: reconfigure。gate 复验 host/venue/code_hash; 层 4 scope 已在
        # deploy 时验过, 此处不重新解密 credential。
        _check_g6_gate(self.nautilus_host, spec, credential=None)
        await self.nautilus_host.reconfigure(spec)
        return state.container_id or ""

    @staticmethod
    def _credential_ref(spec: dict, spec_id: str) -> str:
        provenance = spec.get("provenance_ref")
        if isinstance(provenance, dict) and provenance.get("credential_id"):
            return provenance["credential_id"]
        return spec_id  # fallback: use spec_id as opaque cred ref

    async def _report_status(
        self,
        *,
        spec_id: str,
        spec: dict,
        state: _ReconcileState,
        phase: str,
        health: str,
    ) -> None:
        """Publish DeploymentStatus back to cloud。失败必接 log (lesson #21)。"""
        payload = {
            "status_id": str(uuid.uuid4()),
            "spec_id": spec_id,
            "observed_generation": state.observed_generation,
            "container_id": state.container_id,
            "phase": phase,
            "health": health,
            "runner_id": self.runner_id,
        }
        try:
            await self.nats_client.publish_deployment_status(
                spec_id=spec_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "deployment_status_publish_failed",
                spec_id=spec_id,
                error=str(exc),
            )
