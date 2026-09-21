"""Momentum indicators: RSI (Wilder), MACD."""
from __future__ import annotations
import pandas as pd
import numpy as np

__all__ = ["rsi", "macd"]


def rsi(df: pd.DataFrame, period: int = 14, col: str = "close") -> pd.DataFrame:
    """Add RSI column using Wilder's smoothing (SMA seed + recursive).
    Appends: rsi_{period}
    """
    result = df.copy()
    delta = result[col].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    n = len(gain)
    rsi_vals = np.full(n, np.nan)

    if n > period:
        # Seed: SMA of first `period` changes (indices 1..period)
        avg_g = gain.iloc[1:period + 1].mean()
        avg_l = loss.iloc[1:period + 1].mean()
        rsi_vals[period] = _calc_rsi(avg_g, avg_l)

        # Wilder's recursive smoothing
        for i in range(period + 1, n):
            avg_g = (avg_g * (period - 1) + gain.iloc[i]) / period
            avg_l = (avg_l * (period - 1) + loss.iloc[i]) / period
            rsi_vals[i] = _calc_rsi(avg_g, avg_l)

    result[f"rsi_{period}"] = rsi_vals
    return result


def _calc_rsi(avg_gain: float, avg_loss: float) -> float:
    """Compute RSI from average gain and loss, handling edge cases."""
    if avg_gain == 0 and avg_loss == 0:
        return 50.0  # No movement
    if avg_loss == 0:
        return 100.0  # All gains
    if avg_gain == 0:
        return 0.0  # All losses
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
         signal_period: int = 9, col: str = "close") -> pd.DataFrame:
    """Add MACD, signal, and histogram columns."""
    result = df.copy()
    ema_fast = result[col].ewm(span=fast, adjust=False).mean()
    ema_slow = result[col].ewm(span=slow, adjust=False).mean()
    result["macd"] = ema_fast - ema_slow
    result["macd_signal"] = result["macd"].ewm(span=signal_period, adjust=False).mean()
    result["macd_histogram"] = result["macd"] - result["macd_signal"]
    return result
