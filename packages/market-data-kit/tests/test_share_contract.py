from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

import market_data_kit as kit


def bars(end=None, adjust="none", count=5):
    end = end or date.today()
    return pd.DataFrame([{"symbol": "US.AAPL", "date": end - timedelta(days=n),
                          "open": 10., "high": 11., "low": 9., "close": 10.,
                          "volume": 100, "adjust": adjust} for n in reversed(range(count))])


def test_push2_preserves_recipient_proxy_settings(monkeypatch):
    import io
    import urllib.request
    from market_data_kit.providers.push2 import _fetch_json

    configured = {"http": "http://proxy.example:8080"}
    monkeypatch.setattr(urllib.request, "getproxies", lambda: configured)
    observed = []

    def fake_open(opener, request, timeout):
        observed.extend(handler.proxies for handler in opener.handlers
                        if isinstance(handler, urllib.request.ProxyHandler))
        return io.BytesIO(b'{"data": {}}')

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    assert _fetch_json("http://example.com/data") == {"data": {}}
    assert observed == [configured]


def provider(monkeypatch, response=None, error=None):
    mock = Mock()
    mock.fetch_klines.side_effect = error
    mock.fetch_klines.return_value = bars() if response is None else response
    monkeypatch.setattr(kit, "get_provider", lambda _: mock)
    return mock


def test_qfq_reaches_provider_and_cache_is_separate(monkeypatch):
    mock = provider(monkeypatch, bars(adjust="qfq"))
    df = kit.load_klines("AAPL", days=5, adjust="qfq")
    assert mock.fetch_klines.call_args.kwargs == {"adjust": "qfq"}
    assert df.attrs["adjust"] == "qfq"
    mock.fetch_klines.return_value = bars()
    kit.load_klines("AAPL", days=5, adjust="none")
    assert mock.fetch_klines.call_count == 2


def test_cache_keeps_provenance_after_reset(monkeypatch):
    provider(monkeypatch)
    first = kit.load_klines("AAPL", days=5)
    kit.reset()
    mock = provider(monkeypatch, error=RuntimeError("offline"))
    cached = kit.load_klines("AAPL", days=5)
    assert cached.attrs["cache_hit"] is True
    assert cached.attrs["provider"] == "yfinance"
    assert cached.attrs["fetched_at"] == first.attrs["fetched_at"]
    mock.fetch_klines.assert_not_called()


def test_expired_source_rejected_and_explicitly_labeled(monkeypatch):
    provider(monkeypatch, bars(date.today() - timedelta(days=20)))
    with pytest.raises(kit.StaleDataError):
        kit.load_klines("AAPL", days=5)
    with pytest.warns(RuntimeWarning):
        df = kit.load_klines("AAPL", days=5, allow_stale=True)
    assert df.attrs["stale"] is True
    assert df.attrs["refresh_failed"] is True


def test_refresh_failure_is_not_silently_hidden(monkeypatch):
    provider(monkeypatch)
    kit.load_klines("AAPL", days=5)
    provider(monkeypatch, error=RuntimeError("offline"))
    with pytest.raises(kit.ProviderUnavailableError):
        kit.load_klines("AAPL", days=5, refresh=True)
    with pytest.warns(RuntimeWarning):
        df = kit.load_klines("AAPL", days=5, refresh=True, allow_stale=True)
    assert df.attrs["refresh_failed"] and df.attrs["cache_hit"]


def test_wrong_adjustment_rejected(monkeypatch):
    provider(monkeypatch, bars(adjust="qfq"))
    with pytest.raises(kit.ProviderUnavailableError):
        kit.load_klines("AAPL", adjust="none")


def test_empty_provider_falls_through(monkeypatch):
    empty = SimpleNamespace(fetch_klines=lambda *a, **k: pd.DataFrame())
    valid = SimpleNamespace(fetch_klines=lambda *a, **k: bars())
    monkeypatch.setattr(kit, "get_provider", lambda name: empty if name == "yfinance" else valid)
    assert kit.load_klines("AAPL", days=5).attrs["provider"] == "akshare"


def test_unknown_provider_rejected_without_writes(tmp_path):
    root = tmp_path / "unused"
    with pytest.raises(ValueError):
        kit.init(providers=("unknown",), data_root=root)
    assert not root.exists()


def test_stub_data_never_written_or_read_as_real(tmp_path):
    kit.init(data_root=tmp_path, use_stubs=True)
    df = kit.load_klines("AAPL", days=5, adjust="qfq")
    assert df.attrs["simulated"] and df.attrs["provider"] == "stub"
    assert not list(tmp_path.rglob("*.parquet"))
    with pytest.raises(ValueError):
        kit.init(providers=("stub",))


def test_historical_end_date_uses_requested_freshness(monkeypatch):
    end = date.today() - timedelta(days=100)
    provider(monkeypatch, bars(end))
    assert not kit.load_klines("AAPL", days=5, end_date=end).attrs["stale"]


def test_short_history_and_rows_are_explicit(monkeypatch):
    provider(monkeypatch, bars(count=5))
    result = kit.load_klines("AAPL", days=120)
    assert result.attrs["complete"] is False
    assert result.attrs["returned_rows"] == 5


def test_doctor_does_not_fetch(monkeypatch):
    monkeypatch.setattr(kit, "get_provider", lambda _: pytest.fail("doctor must not connect"))
    assert kit.run_doctor()["live_verified"] is False


@pytest.mark.parametrize("adjust", ["qfq", "hfq"])
def test_yahoo_does_not_claim_cn_adjustment(adjust):
    from market_data_kit.providers.yfinance_provider import YfinanceProvider
    with pytest.raises(NotImplementedError):
        YfinanceProvider().fetch_klines("US.AAPL", 5, adjust=adjust)


def test_public_snapshot_has_provenance_without_realtime_claim(monkeypatch):
    mock = SimpleNamespace(fetch_snapshot=lambda syms: [{"symbol": syms[0], "last_price": 10}])
    monkeypatch.setattr(kit, "get_provider", lambda _: mock)
    row = kit.snapshot(["AAPL"])[0]
    assert row["provider"] == "yfinance"
    assert row["as_of"] is None and row["realtime_verified"] is False


@pytest.mark.parametrize("adjust,expected", [("none",0),("qfq",1),("hfq",2)])
def test_push2_forwards_adjustment(monkeypatch, adjust, expected):
    from market_data_kit.providers import push2
    calls = []
    def fetch(url):
        calls.append(url)
        return {"data": {"klines": ["2026-01-01,10,10,11,9,20,20000,1,0,0,0"]}}
    monkeypatch.setattr(push2, "_fetch_json", fetch)
    df = push2.Push2Provider().fetch_klines("CN.600519", 5, end_date=date(2026, 1, 1), adjust=adjust)
    assert f"fqt={expected}" in calls[0]
    assert df.adjust.iloc[0] == adjust


def test_futu_passes_explicit_autype(monkeypatch):
    from market_data_kit.providers import futu_provider as fp
    sdk = SimpleNamespace(KLType=SimpleNamespace(K_DAY="daily"),
                          AuType=SimpleNamespace(NONE="raw", QFQ="forward", HFQ="backward"), RET_OK=0)
    ctx = Mock()
    ctx.request_history_kline.return_value = (0, pd.DataFrame({"time_key":[str(date.today())]}), None)
    monkeypatch.setattr(fp, "_import_futu", lambda: sdk)
    monkeypatch.setattr(fp.time, "sleep", lambda _: None)
    p = fp.FutuProvider()
    p._ctx = ctx
    monkeypatch.setattr(p, "_map_kline_columns", lambda *args: bars())
    assert p.fetch_klines("US.AAPL", 5, adjust="hfq").adjust.eq("hfq").all()
    assert ctx.request_history_kline.call_args.kwargs["autype"] == "backward"


def test_allow_stale_selects_freshest_candidate(monkeypatch):
    def p(name):
        gap = 4 if name == 'yfinance' else 20
        return SimpleNamespace(fetch_klines=lambda *a, **k: bars(date.today()-timedelta(days=gap)))
    monkeypatch.setattr(kit, 'get_provider', p)
    with pytest.warns(RuntimeWarning):
        result = kit.load_klines('AAPL', 5, allow_stale=True)
    assert result.attrs['provider'] == 'yfinance'
    assert result.attrs['as_of'] == (date.today()-timedelta(days=4)).isoformat()


def test_push2_keeps_trading_rows_not_calendar_days(monkeypatch):
    from market_data_kit.providers import push2
    end = date(2026, 9, 18)
    dates = pd.bdate_range(end=end, periods=30)
    raw = [f'{d.date()},10,10,11,9,20,20000,1,0,0,0' for d in dates]
    monkeypatch.setattr(push2, '_fetch_json', lambda _: {'data': {'klines': raw}})
    assert len(push2.Push2Provider().fetch_klines('CN.600519', 30, end_date=end)) == 30


@pytest.mark.parametrize('method,api,field',[
    ('fetch_balance_sheet','stock_balance_sheet_by_report_em','TOTAL_ASSETS'),
    ('fetch_income_statement','stock_profit_sheet_by_report_em','NETPROFIT'),
    ('fetch_cash_flow_statement','stock_cash_flow_sheet_by_report_em','NETCASH_OPERATE'),
])
def test_financial_reports_use_exchange_and_actual_date(monkeypatch, method, api, field):
    from market_data_kit.providers import akshare_provider as ak
    sdk = Mock()
    getattr(sdk, api).return_value = pd.DataFrame([{'REPORT_DATE':'2025-12-31 00:00:00', 'REPORT_DATE_NAME':'2025年报', field:0}])
    monkeypatch.setattr(ak, '_import_ak', lambda: sdk)
    result = getattr(ak.AkshareProvider(),method)('CN.600519')
    assert result[0]['period'] == '2025Q4'
    assert getattr(sdk, api).call_args.kwargs['symbol'] == 'SH600519'
    key = {'TOTAL_ASSETS':'total_assets','NETPROFIT':'net_income','NETCASH_OPERATE':'operating_cf'}[field]
    assert result[0][key] == 0


def test_total_assets_never_become_market_cap(monkeypatch):
    from market_data_kit.providers import akshare_provider as ak
    sdk = Mock()
    sdk.stock_a_lg_indicator.return_value = pd.DataFrame([{'总资产(元)':1e9}])
    monkeypatch.setattr(ak, '_import_ak', lambda: sdk)
    assert pd.isna(ak.AkshareProvider().fetch_fundamentals('CN.600519')['market_cap'])


def test_cn_volume_converted_to_shares(monkeypatch):
    from market_data_kit.providers import push2
    monkeypatch.setattr(push2, '_fetch_json', lambda _: {'data':{'klines':['2026-01-01,10,10,11,9,20,20000,1,0,0,0']}})
    df=push2.Push2Provider().fetch_klines('CN.600519',5,end_date=date(2026,1,1))
    assert df.volume.iloc[0] == 2000


def test_yahoo_annual_statements_have_period_type(monkeypatch):
    from market_data_kit.providers import yfinance_provider as yf
    ticker = SimpleNamespace(income_stmt=pd.DataFrame({'2025-12-31':{'Total Revenue':400}}), cash_flow=pd.DataFrame({'2025-12-31':{'Operating Cash Flow':200}}))
    monkeypatch.setattr(yf,'_import_yfinance',lambda:SimpleNamespace(Ticker=lambda _:ticker))
    income=yf.YfinanceProvider().fetch_income_statement('US.AAPL')[0]
    cash=yf.YfinanceProvider().fetch_cash_flow_statement('US.AAPL')[0]
    assert income['period_type'] == cash['period_type'] == 'annual'
    assert income['period_end'] == cash['period_end'] == '2025-12-31'


def test_commodity_unknown_quote_time_not_stamped_today(monkeypatch):
    from market_data_kit.providers import commodity_provider as cp
    ticker=SimpleNamespace(fast_info=SimpleNamespace(last_price=100,previous_close=99))
    monkeypatch.setattr(cp,'_import_yf',lambda:SimpleNamespace(Ticker=lambda _:ticker))
    rows=cp.CommodityProvider().fetch_commodity_prices({'GC=F': {'unit':'USD'}})
    assert rows[0]['date'] is None and rows[0]['as_of'] is None
