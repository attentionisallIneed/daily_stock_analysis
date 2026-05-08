from types import SimpleNamespace

import analyzer as analyzer_module
from analyzer import AnalysisResult, OpenAIAnalyzer


def _analyzer():
    instance = object.__new__(OpenAIAnalyzer)
    instance._client = None
    instance._is_available = False
    instance._model_name = "model"
    return instance


def test_analysis_result_dashboard_helpers_and_defaults():
    result = AnalysisResult(
        code="000001",
        name="Alpha",
        sentiment_score=72,
        trend_prediction="up",
        operation_advice="buy",
        confidence_level="high",
        dashboard={
            "core_conclusion": {
                "one_sentence": "core decision",
                "position_advice": {"no_position": "wait", "has_position": "hold"},
            },
            "battle_plan": {
                "sniper_points": {"ideal_buy": "10.0"},
                "action_checklist": ["check trend"],
            },
            "intelligence": {"risk_alerts": ["risk"]},
        },
        analysis_summary="summary",
    )

    rendered = result.to_dict()

    assert rendered["code"] == "000001"
    assert result.get_core_conclusion() == "core decision"
    assert result.get_position_advice() == "wait"
    assert result.get_position_advice(has_position=True) == "hold"
    assert result.get_sniper_points() == {"ideal_buy": "10.0"}
    assert result.get_checklist() == ["check trend"]
    assert result.get_risk_alerts() == ["risk"]
    assert result.get_emoji()
    assert result.get_confidence_stars()


def test_format_prompt_includes_enriched_context_sections():
    analyzer = _analyzer()
    context = {
        "code": "000001",
        "stock_name": "Alpha",
        "date": "2026-05-08",
        "today": {
            "close": 10.2,
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "pct_chg": 2.0,
            "volume": 150000000,
            "amount": 250000000,
            "ma5": 10.0,
            "ma10": 9.8,
            "ma20": 9.5,
        },
        "ma_status": "bullish",
        "market_context": {
            "overview": {
                "indices": [{"name": "IndexA", "change_pct": 1.2}],
                "top_sectors": [{"name": "Tech", "change_pct": 3.4}],
                "bottom_sectors": [{"name": "Bank", "change_pct": -1.0}],
            },
            "environment": {
                "market_status": "strong",
                "market_score": 80,
                "risk_level": "low",
                "summary": "healthy",
                "reasons": ["breadth improved"],
                "sector_heat_summary": "Tech leads",
            },
        },
        "realtime": {
            "price": 10.3,
            "volume_ratio": 1.5,
            "volume_ratio_desc": "active",
            "turnover_rate": 4.1,
            "pe_ratio": 12.5,
            "pb_ratio": 1.2,
            "total_mv": 100000000,
            "circ_mv": 80000000,
            "change_60d": 8.0,
        },
        "chip": {
            "profit_ratio": 0.72,
            "avg_cost": 9.5,
            "concentration_90": 0.12,
            "concentration_70": 0.08,
            "chip_status": "healthy",
        },
        "trend_analysis": {
            "instrument_type": "stock",
            "strategy_profile": "trend",
            "strategy_notes": ["follow rules"],
            "bias_ma5": 2.0,
            "adaptive_bias_threshold": 5.0,
            "adaptive_support_tolerance": 0.02,
            "relative_strength_period": 20,
            "relative_strength_status": "strong",
            "relative_strength_summary": "beats benchmark",
            "relative_strength_score": 8,
            "sector_name": "Tech",
            "support_levels": [9.8, 9.5],
            "resistance_levels": [10.8],
            "breakout_reasons": ["new high"],
            "breakout_risks": ["extension"],
            "risk_reward_ratio": 2.0,
            "final_position_pct": 25.0,
            "signal_reasons": ["trend intact"],
            "risk_factors": ["watch volume"],
        },
        "yesterday": {"close": 10.0},
        "volume_change_ratio": 1.3,
        "price_change_ratio": 2.0,
        "company_intel_context": "official filing context",
    }

    prompt = analyzer._format_prompt(context, "Fallback", news_context="news context")

    assert "000001" in prompt
    assert "Alpha" in prompt
    assert "official filing context" in prompt
    assert "news context" in prompt
    assert "breadth improved" in prompt
    assert "trend intact" in prompt


def test_parse_response_handles_json_fences_repairs_and_text_fallbacks():
    analyzer = _analyzer()

    parsed = analyzer._parse_response(
        """prefix ```json
        {
            "sentiment_score": 73,
            "trend_prediction": "up",
            "operation_advice": "buy",
            "confidence_level": "high",
            "dashboard": {"core_conclusion": {"one_sentence": "go"}},
            "search_performed": True,
        }
        ``` suffix""",
        code="000001",
        name="Alpha",
    )

    assert parsed.sentiment_score == 73
    assert parsed.dashboard["core_conclusion"]["one_sentence"] == "go"
    assert parsed.search_performed is True

    positive = analyzer._parse_response("bullish buy breakout catalyst", "000001", "Alpha")
    negative = analyzer._parse_response("bearish sell weak breakdown", "000001", "Alpha")

    assert positive.sentiment_score == 65
    assert negative.sentiment_score == 35
    assert positive.raw_response.startswith("bullish")
    assert negative.raw_response.startswith("bearish")


def test_analyze_returns_default_when_unavailable_and_success_when_mocked(monkeypatch):
    config = SimpleNamespace(llm_request_delay=0)
    monkeypatch.setattr(analyzer_module, "get_config", lambda: config)

    unavailable = _analyzer()
    result = unavailable.analyze({"code": "000001", "realtime": {"name": "Alpha"}})

    assert result.name == "Alpha"
    assert result.success is False
    assert result.error_message

    available = _analyzer()
    available._is_available = True
    calls = []
    monkeypatch.setattr(available, "_format_prompt", lambda context, name, news_context=None: "prompt")
    monkeypatch.setattr(
        available,
        "_call_api_with_retry",
        lambda prompt, generation_config: calls.append((prompt, generation_config)) or '{"sentiment_score": 66}',
    )
    monkeypatch.setattr(available, "_apply_hard_rules", lambda result, context: result)

    parsed = available.analyze({"code": "000002", "stock_name": "Beta"}, news_context="news")

    assert parsed.code == "000002"
    assert parsed.sentiment_score == 66
    assert parsed.raw_response == '{"sentiment_score": 66}'
    assert parsed.search_performed is True
    assert calls[0][0] == "prompt"


def test_call_api_with_retry_uses_client_and_retry_delay(monkeypatch):
    analyzer = _analyzer()
    analyzer._client = SimpleNamespace()
    analyzer._model_name = "model"
    config = SimpleNamespace(llm_max_retries=2, llm_retry_delay=0.5)
    monkeypatch.setattr(analyzer_module, "get_config", lambda: config)
    sleeps = []
    monkeypatch.setattr(analyzer_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    attempts = []

    class FakeCompletions:
        def create(self, **kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise RuntimeError("temporary")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    analyzer._client.chat = SimpleNamespace(completions=FakeCompletions())

    assert analyzer._call_api_with_retry("prompt", {"temperature": 0.2, "max_output_tokens": 100}) == "ok"
    assert sleeps == [0.5]
    assert attempts[1]["model"] == "model"
    assert attempts[1]["messages"][1]["content"] == "prompt"


def test_format_helpers_and_batch_analyze(monkeypatch):
    analyzer = _analyzer()
    contexts = [{"code": "000001"}, {"code": "000002"}]
    sleeps = []
    seen = []
    monkeypatch.setattr(analyzer_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        analyzer,
        "analyze",
        lambda context: seen.append(context["code"])
        or AnalysisResult(context["code"], context["code"], 50, "flat", "hold"),
    )

    assert analyzer._format_volume(None) == "N/A"
    assert analyzer._format_amount(None) == "N/A"
    assert analyzer._format_volume(150000000).startswith("1.50")
    assert analyzer._format_amount(250000000).startswith("2.50")

    results = analyzer.batch_analyze(contexts, delay_between=1.25)

    assert [result.code for result in results] == ["000001", "000002"]
    assert sleeps == [1.25]
    assert seen == ["000001", "000002"]
