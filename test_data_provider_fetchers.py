from types import SimpleNamespace

import pandas as pd
import pytest

import data_provider.tushare_fetcher as tushare_module
from data_provider.baostock_fetcher import BaostockFetcher
from data_provider.base import DataFetchError
from data_provider.tushare_fetcher import TushareFetcher
from data_provider.yfinance_fetcher import YfinanceFetcher


def test_yfinance_converts_codes_and_normalizes_downloaded_data():
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("600519") == "600519.SS"
    assert fetcher._convert_stock_code("000001") == "000001.SZ"
    assert fetcher._convert_stock_code("600519.ss") == "600519.SS"
    assert fetcher._convert_stock_code("123456") == "123456.SZ"

    raw = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.5],
            "Close": [10.0, 11.0],
            "Volume": [100, 200],
        },
        index=pd.Index(pd.to_datetime(["2026-01-01", "2026-01-02"]), name="Date"),
    )

    normalized = fetcher._normalize_data(raw, "600519")

    assert normalized["code"].tolist() == ["600519", "600519"]
    assert normalized["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02"]
    assert normalized["pct_chg"].tolist() == [0.0, 10.0]
    assert normalized["amount"].tolist() == [1000.0, 2200.0]


def test_tushare_converts_codes_normalizes_data_and_rate_limits(monkeypatch):
    fetcher = object.__new__(TushareFetcher)

    assert fetcher._convert_stock_code("600519") == "600519.SH"
    assert fetcher._convert_stock_code("000001") == "000001.SZ"
    assert fetcher._convert_stock_code("600519.sh") == "600519.SH"
    assert fetcher._convert_stock_code("123456") == "123456.SZ"

    raw = pd.DataFrame(
        {
            "trade_date": ["20260101", "20260102"],
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.5, 10.5],
            "close": [10.0, 11.0],
            "vol": [10, 20],
            "amount": [1.5, 2.5],
            "pct_chg": [0.0, 1.0],
        }
    )

    normalized = fetcher._normalize_data(raw, "000001")

    assert normalized["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02"]
    assert normalized["volume"].tolist() == [1000, 2000]
    assert normalized["amount"].tolist() == [1500.0, 2500.0]

    fetcher.rate_limit_per_minute = 1
    fetcher._minute_start = None
    fetcher._call_count = 0
    times = iter([100.0, 101.0, 162.0])
    sleeps = []
    monkeypatch.setattr(tushare_module.time, "time", lambda: next(times))
    monkeypatch.setattr(tushare_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    fetcher._check_rate_limit()
    fetcher._check_rate_limit()

    assert sleeps == [60.0]
    assert fetcher._call_count == 1
    assert fetcher._minute_start == 162.0


def test_baostock_converts_codes_normalizes_data_and_manages_session():
    fetcher = BaostockFetcher()

    assert fetcher._convert_stock_code("600519") == "sh.600519"
    assert fetcher._convert_stock_code("000001") == "sz.000001"
    assert fetcher._convert_stock_code("SH.600519") == "sz.SH.600519"
    assert fetcher._convert_stock_code("123456") == "sz.123456"

    raw = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "open": ["10.0", "11.0"],
            "high": ["11.0", "12.0"],
            "low": ["9.5", "10.5"],
            "close": ["10.0", "11.0"],
            "volume": ["100", "200"],
            "amount": ["1000", "2200"],
            "pctChg": ["0.0", "1.0"],
        }
    )

    normalized = fetcher._normalize_data(raw, "000001")

    assert normalized["code"].tolist() == ["000001", "000001"]
    assert normalized["pct_chg"].tolist() == [0.0, 1.0]
    assert normalized["volume"].tolist() == [100, 200]

    calls = []

    class FakeBaostock:
        def login(self):
            calls.append("login")
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            calls.append("logout")
            return SimpleNamespace(error_code="0", error_msg="")

    fetcher._bs_module = FakeBaostock()

    with fetcher._baostock_session() as bs:
        assert bs is fetcher._bs_module

    assert calls == ["login", "logout"]


def test_baostock_session_raises_on_login_failure_and_still_logs_out():
    fetcher = BaostockFetcher()
    calls = []

    class FakeBaostock:
        def login(self):
            calls.append("login")
            return SimpleNamespace(error_code="1", error_msg="bad login")

        def logout(self):
            calls.append("logout")
            return SimpleNamespace(error_code="0", error_msg="")

    fetcher._bs_module = FakeBaostock()

    with pytest.raises(DataFetchError) as excinfo:
        with fetcher._baostock_session():
            pass

    assert "bad login" in str(excinfo.value)
    assert calls == ["login", "logout"]
