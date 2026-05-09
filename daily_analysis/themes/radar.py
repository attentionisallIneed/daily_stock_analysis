# -*- coding: utf-8 -*-
"""Hot-sector LLM radar orchestration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from daily_analysis.analysis.capital_flow import CapitalFlowAdapter, CapitalFlowEvidence
from daily_analysis.prompts.theme_discovery import build_theme_discovery_prompt, parse_theme_discovery_response
from daily_analysis.analysis.stock_screener import ScreeningResult, StockScreener
from daily_analysis.themes.models import LeaderCandidate, ThemeEvidence, ThemeRadarResult, ThemeSignal
from daily_analysis.themes.tracker import ThemeTracker

logger = logging.getLogger(__name__)


CONFIDENCE_ORDER = {"低": 0, "中": 1, "高": 2}


class ThemeRadar:
    """Coordinate market context, evidence, theme discovery, leaders, and history."""

    def __init__(
        self,
        market_analyzer: Any = None,
        search_service: Any = None,
        sector_fetcher: Any = None,
        daily_fetcher: Any = None,
        trend_analyzer: Any = None,
        analyzer: Any = None,
        llm_analyzer: Any = None,
        detail_analyzer: Optional[Callable[[str], Any]] = None,
        screener: Any = None,
        capital_flow: Optional[CapitalFlowAdapter] = None,
        tracker: Optional[ThemeTracker] = None,
    ) -> None:
        if llm_analyzer is None and analyzer is not None:
            llm_analyzer = analyzer
        self.market_analyzer = market_analyzer
        self.search_service = search_service
        self.sector_fetcher = sector_fetcher
        self.daily_fetcher = daily_fetcher
        self.trend_analyzer = trend_analyzer
        self.llm_analyzer = llm_analyzer
        self.detail_analyzer = detail_analyzer
        self.screener = screener
        self.capital_flow = capital_flow or CapitalFlowAdapter()
        self.tracker = tracker or ThemeTracker()

    def run(
        self,
        theme_count: int = 5,
        leader_top_n: int = 3,
        lookback_days: int = 7,
        include_detail_analysis: bool = True,
        include_concepts: bool = True,
        save_history: bool = True,
    ) -> ThemeRadarResult:
        market_environment = self._get_market_environment()
        sectors = self._get_hot_sectors(theme_count, include_concepts)
        evidence = self._collect_evidence(sectors, lookback_days)
        capital_map = self.capital_flow.collect_for_sectors(sectors, market_environment)
        data_quality = self._build_data_quality(sectors, capital_map, evidence)
        market_environment["data_quality"] = data_quality
        theme_dicts = self._discover_theme_dicts(evidence, sectors, market_environment, theme_count)
        themes = self._build_theme_signals(theme_dicts, sectors, evidence, capital_map, data_quality)

        if sectors:
            screening_result = self._screen_hot_sectors(theme_count, leader_top_n, include_concepts)
        else:
            screening_result = ScreeningResult(
                filtered=[
                    {
                        "code": "-",
                        "name": "候选龙头",
                        "reasons": ["未生成候选龙头，因为缺少板块成分股/行情验证"],
                    }
                ]
            )
        leaders = self._build_leader_candidates(screening_result, themes, leader_top_n)
        self._attach_leaders(themes, leaders)

        detailed_results = []
        if include_detail_analysis:
            detailed_results = self._run_detail_analysis(leaders[:leader_top_n])

        self.tracker.update_theme_statuses(themes)
        result = ThemeRadarResult(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market_environment=market_environment,
            themes=themes[: max(1, theme_count)],
            selected_stocks=leaders[: max(1, leader_top_n)],
            filtered_reasons=list(getattr(screening_result, "filtered", []) or []),
            detailed_results=detailed_results,
            evidence=evidence,
        )
        result.report_markdown = self.format_report(result)
        if save_history:
            result.history_path = self.tracker.save_history(result)
        return result

    def format_report(self, result: ThemeRadarResult) -> str:
        """Render a Markdown radar report."""
        env = result.market_environment or {}
        lines = [
            "# 热点板块 LLM 雷达日报",
            "",
            f"> 生成时间：{result.generated_at}",
            "> 用途：投资研究与复盘辅助，不构成投资建议。",
            "",
            "## 1. 市场环境",
            "",
            f"- 市场状态：{env.get('market_status', '未知')}",
            f"- 市场评分：{env.get('market_score', 'N/A')}",
            f"- 北向资金：{env.get('north_flow', env.get('overview', {}).get('north_flow', 'N/A'))}",
            f"- 板块热度：{env.get('sector_heat_summary', '无')}",
        ]
        data_quality = env.get("data_quality") or {}
        lines.append(f"- 数据质量：{self._format_data_quality(data_quality)}")
        if data_quality.get("downgrade_note"):
            lines.append(f"- 降级说明：{data_quality['downgrade_note']}")
        lines.extend(
            [
                "",
                "## 2. 今日热点主题 Top 3-5",
                "",
                "| 排名 | 主题 | 置信度 | 热度分 | 新闻验证 | 资金验证 | 关联板块 | 状态 |",
                "| --- | --- | --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for index, theme in enumerate(result.themes, start=1):
            lines.append(
                f"| {index} | {theme.name} | {theme.confidence} | {theme.total_score:.1f} | "
                f"{theme.news_score:.1f} | {theme.capital_observation} | "
                f"{', '.join(theme.related_sectors) or '待确认'} | {theme.status} |"
            )

        lines.extend(["", "## 3. 主题详情", ""])
        for theme in result.themes:
            lines.extend(
                [
                    f"### {theme.name}",
                    f"- 核心催化：{'；'.join(theme.catalysts) or '待确认'}",
                    f"- 证据链：{', '.join(theme.evidence_ids) or '无'}",
                    f"- 资金/行情验证：{theme.capital_observation}",
                    f"- 关联板块：{', '.join(theme.related_sectors) or '待确认'}",
                    f"- 状态：{theme.status}（{theme.status_reason or '暂无历史'}）",
                    f"- 风险点：{'；'.join(theme.risks + theme.downgrade_reasons) or '无'}",
                    "",
                ]
            )
            if theme.leader_candidates:
                lines.append("| 代码 | 名称 | 板块 | 综合分 | 龙头理由 | 风险 |")
                lines.append("| --- | --- | --- | ---: | --- | --- |")
                for leader in theme.leader_candidates:
                    lines.append(
                        f"| {leader.code} | {leader.name} | {leader.sector_name} | "
                        f"{leader.composite_score:.1f} | {leader.leader_reason} | "
                        f"{'；'.join(leader.risk_flags) or '-'} |"
                    )
                lines.append("")

        lines.extend(
            [
                "## 4. 候选龙头排序",
                "",
                "| 排名 | 代码 | 名称 | 主题 | 板块 | 综合分 | RS | 突破 | 流动性 | 风险 |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for index, leader in enumerate(result.selected_stocks, start=1):
            lines.append(
                f"| {index} | {leader.code} | {leader.name} | {leader.theme_name or '-'} | "
                f"{leader.sector_name} | {leader.composite_score:.1f} | {leader.rs_score:.1f} | "
                f"{leader.breakout_score:.1f} | {leader.liquidity_score:.1f} | "
                f"{'；'.join(leader.risk_flags) or '-'} |"
            )
        if not result.selected_stocks:
            lines.append("未生成候选龙头，因为缺少板块成分股或行情验证。")

        if result.detailed_results:
            lines.extend(["", "## 5. Top 个股精细报告摘要", ""])
            for detail in result.detailed_results:
                code = getattr(detail, "code", "")
                name = getattr(detail, "name", code)
                summary = getattr(detail, "analysis_summary", "") or str(detail)
                lines.extend([f"### {name}({code})", summary[:500], ""])

        if result.filtered_reasons:
            lines.extend(["", "## 6. 过滤与降权原因", ""])
            for item in result.filtered_reasons[:20]:
                lines.append(
                    f"- {item.get('code', '-')}/{item.get('name', '-')}: "
                    f"{'；'.join(item.get('reasons') or []) or '未说明'}"
                )
        return "\n".join(lines)

    def analyze_stock(self, code: str) -> Any:
        """Reuse StockAnalysisPipeline.analyze_stock or a compatible detail callable."""
        if self.detail_analyzer:
            return self.detail_analyzer(code)
        return None

    def _build_data_quality(
        self,
        sectors: Sequence[Dict[str, Any]],
        capital_map: Dict[str, CapitalFlowEvidence],
        evidence: Sequence[ThemeEvidence],
    ) -> Dict[str, Any]:
        sector_available = bool(sectors)
        capital_available = any(self._has_capital_validation(item) for item in (capital_map or {}).values())
        news_available = bool(evidence)
        notes = []
        downgrade_note = ""
        if not sector_available:
            notes.append("板块行情缺失")
            downgrade_note = "板块行情获取失败，本报告仅作为新闻主题观察"
        if sector_available and not capital_available:
            notes.append("资金数据缺失")
            downgrade_note = "资金数据缺失，主题按中性偏保守处理"
        if not news_available:
            notes.append("新闻证据缺失")
        return {
            "sector_data_available": sector_available,
            "capital_data_available": capital_available,
            "news_data_available": news_available,
            "notes": notes,
            "downgrade_note": downgrade_note,
        }

    @staticmethod
    def _format_data_quality(data_quality: Dict[str, Any]) -> str:
        if not data_quality:
            return "未记录"
        parts = []
        parts.append("板块行情可用" if data_quality.get("sector_data_available") else "板块行情缺失")
        parts.append("资金数据可用" if data_quality.get("capital_data_available") else "资金数据缺失")
        parts.append("新闻证据可用" if data_quality.get("news_data_available") else "新闻证据缺失")
        return " / ".join(parts)

    def _get_market_environment(self) -> Dict[str, Any]:
        if not self.market_analyzer:
            return {
                "market_score": 50,
                "market_status": "震荡",
                "risk_level": "中",
                "sector_heat_summary": "市场环境数据缺失，按中性处理",
            }
        try:
            overview = self.market_analyzer.get_market_overview()
            if hasattr(overview, "to_dict"):
                overview_dict = overview.to_dict()
            elif isinstance(overview, dict):
                overview_dict = overview
            else:
                overview_dict = {}
            if hasattr(self.market_analyzer, "evaluate_market_environment"):
                env = self.market_analyzer.evaluate_market_environment(overview)
            else:
                from daily_analysis.analysis.market_analyzer import evaluate_market_environment

                env = evaluate_market_environment(overview)
            env["overview"] = overview_dict
            if "north_flow" not in env:
                env["north_flow"] = overview_dict.get("north_flow", 0.0)
            return env
        except Exception as exc:
            logger.warning("theme radar market environment fallback: %s", exc)
            return {
                "market_score": 50,
                "market_status": "震荡",
                "risk_level": "中",
                "sector_heat_summary": "市场环境数据获取失败，按中性处理",
            }

    def _get_hot_sectors(self, theme_count: int, include_concepts: bool) -> List[Dict[str, Any]]:
        if not self.sector_fetcher or not hasattr(self.sector_fetcher, "get_hot_sectors"):
            return []
        try:
            return list(
                self.sector_fetcher.get_hot_sectors(
                    sector_count=max(theme_count, 1),
                    include_concepts=include_concepts,
                )
                or []
            )
        except Exception as exc:
            logger.warning("theme radar hot sector fallback: %s", exc)
            return []

    def _collect_evidence(self, sectors: Sequence[Dict[str, Any]], lookback_days: int) -> List[ThemeEvidence]:
        evidence: List[ThemeEvidence] = []
        for index, sector in enumerate(sectors, start=1):
            name = str(sector.get("name") or "")
            evidence.append(
                ThemeEvidence(
                    id=f"sector_{index:03d}",
                    source="sector_rank",
                    title=f"{name} 板块异动",
                    summary=(
                        f"涨跌幅 {sector.get('change_pct', 0)}%，成交额 {self._format_amount(sector.get('amount'))}，"
                        f"领涨股 {sector.get('leading_stock', '') or '未提供'}"
                    ),
                    related_sectors=[name] if name else [],
                    related_stocks=[str(sector.get("leading_stock") or "")] if sector.get("leading_stock") else [],
                )
            )

        if self.search_service and getattr(self.search_service, "is_available", False):
            try:
                query = f"A股热点板块 近{lookback_days}日 政策 产业 资金"
                if hasattr(self.search_service, "search_market_news"):
                    response = self.search_service.search_market_news(query, max_results=5)
                else:
                    response = self.search_service.search_stock_news("market", query, max_results=5)
                for item in getattr(response, "results", []) or []:
                    idx = len([e for e in evidence if e.id.startswith("news_")]) + 1
                    evidence.append(
                        ThemeEvidence(
                            id=f"news_{idx:03d}",
                            source=getattr(item, "source", "search"),
                            title=getattr(item, "title", ""),
                            summary=getattr(item, "snippet", ""),
                            published_at=getattr(item, "published_date", "") or "",
                            url=getattr(item, "url", ""),
                        )
                    )
            except Exception as exc:
                logger.warning("theme radar news search skipped: %s", exc)
        return evidence

    def _discover_theme_dicts(
        self,
        evidence: Sequence[ThemeEvidence],
        sectors: Sequence[Dict[str, Any]],
        market_environment: Dict[str, Any],
        theme_count: int,
    ) -> List[Dict[str, Any]]:
        valid_ids = [item.id for item in evidence]
        sector_names = [str(item.get("name") or "") for item in sectors if item.get("name")]
        prompt = build_theme_discovery_prompt(
            [item.to_dict() for item in evidence],
            sectors,
            market_environment,
            theme_count=theme_count,
        )
        response_text = ""
        if self.llm_analyzer and getattr(self.llm_analyzer, "is_available", lambda: False)():
            try:
                if hasattr(self.llm_analyzer, "generate_theme_json"):
                    response_text = self.llm_analyzer.generate_theme_json(prompt)
                elif hasattr(self.llm_analyzer, "_call_api_with_retry"):
                    response_text = self.llm_analyzer._call_api_with_retry(
                        prompt,
                        {"temperature": 0.2, "max_output_tokens": 2048},
                    )
            except Exception as exc:
                logger.warning("theme discovery LLM fallback: %s", exc)
        if response_text:
            try:
                parsed = parse_theme_discovery_response(response_text, valid_ids, sector_names)
                if parsed:
                    return parsed[:theme_count]
            except Exception as exc:
                logger.warning("theme discovery JSON parse fallback: %s", exc)
        return self._fallback_theme_dicts(sectors, evidence, theme_count)

    def _fallback_theme_dicts(
        self,
        sectors: Sequence[Dict[str, Any]],
        evidence: Sequence[ThemeEvidence],
        theme_count: int,
    ) -> List[Dict[str, Any]]:
        themes = []
        evidence_by_sector = {sector: item.id for item in evidence for sector in item.related_sectors}
        for sector in sectors[: max(1, theme_count)]:
            name = str(sector.get("name") or "")
            if not name:
                continue
            themes.append(
                {
                    "name": f"{name} 资金驱动主题",
                    "confidence": "中",
                    "heat_score": 0,
                    "news_score": 8,
                    "capital_score": 0,
                    "market_score": 0,
                    "persistence_score": 0,
                    "related_sectors": [name],
                    "catalysts": [f"{name} 位于热门板块前列"],
                    "risks": ["缺少独立新闻证据，催化待确认"],
                    "evidence_ids": [evidence_by_sector.get(name, "sector_001")],
                    "unsupported_claims": [],
                }
            )
        return themes

    def _build_theme_signals(
        self,
        theme_dicts: Sequence[Dict[str, Any]],
        sectors: Sequence[Dict[str, Any]],
        evidence: Sequence[ThemeEvidence],
        capital_map: Dict[str, CapitalFlowEvidence],
        data_quality: Optional[Dict[str, Any]] = None,
    ) -> List[ThemeSignal]:
        known_sectors = {str(item.get("name") or ""): item for item in sectors}
        valid_evidence = {item.id for item in evidence}
        data_quality = data_quality or self._build_data_quality(sectors, capital_map, evidence)
        sectors_available = bool(data_quality.get("sector_data_available"))
        themes: List[ThemeSignal] = []
        for raw in theme_dicts:
            requested_source = raw.get("requested_sectors", raw.get("related_sectors", []))
            requested_sectors = [str(item) for item in requested_source if str(item)]
            related_sectors = [item for item in requested_sectors if item in known_sectors]
            risks = list(raw.get("risks") or [])
            downgrade_reasons: List[str] = []
            evidence_ids = [item for item in raw.get("evidence_ids", []) if item in valid_evidence]
            if not evidence_ids:
                continue

            capital_score = 12.5
            capital_observation = "资金数据缺失，按中性处理"
            flows: List[CapitalFlowEvidence] = []
            theme_capital_available = False
            if related_sectors:
                flows = [capital_map[item] for item in related_sectors if item in capital_map]
                theme_capital_available = any(self._has_capital_validation(flow) for flow in flows)
                if flows:
                    capital_score = round(sum(flow.score for flow in flows) / len(flows), 2)
                    observations = [flow.observation for flow in flows]
                    if any(item == "新闻与资金共振" for item in observations):
                        capital_observation = "新闻与资金共振"
                    elif any(item.startswith("资金强") for item in observations):
                        capital_observation = "资金强、新闻弱"
                    elif any(item.startswith("新闻热") for item in observations):
                        capital_observation = "新闻热、资金弱"
                    else:
                        capital_observation = observations[0]

            news_score = self._score_news(raw, evidence_ids)
            market_score = self._score_market(related_sectors, known_sectors)
            persistence_score = self._safe_float(raw.get("persistence_score"), 6.0)
            confidence = str(raw.get("confidence") or "中")
            status = "待确认" if not related_sectors else "新发酵"
            heat_cap = 100.0

            if not sectors_available:
                confidence = self._cap_confidence(confidence, "中")
                status = "待确认"
                capital_score = 0.0
                market_score = 0.0
                heat_cap = 59.0
                capital_observation = "板块行情/资金数据缺失，本报告仅作为新闻主题观察"
                self._append_unique(risks, "板块行情获取失败，本报告仅作为新闻主题观察")
                self._append_unique(downgrade_reasons, "缺少可验证板块行情与资金验证")
            elif requested_sectors and not related_sectors:
                confidence = self._cap_confidence(confidence, "中")
                status = "待确认"
                capital_score = min(capital_score, 6.0)
                market_score = min(market_score, 6.0)
                heat_cap = 64.0
                self._append_unique(risks, "主题与现有板块映射待确认")
                self._append_unique(downgrade_reasons, "缺少可验证板块映射")
            elif not requested_sectors:
                confidence = self._cap_confidence(confidence, "中")
                status = "待确认"
                capital_score = min(capital_score, 6.0)
                market_score = min(market_score, 6.0)
                heat_cap = 59.0
                self._append_unique(risks, "LLM 未提供可验证关联板块")
                self._append_unique(downgrade_reasons, "缺少可验证关联板块")

            if sectors_available and not theme_capital_available:
                confidence = self._cap_confidence(confidence, "中")
                capital_score = min(capital_score, 8.0)
                if capital_observation == "资金数据缺失，按中性处理":
                    capital_observation = "资金数据缺失，按中性偏保守处理"
                self._append_unique(downgrade_reasons, "资金验证缺失")

            heat_score = self._clamp_score(
                news_score + capital_score + market_score + persistence_score,
                upper=heat_cap,
            )

            themes.append(
                ThemeSignal(
                    name=str(raw.get("name") or "未命名主题"),
                    related_sectors=related_sectors,
                    heat_score=round(heat_score, 2),
                    news_score=news_score,
                    capital_score=capital_score,
                    market_score=market_score,
                    persistence_score=persistence_score,
                    catalysts=list(raw.get("catalysts") or []),
                    risks=risks,
                    evidence_ids=evidence_ids,
                    confidence=confidence,
                    unsupported_claims=list(raw.get("unsupported_claims") or []),
                    capital_observation=capital_observation,
                    status=status,
                    downgrade_reasons=downgrade_reasons,
                )
            )
        themes.sort(key=lambda item: item.total_score, reverse=True)
        return themes

    def _screen_hot_sectors(self, theme_count: int, leader_top_n: int, include_concepts: bool) -> ScreeningResult:
        if self.screener is not None:
            screener = self.screener
        else:
            screener = StockScreener(
                daily_fetcher=self.daily_fetcher,
                sector_fetcher=self.sector_fetcher,
                trend_analyzer=self.trend_analyzer,
            )
        try:
            return screener.screen_hot_sectors(
                sector_count=max(1, theme_count),
                top_n=max(1, leader_top_n),
                include_concepts=include_concepts,
                prefer_leading_stocks=True,
            )
        except TypeError:
            return screener.screen_hot_sectors(sector_count=max(1, theme_count), top_n=max(1, leader_top_n))
        except Exception as exc:
            logger.warning("theme radar screen_hot_sectors fallback: %s", exc)
            return ScreeningResult()

    def _build_leader_candidates(
        self,
        screening_result: ScreeningResult,
        themes: Sequence[ThemeSignal],
        leader_top_n: int,
    ) -> List[LeaderCandidate]:
        leaders: List[LeaderCandidate] = []
        for candidate in list(getattr(screening_result, "selected", []) or [])[: max(1, leader_top_n * 3)]:
            trend = getattr(candidate, "trend_result", None)
            sector_name = str(getattr(candidate, "sector_name", ""))
            theme_name = self._find_theme_for_sector(themes, sector_name)
            score_breakdown = getattr(candidate, "score_breakdown", {}) or {}
            leaders.append(
                LeaderCandidate(
                    code=str(getattr(candidate, "code", "")),
                    name=str(getattr(candidate, "name", "")),
                    sector_name=sector_name,
                    leader_reason=self._leader_reason(candidate, trend),
                    composite_score=float(getattr(candidate, "composite_score", 0.0)),
                    rs_score=float(getattr(trend, "relative_strength_score", 0.0) or 0.0),
                    breakout_score=float(getattr(trend, "breakout_score", 0.0) or 0.0),
                    liquidity_score=float(score_breakdown.get("liquidity", 0.0) or 0.0),
                    risk_flags=list(getattr(candidate, "risk_flags", []) or []),
                    theme_name=theme_name,
                )
            )
        leaders.sort(key=lambda item: item.composite_score, reverse=True)
        return leaders

    def _attach_leaders(self, themes: Sequence[ThemeSignal], leaders: Sequence[LeaderCandidate]) -> None:
        for theme in themes:
            if not theme.related_sectors:
                theme.leader_candidates = []
                continue
            matched = [leader for leader in leaders if leader.sector_name in theme.related_sectors]
            theme.leader_candidates = matched[:3]

    def _run_detail_analysis(self, leaders: Sequence[LeaderCandidate]) -> List[Any]:
        details = []
        seen = set()
        for leader in leaders:
            if not leader.code or leader.code in seen:
                continue
            seen.add(leader.code)
            detail = self.analyze_stock(leader.code)
            if detail:
                details.append(detail)
        return details

    def _find_theme_for_sector(self, themes: Sequence[ThemeSignal], sector_name: str) -> str:
        for theme in themes:
            if sector_name in theme.related_sectors:
                return theme.name
        return themes[0].name if themes else ""

    def _leader_reason(self, candidate: Any, trend: Any) -> str:
        parts = []
        if getattr(candidate, "is_sector_leader", False):
            parts.append("板块接口领涨股")
        if trend is not None:
            if getattr(trend, "stock_vs_sector", 0):
                parts.append(f"相对板块 {getattr(trend, 'stock_vs_sector'):+.2f}pct")
            if getattr(trend, "breakout_valid", False):
                parts.append("规则层确认突破")
        return "；".join(parts) or "规则层综合评分靠前"

    def _score_news(self, raw: Dict[str, Any], evidence_ids: Sequence[str]) -> float:
        supplied = self._safe_float(raw.get("news_score"))
        if supplied:
            return max(0.0, min(25.0, supplied))
        return round(min(25.0, 8.0 + len(evidence_ids) * 4.0 + len(raw.get("catalysts") or []) * 2.0), 2)

    def _score_market(self, related_sectors: Sequence[str], sectors: Dict[str, Dict[str, Any]]) -> float:
        if not related_sectors:
            return 6.0
        scores = []
        for sector_name in related_sectors:
            sector = sectors.get(sector_name) or {}
            rank = self._safe_float(sector.get("rank"), 5.0)
            change_pct = self._safe_float(sector.get("change_pct"))
            scores.append(max(4.0, min(20.0, 14.0 - max(rank - 1, 0) * 1.5 + max(0.0, change_pct))))
        return round(sum(scores) / len(scores), 2)

    @staticmethod
    def _cap_confidence(value: str, ceiling: str) -> str:
        value = str(value or "中")
        ceiling = str(ceiling or "中")
        if CONFIDENCE_ORDER.get(value, 1) > CONFIDENCE_ORDER.get(ceiling, 1):
            return ceiling
        return value

    @staticmethod
    def _clamp_score(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
        return round(max(lower, min(upper, float(value or 0.0))), 2)

    @staticmethod
    def _append_unique(items: List[str], value: str) -> None:
        if value and value not in items:
            items.append(value)

    @staticmethod
    def _has_capital_validation(flow: CapitalFlowEvidence) -> bool:
        if not flow:
            return False
        observation = str(getattr(flow, "observation", "") or "")
        missing_fields = list(getattr(flow, "missing_fields", []) or [])
        return not missing_fields and not observation.startswith("资金数据缺失")

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
                if not value or value in {"-", "--"}:
                    return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _format_amount(cls, value: Any) -> str:
        amount = cls._safe_float(value)
        if amount <= 0:
            return "未知"
        if amount >= 100_000_000:
            return f"{amount / 100_000_000:.2f}亿"
        if amount >= 10_000:
            return f"{amount / 10_000:.2f}万"
        return f"{amount:.2f}亿"
