import pandas as pd

from analyzer import AnalysisResult
from stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus
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


def test_stock_screener_edge_helpers_cover_filters_scores_and_reports():
    class DirectDailyFetcher:
        def __init__(self, data=None, error=None):
            self.data = data
            self.error = error

        def get_daily_data(self, stock_code, days=120):
            if self.error:
                raise self.error
            return self.data

    class NoHistorySectorFetcher:
        def get_hot_sectors(self, sector_count=5, include_concepts=True):
            return [{"name": "ConceptA", "sector_type": "concept", "rank": "2", "change_pct": "4.0"}]

        def get_sector_constituents(self, sector_name, sector_type="industry"):
            return []

    class RaisingHistorySectorFetcher(NoHistorySectorFetcher):
        def get_index_daily_data(self, index_code="000300", days=250):
            raise RuntimeError("index down")

        def get_sector_daily_data(self, sector_name, sector_type="industry", days=120):
            raise RuntimeError("sector down")

    class WorkingHistorySectorFetcher(NoHistorySectorFetcher):
        def __init__(self):
            self.calls = 0

        def get_index_daily_data(self, index_code="000300", days=250):
            return _make_df([10.0] * 80)

        def get_sector_daily_data(self, sector_name, sector_type="industry", days=120):
            self.calls += 1
            return _make_df([10.0] * 80)

    class FakeTrendAnalyzer:
        def __init__(self, trend):
            self.trend = trend

        def analyze(self, *args, **kwargs):
            return self.trend

    sector = SectorCandidate(name="ConceptA", sector_type="concept", rank=2, heat_score=12.5, leading_stock="000001 Alpha")
    trend = TrendAnalysisResult(
        code="000001",
        trend_status=TrendStatus.BULL,
        buy_signal=BuySignal.BUY,
        signal_score=70,
        pattern_signal="platform",
        breakout_score=3,
        bias_ma5=1.25,
        volume_ratio_5d=1.4,
        stock_vs_benchmark=2.0,
        stock_vs_sector=3.0,
        relative_strength_score=8,
        risk_factors=["risk one"],
    )
    screened = ScreenedStock(
        code="000001",
        name="Alpha",
        sector_name="ConceptA",
        sector_type="concept",
        sector_rank=2,
        composite_score=88.88,
        score_breakdown={"risk": 7.5},
        trend_result=trend,
        change_pct=2.5,
        turnover_rate=4.0,
        average_amount_5d=600_000_000,
        is_sector_leader=True,
        risk_flags=["risk one"],
    )
    row = screened.to_row()
    assert row["sector_type"] == "concept"
    assert row["trend_status"] == TrendStatus.BULL.value

    detail = AnalysisResult(
        code="000001",
        name="Alpha",
        sentiment_score=70,
        trend_prediction="up",
        operation_advice="buy",
        analysis_summary="detail summary",
    )
    report = ScreeningResult(
        sectors=[sector],
        candidates=[screened],
        selected=[screened],
        filtered=[{"code": "000009", "name": "Filtered", "sector_name": "ConceptA", "reasons": ["bad quote"]}],
        detailed_results=[detail],
    ).format_report()
    assert "Filtered" in report
    assert "detail summary" in report
    assert "Alpha(000001)" in report

    screener = StockScreener(DirectDailyFetcher(_make_df([10.0] * 80)), NoHistorySectorFetcher())
    sectors = screener._build_sector_candidates(
        [{"name": "", "rank": "-", "change_pct": "--"}, {"name": "ConceptA", "sector_type": "concept"}],
        5,
    )
    assert sectors[0].name == "ConceptA"
    assert screener._prefilter_quote({"code": "9BAD", "name": "Normal", "price": 0, "amount": 0})
    assert screener._filter_by_daily_data({"amount": 1}, pd.DataFrame())
    assert screener._filter_by_daily_data({"amount": 1}, None)
    assert screener._average_amount_5d(pd.DataFrame({"volume": [1, 2]}), fallback=123.0) == 123.0
    assert screener._safe_float("1,234.5%") == 1234.5
    assert screener._safe_float("--", default=7.0) == 7.0
    assert screener._safe_float(object(), default=9.0) == 9.0

    chasing = TrendAnalysisResult(code="000002", bias_ma5=8.0, adaptive_bias_threshold=5.0, ma20_breakdown=True)
    trend_reasons = screener._filter_by_trend({"change_pct": 9.0}, _make_df([10.0] * 80), chasing)
    assert len(trend_reasons) == 2
    risk_breakdown = screener._score_candidate(sector, chasing, 50_000_000, is_sector_leader=False)
    assert risk_breakdown["risk"] == 0.0

    support_trend = TrendAnalysisResult(code="s", support_ma5=True)
    breakout_trend = TrendAnalysisResult(code="b", breakout_valid=True, bias_ma5=1.0, breakout_extension_threshold=2.0)
    assert screener._buy_point_score(support_trend) == 20.0
    assert screener._buy_point_score(breakout_trend) == 16.0
    assert screener._buy_point_score(TrendAnalysisResult(code="flat", bias_ma5=0.0)) == 18.0
    assert screener._buy_point_score(TrendAnalysisResult(code="dip", bias_ma5=-4.0)) == 14.0
    assert screener._buy_point_score(TrendAnalysisResult(code="near", bias_ma5=3.0, adaptive_bias_threshold=5.0)) == 12.0
    assert screener._buy_point_score(TrendAnalysisResult(code="deep", bias_ma5=-6.0)) == 6.0
    assert screener._buy_point_score(TrendAnalysisResult(code="high", bias_ma5=8.0, adaptive_bias_threshold=5.0)) == 2.0
    assert [screener._liquidity_score(value) for value in [1_000_000_000, 500_000_000, 200_000_000, 100_000_000, 1]] == [
        10.0,
        9.0,
        8.0,
        6.0,
        0.0,
    ]

    raising = StockScreener(DirectDailyFetcher(_make_df([10.0] * 80)), RaisingHistorySectorFetcher())
    assert raising._get_benchmark_history() is None
    assert raising._get_benchmark_history() is None
    assert raising._get_sector_history(sector) is None

    working_fetcher = WorkingHistorySectorFetcher()
    working = StockScreener(DirectDailyFetcher(_make_df([10.0] * 80)), working_fetcher)
    assert working._get_sector_history(sector) is not None
    assert working._get_sector_history(sector) is not None
    assert working_fetcher.calls == 1
    assert working._fetch_daily_data("000001").shape[0] == 80

    fetch_error = StockScreener(DirectDailyFetcher(error=RuntimeError("daily down")), NoHistorySectorFetcher())
    filtered = fetch_error._screen_one_stock({"code": "000001", "name": "Alpha"}, sector, None, None)
    assert "daily down" in filtered["reasons"][0]

    trend_filtered = StockScreener(
        DirectDailyFetcher(_make_df([10.0] * 80)),
        NoHistorySectorFetcher(),
        trend_analyzer=FakeTrendAnalyzer(chasing),
    )._screen_one_stock({"code": "000002", "name": "Beta", "change_pct": 9.0}, sector, None, None)
    assert len(trend_filtered["reasons"]) == 2
