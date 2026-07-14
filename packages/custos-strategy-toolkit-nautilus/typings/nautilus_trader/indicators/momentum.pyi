from nautilus_trader.core.nautilus_pyo3 import EfficiencyRatio as _EfficiencyRatio
from nautilus_trader.core.nautilus_pyo3 import RateOfChange as RateOfChange
from nautilus_trader.core.nautilus_pyo3 import RelativeStrengthIndex as _RelativeStrengthIndex

class EfficiencyRatio(_EfficiencyRatio):
    def reset(self) -> None: ...

class RelativeStrengthIndex(_RelativeStrengthIndex):
    def reset(self) -> None: ...
