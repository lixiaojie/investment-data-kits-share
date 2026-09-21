"""Tests for yfinance provider."""
import datetime
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from market_data_kit.providers.yfinance_provider import YfinanceProvider
from market_data_kit.providers.base import DataNotFoundError


def _make_history_fixture():
    """Mock yfinance Ticker.history() output (has DatetimeIndex)."""
    dates = pd.DatetimeIndex(["2026-03-27", "2026-03-28"], name="Date")
    return pd.DataFrame({
        "Open": [178.0, 179.5],
        "High": [180.0, 182.0],
        "Low": [177.0, 178.5],
        "Close": [179.5, 181.0],
        "Adj Close": [179.5, 181.0],
        "Volume": [50000000, 55000000],
    }, index=dates)


def _make_info_fixture():
    return {
        "shortName": "Apple Inc.",
        "currentPrice": 181.0,
        "regularMarketPrice": 181.0,
        "regularMarketChangePercent": 0.84,
        "regularMarketVolume": 55000000,
        "dayHigh": 182.0,
        "dayLow": 178.5,
        "regularMarketOpen": 179.5,
        "regularMarketPreviousClose": 179.5,
        "trailingPE": 28.5,
        "priceToBook": 45.0,
        "marketCap": 2800000000000,
        "returnOnEquity": 1.47,
        "dividendYield": 0.005,
        "totalRevenue": 383000000000,
        "netIncomeToCommon": 97000000000,
        "trailingEps": 6.35,
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }


class TestYfinanceKlines:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_basic_us_klines(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history_fixture()
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_klines("US.AAPL", days=30, end_date=datetime.date(2026, 3, 28))
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 181.0
        assert result.iloc[-1]["symbol"] == "US.AAPL"
        assert result.iloc[-1]["exchange"] == "NYSE"

    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_empty_history(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_klines("US.AAPL", days=30)


class TestYfinanceSnapshot:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_basic_snapshot(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.info = _make_info_fixture()
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_snapshot(["US.AAPL"])
        assert len(result) == 1
        assert result[0]["last_price"] == 181.0
        assert result[0]["name"] == "Apple Inc."


class TestYfinanceFundamentals:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_basic_fundamentals(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.info = _make_info_fixture()
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_fundamentals("US.AAPL")
        assert result["pe_ratio"] == 28.5
        assert result["eps"] == 6.35
        assert result["market_cap"] == 2800000000000

    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_empty_info(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_fundamentals("US.AAPL")


class TestYfinancePlates:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_basic_plates(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.info = _make_info_fixture()
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_plates("US.AAPL")
        assert len(result) == 2
        assert result[0]["type"] == "industry"
        assert result[0]["name"] == "Technology"


class TestYfinanceIncomeStatement:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_fetch_income_statement_us(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()

        mock_income = pd.DataFrame({
            "Total Revenue": [150e9, 140e9],
            "Cost Of Revenue": [60e9, 55e9],
            "Gross Profit": [90e9, 85e9],
            "Operating Income": [50e9, 45e9],
            "Net Income": [40e9, 35e9],
            "Basic EPS": [6.5, 5.8],
            "Diluted EPS": [6.4, 5.7],
        }, index=pd.to_datetime(["2025-12-31", "2025-09-30"]))
        mock_income = mock_income.T  # yfinance: dates as columns, items as rows

        type(mock_ticker).income_stmt = PropertyMock(return_value=mock_income)
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_income_statement("US.AAPL")
        assert len(result) == 2
        assert result[0]["symbol"] == "US.AAPL"
        assert result[0]["revenue"] == 150e9
        assert result[0]["period"] == "2025Q4"
        assert result[0]["net_income"] == 40e9
        assert result[0]["eps_basic"] == 6.5
        # Check margin calculations
        assert abs(result[0]["gross_margin"] - 60.0) < 0.01
        assert abs(result[0]["operating_margin"] - 33.33) < 0.01
        assert abs(result[0]["net_margin"] - 26.67) < 0.01

    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_fetch_income_statement_empty(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        type(mock_ticker).income_stmt = PropertyMock(return_value=pd.DataFrame())
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_income_statement("US.AAPL")

    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_fetch_income_statement_quarter_mapping(self, mock_import):
        """Test that non-standard month endings map correctly."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()

        mock_income = pd.DataFrame({
            "Total Revenue": [100e9],
            "Cost Of Revenue": [40e9],
            "Gross Profit": [60e9],
            "Operating Income": [30e9],
            "Net Income": [20e9],
            "Basic EPS": [4.0],
            "Diluted EPS": [3.9],
        }, index=pd.to_datetime(["2025-03-31"]))
        mock_income = mock_income.T

        type(mock_ticker).income_stmt = PropertyMock(return_value=mock_income)
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_income_statement("US.AAPL")
        assert result[0]["period"] == "2025Q1"


class TestYfinanceCashFlowStatement:
    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_fetch_cash_flow_statement_us(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()

        mock_cf = pd.DataFrame({
            "Operating Cash Flow": [30e9, 28e9],
            "Investing Cash Flow": [-5e9, -4e9],
            "Financing Cash Flow": [-25e9, -20e9],
            "Capital Expenditure": [-3e9, -2.5e9],
            "Depreciation And Amortization": [4e9, 3.5e9],
        }, index=pd.to_datetime(["2025-12-31", "2025-09-30"]))
        mock_cf = mock_cf.T  # yfinance: dates as columns

        type(mock_ticker).cash_flow = PropertyMock(return_value=mock_cf)
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        result = provider.fetch_cash_flow_statement("US.AAPL")
        assert len(result) == 2
        assert result[0]["symbol"] == "US.AAPL"
        assert result[0]["period"] == "2025Q4"
        assert result[0]["operating_cf"] == 30e9
        assert result[0]["capex"] == -3e9
        assert result[0]["free_cf"] == 27e9  # 30e9 + (-3e9)
        assert result[0]["net_cf"] == 0  # 30 - 5 - 25 = 0
        assert result[0]["depreciation"] == 4e9

    @patch("market_data_kit.providers.yfinance_provider._import_yfinance")
    def test_fetch_cash_flow_statement_empty(self, mock_import):
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        type(mock_ticker).cash_flow = PropertyMock(return_value=pd.DataFrame())
        mock_yf.Ticker.return_value = mock_ticker
        mock_import.return_value = mock_yf

        provider = YfinanceProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_cash_flow_statement("US.AAPL")


class TestYfinanceMisc:
    def test_capital_flow_not_implemented(self):
        provider = YfinanceProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_capital_flow("US.AAPL")
