# -*- coding: utf-8 -*-
"""Minimal backtesting for theme and leader radar history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme_count": self.theme_count,
            "leader_count": self.leader_count,
            "horizons": list(self.horizons),
            "theme_returns": self.theme_returns,
            "leader_returns": self.leader_returns,
            "win_rates": self.win_rates,
            "factor_effectiveness": self.factor_effectiveness,
        }


@dataclass
class ThemeBacktestResult:
    summary: ThemeBacktestSummary
    rows: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary.to_dict(), "rows": self.rows}


class ThemeBacktester:
    """Evaluate saved radar themes and leaders with simple forward returns."""

    def __init__(self, horizons: Sequence[int] = DEFAULT_HORIZONS) -> None:
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
                row = {
                    "generated_at": generated_at,
                    "theme": theme.get("name", ""),
                    "heat_score": float(theme.get("heat_score") or theme.get("total_score") or 0),
                    "news_score": float(theme.get("news_score") or 0),
                    "capital_score": float(theme.get("capital_score") or 0),
                    "market_score": float(theme.get("market_score") or 0),
                    "persistence_score": float(theme.get("persistence_score") or 0),
                    "confidence": theme.get("confidence", ""),
                    "theme_forward_returns": self._extract_horizon_returns(theme, "sector_forward_returns"),
                    "leader_forward_returns": [],
                }
                for leader in theme.get("leader_candidates") or []:
                    if isinstance(leader, dict):
                        leader_count += 1
                        row["leader_forward_returns"].append(
                            self._extract_horizon_returns(leader, "leader_forward_returns")
                        )
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
        return ThemeBacktestSummary(
            theme_count=len(rows),
            leader_count=leader_count,
            horizons=self.horizons,
            theme_returns=theme_returns,
            leader_returns=leader_returns,
            win_rates=win_rates,
            factor_effectiveness=factor_effectiveness,
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
