from datetime import date, datetime, timedelta

from company_intel import (
    AnnouncementItem,
    CompanyIntelligence,
    CompanyIntelligenceService,
    FinancialSnapshot,
    RestrictedReleaseItem,
    _fmt_number,
    _fmt_pct,
    _fmt_ratio_pct,
    _format_date,
    _parse_date,
    _pick_float,
    _pick_int,
    _pick_value,
    _to_float,
)


def test_company_intelligence_edge_helpers_and_empty_paths():
    announcement = AnnouncementItem(
        title="Risk and catalyst",
        date="2026-01-01",
        url="https://example.com",
        category="notice",
        risk_tags=["risk"],
        positive_tags=["good"],
    )
    financial = FinancialSnapshot(
        report_date="2026-03-31",
        revenue_growth_pct=-20.0,
        net_profit_growth_pct=-30.0,
        roe_pct=2.0,
        gross_margin_pct=10.0,
        debt_ratio_pct=75.0,
        operating_cashflow=-1.0,
        risk_flags=["cash risk"],
    )
    release = RestrictedReleaseItem(
        release_date="2026-04-01",
        shareholder_count=1,
        release_shares=100.0,
        actual_release_shares=90.0,
        remaining_locked_shares=10.0,
        market_value=200_000_000.0,
        total_mv_ratio_pct=2.0,
        float_mv_ratio_pct=4.0,
        shareholder_type="founder",
        pre_close_price=10.0,
        pre_20d_change_pct=-5.0,
        post_20d_change_pct=3.0,
        risk_tags=["unlock"],
    )
    intelligence = CompanyIntelligence(
        code="000001",
        announcements=[announcement],
        financial=financial,
        restricted_releases=[release],
        risk_flags=["risk flag"],
        positive_catalysts=["catalyst"],
    )

    rendered = intelligence.to_dict()

    assert rendered["announcements"][0]["is_risk"] is True
    assert rendered["announcements"][0]["is_positive"] is True
    assert rendered["financial"]["risk_flags"] == ["cash risk"]
    assert rendered["restricted_releases"][0]["is_risk"] is True
    assert "Risk and catalyst" in intelligence.format_context(max_announcements=1)

    class EmptyFetcher:
        def get_cninfo_announcements(self, code, max_items=20):
            raise RuntimeError("announcements down")

        def get_restricted_release_queue(self, code, max_items=20):
            raise RuntimeError("release down")

        def get_financial_indicators(self, code):
            raise RuntimeError("financial down")

    empty = CompanyIntelligenceService(EmptyFetcher()).get_company_intelligence("000002")
    empty_context = empty.format_context()

    assert empty.announcements == []
    assert empty.restricted_releases == []
    assert empty.financial is None
    assert empty_context

    service = CompanyIntelligenceService(EmptyFetcher())
    recent_release = RestrictedReleaseItem(
        release_date=(date.today() - timedelta(days=5)).isoformat(),
        float_mv_ratio_pct=6.0,
        market_value=1_500_000_000,
    )
    small_release = RestrictedReleaseItem(
        release_date=(date.today() + timedelta(days=90)).isoformat(),
        float_mv_ratio_pct=3.5,
        market_value=10_000,
    )

    assert len(service._restricted_release_risk_tags(recent_release)) >= 3
    assert service._restricted_release_risk_tags(small_release)
    assert len(service._financial_risk_flags(financial)) == 5
    assert service._financial_risk_flags(FinancialSnapshot(revenue_growth_pct=1.0)) == []

    row = {"a": "1,234.5%", "b": "--", "c": "", "d": "3.8"}
    assert _pick_value(row, ["missing", "a"]) == "1,234.5%"
    assert _pick_value(row, ["c", "missing"]) is None
    assert _pick_float(row, ["a"]) == 1234.5
    assert _pick_float(row, ["b"]) is None
    assert _pick_int(row, ["d"]) == 3
    assert _pick_int({}, ["missing"]) is None
    assert _to_float(object()) is None
    assert _format_date("") == ""
    assert _format_date(datetime(2026, 1, 2, 3, 4)) == "2026-01-02"
    assert _format_date(date(2026, 1, 3)) == "2026-01-03"
    assert _format_date("20260104") == "2026-01-04"
    assert _format_date("not-a-date") == "not-a-date"
    assert _parse_date("") is None
    assert _fmt_pct(None) == "N/A"
    assert _fmt_pct(1.234) == "+1.23%"
    assert _fmt_ratio_pct(None) == "N/A"
    assert _fmt_ratio_pct(12.345) == "12.35%"
    assert _fmt_number(None) == "N/A"
    assert _fmt_number(200_000_000).startswith("2.00")
    assert _fmt_number(20_000).startswith("2.00")
    assert _fmt_number(20) == "20.00"
