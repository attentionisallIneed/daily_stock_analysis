from search_service import BaseSearchProvider, SearchResponse, SearchResult, SearchService


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
