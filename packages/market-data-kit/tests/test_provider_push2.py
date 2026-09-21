"""Tests for push2 provider."""
import datetime
import json
import pytest
from unittest.mock import patch, MagicMock
from market_data_kit.providers.push2 import Push2Provider


# Fixture: snapshot response
SNAP_FIXTURE = {
    "data": {
        "diff": [
            {
                "f2": 15.35, "f3": 2.5, "f5": 500000, "f6": 7700000.0,
                "f7": 1.31, "f8": 0.37, "f9": 18.5, "f12": "000001",
                "f13": 0, "f14": "\u5e73\u5b89\u94f6\u884c", "f15": 15.50, "f16": 15.20,
                "f17": 15.30, "f18": 14.97, "f20": 300000000000.0,
                "f21": 290000000000.0, "f23": 0.85,
            }
        ]
    }
}

# Fixture: kline response
KLINE_FIXTURE = {
    "data": {
        "klines": [
            "2026-03-27,15.20,15.30,15.40,15.10,400000,6100000.0,1.98,1.0,0.15,0.30",
            "2026-03-28,15.30,15.45,15.50,15.20,500000,7700000.0,1.31,0.98,0.15,0.37",
        ]
    }
}

# Fixture: capital flow response
FLOW_FIXTURE = {
    "data": {
        "klines": [
            "2026-04-07,112301855.0,-51019523.0,-14285851.0,51141283.0,-102160806.0,1.0,-0.5,-0.1,0.5,-1.0,10.5,0.5,0.0,0.0",
            "2026-04-08,99590184.0,-60823838.0,-38766352.0,40746616.0,58843568.0,1.1,-0.7,-0.4,0.5,0.6,11.0,0.3,0.0,0.0",
            "2026-04-09,-30314508.0,-37481557.0,67796066.0,20898638.0,-51213146.0,-0.5,-0.6,1.0,0.3,-0.8,11.1,-0.1,0.0,0.0",
        ]
    }
}


class TestPush2Snapshot:
    @patch("market_data_kit.providers.push2._fetch_json")
    def test_basic_snapshot(self, mock_fetch):
        mock_fetch.return_value = SNAP_FIXTURE
        provider = Push2Provider()
        result = provider.fetch_snapshot(["CN.000001"])
        assert len(result) == 1
        assert result[0]["last_price"] == 15.35
        assert result[0]["pct_change"] == 2.5
        assert result[0]["name"] == "\u5e73\u5b89\u94f6\u884c"
        assert result[0]["market_cap"] == 300000000000.0

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_hk_symbols_skipped(self, mock_fetch):
        mock_fetch.return_value = {"data": {"diff": []}}
        provider = Push2Provider()
        result = provider.fetch_snapshot(["HK.00700"])
        assert result == []

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_empty_response(self, mock_fetch):
        mock_fetch.return_value = {"data": {"diff": []}}
        provider = Push2Provider()
        result = provider.fetch_snapshot(["CN.600519"])
        assert result == []


class TestPush2Klines:
    @patch("market_data_kit.providers.push2._fetch_json")
    def test_cn_klines(self, mock_fetch):
        mock_fetch.return_value = KLINE_FIXTURE
        provider = Push2Provider()
        result = provider.fetch_klines("CN.000001", days=30, end_date=datetime.date(2026, 3, 28), adjust="qfq")
        assert len(result) == 2
        assert result.iloc[-1]["close"] == 15.45
        assert result.iloc[-1]["symbol"] == "CN.000001"
        assert result.iloc[-1]["exchange"] == "SZ"
        assert result.iloc[-1]["adjust"] == "qfq"

    def test_hk_raises_not_implemented(self):
        provider = Push2Provider()
        with pytest.raises(NotImplementedError):
            provider.fetch_klines("HK.00700", days=30)

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_empty_klines(self, mock_fetch):
        mock_fetch.return_value = {"data": None}
        provider = Push2Provider()
        result = provider.fetch_klines("CN.600519", days=30)
        assert len(result) == 0


class TestPush2CapitalFlow:
    @patch("market_data_kit.providers.push2._fetch_json")
    def test_cn_capital_flow(self, mock_fetch):
        mock_fetch.return_value = FLOW_FIXTURE
        provider = Push2Provider()
        result = provider.fetch_capital_flow("CN.000001", days=5)
        assert len(result) == 3
        assert list(result.columns) == ["symbol", "date", "main_in", "super_in", "big_in", "mid_in", "small_in"]
        assert result.iloc[-1]["symbol"] == "CN.000001"
        assert result.iloc[-1]["date"] == datetime.date(2026, 4, 9)

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_hk_capital_flow(self, mock_fetch):
        mock_fetch.return_value = FLOW_FIXTURE
        provider = Push2Provider()
        result = provider.fetch_capital_flow("HK.00700", days=5)
        assert len(result) == 3
        assert result.iloc[0]["symbol"] == "HK.00700"

    def test_us_raises_not_implemented(self):
        provider = Push2Provider()
        with pytest.raises(NotImplementedError):
            provider.fetch_capital_flow("US.AAPL")

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_empty_flow(self, mock_fetch):
        mock_fetch.return_value = {"data": None}
        provider = Push2Provider()
        result = provider.fetch_capital_flow("CN.600519", days=5)
        assert len(result) == 0


class TestPush2Misc:
    def test_plates_not_implemented(self):
        provider = Push2Provider()
        with pytest.raises(NotImplementedError):
            provider.fetch_plates("CN.000001")

    @patch("market_data_kit.providers.push2._fetch_json")
    def test_healthcheck(self, mock_fetch):
        mock_fetch.return_value = {"data": {"diff": []}}
        provider = Push2Provider()
        assert provider.healthcheck() is True
