# -*- coding: utf-8 -*-
"""Minimal backtesting for theme and leader radar history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_HORIZONS = (1, 3, 5, 10)


@dataclass
class ThemeBacktestSummary:
    theme_count: int
    leader_count: int
    horizons: Sequence[int]
    theme_returns: Dict[str, float] = field(default_factory=dict)
    leader_returns: Dict[str, float] = field(default_factory=dict)
    win_rates: Dict[str, float] = field(default_factory=dict)
    factor_effectiveness: Dict[str, float] = field(default_factory=dict)
    return_source_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme_count": self.theme_count,
            "leader_count": self.leader_count,
            "horizons": list(self.horizons),
            "theme_returns": self.theme_returns,
            "leader_returns": self.leader_returns,
            "win_rates": self.win_rates,
            "factor_effectiveness": self.factor_effectiveness,
            "return_source_counts": self.return_source_counts,
        }


@dataclass
class ThemeBacktestResult:
    summary: ThemeBacktestSummary
    rows: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary.to_dict(), "rows": self.rows}


class ThemeBacktester:
    """Evaluate saved radar themes and leaders with simple forward returns."""

    def __init__(
        self,
        sector_fetcher: Any = None,
        daily_fetcher: Any = None,
        horizons: Sequence[int] = DEFAULT_HORIZONS,
    ) -> None:
        if daily_fetcher is None and horizons == DEFAULT_HORIZONS and self._looks_like_horizons(sector_fetcher):
            horizons = sector_fetcher
            sector_fetcher = None
        self.sector_fetcher = sector_fetcher
        self.daily_fetcher = daily_fetcher
        self.horizons = tuple(horizons)

    def run_backtest(self, records: str | Path | Iterable[Dict[str, Any]]) -> ThemeBacktestResult:
        loaded = self._load_records(records)
        rows: List[Dict[str, Any]] = []
        leader_count = 0

        for record in loaded:
            generated_at = record.get("generated_at", "")
            for theme in record.get("themes", []):
                if not isinstance(theme, dict):
                    continue
                theme_returns = self._extract_horizon_returns(theme, "sector_forward_returns")
                return_source = "history_fields" if theme_returns else "missing"
                if not theme_returns:
                    theme_returns = self._supplement_theme_returns(theme, generated_at)
                    if theme_returns:
                        return_source = "market_supplement"

                row = {
                    "generated_at": generated_at,
                    "theme": theme.get("name", ""),
                    "heat_score": float(theme.get("heat_score") or theme.get("total_score") or 0),
                    "news_score": float(theme.get("news_score") or 0),
                    "capital_score": float(theme.get("capital_score") or 0),
                    "market_score": float(theme.get("market_score") or 0),
                    "persistence_score": float(theme.get("persistence_score") or 0),
                    "confidence": theme.get("confidence", ""),
                    "theme_forward_returns": theme_returns,
                    "return_source": return_source,
                    "leader_forward_returns": [],
                    "leader_return_sources": [],
                }
                for leader in theme.get("leader_candidates") or []:
                    if isinstance(leader, dict):
                        leader_count += 1
                        leader_returns = self._extract_horizon_returns(leader, "leader_forward_returns")
                        leader_source = "history_fields" if leader_returns else "missing"
                        if not leader_returns:
                            leader_returns = self._supplement_leader_returns(leader, generated_at)
                            if leader_returns:
                                leader_source = "market_supplement"
                        row["leader_forward_returns"].append(leader_returns)
                        row["leader_return_sources"].append(leader_source)
                rows.append(row)

        summary = self._build_summary(rows, leader_count)
        return ThemeBacktestResult(summary=summary, rows=rows)

    def format_report(self, result: ThemeBacktestResult) -> str:
        summary = result.summary
        lines = [
            "# 热点主题雷达最小回测报告",
            "",
            f"- 主题样本数：{summary.theme_count}",
            f"- 龙头样本数：{summary.leader_count}",
            f"- 收益来源：{self._format_source_counts(summary.return_source_counts)}",
            "",
            "## 主题收益",
            "",
            "| 周期 | 平均收益 | 胜率 |",
            "| --- | ---: | ---: |",
        ]
        for horizon in summary.horizons:
            key = f"{horizon}d"
            lines.append(
                f"| {key} | {summary.theme_returns.get(key, 0.0):+.2f}% | {summary.win_rates.get(key, 0.0):.1f}% |"
            )
        lines.extend(["", "## 因子有效性", ""])
        for name, value in summary.factor_effectiveness.items():
            lines.append(f"- {name}: {value:+.2f}")
        return "\n".join(lines)

    def _build_summary(self, rows: List[Dict[str, Any]], leader_count: int) -> ThemeBacktestSummary:
        theme_returns: Dict[str, float] = {}
        leader_returns: Dict[str, float] = {}
        win_rates: Dict[str, float] = {}

        for horizon in self.horizons:
            key = f"{horizon}d"
            theme_values = [
                row["theme_forward_returns"][key]
                for row in rows
                if key in row["theme_forward_returns"]
            ]
            leader_values = [
                leader[key]
                for row in rows
                for leader in row["leader_forward_returns"]
                if key in leader
            ]
            theme_returns[key] = round(mean(theme_values), 2) if theme_values else 0.0
            leader_returns[key] = round(mean(leader_values), 2) if leader_values else 0.0
            win_rates[key] = round(sum(1 for value in theme_values if value > 0) / len(theme_values) * 100, 2) if theme_values else 0.0

        factor_effectiveness = self._factor_effectiveness(rows)
        source_counts: Dict[str, int] = {}
        for row in rows:
            source = str(row.get("return_source") or "missing")
            source_counts[source] = source_counts.get(source, 0) + 1
        return ThemeBacktestSummary(
            theme_count=len(rows),
            leader_count=leader_count,
            horizons=self.horizons,
            theme_returns=theme_returns,
            leader_returns=leader_returns,
            win_rates=win_rates,
            factor_effectiveness=factor_effectiveness,
            return_source_counts=source_counts,
        )

    def _factor_effectiveness(self, rows: List[Dict[str, Any]]) -> Dict[str, float]:
        target_key = f"{self.horizons[0]}d"
        target = [row["theme_forward_returns"].get(target_key, 0.0) for row in rows]
        factors = {}
        for field_name in ("news_score", "capital_score", "market_score", "persistence_score", "heat_score"):
            values = [float(row.get(field_name) or 0) for row in rows]
            factors[field_name] = self._simple_slope(values, target)
        return factors

    def _load_records(self, records: str | Path | Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if isinstance(records, (str, Path)):
            path = Path(records)
            if path.is_dir():
                return [
                    json.loads(item.read_text(encoding="utf-8"))
                    for item in sorted(path.glob("theme_radar_*.json"))
                ]
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return payload if isinstance(payload, list) else [payload]
            return []
        return list(records)

    def _extract_horizon_returns(self, item: Dict[str, Any], field_name: str) -> Dict[str, float]:
        raw = item.get(field_name) or item.get("forward_returns") or {}
        result: Dict[str, float] = {}
        for horizon in self.horizons:
            key = f"{horizon}d"
            value = raw.get(key, raw.get(str(horizon)))
            if value is not None:
                result[key] = float(value)
        return result

    def _supplement_theme_returns(self, theme: Dict[str, Any], generated_at: str) -> Dict[str, float]:
        if not self.sector_fetcher:
            return {}
        sector_names = [str(item) for item in theme.get("related_sectors") or [] if str(item)]
        if not sector_names:
            return {}
        data = self._call_fetcher(
            self.sector_fetcher,
            ("get_sector_daily_data", "get_daily_data"),
            sector_names[0],
        )
        return self._calculate_forward_returns(data, generated_at)

    def _supplement_leader_returns(self, leader: Dict[str, Any], generated_at: str) -> Dict[str, float]:
        if not self.daily_fetcher:
            return {}
        code = str(leader.get("code") or leader.get("stock_code") or "")
        if not code:
            return {}
        data = self._call_fetcher(
            self.daily_fetcher,
            ("get_daily_data", "get_stock_daily_data"),
            code,
        )
        return self._calculate_forward_returns(data, generated_at)

    def _call_fetcher(self, fetcher: Any, method_names: Sequence[str], key: str) -> Any:
        for method_name in method_names:
            method = getattr(fetcher, method_name, None)
            if not method:
                continue
            try:
                return method(key, days=max(self.horizons) + 30)
            except TypeError:
                try:
                    return method(key)
                except Exception:
                    return None
            except Exception:
                return None
        return None

    def _calculate_forward_returns(self, data: Any, generated_at: str) -> Dict[str, float]:
        rows = self._normalize_price_rows(data)
        if not rows:
            return {}
        generated_date = self._parse_date(generated_at)
        base_index = self._find_base_index(rows, generated_date)
        if base_index is None:
            return {}
        base_close = rows[base_index]["close"]
        if base_close <= 0:
            return {}
        returns: Dict[str, float] = {}
        for horizon in self.horizons:
            target_index = base_index + horizon
            if target_index < len(rows):
                target_close = rows[target_index]["close"]
                returns[f"{horizon}d"] = round((target_close / base_close - 1.0) * 100.0, 2)
        return returns

    def _normalize_price_rows(self, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, tuple):
            data = data[0] if data else None
        if data is None:
            return []
        if hasattr(data, "empty") and getattr(data, "empty"):
            return []
        if hasattr(data, "to_dict"):
            records = data.to_dict("records")
        elif isinstance(data, dict):
            records = data.get("data") or data.get("records") or []
        else:
            records = list(data or [])

        rows: List[Dict[str, Any]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            close = self._first_present_float(item, ("close", "收盘", "收盘价", "Close"))
            row_date = self._parse_date(
                item.get("date")
                or item.get("trade_date")
                or item.get("datetime")
                or item.get("日期")
            )
            if close is not None:
                rows.append({"date": row_date, "close": close})
        rows.sort(key=lambda item: item["date"] or date.min)
        return rows

    @staticmethod
    def _find_base_index(rows: Sequence[Dict[str, Any]], generated_date: Optional[date]) -> Optional[int]:
        if not rows:
            return None
        if generated_date is None:
            return 0
        dated_indexes = [(idx, row["date"]) for idx, row in enumerate(rows) if row.get("date") is not None]
        if not dated_indexes:
            return 0
        for idx, row_date in dated_indexes:
            if row_date >= generated_date:
                return idx
        return None

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = text[:10] if "-" in text else text[:8]
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _first_present_float(item: Dict[str, Any], keys: Sequence[str]) -> Optional[float]:
        for key in keys:
            if key not in item:
                continue
            try:
                value = item[key]
                if isinstance(value, str):
                    value = value.replace(",", "").strip()
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _format_source_counts(source_counts: Dict[str, int]) -> str:
        labels = {
            "history_fields": "历史字段读取",
            "market_supplement": "真实行情补算",
            "missing": "样本行情不足",
        }
        if not source_counts:
            return "样本行情不足"
        return " / ".join(f"{labels.get(key, key)} {value}" for key, value in source_counts.items())

    @staticmethod
    def _looks_like_horizons(value: Any) -> bool:
        return isinstance(value, (list, tuple)) and all(isinstance(item, int) for item in value)

    @staticmethod
    def _simple_slope(values: Sequence[float], target: Sequence[float]) -> float:
        if len(values) < 2 or len(values) != len(target):
            return 0.0
        avg_x = mean(values)
        avg_y = mean(target)
        denominator = sum((x - avg_x) ** 2 for x in values)
        if denominator == 0:
            return 0.0
        numerator = sum((x - avg_x) * (y - avg_y) for x, y in zip(values, target))
        return round(numerator / denominator, 4)
