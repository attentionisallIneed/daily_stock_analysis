import sys
import types

import config as config_module
import search_service as search_module
from search_service import (
    BaseSearchProvider,
    SearchResponse,
    SearchResult,
    SearchService,
    SerpAPISearchProvider,
    TavilySearchProvider,
)


class FakeSearchProvider(BaseSearchProvider):
    def __init__(self, api_keys=None, name="fake", response=None, error=None):
        super().__init__(["key-1"] if api_keys is None else api_keys, name)
        self.response = response
        self.error = error
        self.calls = []

    def _do_search(self, query, api_key, max_results):
        self.calls.append((query, api_key, max_results))
        if self.error:
            raise self.error
        return self.response or SearchResponse(
            query=query,
            results=[SearchResult("headline", "summary", "https://example.com/a", "example.com", "2026-01-01")],
            provider=self.name,
            success=True,
        )


def test_search_result_and_response_formatting():
    result = SearchResult("Title", "Snippet", "https://example.com/news", "example.com", "2026-01-01")

    text = result.to_text()
    assert "example.com" in text
    assert "Title" in text
    assert "2026-01-01" in text
    assert "Snippet" in text

    context = SearchResponse("query", [result], "fake").to_context(max_results=1)
    assert "query" in context
    assert "fake" in context
    assert "Title" in context

    empty_context = SearchResponse("query", [], "fake", success=False).to_context()
    assert "query" in empty_context


def test_base_search_provider_records_success_and_failures():
    successful = FakeSearchProvider(api_keys=["key-1"])

    response = successful.search("demo", max_results=2)

    assert response.success is True
    assert successful.calls == [("demo", "key-1", 2)]
    assert successful._key_usage["key-1"] == 1

    unavailable = FakeSearchProvider(api_keys=[])
    unavailable_response = unavailable.search("demo")
    assert unavailable_response.success is False
    assert "API Key" in unavailable_response.error_message

    failing = FakeSearchProvider(api_keys=["bad-key"], error=RuntimeError("boom"))
    failed_response = failing.search("demo")
    assert failed_response.success is False
    assert failed_response.error_message == "boom"
    assert failing._key_errors["bad-key"] == 1

    saturated = FakeSearchProvider(api_keys=["a", "b"])
    saturated._key_errors = {"a": 3, "b": 4}
    assert saturated._get_next_key() == "a"
    assert saturated._key_errors == {"a": 0, "b": 0}

    saturated._key_errors["a"] = 2
    saturated._record_success("a")
    assert saturated._key_usage["a"] == 1
    assert saturated._key_errors["a"] == 1


def test_tavily_and_serpapi_providers_parse_success_and_error_paths(monkeypatch):
    tavily_module = types.ModuleType("tavily")
    serpapi_module = types.ModuleType("serpapi")
    tavily_calls = []
    serpapi_calls = []

    class FakeTavilyClient:
        def __init__(self, api_key):
            tavily_calls.append(("init", api_key))

        def search(self, **kwargs):
            tavily_calls.append(("search", kwargs))
            return {
                "results": [
                    {
                        "title": "Tavily title",
                        "content": "Tavily content",
                        "url": "https://www.example.com/a",
                        "published_date": "2026-01-01",
                    }
                ]
            }

    class FailingTavilyClient:
        def __init__(self, api_key):
            pass

        def search(self, **kwargs):
            raise RuntimeError("rate limit exceeded")

    class FakeGoogleSearch:
        def __init__(self, params):
            serpapi_calls.append(params)

        def get_dict(self):
            return {
                "organic_results": [
                    {
                        "title": "Serp title",
                        "snippet": "Serp snippet",
                        "link": "https://news.example.com/a",
                        "date": "2026-01-02",
                    }
                ]
            }

    class FailingGoogleSearch:
        def __init__(self, params):
            pass

        def get_dict(self):
            raise RuntimeError("serp failed")

    tavily_module.TavilyClient = FakeTavilyClient
    serpapi_module.GoogleSearch = FakeGoogleSearch
    monkeypatch.setitem(sys.modules, "tavily", tavily_module)
    monkeypatch.setitem(sys.modules, "serpapi", serpapi_module)

    tavily = TavilySearchProvider(["tk"])
    serpapi = SerpAPISearchProvider(["sk"])

    tavily_response = tavily._do_search("query", "tk", 2)
    serpapi_response = serpapi._do_search("query", "sk", 1)

    assert tavily_response.success is True
    assert tavily_response.results[0].source == "example.com"
    assert tavily_calls[1][1]["search_depth"] == "advanced"
    assert serpapi_response.success is True
    assert serpapi_response.results[0].source == "news.example.com"
    assert serpapi_calls[0]["engine"] == "baidu"
    assert TavilySearchProvider._extract_domain("https://www.example.com/path") == "example.com"
    assert SerpAPISearchProvider._extract_domain("https://www.example.com/path") == "example.com"

    tavily_module.TavilyClient = FailingTavilyClient
    serpapi_module.GoogleSearch = FailingGoogleSearch

    assert "API" in tavily._do_search("query", "tk", 2).error_message
    assert serpapi._do_search("query", "sk", 1).error_message == "serp failed"

    monkeypatch.setitem(sys.modules, "tavily", None)
    monkeypatch.setitem(sys.modules, "serpapi", None)
    assert TavilySearchProvider(["tk"])._do_search("query", "tk", 1).success is False
    assert SerpAPISearchProvider(["sk"])._do_search("query", "sk", 1).success is False


def test_search_service_uses_first_successful_provider_and_formats_reports():
    failing = FakeSearchProvider(
        name="failing",
        response=SearchResponse("q", [], "failing", success=False, error_message="no data"),
    )
    succeeding = FakeSearchProvider(name="succeeding")
    service = SearchService()
    service._providers = [failing, succeeding]

    response = service.search_stock_news("000001", "TestStock", max_results=2)

    assert response.success is True
    assert response.provider == "succeeding"
    assert failing.calls
    assert succeeding.calls

    report = service.format_intel_report(
        {
            "latest_news": response,
            "risk_check": SearchResponse("risk", [], "fake", success=False),
            "earnings": SearchResponse("earnings", [], "fake", success=False),
        },
        "TestStock",
    )
    assert "TestStock" in report
    assert "headline" in report


def test_search_service_events_comprehensive_report_and_singleton(monkeypatch):
    monkeypatch.setattr("search_service.time.sleep", lambda seconds: None)
    first = FakeSearchProvider(name="first")
    second = FakeSearchProvider(name="second")
    service = SearchService(tavily_keys=["tavily"], serpapi_keys=["serp"])
    service._providers = [first, second]

    event_response = service.search_stock_events("000001", "TestStock", event_types=["event-a", "event-b"])
    intel = service.search_comprehensive_intel("000001", "TestStock", max_searches=3)
    report = service.format_intel_report(intel, "TestStock")

    assert event_response.success is True
    assert "event-a OR event-b" in first.calls[0][0]
    assert set(intel) == {"latest_news", "risk_check", "earnings"}
    assert [call[0] for call in first.calls[1:]] == [
        intel["latest_news"].query,
        intel["earnings"].query,
    ]
    assert second.calls[0][0] == intel["risk_check"].query
    assert "headline" in report

    unavailable = SearchService()
    unavailable._providers = [FakeSearchProvider(api_keys=[], name="empty")]
    assert unavailable.search_stock_events("000001", "TestStock").success is False

    search_module.reset_search_service()
    monkeypatch.setattr(
        config_module,
        "get_config",
        lambda: types.SimpleNamespace(tavily_api_keys=["tk"], serpapi_keys=[]),
    )
    singleton = search_module.get_search_service()
    assert singleton is search_module.get_search_service()
    assert singleton.is_available is True
    search_module.reset_search_service()
    assert search_module._search_service is None


def test_search_service_handles_unavailable_and_batch_search(monkeypatch):
    service = SearchService()

    assert service.is_available is False
    assert service.search_stock_news("000001", "TestStock").success is False
    assert service.search_stock_events("000001", "TestStock").success is False
    assert service.search_comprehensive_intel("000001", "TestStock") == {}

    succeeding = FakeSearchProvider(name="succeeding")
    service._providers = [succeeding]
    monkeypatch.setattr("search_service.time.sleep", lambda seconds: None)

    batch = service.batch_search(
        [{"code": "000001", "name": "First"}, {"code": "000002", "name": "Second"}],
        delay_between=0,
    )

    assert set(batch) == {"000001", "000002"}
    assert all(response.success for response in batch.values())
