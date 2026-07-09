"""Runtime configuration knobs surfaced to operators.

Only knobs that legitimately tune backpressure / capacity live here.
Wire shape / subject names are not configurable — they live in plan-index
§6 and are baked into the codec.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryQueueConfig:
    """Bounds on the in-process telemetry queue between the NT MessageBus
    callback (which runs on the NT thread) and the async flush loop
    (which runs on the asyncio loop).

    ``max_queue_size`` is the hard cap; once full ``on_event`` drops the
    newest event so older buffered envelopes still publish in seq order.
    ``max_batch_size_per_publish`` caps one publish call's payload — even
    if the queue has 10_000 envelopes the flush loop ships them in chunks
    of this size to keep individual JetStream publishes reasonable.
    """

    max_queue_size: int = 10_000
    max_batch_size_per_publish: int = 500
