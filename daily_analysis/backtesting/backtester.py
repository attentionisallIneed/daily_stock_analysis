# -*- coding: utf-8 -*-
"""
Minimal rule-layer backtester for StockTrendAnalyzer.

The backtester evaluates historical OHLCV data offline. It intentionally keeps
LLM, news, notification, and live data dependencies out of the loop so strategy
thresholds can be tested cheaply and repeatedly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from daily_analysis.analysis.stock_analyzer import BuySignal, StockTrendAnalyzer, TrendAnalysisResult


DEFAULT_BUY_SIGNALS = frozenset({BuySignal.BUY, BuySignal.STRONG_BUY})


def _format_date(value: object) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


@dataclass
class BacktestTrade:
    code: str
    analysis_date: object
    entry_date: object
    exit_date: object
    entry_price: float
    exit_price: float
    holding_days: int
    signal: str
    signal_score: int
    return_pct: float
    max_drawdown_pct: float
    exit_reason: str
    risk_reward_ratio: float
    exit_index: int = field(repr=False)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "analysis_date": _format_date(self.analysis_date),
            "entry_date": _format_date(self.entry_date),
            "exit_date": _format_date(self.exit_date),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "holding_days": self.holding_days,
            "signal": self.signal,
            "signal_score": self.signal_score,
            "return_pct": self.return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "exit_reason": self.exit_reason,
            "risk_reward_ratio": self.risk_reward_ratio,
        }


@dataclass
class BacktestSummary:
    code: str
    holding_days: int
    signals_evaluated: int
    buy_signal_days: int
    trade_count: int
    win_rate: float
    average_return_pct: float
    median_return_pct: float
    best_return_pct: float
    worst_return_pct: float
    max_drawdown_pct: float
    profit_loss_ratio: Optional[float]
    average_holding_days: float

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "holding_days": self.holding_days,
            "signals_evaluated": self.signals_evaluated,
            "buy_signal_days": self.buy_signal_days,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "average_return_pct": self.average_return_pct,
            "median_return_pct": self.median_return_pct,
            "best_return_pct": self.best_return_pct,
            "worst_return_pct": self.worst_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_loss_ratio": self.profit_loss_ratio,
            "average_holding_days": self.average_holding_days,
        }


@dataclass
class BacktestResult:
    code: str
    holding_days: int
    summary: BacktestSummary
    trades: List[BacktestTrade]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "holding_days": self.holding_days,
            "summary": self.summary.to_dict(),
            "trades": [trade.to_dict() for trade in self.trades],
        }


class TrendBacktester:
    """Backtest StockTrendAnalyzer buy signals on daily bars."""

    def __init__(
        self,
        analyzer: Optional[StockTrendAnalyzer] = None,
        min_history: int = 60,
        holding_days: int = 10,
        use_trade_plan_stops: bool = True,
        allow_overlap: bool = False,
        buy_signals: Iterable[BuySignal] = DEFAULT_BUY_SIGNALS,
    ) -> None:
        if min_history < 20:
            raise ValueError("min_history must be at least 20")
        if holding_days < 1:
            raise ValueError("holding_days must be at least 1")

        self.analyzer = analyzer or StockTrendAnalyzer()
        self.min_history = min_history
        self.holding_days = holding_days
        self.use_trade_plan_stops = use_trade_plan_stops
        self.allow_overlap = allow_overlap
        self.buy_signals = set(buy_signals)

    def run(self, df: pd.DataFrame, code: str, holding_days: Optional[int] = None) -> BacktestResult:
        """Run one fixed-horizon backtest for a single stock."""
        holding_days = holding_days or self.holding_days
        if holding_days < 1:
            raise ValueError("holding_days must be at least 1")

        prices = self._prepare_data(df)
        trades: List[BacktestTrade] = []
        signals_evaluated = 0
        buy_signal_days = 0

        if len(prices) <= self.min_history:
            summary = self._build_summary(code, holding_days, signals_evaluated, buy_signal_days, trades)
            return BacktestResult(code=code, holding_days=holding_days, summary=summary, trades=trades)

        index = self.min_history - 1
        last_signal_index = len(prices) - 2

        while index <= last_signal_index:
            history = prices.iloc[: index + 1]
            analysis = self.analyzer.analyze(history, code)
            signals_evaluated += 1

            if analysis.buy_signal in self.buy_signals:
                buy_signal_days += 1
                trade = self._simulate_trade(prices, index, code, analysis, holding_days)
                trades.append(trade)
                if not self.allow_overlap:
                    index = trade.exit_index + 1
                    continue

            index += 1

        summary = self._build_summary(code, holding_days, signals_evaluated, buy_signal_days, trades)
        return BacktestResult(code=code, holding_days=holding_days, summary=summary, trades=trades)

    def run_multi_horizon(
        self,
        df: pd.DataFrame,
        code: str,
        holding_days_options: Sequence[int] = (5, 10, 20),
    ) -> List[BacktestResult]:
        """Run several fixed holding-period tests against the same history."""
        return [self.run(df, code, holding_days=days) for days in holding_days_options]

    def _simulate_trade(
        self,
        prices: pd.DataFrame,
        signal_index: int,
        code: str,
        analysis: TrendAnalysisResult,
        holding_days: int,
    ) -> BacktestTrade:
        entry_index = signal_index + 1
        exit_index = min(entry_index + holding_days - 1, len(prices) - 1)
        entry_row = prices.iloc[entry_index]
        exit_row = prices.iloc[exit_index]

        entry_price = float(entry_row["open"])
        exit_price = float(exit_row["close"])
        exit_reason = f"held_{holding_days}_days"

        stop_loss = analysis.stop_loss if 0 < analysis.stop_loss < entry_price else 0.0
        take_profit = analysis.take_profit if analysis.take_profit > entry_price else 0.0

        if self.use_trade_plan_stops and (stop_loss > 0 or take_profit > 0):
            for row_index in range(entry_index, exit_index + 1):
                row = prices.iloc[row_index]
                if stop_loss > 0 and float(row["low"]) <= stop_loss:
                    exit_index = row_index
                    exit_row = row
                    exit_price = stop_loss
                    exit_reason = "stop_loss"
                    break
                if take_profit > 0 and float(row["high"]) >= take_profit:
                    exit_index = row_index
                    exit_row = row
                    exit_price = take_profit
                    exit_reason = "take_profit"
                    break

        lows = prices.iloc[entry_index : exit_index + 1]["low"]
        max_drawdown_pct = 0.0
        if entry_price > 0 and not lows.empty:
            adverse_move = (float(lows.min()) - entry_price) / entry_price * 100
            max_drawdown_pct = round(abs(min(0.0, adverse_move)), 2)

        return_pct = round((exit_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0
        actual_holding_days = exit_index - entry_index + 1

        return BacktestTrade(
            code=code,
            analysis_date=prices.iloc[signal_index]["date"],
            entry_date=entry_row["date"],
            exit_date=exit_row["date"],
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            holding_days=actual_holding_days,
            signal=analysis.buy_signal.value,
            signal_score=analysis.signal_score,
            return_pct=return_pct,
            max_drawdown_pct=max_drawdown_pct,
            exit_reason=exit_reason,
            risk_reward_ratio=analysis.risk_reward_ratio,
            exit_index=exit_index,
        )

    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            raise ValueError("df must contain historical OHLCV data")

        prices = df.copy()
        prices.columns = [str(column).strip().lower() for column in prices.columns]

        if "date" not in prices.columns:
            raise ValueError("df must contain a date column")
        if "close" not in prices.columns:
            raise ValueError("df must contain a close column")

        for column in ("open", "high", "low"):
            if column not in prices.columns:
                prices[column] = prices["close"]
        if "volume" not in prices.columns:
            prices["volume"] = 0

        for column in ("open", "high", "low", "close", "volume"):
            prices[column] = pd.to_numeric(prices[column], errors="coerce")

        prices = prices.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)
        if prices.empty:
            raise ValueError("df has no valid price rows")

        return prices

    def _build_summary(
        self,
        code: str,
        holding_days: int,
        signals_evaluated: int,
        buy_signal_days: int,
        trades: List[BacktestTrade],
    ) -> BacktestSummary:
        if not trades:
            return BacktestSummary(
                code=code,
                holding_days=holding_days,
                signals_evaluated=signals_evaluated,
                buy_signal_days=buy_signal_days,
                trade_count=0,
                win_rate=0.0,
                average_return_pct=0.0,
                median_return_pct=0.0,
                best_return_pct=0.0,
                worst_return_pct=0.0,
                max_drawdown_pct=0.0,
                profit_loss_ratio=None,
                average_holding_days=0.0,
            )

        returns = pd.Series([trade.return_pct for trade in trades], dtype="float64")
        wins = returns[returns > 0]
        losses = returns[returns < 0].abs()

        profit_loss_ratio: Optional[float]
        if not wins.empty and not losses.empty and losses.mean() > 0:
            profit_loss_ratio = round(float(wins.mean() / losses.mean()), 2)
        elif not wins.empty:
            profit_loss_ratio = None
        else:
            profit_loss_ratio = 0.0

        equity = 1.0
        peak = 1.0
        max_drawdown_pct = 0.0
        for value in returns:
            equity *= 1 + float(value) / 100
            peak = max(peak, equity)
            if peak > 0:
                drawdown = (peak - equity) / peak * 100
                max_drawdown_pct = max(max_drawdown_pct, drawdown)

        return BacktestSummary(
            code=code,
            holding_days=holding_days,
            signals_evaluated=signals_evaluated,
            buy_signal_days=buy_signal_days,
            trade_count=len(trades),
            win_rate=round(float((returns > 0).mean() * 100), 2),
            average_return_pct=round(float(returns.mean()), 2),
            median_return_pct=round(float(returns.median()), 2),
            best_return_pct=round(float(returns.max()), 2),
            worst_return_pct=round(float(returns.min()), 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            profit_loss_ratio=profit_loss_ratio,
            average_holding_days=round(sum(trade.holding_days for trade in trades) / len(trades), 2),
        )


def run_backtest_from_csv(
    csv_path: str | Path,
    code: Optional[str] = None,
    holding_days: int = 10,
    use_trade_plan_stops: bool = True,
) -> BacktestResult:
    """Convenience wrapper for ad hoc CSV backtests."""
    path = Path(csv_path)
    df = pd.read_csv(path)
    stock_code = code or (str(df["code"].iloc[0]) if "code" in df.columns and not df.empty else path.stem)
    return TrendBacktester(holding_days=holding_days, use_trade_plan_stops=use_trade_plan_stops).run(df, stock_code)
