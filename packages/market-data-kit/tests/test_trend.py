"""Tests for trend indicators: MA, EMA, Bollinger, ATR, Bias."""
import pandas as pd
import numpy as np
import pytest
from market_data_kit.indicators.trend import ma, ema, bollinger, atr, bias


def _make_ohlcv(n=60):
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 0.5,
        "high": close + abs(np.random.randn(n)) * 2,
        "low": close - abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(1000, 100000, n),
    })


class TestMA:
    def test_default_periods(self):
        df = _make_ohlcv()
        result = ma(df)
        for p in [5, 10, 20, 60]:
            assert f"ma_{p}" in result.columns

    def test_custom_periods(self):
        df = _make_ohlcv()
        result = ma(df, periods=[3, 7])
        assert "ma_3" in result.columns
        assert "ma_7" in result.columns

    def test_ma_values(self):
        df = pd.DataFrame({"close": [10.0, 20.0, 30.0, 40.0, 50.0]})
        result = ma(df, periods=[3])
        assert result["ma_3"].iloc[2] == 20.0  # (10+20+30)/3
        assert result["ma_3"].iloc[4] == 40.0  # (30+40+50)/3

    def test_not_modified(self):
        df = _make_ohlcv()
        orig = list(df.columns)
        ma(df)
        assert list(df.columns) == orig


class TestEMA:
    def test_default_periods(self):
        df = _make_ohlcv()
        result = ema(df)
        assert "ema_12" in result.columns
        assert "ema_26" in result.columns

    def test_custom(self):
        df = _make_ohlcv()
        result = ema(df, periods=[5, 10])
        assert "ema_5" in result.columns


class TestBollinger:
    def test_columns(self):
        df = _make_ohlcv()
        result = bollinger(df)
        for col in ["bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_position"]:
            assert col in result.columns

    def test_upper_gt_lower(self):
        df = _make_ohlcv()
        result = bollinger(df).dropna(subset=["bb_upper"])
        assert (result["bb_upper"] >= result["bb_lower"]).all()

    def test_middle_is_ma(self):
        df = _make_ohlcv()
        result = bollinger(df, period=20)
        expected = df["close"].rolling(20).mean()
        valid = result.dropna(subset=["bb_middle"])
        pd.testing.assert_series_equal(
            valid["bb_middle"].reset_index(drop=True),
            expected.dropna().reset_index(drop=True),
            check_names=False
        )


class TestATR:
    def test_columns(self):
        df = _make_ohlcv()
        result = atr(df)
        assert "atr_14" in result.columns
        assert "atr_pct" in result.columns

    def test_atr_positive(self):
        df = _make_ohlcv()
        result = atr(df).dropna(subset=["atr_14"])
        assert (result["atr_14"] > 0).all()

    def test_atr_pct_is_ratio(self):
        df = _make_ohlcv()
        result = atr(df).dropna(subset=["atr_14", "atr_pct"])
        expected_pct = result["atr_14"] / result["close"] * 100
        pd.testing.assert_series_equal(
            result["atr_pct"].reset_index(drop=True),
            expected_pct.reset_index(drop=True),
            check_names=False, atol=1e-10
        )

    def test_needs_high_low_close(self):
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        with pytest.raises(KeyError):
            atr(df)


class TestBias:
    def test_column(self):
        df = _make_ohlcv()
        result = bias(df)
        assert "bias_20" in result.columns

    def test_custom_period(self):
        df = _make_ohlcv()
        result = bias(df, period=10)
        assert "bias_10" in result.columns

    def test_bias_formula(self):
        df = pd.DataFrame({"close": [10.0] * 20 + [12.0]})
        result = bias(df, period=20)
        last = result["bias_20"].iloc[-1]
        # ma20 at last = (10*19 + 12) / 20 = 10.1, bias = (12-10.1)/10.1*100 ≈ 18.81
        expected_ma = (10.0 * 19 + 12.0) / 20
        expected_bias = (12.0 - expected_ma) / expected_ma * 100
        assert abs(last - expected_bias) < 0.01
