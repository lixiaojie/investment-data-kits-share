"""Tests for symbol normalization — the most critical module."""

import pytest
from market_data_kit.symbols import (
    normalize,
    market,
    exchange,
    to_futu,
    to_tushare,
    to_yfinance,
    to_push2_secid,
    to_akshare,
    from_wind,
    SymbolError,
)


class TestNormalizeHK:
    def test_pure_5digit(self):
        assert normalize("00700") == "HK.00700"

    def test_futu_format(self):
        assert normalize("HK.00700") == "HK.00700"

    def test_yfinance_format(self):
        assert normalize("0700.HK") == "HK.00700"

    def test_yfinance_3digit(self):
        assert normalize("0005.HK") == "HK.00005"

    def test_pad_short_code(self):
        assert normalize("HK.700") == "HK.00700"

    def test_already_padded(self):
        assert normalize("HK.00005") == "HK.00005"

    def test_yfinance_2digit(self):
        assert normalize("05.HK") == "HK.00005"


class TestNormalizeCN:
    def test_tushare_sh(self):
        assert normalize("600519.SH") == "CN.600519"

    def test_tushare_sz(self):
        assert normalize("000001.SZ") == "CN.000001"

    def test_futu_sh(self):
        assert normalize("SH.600519") == "CN.600519"

    def test_futu_sz(self):
        assert normalize("SZ.000001") == "CN.000001"

    def test_yfinance_ss(self):
        assert normalize("600519.SS") == "CN.600519"

    def test_pure_6digit_sh(self):
        assert normalize("600519") == "CN.600519"

    def test_pure_6digit_sz(self):
        assert normalize("000001") == "CN.000001"

    def test_pure_6digit_9xx(self):
        assert normalize("900001") == "CN.900001"

    def test_pure_6digit_5xx(self):
        assert normalize("510050") == "CN.510050"

    def test_pure_6digit_3xx(self):
        assert normalize("300001") == "CN.300001"

    def test_already_standard(self):
        assert normalize("CN.600519") == "CN.600519"


class TestNormalizeUS:
    def test_pure_alpha(self):
        assert normalize("AAPL") == "US.AAPL"

    def test_already_standard(self):
        assert normalize("US.AAPL") == "US.AAPL"

    def test_dot_in_ticker(self):
        assert normalize("BRK.B") == "US.BRK.B"

    def test_us_prefix_with_dot_ticker(self):
        assert normalize("US.BRK.B") == "US.BRK.B"

    def test_lowercase_input(self):
        assert normalize("aapl") == "US.AAPL"

    def test_tsla(self):
        assert normalize("TSLA") == "US.TSLA"

    def test_us_lowercase_prefix(self):
        assert normalize("us.MSFT") == "US.MSFT"


class TestNormalizeEdgeCases:
    def test_whitespace_stripped(self):
        assert normalize("  HK.00700  ") == "HK.00700"

    def test_empty_string_raises(self):
        with pytest.raises(SymbolError):
            normalize("")

    def test_none_raises(self):
        with pytest.raises((SymbolError, TypeError)):
            normalize(None)

    def test_pure_numeric_4digit_is_hk(self):
        assert normalize("9988") == "HK.09988"

    def test_pure_numeric_7digit_raises(self):
        with pytest.raises(SymbolError):
            normalize("1234567")


class TestMarket:
    def test_hk(self):
        assert market("HK.00700") == "HK"

    def test_cn(self):
        assert market("CN.600519") == "CN"

    def test_us(self):
        assert market("US.AAPL") == "US"

    def test_invalid_raises(self):
        with pytest.raises(SymbolError):
            market("XX.12345")


class TestExchange:
    def test_hk(self):
        assert exchange("HK.00700") == "HKEX"

    def test_cn_sh_600(self):
        assert exchange("CN.600519") == "SH"

    def test_cn_sh_500(self):
        assert exchange("CN.510050") == "SH"

    def test_cn_sh_900(self):
        assert exchange("CN.900001") == "SH"

    def test_cn_sz_000(self):
        assert exchange("CN.000001") == "SZ"

    def test_cn_sz_300(self):
        assert exchange("CN.300001") == "SZ"

    def test_us_default_nyse(self):
        assert exchange("US.AAPL") == "NYSE"

    def test_us_dot_ticker(self):
        assert exchange("US.BRK.B") == "NYSE"


class TestToFutu:
    def test_hk(self):
        assert to_futu("HK.00700") == "HK.00700"

    def test_cn_sh(self):
        assert to_futu("CN.600519") == "SH.600519"

    def test_cn_sz(self):
        assert to_futu("CN.000001") == "SZ.000001"

    def test_us(self):
        assert to_futu("US.AAPL") == "US.AAPL"

    def test_us_dot_ticker(self):
        assert to_futu("US.BRK.B") == "US.BRK.B"


class TestToTushare:
    def test_cn_sh(self):
        assert to_tushare("CN.600519") == "600519.SH"

    def test_cn_sz(self):
        assert to_tushare("CN.000001") == "000001.SZ"

    def test_hk(self):
        assert to_tushare("HK.00700") == "00700.HK"

    def test_us(self):
        assert to_tushare("US.AAPL") == "AAPL.US"


class TestToYfinance:
    def test_hk(self):
        assert to_yfinance("HK.00700") == "0700.HK"

    def test_hk_short(self):
        assert to_yfinance("HK.00005") == "0005.HK"

    def test_cn_sh(self):
        assert to_yfinance("CN.600519") == "600519.SS"

    def test_cn_sz(self):
        assert to_yfinance("CN.000001") == "000001.SZ"

    def test_us(self):
        assert to_yfinance("US.AAPL") == "AAPL"

    def test_us_dot_ticker(self):
        assert to_yfinance("US.BRK.B") == "BRK-B"


class TestToPush2Secid:
    def test_cn_sz(self):
        assert to_push2_secid("CN.000001") == "0.000001"

    def test_cn_sh(self):
        assert to_push2_secid("CN.600519") == "1.600519"

    def test_cn_sz_300(self):
        assert to_push2_secid("CN.300001") == "0.300001"

    def test_us_returns_primary_prefix(self):
        result = to_push2_secid("US.AAPL")
        assert result == "105.AAPL"

    def test_hk_returns_116_prefix(self):
        assert to_push2_secid("HK.00700") == "116.00700"
        assert to_push2_secid("HK.09988") == "116.09988"


class TestToAkshare:
    def test_cn_sh(self):
        assert to_akshare("CN.600519") == "600519"

    def test_cn_sz(self):
        assert to_akshare("CN.000001") == "000001"

    def test_hk(self):
        assert to_akshare("HK.00700") == "00700"

    def test_us(self):
        assert to_akshare("US.AAPL") == "AAPL"


class TestIDXSymbols:
    """Tests for IDX (index) market symbols."""

    def test_normalize_idx_explicit(self):
        assert normalize("IDX.000300") == "IDX.000300"
        assert normalize("IDX.HSI") == "IDX.HSI"
        assert normalize("IDX.SPX") == "IDX.SPX"
        assert normalize("idx.000300") == "IDX.000300"

    def test_market_idx(self):
        assert market("IDX.000300") == "IDX"
        assert market("IDX.HSI") == "IDX"

    def test_exchange_idx(self):
        assert exchange("IDX.000300") == "INDEX"

    def test_to_yfinance_idx(self):
        assert to_yfinance("IDX.000300") == "000300.SS"
        assert to_yfinance("IDX.HSI") == "^HSI"
        assert to_yfinance("IDX.SPX") == "^GSPC"
        assert to_yfinance("IDX.DJI") == "^DJI"

    def test_to_yfinance_idx_all_backfill_symbols(self):
        """Verify all IDX_SYMBOLS from backfill.py convert to valid yfinance tickers."""
        expected = {
            # Hong Kong
            "IDX.HSI": "^HSI",
            "IDX.HSCEI": "^HSCE",
            "IDX.HSTECH": "^HSTECH",
            # China A-share
            "IDX.000001": "000001.SS",
            "IDX.399001": "399001.SZ",
            "IDX.000300": "000300.SS",
            "IDX.000905": "000905.SS",
            "IDX.399006": "399006.SZ",
            # US
            "IDX.SPX": "^GSPC",
            "IDX.DJI": "^DJI",
            "IDX.IXIC": "^IXIC",
            "IDX.RUT": "^RUT",
            # Global
            "IDX.VIX": "^VIX",
        }
        for idx_sym, yf_expected in expected.items():
            assert to_yfinance(idx_sym) == yf_expected, f"{idx_sym} -> {to_yfinance(idx_sym)} != {yf_expected}"

    def test_to_wind_idx(self):
        from market_data_kit.symbols import to_wind
        assert to_wind("IDX.000300") == "000300.SH"
        assert to_wind("IDX.HSI") == "HSI.HI"
        assert to_wind("IDX.SPX") == "SPX.GI"

    def test_to_wind_stocks(self):
        from market_data_kit.symbols import to_wind
        assert to_wind("HK.00700") == "0700.HK"
        assert to_wind("CN.600519") == "600519.SH"
        assert to_wind("CN.000001") == "000001.SZ"

    def test_to_futu_idx(self):
        assert to_futu("IDX.HSI") == "HK.800000"
        assert to_futu("IDX.000300") == "SH.000300"

    def test_to_push2_idx(self):
        assert to_push2_secid("IDX.000300") == "1.000300"
        assert to_push2_secid("IDX.399001") == "0.399001"

    def test_bare_number_not_idx(self):
        """Bare 6-digit numbers should still be CN, not IDX."""
        assert normalize("000300") == "CN.000300"  # 6 digits → CN, not IDX
        assert normalize("300001") == "CN.300001"  # 6 digits → CN


class TestFromWind:
    """Tests for from_wind() — Wind format → kit standard."""

    def test_from_wind_hk(self):
        assert from_wind("00700.HK") == "HK.00700"

    def test_from_wind_cn_sh(self):
        assert from_wind("600519.SH") == "CN.600519"

    def test_from_wind_cn_sz(self):
        assert from_wind("000001.SZ") == "CN.000001"

    def test_from_wind_cn_bj(self):
        assert from_wind("430000.BJ") == "CN.430000"

    def test_from_wind_us_nasdaq(self):
        assert from_wind("AAPL.O") == "US.AAPL"

    def test_from_wind_us_nyse(self):
        assert from_wind("MSFT.N") == "US.MSFT"

    def test_from_wind_us_underscore(self):
        assert from_wind("BRK_B.N") == "US.BRK.B"

    def test_from_wind_idx_hi(self):
        assert from_wind("HSI.HI") == "IDX.HSI"

    def test_from_wind_idx_gi(self):
        assert from_wind("SPX.GI") == "IDX.SPX"

    def test_from_wind_invalid(self):
        with pytest.raises(SymbolError):
            from_wind("AAPL.XX")
