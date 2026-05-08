import os

from market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview, evaluate_market_environment, temporary_no_proxy
from search_service import SearchResponse, SearchResult


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
