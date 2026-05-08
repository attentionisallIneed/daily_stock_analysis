import pandas as pd

from stock_screener import StockScreener


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
