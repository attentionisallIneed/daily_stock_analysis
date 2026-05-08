from capital_flow import CapitalFlowAdapter


def test_capital_flow_normalizes_source_update_reliability_and_scores():
    adapter = CapitalFlowAdapter()

    flows = adapter.collect_for_sectors(
        [
            {
                "name": "AI应用",
                "change_pct": "4.5%",
                "amount": "1500000000",
                "turnover_rate": "3.2",
                "leading_stock": "Alpha",
                "source": "unit",
                "updated_at": "2026-05-08 10:00:00",
                "reliability": "high",
            },
            {"name": "低空经济", "change_pct": "1.0"},
        ],
        {"north_flow": 35.0},
    )

    strong = flows["AI应用"]
    weak = flows["低空经济"]

    assert strong.source == "unit"
    assert strong.updated_at == "2026-05-08 10:00:00"
    assert strong.reliability == "high"
    assert strong.score > weak.score
    assert strong.observation in {"新闻与资金共振", "资金强、新闻待确认"}
    assert weak.missing_fields == ["amount", "turnover_rate"]
    assert weak.observation == "资金数据缺失，按中性处理"
