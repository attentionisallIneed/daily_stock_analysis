# -*- coding: utf-8 -*-
"""Structured models for the hot-sector theme radar."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ThemeEvidence:
    id: str
    source: str
    title: str
    summary: str
    published_at: str = ""
    url: str = ""
    related_sectors: List[str] = field(default_factory=list)
    related_stocks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LeaderCandidate:
    code: str
    name: str
    sector_name: str
    leader_reason: str
    composite_score: float
    rs_score: float = 0.0
    breakout_score: float = 0.0
    liquidity_score: float = 0.0
    risk_flags: List[str] = field(default_factory=list)
    theme_name: str = ""
    capital_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ThemeSignal:
    name: str
    related_sectors: List[str]
    heat_score: float
    news_score: float
    capital_score: float
    market_score: float
    persistence_score: float
    catalysts: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    leader_candidates: List[LeaderCandidate] = field(default_factory=list)
    confidence: str = "中"
    unsupported_claims: List[str] = field(default_factory=list)
    capital_observation: str = "资金数据缺失，按中性处理"
    status: str = "待确认"
    status_reason: str = ""
    consecutive_days: int = 1
    downgrade_reasons: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return round(
            float(self.news_score)
            + float(self.capital_score)
            + float(self.market_score)
            + float(self.persistence_score),
            2,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["total_score"] = self.total_score
        return data


@dataclass
class ThemeRadarResult:
    generated_at: str
    market_environment: Dict[str, Any]
    themes: List[ThemeSignal]
    selected_stocks: List[LeaderCandidate]
    filtered_reasons: List[Dict[str, Any]]
    detailed_results: List[Any] = field(default_factory=list)
    evidence: List[ThemeEvidence] = field(default_factory=list)
    report_markdown: str = ""
    history_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "market_environment": self.market_environment,
            "themes": [theme.to_dict() for theme in self.themes],
            "selected_stocks": [stock.to_dict() for stock in self.selected_stocks],
            "filtered_reasons": list(self.filtered_reasons),
            "detailed_results": [self._detail_to_dict(item) for item in self.detailed_results],
            "evidence": [item.to_dict() for item in self.evidence],
            "report_markdown": self.report_markdown,
            "history_path": self.history_path,
        }

    @staticmethod
    def _detail_to_dict(item: Any) -> Any:
        if hasattr(item, "to_dict"):
            return item.to_dict()
        if hasattr(item, "__dict__"):
            return dict(item.__dict__)
        return str(item)
