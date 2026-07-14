"""Typed facade for the dynamically re-exported vendored pandas-ta surface."""

from typing import Protocol, cast

from pandas import DataFrame, Series

from custos_toolkit_nautilus._vendor import pandas_ta as _pandas_ta


class _PandasTa(Protocol):
    def adx(self, high: Series, low: Series, close: Series, *, length: int) -> DataFrame | None: ...

    def atr(self, high: Series, low: Series, close: Series, *, length: int) -> Series | None: ...

    def macd(self, close: Series, *, fast: int, slow: int, signal: int) -> DataFrame | None: ...

    def rsi(self, close: Series, *, length: int) -> Series | None: ...

    def supertrend(
        self,
        high: Series,
        low: Series,
        close: Series,
        *,
        length: int,
        multiplier: float,
    ) -> DataFrame | None: ...


ta = cast(_PandasTa, _pandas_ta)
