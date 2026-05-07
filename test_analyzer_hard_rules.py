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
