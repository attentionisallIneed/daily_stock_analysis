# -*- coding: utf-8 -*-
"""Prompt construction and strict JSON parsing for theme discovery."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


REQUIRED_THEME_FIELDS = {
    "name",
    "confidence",
    "catalysts",
    "risks",
    "related_sectors",
    "evidence_ids",
    "unsupported_claims",
}


def build_theme_discovery_prompt(
    evidence: Sequence[Dict[str, Any]],
    sectors: Sequence[Dict[str, Any]],
    market_environment: Optional[Dict[str, Any]] = None,
    theme_count: int = 5,
) -> str:
    """Build a JSON-only prompt that forces evidence-backed theme output."""
    market_environment = market_environment or {}
    evidence_lines = []
    for item in evidence:
        evidence_lines.append(
            "- {id} | {source} | {title} | sectors={sectors} | summary={summary}".format(
                id=item.get("id", ""),
                source=item.get("source", ""),
                title=item.get("title", ""),
                sectors=",".join(item.get("related_sectors") or []),
                summary=item.get("summary", ""),
            )
        )

    sector_lines = [
        "- {name} ({sector_type}) change={change_pct}% amount={amount} turnover={turnover_rate} leader={leading_stock}".format(
            name=item.get("name", ""),
            sector_type=item.get("sector_type", "industry"),
            change_pct=item.get("change_pct", 0),
            amount=item.get("amount", 0),
            turnover_rate=item.get("turnover_rate", 0),
            leading_stock=item.get("leading_stock", ""),
        )
        for item in sectors
    ]

    return f"""你是热点板块主题发现助手。请只输出严格 JSON，不要输出解释文字。

目标：从新闻/政策/公告/资金证据中归纳不超过 {theme_count} 个 A 股热点主题。

硬规则：
- 每个主题必须引用输入 evidence_ids，不能为空。
- 不允许输出无证据主题。
- 不得臆造买卖结论、目标价、仓位或止损。
- 每个主题必须包含 confidence、catalysts、risks、related_sectors、evidence_ids、unsupported_claims。
- unsupported_claims 非空时，该主题不得标为高置信度。
- 若新闻热但行情未验证，标注“新闻热、资金未确认”。
- 若行情强但新闻证据弱，标注“资金驱动、催化待确认”。

市场环境：
{json.dumps(market_environment, ensure_ascii=False)}

输入证据：
{chr(10).join(evidence_lines) if evidence_lines else "- 无新闻证据，仅可基于板块证据生成待确认主题"}

热门板块：
{chr(10).join(sector_lines) if sector_lines else "- 无板块数据"}

输出 JSON schema:
{{
  "themes": [
    {{
      "name": "主题名称",
      "confidence": "高/中/低",
      "heat_score": 0,
      "news_score": 0,
      "capital_score": 0,
      "market_score": 0,
      "persistence_score": 0,
      "related_sectors": ["板块名称"],
      "catalysts": ["催化1"],
      "risks": ["风险1"],
      "evidence_ids": ["news_001", "sector_001"],
      "unsupported_claims": []
    }}
  ]
}}"""


def parse_theme_discovery_response(
    response_text: str,
    valid_evidence_ids: Optional[Iterable[str]] = None,
    fallback_sectors: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Parse LLM JSON and filter unsupported or evidence-free themes."""
    if not response_text:
        return []

    payload = _load_json_object(response_text)
    themes = payload.get("themes", []) if isinstance(payload, dict) else []
    valid_ids: Set[str] = set(valid_evidence_ids or [])
    fallback_sector_set = set(fallback_sectors or [])
    parsed: List[Dict[str, Any]] = []

    for raw in themes:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_theme(raw)
        if not normalized["evidence_ids"]:
            continue
        if valid_ids:
            normalized["evidence_ids"] = [item for item in normalized["evidence_ids"] if item in valid_ids]
            if not normalized["evidence_ids"]:
                continue
        if fallback_sector_set:
            requested_sectors = list(normalized["related_sectors"])
            normalized["related_sectors"] = [
                item for item in normalized["related_sectors"] if item in fallback_sector_set
            ]
            if requested_sectors and not normalized["related_sectors"]:
                normalized["requested_sectors"] = requested_sectors
                normalized["risks"].append("主题与现有板块映射待确认")
        if normalized["unsupported_claims"] and normalized["confidence"] == "高":
            normalized["confidence"] = "中"
            normalized["risks"].append("存在 unsupported_claims，自动降低置信度")
        parsed.append(normalized)
    return parsed


def _load_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    elif not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        cleaned = cleaned[start : end + 1] if start >= 0 and end > start else "{}"

    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return json.loads(cleaned)


def _normalize_theme(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = {field: raw.get(field) for field in REQUIRED_THEME_FIELDS}
    data["name"] = str(data.get("name") or "").strip()
    data["confidence"] = str(data.get("confidence") or "中").strip() or "中"
    for key in ("catalysts", "risks", "related_sectors", "evidence_ids", "unsupported_claims"):
        data[key] = _as_str_list(data.get(key))
    for key in ("heat_score", "news_score", "capital_score", "market_score", "persistence_score"):
        data[key] = _safe_float(raw.get(key))
    return data


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
