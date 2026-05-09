from theme_backtester import ThemeBacktester


def test_theme_backtester_runs_minimal_theme_and_leader_report():
    records = [
        {
            "generated_at": "2026-05-01 10:00:00",
            "themes": [
                {
                    "name": "AI应用端扩散",
                    "heat_score": 80,
                    "news_score": 22,
                    "capital_score": 20,
                    "market_score": 18,
                    "persistence_score": 10,
                    "confidence": "高",
                    "sector_forward_returns": {"1d": 2.0, "3d": 5.0},
                    "leader_candidates": [
                        {"code": "000001", "leader_forward_returns": {"1d": 3.0, "3d": 6.0}}
                    ],
                },
                {
                    "name": "弱主题",
                    "heat_score": 45,
                    "news_score": 10,
                    "capital_score": 5,
                    "market_score": 8,
                    "persistence_score": 4,
                    "sector_forward_returns": {"1d": -1.0, "3d": -2.0},
                    "leader_candidates": [],
                },
            ],
        }
    ]

    result = ThemeBacktester(horizons=(1, 3)).run_backtest(records)
    report = ThemeBacktester(horizons=(1, 3)).format_report(result)

    assert result.summary.theme_count == 2
    assert result.summary.leader_count == 1
    assert result.summary.theme_returns["1d"] == 0.5
    assert result.summary.win_rates["1d"] == 50.0
    assert result.summary.factor_effectiveness["capital_score"] > 0
    assert "热点主题雷达最小回测报告" in report


def test_theme_backtester_supplements_forward_returns_from_market_data():
    class FakeSectorFetcher:
        def get_sector_daily_data(self, sector_name, days=40):
            return [
                {"date": "2026-05-01", "close": 100},
                {"date": "2026-05-02", "close": 102},
                {"date": "2026-05-03", "close": 104},
                {"date": "2026-05-04", "close": 105},
            ]

    class FakeDailyFetcher:
        def get_daily_data(self, code, days=40):
            return [
                {"date": "2026-05-01", "close": 10},
                {"date": "2026-05-02", "close": 11},
                {"date": "2026-05-03", "close": 12},
                {"date": "2026-05-04", "close": 13},
            ]

    records = [
        {
            "generated_at": "2026-05-01 10:00:00",
            "themes": [
                {
                    "name": "AI应用",
                    "heat_score": 80,
                    "news_score": 22,
                    "capital_score": 20,
                    "market_score": 18,
                    "persistence_score": 10,
                    "related_sectors": ["AI应用"],
                    "leader_candidates": [{"code": "000001"}],
                }
            ],
        }
    ]

    backtester = ThemeBacktester(
        sector_fetcher=FakeSectorFetcher(),
        daily_fetcher=FakeDailyFetcher(),
        horizons=(1, 3),
    )
    result = backtester.run_backtest(records)
    report = backtester.format_report(result)

    assert result.rows[0]["return_source"] == "market_supplement"
    assert result.rows[0]["theme_forward_returns"] == {"1d": 2.0, "3d": 5.0}
    assert result.rows[0]["leader_forward_returns"][0] == {"1d": 10.0, "3d": 30.0}
    assert result.summary.theme_returns["1d"] == 2.0
    assert "真实行情补算 1" in report
