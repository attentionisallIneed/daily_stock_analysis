import runpy
import sys
import time
import warnings
from types import SimpleNamespace

import akshare as ak
import pandas as pd
import pytest

import data_provider.akshare_fetcher as akshare_module
from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.base import DataFetchError


COL_CODE = "\u4ee3\u7801"
COL_NAME = "\u540d\u79f0"
COL_PRICE = "\u6700\u65b0\u4ef7"
COL_CHANGE = "\u6da8\u8dcc\u5e45"
COL_CHANGE_AMOUNT = "\u6da8\u8dcc\u989d"
COL_VOLUME_RATIO = "\u91cf\u6bd4"
COL_TURNOVER = "\u6362\u624b\u7387"
COL_AMPLITUDE = "\u632f\u5e45"
COL_PE = "\u5e02\u76c8\u7387-\u52a8\u6001"
COL_PB = "\u5e02\u51c0\u7387"
COL_TOTAL_MV = "\u603b\u5e02\u503c"
COL_CIRC_MV = "\u6d41\u901a\u5e02\u503c"
COL_60D_CHANGE = "60\u65e5\u6da8\u8dcc\u5e45"
COL_52W_HIGH = "52\u5468\u6700\u9ad8"
COL_52W_LOW = "52\u5468\u6700\u4f4e"
COL_CHIP_DATE = "\u65e5\u671f"
COL_PROFIT_RATIO = "\u83b7\u5229\u6bd4\u4f8b"
COL_AVG_COST = "\u5e73\u5747\u6210\u672c"
COL_COST_90_LOW = "90\u6210\u672c-\u4f4e"
COL_COST_90_HIGH = "90\u6210\u672c-\u9ad8"
COL_CONCENTRATION_90 = "90\u96c6\u4e2d\u5ea6"
COL_COST_70_LOW = "70\u6210\u672c-\u4f4e"
COL_COST_70_HIGH = "70\u6210\u672c-\u9ad8"
COL_CONCENTRATION_70 = "70\u96c6\u4e2d\u5ea6"


def _quiet_fetcher():
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    fetcher._set_random_user_agent = lambda: None
    fetcher._enforce_rate_limit = lambda: None
    return fetcher


def _raise(message):
    raise RuntimeError(message)


def test_akshare_empty_and_exception_provider_branches(monkeypatch):
    fetcher = _quiet_fetcher()

    def mixed_fetch(api_name, fetch_func):
        if api_name == "ak.stock_board_industry_name_em":
            return pd.DataFrame()
        if api_name == "ak.stock_board_concept_name_em":
            raise RuntimeError("concept down")
        if api_name in {
            "ak.stock_board_industry_cons_em",
            "ak.stock_board_concept_cons_em",
        }:
            return pd.DataFrame()
        raise AssertionError(api_name)

    fetcher._fetch_with_retry = mixed_fetch
    assert fetcher.get_hot_sectors(sector_count=3, include_concepts=True) == []
    assert fetcher.get_sector_constituents("empty", sector_type="industry") == []

    fetcher._fetch_with_retry = lambda api_name, fetch_func: pd.DataFrame()
    with pytest.raises(DataFetchError):
        fetcher.get_sector_daily_data("empty", sector_type="industry", end_date=None, start_date=None)
    with pytest.raises(DataFetchError):
        fetcher.get_index_daily_data("000300", end_date=None, start_date=None)

    fetcher._fetch_with_retry = lambda api_name, fetch_func: _raise(api_name)
    assert fetcher.get_cninfo_announcements("600519") == []
    assert fetcher.get_financial_indicators("600519") == []
    assert fetcher.get_restricted_release_queue("600519") == []
    assert fetcher.get_stock_name("600519") == ""

    monkeypatch.setattr(fetcher, "get_daily_data", lambda stock_code, days=60: _raise("daily down"))
    monkeypatch.setattr(fetcher, "get_realtime_quote", lambda stock_code: None)
    monkeypatch.setattr(fetcher, "get_chip_distribution", lambda stock_code: None)
    enhanced = fetcher.get_enhanced_data("600519", days=5)

    assert enhanced == {
        "code": "600519",
        "daily_data": None,
        "realtime_quote": None,
        "chip_distribution": None,
    }


def test_akshare_realtime_and_chip_failure_fallbacks():
    fetcher = _quiet_fetcher()
    akshare_module._realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    akshare_module._etf_realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})

    bad_number = pd.NA
    invalid_number = "not-a-number"

    def stock_fetch(api_name, fetch_func):
        assert api_name == "ak.stock_zh_a_spot_em"
        return pd.DataFrame(
            {
                COL_CODE: ["600519"],
                COL_NAME: ["Moutai"],
                COL_PRICE: [bad_number],
                COL_CHANGE: [invalid_number],
                COL_CHANGE_AMOUNT: [bad_number],
                COL_VOLUME_RATIO: [bad_number],
                COL_TURNOVER: [bad_number],
                COL_AMPLITUDE: [bad_number],
                COL_PE: [bad_number],
                COL_PB: [bad_number],
                COL_TOTAL_MV: [bad_number],
                COL_CIRC_MV: [bad_number],
                COL_60D_CHANGE: [bad_number],
                COL_52W_HIGH: [bad_number],
                COL_52W_LOW: [bad_number],
            }
        )

    fetcher._fetch_with_retry = stock_fetch
    quote = fetcher.get_realtime_quote("600519")
    assert quote.price == 0.0
    assert quote.pb_ratio == 0.0

    fetcher._fetch_with_retry = lambda api_name, fetch_func: _raise("stock spot down")
    akshare_module._realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    assert fetcher.get_realtime_quote("600519") is None

    def etf_fetch(api_name, fetch_func):
        assert api_name == "ak.fund_etf_spot_em"
        return pd.DataFrame(
            {
                COL_CODE: ["512880"],
                COL_NAME: ["ETF"],
                COL_PRICE: [bad_number],
                COL_CHANGE: [invalid_number],
                COL_CHANGE_AMOUNT: [bad_number],
                COL_VOLUME_RATIO: [bad_number],
                COL_TURNOVER: [bad_number],
                COL_AMPLITUDE: [bad_number],
            }
        )

    fetcher._fetch_with_retry = etf_fetch
    akshare_module._etf_realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    etf_quote = fetcher.get_realtime_quote("512880")
    assert etf_quote.price == 0.0
    assert etf_quote.volume_ratio == 0.0
    assert fetcher.get_realtime_quote("512999") is None

    fetcher._fetch_with_retry = lambda api_name, fetch_func: _raise("etf spot down")
    akshare_module._etf_realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    assert fetcher.get_realtime_quote("512880") is None

    fetcher._fetch_with_retry = lambda api_name, fetch_func: pd.DataFrame()
    assert fetcher.get_chip_distribution("600519") is None

    def chip_fetch(api_name, fetch_func):
        assert api_name == "ak.stock_cyq_em"
        return pd.DataFrame(
            {
                COL_CHIP_DATE: ["2026-01-02"],
                COL_PROFIT_RATIO: [bad_number],
                COL_AVG_COST: [invalid_number],
                COL_COST_90_LOW: [bad_number],
                COL_COST_90_HIGH: [bad_number],
                COL_CONCENTRATION_90: [bad_number],
                COL_COST_70_LOW: [bad_number],
                COL_COST_70_HIGH: [bad_number],
                COL_CONCENTRATION_70: [bad_number],
            }
        )

    fetcher._fetch_with_retry = chip_fetch
    chip = fetcher.get_chip_distribution("600519")
    assert chip.profit_ratio == 0.0
    assert chip.concentration_70 == 0.0

    fetcher._fetch_with_retry = lambda api_name, fetch_func: _raise("chip down")
    assert fetcher.get_chip_distribution("600519") is None


def test_akshare_demo_entrypoint_handles_fetch_failures(monkeypatch, capsys):
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ak, "stock_zh_a_hist", lambda **kwargs: _raise("stock down"))
    monkeypatch.setattr(ak, "fund_etf_hist_em", lambda **kwargs: _raise("etf down"))
    monkeypatch.setattr(ak, "fund_etf_spot_em", lambda: pd.DataFrame({COL_CODE: ["159999"]}))
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(get_config=lambda: SimpleNamespace()))

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        runpy.run_module("data_provider.akshare_fetcher", run_name="__main__")

    output = capsys.readouterr().out
    assert "获取失败" in output
    assert "未获取到数据" in output
