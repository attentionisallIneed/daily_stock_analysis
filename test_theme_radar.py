from types import SimpleNamespace

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
