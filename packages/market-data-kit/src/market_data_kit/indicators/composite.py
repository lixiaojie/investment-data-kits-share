"""Composite indicator computation with preset profiles."""
from __future__ import annotations
import pandas as pd

from market_data_kit.indicators.momentum import rsi, macd
from market_data_kit.indicators.trend import ma, ema, bollinger, atr, bias
from market_data_kit.indicators.volume import volume_ratio, obv
from market_data_kit.indicators.level import high_low_52w, support_resistance

__all__ = ["compute_all", "PRESETS"]

PRESETS: dict[str, list[str]] = {
    "default": ["rsi", "ma", "bollinger", "atr", "volume_ratio", "high_low_52w"],
    "backtest": ["rsi", "ma", "bollinger", "atr", "volume_ratio", "high_low_52w",
                 "macd", "bias", "obv"],
    "report": ["rsi", "ma", "bollinger", "atr", "volume_ratio", "high_low_52w",
               "support_resistance"],
    "minimal": ["rsi", "ma_minimal", "volume_ratio"],
}

_INDICATOR_MAP = {
    "rsi": lambda df: rsi(df, period=14),
    "ma": lambda df: ma(df, periods=[5, 10, 20, 60]),
    "ma_minimal": lambda df: ma(df, periods=[20, 60]),
    "bollinger": lambda df: bollinger(df),
    "atr": lambda df: atr(df),
    "volume_ratio": lambda df: volume_ratio(df),
    "high_low_52w": lambda df: high_low_52w(df),
    "macd": lambda df: macd(df),
    "bias": lambda df: bias(df),
    "obv": lambda df: obv(df),
    "support_resistance": lambda df: support_resistance(df),
}


def compute_all(df: pd.DataFrame, preset: str = "default") -> pd.DataFrame:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset!r}. Available: {list(PRESETS.keys())}")

    result = df.copy()
    for indicator_name in PRESETS[preset]:
        fn = _INDICATOR_MAP[indicator_name]
        computed = fn(result)
        # Add only the new columns
        new_cols = [c for c in computed.columns if c not in result.columns]
        for c in new_cols:
            result[c] = computed[c]
    return result
