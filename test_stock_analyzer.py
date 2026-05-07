import pandas as pd

from stock_analyzer import BuySignal, StockTrendAnalyzer, TrendAnalysisResult


def _make_df(closes, highs=None, lows=None):
    highs = highs or [price * 1.02 for price in closes]
    lows = lows or [price * 0.98 for price in closes]
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(closes), freq="D"),
            "open": closes,
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

    assert result.bias_ma5 >= StockTrendAnalyzer.BIAS_THRESHOLD
    assert result.signal_score <= 59
    assert result.buy_signal not in {BuySignal.BUY, BuySignal.STRONG_BUY}


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
