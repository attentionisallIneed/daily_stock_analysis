import os

import pandas as pd

import market_analyzer as market_module
from market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview, evaluate_market_environment, temporary_no_proxy
from search_service import SearchResponse, SearchResult


COL_CODE = "\u4ee3\u7801"
COL_PRICE = "\u6700\u65b0\u4ef7"
COL_CHANGE_AMOUNT = "\u6da8\u8dcc\u989d"
COL_CHANGE = "\u6da8\u8dcc\u5e45"
COL_OPEN_TODAY = "\u4eca\u5f00"
COL_HIGH = "\u6700\u9ad8"
COL_LOW = "\u6700\u4f4e"
COL_PREV_CLOSE = "\u6628\u6536"
COL_VOLUME = "\u6210\u4ea4\u91cf"
COL_AMOUNT = "\u6210\u4ea4\u989d"
COL_SECTOR_NAME = "\u677f\u5757\u540d\u79f0"
COL_TODAY_NET_BUY = "\u4eca\u65e5\u51c0\u4e70\u989d"


def _overview(**overrides):
    overview = MarketOverview(
        date="2026-01-01",
        indices=[
            MarketIndex(code="000001", name="IndexA", current=3100, change_pct=1.2, high=3120, low=3060, prev_close=3080),
            MarketIndex(code="399001", name="IndexB", current=9800, change_pct=0.8),
        ],
        up_count=700,
        down_count=300,
        flat_count=20,
        limit_up_count=40,
        limit_down_count=3,
        total_amount=9000,
        north_flow=35,
        top_sectors=[{"name": "Tech", "change_pct": 3.2}],
        bottom_sectors=[{"name": "Banks", "change_pct": -1.1}],
    )
    for key, value in overrides.items():
        setattr(overview, key, value)
    return overview


def test_market_index_and_overview_to_dict():
    index = MarketIndex(
        code="000001",
        name="IndexA",
        current=3100,
        change=12,
        change_pct=0.4,
        open=3080,
        high=3120,
        low=3070,
        volume=1000,
        amount=2000,
        amplitude=1.6,
    )
    overview = MarketOverview(date="2026-01-01", indices=[index], up_count=1, top_sectors=[{"name": "Tech"}])

    assert index.to_dict()["code"] == "000001"
    assert index.to_dict()["amplitude"] == 1.6
    rendered = overview.to_dict()
    assert rendered["date"] == "2026-01-01"
    assert rendered["indices"][0]["name"] == "IndexA"
    assert rendered["top_sectors"] == [{"name": "Tech"}]


def test_evaluate_market_environment_scores_strong_and_weak_markets():
    strong = evaluate_market_environment(_overview())

    assert strong["market_score"] > 75
    assert strong["avg_index_change"] == 1.0
    assert strong["top_sectors"] == [{"name": "Tech", "change_pct": 3.2}]

    weak = evaluate_market_environment(
        _overview(
            indices=[MarketIndex(code="000001", name="IndexA", change_pct=-1.5)],
            up_count=200,
            down_count=800,
            limit_up_count=1,
            limit_down_count=30,
            north_flow=-40,
            top_sectors=[],
            bottom_sectors=[],
        )
    )

    assert weak["market_score"] < 30
    assert weak["avg_index_change"] == -1.5
    assert weak["risk_level"]


def test_temporary_no_proxy_restores_environment(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy")
    monkeypatch.setenv("NO_PROXY", "old")

    with temporary_no_proxy():
        assert os.environ["NO_PROXY"] == "*"
        assert "HTTP_PROXY" not in os.environ
        assert "HTTPS_PROXY" not in os.environ

    assert os.environ["HTTP_PROXY"] == "http://proxy"
    assert os.environ["HTTPS_PROXY"] == "http://proxy"
    assert os.environ["NO_PROXY"] == "old"


def test_market_analyzer_uses_template_when_ai_is_unavailable():
    class UnavailableAnalyzer:
        def is_available(self):
            return False

    analyzer = MarketAnalyzer(search_service=None, analyzer=UnavailableAnalyzer())
    report = analyzer.generate_market_review(_overview(), [{"title": "News", "snippet": "Snippet"}])

    assert "2026-01-01" in report
    assert "IndexA" in report
    assert "Tech" in report


def test_market_analyzer_searches_market_news_with_service():
    class FakeSearchService:
        def __init__(self):
            self.calls = []

        def search_stock_news(self, stock_code, stock_name, max_results=3, focus_keywords=None):
            self.calls.append((stock_code, stock_name, max_results, focus_keywords))
            return SearchResponse(
                query="market",
                results=[SearchResult("Headline", "Snippet", "https://example.com", "example.com")],
                provider="fake",
            )

    service = FakeSearchService()
    analyzer = MarketAnalyzer(search_service=service, analyzer=None)

    news = analyzer.search_market_news()

    assert len(service.calls) == 3
    assert all(call[0] == "market" for call in service.calls)
    assert len(news) == 3

    assert MarketAnalyzer(search_service=None, analyzer=None).search_market_news() == []

    class FailingSearchService:
        def search_stock_news(self, *args, **kwargs):
            raise RuntimeError("search failed")

    assert MarketAnalyzer(search_service=FailingSearchService(), analyzer=None).search_market_news() == []


def test_market_overview_orchestrates_collection_steps(monkeypatch):
    analyzer = MarketAnalyzer(search_service=None, analyzer=None)
    analyzer.config.market_breadth_enabled = True
    calls = []

    monkeypatch.setattr(
        analyzer,
        "_get_main_indices",
        lambda: calls.append("indices")
        or [MarketIndex(code="000001", name="IndexA", current=3100, change_pct=1.0)],
    )

    def fake_stats(overview):
        calls.append("stats")
        overview.up_count = 10

    def fake_sectors(overview):
        calls.append("sectors")
        overview.top_sectors = [{"name": "Tech", "change_pct": 3.0}]

    def fake_north_flow(overview):
        calls.append("north")
        overview.north_flow = 12.5

    monkeypatch.setattr(analyzer, "_get_market_statistics", fake_stats)
    monkeypatch.setattr(analyzer, "_get_sector_rankings", fake_sectors)
    monkeypatch.setattr(analyzer, "_get_north_flow", fake_north_flow)

    overview = analyzer.get_market_overview()

    assert calls == ["indices", "stats", "sectors", "north"]
    assert overview.indices[0].code == "000001"
    assert overview.up_count == 10
    assert overview.top_sectors == [{"name": "Tech", "change_pct": 3.0}]
    assert overview.north_flow == 12.5


def test_market_analyzer_collects_market_data_from_mocked_akshare(monkeypatch):
    calls = []

    def fake_akshare(api_name, fetch_func):
        calls.append(api_name)
        if api_name == "ak.stock_zh_index_spot_em":
            codes = ["000001", "399001", "399006", "000688", "000016", "000300"]
            return pd.DataFrame(
                {
                    COL_CODE: codes,
                    COL_PRICE: [3000, 10000, 2200, 900, 2500, 3600],
                    COL_CHANGE_AMOUNT: [10, 20, -5, 1, 3, 8],
                    COL_CHANGE: [0.5, 1.2, -0.3, 0.1, 0.2, 0.4],
                    COL_OPEN_TODAY: [2990, 9900, 2210, 899, 2490, 3590],
                    COL_HIGH: [3010, 10100, 2220, 910, 2510, 3610],
                    COL_LOW: [2980, 9800, 2180, 890, 2480, 3580],
                    COL_PREV_CLOSE: [2990, 9980, 2205, 899, 2497, 3592],
                    COL_VOLUME: [100, 200, 300, 400, 500, 600],
                    COL_AMOUNT: [1e8, 2e8, 3e8, 4e8, 5e8, 6e8],
                }
            )
        if api_name == "ak.stock_zh_a_spot_em":
            return pd.DataFrame(
                {
                    COL_CHANGE: [10.0, -10.0, 0.0, 2.0],
                    COL_AMOUNT: [1e8, 2e8, 3e8, 4e8],
                }
            )
        if api_name == "ak.stock_board_industry_name_em":
            return pd.DataFrame(
                {
                    COL_SECTOR_NAME: ["Tech", "Banks", "Energy"],
                    COL_CHANGE: [3.0, -2.0, 1.0],
                }
            )
        if api_name == "ak.stock_hsgt_north_net_flow_in_em":
            raise AttributeError("removed")
        if api_name == "ak.stock_hsgt_fund_flow_summary_em":
            return pd.DataFrame({COL_TODAY_NET_BUY: [3.0]})
        if api_name == "ak.stock_hsgt_hist_em":
            raise AssertionError("history fallback should not run when summary has data")
        raise AssertionError(api_name)

    monkeypatch.setattr(market_module, "_call_akshare_with_retry", fake_akshare)

    analyzer = MarketAnalyzer(search_service=None, analyzer=None)
    overview = MarketOverview(date="2026-01-01")
    overview.indices = analyzer._get_main_indices()
    analyzer._get_market_statistics(overview)
    analyzer._get_sector_rankings(overview)
    analyzer._get_north_flow(overview)

    assert [index.code for index in overview.indices] == list(MarketAnalyzer.MAIN_INDICES)
    assert round(overview.indices[0].amplitude, 2) == 1.0
    assert overview.up_count == 2
    assert overview.down_count == 1
    assert overview.flat_count == 1
    assert overview.limit_up_count == 1
    assert overview.limit_down_count == 1
    assert overview.total_amount == 10.0
    assert overview.top_sectors[0] == {"name": "Tech", "change_pct": 3.0}
    assert overview.bottom_sectors[0] == {"name": "Banks", "change_pct": -2.0}
    assert overview.north_flow == 3.0
    assert "ak.stock_hsgt_fund_flow_summary_em" in calls


def test_market_analyzer_extracts_north_flow_from_history_fallback(monkeypatch):
    calls = []

    def fake_akshare(api_name, fetch_func):
        calls.append(api_name)
        if api_name == "ak.stock_hsgt_fund_flow_summary_em":
            return pd.DataFrame({"成交净买额": [0.0], "资金方向": ["北向"]})
        if api_name == "ak.stock_hsgt_hist_em":
            return pd.DataFrame({"当日成交净买额": [None, 12.5]})
        raise AssertionError(api_name)

    monkeypatch.setattr(market_module.ak, "stock_hsgt_north_net_flow_in_em", None, raising=False)
    monkeypatch.setattr(market_module, "_call_akshare_with_retry", fake_akshare)

    analyzer = MarketAnalyzer(search_service=None, analyzer=None)
    overview = MarketOverview(date="2026-01-01")
    analyzer._get_north_flow(overview)

    assert overview.north_flow == 12.5
    assert calls == [
        "ak.stock_hsgt_north_net_flow_in_em",
        "ak.stock_hsgt_fund_flow_summary_em",
        "ak.stock_hsgt_hist_em",
    ]


def test_market_analyzer_collects_market_data_from_fallback_akshare(monkeypatch):
    calls = []

    def fake_akshare(api_name, fetch_func):
        calls.append(api_name)
        if api_name in {"ak.stock_zh_index_spot_em", "ak.stock_board_industry_name_em"}:
            raise RuntimeError("eastmoney down")
        if api_name == "ak.stock_zh_index_spot_sina":
            return pd.DataFrame(
                {
                    COL_CODE: ["000001", "399001"],
                    COL_PRICE: [3000, 10000],
                    COL_CHANGE_AMOUNT: [10, 20],
                    COL_CHANGE: [0.5, 1.2],
                    COL_OPEN_TODAY: [2990, 9900],
                    COL_HIGH: [3010, 10100],
                    COL_LOW: [2980, 9800],
                    COL_PREV_CLOSE: [2990, 9980],
                    COL_VOLUME: [100, 200],
                    COL_AMOUNT: [1e8, 2e8],
                }
            )
        if api_name == "ak.stock_board_industry_summary_ths":
            return pd.DataFrame(
                {
                    "板块": ["Robotics", "Banks"],
                    COL_CHANGE: [4.0, -1.5],
                }
            )
        raise AssertionError(api_name)

    monkeypatch.setattr(market_module, "_call_akshare_with_retry", fake_akshare)

    analyzer = MarketAnalyzer(search_service=None, analyzer=None)
    overview = MarketOverview(date="2026-01-01")
    overview.indices = analyzer._get_main_indices()
    analyzer._get_sector_rankings(overview)

    assert [index.code for index in overview.indices] == ["000001", "399001"]
    assert overview.top_sectors[0] == {"name": "Robotics", "change_pct": 4.0}
    assert overview.bottom_sectors[0] == {"name": "Banks", "change_pct": -1.5}
    assert "ak.stock_zh_index_spot_sina" in calls
    assert "ak.stock_board_industry_summary_ths" in calls


def test_market_review_uses_ai_when_available_and_falls_back_on_failure():
    calls = []

    class AvailableAnalyzer:
        def is_available(self):
            return True

        def _call_api_with_retry(self, prompt, generation_config):
            calls.append((prompt, generation_config))
            return "AI review"

    analyzer = MarketAnalyzer(search_service=None, analyzer=AvailableAnalyzer())
    report = analyzer.generate_market_review(
        _overview(),
        [
            SearchResult("Object headline", "Object snippet", "https://example.com", "example.com"),
            {"title": "Dict headline", "snippet": "Dict snippet"},
        ],
    )

    assert report == "AI review"
    assert "2026-01-01" in calls[0][0]
    assert "Object headline" in calls[0][0]
    assert "Dict headline" in calls[0][0]
    assert calls[0][1]["max_output_tokens"] == 2048

    class FailingAnalyzer(AvailableAnalyzer):
        def _call_api_with_retry(self, prompt, generation_config):
            raise RuntimeError("temporary")

    fallback = MarketAnalyzer(search_service=None, analyzer=FailingAnalyzer()).generate_market_review(_overview(), [])

    assert "2026-01-01" in fallback
    assert "IndexA" in fallback


def test_run_daily_review_composes_overview_news_and_report(monkeypatch):
    analyzer = MarketAnalyzer(search_service=None, analyzer=None)
    calls = []
    overview = _overview()

    monkeypatch.setattr(analyzer, "get_market_overview", lambda: calls.append("overview") or overview)
    monkeypatch.setattr(analyzer, "search_market_news", lambda: calls.append("news") or [{"title": "Headline"}])
    monkeypatch.setattr(
        analyzer,
        "generate_market_review",
        lambda overview_arg, news_arg: calls.append((overview_arg, news_arg)) or "daily review",
    )

    assert analyzer.run_daily_review() == "daily review"
    assert calls[0] == "overview"
    assert calls[1] == "news"
    assert calls[2][0] is overview
    assert calls[2][1] == [{"title": "Headline"}]
