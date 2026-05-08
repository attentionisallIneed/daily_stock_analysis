from analyzer import AnalysisResult, OpenAIAnalyzer


def test_hard_rules_enrich_dashboard_for_weak_market_low_position():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=88,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={
            "core_conclusion": {"one_sentence": "old", "position_advice": {}},
            "data_perspective": {"price_position": {}},
            "battle_plan": {"position_strategy": {}},
            "intelligence": {"risk_alerts": []},
        },
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 1.5,
            "final_position_pct": 8.0,
            "instrument_type": "行业ETF",
            "strategy_profile": "sector",
            "strategy_notes": ["follow sector heat"],
            "pattern_signal": "breakout",
            "breakout_status": "valid",
            "breakout_score": 6,
            "breakout_level": 10.5,
            "breakout_extension_threshold": 4.0,
            "support_levels": [9.6, 10.1],
            "resistance_levels": [11.2, 12.0],
            "current_price": 10.0,
            "ideal_buy": 10.2,
            "secondary_buy": 9.9,
            "stop_loss": 9.4,
            "take_profit": 11.2,
            "invalidation_condition": "break 9.4",
            "single_trade_risk_pct": 2.0,
            "max_position_by_risk_pct": 15.0,
            "position_note": "cap note",
        },
        "market_context": {"environment": {"market_status": "偏弱"}},
        "chip": {"profit_ratio": 0.95, "concentration_90": 0.2},
        "company_intel": {"risk_flags": ["risk flag"]},
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "买入"
    assert updated.sentiment_score <= 65
    assert updated.confidence_level == "中"
    data_perspective = updated.dashboard["data_perspective"]
    assert data_perspective["instrument_strategy"]["instrument_type"] == "行业ETF"
    assert data_perspective["pattern_status"]["breakout_score"] == 6
    assert data_perspective["price_position"]["support_level"] == 10.1
    assert data_perspective["price_position"]["resistance_level"] == 11.2
    sniper_points = updated.dashboard["battle_plan"]["sniper_points"]
    assert {
        "ideal_buy",
        "secondary_buy",
        "stop_loss",
        "take_profit",
        "risk_reward_ratio",
        "invalidation_condition",
    } <= set(sniper_points)
    position_strategy = updated.dashboard["battle_plan"]["position_strategy"]
    assert "8.0%" in position_strategy["suggested_position"]
    assert "cap note" in position_strategy["risk_control"]
    assert len(updated.dashboard["intelligence"]["risk_alerts"]) >= 4


def test_hard_rules_zero_position_extreme_market_updates_core_dashboard():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=88,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={
            "core_conclusion": {"one_sentence": "old", "position_advice": {}},
            "battle_plan": {"position_strategy": {}},
        },
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 0.0,
        },
        "market_context": {"environment": {"market_status": "极弱"}},
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "观望"
    assert updated.sentiment_score <= 55
    assert updated.confidence_level == "中"
    core = updated.dashboard["core_conclusion"]
    assert core["one_sentence"] != "old"
    assert "no_position" in core["position_advice"]
    position_strategy = updated.dashboard["battle_plan"]["position_strategy"]
    assert "0.0%" in position_strategy["suggested_position"]


def test_analyzer_rule_helpers_append_and_repair_json():
    analyzer = object.__new__(OpenAIAnalyzer)

    repaired = analyzer._fix_json_string(
        """
        {
            "enabled": True,
            "disabled": False,
            "items": [1,],
        }
        """
    )

    assert '"enabled": true' in repaired
    assert '"disabled": false' in repaired
    assert ",]" not in repaired
    assert OpenAIAnalyzer._append_warnings("base", ["next"]).startswith("base")
