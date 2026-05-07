import pandas as pd

from stock_analyzer import BuySignal, StockTrendAnalyzer, TrendAnalysisResult


def _make_df(closes, highs=None, lows=None, opens=None):
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
        }
    )


def test_trade_plan_generates_rule_prices_and_good_risk_reward():
    closes = [10 + i * 0.05 for i in range(80)]
    closes[-1] = 13.78
    highs = [price * 1.01 for price in closes]
    lows = [price * 0.98 for price in closes]
    highs[-20:] = [15.2] * 20

    result = StockTrendAnalyzer().analyze(_make_df(closes, highs=highs, lows=lows), "000001")

    assert result.ideal_buy > 0
    assert result.stop_loss > 0
    assert result.take_profit > result.ideal_buy
    assert result.risk_reward_ratio >= 1.8
    assert result.buy_signal in {BuySignal.BUY, BuySignal.STRONG_BUY}


def test_low_risk_reward_downgrades_buy_signal_to_wait():
    closes = [10 + i * 0.05 for i in range(80)]
    closes[-1] = 13.72
    highs = [price * 1.01 for price in closes]
    lows = [price * 0.98 for price in closes]
    highs[-20:] = [13.82] * 20

    result = StockTrendAnalyzer().analyze(_make_df(closes, highs=highs, lows=lows), "000001")

    assert 0 < result.risk_reward_ratio < 1.2
    assert result.signal_score <= 59
    assert result.buy_signal == BuySignal.WAIT


def test_high_ma5_bias_keeps_no_chasing_discipline():
    closes = [10 + i * 0.02 for i in range(80)]
    closes[-1] = closes[-2] * 1.12

    result = StockTrendAnalyzer().analyze(_make_df(closes), "000001")

    assert result.bias_ma5 >= result.adaptive_bias_threshold
    assert result.signal_score <= 59
    assert result.buy_signal not in {BuySignal.BUY, BuySignal.STRONG_BUY}


def test_low_volatility_tightens_bias_threshold_and_blocks_chasing():
    closes = [10.0] * 79 + [10.3]
    highs = [price * 1.001 for price in closes]
    lows = [price * 0.999 for price in closes]

    result = StockTrendAnalyzer().analyze(_make_df(closes, highs=highs, lows=lows), "000001")

    assert 0 < result.adaptive_bias_threshold < StockTrendAnalyzer.BIAS_THRESHOLD
    assert result.bias_ma5 > result.adaptive_bias_threshold
    assert result.signal_score <= 59
    assert result.buy_signal not in {BuySignal.BUY, BuySignal.STRONG_BUY}


def test_atr_stop_tightens_rule_stop_for_low_volatility_stock():
    closes = [10.0] * 79 + [10.05]
    highs = [price * 1.001 for price in closes]
    lows = [price * 0.999 for price in closes]

    result = StockTrendAnalyzer().analyze(_make_df(closes, highs=highs, lows=lows), "000001")

    atr_stop = round(result.ideal_buy - StockTrendAnalyzer.ATR_STOP_MULTIPLIER * result.atr_20, 2)
    assert result.atr_20 > 0
    assert result.stop_loss == atr_stop
    assert result.stop_loss > round(result.ma20 * 0.98, 2)
    assert "ATR" in result.invalidation_condition


def test_relative_strength_compares_stock_to_benchmark_and_sector():
    stock_closes = [10.0] * 59 + [10.0 + i * 0.1 for i in range(21)]
    benchmark_closes = [10.0] * 80
    sector_closes = [10.0] * 59 + [10.0 + i * 0.05 for i in range(21)]

    result = StockTrendAnalyzer().analyze(
        _make_df(stock_closes),
        "000001",
        benchmark_df=_make_df(benchmark_closes),
        sector_df=_make_df(sector_closes),
        sector_name="测试行业",
    )

    assert result.stock_return_20d == 20.0
    assert result.benchmark_return_20d == 0.0
    assert result.sector_return_20d == 10.0
    assert result.stock_vs_benchmark == 20.0
    assert result.stock_vs_sector == 10.0
    assert result.sector_vs_benchmark == 10.0
    assert result.relative_strength_score == 10
    assert result.relative_strength_status == "明显强于基准/行业"
    assert "测试行业" in result.relative_strength_summary
    assert result.to_dict()["relative_strength_score"] == 10


def test_weak_relative_strength_caps_buy_score():
    stock_closes = [10.0] * 80
    benchmark_closes = [10.0] * 59 + [10.0 + i * 0.1 for i in range(21)]
    sector_closes = [10.0] * 59 + [10.0 + i * 0.08 for i in range(21)]

    result = StockTrendAnalyzer().analyze(
        _make_df(stock_closes),
        "000001",
        benchmark_df=_make_df(benchmark_closes),
        sector_df=_make_df(sector_closes),
        sector_name="测试行业",
    )

    assert result.relative_strength_score <= -6
    assert result.relative_strength_status == "明显弱于基准/行业"
    assert result.signal_score <= 64
    assert any("相对强弱" in risk for risk in result.risk_factors)


def test_kline_reclaim_confirms_ma5_support():
    closes = [10.0] * 79 + [10.05]
    opens = [10.0] * 79 + [9.98]
    highs = [10.04] * 79 + [10.08]
    lows = [9.98] * 79 + [9.96]

    result = StockTrendAnalyzer().analyze(
        _make_df(closes, highs=highs, lows=lows, opens=opens),
        "000001",
    )

    assert result.support_ma5 is True
    assert result.ma5_touch_reclaim is True
    assert result.bullish_candle is True
    assert "回踩MA5后收回" in result.support_confirmation


def test_near_ma5_without_kline_confirmation_does_not_count_as_support():
    closes = [10.0] * 79 + [9.95]
    opens = [10.0] * 79 + [10.02]
    highs = [10.04] * 79 + [10.03]
    lows = [9.98] * 79 + [9.94]

    result = StockTrendAnalyzer().analyze(
        _make_df(closes, highs=highs, lows=lows, opens=opens),
        "000001",
    )

    assert result.support_ma5 is False
    assert result.signal_score <= 64
    assert any("尚未出现K线支撑确认" in risk for risk in result.risk_factors)


def test_ma20_breakdown_downgrades_buy_signal():
    closes = [10.0] * 79 + [9.5]
    opens = [10.0] * 79 + [9.8]
    highs = [10.04] * 79 + [9.85]
    lows = [9.98] * 79 + [9.45]

    result = StockTrendAnalyzer().analyze(
        _make_df(closes, highs=highs, lows=lows, opens=opens),
        "000001",
    )

    assert result.ma20_breakdown is True
    assert result.signal_score <= 49
    assert result.buy_signal not in {BuySignal.BUY, BuySignal.STRONG_BUY}
    assert any("跌破MA20" in risk for risk in result.risk_factors)


def test_position_model_generates_rule_position_from_market_and_risk_reward():
    closes = [10 + i * 0.05 for i in range(80)]
    closes[-1] = 13.78
    highs = [price * 1.01 for price in closes]
    highs[-20:] = [15.2] * 20

    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(_make_df(closes, highs=highs), "000001")
    analyzer.apply_position_model(result, market_status="强势")

    assert result.base_position_pct > 0
    assert result.market_position_multiplier == 1.0
    assert result.risk_reward_position_multiplier > 0
    assert 0 < result.final_position_pct <= result.base_position_pct
    assert "规则建议仓位" in result.position_note


def test_position_model_zeros_position_in_extremely_weak_market():
    result = TrendAnalysisResult(
        code="000001",
        signal_score=90,
        ideal_buy=10.0,
        stop_loss=9.5,
        risk_reward_ratio=2.0,
    )

    StockTrendAnalyzer().apply_position_model(result, market_status="极弱")

    assert result.base_position_pct == 30.0
    assert result.market_position_multiplier == 0.0
    assert result.final_position_pct == 0.0
    assert "极弱" in result.position_note


def test_position_model_caps_position_by_single_trade_risk_budget():
    result = TrendAnalysisResult(
        code="000001",
        signal_score=90,
        ideal_buy=10.0,
        stop_loss=9.0,
        risk_reward_ratio=2.0,
    )

    StockTrendAnalyzer().apply_position_model(result, market_status="强势", account_risk_budget_pct=1.0)

    assert result.base_position_pct == 30.0
    assert result.single_trade_risk_pct == 10.0
    assert result.max_position_by_risk_pct == 10.0
    assert result.final_position_pct == 10.0
