# -*- coding: utf-8 -*-
"""
热门板块驱动的规则层选股器。

该模块只负责低成本粗筛和排序，不直接让 LLM 参与候选池筛选。
Top N 候选股可由主流程复用现有 analyze_stock() 做精细报告。
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from analyzer import AnalysisResult
from stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class SectorCandidate:
    """进入粗筛的热门板块。"""

    name: str
    sector_type: str = "industry"
    rank: int = 0
    change_pct: float = 0.0
    heat_score: float = 0.0
    code: str = ""
    leading_stock: str = ""


@dataclass
class ScreenedStock:
    """规则层筛出的个股候选。"""

    code: str
    name: str
    sector_name: str
    sector_type: str
    sector_rank: int
    composite_score: float
    score_breakdown: Dict[str, float]
    trend_result: TrendAnalysisResult
    change_pct: float = 0.0
    turnover_rate: float = 0.0
    average_amount_5d: float = 0.0
    is_sector_leader: bool = False
    filter_reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)

    def to_row(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "sector_name": self.sector_name,
            "sector_type": self.sector_type,
            "composite_score": round(self.composite_score, 2),
            "trend_score": self.trend_result.signal_score,
            "buy_signal": self.trend_result.buy_signal.value,
            "trend_status": self.trend_result.trend_status.value,
            "pattern_signal": self.trend_result.pattern_signal,
            "breakout_score": self.trend_result.breakout_score,
            "bias_ma5": round(self.trend_result.bias_ma5, 2),
            "volume_ratio_5d": round(self.trend_result.volume_ratio_5d, 2),
            "stock_vs_benchmark": self.trend_result.stock_vs_benchmark,
            "stock_vs_sector": self.trend_result.stock_vs_sector,
            "average_amount_5d": round(self.average_amount_5d, 2),
            "change_pct": self.change_pct,
            "is_sector_leader": self.is_sector_leader,
            "risk_flags": self.risk_flags,
        }


@dataclass
class ScreeningResult:
    """热门板块选股结果。"""

    sectors: List[SectorCandidate] = field(default_factory=list)
    candidates: List[ScreenedStock] = field(default_factory=list)
    selected: List[ScreenedStock] = field(default_factory=list)
    filtered: List[Dict[str, Any]] = field(default_factory=list)
    detailed_results: List[AnalysisResult] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "sector_count": len(self.sectors),
            "candidate_count": len(self.candidates),
            "selected_count": len(self.selected),
            "filtered_count": len(self.filtered),
        }

    def format_report(self) -> str:
        """生成 Markdown 规则层选股报告。"""
        stats = self.stats
        lines = [
            f"# 热门板块规则选股报告",
            "",
            f"> 生成时间：{self.generated_at}",
            "",
            "## 板块概览",
            "",
            "| 排名 | 类型 | 板块 | 涨跌幅 | 热度分 | 领涨股 |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]

        for sector in self.sectors:
            lines.append(
                f"| {sector.rank} | {self._sector_type_text(sector.sector_type)} | {sector.name} | "
                f"{sector.change_pct:+.2f}% | {sector.heat_score:.1f} | {sector.leading_stock or '-'} |"
            )

        lines.extend(
            [
                "",
                "## 候选池统计",
                "",
                f"- 热门板块数：{stats['sector_count']}",
                f"- 有效候选数：{stats['candidate_count']}",
                f"- 入选 Top 数：{stats['selected_count']}",
                f"- 过滤数：{stats['filtered_count']}",
                "",
                "## 排序结果",
                "",
                "| 排名 | 代码 | 名称 | 板块 | 龙头 | 综合分 | 趋势分 | 信号 | 形态 | MA5乖离 | 量比 | 相对大盘 | 相对行业 | 5日均成交额 |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for idx, candidate in enumerate(self.candidates[:20], start=1):
            trend = candidate.trend_result
            lines.append(
                f"| {idx} | {candidate.code} | {candidate.name} | {candidate.sector_name} | "
                f"{'是' if candidate.is_sector_leader else '-'} | "
                f"{candidate.composite_score:.1f} | {trend.signal_score} | {trend.buy_signal.value} | "
                f"{trend.pattern_signal}({trend.breakout_score:+d}) | "
                f"{trend.bias_ma5:+.2f}% | {trend.volume_ratio_5d:.2f} | "
                f"{trend.stock_vs_benchmark:+.2f}pct | {trend.stock_vs_sector:+.2f}pct | "
                f"{candidate.average_amount_5d / 100000000:.2f}亿 |"
            )

        if self.filtered:
            lines.extend(
                [
                    "",
                    "## 过滤样本",
                    "",
                    "| 代码 | 名称 | 板块 | 原因 |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for item in self.filtered[:20]:
                reasons = "；".join(item.get("reasons") or [])
                lines.append(
                    f"| {item.get('code', '-')} | {item.get('name', '-')} | "
                    f"{item.get('sector_name', '-')} | {reasons or '-'} |"
                )

        if self.detailed_results:
            lines.extend(["", "## Top 个股精细报告", ""])
            for detail in self.detailed_results:
                lines.extend(
                    [
                        f"### {detail.name}({detail.code})",
                        "",
                        f"- 操作建议：{detail.operation_advice}",
                        f"- 综合评分：{detail.sentiment_score}",
                        f"- 趋势判断：{detail.trend_prediction}",
                        f"- 核心摘要：{detail.analysis_summary}",
                        "",
                    ]
                )

        return "\n".join(lines)

    @staticmethod
    def _sector_type_text(sector_type: str) -> str:
        return "概念" if sector_type == "concept" else "行业"


class StockScreener:
    """热门板块驱动的规则层选股器。"""

    MIN_HISTORY_DAYS = 60
    MIN_AVG_AMOUNT = 100_000_000.0
    MAX_CHASING_CHANGE_PCT = 8.0

    def __init__(
        self,
        daily_fetcher: Any,
        sector_fetcher: Any,
        trend_analyzer: Optional[StockTrendAnalyzer] = None,
        min_avg_amount: float = MIN_AVG_AMOUNT,
        min_history_days: int = MIN_HISTORY_DAYS,
        max_chasing_change_pct: float = MAX_CHASING_CHANGE_PCT,
    ):
        self.daily_fetcher = daily_fetcher
        self.sector_fetcher = sector_fetcher
        self.trend_analyzer = trend_analyzer or StockTrendAnalyzer()
        self.min_avg_amount = min_avg_amount
        self.min_history_days = min_history_days
        self.max_chasing_change_pct = max_chasing_change_pct
        self._benchmark_df: Optional[pd.DataFrame] = None
        self._benchmark_loaded = False
        self._sector_history_cache: Dict[Tuple[str, str], Optional[pd.DataFrame]] = {}

    def screen_hot_sectors(
        self,
        sector_count: int = 5,
        top_n: int = 3,
        include_concepts: bool = True,
        benchmark_df: Optional[pd.DataFrame] = None,
        prefer_leading_stocks: bool = False,
    ) -> ScreeningResult:
        """按热门板块生成候选池并排序。"""
        result = ScreeningResult()
        raw_sectors = self.sector_fetcher.get_hot_sectors(
            sector_count=sector_count,
            include_concepts=include_concepts,
        )
        result.sectors = self._build_sector_candidates(raw_sectors, sector_count)
        benchmark_df = benchmark_df if benchmark_df is not None else self._get_benchmark_history()

        seen_codes = set()
        for sector in result.sectors:
            leading_rows = self._leading_stock_rows(sector)
            if prefer_leading_stocks and leading_rows:
                for row in leading_rows:
                    self._screen_constituent_row(row, sector, benchmark_df, None, seen_codes, result)
                continue

            try:
                constituents = self.sector_fetcher.get_sector_constituents(
                    sector.name,
                    sector_type=sector.sector_type,
                )
            except Exception as e:
                logger.warning(f"[选股] 获取板块 {sector.name} 成分股失败: {e}")
                constituents = leading_rows
                if not constituents:
                    continue

            sector_df = self._get_sector_history(sector)
            for row in constituents:
                self._screen_constituent_row(row, sector, benchmark_df, sector_df, seen_codes, result)

        result.candidates.sort(key=lambda item: item.composite_score, reverse=True)
        result.selected = result.candidates[: max(1, top_n)]
        return result

    def _screen_constituent_row(
        self,
        row: Dict[str, Any],
        sector: SectorCandidate,
        benchmark_df: Optional[pd.DataFrame],
        sector_df: Optional[pd.DataFrame],
        seen_codes: set,
        result: ScreeningResult,
    ) -> None:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code or not name or code in seen_codes:
            return
        seen_codes.add(code)

        prefilter_reasons = self._prefilter_quote(row)
        if prefilter_reasons:
            result.filtered.append(
                {"code": code, "name": name, "sector_name": sector.name, "reasons": prefilter_reasons}
            )
            return

        candidate = self._screen_one_stock(row, sector, benchmark_df, sector_df)
        if isinstance(candidate, ScreenedStock):
            result.candidates.append(candidate)
        else:
            result.filtered.append(candidate)

    def _leading_stock_rows(self, sector: SectorCandidate) -> List[Dict[str, Any]]:
        """Build a minimal candidate row from the sector API's leading-stock field."""
        name, code = self._parse_leading_stock(sector.leading_stock)
        if name and not code and hasattr(self.sector_fetcher, "resolve_stock_code_by_name"):
            try:
                code = str(self.sector_fetcher.resolve_stock_code_by_name(name) or "")
            except Exception as exc:
                logger.warning(f"[选股] 解析领涨股 {name} 代码失败: {exc}")
        if not name or not code:
            return []
        return [
            {
                "code": code,
                "name": name,
                "price": 0.0,
                "change_pct": sector.change_pct,
                "amount": 0.0,
                "turnover_rate": 0.0,
                "from_leading_stock": True,
            }
        ]

    @staticmethod
    def _parse_leading_stock(value: str) -> Tuple[str, str]:
        text = str(value or "").strip()
        if not text:
            return "", ""
        text = re.split(r"[、,/，\s]+", text)[0].strip()
        code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        code = code_match.group(1) if code_match else ""
        name = re.sub(r"(?<!\d)\d{6}(?!\d)", "", text)
        name = re.sub(r"(涨跌幅|涨幅|涨停|[\(\)（）:：])", "", name)
        name = re.sub(r"[0-9.+%\\-]+$", "", name).strip()
        return name or text, code

    def _build_sector_candidates(self, raw_sectors: List[Dict[str, Any]], sector_count: int) -> List[SectorCandidate]:
        sectors = []
        for idx, raw in enumerate(raw_sectors[: max(1, sector_count)], start=1):
            change_pct = self._safe_float(raw.get("change_pct"))
            rank = int(self._safe_float(raw.get("rank"), idx)) or idx
            heat_score = self._sector_heat_score(rank, change_pct)
            sectors.append(
                SectorCandidate(
                    name=str(raw.get("name") or "").strip(),
                    sector_type=str(raw.get("sector_type") or "industry"),
                    rank=rank,
                    change_pct=change_pct,
                    heat_score=heat_score,
                    code=str(raw.get("code") or ""),
                    leading_stock=str(raw.get("leading_stock") or ""),
                )
            )
        return [sector for sector in sectors if sector.name]

    def _screen_one_stock(
        self,
        row: Dict[str, Any],
        sector: SectorCandidate,
        benchmark_df: Optional[pd.DataFrame],
        sector_df: Optional[pd.DataFrame],
    ) -> ScreenedStock | Dict[str, Any]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()

        try:
            daily_df = self._fetch_daily_data(code)
        except Exception as e:
            return {"code": code, "name": name, "sector_name": sector.name, "reasons": [f"日线数据获取失败: {e}"]}

        filter_reasons = self._filter_by_daily_data(row, daily_df)
        if filter_reasons:
            return {"code": code, "name": name, "sector_name": sector.name, "reasons": filter_reasons}

        trend = self.trend_analyzer.analyze(
            daily_df,
            code,
            benchmark_df=benchmark_df,
            sector_df=sector_df,
            sector_name=sector.name,
            security_name=name,
        )

        filter_reasons = self._filter_by_trend(row, daily_df, trend)
        if filter_reasons:
            return {"code": code, "name": name, "sector_name": sector.name, "reasons": filter_reasons}

        average_amount_5d = self._average_amount_5d(daily_df, fallback=self._safe_float(row.get("amount")))
        change_pct = self._safe_float(row.get("change_pct"))
        turnover_rate = self._safe_float(row.get("turnover_rate"))
        is_sector_leader = self._is_sector_leader(row, sector)
        breakdown = self._score_candidate(sector, trend, average_amount_5d, is_sector_leader)
        composite_score = sum(breakdown.values())
        risk_flags = list(trend.risk_factors)

        return ScreenedStock(
            code=code,
            name=name,
            sector_name=sector.name,
            sector_type=sector.sector_type,
            sector_rank=sector.rank,
            composite_score=round(composite_score, 2),
            score_breakdown=breakdown,
            trend_result=trend,
            change_pct=change_pct,
            turnover_rate=turnover_rate,
            average_amount_5d=average_amount_5d,
            is_sector_leader=is_sector_leader,
            risk_flags=risk_flags,
        )

    def _prefilter_quote(self, row: Dict[str, Any]) -> List[str]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        reasons = []
        if "ST" in name.upper() or "退" in name:
            reasons.append("ST或退市风险标的")
        if not code.startswith(("0", "3", "4", "6", "8")):
            reasons.append("非A股常见代码段")

        price = self._safe_float(row.get("price"))
        amount = self._safe_float(row.get("amount"))
        if not row.get("from_leading_stock") and price <= 0 and amount <= 0:
            reasons.append("停牌或实时行情无有效成交")
        return reasons

    def _filter_by_daily_data(self, row: Dict[str, Any], daily_df: pd.DataFrame) -> List[str]:
        reasons = []
        if daily_df is None or daily_df.empty or len(daily_df) < self.min_history_days:
            reasons.append(f"历史数据不足{self.min_history_days}日")
            return reasons

        average_amount_5d = self._average_amount_5d(daily_df, fallback=self._safe_float(row.get("amount")))
        if average_amount_5d < self.min_avg_amount:
            reasons.append(f"近5日平均成交额不足{self.min_avg_amount / 100000000:.1f}亿")

        latest = daily_df.iloc[-1]
        high = self._safe_float(latest.get("high"))
        low = self._safe_float(latest.get("low"))
        close = self._safe_float(latest.get("close"))
        open_price = self._safe_float(latest.get("open"))
        change_pct = self._safe_float(row.get("change_pct"))
        if change_pct >= 9.5 and high == low and high > 0:
            reasons.append("一字涨停，流动性不足")
        elif change_pct >= 9.5 and min(open_price, high, low, close) == max(open_price, high, low, close) and close > 0:
            reasons.append("一字涨停，流动性不足")

        return reasons

    def _filter_by_trend(
        self,
        row: Dict[str, Any],
        daily_df: pd.DataFrame,
        trend: TrendAnalysisResult,
    ) -> List[str]:
        reasons = []
        change_pct = self._safe_float(row.get("change_pct"))
        if change_pct >= self.max_chasing_change_pct and trend.bias_ma5 >= trend.adaptive_bias_threshold:
            reasons.append("当日涨幅较高且MA5乖离超过纪律线")
        if trend.ma20_breakdown:
            reasons.append("收盘跌破MA20，买入信号失效")
        return reasons

    def _score_candidate(
        self,
        sector: SectorCandidate,
        trend: TrendAnalysisResult,
        average_amount_5d: float,
        is_sector_leader: bool = False,
    ) -> Dict[str, float]:
        buy_point_score = self._buy_point_score(trend)
        liquidity_score = self._liquidity_score(average_amount_5d)
        relative_strength_score = max(0.0, min(10.0, 5.0 + trend.relative_strength_score / 2))
        risk_score = max(0.0, 10.0 - len(trend.risk_factors) * 2.5)
        if trend.ma20_breakdown:
            risk_score = 0.0

        return {
            "sector_heat": round(sector.heat_score, 2),
            "trend": round(trend.signal_score * 0.30, 2),
            "buy_point": round(buy_point_score, 2),
            "liquidity": round(liquidity_score, 2),
            "relative_strength": round(relative_strength_score, 2),
            "sector_leader": 5.0 if is_sector_leader else 0.0,
            "risk": round(risk_score, 2),
        }

    def _is_sector_leader(self, row: Dict[str, Any], sector: SectorCandidate) -> bool:
        leader = str(sector.leading_stock or "").strip()
        if not leader:
            return False
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        return bool((code and code in leader) or (name and name in leader))

    def _buy_point_score(self, trend: TrendAnalysisResult) -> float:
        bias_threshold = trend.adaptive_bias_threshold or StockTrendAnalyzer.BIAS_THRESHOLD
        bias = trend.bias_ma5
        if trend.support_ma5 or trend.support_ma10:
            return 20.0
        if trend.breakout_valid and trend.bias_ma5 < trend.breakout_extension_threshold:
            return 16.0
        if -3 <= bias <= 2:
            return 18.0
        if -5 <= bias < -3:
            return 14.0
        if 2 < bias < bias_threshold:
            return 12.0
        if bias < -5:
            return 6.0
        return 2.0

    def _liquidity_score(self, average_amount_5d: float) -> float:
        if average_amount_5d >= 1_000_000_000:
            return 10.0
        if average_amount_5d >= 500_000_000:
            return 9.0
        if average_amount_5d >= 200_000_000:
            return 8.0
        if average_amount_5d >= self.min_avg_amount:
            return 6.0
        return 0.0

    def _sector_heat_score(self, rank: int, change_pct: float) -> float:
        rank_score = max(0.0, 14.0 - max(rank - 1, 0) * 2.0)
        change_score = max(0.0, min(6.0, change_pct * 1.5))
        return round(min(20.0, rank_score + change_score), 2)

    def _fetch_daily_data(self, code: str) -> pd.DataFrame:
        data = self.daily_fetcher.get_daily_data(code, days=120)
        if isinstance(data, tuple):
            return data[0]
        return data

    def _get_benchmark_history(self) -> Optional[pd.DataFrame]:
        if self._benchmark_loaded:
            return self._benchmark_df
        self._benchmark_loaded = True
        providers = [self.daily_fetcher, self.sector_fetcher]
        seen = set()
        errors = []
        for provider in providers:
            if provider is None or id(provider) in seen or not hasattr(provider, "get_index_daily_data"):
                continue
            seen.add(id(provider))
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            try:
                self._benchmark_df = provider.get_index_daily_data("000300", days=250)
                logger.info(f"[选股] 已获取沪深300基准，来源: {provider_name}")
                return self._benchmark_df
            except Exception as e:
                errors.append(f"{provider_name}: {e}")
        if errors:
            logger.warning(f"[选股] 获取沪深300基准失败，跳过RS大盘基准: {'；'.join(errors)}")
        self._benchmark_df = None
        return self._benchmark_df

    def _get_sector_history(self, sector: SectorCandidate) -> Optional[pd.DataFrame]:
        key = (sector.sector_type, sector.name)
        if key in self._sector_history_cache:
            return self._sector_history_cache[key]
        if not hasattr(self.sector_fetcher, "get_sector_daily_data"):
            self._sector_history_cache[key] = None
            return None
        try:
            self._sector_history_cache[key] = self.sector_fetcher.get_sector_daily_data(
                sector.name,
                sector_type=sector.sector_type,
                days=120,
            )
        except Exception as e:
            logger.warning(f"[选股] 获取板块 {sector.name} 日线失败，跳过行业RS: {e}")
            self._sector_history_cache[key] = None
        return self._sector_history_cache[key]

    def _average_amount_5d(self, df: pd.DataFrame, fallback: float = 0.0) -> float:
        if df is not None and not df.empty and "amount" in df.columns:
            amount = df["amount"].tail(5).mean()
            if pd.notna(amount) and amount > 0:
                return float(amount)
        return fallback

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if pd.isna(value):
                return default
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
                if value in {"", "-", "--"}:
                    return default
            return float(value)
        except Exception:
            return default
