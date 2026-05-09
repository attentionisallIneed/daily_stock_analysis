import runpy
import sys
import warnings
from types import SimpleNamespace

import pandas as pd
import pytest

import config as config_module
import data_provider.akshare_fetcher as akshare_fetcher_module
import data_provider.baostock_fetcher as baostock_fetcher_module
import data_provider.tushare_fetcher as tushare_fetcher_module
import data_provider.yfinance_fetcher as yfinance_fetcher_module
from data_provider.baostock_fetcher import BaostockFetcher
from data_provider.base import BaseFetcher, DataFetcherManager, DataFetchError
from data_provider.tushare_fetcher import TushareFetcher
from data_provider.yfinance_fetcher import YfinanceFetcher


def _raise(message):
    raise RuntimeError(message)


def test_base_fetcher_stubs_and_default_manager_sorting(monkeypatch):
    assert BaseFetcher._fetch_raw_data(object(), "000001", "2026-01-01", "2026-01-02") is None
    assert BaseFetcher._normalize_data(object(), pd.DataFrame(), "000001") is None

    class FakeFetcher:
        def __init__(self, name, priority):
            self.name = name
            self.priority = priority

        def get_daily_data(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(akshare_fetcher_module, "AkshareFetcher", lambda: FakeFetcher("ak", 1))
    monkeypatch.setattr(tushare_fetcher_module, "TushareFetcher", lambda: FakeFetcher("ts", 2))
    monkeypatch.setattr(baostock_fetcher_module, "BaostockFetcher", lambda: FakeFetcher("bs", 3))
    monkeypatch.setattr(yfinance_fetcher_module, "YfinanceFetcher", lambda: FakeFetcher("yf", 4))

    manager = DataFetcherManager()
    manager.add_fetcher(FakeFetcher("first", 0))

    assert manager.available_fetchers == ["first", "ak", "ts", "bs", "yf"]

    class UnavailableFetcher(FakeFetcher):
        is_available = False

    monkeypatch.setattr(tushare_fetcher_module, "TushareFetcher", lambda: UnavailableFetcher("ts", 2))
    manager_without_unavailable = DataFetcherManager()
    assert manager_without_unavailable.available_fetchers == ["ak", "bs", "yf"]


def test_default_manager_skips_unavailable_fetchers(monkeypatch):
    class FakeFetcher:
        def __init__(self, name, priority, is_available=True):
            self.name = name
            self.priority = priority
            self.is_available = is_available

        def get_daily_data(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(akshare_fetcher_module, "AkshareFetcher", lambda: FakeFetcher("ak", 1))
    monkeypatch.setattr(tushare_fetcher_module, "TushareFetcher", lambda: FakeFetcher("ts", 2, is_available=False))
    monkeypatch.setattr(baostock_fetcher_module, "BaostockFetcher", lambda: FakeFetcher("bs", 3))
    monkeypatch.setattr(yfinance_fetcher_module, "YfinanceFetcher", lambda: FakeFetcher("yf", 4))

    manager = DataFetcherManager()

    assert manager.available_fetchers == ["ak", "bs", "yf"]


def test_baostock_lazy_import_logout_and_wrapped_query_errors(monkeypatch):
    imported = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "baostock", imported)
    fetcher = BaostockFetcher()

    assert fetcher._get_baostock() is imported
    assert fetcher._convert_stock_code("sh.600519") == "sh.600519"

    class LogoutWarningBaostock:
        def login(self):
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            return SimpleNamespace(error_code="1", error_msg="logout warning")

    fetcher._bs_module = LogoutWarningBaostock()
    with fetcher._baostock_session():
        pass

    class LogoutRaisesBaostock(LogoutWarningBaostock):
        def logout(self):
            raise RuntimeError("logout failed")

    fetcher._bs_module = LogoutRaisesBaostock()
    with fetcher._baostock_session():
        pass

    class QueryRaisesBaostock(LogoutWarningBaostock):
        def query_history_k_data_plus(self, **kwargs):
            raise ValueError("query exploded")

    fetcher._bs_module = QueryRaisesBaostock()
    with pytest.raises(DataFetchError):
        fetcher._fetch_raw_data("600519", "2026-01-01", "2026-01-31")


def test_tushare_init_api_success_failure_and_counter_reset(monkeypatch):
    monkeypatch.setattr(
        tushare_fetcher_module,
        "get_config",
        lambda: SimpleNamespace(tushare_token="token"),
    )
    calls = []

    class FakeTushare:
        def set_token(self, token):
            calls.append(("token", token))

        def pro_api(self):
            calls.append(("pro_api",))
            return object()

    monkeypatch.setitem(sys.modules, "tushare", FakeTushare())

    fetcher = TushareFetcher()

    assert fetcher._api is not None
    assert fetcher.is_available is True
    assert calls == [("token", "token"), ("pro_api",)]

    class BrokenTushare(FakeTushare):
        def pro_api(self):
            raise RuntimeError("init down")

    monkeypatch.setitem(sys.modules, "tushare", BrokenTushare())
    failed = TushareFetcher()
    assert failed._api is None
    assert failed.is_available is False

    limiter = object.__new__(TushareFetcher)
    limiter.rate_limit_per_minute = 10
    limiter._minute_start = 0.0
    limiter._call_count = 5
    monkeypatch.setattr(tushare_fetcher_module.time, "time", lambda: 61.0)

    limiter._check_rate_limit()

    assert limiter._minute_start == 61.0
    assert limiter._call_count == 1


def test_yfinance_normalize_without_volume_uses_zero_amount():
    fetcher = YfinanceFetcher()
    raw = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.5],
        },
        index=pd.Index(pd.to_datetime(["2026-01-01"]), name="Date"),
    )

    normalized = fetcher._normalize_data(raw, "600519")

    assert normalized["amount"].tolist() == [0]
    assert normalized["code"].tolist() == ["600519"]


def test_provider_demo_entrypoints_cover_success_and_failure_paths(monkeypatch, capsys):
    col_date = "\u65e5\u671f"

    class FailingBaostock:
        fields = ["date", "open", "high", "low", "close", "volume", "amount", "pctChg"]

        def login(self):
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            return SimpleNamespace(error_code="0", error_msg="")

        def query_history_k_data_plus(self, **kwargs):
            return SimpleNamespace(error_code="1", error_msg="query failed", fields=self.fields)

    monkeypatch.setitem(sys.modules, "baostock", FailingBaostock())
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        runpy.run_module("data_provider.baostock_fetcher", run_name="__main__")

    class SuccessfulResult:
        fields = ["date", "open", "high", "low", "close", "volume", "amount", "pctChg"]

        def __init__(self):
            self.error_code = "0"
            self.error_msg = ""
            self._rows = [["2026-01-01", "10", "11", "9", "10.5", "100", "1050", "5.0"]]
            self._index = 0

        def next(self):
            has_row = self._index < len(self._rows)
            if has_row:
                self._index += 1
            return has_row

        def get_row_data(self):
            return self._rows[self._index - 1]

    class SuccessfulBaostock(FailingBaostock):
        def query_history_k_data_plus(self, **kwargs):
            return SuccessfulResult()

    monkeypatch.setitem(sys.modules, "baostock", SuccessfulBaostock())
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        runpy.run_module("data_provider.baostock_fetcher", run_name="__main__")

    tushare_df = pd.DataFrame(
        {
            "trade_date": ["20260101"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.5],
            "vol": [10.0],
            "amount": [1.5],
            "pct_chg": [5.0],
        }
    )

    class DemoTushare:
        def set_token(self, token):
            pass

        def pro_api(self):
            return SimpleNamespace(daily=lambda **kwargs: tushare_df)

    monkeypatch.setitem(sys.modules, "tushare", DemoTushare())
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    config_module.Config.reset_instance()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        runpy.run_module("data_provider.tushare_fetcher", run_name="__main__")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda **kwargs: pd.DataFrame()))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        runpy.run_module("data_provider.yfinance_fetcher", run_name="__main__")

    monkeypatch.setattr(
        sys.modules["yfinance"],
        "download",
        lambda **kwargs: pd.DataFrame(
            {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.5]},
            index=pd.Index(pd.to_datetime(["2026-01-01"]), name="Date"),
        ),
    )
    normalized = YfinanceFetcher()._normalize_data(
        pd.DataFrame(
            {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.5]},
            index=pd.Index(pd.to_datetime(["2026-01-01"]), name="Date"),
        ),
        "600519",
    )

    output = capsys.readouterr().out
    assert "query failed" in output
    assert "获取成功" in output
    assert "获取失败" in output
    assert normalized["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01"]
