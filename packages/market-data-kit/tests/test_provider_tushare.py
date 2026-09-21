"""Tests for Tushare provider."""
import datetime
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from market_data_kit.providers.tushare_provider import TushareProvider
from market_data_kit.providers.base import DataNotFoundError


def _make_daily_fixture():
    return pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ"],
        "trade_date": ["20260327", "20260328"],
        "open": [15.20, 15.30],
        "high": [15.40, 15.50],
        "low": [15.10, 15.20],
        "close": [15.30, 15.45],
        "pre_close": [15.15, 15.30],
        "vol": [400000, 500000],
        "amount": [6100.0, 7700.0],
        "pct_chg": [1.0, 0.98],
    })


class TestTushareKlines:
    @patch("market_data_kit.providers.tushare_provider._import_tushare")
    def test_basic_klines(self, mock_import):
        mock_ts = MagicMock()
        mock_pro = MagicMock()
        mock_pro.daily.return_value = _make_daily_fixture()
        mock_ts.pro_api.return_value = mock_pro
        mock_import.return_value = mock_ts

        provider = TushareProvider(token="test_token")
        result = provider.fetch_klines("CN.000001", days=30, end_date=datetime.date(2026, 3, 28))
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 15.45
        assert result.iloc[-1]["symbol"] == "CN.000001"
        assert result.iloc[-1]["exchange"] == "SZ"

    @patch("market_data_kit.providers.tushare_provider._import_tushare")
    def test_empty_returns_error(self, mock_import):
        mock_ts = MagicMock()
        mock_pro = MagicMock()
        mock_pro.daily.return_value = pd.DataFrame()
        mock_ts.pro_api.return_value = mock_pro
        mock_import.return_value = mock_ts

        provider = TushareProvider(token="test_token")
        with pytest.raises(DataNotFoundError):
            provider.fetch_klines("CN.000001", days=30)

    def test_hk_raises_not_implemented(self):
        provider = TushareProvider(token="test")
        with pytest.raises(NotImplementedError):
            provider.fetch_klines("HK.00700", days=30)

    @patch("market_data_kit.providers.tushare_provider._import_tushare")
    def test_no_token_raises(self, mock_import):
        mock_import.return_value = MagicMock()
        provider = TushareProvider(token="")
        with pytest.raises(DataNotFoundError):
            provider.fetch_klines("CN.000001", days=30)


class TestTushareMisc:
    def test_snapshot_not_implemented(self):
        provider = TushareProvider(token="test")
        with pytest.raises(NotImplementedError):
            provider.fetch_snapshot(["CN.000001"])

    def test_healthcheck_with_token(self):
        provider = TushareProvider(token="test_token")
        # Can't actually check without tushare installed
        # Just verify it doesn't crash
        result = provider.healthcheck()
        assert isinstance(result, bool)
