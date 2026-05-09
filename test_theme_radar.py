from types import SimpleNamespace

from capital_flow import CapitalFlowEvidence
from theme_models import ThemeEvidence, ThemeSignal
from theme_radar import ThemeRadar


class FakeSectorFetcher:
    def get_hot_sectors(self, sector_count=5, include_concepts=True):
        return [
            {
                "name": "AI应用",
                "sector_type": "concept",
                "rank": 1,
                "change_pct": 4.0,
                "amount": 2_000_000_000,
                "turnover_rate": 3.5,
                "leading_stock": "Alpha",
            }
        ][:sector_count]


class FakeMarketAnalyzer:
    def get_market_overview(self):
        return SimpleNamespace(
            to_dict=lambda: {
                "north_flow": 20.0,
                "top_sectors": [{"name": "AI应用", "change_pct": 4.0}],
            }
        )


class FakeScreener:
    def screen_hot_sectors(self, sector_count=5, top_n=3, include_concepts=True):
        trend = SimpleNamespace(
            relative_strength_score=8,
            breakout_score=4,
            stock_vs_sector=3.0,
            breakout_valid=True,
        )
        candidate = SimpleNamespace(
            code="000001",
            name="Alpha",
            sector_name="AI应用",
            composite_score=88.0,
            score_breakdown={"liquidity": 9.0},
            trend_result=trend,
            risk_flags=[],
            is_sector_leader=True,
        )
        return SimpleNamespace(selected=[candidate], filtered=[])


def test_theme_radar_fallback_outputs_evidence_theme_leaders_and_report(tmp_path):
    details = []
    radar = ThemeRadar(
        market_analyzer=FakeMarketAnalyzer(),
        sector_fetcher=FakeSectorFetcher(),
        screener=FakeScreener(),
        detail_analyzer=lambda code: details.append(code) or SimpleNamespace(code=code, name="Alpha", analysis_summary="detail"),
    )
    radar.tracker.history_dir = tmp_path

    result = radar.run(theme_count=1, leader_top_n=1, include_detail_analysis=True)

    assert result.themes[0].evidence_ids
    assert result.themes[0].related_sectors == ["AI应用"]
    assert result.selected_stocks[0].code == "000001"
    assert result.detailed_results
    assert details == ["000001"]
    assert result.history_path
    assert "热点板块 LLM 雷达日报" in result.report_markdown
    assert result.themes[0].capital_observation in result.report_markdown


def test_theme_score_is_capped_at_100():
    theme = ThemeSignal(
        name="过热主题",
        related_sectors=["AI应用"],
        heat_score=125.5,
        news_score=30,
        capital_score=30,
        market_score=30,
        persistence_score=20,
    )

    assert theme.total_score == 100.0
    assert theme.to_dict()["total_score"] == 100.0


def test_unmapped_high_confidence_theme_is_downgraded():
    radar = ThemeRadar()
    themes = radar._build_theme_signals(
        [
            {
                "name": "无法映射主题",
                "confidence": "高",
                "related_sectors": ["不存在板块"],
                "catalysts": ["政策催化"],
                "risks": [],
                "evidence_ids": ["news_001"],
                "news_score": 25,
                "persistence_score": 20,
            }
        ],
        [{"name": "AI应用", "rank": 1, "change_pct": 5.0}],
        [ThemeEvidence(id="news_001", source="unit", title="AI政策", summary="policy")],
        {
            "AI应用": CapitalFlowEvidence(
                sector_name="AI应用",
                source="unit",
                updated_at="2026-05-01",
                reliability="medium",
                score=22,
                observation="新闻与资金共振",
            )
        },
        {"sector_data_available": True, "capital_data_available": True, "news_data_available": True},
    )

    theme = themes[0]
    assert theme.confidence == "中"
    assert theme.status == "待确认"
    assert theme.total_score <= 64
    assert theme.capital_score <= 6
    assert theme.market_score <= 6
    assert any("映射" in item for item in theme.risks + theme.downgrade_reasons)


def test_missing_capital_fields_cap_confidence_and_capital_score():
    radar = ThemeRadar()
    themes = radar._build_theme_signals(
        [
            {
                "name": "资金缺失主题",
                "confidence": "高",
                "related_sectors": ["AI应用"],
                "catalysts": ["政策催化"],
                "risks": [],
                "evidence_ids": ["sector_001"],
                "news_score": 20,
                "persistence_score": 10,
            }
        ],
        [{"name": "AI应用", "rank": 1, "change_pct": 5.0}],
        [ThemeEvidence(id="sector_001", source="unit", title="AI板块", summary="sector")],
        {
            "AI应用": CapitalFlowEvidence(
                sector_name="AI应用",
                source="unit",
                updated_at="2026-05-01",
                reliability="medium",
                score=18,
                observation="资金数据缺失，按中性处理",
                missing_fields=["amount", "turnover_rate"],
            )
        },
        {"sector_data_available": True, "capital_data_available": False, "news_data_available": True},
    )

    theme = themes[0]
    assert theme.confidence == "中"
    assert theme.capital_score <= 8
    assert theme.capital_observation.startswith("资金数据缺失")
    assert "资金验证缺失" in theme.downgrade_reasons


def test_no_sector_data_marks_report_as_news_observation(tmp_path):
    class EmptySectorFetcher:
        def get_hot_sectors(self, sector_count=5, include_concepts=True):
            return []

    class FakeSearchService:
        is_available = True

        def search_market_news(self, query, max_results=5):
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        source="unit",
                        title="AI政策",
                        snippet="政策催化",
                        published_date="2026-05-01",
                        url="https://example.test/news",
                    )
                ]
            )

    class FakeLLM:
        def is_available(self):
            return True

        def generate_theme_json(self, prompt):
            return """
            {
              "themes": [
                {
                  "name": "AI新闻观察",
                  "confidence": "高",
                  "related_sectors": ["AI应用"],
                  "catalysts": ["政策催化"],
                  "risks": [],
                  "evidence_ids": ["news_001"],
                  "unsupported_claims": [],
                  "news_score": 25,
                  "persistence_score": 20
                }
              ]
            }
            """

    radar = ThemeRadar(
        market_analyzer=FakeMarketAnalyzer(),
        search_service=FakeSearchService(),
        sector_fetcher=EmptySectorFetcher(),
        llm_analyzer=FakeLLM(),
    )
    radar.tracker.history_dir = tmp_path

    result = radar.run(theme_count=1, leader_top_n=1, include_detail_analysis=False, save_history=False)

    assert result.selected_stocks == []
    assert result.themes[0].confidence == "中"
    assert result.themes[0].status == "待确认"
    assert result.themes[0].total_score <= 59
    assert "板块行情获取失败" in result.report_markdown
    assert "未生成候选龙头" in result.report_markdown


def test_theme_radar_uses_market_news_search_when_available(tmp_path):
    calls = []

    class FakeMarketSearch:
        is_available = True

        def search_market_news(self, query, max_results=5):
            calls.append(("market", query, max_results))
            return SimpleNamespace(results=[])

        def search_stock_news(self, *args, **kwargs):
            raise AssertionError("stock news template should not be used for market themes")

    radar = ThemeRadar(
        market_analyzer=FakeMarketAnalyzer(),
        search_service=FakeMarketSearch(),
        sector_fetcher=FakeSectorFetcher(),
        screener=FakeScreener(),
    )
    radar.tracker.history_dir = tmp_path

    radar.run(theme_count=1, leader_top_n=1, include_detail_analysis=False, save_history=False)

    assert calls and calls[0][0] == "market"
