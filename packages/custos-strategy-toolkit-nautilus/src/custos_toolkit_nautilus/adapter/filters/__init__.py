# shared/nautilus/filters/__init__.py
"""Nautilus-backed indicator filters.

Nautilus-path-specific filter implementations: indicator computation uses nautilus
native ``indicators/`` (layer 0) with the business decision inlined (layer 2). These
replace the hand-written indicator filters in ``custos_toolkit.filters``
(volatility/adx/momentum/volume/regime).

time/cooldown/mtf have no indicator computation and no nautilus counterpart, so they
are still provided by ``custos_toolkit.filters``.
"""

from .adx import NautilusAdxFilter
from .momentum import NautilusMomentumFilter
from .regime import NautilusRegimeFilter
from .volatility import NautilusVolatilityFilter
from .volume import NautilusVolumeFilter

__all__ = [
    "NautilusAdxFilter",
    "NautilusMomentumFilter",
    "NautilusRegimeFilter",
    "NautilusVolatilityFilter",
    "NautilusVolumeFilter",
]
