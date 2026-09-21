"""Tests for composite indicator computation with presets."""
import pandas as pd
import numpy as np
import pytest
from market_data_kit.indicators.composite import compute_all, PRESETS


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


class TestPresets:
    def test_default_preset_exists(self):
        assert "default" in PRESETS

    def test_backtest_preset_exists(self):
        assert "backtest" in PRESETS

    def test_report_preset_exists(self):
        assert "report" in PRESETS

    def test_minimal_preset_exists(self):
        assert "minimal" in PRESETS


class TestComputeAll:
    def test_default_adds_columns(self):
        df = _make_ohlcv()
        result = compute_all(df, preset="default")
        assert "rsi_14" in result.columns
        assert "ma_20" in result.columns
        assert "bb_upper" in result.columns
        assert "atr_14" in result.columns
        assert "volume_ratio" in result.columns
        assert "high_52w" in result.columns

    def test_backtest_includes_macd(self):
        df = _make_ohlcv()
        result = compute_all(df, preset="backtest")
        assert "macd" in result.columns
        assert "bias_20" in result.columns
        assert "obv" in result.columns

    def test_report_includes_support(self):
        df = _make_ohlcv()
        result = compute_all(df, preset="report")
        assert "support" in result.columns
        assert "resistance" in result.columns

    def test_minimal_is_small(self):
        df = _make_ohlcv()
        result = compute_all(df, preset="minimal")
        assert "rsi_14" in result.columns
        assert "ma_20" in result.columns
        assert "ma_60" in result.columns
        assert "volume_ratio" in result.columns
        # Should NOT have backtest-only columns
        assert "macd" not in result.columns

    def test_original_columns_preserved(self):
        df = _make_ohlcv()
        orig_cols = set(df.columns)
        result = compute_all(df)
        assert orig_cols.issubset(set(result.columns))

    def test_not_modified(self):
        df = _make_ohlcv()
        orig = list(df.columns)
        compute_all(df)
        assert list(df.columns) == orig

    def test_invalid_preset_raises(self):
        df = _make_ohlcv()
        with pytest.raises(ValueError):
            compute_all(df, preset="nonexistent")

    def test_row_count_unchanged(self):
        df = _make_ohlcv(100)
        result = compute_all(df)
        assert len(result) == 100
