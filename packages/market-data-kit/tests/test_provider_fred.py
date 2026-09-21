"""Tests for FredProvider."""

from __future__ import annotations

import datetime
import io
import json
from unittest.mock import patch, MagicMock

import pytest

from market_data_kit.providers.fred_provider import (
    FredProvider,
    _latest_value,
    _calc_yoy_pct,
    _SERIES,
    _YOY_SERIES,
)


# ── Fixtures ────────────────────────────────────────────────────


def _make_obs(date: str, value: str) -> dict[str, str]:
    return {"date": date, "value": value}


def _make_fred_response(observations: list[dict[str, str]]) -> bytes:
    return json.dumps({"observations": observations}).encode("utf-8")


def _mock_urlopen(responses: dict[str, bytes]):
    """Return a side_effect function that dispatches by series_id in URL."""

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for series_id, body in responses.items():
            if f"series_id={series_id}" in url:
                resp = MagicMock()
                resp.read.return_value = body
                resp.__enter__ = lambda s: s
                resp.__exit__ = MagicMock(return_value=False)
                return resp
        raise ConnectionError(f"Unexpected URL: {url}")

    return side_effect


# ── Unit tests: helper functions ────────────────────────────────


class TestLatestValue:
    def test_returns_first_valid(self):
        obs = [
            _make_obs("2026-03-28", "."),
            _make_obs("2026-03-27", "4.33"),
            _make_obs("2026-03-26", "4.30"),
        ]
        value, date = _latest_value(obs)
        assert value == 4.33
        assert date == "2026-03-27"

    def test_all_dots_returns_none(self):
        obs = [_make_obs("2026-03-28", "."), _make_obs("2026-03-27", ".")]
        value, date = _latest_value(obs)
        assert value is None
        assert date is None

    def test_empty_list(self):
        value, date = _latest_value([])
        assert value is None
        assert date is None

    def test_non_numeric_skipped(self):
        obs = [_make_obs("2026-03-28", "N/A"), _make_obs("2026-03-27", "3.50")]
        value, date = _latest_value(obs)
        assert value == 3.50
        assert date == "2026-03-27"


class TestCalcYoyPct:
    def test_cpi_yoy_calculation(self):
        """CPI 315.0 in 2026-02, 305.0 in 2025-02 → (315-305)/305*100 = 3.28%."""
        obs = [
            _make_obs("2026-02-01", "315.0"),
            _make_obs("2026-01-01", "314.0"),
            _make_obs("2025-12-01", "312.0"),
            _make_obs("2025-11-01", "311.0"),
            _make_obs("2025-10-01", "310.5"),
            _make_obs("2025-09-01", "310.0"),
            _make_obs("2025-08-01", "309.5"),
            _make_obs("2025-07-01", "309.0"),
            _make_obs("2025-06-01", "308.5"),
            _make_obs("2025-05-01", "308.0"),
            _make_obs("2025-04-01", "307.5"),
            _make_obs("2025-03-01", "306.5"),
            _make_obs("2025-02-01", "305.0"),
            _make_obs("2025-01-01", "304.0"),
        ]
        value, date = _calc_yoy_pct(obs)
        assert value == pytest.approx(3.28, abs=0.01)
        assert date == "2026-02-01"

    def test_skips_dots(self):
        obs = [
            _make_obs("2026-03-01", "."),
            _make_obs("2026-02-01", "315.0"),
            _make_obs("2025-02-01", "305.0"),
        ]
        value, date = _calc_yoy_pct(obs)
        assert value == pytest.approx(3.28, abs=0.01)
        assert date == "2026-02-01"

    def test_not_enough_data(self):
        obs = [_make_obs("2026-02-01", "315.0")]
        value, date = _calc_yoy_pct(obs)
        assert value is None

    def test_zero_base_returns_none(self):
        obs = [
            _make_obs("2026-02-01", "315.0"),
            _make_obs("2025-02-01", "0"),
        ]
        value, date = _calc_yoy_pct(obs)
        assert value is None


# ── Integration tests: FredProvider ─────────────────────────────


class TestFredProviderFetchMacro:
    def _build_responses(self) -> dict[str, bytes]:
        """Build mock responses for all 9 FRED series."""
        return {
            "DFF": _make_fred_response([
                _make_obs("2026-03-28", "4.33"),
                _make_obs("2026-03-27", "4.33"),
            ]),
            "DGS10": _make_fred_response([
                _make_obs("2026-03-28", "4.25"),
            ]),
            "DGS2": _make_fred_response([
                _make_obs("2026-03-28", "3.95"),
            ]),
            "T10Y2Y": _make_fred_response([
                _make_obs("2026-03-28", "0.30"),
            ]),
            "CPIAUCSL": _make_fred_response([
                _make_obs("2026-02-01", "315.0"),
                _make_obs("2026-01-01", "314.0"),
                _make_obs("2025-12-01", "312.0"),
                _make_obs("2025-11-01", "311.0"),
                _make_obs("2025-10-01", "310.5"),
                _make_obs("2025-09-01", "310.0"),
                _make_obs("2025-08-01", "309.5"),
                _make_obs("2025-07-01", "309.0"),
                _make_obs("2025-06-01", "308.5"),
                _make_obs("2025-05-01", "308.0"),
                _make_obs("2025-04-01", "307.5"),
                _make_obs("2025-03-01", "306.5"),
                _make_obs("2025-02-01", "305.0"),
                _make_obs("2025-01-01", "304.0"),
            ]),
            "PCEPI": _make_fred_response([
                _make_obs("2026-02-01", "125.0"),
                _make_obs("2026-01-01", "124.5"),
                _make_obs("2025-12-01", "124.0"),
                _make_obs("2025-11-01", "123.5"),
                _make_obs("2025-10-01", "123.0"),
                _make_obs("2025-09-01", "122.8"),
                _make_obs("2025-08-01", "122.5"),
                _make_obs("2025-07-01", "122.2"),
                _make_obs("2025-06-01", "122.0"),
                _make_obs("2025-05-01", "121.7"),
                _make_obs("2025-04-01", "121.5"),
                _make_obs("2025-03-01", "121.0"),
                _make_obs("2025-02-01", "121.5"),
                _make_obs("2025-01-01", "121.0"),
            ]),
            "UNRATE": _make_fred_response([
                _make_obs("2026-02-01", "3.9"),
            ]),
            "PAYEMS": _make_fred_response([
                _make_obs("2026-02-01", "157500"),
            ]),
            "DTWEXBGS": _make_fred_response([
                _make_obs("2026-03-28", "123.45"),
            ]),
        }

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_returns_all_9_indicators(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        assert len(results) == 9
        names = {r["indicator"] for r in results}
        expected = set(_SERIES.keys())
        assert names == expected

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_record_schema(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        for rec in results:
            assert set(rec.keys()) == {"indicator", "date", "value", "unit", "source"}
            assert isinstance(rec["date"], datetime.date)
            assert isinstance(rec["value"], float)
            assert rec["source"] == "fred"

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_cpi_yoy_value(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        cpi = next(r for r in results if r["indicator"] == "cpi_yoy")
        # (315 - 305) / 305 * 100 = 3.28
        assert cpi["value"] == pytest.approx(3.28, abs=0.01)
        assert cpi["unit"] == "%"
        assert cpi["date"] == datetime.date(2026, 2, 1)

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_pce_yoy_value(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        pce = next(r for r in results if r["indicator"] == "pce_yoy")
        # (125 - 121.5) / 121.5 * 100 = 2.88
        assert pce["value"] == pytest.approx(2.88, abs=0.01)

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_rate_series_value(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        ffr = next(r for r in results if r["indicator"] == "fed_funds_rate")
        assert ffr["value"] == 4.33
        assert ffr["unit"] == "%"
        assert ffr["date"] == datetime.date(2026, 3, 28)

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_units_correct(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_urlopen(self._build_responses())
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        units = {r["indicator"]: r["unit"] for r in results}
        assert units["nonfarm_payrolls"] == "千人"
        assert units["usd_index"] == "index"
        assert units["fed_funds_rate"] == "%"

    def test_missing_api_key_returns_empty(self):
        provider = FredProvider(api_key="")
        results = provider.fetch_macro(market="US")
        assert results == []

    def test_non_us_market_returns_empty(self):
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="CN")
        assert results == []

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_partial_failure_returns_successful(self, mock_urlopen):
        """If some series fail, still return the ones that succeed."""
        responses = {
            "DFF": _make_fred_response([_make_obs("2026-03-28", "4.33")]),
        }
        # Other series will raise ConnectionError
        mock_urlopen.side_effect = _mock_urlopen(responses)
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        assert len(results) == 1
        assert results[0]["indicator"] == "fed_funds_rate"

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_all_failures_returns_empty_and_trips_breaker(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionError("network down")
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        assert results == []
        # Circuit breaker should have recorded a failure
        assert provider._cb._failure_count >= 1

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_circuit_breaker_blocks_when_open(self, mock_urlopen):
        provider = FredProvider(api_key="test-key")
        # Trip the circuit breaker manually
        for _ in range(3):
            provider._cb.record_failure()
        assert provider._cb.state == "open"

        results = provider.fetch_macro(market="US")
        assert results == []
        # Should not have made any HTTP calls
        mock_urlopen.assert_not_called()

    def test_healthcheck_with_key(self):
        provider = FredProvider(api_key="test-key")
        assert provider.healthcheck() is True

    def test_healthcheck_without_key(self):
        provider = FredProvider(api_key="")
        assert provider.healthcheck() is False

    @patch("market_data_kit.providers.fred_provider.urllib.request.urlopen")
    def test_dot_values_skipped(self, mock_urlopen):
        """FRED returns '.' for missing data points — these should be skipped."""
        responses = {
            "DFF": _make_fred_response([
                _make_obs("2026-03-28", "."),
                _make_obs("2026-03-27", "."),
                _make_obs("2026-03-26", "."),
                _make_obs("2026-03-25", "."),
                _make_obs("2026-03-24", "."),
            ]),
        }
        # Only DFF available, rest will raise ConnectionError
        mock_urlopen.side_effect = _mock_urlopen(responses)
        provider = FredProvider(api_key="test-key")
        results = provider.fetch_macro(market="US")

        # DFF had all dots, so no result for it
        names = {r["indicator"] for r in results}
        assert "fed_funds_rate" not in names
