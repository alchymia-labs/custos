from decimal import Decimal

from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Money, Price, Quantity

class FixedRiskSizer:
    def __init__(self, instrument: Instrument) -> None: ...
    def calculate(
        self,
        *,
        entry: Price,
        stop_loss: Price,
        equity: Money,
        risk: Decimal,
        unit_batch_size: Decimal,
    ) -> Quantity: ...
