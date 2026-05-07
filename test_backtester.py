import pandas as pd

from backtester import TrendBacktester


def _make_df(closes, highs=None, lows=None):
    highs = highs or [price * 1.01 for price in closes]
    lows = lows or [price * 0.99 for price in closes]
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


def test_backtester_records_buy_signal_trades_and_summary_metrics():
    closes = [10 + i * 0.08 for i in range(100)]
    highs = [price * 1.2 for price in closes]

    result = TrendBacktester(holding_days=5, use_trade_plan_stops=False).run(
        _make_df(closes, highs=highs),
        "000001",
    )

    assert result.summary.signals_evaluated > 0
    assert result.summary.buy_signal_days > 0
    assert result.summary.trade_count > 0
    assert result.summary.win_rate == 100.0
    assert result.summary.average_return_pct > 0
    assert result.trades[0].entry_date > result.trades[0].analysis_date
    assert result.trades[0].exit_reason == "held_5_days"


def test_backtester_can_exit_by_rule_stop_loss():
    closes = [10 + i * 0.05 for i in range(90)]
    highs = [price * 1.2 for price in closes]
    lows = [price * 0.99 for price in closes]
    lows[60] = 8.0

    result = TrendBacktester(holding_days=10, use_trade_plan_stops=True).run(
        _make_df(closes, highs=highs, lows=lows),
        "000001",
    )

    assert result.summary.trade_count > 0
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].return_pct < 0


def test_backtester_runs_standard_multi_horizon_checks():
    closes = [10 + i * 0.06 for i in range(100)]
    highs = [price * 1.2 for price in closes]

    results = TrendBacktester(use_trade_plan_stops=False).run_multi_horizon(
        _make_df(closes, highs=highs),
        "000001",
    )

    assert [result.holding_days for result in results] == [5, 10, 20]
    assert all(result.summary.trade_count > 0 for result in results)
