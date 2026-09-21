"""Trend indicators: MA, EMA, Bollinger Bands, ATR, Bias."""
from __future__ import annotations
import pandas as pd

__all__ = ["ma", "ema", "bollinger", "atr", "bias"]


def ma(df: pd.DataFrame, periods: list[int] | None = None, col: str = "close") -> pd.DataFrame:
    """Add simple moving average columns. Appends: ma_{period} for each period."""
    if periods is None:
        periods = [5, 10, 20, 60]
    result = df.copy()
    for p in periods:
        result[f"ma_{p}"] = result[col].rolling(p).mean()
    return result


def ema(df: pd.DataFrame, periods: list[int] | None = None, col: str = "close") -> pd.DataFrame:
    """Add exponential moving average columns. Appends: ema_{period} for each period."""
    if periods is None:
        periods = [12, 26]
    result = df.copy()
    for p in periods:
        result[f"ema_{p}"] = result[col].ewm(span=p, adjust=False).mean()
    return result


def bollinger(df: pd.DataFrame, period: int = 20, num_std: float = 2.0,
              col: str = "close") -> pd.DataFrame:
    """Add Bollinger Bands. Appends: bb_upper, bb_middle, bb_lower, bb_width, bb_position."""
    result = df.copy()
    mid = result[col].rolling(period).mean()
    std = result[col].rolling(period).std()
    result["bb_middle"] = mid
    result["bb_upper"] = mid + num_std * std
    result["bb_lower"] = mid - num_std * std
    result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / mid
    result["bb_position"] = (result[col] - result["bb_lower"]) / (result["bb_upper"] - result["bb_lower"])
    return result


def atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR using Wilder's smoothing. Appends: atr_{period}, atr_pct."""
    result = df.copy()
    prev_close = result["close"].shift(1)
    tr = pd.concat([
        result["high"] - result["low"],
        (result["high"] - prev_close).abs(),
        (result["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    result[f"atr_{period}"] = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    result["atr_pct"] = result[f"atr_{period}"] / result["close"] * 100
    return result


def bias(df: pd.DataFrame, period: int = 20, col: str = "close") -> pd.DataFrame:
    """Add bias ratio (deviation from MA). Appends: bias_{period}."""
    result = df.copy()
    moving_avg = result[col].rolling(period).mean()
    result[f"bias_{period}"] = (result[col] - moving_avg) / moving_avg * 100
    return result
