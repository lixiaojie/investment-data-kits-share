"""Level indicators: 52-week High/Low, Support/Resistance."""
from __future__ import annotations
import pandas as pd

__all__ = ["high_low_52w", "support_resistance"]


def high_low_52w(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    result = df.copy()
    result["high_52w"] = result["close"].rolling(window, min_periods=window).max()
    result["low_52w"] = result["close"].rolling(window, min_periods=window).min()
    result["drawdown_52w"] = (result["close"] - result["high_52w"]) / result["high_52w"] * 100
    return result


def support_resistance(df: pd.DataFrame, lookback: int = 20,
                       sensitivity: float = 1.0) -> pd.DataFrame:
    result = df.copy()
    result["support"] = result["low"].rolling(lookback, min_periods=1).min()
    result["resistance"] = result["high"].rolling(lookback, min_periods=1).max()
    return result
