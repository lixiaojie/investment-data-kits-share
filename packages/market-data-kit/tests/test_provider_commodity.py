"""Tests for CommodityProvider."""
from unittest.mock import patch, MagicMock
import pytest

from market_data_kit.providers.commodity_provider import CommodityProvider, COMMODITY_SYMBOLS


@pytest.fixture
def provider():
    return CommodityProvider()


def test_fetch_commodity_prices(provider):
    mock_fast_info = MagicMock()
    mock_fast_info.last_price = 2345.60
    mock_fast_info.previous_close = 2325.80

    with patch("market_data_kit.providers.commodity_provider._import_yf") as mock_yf:
        ticker = MagicMock()
        type(ticker).fast_info = mock_fast_info
        mock_yf.return_value.Ticker.return_value = ticker

        result = provider.fetch_commodity_prices({"GC=F": {"name": "黄金", "unit": "USD/oz"}})
        assert len(result) == 1
        assert result[0]["symbol"] == "GC=F"
        assert result[0]["price"] == 2345.60
        assert result[0]["source"] == "yfinance"
        assert result[0]["unit"] == "USD/oz"


def test_fetch_all_defaults(provider):
    mock_fast_info = MagicMock()
    mock_fast_info.last_price = 100.0
    mock_fast_info.previous_close = 99.0

    with patch("market_data_kit.providers.commodity_provider._import_yf") as mock_yf:
        ticker = MagicMock()
        type(ticker).fast_info = mock_fast_info
        mock_yf.return_value.Ticker.return_value = ticker

        result = provider.fetch_commodity_prices()
        assert len(result) == len(COMMODITY_SYMBOLS)


def test_fetch_empty_raises(provider):
    from market_data_kit.providers.base import DataNotFoundError

    with patch("market_data_kit.providers.commodity_provider._import_yf") as mock_yf:
        ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = None
        type(ticker).fast_info = mock_fast_info
        ticker.info = {}
        mock_yf.return_value.Ticker.return_value = ticker

        with pytest.raises(DataNotFoundError):
            provider.fetch_commodity_prices({"GC=F": {"name": "黄金", "unit": "USD/oz"}})


def test_healthcheck(provider):
    with patch("market_data_kit.providers.commodity_provider._import_yf"):
        assert provider.healthcheck() is True


def test_healthcheck_no_yfinance(provider):
    with patch("market_data_kit.providers.commodity_provider._import_yf", side_effect=ImportError):
        assert provider.healthcheck() is False
