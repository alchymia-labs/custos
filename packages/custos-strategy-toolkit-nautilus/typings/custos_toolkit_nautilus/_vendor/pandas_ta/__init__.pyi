from pandas import DataFrame, Series

def adx(
    high: Series,
    low: Series,
    close: Series,
    *,
    length: int,
) -> DataFrame | None: ...
def atr(
    high: Series,
    low: Series,
    close: Series,
    *,
    length: int,
) -> Series | None: ...
def macd(
    close: Series,
    *,
    fast: int,
    slow: int,
    signal: int,
) -> DataFrame | None: ...
def rsi(close: Series, *, length: int) -> Series | None: ...
def supertrend(
    high: Series,
    low: Series,
    close: Series,
    *,
    length: int,
    multiplier: float,
) -> DataFrame | None: ...
