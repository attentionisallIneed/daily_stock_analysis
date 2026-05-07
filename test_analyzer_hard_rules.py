from analyzer import AnalysisResult, OpenAIAnalyzer


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
