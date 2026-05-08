from analyzer import AnalysisResult, OpenAIAnalyzer


BUY = "\u4e70\u5165"
WATCH = "\u89c2\u671b"
BULLISH = "\u770b\u591a"
HIGH = "\u9ad8"
MEDIUM = "\u4e2d"
BULLISH_TREND = "\u591a\u5934\u6392\u5217"
BEARISH_TREND = "\u7a7a\u5934\u6392\u5217"
WEAK_MARKET = "\u504f\u5f31"
EXTREME_WEAK_MARKET = "\u6781\u5f31"


def test_hard_rules_enrich_dashboard_with_position_price_and_rule_warnings():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=88,
        trend_prediction=BULLISH,
        operation_advice=BUY,
        confidence_level=HIGH,
        dashboard={
            "core_conclusion": {"position_advice": {}},
            "data_perspective": {"price_position": {}},
            "battle_plan": {"sniper_points": {}, "position_strategy": {}},
            "intelligence": {"risk_alerts": []},
        },
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": BULLISH_TREND,
            "risk_reward_ratio": 1.5,
            "final_position_pct": 8.0,
            "current_price": 10.0,
            "support_levels": [9.6, 10.2],
            "resistance_levels": [11.5, 12.0],
            "instrument_type": "ETF",
            "strategy_profile": "breakout",
            "strategy_notes": ["rule note"],
            "pattern_signal": "platform",
            "breakout_status": "watch",
            "breakout_score": 77,
            "breakout_level": 10.8,
            "breakout_extension_threshold": 6.0,
            "ideal_buy": 9.8,
            "secondary_buy": 9.5,
            "stop_loss": 9.0,
            "take_profit": 12.0,
            "invalidation_condition": "break 9",
            "single_trade_risk_pct": 1.2,
            "max_position_by_risk_pct": 18.0,
            "position_note": "use small size",
        },
        "chip": {"profit_ratio": 0.95, "concentration_90": 0.2},
        "market_context": {"environment": {"market_status": WEAK_MARKET}},
        "company_intel": {"risk_flags": ["official risk"]},
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    dashboard = updated.dashboard
    data_perspective = dashboard["data_perspective"]
    battle_plan = dashboard["battle_plan"]

    assert updated.operation_advice == BUY
    assert updated.sentiment_score <= 65
    assert updated.confidence_level == MEDIUM
    assert data_perspective["instrument_strategy"]["instrument_type"] == "ETF"
    assert data_perspective["instrument_strategy"]["strategy_notes"] == ["rule note"]
    assert data_perspective["pattern_status"]["breakout_score"] == 77
    assert data_perspective["price_position"]["support_level"] == 10.2
    assert data_perspective["price_position"]["resistance_level"] == 11.5
    assert "9.80" in battle_plan["sniper_points"]["ideal_buy"]
    assert "1.50" in battle_plan["sniper_points"]["risk_reward_ratio"]
    assert battle_plan["sniper_points"]["invalidation_condition"] == "break 9"
    assert "8.0%" in battle_plan["position_strategy"]["suggested_position"]
    assert "use small size" in battle_plan["position_strategy"]["risk_control"]
    assert any("official risk" in alert for alert in dashboard["intelligence"]["risk_alerts"])
    assert "\u5927\u76d8" in updated.risk_warning


def test_hard_rules_extreme_market_rewrites_dashboard_to_wait():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=90,
        trend_prediction=BULLISH,
        operation_advice=BUY,
        confidence_level=HIGH,
        dashboard={
            "core_conclusion": {"one_sentence": "buy", "signal_type": "buy", "position_advice": {}},
            "battle_plan": {"position_strategy": {}},
        },
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": BULLISH_TREND,
            "risk_reward_ratio": 2.2,
            "final_position_pct": 0.0,
        },
        "market_context": {"environment": {"market_status": EXTREME_WEAK_MARKET}},
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == WATCH
    assert updated.sentiment_score <= 55
    assert updated.dashboard["core_conclusion"]["one_sentence"]
    assert updated.dashboard["core_conclusion"]["signal_type"]
    assert updated.dashboard["core_conclusion"]["position_advice"]["no_position"]
    assert "0.0%" in updated.dashboard["battle_plan"]["position_strategy"]["suggested_position"]


def test_hard_rules_block_buy_for_bearish_trend_status():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=85,
        trend_prediction=BULLISH,
        operation_advice=BUY,
        confidence_level=HIGH,
        dashboard={"core_conclusion": {"position_advice": {}}, "battle_plan": {"position_strategy": {}}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": BEARISH_TREND,
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == WATCH
    assert updated.sentiment_score <= 39
    assert "\u7a7a\u5934" in updated.risk_warning


def test_hard_rules_use_adaptive_bias_threshold_to_block_buy_advice():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 3.0,
            "adaptive_bias_threshold": 2.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "观望"
    assert updated.sentiment_score <= 59
    assert "超过2.00%纪律线" in updated.risk_warning


def test_hard_rules_do_not_block_safe_bias_below_adaptive_threshold():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 3.0,
            "adaptive_bias_threshold": 4.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "买入"
    assert "纪律线" not in updated.risk_warning


def test_hard_rules_allow_confirmed_breakout_below_extension_line():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=88,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}, "data_perspective": {}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 3.0,
            "adaptive_bias_threshold": 2.0,
            "breakout_valid": True,
            "breakout_extension_threshold": 4.0,
            "breakout_status": "放量突破20日高点",
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "买入"
    assert updated.sentiment_score <= 79
    assert updated.confidence_level == "中"
    assert "有效突破" in updated.risk_warning
    assert updated.dashboard["data_perspective"]["pattern_status"]["breakout_extension_threshold"] == 4.0


def test_hard_rules_block_breakout_after_extension_line():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=88,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}, "data_perspective": {}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 5.0,
            "adaptive_bias_threshold": 2.0,
            "breakout_valid": True,
            "breakout_extension_threshold": 4.0,
            "breakout_status": "放量突破20日高点",
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "观望"
    assert updated.sentiment_score <= 59
    assert "突破延伸线" in updated.risk_warning


def test_hard_rules_block_buy_advice_after_ma20_breakdown():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
            "ma20_breakdown": True,
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "观望"
    assert updated.sentiment_score <= 49
    assert "跌破MA20" in updated.risk_warning


def test_hard_rules_reduce_confidence_for_weak_relative_strength():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
            "relative_strength_score": -8,
            "relative_strength_status": "明显弱于基准/行业",
        }
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "买入"
    assert updated.sentiment_score <= 69
    assert updated.confidence_level == "中"
    assert "相对强弱明显弱于基准/行业" in updated.risk_warning


def test_hard_rules_prioritize_official_risk_flags():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}, "intelligence": {"risk_alerts": []}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        },
        "company_intel": {
            "risk_flags": ["2026-05-01 关于控股股东减持股份预披露公告（减持）"],
        },
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "买入"
    assert updated.sentiment_score <= 69
    assert updated.confidence_level == "中"
    assert "官方公告/财务风险" in updated.risk_warning
    assert any("官方公告/财务风险" in item for item in updated.dashboard["intelligence"]["risk_alerts"])


def test_hard_rules_block_buy_for_severe_official_risk_flags():
    result = AnalysisResult(
        code="000001",
        name="test",
        sentiment_score=82,
        trend_prediction="看多",
        operation_advice="买入",
        confidence_level="高",
        dashboard={"core_conclusion": {"position_advice": {}}, "intelligence": {"risk_alerts": []}},
    )
    context = {
        "trend_analysis": {
            "bias_ma5": 1.0,
            "adaptive_bias_threshold": 5.0,
            "trend_status": "多头排列",
            "risk_reward_ratio": 2.0,
            "final_position_pct": 20.0,
        },
        "company_intel": {
            "risk_flags": ["2026-05-01 公司被立案调查公告（立案）"],
        },
    }

    updated = OpenAIAnalyzer._apply_hard_rules(object.__new__(OpenAIAnalyzer), result, context)

    assert updated.operation_advice == "观望"
    assert updated.sentiment_score <= 59
    assert updated.confidence_level == "中"
