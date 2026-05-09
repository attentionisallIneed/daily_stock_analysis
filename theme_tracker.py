# -*- coding: utf-8 -*-
"""Theme status and history tracking for the hot-sector radar."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


STATUS_NEW = "新发酵"
STATUS_CONTINUE = "延续"
STATUS_DIVERGE = "分化"
STATUS_RECEDE = "退潮"
STATUS_PENDING = "待确认"


def classify_theme_status(
    current_theme: Dict[str, Any],
    previous_items: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify one theme as new, continuing, diverging, receding, or pending."""
    previous = list(previous_items or [])
    heat_score = float(current_theme.get("heat_score") or current_theme.get("total_score") or 0)
    capital_score = float(current_theme.get("capital_score") or 0)
    leader_count = len(current_theme.get("leader_candidates") or [])
    name = str(current_theme.get("name") or "")
    matched = [item for item in previous if str(item.get("name") or "") == name]
    existing_status = str(current_theme.get("status") or "")
    existing_downgrades = list(current_theme.get("downgrade_reasons") or [])

    if existing_status == STATUS_PENDING and existing_downgrades:
        status = STATUS_PENDING
        reason = "数据验证不足，保持待确认"
        consecutive_days = 1
    elif not matched:
        status = STATUS_NEW if heat_score >= 50 else STATUS_PENDING
        reason = "首次出现或历史记录为空"
        consecutive_days = 1
    else:
        last = matched[-1]
        last_score = float(last.get("heat_score") or last.get("total_score") or 0)
        consecutive_days = int(last.get("consecutive_days") or 1) + 1
        if heat_score <= last_score - 15 or capital_score <= 6:
            status = STATUS_RECEDE
            reason = "热度或资金验证明显下降"
        elif leader_count <= 1 and heat_score >= 50:
            status = STATUS_DIVERGE
            reason = "主题仍有热度，但核心龙头数量减少"
        else:
            status = STATUS_CONTINUE
            reason = "热度与核心线索延续"

    downgrade_reasons = list(current_theme.get("downgrade_reasons") or [])
    if capital_score <= 6:
        downgrade_reasons.append("板块成交额、换手率或北向资金验证不足")
    if any("MA20" in str(flag) for flag in current_theme.get("risks") or []):
        downgrade_reasons.append("核心股跌破 MA20")

    return {
        "status": status,
        "status_reason": reason,
        "consecutive_days": consecutive_days,
        "downgrade_reasons": downgrade_reasons,
        "history": matched[-5:],
    }


class ThemeTracker:
    """Persist daily ThemeRadarResult snapshots and update theme statuses."""

    def __init__(self, history_dir: str | Path = "data/theme_radar") -> None:
        self.history_dir = Path(history_dir)

    def save_history(self, result: Any) -> str:
        """Save one radar result snapshot as JSON and return the file path."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
        generated_at = getattr(result, "generated_at", "") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_part = generated_at[:10] if len(generated_at) >= 10 else datetime.now().strftime("%Y-%m-%d")
        path = self.history_dir / f"theme_radar_{date_part}.json"
        data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def load_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.history_dir.exists():
            return []
        records: List[Dict[str, Any]] = []
        for path in sorted(self.history_dir.glob("theme_radar_*.json"))[-limit:]:
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return records

    def update_theme_statuses(self, themes: Iterable[Any]) -> None:
        history_items = self._flatten_history(self.load_history())
        for theme in themes:
            data = theme.to_dict() if hasattr(theme, "to_dict") else dict(theme)
            status = classify_theme_status(data, history_items)
            if hasattr(theme, "status"):
                theme.status = status["status"]
                theme.status_reason = status["status_reason"]
                theme.consecutive_days = status["consecutive_days"]
                theme.downgrade_reasons = status["downgrade_reasons"]
                theme.history = status["history"]

    @staticmethod
    def _flatten_history(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        themes: List[Dict[str, Any]] = []
        for record in records:
            for theme in record.get("themes", []):
                if isinstance(theme, dict):
                    themes.append(theme)
        return themes
