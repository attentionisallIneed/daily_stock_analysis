# -*- coding: utf-8 -*-
"""官方公告与结构化财务情报整理。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


RISK_KEYWORDS = [
    "减持",
    "处罚",
    "立案",
    "调查",
    "监管函",
    "警示函",
    "问询函",
    "诉讼",
    "仲裁",
    "冻结",
    "质押",
    "预亏",
    "亏损",
    "业绩下降",
    "业绩预减",
    "解禁",
    "退市",
]

POSITIVE_KEYWORDS = [
    "增持",
    "回购",
    "中标",
    "合同",
    "预增",
    "业绩增长",
    "盈利",
    "分红",
    "股权激励",
]


@dataclass
class AnnouncementItem:
    """单条官方公告。"""

    title: str
    date: str = ""
    url: str = ""
    category: str = ""
    source: str = "CNINFO"
    risk_tags: List[str] = field(default_factory=list)
    positive_tags: List[str] = field(default_factory=list)

    @property
    def is_risk(self) -> bool:
        return bool(self.risk_tags)

    @property
    def is_positive(self) -> bool:
        return bool(self.positive_tags)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "date": self.date,
            "url": self.url,
            "category": self.category,
            "source": self.source,
            "risk_tags": self.risk_tags,
            "positive_tags": self.positive_tags,
            "is_risk": self.is_risk,
            "is_positive": self.is_positive,
        }


@dataclass
class FinancialSnapshot:
    """最近一期结构化财务指标。"""

    report_date: str = ""
    revenue_growth_pct: Optional[float] = None
    net_profit_growth_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    debt_ratio_pct: Optional[float] = None
    operating_cashflow: Optional[float] = None
    risk_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_date": self.report_date,
            "revenue_growth_pct": self.revenue_growth_pct,
            "net_profit_growth_pct": self.net_profit_growth_pct,
            "roe_pct": self.roe_pct,
            "gross_margin_pct": self.gross_margin_pct,
            "debt_ratio_pct": self.debt_ratio_pct,
            "operating_cashflow": self.operating_cashflow,
            "risk_flags": self.risk_flags,
        }


@dataclass
class RestrictedReleaseItem:
    """单批限售股解禁。"""

    release_date: str = ""
    shareholder_count: Optional[int] = None
    release_shares: Optional[float] = None
    actual_release_shares: Optional[float] = None
    remaining_locked_shares: Optional[float] = None
    market_value: Optional[float] = None
    total_mv_ratio_pct: Optional[float] = None
    float_mv_ratio_pct: Optional[float] = None
    shareholder_type: str = ""
    pre_close_price: Optional[float] = None
    pre_20d_change_pct: Optional[float] = None
    post_20d_change_pct: Optional[float] = None
    source: str = "Eastmoney"
    risk_tags: List[str] = field(default_factory=list)

    @property
    def is_risk(self) -> bool:
        return bool(self.risk_tags)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_date": self.release_date,
            "shareholder_count": self.shareholder_count,
            "release_shares": self.release_shares,
            "actual_release_shares": self.actual_release_shares,
            "remaining_locked_shares": self.remaining_locked_shares,
            "market_value": self.market_value,
            "total_mv_ratio_pct": self.total_mv_ratio_pct,
            "float_mv_ratio_pct": self.float_mv_ratio_pct,
            "shareholder_type": self.shareholder_type,
            "pre_close_price": self.pre_close_price,
            "pre_20d_change_pct": self.pre_20d_change_pct,
            "post_20d_change_pct": self.post_20d_change_pct,
            "source": self.source,
            "risk_tags": self.risk_tags,
            "is_risk": self.is_risk,
        }


@dataclass
class CompanyIntelligence:
    """官方公告和财务指标汇总。"""

    code: str
    announcements: List[AnnouncementItem] = field(default_factory=list)
    financial: Optional[FinancialSnapshot] = None
    restricted_releases: List[RestrictedReleaseItem] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    positive_catalysts: List[str] = field(default_factory=list)
    source_priority: str = "官方公告 > 解禁/财务结构化数据 > 搜索摘要"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "announcements": [item.to_dict() for item in self.announcements],
            "financial": self.financial.to_dict() if self.financial else {},
            "restricted_releases": [item.to_dict() for item in self.restricted_releases],
            "risk_flags": self.risk_flags,
            "positive_catalysts": self.positive_catalysts,
            "source_priority": self.source_priority,
        }

    def format_context(self, max_announcements: int = 8) -> str:
        lines = [
            "## 官方公告、限售解禁与结构化财务数据",
            f"信息优先级：{self.source_priority}",
            "",
            "### 近期公告",
        ]
        if self.announcements:
            for item in self.announcements[:max_announcements]:
                tags = []
                if item.risk_tags:
                    tags.append("风险:" + "/".join(item.risk_tags))
                if item.positive_tags:
                    tags.append("利好:" + "/".join(item.positive_tags))
                tag_text = f"（{'；'.join(tags)}）" if tags else ""
                url_text = f" {item.url}" if item.url else ""
                lines.append(f"- [{item.source}] {item.date} {item.title}{tag_text}{url_text}")
        else:
            lines.append("- 未获取到近期官方公告")

        lines.extend(["", "### 限售解禁"])
        if self.restricted_releases:
            for item in self.restricted_releases:
                tag_text = f"（风险:{'/'.join(item.risk_tags)}）" if item.risk_tags else ""
                ratio_text = _fmt_ratio_pct(item.float_mv_ratio_pct)
                value_text = _fmt_number(item.market_value)
                lines.append(
                    f"- {item.release_date or '未知日期'} {item.shareholder_type or '限售股'}"
                    f" 解禁市值{value_text}，占流通市值{ratio_text}{tag_text}"
                )
        else:
            lines.append("- 未获取到限售解禁批次")

        lines.extend(["", "### 财务指标"])
        if self.financial:
            financial = self.financial
            lines.extend(
                [
                    f"- 报告期：{financial.report_date or '未知'}",
                    f"- 营收同比：{_fmt_pct(financial.revenue_growth_pct)}",
                    f"- 净利润同比：{_fmt_pct(financial.net_profit_growth_pct)}",
                    f"- ROE：{_fmt_pct(financial.roe_pct)}",
                    f"- 毛利率：{_fmt_pct(financial.gross_margin_pct)}",
                    f"- 资产负债率：{_fmt_pct(financial.debt_ratio_pct)}",
                    f"- 经营现金流：{_fmt_number(financial.operating_cashflow)}",
                ]
            )
            if financial.risk_flags:
                lines.append("- 财务风险：" + "；".join(financial.risk_flags))
        else:
            lines.append("- 未获取到结构化财务指标")

        if self.risk_flags:
            lines.extend(["", "### 官方风险提示"])
            lines.extend(f"- {flag}" for flag in self.risk_flags)

        if self.positive_catalysts:
            lines.extend(["", "### 官方正向催化"])
            lines.extend(f"- {catalyst}" for catalyst in self.positive_catalysts)

        return "\n".join(lines)


class CompanyIntelligenceService:
    """从数据源拉取并整理官方公告和财务指标。"""

    FINANCIAL_ALIASES = {
        "report_date": ["报告期", "日期", "公告日期"],
        "revenue_growth_pct": ["营业总收入同比增长率", "营业收入同比增长率", "营业收入增长率", "营收同比增长率"],
        "net_profit_growth_pct": ["归属净利润同比增长率", "净利润同比增长率", "扣非净利润同比增长率", "净利润增长率"],
        "roe_pct": ["净资产收益率", "加权净资产收益率", "ROE"],
        "gross_margin_pct": ["销售毛利率", "毛利率"],
        "debt_ratio_pct": ["资产负债率"],
        "operating_cashflow": ["经营现金流量净额", "每股经营现金流量", "经营性现金流"],
    }

    def __init__(self, fetcher: Any):
        self.fetcher = fetcher

    def get_company_intelligence(self, code: str, stock_name: str = "") -> CompanyIntelligence:
        announcements = self._load_announcements(code)
        restricted_releases = self._load_restricted_releases(code)
        financial = self._load_financial_snapshot(code)

        intelligence = CompanyIntelligence(
            code=code,
            announcements=announcements,
            financial=financial,
            restricted_releases=restricted_releases,
        )
        for announcement in announcements:
            if announcement.risk_tags:
                intelligence.risk_flags.append(
                    f"{announcement.date} {announcement.title}（{','.join(announcement.risk_tags)}）"
                )
            if announcement.positive_tags:
                intelligence.positive_catalysts.append(
                    f"{announcement.date} {announcement.title}（{','.join(announcement.positive_tags)}）"
                )

        for item in restricted_releases:
            if item.risk_tags:
                ratio_text = _fmt_ratio_pct(item.float_mv_ratio_pct)
                value_text = _fmt_number(item.market_value)
                intelligence.risk_flags.append(
                    f"{item.release_date} 限售股解禁：{item.shareholder_type or '未分类'}，"
                    f"解禁市值{value_text}，占流通市值{ratio_text}（{','.join(item.risk_tags)}）"
                )

        if financial and financial.risk_flags:
            intelligence.risk_flags.extend(financial.risk_flags)

        return intelligence

    def _load_announcements(self, code: str) -> List[AnnouncementItem]:
        try:
            raw_items = self.fetcher.get_cninfo_announcements(code, max_items=20)
        except Exception:
            raw_items = []

        announcements = []
        for raw in raw_items:
            title = str(_pick_value(raw, ["title", "公告标题", "标题", "announcement_title"]) or "").strip()
            if not title:
                continue
            risk_tags = [keyword for keyword in RISK_KEYWORDS if keyword in title]
            positive_tags = [keyword for keyword in POSITIVE_KEYWORDS if keyword in title]
            announcements.append(
                AnnouncementItem(
                    title=title,
                    date=str(_pick_value(raw, ["date", "公告时间", "公告日期", "披露日期"]) or ""),
                    url=str(_pick_value(raw, ["url", "公告链接", "链接", "adjunctUrl"]) or ""),
                    category=str(_pick_value(raw, ["category", "公告类型", "分类"]) or ""),
                    source=str(_pick_value(raw, ["source"]) or "CNINFO"),
                    risk_tags=risk_tags,
                    positive_tags=positive_tags,
                )
            )
        return announcements

    def _load_restricted_releases(self, code: str) -> List[RestrictedReleaseItem]:
        try:
            raw_items = self.fetcher.get_restricted_release_queue(code, max_items=20)
        except Exception:
            raw_items = []

        releases = []
        for raw in raw_items:
            release_date = _format_date(_pick_value(raw, ["release_date", "解禁时间", "解禁日期"]))
            item = RestrictedReleaseItem(
                release_date=release_date,
                shareholder_count=_pick_int(raw, ["shareholder_count", "解禁股东数"]),
                release_shares=_pick_float(raw, ["release_shares", "解禁数量"]),
                actual_release_shares=_pick_float(raw, ["actual_release_shares", "实际解禁数量"]),
                remaining_locked_shares=_pick_float(raw, ["remaining_locked_shares", "未解禁数量"]),
                market_value=_pick_float(raw, ["market_value", "实际解禁数量市值", "实际解禁市值", "解禁股流通市值"]),
                total_mv_ratio_pct=_pick_float(raw, ["total_mv_ratio_pct", "占总市值比例"]),
                float_mv_ratio_pct=_pick_float(raw, ["float_mv_ratio_pct", "占流通市值比例", "占解禁前流通市值比例"]),
                shareholder_type=str(_pick_value(raw, ["shareholder_type", "限售股类型"]) or ""),
                pre_close_price=_pick_float(raw, ["pre_close_price", "解禁前一交易日收盘价"]),
                pre_20d_change_pct=_pick_float(raw, ["pre_20d_change_pct", "解禁前20日涨跌幅"]),
                post_20d_change_pct=_pick_float(raw, ["post_20d_change_pct", "解禁后20日涨跌幅"]),
                source=str(_pick_value(raw, ["source"]) or "Eastmoney"),
            )
            item.risk_tags = self._restricted_release_risk_tags(item)
            releases.append(item)

        return sorted(releases, key=lambda item: _parse_date(item.release_date) or date.max)

    def _restricted_release_risk_tags(self, item: RestrictedReleaseItem) -> List[str]:
        tags = []
        release_dt = _parse_date(item.release_date)
        if release_dt:
            days_delta = (release_dt - date.today()).days
            if 0 <= days_delta <= 60:
                tags.append(f"未来{days_delta}日解禁")
            elif -10 <= days_delta < 0:
                tags.append(f"近{abs(days_delta)}日已解禁")

        ratio = item.float_mv_ratio_pct
        if ratio is not None:
            if ratio >= 10:
                tags.append("大额解禁")
            elif ratio >= 5:
                tags.append("中等规模解禁")
            elif ratio >= 3:
                tags.append("小规模解禁")

        if item.market_value is not None and item.market_value >= 1_000_000_000:
            tags.append("解禁市值较高")

        return tags

    def _load_financial_snapshot(self, code: str) -> Optional[FinancialSnapshot]:
        try:
            raw_rows = self.fetcher.get_financial_indicators(code)
        except Exception:
            raw_rows = []
        if not raw_rows:
            return None

        latest = raw_rows[0]
        snapshot = FinancialSnapshot(
            report_date=str(_pick_value(latest, self.FINANCIAL_ALIASES["report_date"]) or ""),
            revenue_growth_pct=_pick_float(latest, self.FINANCIAL_ALIASES["revenue_growth_pct"]),
            net_profit_growth_pct=_pick_float(latest, self.FINANCIAL_ALIASES["net_profit_growth_pct"]),
            roe_pct=_pick_float(latest, self.FINANCIAL_ALIASES["roe_pct"]),
            gross_margin_pct=_pick_float(latest, self.FINANCIAL_ALIASES["gross_margin_pct"]),
            debt_ratio_pct=_pick_float(latest, self.FINANCIAL_ALIASES["debt_ratio_pct"]),
            operating_cashflow=_pick_float(latest, self.FINANCIAL_ALIASES["operating_cashflow"]),
        )
        snapshot.risk_flags = self._financial_risk_flags(snapshot)
        return snapshot

    def _financial_risk_flags(self, snapshot: FinancialSnapshot) -> List[str]:
        flags = []
        if snapshot.revenue_growth_pct is not None and snapshot.revenue_growth_pct <= -20:
            flags.append(f"营收同比下滑{abs(snapshot.revenue_growth_pct):.1f}%")
        if snapshot.net_profit_growth_pct is not None and snapshot.net_profit_growth_pct <= -30:
            flags.append(f"净利润同比下滑{abs(snapshot.net_profit_growth_pct):.1f}%")
        if snapshot.roe_pct is not None and snapshot.roe_pct < 3:
            flags.append(f"ROE偏低({snapshot.roe_pct:.1f}%)")
        if snapshot.debt_ratio_pct is not None and snapshot.debt_ratio_pct >= 75:
            flags.append(f"资产负债率偏高({snapshot.debt_ratio_pct:.1f}%)")
        if snapshot.operating_cashflow is not None and snapshot.operating_cashflow < 0:
            flags.append("经营现金流为负")
        return flags


def _pick_value(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _pick_float(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
    value = _pick_value(row, keys)
    return _to_float(value)


def _pick_int(row: Dict[str, Any], keys: List[str]) -> Optional[int]:
    value = _to_float(_pick_value(row, keys))
    if value is None:
        return None
    return int(value)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
            if value in {"", "-", "--", "不适用"}:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return ""
    parsed = _parse_date(text)
    return parsed.isoformat() if parsed else text


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _fmt_pct(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def _fmt_ratio_pct(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _fmt_number(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 100000000:
        return f"{value / 100000000:.2f}亿"
    if abs(value) >= 10000:
        return f"{value / 10000:.2f}万"
    return f"{value:.2f}"
