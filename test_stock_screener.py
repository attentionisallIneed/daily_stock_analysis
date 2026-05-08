import pandas as pd

from types import SimpleNamespace

from stock_screener import ScreenedStock, ScreeningResult, SectorCandidate, StockScreener


def _make_df(closes, amount=200_000_000, highs=None, lows=None, opens=None):
    highs = highs or [price * 1.02 for price in closes]
    lows = lows or [price * 0.98 for price in closes]
    opens = opens or closes
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(closes), freq="D"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000_000] * len(closes),
            "amount": [amount] * len(closes),
        }
    )


class FakeDailyFetcher:
    def __init__(self, data):
        self.data = data

    def get_daily_data(self, stock_code, days=120):
        return self.data[stock_code], "fake"


class FakeSectorFetcher:
    def __init__(self, constituents):
        self.constituents = constituents

    def get_hot_sectors(self, sector_count=5, include_concepts=True):
        return [
            {
                "name": "测试行业",
                "sector_type": "industry",
                "rank": 1,
                "change_pct": 3.0,
                "leading_stock": "强势股",
            }
        ][:sector_count]

    def get_sector_constituents(self, sector_name, sector_type="industry"):
        return self.constituents

    def get_sector_daily_data(self, sector_name, sector_type="industry", days=120):
        return _make_df([10.0] * 59 + [10.0 + i * 0.04 for i in range(21)])

    def get_index_daily_data(self, index_code="000300", days=250):
        return _make_df([10.0] * 80)


def test_hot_sector_screener_filters_and_ranks_candidates():
    valid_closes = [10 + i * 0.05 for i in range(80)]
    weak_closes = [10.0] * 80
    short_closes = [10.0] * 30
    one_line_closes = [10.0] * 79 + [11.0]
    one_line_df = _make_df(
        one_line_closes,
        highs=[10.2] * 79 + [11.0],
        lows=[9.8] * 79 + [11.0],
        opens=[10.0] * 79 + [11.0],
    )

    daily_fetcher = FakeDailyFetcher(
        {
            "000001": _make_df(valid_closes),
            "000002": _make_df(weak_closes, amount=10_000_000),
            "000004": one_line_df,
            "000005": _make_df(short_closes),
        }
    )
    sector_fetcher = FakeSectorFetcher(
        [
            {"code": "000001", "name": "强势股", "price": 13.9, "change_pct": 2.0, "amount": 300_000_000},
            {"code": "000002", "name": "低流动", "price": 10.0, "change_pct": 0.5, "amount": 10_000_000},
            {"code": "000003", "name": "*ST风险", "price": 5.0, "change_pct": 1.0, "amount": 200_000_000},
            {"code": "000004", "name": "一字板", "price": 11.0, "change_pct": 10.0, "amount": 300_000_000},
            {"code": "000005", "name": "新股", "price": 10.0, "change_pct": 1.0, "amount": 300_000_000},
        ]
    )

    result = StockScreener(
        daily_fetcher=daily_fetcher,
        sector_fetcher=sector_fetcher,
        min_avg_amount=100_000_000,
    ).screen_hot_sectors(sector_count=1, top_n=1)

    assert len(result.sectors) == 1
    assert len(result.candidates) == 1
    assert result.selected[0].code == "000001"
    assert result.selected[0].composite_score > 0
    assert result.selected[0].is_sector_leader is True
    assert result.selected[0].score_breakdown["sector_leader"] == 5.0
    assert result.selected[0].trend_result.sector_name == "测试行业"
    assert len(result.filtered) == 4
    all_reasons = "；".join("；".join(item["reasons"]) for item in result.filtered)
    assert "近5日平均成交额不足" in all_reasons
    assert "ST或退市风险标的" in all_reasons
    assert "一字涨停" in all_reasons
    assert "历史数据不足60日" in all_reasons


def test_screening_result_report_renders_filtered_detailed_and_row_data():
    class EnumValue:
        def __init__(self, value):
            self.value = value

    trend = SimpleNamespace(
        signal_score=80,
        buy_signal=EnumValue("buy"),
        trend_status=EnumValue("bullish"),
        pattern_signal="breakout",
        breakout_score=12,
        bias_ma5=1.234,
        volume_ratio_5d=1.8,
        stock_vs_benchmark=5.5,
        stock_vs_sector=2.2,
    )
    candidate = ScreenedStock(
        code="000001",
        name="Alpha",
        sector_name="AI",
        sector_type="concept",
        sector_rank=1,
        composite_score=91.236,
        score_breakdown={"trend": 24},
        trend_result=trend,
        average_amount_5d=300_000_000,
        change_pct=2.5,
        is_sector_leader=True,
        risk_flags=["gap"],
    )
    result = ScreeningResult(
        sectors=[SectorCandidate(name="AI", sector_type="concept", rank=1, change_pct=3.0, heat_score=18.5, leading_stock="Alpha")],
        candidates=[candidate],
        selected=[candidate],
        filtered=[{"code": "000002", "name": "Beta", "sector_name": "AI", "reasons": ["weak"]}],
        detailed_results=[
            SimpleNamespace(
                name="Alpha",
                code="000001",
                operation_advice="buy",
                sentiment_score=88,
                trend_prediction="up",
                analysis_summary="summary",
            )
        ],
        generated_at="2026-01-01 09:30:00",
    )

    row = candidate.to_row()
    report = result.format_report()

    assert row["composite_score"] == 91.24
    assert row["risk_flags"] == ["gap"]
    assert result._sector_type_text("concept") != result._sector_type_text("industry")
    assert "weak" in report
    assert "Top" in report
    assert "summary" in report


def test_stock_screener_helper_thresholds_and_history_fallbacks():
    def trend(**overrides):
        base = {
            "adaptive_bias_threshold": 6.0,
            "bias_ma5": 0.0,
            "support_ma5": False,
            "support_ma10": False,
            "breakout_valid": False,
            "breakout_extension_threshold": 8.0,
            "ma20_breakdown": False,
            "relative_strength_score": 6.0,
            "risk_factors": [],
            "signal_score": 70,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    class RaisingDailyFetcher:
        def get_daily_data(self, stock_code, days=120):
            raise RuntimeError("no daily")

    class NoHistorySectorFetcher:
        pass

    screener = StockScreener(
        daily_fetcher=RaisingDailyFetcher(),
        sector_fetcher=NoHistorySectorFetcher(),
        min_avg_amount=100_000_000,
    )
    sector = SectorCandidate(name="AI", rank=1, heat_score=18.0, leading_stock="")

    failed = screener._screen_one_stock({"code": "000001", "name": "Alpha"}, sector, None, None)
    assert failed["reasons"]
    assert screener._get_benchmark_history() is None
    assert screener._get_sector_history(sector) is None
    assert screener._get_sector_history(sector) is None

    daily_df = _make_df([10.0] * 60, amount=50_000_000)
    assert screener._filter_by_daily_data({"amount": 50_000_000}, daily_df)
    assert screener._filter_by_daily_data({}, pd.DataFrame({"close": [1]}))
    assert screener._filter_by_trend({"change_pct": 9.0}, daily_df, trend(bias_ma5=8.0))
    assert screener._filter_by_trend({"change_pct": 1.0}, daily_df, trend(ma20_breakdown=True))
    assert screener._is_sector_leader({"code": "000001", "name": "Alpha"}, SectorCandidate(name="AI", leading_stock="Alpha 000001"))
    assert screener._is_sector_leader({"code": "000001", "name": "Alpha"}, SectorCandidate(name="AI")) is False

    assert screener._buy_point_score(trend(support_ma5=True)) == 20.0
    assert screener._buy_point_score(trend(breakout_valid=True, bias_ma5=1.0)) == 16.0
    assert screener._buy_point_score(trend(bias_ma5=1.0)) == 18.0
    assert screener._buy_point_score(trend(bias_ma5=-4.0)) == 14.0
    assert screener._buy_point_score(trend(bias_ma5=4.0)) == 12.0
    assert screener._buy_point_score(trend(bias_ma5=-6.0)) == 6.0
    assert screener._buy_point_score(trend(bias_ma5=9.0)) == 2.0
    assert screener._liquidity_score(1_000_000_000) == 10.0
    assert screener._liquidity_score(500_000_000) == 9.0
    assert screener._liquidity_score(200_000_000) == 8.0
    assert screener._liquidity_score(100_000_000) == 6.0
    assert screener._liquidity_score(1) == 0.0
    assert screener._sector_heat_score(rank=10, change_pct=10) <= 20.0
    assert screener._safe_float("bad", default=7.0) == 7.0

    class FailingSectorFetcher:
        def get_index_daily_data(self, *args, **kwargs):
            raise RuntimeError("index failed")

        def get_sector_daily_data(self, *args, **kwargs):
            raise RuntimeError("sector failed")

    failing = StockScreener(daily_fetcher=RaisingDailyFetcher(), sector_fetcher=FailingSectorFetcher())
    assert failing._get_benchmark_history() is None
    assert failing._get_sector_history(sector) is None


def test_screening_report_contains_ranking_table():
    closes = [10 + i * 0.05 for i in range(80)]
    daily_fetcher = FakeDailyFetcher({"000001": _make_df(closes)})
    sector_fetcher = FakeSectorFetcher(
        [{"code": "000001", "name": "强势股", "price": 13.9, "change_pct": 2.0, "amount": 300_000_000}]
    )

    result = StockScreener(
        daily_fetcher=daily_fetcher,
        sector_fetcher=sector_fetcher,
        min_avg_amount=100_000_000,
    ).screen_hot_sectors(sector_count=1, top_n=1)

    report = result.format_report()

    assert "热门板块规则选股报告" in report
    assert "| 1 | 000001 | 强势股 | 测试行业 |" in report
