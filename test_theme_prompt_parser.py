from prompts.theme_discovery import build_theme_discovery_prompt, parse_theme_discovery_response


def test_theme_prompt_requires_evidence_ids_and_unsupported_claims():
    prompt = build_theme_discovery_prompt(
        [{"id": "news_001", "source": "unit", "title": "AI政策", "summary": "policy", "related_sectors": ["AI应用"]}],
        [{"name": "AI应用", "sector_type": "concept", "change_pct": 3.5}],
        {"market_status": "强势"},
        theme_count=3,
    )

    assert "evidence_ids" in prompt
    assert "unsupported_claims" in prompt
    assert "news_001" in prompt


def test_parse_theme_discovery_response_filters_unbacked_themes_and_downgrades():
    response = """
    ```json
    {
      "themes": [
        {
          "name": "AI应用端扩散",
          "confidence": "高",
          "related_sectors": ["AI应用", "不存在板块"],
          "catalysts": ["政策"],
          "risks": [],
          "evidence_ids": ["news_001", "bad_id"],
          "unsupported_claims": ["无证据订单"],
          "news_score": 20
        },
        {
          "name": "无证据主题",
          "confidence": "中",
          "related_sectors": ["AI应用"],
          "catalysts": [],
          "risks": [],
          "evidence_ids": [],
          "unsupported_claims": []
        }
      ]
    }
    ```
    """

    parsed = parse_theme_discovery_response(response, {"news_001"}, ["AI应用"])

    assert len(parsed) == 1
    assert parsed[0]["confidence"] == "中"
    assert parsed[0]["related_sectors"] == ["AI应用"]
    assert parsed[0]["evidence_ids"] == ["news_001"]
    assert "unsupported_claims" in parsed[0]["risks"][0]
