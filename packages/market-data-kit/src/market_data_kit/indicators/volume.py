"""Volume indicators: Volume Ratio, OBV."""
from __future__ import annotations
import pandas as pd
import numpy as np

__all__ = ["volume_ratio", "obv"]


def volume_ratio(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.DataFrame:
    result = df.copy()
    result[f"vol_ma_{fast}"] = result["volume"].rolling(fast).mean()
    result[f"vol_ma_{slow}"] = result["volume"].rolling(slow).mean()
    result["volume_ratio"] = result[f"vol_ma_{fast}"] / result[f"vol_ma_{slow}"]
    return result


def obv(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    direction = np.sign(result["close"].diff())
    direction.iloc[0] = 0
    result["obv"] = (direction * result["volume"]).cumsum()
    return result
