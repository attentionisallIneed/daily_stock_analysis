# -*- coding: utf-8 -*-
"""Capital-flow evidence normalization for theme radar scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class CapitalFlowEvidence:
    sector_name: str
    source: str
    updated_at: str
    reliability: str
    change_pct: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0
    north_flow: float = 0.0
    main_net_inflow: Optional[float] = None
    etf_net_inflow: Optional[float] = None
    dragon_tiger_net_inflow: Optional[float] = None
    leading_stock: str = ""
    score: float = 12.5
    observation: str = "资金数据缺失，按中性处理"
    missing_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CapitalFlowAdapter:
    """Build comparable capital-flow evidence from available market fields."""

    SOURCE = "akshare_hot_sector_snapshot"
    RELIABILITY = "medium"

    def collect_for_sectors(
        self,
        sectors: Iterable[Dict[str, Any]],
        market_environment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, CapitalFlowEvidence]:
        market_environment = market_environment or {}
        north_flow = self._safe_float(market_environment.get("north_flow"))
        if not north_flow and isinstance(market_environment.get("overview"), dict):
            north_flow = self._safe_float(market_environment["overview"].get("north_flow"))

        flows: Dict[str, CapitalFlowEvidence] = {}
        for raw in sectors or []:
            evidence = self.from_sector_snapshot(raw, north_flow=north_flow)
            if evidence.sector_name:
                flows[evidence.sector_name] = evidence
        return flows

    def from_sector_snapshot(self, raw: Dict[str, Any], north_flow: float = 0.0) -> CapitalFlowEvidence:
        updated_at = str(raw.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        sector_name = str(raw.get("name") or raw.get("sector_name") or "").strip()
        change_pct = self._safe_float(raw.get("change_pct"))
        amount = self._safe_float(raw.get("amount"))
        turnover_rate = self._safe_float(raw.get("turnover_rate"))
        leading_stock = str(raw.get("leading_stock") or "")

        missing = []
        if amount <= 0:
            missing.append("amount")
        if turnover_rate <= 0:
            missing.append("turnover_rate")

        score = 12.5
        if change_pct > 0:
            score += min(6.0, change_pct * 1.2)
        if amount > 0:
            score += 4.0 if amount >= 1_000_000_000 else 2.0
        if turnover_rate > 0:
            score += min(4.0, turnover_rate)
        if north_flow > 0:
            score += 2.0
        elif north_flow < 0:
            score -= 2.0
        score = round(max(0.0, min(25.0, score)), 2)

        if missing:
            observation = "资金数据缺失，按中性处理"
        elif score >= 19:
            observation = "资金强、新闻待确认"
        elif score >= 15:
            observation = "新闻与资金共振"
        else:
            observation = "新闻热、资金弱"

        return CapitalFlowEvidence(
            sector_name=sector_name,
            source=str(raw.get("source") or self.SOURCE),
            updated_at=updated_at,
            reliability=str(raw.get("reliability") or self.RELIABILITY),
            change_pct=change_pct,
            amount=amount,
            turnover_rate=turnover_rate,
            north_flow=north_flow,
            leading_stock=leading_stock,
            score=score,
            observation=observation,
            missing_fields=missing,
        )

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
                if value in {"", "-", "--", "N/A"}:
                    return default
            return float(value)
        except (TypeError, ValueError):
            return default
