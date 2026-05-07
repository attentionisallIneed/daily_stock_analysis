from datetime import date, timedelta

from company_intel import CompanyIntelligenceService


class FakeFetcher:
    def get_cninfo_announcements(self, code, max_items=20):
        return [
            {
                "公告标题": "关于控股股东减持股份预披露公告",
                "公告时间": "2026-05-01",
                "公告链接": "https://example.com/risk.pdf",
            },
            {
                "公告标题": "关于回购公司股份方案的公告",
                "公告时间": "2026-04-20",
                "公告链接": "https://example.com/buyback.pdf",
            },
        ]

    def get_restricted_release_queue(self, code, max_items=20):
        return [
            {
                "解禁时间": (date.today() + timedelta(days=20)).isoformat(),
                "解禁股东数": "3",
                "解禁数量": "20000000",
                "实际解禁数量": "18000000",
                "未解禁数量": "5000000",
                "实际解禁数量市值": "1200000000",
                "占总市值比例": "2.4",
                "占流通市值比例": "12.5",
                "解禁前一交易日收盘价": "30.1",
                "限售股类型": "首发原股东限售股份",
                "解禁前20日涨跌幅": "8.2",
            }
        ]

    def get_financial_indicators(self, code):
        return [
            {
                "报告期": "2026-03-31",
                "营业收入同比增长率": "-25.3",
                "净利润同比增长率": "-42.1",
                "净资产收益率": "2.5",
                "销售毛利率": "18.2",
                "资产负债率": "76.0",
                "经营现金流量净额": "-120000000",
            }
        ]


def test_company_intelligence_extracts_official_risks_and_financial_flags():
    intel = CompanyIntelligenceService(FakeFetcher()).get_company_intelligence("000001", "测试股")

    assert len(intel.announcements) == 2
    assert intel.announcements[0].risk_tags == ["减持"]
    assert "回购" in intel.announcements[1].positive_tags
    assert len(intel.restricted_releases) == 1
    assert "大额解禁" in intel.restricted_releases[0].risk_tags
    assert "解禁市值较高" in intel.restricted_releases[0].risk_tags
    assert intel.financial.report_date == "2026-03-31"
    assert intel.financial.net_profit_growth_pct == -42.1
    assert any("限售股解禁" in flag and "大额解禁" in flag for flag in intel.risk_flags)
    assert any("净利润同比下滑" in flag for flag in intel.risk_flags)
    assert any("资产负债率偏高" in flag for flag in intel.risk_flags)
    assert any("经营现金流为负" in flag for flag in intel.risk_flags)


def test_company_intelligence_formats_context_with_source_priority():
    intel = CompanyIntelligenceService(FakeFetcher()).get_company_intelligence("000001")
    context = intel.format_context()

    assert "官方公告、限售解禁与结构化财务数据" in context
    assert "官方公告 > 解禁/财务结构化数据 > 搜索摘要" in context
    assert "关于控股股东减持股份预披露公告" in context
    assert "限售解禁" in context
    assert "首发原股东限售股份" in context
    assert "财务风险" in context
