from types import SimpleNamespace

import notification
from analyzer import AnalysisResult
from notification import ChannelDetector, NotificationBuilder, NotificationChannel, NotificationService


BUY = "涔板叆"
HOLD = "瑙傛湜"
SELL = "鍗栧嚭"


def _service(**overrides):
    service = object.__new__(NotificationService)
    service._wechat_url = None
    service._feishu_url = None
    service._telegram_config = {"bot_token": None, "chat_id": None}
    service._email_config = {"sender": None, "password": None, "receivers": []}
    service._custom_webhook_urls = []
    service._wechat_max_bytes = 4000
    service._feishu_max_bytes = 20000
    service._available_channels = []
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def _result(**overrides):
    result = AnalysisResult(
        code="000001",
        name="Alpha",
        sentiment_score=72,
        trend_prediction="up",
        operation_advice=BUY,
        confidence_level="high",
        dashboard=None,
        trend_analysis="trend",
        short_term_outlook="short outlook",
        medium_term_outlook="medium outlook",
        technical_analysis="technical",
        ma_analysis="ma",
        volume_analysis="volume",
        pattern_analysis="pattern",
        fundamental_analysis="fundamental",
        sector_position="leader",
        company_highlights="highlight",
        news_summary="news",
        market_sentiment="sentiment",
        hot_topics="topic",
        analysis_summary="summary",
        key_points="key point",
        risk_warning="risk",
        buy_reason="reason",
        search_performed=True,
        data_sources="DataFeed",
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _dashboard():
    return {
        "intelligence": {
            "sentiment_summary": "positive sentiment",
            "earnings_outlook": "better earnings",
            "risk_alerts": ["risk one", "risk two"],
            "positive_catalysts": ["catalyst one", "catalyst two"],
            "latest_news": "latest update",
        },
        "core_conclusion": {
            "one_sentence": "Buy the pullback",
            "time_sensitivity": "this week",
            "position_advice": {"no_position": "wait for entry", "has_position": "hold"},
        },
        "data_perspective": {
            "trend_status": {"is_bullish": True, "ma_alignment": "bullish", "trend_score": 82},
            "price_position": {
                "current_price": 10.2,
                "ma5": 10.0,
                "ma10": 9.8,
                "ma20": 9.5,
                "bias_ma5": 2.0,
                "bias_status": "safe",
                "support_level": 9.8,
                "resistance_level": 11.0,
            },
            "volume_analysis": {"volume_ratio": 1.6, "volume_status": "active", "turnover_rate": 4.2, "volume_meaning": "healthy"},
            "chip_structure": {"profit_ratio": "70%", "avg_cost": 9.7, "concentration": "tight", "chip_health": "healthy"},
        },
        "battle_plan": {
            "sniper_points": {"ideal_buy": "10.0", "secondary_buy": "9.8", "stop_loss": "9.3", "take_profit": "11.2"},
            "position_strategy": {"suggested_position": "30%", "entry_plan": "scale in", "risk_control": "strict stop"},
            "action_checklist": ["safe trend", "risk reviewed"],
        },
    }


def test_notification_service_detects_all_configured_channels(monkeypatch):
    config = SimpleNamespace(
        wechat_webhook_url="https://wechat.example/hook",
        feishu_webhook_url="https://feishu.example/hook",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        email_sender="sender@example.com",
        email_password="secret",
        email_receivers=[],
        custom_webhook_urls=["https://hooks.slack.com/services/test"],
        feishu_max_bytes=123,
        wechat_max_bytes=456,
    )
    monkeypatch.setattr(notification, "get_config", lambda: config)

    service = NotificationService()

    assert service.is_available() is True
    assert service.get_available_channels() == [
        NotificationChannel.WECHAT,
        NotificationChannel.FEISHU,
        NotificationChannel.TELEGRAM,
        NotificationChannel.EMAIL,
        NotificationChannel.CUSTOM,
    ]
    assert service._email_config["receivers"] == ["sender@example.com"]
    assert ChannelDetector.get_channel_name(NotificationChannel.UNKNOWN)


def test_signal_levels_cover_score_thresholds():
    service = _service()

    labels = [
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=85)),
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=70)),
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=60)),
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=50)),
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=40)),
        service._get_signal_level(SimpleNamespace(operation_advice="", sentiment_score=30)),
    ]

    assert len({label[2] for label in labels}) == 6


def test_generates_daily_dashboard_and_wechat_reports():
    service = _service()
    rich = _result(dashboard=_dashboard())
    failed = _result(code="000002", name="Beta", sentiment_score=31, operation_advice=SELL, success=False, error_message="bad data")

    daily = service.generate_daily_report([failed, rich], report_date="2026-05-08")
    dashboard = service.generate_dashboard_report([rich], report_date="2026-05-08")
    wechat_dashboard = service.generate_wechat_dashboard([rich])
    wechat_summary = service.generate_wechat_summary([rich])

    assert "Alpha" in daily
    assert "Beta" in daily
    assert "bad data" in daily
    assert "Buy the pullback" in dashboard
    assert "catalyst one" in dashboard
    assert "Alpha" in wechat_dashboard
    assert "reason" in wechat_summary


def test_format_converters_and_custom_payloads():
    service = _service()

    html = service._markdown_to_html("# Title\n\n**bold**\n- item\n> quote\n---")
    telegram = service._convert_to_telegram_markdown("# Title\n**bold** [link](url)")

    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "Title" in telegram
    assert "*bold*" in telegram
    assert "\\[link\\]" in telegram
    assert service._build_custom_webhook_payload("https://oapi.dingtalk.com/robot/send", "content")["msgtype"] == "markdown"
    assert service._build_custom_webhook_payload("https://discord.com/api/webhooks/1", "x" * 2001)["content"].endswith("...")
    assert service._build_custom_webhook_payload("https://hooks.slack.com/services/T", "content")["mrkdwn"] is True
    assert service._build_custom_webhook_payload("https://api.day.app/key", "content")["group"] == "stock"
    assert service._build_custom_webhook_payload("https://example.com/hook", "content")["message"] == "content"


def test_send_dispatches_to_available_channels(monkeypatch):
    service = _service(
        _available_channels=[
            NotificationChannel.WECHAT,
            NotificationChannel.FEISHU,
            NotificationChannel.TELEGRAM,
            NotificationChannel.EMAIL,
            NotificationChannel.CUSTOM,
            NotificationChannel.UNKNOWN,
        ]
    )
    calls = []
    monkeypatch.setattr(service, "send_to_wechat", lambda content: calls.append(("wechat", content)) or True)
    monkeypatch.setattr(service, "send_to_feishu", lambda content: calls.append(("feishu", content)) or False)
    monkeypatch.setattr(service, "send_to_telegram", lambda content: calls.append(("telegram", content)) or True)
    monkeypatch.setattr(service, "send_to_email", lambda content: calls.append(("email", content)) or True)
    monkeypatch.setattr(service, "send_to_custom", lambda content: calls.append(("custom", content)) or False)

    assert service.send("message") is True
    assert [call[0] for call in calls] == ["wechat", "feishu", "telegram", "email", "custom"]


def test_chunk_helpers_truncate_and_route_messages(monkeypatch):
    service = _service()
    sent = []
    monkeypatch.setattr(service, "send", lambda content: sent.append(content) or True)

    assert service._truncate_to_bytes("abc", 10) == "abc"
    assert service._truncate_to_bytes("汉字abc", 5) == "汉"
    assert service._send_chunked_messages("a\n---\n" + "b" * 20 + "\n---\nc", max_length=15) is True
    assert len(sent) >= 2


def test_builder_helpers_and_daily_report_shortcut(monkeypatch, tmp_path):
    service = _service()
    saved = []
    sent = []

    class FakeService:
        def generate_daily_report(self, results):
            return "daily report"

        def save_report_to_file(self, report):
            saved.append(report)

        def send(self, report):
            sent.append(report)
            return True

    monkeypatch.setattr(notification, "get_notification_service", lambda: FakeService())
    monkeypatch.setattr(notification, "__file__", str(tmp_path / "notification.py"))

    path = service.save_report_to_file("content", filename="custom.md")
    alert = NotificationBuilder.build_simple_alert("Title", "Body", "warning")
    summary = NotificationBuilder.build_stock_summary([_result(), _result(name="Beta", sentiment_score=90)])

    assert path.endswith("custom.md")
    assert (tmp_path / "reports" / "custom.md").read_text(encoding="utf-8") == "content"
    assert "Title" in alert
    assert "Beta" in summary.splitlines()[2]
    assert notification.send_daily_report([_result()]) is True
    assert saved == ["daily report"]
    assert sent == ["daily report"]
