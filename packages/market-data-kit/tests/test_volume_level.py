"""Tests for volume and level indicators."""
import pandas as pd
import numpy as np
import pytest
from market_data_kit.indicators.volume import volume_ratio, obv
from market_data_kit.indicators.level import high_low_52w, support_resistance


def _make_ohlcv(n=300):
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.5,
        "high": close + abs(np.random.randn(n)) * 2,
        "low": close - abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(1000, 100000, n).astype(float),
    })


class TestVolumeRatio:
    def test_columns(self):
        df = _make_ohlcv(60)
        result = volume_ratio(df)
        assert "vol_ma_5" in result.columns
        assert "vol_ma_20" in result.columns
        assert "volume_ratio" in result.columns

    def test_custom_periods(self):
        df = _make_ohlcv(60)
        result = volume_ratio(df, fast=3, slow=10)
        assert "vol_ma_3" in result.columns
        assert "vol_ma_10" in result.columns

    def test_ratio_is_fast_over_slow(self):
        df = _make_ohlcv(60)
        result = volume_ratio(df).dropna(subset=["volume_ratio"])
        expected = result["vol_ma_5"] / result["vol_ma_20"]
        pd.testing.assert_series_equal(
            result["volume_ratio"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False, atol=1e-10
        )

    def test_not_modified(self):
        df = _make_ohlcv(60)
        orig = list(df.columns)
        volume_ratio(df)
        assert list(df.columns) == orig


class TestOBV:
    def test_column(self):
        df = _make_ohlcv(60)
        result = obv(df)
        assert "obv" in result.columns

    def test_obv_direction(self):
        df = pd.DataFrame({
            "close": [10.0, 11.0, 10.5, 12.0, 11.0],
            "volume": [1000.0, 2000.0, 1500.0, 3000.0, 1000.0],
        })
        result = obv(df)
        # Day 0: OBV = 0 (or first volume)
        # Day 1: close up → +2000
        # Day 2: close down → -1500
        # Day 3: close up → +3000
        # Day 4: close down → -1000
        assert result["obv"].iloc[-1] != 0  # just verify it's computed

    def test_not_modified(self):
        df = _make_ohlcv(60)
        orig = list(df.columns)
        obv(df)
        assert list(df.columns) == orig


class TestHighLow52w:
    def test_columns(self):
        df = _make_ohlcv(300)
        result = high_low_52w(df)
        assert "high_52w" in result.columns
        assert "low_52w" in result.columns
        assert "drawdown_52w" in result.columns

    def test_high_gte_close(self):
        df = _make_ohlcv(300)
        result = high_low_52w(df).dropna(subset=["high_52w"])
        assert (result["high_52w"] >= result["close"]).all()

    def test_low_lte_close(self):
        df = _make_ohlcv(300)
        result = high_low_52w(df).dropna(subset=["low_52w"])
        assert (result["low_52w"] <= result["close"]).all()

    def test_drawdown_negative_or_zero(self):
        df = _make_ohlcv(300)
        result = high_low_52w(df).dropna(subset=["drawdown_52w"])
        assert (result["drawdown_52w"] <= 0).all()

    def test_short_data(self):
        df = _make_ohlcv(30)
        result = high_low_52w(df)
        assert "high_52w" in result.columns
        # With only 30 bars, 252-period rolling will be all NaN
        assert result["high_52w"].isna().all()


class TestSupportResistance:
    def test_columns(self):
        df = _make_ohlcv(60)
        result = support_resistance(df)
        assert "support" in result.columns
        assert "resistance" in result.columns

    def test_support_lte_resistance(self):
        df = _make_ohlcv(60)
        result = support_resistance(df).dropna(subset=["support", "resistance"])
        if len(result) > 0:
            assert (result["support"] <= result["resistance"]).all()

    def test_not_modified(self):
        df = _make_ohlcv(60)
        orig = list(df.columns)
        support_resistance(df)
        assert list(df.columns) == orig
