"""Tests for akshare provider."""
import datetime
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from market_data_kit.providers.akshare_provider import AkshareProvider
from market_data_kit.providers.base import DataNotFoundError


def _make_cn_kline_fixture():
    """Fixture mimicking akshare stock_zh_a_hist output."""
    return pd.DataFrame({
        "日期": ["2026-03-27", "2026-03-28"],
        "开盘": [15.20, 15.30],
        "收盘": [15.30, 15.45],
        "最高": [15.40, 15.50],
        "最低": [15.10, 15.20],
        "成交量": [400000, 500000],
        "成交额": [6100000.0, 7700000.0],
        "涨跌幅": [1.0, 0.98],
        "换手率": [0.30, 0.37],
    })


def _make_hk_kline_fixture():
    return pd.DataFrame({
        "日期": ["2026-03-27", "2026-03-28"],
        "开盘": [413.0, 415.0],
        "收盘": [416.5, 418.6],
        "最高": [418.0, 420.0],
        "最低": [412.0, 413.0],
        "成交量": [16000000, 18000000],
        "成交额": [6.6e9, 7.5e9],
        "涨跌幅": [0.85, 0.50],
    })


def _make_fundamentals_fixture():
    return pd.DataFrame({
        "trade_date": ["2026-03-28"],
        "pe": [18.5],
        "pb": [0.85],
        "total_mv": [300000.0],
        "circ_mv": [290000.0],
    })


class TestAkshareCNKlines:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_basic_cn_klines(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = _make_cn_kline_fixture()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_klines("CN.000001", days=30, end_date=datetime.date(2026, 3, 28))
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 15.45
        assert result.iloc[-1]["symbol"] == "CN.000001"
        assert result.iloc[-1]["exchange"] == "SZ"

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_empty_returns_error(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_klines("CN.000001", days=30)


class TestAkshareHKKlines:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_basic_hk_klines(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_hk_hist.return_value = _make_hk_kline_fixture()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_klines("HK.00700", days=30, end_date=datetime.date(2026, 3, 28))
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 418.6
        assert result.iloc[-1]["exchange"] == "HKEX"

    def test_us_no_longer_raises_not_implemented(self, monkeypatch):
        """After W1a Task 2.1, US is supported; NotImplementedError should not be raised."""
        from unittest.mock import MagicMock
        import pandas as pd
        provider = AkshareProvider()

        def fake_fetch_us(symbol, days, end_date, adjust=""):
            return pd.DataFrame([{
                "symbol": symbol, "exchange": "NASDAQ",
                "date": __import__("datetime").date(2026, 5, 13),
                "open": 197.0, "high": 200.0, "low": 196.5, "close": 199.0,
                "volume": 48000000, "turnover": 9.55e9,
                "pct_change": 1.02, "prev_close": 197.0, "turnover_rate": 0.30,
                "pe_ratio": float("nan"), "adjust": "qfq",
                "adjust_factor": 1.0, "raw_close": 199.0,
            }])
        monkeypatch.setattr(provider, "_fetch_us_klines", fake_fetch_us)
        result = provider.fetch_klines("US.AAPL", days=30)
        assert not result.empty


class TestAkshareFundamentals:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_cn_fundamentals(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_a_lg_indicator.return_value = _make_fundamentals_fixture()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_fundamentals("CN.000001")
        assert result["pe_ratio"] == 18.5
        assert result["pb_ratio"] == 0.85

    def test_hk_fundamentals_raises(self):
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_fundamentals("HK.00700")


def _make_idx_kline_fixture():
    """Fixture mimicking akshare stock_zh_index_daily output."""
    return pd.DataFrame({
        "date": ["2026-03-27", "2026-03-28"],
        "open": [3350.0, 3360.0],
        "high": [3375.0, 3390.0],
        "low": [3340.0, 3355.0],
        "close": [3365.0, 3380.0],
        "volume": [3800000000, 4100000000],
    })


class TestAkshareIDXKlines:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_basic_idx_klines(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_zh_index_daily.return_value = _make_idx_kline_fixture()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_klines("IDX.000300", days=30, end_date=datetime.date(2026, 3, 28))
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 3380.0
        assert result.iloc[-1]["symbol"] == "IDX.000300"
        assert result.iloc[-1]["exchange"] == "INDEX"
        assert result.iloc[-1]["adjust"] == "none"
        assert pd.isna(result.iloc[-1]["turnover_rate"])

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_idx_empty_returns_error(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_zh_index_daily.return_value = pd.DataFrame()
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        with pytest.raises(DataNotFoundError):
            provider.fetch_klines("IDX.000001", days=30)

    def test_non_cn_idx_raises(self):
        """Non-numeric IDX codes (HK/US indices) should raise NotImplementedError."""
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_klines("IDX.HSI", days=30)


class TestAkshareMisc:
    def test_snapshot_not_implemented(self):
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_snapshot(["CN.000001"])

    def test_capital_flow_non_cn_raises(self):
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_capital_flow("HK.00700")


class TestAkshareIncomeStatement:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_fetch_income_statement_cn(self, mock_import):
        """Test akshare income statement fetch for CN stocks."""
        mock_ak = MagicMock()
        mock_ak.stock_profit_sheet_by_report_em.return_value = pd.DataFrame([{
            "REPORT_DATE_NAME": "2025-12-31",
            "TOTAL_OPERATE_INCOME": 150e9,
            "OPERATE_COST": 30e9,
            "OPERATE_PROFIT": 100e9,
            "NETPROFIT": 80e9,
            "BASIC_EPS": 63.5,
            "DILUTED_EPS": 63.5,
        }])
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_income_statement("CN.600519")
        assert len(result) == 1
        assert result[0]["symbol"] == "CN.600519"
        assert result[0]["period"] == "2025Q4"
        assert result[0]["revenue"] == 150e9
        assert result[0]["net_income"] == 80e9
        assert result[0]["gross_profit"] == 120e9

    def test_fetch_income_statement_non_cn(self):
        """akshare income statement only supports CN."""
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_income_statement("US.AAPL")

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_income_statement_margins(self, mock_import):
        """Verify margin calculations are correct."""
        mock_ak = MagicMock()
        mock_ak.stock_profit_sheet_by_report_em.return_value = pd.DataFrame([{
            "REPORT_DATE_NAME": "2025-12-31",
            "TOTAL_OPERATE_INCOME": 200e9,
            "OPERATE_COST": 50e9,
            "OPERATE_PROFIT": 120e9,
            "NETPROFIT": 100e9,
            "BASIC_EPS": 10.0,
            "DILUTED_EPS": 9.5,
        }])
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_income_statement("CN.600519")
        r = result[0]
        assert r["gross_margin"] == pytest.approx(75.0)  # (200-50)/200*100
        assert r["operating_margin"] == pytest.approx(60.0)  # 120/200*100
        assert r["net_margin"] == pytest.approx(50.0)  # 100/200*100

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_income_statement_fallback_to_yearly(self, mock_import):
        """Falls back to yearly API when report API fails."""
        mock_ak = MagicMock()
        mock_ak.stock_profit_sheet_by_report_em.side_effect = Exception("API error")
        mock_ak.stock_profit_sheet_by_yearly_em.return_value = pd.DataFrame([{
            "REPORT_DATE_NAME": "2025-06-30",
            "TOTAL_OPERATE_INCOME": 80e9,
            "OPERATE_COST": 20e9,
            "OPERATE_PROFIT": 50e9,
            "NETPROFIT": 40e9,
            "BASIC_EPS": 30.0,
            "DILUTED_EPS": 30.0,
        }])
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_income_statement("CN.600519")
        assert len(result) == 1
        assert result[0]["period"] == "2025Q2"


class TestAkshareCashFlowStatement:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_fetch_cash_flow_statement_cn(self, mock_import):
        """Test akshare cash flow statement fetch for CN stocks."""
        mock_ak = MagicMock()
        mock_ak.stock_cash_flow_sheet_by_report_em.return_value = pd.DataFrame([{
            "REPORT_DATE_NAME": "2025-12-31",
            "NETCASH_OPERATE": 60e9,
            "NETCASH_INVEST": -10e9,
            "NETCASH_FINANCE": -20e9,
            "CCE_ADD": 30e9,
            "BUY_FIX_ASSETS_OTHER": 8e9,
            "FIXED_ASSETS_DEPRECIATION": 3e9,
        }])
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_cash_flow_statement("CN.600519")
        assert len(result) == 1
        assert result[0]["symbol"] == "CN.600519"
        assert result[0]["period"] == "2025Q4"
        assert result[0]["operating_cf"] == 60e9
        assert result[0]["capex"] == -8e9
        assert result[0]["free_cf"] == 52e9

    def test_fetch_cash_flow_statement_non_cn(self):
        """akshare cash flow statement only supports CN."""
        provider = AkshareProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_cash_flow_statement("US.AAPL")

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_cash_flow_fallback_to_yearly(self, mock_import):
        """Falls back to yearly API when report API fails."""
        mock_ak = MagicMock()
        mock_ak.stock_cash_flow_sheet_by_report_em.side_effect = Exception("API error")
        mock_ak.stock_cash_flow_sheet_by_yearly_em.return_value = pd.DataFrame([{
            "REPORT_DATE_NAME": "2025-09-30",
            "NETCASH_OPERATE": 45e9,
            "NETCASH_INVEST": -5e9,
            "NETCASH_FINANCE": -15e9,
            "CCE_ADD": 25e9,
            "BUY_FIX_ASSETS_OTHER": 6e9,
            "FIXED_ASSETS_DEPRECIATION": 2e9,
        }])
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_cash_flow_statement("CN.600519")
        assert len(result) == 1
        assert result[0]["period"] == "2025Q3"
        assert result[0]["capex"] == -6e9
        assert result[0]["free_cf"] == 39e9


# ─── earnings_calendar ─────────────────────────────────────────────

def _make_disclosure_fixture(code: str, actual_date: str | None, scheduled: str | None = None):
    """Mock stock_report_disclosure output."""
    return pd.DataFrame({
        "股票代码": [code, "999999"],  # second row as noise
        "股票简称": ["test", "noise"],
        "首次预约": [scheduled or pd.NaT, "2026-04-30"],
        "初次变更": [pd.NaT, pd.NaT],
        "二次变更": [pd.NaT, pd.NaT],
        "三次变更": [pd.NaT, pd.NaT],
        "实际披露": [actual_date or pd.NaT, "2026-04-30"],
    })


class TestEarningsCalendar:
    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_cn_returns_actual_disclosure_dates(self, mock_import):
        mock_ak = MagicMock()
        # stock_report_disclosure called with multiple periods; return one row per period
        mock_ak.stock_report_disclosure.side_effect = [
            _make_disclosure_fixture("600519", "2026-04-25"),
            _make_disclosure_fixture("600519", "2026-03-21"),
            _make_disclosure_fixture("600519", "2025-10-30"),
            _make_disclosure_fixture("600519", "2025-04-30"),
        ]
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_earnings_calendar("CN.600519")

        assert len(result) >= 1
        assert result[0]["symbol"] == "CN.600519"
        assert result[0]["report_date"] == "2026-04-25"
        # EPS fields are None (cninfo doesn't expose these)
        assert result[0]["eps_estimate"] is None
        assert result[0]["eps_actual"] is None

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_cn_falls_back_to_scheduled_when_actual_nat(self, mock_import):
        mock_ak = MagicMock()
        mock_ak.stock_report_disclosure.side_effect = [
            _make_disclosure_fixture("600519", None, scheduled="2026-07-30"),
            _make_disclosure_fixture("600519", "2026-04-25"),
            _make_disclosure_fixture("600519", "2025-10-30"),
            _make_disclosure_fixture("600519", "2025-04-30"),
        ]
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_earnings_calendar("CN.600519")

        # First entry should use 首次预约 since 实际披露 is NaT
        assert result[0]["report_date"] == "2026-07-30"

    def test_non_cn_market_raises(self):
        provider = AkshareProvider()
        with pytest.raises(DataNotFoundError, match="only supports CN"):
            provider.fetch_earnings_calendar("HK.00700")
        with pytest.raises(DataNotFoundError, match="only supports CN"):
            provider.fetch_earnings_calendar("US.AAPL")

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_symbol_not_found_raises_data_not_found(self, mock_import):
        mock_ak = MagicMock()
        # Return DataFrames where the symbol we're querying doesn't appear
        mock_ak.stock_report_disclosure.return_value = _make_disclosure_fixture("000001", "2026-04-25")
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        with pytest.raises(DataNotFoundError, match="no disclosures"):
            provider.fetch_earnings_calendar("CN.600519")

    @patch("market_data_kit.providers.akshare_provider._import_ak")
    def test_api_error_continues_to_next_period(self, mock_import):
        """If akshare throws on one period, skip and try next."""
        mock_ak = MagicMock()
        mock_ak.stock_report_disclosure.side_effect = [
            Exception("cninfo timeout"),
            _make_disclosure_fixture("600519", "2026-03-21"),
            _make_disclosure_fixture("600519", "2025-10-30"),
            _make_disclosure_fixture("600519", "2025-04-30"),
        ]
        mock_import.return_value = mock_ak

        provider = AkshareProvider()
        result = provider.fetch_earnings_calendar("CN.600519")
        # First period errored → skipped; second period succeeded
        assert len(result) == 3
        assert result[0]["report_date"] == "2026-03-21"


# ── US klines tests (W1a Task 2.1) ──────────────────────────────


@pytest.fixture
def akshare_us_mock_df():
    """Mock akshare stock_us_hist return: qfq adjusted prices."""
    import pandas as pd
    return pd.DataFrame([
        {"日期": "2026-05-12", "开盘": 195.0, "收盘": 197.0, "最高": 198.0,
         "最低": 194.0, "成交量": 50000000, "成交额": 9.85e9,
         "振幅": 2.1, "涨跌幅": 1.0, "涨跌额": 1.95, "换手率": 0.32},
        {"日期": "2026-05-13", "开盘": 197.0, "收盘": 199.0, "最高": 200.0,
         "最低": 196.5, "成交量": 48000000, "成交额": 9.55e9,
         "振幅": 1.8, "涨跌幅": 1.02, "涨跌额": 2.0, "换手率": 0.30},
    ])


def test_us_klines_routes_to_us_method(monkeypatch, akshare_us_mock_df):
    """fetch_klines on US.AAPL must dispatch to _fetch_us_klines."""
    from market_data_kit.providers.akshare_provider import AkshareProvider
    provider = AkshareProvider()

    called = {}
    def fake_fetch_us(symbol, days, end_date, adjust=""):
        called["symbol"] = symbol
        called["days"] = days
        # Return a minimal valid 16-column DataFrame to avoid downstream failures
        import pandas as pd
        return pd.DataFrame([{
            "symbol": symbol, "exchange": "NASDAQ",
            "date": __import__("datetime").date(2026, 5, 13),
            "open": 197.0, "high": 200.0, "low": 196.5, "close": 199.0,
            "volume": 48000000, "turnover": 9.55e9,
            "pct_change": 1.02, "prev_close": 197.0, "turnover_rate": 0.30,
            "pe_ratio": float("nan"), "adjust": "qfq",
            "adjust_factor": 1.0, "raw_close": 199.0,
        }])
    monkeypatch.setattr(provider, "_fetch_us_klines", fake_fetch_us)

    result = provider.fetch_klines("US.AAPL", days=30)
    assert called["symbol"] == "US.AAPL"
    assert called["days"] == 30
    assert not result.empty


def test_us_klines_output_schema(monkeypatch, akshare_us_mock_df):
    """Output DataFrame must have all 16 W1a columns including adjust_factor + raw_close."""
    from unittest.mock import MagicMock
    fake_ak = MagicMock()
    fake_ak.stock_us_hist.return_value = akshare_us_mock_df
    # stock_us_spot_em returns a DataFrame with 代码 and 名称 columns
    import pandas as pd
    fake_ak.stock_us_spot_em.return_value = pd.DataFrame([
        {"代码": "105.AAPL", "名称": "苹果"},
        {"代码": "105.MSFT", "名称": "微软"},
    ])

    monkeypatch.setattr(
        "market_data_kit.providers.akshare_provider._import_ak",
        lambda: fake_ak,
    )

    from market_data_kit.providers.akshare_provider import AkshareProvider
    provider = AkshareProvider()
    df = provider.fetch_klines("US.AAPL", days=30, adjust="qfq")

    required = {
        "symbol", "exchange", "date", "open", "high", "low", "close",
        "volume", "turnover", "pct_change", "prev_close",
        "turnover_rate", "pe_ratio", "adjust", "adjust_factor", "raw_close",
    }
    assert required.issubset(set(df.columns)), \
        f"Missing: {required - set(df.columns)}"
    # adjust must be 'qfq' for stock_us_hist with adjust='qfq'
    assert (df["adjust"] == "qfq").all()
    # Factors are unknown for adjusted data, never invent 1.0 as proof.
    assert df["adjust_factor"].isna().all()
    assert df["raw_close"].isna().all()
    # symbol propagated
    assert (df["symbol"] == "US.AAPL").all()


def test_us_em_code_resolution_caches(monkeypatch):
    """_resolve_us_em_code should call stock_us_spot_em only once across multiple lookups."""
    from unittest.mock import MagicMock
    import pandas as pd
    fake_ak = MagicMock()
    call_count = {"n": 0}
    def spot_em():
        call_count["n"] += 1
        return pd.DataFrame([
            {"代码": "105.AAPL", "名称": "苹果"},
            {"代码": "105.MSFT", "名称": "微软"},
        ])
    fake_ak.stock_us_spot_em.side_effect = spot_em
    monkeypatch.setattr(
        "market_data_kit.providers.akshare_provider._import_ak",
        lambda: fake_ak,
    )

    from market_data_kit.providers.akshare_provider import AkshareProvider
    provider = AkshareProvider()
    code1 = provider._resolve_us_em_code("AAPL")
    code2 = provider._resolve_us_em_code("MSFT")
    code3 = provider._resolve_us_em_code("AAPL")
    assert code1 == "105.AAPL"
    assert code2 == "105.MSFT"
    assert code3 == "105.AAPL"
    assert call_count["n"] == 1, f"stock_us_spot_em called {call_count['n']} times, expected 1"


def test_us_em_code_unknown_returns_none(monkeypatch):
    """Unknown ticker should return None, not raise."""
    from unittest.mock import MagicMock
    import pandas as pd
    fake_ak = MagicMock()
    fake_ak.stock_us_spot_em.return_value = pd.DataFrame([
        {"代码": "105.AAPL", "名称": "苹果"},
    ])
    monkeypatch.setattr(
        "market_data_kit.providers.akshare_provider._import_ak",
        lambda: fake_ak,
    )

    from market_data_kit.providers.akshare_provider import AkshareProvider
    provider = AkshareProvider()
    assert provider._resolve_us_em_code("NOSUCHTICKER") is None


@pytest.mark.live
@pytest.mark.parametrize("symbol", ["US.AAPL", "US.MSFT", "US.GOOG", "US.TSLA", "US.NVDA"])
def test_us_klines_live(symbol):
    """Live test: 5 US symbols × 30 days. Skipped by default; run with -m live."""
    from market_data_kit.providers.akshare_provider import AkshareProvider
    provider = AkshareProvider()
    df = provider.fetch_klines(symbol, days=30)
    assert not df.empty, f"No data for {symbol}"
    assert len(df) >= 15, f"Too few rows for {symbol}: {len(df)}"
    assert df["close"].min() > 0
    assert df["volume"].min() >= 0
    assert (df["adjust_factor"] > 0).all()
