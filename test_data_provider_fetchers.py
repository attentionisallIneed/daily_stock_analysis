from types import SimpleNamespace

import pandas as pd
import pytest

import data_provider.akshare_fetcher as akshare_module
import data_provider.tushare_fetcher as tushare_module
from data_provider.akshare_fetcher import AkshareFetcher, _is_etf_code
from data_provider.baostock_fetcher import BaostockFetcher
from data_provider.base import DataFetchError
from data_provider.tushare_fetcher import TushareFetcher
from data_provider.yfinance_fetcher import YfinanceFetcher


COL_CODE = "\u4ee3\u7801"
COL_NAME = "\u540d\u79f0"
COL_SECTOR_NAME = "\u677f\u5757\u540d\u79f0"
COL_SECTOR_CODE = "\u677f\u5757\u4ee3\u7801"
COL_RANK = "\u6392\u540d"
COL_CHANGE = "\u6da8\u8dcc\u5e45"
COL_TURNOVER = "\u6362\u624b\u7387"
COL_AMOUNT = "\u6210\u4ea4\u989d"
COL_LEADER = "\u9886\u6da8\u80a1\u7968"
COL_PRICE = "\u6700\u65b0\u4ef7"
COL_AMPLITUDE = "\u632f\u5e45"
COL_HIGH = "\u6700\u9ad8"
COL_LOW = "\u6700\u4f4e"
COL_OPEN_TODAY = "\u4eca\u5f00"
COL_CHANGE_AMOUNT = "\u6da8\u8dcc\u989d"
COL_VOLUME_RATIO = "\u91cf\u6bd4"
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
COL_REPORT_DATE = "\u62a5\u544a\u671f"


def _quiet_akshare_fetcher():
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    fetcher._set_random_user_agent = lambda: None
    fetcher._enforce_rate_limit = lambda: None
    return fetcher


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


def test_akshare_helpers_normalize_records_symbols_and_float_values():
    fetcher = _quiet_akshare_fetcher()

    assert _is_etf_code("512400") is True
    assert _is_etf_code("159883") is True
    assert _is_etf_code("600519") is False
    assert _is_etf_code("51240") is False

    assert fetcher._safe_float_value("1,234.50%") == 1234.5
    assert fetcher._safe_float_value("-", default=-1.0) == -1.0
    assert fetcher._safe_float_value("bad", default=7.0) == 7.0
    assert fetcher._safe_float_value(pd.NA, default=3.0) == 3.0

    assert fetcher._to_em_stock_symbol("600519") == "600519.SH"
    assert fetcher._to_em_stock_symbol("688001") == "688001.SH"
    assert fetcher._to_em_stock_symbol("000001") == "000001.SZ"
    assert fetcher._to_em_stock_symbol("000001.sz") == "000001.SZ"

    raw = pd.DataFrame(
        {
            "date": ["2026-01-02"],
            "open": ["10.0"],
            "high": ["11.0"],
            "low": ["9.5"],
            "close": ["10.5"],
            "volume": ["1000"],
            "amount": ["10500"],
            "pct_chg": ["5.0"],
            "ignored": ["drop-me"],
        }
    )
    normalized = fetcher._normalize_data(raw, "600519")

    assert normalized.columns.tolist() == [
        "code",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
    ]
    assert normalized.loc[0, "code"] == "600519"

    records = fetcher._dataframe_to_records(pd.DataFrame({"a": [1, None], "b": ["x", "y"]}), max_items=1)
    assert records == [{"a": 1.0, "b": "x"}]
    assert fetcher._dataframe_to_records(None) == []
    assert fetcher._dataframe_to_records(pd.DataFrame()) == []


def test_akshare_hot_sectors_and_constituents_from_mocked_apis():
    fetcher = _quiet_akshare_fetcher()
    calls = []

    def fake_fetch(api_name, fetch_func):
        calls.append(api_name)
        if api_name == "ak.stock_board_industry_name_em":
            return pd.DataFrame(
                {
                    COL_SECTOR_NAME: ["Industry A", ""],
                    COL_SECTOR_CODE: ["BK001", "BK999"],
                    COL_RANK: [2, 99],
                    COL_CHANGE: ["3.5", "10"],
                    COL_TURNOVER: ["1.2", "9.9"],
                    COL_AMOUNT: ["1000", "9999"],
                    COL_LEADER: ["Leader A", "Leader Z"],
                }
            )
        if api_name == "ak.stock_board_concept_name_em":
            return pd.DataFrame(
                {
                    COL_NAME: ["Concept B"],
                    COL_CODE: ["C002"],
                    COL_RANK: [1],
                    COL_CHANGE: ["5.1%"],
                    COL_TURNOVER: ["2.3%"],
                    COL_AMOUNT: ["2,000"],
                    COL_LEADER: ["Leader B"],
                }
            )
        return pd.DataFrame(
            {
                COL_CODE: ["000001", ""],
                COL_NAME: ["Alpha", "Missing"],
                COL_PRICE: ["10.5", "1"],
                COL_CHANGE: ["2.2", "3"],
                COL_AMOUNT: ["5000", "1"],
                COL_TURNOVER: ["4.4", "1"],
                COL_AMPLITUDE: ["5.5", "1"],
                COL_HIGH: ["11", "1"],
                COL_LOW: ["10", "1"],
                COL_OPEN_TODAY: ["10.2", "1"],
            }
        )

    fetcher._fetch_with_retry = fake_fetch

    sectors = fetcher.get_hot_sectors(sector_count=2, include_concepts=True)
    constituents = fetcher.get_sector_constituents("Concept B", sector_type="concept")

    assert [item["name"] for item in sectors] == ["Concept B", "Industry A"]
    assert sectors[0]["sector_type"] == "concept"
    assert sectors[0]["change_pct"] == 5.1
    assert constituents == [
        {
            "code": "000001",
            "name": "Alpha",
            "price": 10.5,
            "change_pct": 2.2,
            "amount": 5000.0,
            "turnover_rate": 4.4,
            "amplitude": 5.5,
            "high": 11.0,
            "low": 10.0,
            "open": 10.2,
        }
    ]
    assert "ak.stock_board_industry_name_em" in calls
    assert "ak.stock_board_concept_cons_em" in calls


def test_akshare_sector_and_index_history_are_cleaned_and_indicator_enriched():
    fetcher = _quiet_akshare_fetcher()
    api_calls = []

    def fake_fetch(api_name, fetch_func):
        api_calls.append(api_name)
        return pd.DataFrame(
            {
                "date": ["2026-01-02", "2026-01-01"],
                "open": ["11", "10"],
                "high": ["12", "11"],
                "low": ["10", "9"],
                "close": ["11", "10"],
                "volume": ["200", "100"],
                "amount": ["2200", "1000"],
                "pct_chg": ["10", "0"],
            }
        )

    fetcher._fetch_with_retry = fake_fetch

    sector_df = fetcher.get_sector_daily_data("Concept B", sector_type="concept", start_date="2026-01-01", end_date="2026-01-02")
    index_df = fetcher.get_index_daily_data("000300", start_date="2026-01-01", end_date="2026-01-02")

    assert sector_df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02"]
    assert sector_df["ma5"].tolist() == [10.0, 10.5]
    assert index_df["volume_ratio"].iloc[-1] == 2.0
    assert api_calls == ["ak.stock_board_concept_hist_em", "ak.index_zh_a_hist"]


def test_akshare_realtime_quotes_chip_distribution_and_enhanced_data(monkeypatch):
    fetcher = _quiet_akshare_fetcher()
    akshare_module._realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    akshare_module._etf_realtime_cache.update({"data": None, "timestamp": 0, "ttl": 60})
    calls = []

    def fake_fetch(api_name, fetch_func):
        calls.append(api_name)
        if api_name == "ak.stock_zh_a_spot_em":
            return pd.DataFrame(
                {
                    COL_CODE: ["600519"],
                    COL_NAME: ["Moutai"],
                    COL_PRICE: [1800.5],
                    COL_CHANGE: [1.2],
                    COL_CHANGE_AMOUNT: [21.0],
                    COL_VOLUME_RATIO: [1.8],
                    COL_TURNOVER: [0.7],
                    COL_AMPLITUDE: [2.3],
                    COL_PE: [30.1],
                    COL_PB: [9.2],
                    COL_TOTAL_MV: [22000],
                    COL_CIRC_MV: [21000],
                    COL_60D_CHANGE: [5.5],
                    COL_52W_HIGH: [1900],
                    COL_52W_LOW: [1500],
                }
            )
        if api_name == "ak.fund_etf_spot_em":
            return pd.DataFrame(
                {
                    COL_CODE: ["512880"],
                    COL_NAME: ["ETF"],
                    COL_PRICE: [1.23],
                    COL_CHANGE: [-0.5],
                    COL_CHANGE_AMOUNT: [-0.01],
                    COL_TURNOVER: [8.8],
                    COL_AMPLITUDE: [1.1],
                }
            )
        if api_name == "ak.stock_cyq_em":
            return pd.DataFrame(
                {
                    COL_CHIP_DATE: ["2026-01-01", "2026-01-02"],
                    COL_PROFIT_RATIO: [0.5, 0.8],
                    COL_AVG_COST: [9.0, 10.0],
                    COL_COST_90_LOW: [8.0, 9.0],
                    COL_COST_90_HIGH: [12.0, 13.0],
                    COL_CONCENTRATION_90: [0.2, 0.1],
                    COL_COST_70_LOW: [8.5, 9.5],
                    COL_COST_70_HIGH: [11.5, 12.5],
                    COL_CONCENTRATION_70: [0.15, 0.08],
                }
            )
        raise AssertionError(api_name)

    fetcher._fetch_with_retry = fake_fetch

    stock_quote = fetcher.get_realtime_quote("600519")
    cached_quote = fetcher.get_realtime_quote("600519")
    missing_quote = fetcher.get_realtime_quote("000404")
    etf_quote = fetcher.get_realtime_quote("512880")
    stock_chip = fetcher.get_chip_distribution("600519")
    etf_chip = fetcher.get_chip_distribution("512880")

    monkeypatch.setattr(fetcher, "get_daily_data", lambda stock_code, days=60: pd.DataFrame({"close": [1, 2]}))
    monkeypatch.setattr(fetcher, "get_realtime_quote", lambda stock_code: stock_quote)
    monkeypatch.setattr(fetcher, "get_chip_distribution", lambda stock_code: stock_chip)
    enhanced = fetcher.get_enhanced_data("600519", days=5)

    assert stock_quote.name == "Moutai"
    assert stock_quote.pe_ratio == 30.1
    assert cached_quote.price == 1800.5
    assert missing_quote is None
    assert etf_quote.name == "ETF"
    assert etf_quote.pe_ratio == 0.0
    assert stock_chip.date == "2026-01-02"
    assert stock_chip.profit_ratio == 0.8
    assert etf_chip is None
    assert enhanced["daily_data"]["close"].tolist() == [1, 2]
    assert enhanced["realtime_quote"] is stock_quote
    assert enhanced["chip_distribution"] is stock_chip
    assert calls.count("ak.stock_zh_a_spot_em") == 1


def test_akshare_company_info_methods_return_records_and_skip_etfs():
    fetcher = _quiet_akshare_fetcher()
    requested = []

    def fake_fetch(api_name, fetch_func):
        requested.append(api_name)
        if api_name == "ak.stock_zh_a_disclosure_report_cninfo":
            return pd.DataFrame({"title": ["notice"], "empty": [None]})
        if api_name == "ak.stock_financial_analysis_indicator_em":
            return pd.DataFrame(
                {
                    COL_REPORT_DATE: ["2025-12-31", "2026-03-31"],
                    "eps": [1.0, 1.2],
                }
            )
        if api_name == "ak.stock_restricted_release_queue_em":
            return pd.DataFrame({"batch": ["first", "second"]})
        if api_name == "ak.stock_info_a_code_name":
            return pd.DataFrame({"code": ["000001", "600519"], "name": ["Alpha", "Moutai"]})
        raise AssertionError(api_name)

    fetcher._fetch_with_retry = fake_fetch

    assert fetcher.get_cninfo_announcements("512880") == []
    assert fetcher.get_financial_indicators("512880") == []
    assert fetcher.get_restricted_release_queue("512880") == []
    assert fetcher.get_cninfo_announcements("600519", max_items=1) == [{"title": "notice", "empty": ""}]
    assert fetcher.get_financial_indicators("600519", max_items=1) == [{COL_REPORT_DATE: "2026-03-31", "eps": 1.2}]
    assert fetcher.get_restricted_release_queue("600519", max_items=1) == [{"batch": "first"}]
    assert fetcher.get_stock_name("600519") == "Moutai"
    assert fetcher.get_stock_name("000404") == ""
    assert requested.count("ak.stock_info_a_code_name") == 2
