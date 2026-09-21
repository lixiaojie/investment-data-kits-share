"""Tests for ChinaMacroProvider."""
from __future__ import annotations

import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from market_data_kit.providers.china_macro_provider import (
    ChinaMacroProvider,
    _fetch_lpr,
    _fetch_pmi,
    _fetch_cpi,
    _fetch_ppi,
    _fetch_m2,
    _safe_float,
    _parse_date,
    _parse_cn_month,
)


@pytest.fixture
def provider():
    return ChinaMacroProvider()


# --- Helper mock factories ---

def _mock_lpr_df():
    """LPR DataFrame: date, LPR1Y, LPR5Y."""
    return pd.DataFrame({
        "TRADE_DATE": ["2026-03-20"],
        "LPR1Y": [3.0],
        "LPR5Y": [3.5],
    })


def _mock_pmi_df():
    """PMI DataFrame: date, 制造业PMI."""
    return pd.DataFrame({
        "月份": ["2026-03-01"],
        "制造业PMI": [53.0],
    })


def _mock_cpi_df():
    """CPI DataFrame matching akshare macro_china_cpi() format."""
    return pd.DataFrame({
        "月份": ["2026年02月份"],
        "全国-当月": [100.7],
        "全国-同比增长": [0.7],
        "全国-环比增长": [0.3],
        "全国-累计": [100.5],
    })


def _mock_ppi_df():
    """PPI DataFrame: date, 当月同比."""
    return pd.DataFrame({
        "月份": ["2026-02-01"],
        "当月同比": [-2.8],
    })


def _mock_m2_df():
    """M2 DataFrame: date, M2数量(亿元), M2同比(%)."""
    return pd.DataFrame({
        "月份": ["2026-02-01"],
        "M2数量(亿元)": [3000000.0],
        "M2同比(%)": [9.7],
    })


def _setup_ak_mock(mock_ak):
    """Configure mock akshare module with all indicator DataFrames."""
    mock_ak.macro_china_lpr.return_value = _mock_lpr_df()
    mock_ak.macro_china_pmi.return_value = _mock_pmi_df()
    mock_ak.macro_china_cpi.return_value = _mock_cpi_df()
    mock_ak.macro_china_ppi.return_value = _mock_ppi_df()
    mock_ak.macro_china_money_supply.return_value = _mock_m2_df()
    return mock_ak


# --- ChinaMacroProvider tests ---

def test_fetch_macro_returns_all_indicators(provider):
    """fetch_macro returns records for all 6 indicators (LPR 1Y+5Y, PMI, CPI, PPI, M2)."""
    mock_ak = MagicMock()
    _setup_ak_mock(mock_ak)

    with patch("market_data_kit.providers.china_macro_provider._import_ak", return_value=mock_ak):
        results = provider.fetch_macro("CN")

    assert len(results) == 6
    indicators = {r["indicator"] for r in results}
    assert indicators == {"lpr_1y", "lpr_5y", "pmi_manufacturing", "cn_cpi_yoy", "cn_ppi_yoy", "cn_m2_yoy"}


def test_fetch_macro_record_schema(provider):
    """Each record matches MacroStore schema: indicator, date, value, unit, source."""
    mock_ak = MagicMock()
    _setup_ak_mock(mock_ak)

    with patch("market_data_kit.providers.china_macro_provider._import_ak", return_value=mock_ak):
        results = provider.fetch_macro("CN")

    for r in results:
        assert "indicator" in r
        assert "date" in r
        assert "value" in r
        assert "unit" in r
        assert "source" in r
        assert r["source"] == "akshare"
        assert isinstance(r["value"], (int, float))


def test_fetch_macro_wrong_market(provider):
    """fetch_macro raises ValueError for non-CN market."""
    with pytest.raises(ValueError, match="CN"):
        provider.fetch_macro("US")


def test_fetch_macro_akshare_unavailable(provider):
    """Returns empty list when akshare is not installed."""
    with patch("market_data_kit.providers.china_macro_provider._import_ak", side_effect=ImportError("no akshare")):
        results = provider.fetch_macro("CN")
    assert results == []


def test_fetch_macro_partial_failure(provider):
    """If one indicator fails, still returns the others."""
    mock_ak = MagicMock()
    _setup_ak_mock(mock_ak)
    # Make PMI fail
    mock_ak.macro_china_pmi.side_effect = Exception("timeout")

    with patch("market_data_kit.providers.china_macro_provider._import_ak", return_value=mock_ak):
        results = provider.fetch_macro("CN")

    indicators = {r["indicator"] for r in results}
    assert "pmi_manufacturing" not in indicators
    # Should still have the other 5
    assert len(results) == 5


def test_fetch_macro_all_fail(provider):
    """Returns empty list when all fetchers fail."""
    mock_ak = MagicMock()
    mock_ak.macro_china_lpr.side_effect = Exception("fail")
    mock_ak.macro_china_pmi.side_effect = Exception("fail")
    mock_ak.macro_china_cpi.side_effect = Exception("fail")
    mock_ak.macro_china_ppi.side_effect = Exception("fail")
    mock_ak.macro_china_money_supply.side_effect = Exception("fail")

    with patch("market_data_kit.providers.china_macro_provider._import_ak", return_value=mock_ak):
        results = provider.fetch_macro("CN")

    assert results == []


# --- LPR tests ---

def test_lpr_returns_both_rates():
    """LPR fetcher returns both 1Y and 5Y."""
    mock_ak = MagicMock()
    mock_ak.macro_china_lpr.return_value = _mock_lpr_df()

    results = _fetch_lpr(mock_ak)
    assert len(results) == 2
    indicators = {r["indicator"] for r in results}
    assert indicators == {"lpr_1y", "lpr_5y"}
    for r in results:
        assert r["unit"] == "%"


def test_lpr_positional_fallback():
    """LPR falls back to positional columns when names don't match."""
    df = pd.DataFrame({
        "date": ["2026-03-20"],
        "col_a": [2.95],
        "col_b": [3.45],
    })
    mock_ak = MagicMock()
    mock_ak.macro_china_lpr.return_value = df

    results = _fetch_lpr(mock_ak)
    assert len(results) == 2
    vals = {r["indicator"]: r["value"] for r in results}
    assert vals["lpr_1y"] == 2.95
    assert vals["lpr_5y"] == 3.45


def test_lpr_empty_df():
    """LPR returns empty list for empty DataFrame."""
    mock_ak = MagicMock()
    mock_ak.macro_china_lpr.return_value = pd.DataFrame()

    results = _fetch_lpr(mock_ak)
    assert results == []


# --- PMI tests ---

def test_pmi_sanity_check_filters_bad():
    """PMI outside 20-80 range is rejected."""
    df = pd.DataFrame({
        "月份": ["2026-03-01"],
        "制造业PMI": [150.0],  # bad value
    })
    mock_ak = MagicMock()
    mock_ak.macro_china_pmi.return_value = df

    results = _fetch_pmi(mock_ak)
    assert results == []


def test_pmi_valid_value():
    mock_ak = MagicMock()
    mock_ak.macro_china_pmi.return_value = _mock_pmi_df()

    results = _fetch_pmi(mock_ak)
    assert len(results) == 1
    assert results[0]["value"] == 53.0
    assert results[0]["unit"] == ""


# --- CPI tests ---

def test_cpi_sanity_check_filters_bad():
    """CPI outside -20 to 30 range is rejected."""
    df = pd.DataFrame({
        "月份": ["2026年02月份"],
        "全国-同比增长": [50.0],  # bad
    })
    mock_ak = MagicMock()
    mock_ak.macro_china_cpi.return_value = df

    results = _fetch_cpi(mock_ak)
    assert results == []


def test_cpi_valid():
    mock_ak = MagicMock()
    mock_ak.macro_china_cpi.return_value = _mock_cpi_df()

    results = _fetch_cpi(mock_ak)
    assert len(results) == 1
    assert results[0]["indicator"] == "cn_cpi_yoy"
    assert results[0]["value"] == 0.7


# --- PPI tests ---

def test_ppi_sanity_check_filters_bad():
    """PPI outside -30 to 30 range is rejected."""
    df = pd.DataFrame({
        "月份": ["2026-02-01"],
        "当月同比": [99.0],
    })
    mock_ak = MagicMock()
    mock_ak.macro_china_ppi.return_value = df

    results = _fetch_ppi(mock_ak)
    assert results == []


def test_ppi_valid():
    mock_ak = MagicMock()
    mock_ak.macro_china_ppi.return_value = _mock_ppi_df()

    results = _fetch_ppi(mock_ak)
    assert len(results) == 1
    assert results[0]["indicator"] == "cn_ppi_yoy"
    assert results[0]["value"] == -2.8


# --- M2 tests ---

def test_m2_valid():
    mock_ak = MagicMock()
    mock_ak.macro_china_money_supply.return_value = _mock_m2_df()

    results = _fetch_m2(mock_ak)
    assert len(results) == 1
    assert results[0]["indicator"] == "cn_m2_yoy"
    assert results[0]["value"] == 9.7


def test_m2_positional_fallback():
    """M2 falls back to positional search when column names don't match."""
    df = pd.DataFrame({
        "月份": ["2026-02-01"],
        "M2(亿元)": [3000000.0],
        "unknown": [8.5],  # idx 2
    })
    mock_ak = MagicMock()
    mock_ak.macro_china_money_supply.return_value = df

    results = _fetch_m2(mock_ak)
    assert len(results) == 1
    assert results[0]["value"] == 8.5


# --- Utility tests ---

def test_safe_float():
    assert _safe_float(3.14) == 3.14
    assert _safe_float("2.5") == 2.5
    assert _safe_float(None) is None
    assert _safe_float("abc") is None


def test_parse_date_isoformat():
    d = _parse_date("2026-03-20")
    assert d == datetime.date(2026, 3, 20)


def test_parse_date_datetime():
    d = _parse_date(datetime.date(2026, 1, 15))
    assert d == datetime.date(2026, 1, 15)


def test_parse_date_timestamp():
    ts = pd.Timestamp("2026-02-01")
    d = _parse_date(ts)
    assert d == datetime.date(2026, 2, 1)


def test_parse_cn_month():
    d = _parse_cn_month("2026年02月份")
    assert d == datetime.date(2026, 2, 1)


def test_parse_cn_month_invalid():
    assert _parse_cn_month("not-a-date") is None


def test_parse_date_none():
    assert _parse_date(None) is None


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None


# --- Healthcheck ---

def test_healthcheck_ok(provider):
    with patch("market_data_kit.providers.china_macro_provider._import_ak"):
        assert provider.healthcheck() is True


def test_healthcheck_no_akshare(provider):
    with patch("market_data_kit.providers.china_macro_provider._import_ak", side_effect=ImportError):
        assert provider.healthcheck() is False
