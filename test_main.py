import logging
from types import SimpleNamespace

import pytest

import main as main_module
from data_provider.akshare_fetcher import ChipDistribution, RealtimeQuote


def test_setup_logging_adds_console_and_file_handlers(tmp_path):
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)

    try:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        main_module.setup_logging(debug=True, log_dir=str(tmp_path))

        assert len(root_logger.handlers) == 3
        assert any(handler.level == logging.DEBUG for handler in root_logger.handlers)
        assert list(tmp_path.glob("stock_analysis_*.log"))
        assert list(tmp_path.glob("stock_analysis_debug_*.log"))
    finally:
        for handler in list(root_logger.handlers):
            handler.close()
            root_logger.removeHandler(handler)
        for handler in original_handlers:
            root_logger.addHandler(handler)


def test_pipeline_fetch_and_save_uses_cache_and_persists_new_data():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)

    class FakeDb:
        def __init__(self):
            self.has_today = True
            self.saved = []

        def has_today_data(self, code, today=None):
            return self.has_today

        def save_daily_data(self, df, code, source):
            self.saved.append((df, code, source))
            return len(df)

    class FakeFetcherManager:
        def __init__(self):
            self.calls = []

        def get_daily_data(self, code, days=250):
            self.calls.append((code, days))
            return main_module.pd.DataFrame({"close": [10, 11]}), "fake"

    pipeline.db = FakeDb()
    pipeline.fetcher_manager = FakeFetcherManager()

    assert pipeline.fetch_and_save_stock_data("000001") == (True, None)
    assert pipeline.fetcher_manager.calls == []

    pipeline.db.has_today = False
    assert pipeline.fetch_and_save_stock_data("000001") == (True, None)
    assert pipeline.fetcher_manager.calls == [("000001", 250)]
    assert pipeline.db.saved[0][1:] == ("000001", "fake")


def test_pipeline_enhances_context_with_market_realtime_chip_and_company_data():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    realtime = RealtimeQuote(
        code="000001",
        name="Alpha",
        price=10.5,
        volume_ratio=2.5,
        turnover_rate=4.1,
        pe_ratio=12.3,
        pb_ratio=1.5,
        total_mv=100,
        circ_mv=80,
        change_60d=9.0,
    )
    chip = ChipDistribution(
        code="000001",
        profit_ratio=0.75,
        avg_cost=9.5,
        concentration_90=0.12,
        concentration_70=0.08,
    )
    company = SimpleNamespace(to_dict=lambda: {"risk_flags": ["risk"]}, format_context=lambda: "company context")

    enhanced = pipeline._enhance_context(
        {"raw_data": []},
        realtime,
        chip,
        company,
        trend_result=None,
        stock_name="Alpha",
        market_context={"environment": {"market_score": 60}},
    )

    assert enhanced["stock_name"] == "Alpha"
    assert enhanced["market_context"]["environment"]["market_score"] == 60
    assert enhanced["realtime"]["volume_ratio_desc"] == pipeline._describe_volume_ratio(2.5)
    assert enhanced["chip"]["chip_status"]
    assert enhanced["company_intel_context"] == "company context"
    assert len({pipeline._describe_volume_ratio(value) for value in [0.3, 0.6, 1.0, 1.5, 2.5, 3.5]}) == 6


def test_pipeline_enhances_context_with_full_trend_result():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)

    class EnumValue:
        def __init__(self, value):
            self.value = value

    trend = SimpleNamespace(
        instrument_type=EnumValue("stock"),
        strategy_profile="trend",
        strategy_notes=["note"],
        trend_status=EnumValue("bullish"),
        ma_alignment="long",
        trend_strength=80,
        bias_ma5=1.1,
        bias_ma10=2.2,
        bias_ma20=3.3,
        ma60_trend="up",
        price_vs_ma60=5.5,
        ma60_slope=0.6,
        medium_trend_risk="low",
        current_price=10.0,
        ma5=9.8,
        ma10=9.5,
        ma20=9.0,
        ma60=8.5,
        support_ma5=True,
        support_ma10=True,
        ma5_touch_reclaim=True,
        ma10_touch_reclaim=False,
        bullish_candle=True,
        lower_shadow_ratio=0.2,
        ma5_hold_days=3,
        ma10_hold_days=5,
        ma20_breakdown=False,
        support_confirmation="confirmed",
        support_levels=[9.5],
        resistance_levels=[11.0],
        pattern_signal="platform",
        breakout_status="valid",
        breakout_level=10.8,
        breakout_score=75,
        breakout_valid=True,
        breakout_extension_threshold=12.0,
        new_high_20d=True,
        volume_breakout=True,
        platform_breakout=True,
        ma_compression_breakout=False,
        limit_up_pullback=False,
        breakout_retest_valid=True,
        trend_acceleration="steady",
        breakout_reasons=["volume"],
        breakout_risks=["extended"],
        volume_status=EnumValue("expanding"),
        volume_trend="rising",
        atr_20=0.4,
        atr_pct=4.0,
        volatility_20d=3.0,
        adaptive_bias_threshold=6.0,
        adaptive_support_tolerance=2.0,
        relative_strength_period=20,
        stock_return_20d=12.0,
        benchmark_return_20d=3.0,
        sector_return_20d=5.0,
        stock_vs_benchmark=9.0,
        stock_vs_sector=7.0,
        sector_vs_benchmark=2.0,
        relative_strength_score=88,
        relative_strength_status="strong",
        relative_strength_summary="beats benchmark",
        sector_name="AI",
        buy_signal=EnumValue("buy"),
        signal_score=82,
        signal_reasons=["trend"],
        risk_factors=["gap"],
        ideal_buy=9.9,
        secondary_buy=9.6,
        stop_loss=9.0,
        take_profit=12.0,
        risk_reward_ratio=2.5,
        invalidation_condition="break 9",
        position_note="normal",
        base_position_pct=30,
        market_position_multiplier=0.8,
        risk_reward_position_multiplier=1.1,
        single_trade_risk_pct=1.0,
        max_position_by_risk_pct=40,
        final_position_pct=26,
    )
    realtime = RealtimeQuote(code="000001", name="Alpha", price=10.0)

    enhanced = pipeline._enhance_context(
        {"raw_data": []},
        realtime_quote=realtime,
        chip_data=None,
        company_intel=None,
        trend_result=trend,
        stock_name="",
        market_context=None,
    )

    assert enhanced["stock_name"] == "Alpha"
    assert enhanced["trend_analysis"]["instrument_type"] == "stock"
    assert enhanced["trend_analysis"]["buy_signal"] == "buy"
    assert enhanced["trend_analysis"]["final_position_pct"] == 26


def test_pipeline_market_context_and_benchmark_history_are_cached(monkeypatch):
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    pipeline._market_context = None
    pipeline._benchmark_history = None
    pipeline._benchmark_history_loaded = False

    market_calls = []

    class FakeOverview:
        def to_dict(self):
            return {"index": "ok"}

    class FakeMarketAnalyzer:
        def __init__(self, search_service=None, analyzer=None):
            market_calls.append((search_service, analyzer))

        def get_market_overview(self):
            return FakeOverview()

    class FakeAkshare:
        def __init__(self):
            self.calls = 0

        def get_index_daily_data(self, index_code, days=250):
            self.calls += 1
            return main_module.pd.DataFrame({"close": [1, 2]})

    monkeypatch.setattr(main_module, "MarketAnalyzer", FakeMarketAnalyzer)
    monkeypatch.setattr(
        main_module,
        "evaluate_market_environment",
        lambda overview: {"market_score": 80, "market_status": "good", "risk_level": "low"},
    )
    pipeline.akshare_fetcher = FakeAkshare()

    first_context = pipeline._get_market_context()
    second_context = pipeline._get_market_context()
    first_history = pipeline._get_benchmark_history()
    second_history = pipeline._get_benchmark_history()

    assert first_context is second_context
    assert first_context["overview"] == {"index": "ok"}
    assert first_context["environment"]["market_score"] == 80
    assert market_calls == [(None, None)]
    assert first_history is second_history
    assert pipeline.akshare_fetcher.calls == 1

    failing = object.__new__(main_module.StockAnalysisPipeline)
    failing._market_context = None
    failing._benchmark_history = "stale"
    failing._benchmark_history_loaded = False
    failing.akshare_fetcher = SimpleNamespace(get_index_daily_data=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_module, "MarketAnalyzer", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("no market")))

    assert failing._get_market_context()["environment"]["market_score"] == 50
    assert failing._get_benchmark_history() is None


def test_pipeline_process_single_stock_and_run_cover_success_dry_run_and_empty_paths():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    result = SimpleNamespace(code="000001", sentiment_score=90, operation_advice="buy")
    calls = []

    pipeline.config = SimpleNamespace(stock_list=["000001"])
    pipeline.max_workers = 1
    pipeline.user_manager = SimpleNamespace(has_users=lambda: True, get_all_stocks=lambda: ["600519"])
    pipeline.db = SimpleNamespace(has_today_data=lambda code: code == "000001")
    pipeline._send_notifications = lambda results: calls.append(("notify", [item.code for item in results]))

    def process(code, skip_analysis=False):
        calls.append(("process", code, skip_analysis))
        return result if code == "000001" and not skip_analysis else None

    pipeline.process_single_stock = process

    assert pipeline.run(stock_codes=[], dry_run=False) == []
    assert pipeline.run(stock_codes=None, dry_run=False, send_notification=True) == [result]
    assert ("notify", ["000001"]) in calls
    dry_results = pipeline.run(stock_codes=["000001", "600519"], dry_run=True, send_notification=True)
    assert dry_results == []
    assert ("process", "000001", True) in calls

    single = object.__new__(main_module.StockAnalysisPipeline)
    single.fetch_and_save_stock_data = lambda code: (False, "fetch failed")
    single.analyze_stock = lambda code: result
    assert single.process_single_stock("000001") is result
    assert single.process_single_stock("000001", skip_analysis=True) is None

    exploding = object.__new__(main_module.StockAnalysisPipeline)
    exploding.fetch_and_save_stock_data = lambda code: (_ for _ in ()).throw(RuntimeError("boom"))
    assert exploding.process_single_stock("000001") is None


def test_pipeline_analyze_stock_happy_path_uses_realtime_trend_search_and_ai():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    calls = []
    result = SimpleNamespace(code="000001", sentiment_score=91)

    class EnumValue:
        def __init__(self, value):
            self.value = value

    trend = SimpleNamespace(
        trend_status=EnumValue("bullish"),
        buy_signal=EnumValue("buy"),
        signal_score=88,
        relative_strength_status="strong",
    )
    company = SimpleNamespace(announcements=[1, 2], risk_flags=[1])
    context = {"raw_data": [{"date": "2026-01-01", "close": 10, "volume": 100}]}

    pipeline.akshare_fetcher = SimpleNamespace(
        get_realtime_quote=lambda code: RealtimeQuote(code=code, name="Alpha", price=10.0, volume_ratio=1.5, turnover_rate=2.0),
        get_chip_distribution=lambda code: ChipDistribution(code=code, profit_ratio=0.8, concentration_90=0.1),
        get_stock_name=lambda code: "Fallback",
    )
    pipeline.company_intel_service = SimpleNamespace(
        get_company_intelligence=lambda code, name: calls.append(("company", code, name)) or company
    )
    pipeline.db = SimpleNamespace(get_analysis_context=lambda code: calls.append(("context", code)) or context)
    pipeline._get_benchmark_history = lambda: calls.append("benchmark") or main_module.pd.DataFrame({"close": [1, 2]})
    pipeline.trend_analyzer = SimpleNamespace(
        analyze=lambda df, code, benchmark_df=None, security_name="": calls.append(("trend", code, security_name)) or trend,
        apply_position_model=lambda trend_result, market_status="": calls.append(("position", market_status)),
    )
    pipeline.search_service = SimpleNamespace(
        is_available=True,
        search_comprehensive_intel=lambda stock_code, stock_name, max_searches=3: {
            "latest_news": SimpleNamespace(success=True, results=[1, 2]),
            "risk_check": SimpleNamespace(success=False, results=[]),
        },
        format_intel_report=lambda intel_results, stock_name: calls.append(("format", stock_name, sorted(intel_results))) or "news context",
    )
    pipeline._get_market_context = lambda: {"environment": {"market_status": "strong"}}
    pipeline._enhance_context = (
        lambda context_arg, realtime, chip, company_intel, trend_result, stock_name, market_context:
        calls.append(("enhance", realtime.name, chip.profit_ratio, stock_name, market_context["environment"]["market_status"]))
        or {"enhanced": True}
    )
    pipeline.analyzer = SimpleNamespace(
        analyze=lambda enhanced_context, news_context=None: calls.append(("ai", enhanced_context, news_context)) or result
    )

    assert pipeline.analyze_stock("000001") is result
    assert ("company", "000001", "Alpha") in calls
    assert ("trend", "000001", "Alpha") in calls
    assert ("position", "strong") in calls
    assert ("format", "Alpha", ["latest_news", "risk_check"]) in calls
    assert ("enhance", "Alpha", 0.8, "Alpha", "strong") in calls
    assert ("ai", {"enhanced": True}, "news context") in calls

    no_context = object.__new__(main_module.StockAnalysisPipeline)
    no_context.akshare_fetcher = SimpleNamespace(
        get_realtime_quote=lambda code: None,
        get_stock_name=lambda code: "",
        get_chip_distribution=lambda code: None,
    )
    no_context.company_intel_service = SimpleNamespace(
        get_company_intelligence=lambda code, name: (_ for _ in ()).throw(RuntimeError("intel unavailable"))
    )
    no_context.db = SimpleNamespace(get_analysis_context=lambda code: None)
    no_context.search_service = SimpleNamespace(is_available=False)
    assert no_context.analyze_stock("000404") is None


def test_pipeline_send_notifications_routes_channels_and_user_reports():
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    calls = []
    result_a = SimpleNamespace(code="000001")
    result_b = SimpleNamespace(code="600519")

    class FakeNotifier:
        def generate_dashboard_report(self, results):
            calls.append(("dashboard", [item.code for item in results]))
            return "report:" + ",".join(item.code for item in results)

        def save_report_to_file(self, report):
            calls.append(("save", report))
            return "saved.md"

        def is_available(self):
            return True

        def get_available_channels(self):
            return [
                main_module.NotificationChannel.WECHAT,
                main_module.NotificationChannel.FEISHU,
                main_module.NotificationChannel.TELEGRAM,
                main_module.NotificationChannel.EMAIL,
                main_module.NotificationChannel.CUSTOM,
                "unknown",
            ]

        def generate_wechat_dashboard(self, results):
            calls.append(("wechat-dashboard", len(results)))
            return "wechat report"

        def send_to_wechat(self, content):
            calls.append(("wechat", content))
            return False

        def send_to_feishu(self, report):
            calls.append(("feishu", report))
            return True

        def send_to_telegram(self, report):
            calls.append(("telegram", report))
            return False

        def send_to_email(self, report, receivers=None):
            calls.append(("email", report, receivers))
            return True

        def send_to_custom(self, report):
            calls.append(("custom", report))
            return False

    pipeline.notifier = FakeNotifier()
    pipeline.config = SimpleNamespace(email_receivers=["admin@example.com"])
    pipeline.user_manager = SimpleNamespace(
        has_users=lambda: True,
        get_users=lambda: [
            SimpleNamespace(name="Ann", email="ann@example.com", stocks=["000001"]),
            SimpleNamespace(name="Ben", email="ben@example.com", stocks=[]),
        ],
    )

    pipeline._send_notifications([result_a, result_b])

    assert ("wechat", "wechat report") in calls
    assert ("feishu", "report:000001,600519") in calls
    assert ("email", "report:000001", ["ann@example.com"]) in calls
    assert ("email", "report:000001,600519", None) in calls
    assert ("custom", "report:000001,600519") in calls

    unavailable = object.__new__(main_module.StockAnalysisPipeline)
    unavailable.notifier = SimpleNamespace(
        generate_dashboard_report=lambda results: "report",
        save_report_to_file=lambda report: "saved.md",
        is_available=lambda: False,
    )
    unavailable._send_notifications([result_a])


def test_pipeline_hot_sector_screening_runs_details_and_sends_report(monkeypatch):
    pipeline = object.__new__(main_module.StockAnalysisPipeline)
    calls = []
    detail = SimpleNamespace(code="000001")

    class FakeScreeningResult:
        def __init__(self):
            self.selected = [SimpleNamespace(code="000001"), SimpleNamespace(code="600519")]
            self.detailed_results = []
            self.candidates = [1, 2, 3]
            self.filtered = [1]

        def format_report(self):
            calls.append(("format", len(self.detailed_results)))
            return "screen report"

    class FakeScreener:
        def __init__(self, daily_fetcher=None, sector_fetcher=None, trend_analyzer=None):
            calls.append(("screener", daily_fetcher, sector_fetcher, trend_analyzer))

        def screen_hot_sectors(self, sector_count=5, top_n=3):
            calls.append(("screen", sector_count, top_n))
            return FakeScreeningResult()

    class FakeNotifier:
        def save_report_to_file(self, report, filename):
            calls.append(("save", report, filename))
            return "screen.md"

        def is_available(self):
            return True

        def send(self, report):
            calls.append(("send", report))
            return True

    monkeypatch.setattr(main_module, "StockScreener", FakeScreener)
    pipeline.fetcher_manager = "daily"
    pipeline.akshare_fetcher = "sector"
    pipeline.trend_analyzer = "trend"
    pipeline.notifier = FakeNotifier()
    pipeline.process_single_stock = lambda code, skip_analysis=False: detail if code == "000001" else None

    screening_result = pipeline.run_hot_sector_screening(top_n=2, sector_count=4, run_llm=True, send_notification=True)

    assert screening_result.detailed_results == [detail]
    assert ("screen", 4, 2) in calls
    assert ("send", "screen report") in calls


def test_main_dispatches_normal_screen_market_and_schedule_modes(monkeypatch):
    calls = []

    def make_args(**overrides):
        values = {
            "debug": False,
            "dry_run": False,
            "stocks": "000001, 600519",
            "no_notify": False,
            "workers": 2,
            "screen_hot_sectors": False,
            "screen_top_n": 2,
            "screen_sector_count": 4,
            "screen_no_llm": False,
            "market_review": False,
            "schedule": False,
            "no_market_review": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    config = SimpleNamespace(
        log_dir="logs",
        validate=lambda: ["config warning"],
        schedule_enabled=False,
        schedule_time="09:30",
        tavily_api_keys=[],
        serpapi_keys=[],
        openai_api_key="",
        openai_base_url="",
        openai_model="",
        market_review_enabled=False,
        email_receivers=[],
    )

    monkeypatch.setattr(main_module, "get_config", lambda: config)
    monkeypatch.setattr(main_module, "setup_logging", lambda debug=False, log_dir="": calls.append(("logging", debug, log_dir)))
    monkeypatch.setattr(
        main_module,
        "run_full_analysis",
        lambda config_arg, args_arg, stock_codes=None: calls.append(("full", args_arg.schedule, stock_codes)),
    )

    monkeypatch.setattr(main_module, "parse_arguments", lambda: make_args())
    assert main_module.main() == 0
    assert ("full", False, ["000001", "600519"]) in calls

    class FakePipeline:
        def __init__(self, config, max_workers=None):
            calls.append(("pipeline", max_workers))

        def run_hot_sector_screening(self, **kwargs):
            calls.append(("screen", kwargs))

    monkeypatch.setattr(main_module, "StockAnalysisPipeline", FakePipeline)
    monkeypatch.setattr(main_module, "parse_arguments", lambda: make_args(screen_hot_sectors=True, dry_run=True, no_notify=True))
    assert main_module.main() == 0
    assert ("screen", {"top_n": 2, "sector_count": 4, "run_llm": False, "send_notification": False}) in calls

    config.tavily_api_keys = ["tk"]
    config.openai_api_key = "key"
    config.openai_base_url = "https://api.example"
    config.openai_model = "model"
    monkeypatch.setattr(main_module, "NotificationService", lambda: calls.append("notifier") or "notifier")
    monkeypatch.setattr(main_module, "SearchService", lambda tavily_keys=None, serpapi_keys=None: calls.append(("search", tavily_keys, serpapi_keys)) or "search")
    monkeypatch.setattr(main_module, "OpenAIAnalyzer", lambda: calls.append("analyzer") or "analyzer")
    monkeypatch.setattr(
        main_module,
        "run_market_review",
        lambda notifier, analyzer, search_service, send_notification=True: calls.append(
            ("market", notifier, analyzer, search_service, send_notification)
        ),
    )
    monkeypatch.setattr(main_module, "parse_arguments", lambda: make_args(market_review=True, no_notify=True))
    assert main_module.main() == 0
    assert ("market", "notifier", "analyzer", "search", False) in calls

    monkeypatch.setattr(
        "scheduler.run_with_schedule",
        lambda task, schedule_time, run_immediately=True: calls.append(("schedule", schedule_time, run_immediately)) or task(),
    )
    monkeypatch.setattr(main_module, "parse_arguments", lambda: make_args(schedule=True))
    assert main_module.main() == 0
    assert ("schedule", "09:30", True) in calls
    assert ("full", True, ["000001", "600519"]) in calls

    monkeypatch.setattr(
        main_module,
        "run_full_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(main_module, "parse_arguments", lambda: make_args())
    assert main_module.main() == 130


def test_run_market_review_saves_and_sends_report(monkeypatch):
    class FakeMarketAnalyzer:
        def __init__(self, search_service=None, analyzer=None):
            self.search_service = search_service
            self.analyzer = analyzer

        def run_daily_review(self):
            return "review body"

    class FakeNotifier:
        def __init__(self):
            self.saved = []
            self.sent = []

        def save_report_to_file(self, content, filename):
            self.saved.append((content, filename))
            return "saved.md"

        def is_available(self):
            return True

        def send(self, content):
            self.sent.append(content)
            return True

    monkeypatch.setattr(main_module, "MarketAnalyzer", FakeMarketAnalyzer)
    notifier = FakeNotifier()

    report = main_module.run_market_review(notifier, analyzer="analyzer", search_service="search")

    assert report == "review body"
    assert notifier.saved[0][1].startswith("market_review_")
    assert notifier.sent[0].endswith("\n\nreview body")


def test_parse_arguments_handles_common_modes(monkeypatch):
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        [
            "main.py",
            "--debug",
            "--dry-run",
            "--stocks",
            "000001,600519",
            "--no-notify",
            "--workers",
            "3",
            "--screen-hot-sectors",
            "--screen-top-n",
            "2",
            "--screen-sector-count",
            "4",
            "--screen-no-llm",
        ],
    )

    args = main_module.parse_arguments()

    assert args.debug is True
    assert args.dry_run is True
    assert args.stocks == "000001,600519"
    assert args.no_notify is True
    assert args.workers == 3
    assert args.screen_hot_sectors is True
    assert args.screen_top_n == 2
    assert args.screen_sector_count == 4
    assert args.screen_no_llm is True


def test_run_full_analysis_delegates_pipeline_market_review_and_feishu(monkeypatch):
    calls = []
    result = SimpleNamespace(
        code="000001",
        name="Alpha",
        sentiment_score=88,
        trend_prediction="up",
        operation_advice="buy",
        get_emoji=lambda: "B",
    )

    class FakeNotifier:
        def __init__(self):
            self.sent = []

        def generate_dashboard_report(self, results):
            calls.append(("dashboard", [item.code for item in results]))
            return "dashboard report"

        def send(self, content):
            self.sent.append(content)
            calls.append(("send", content))
            return True

    class FakePipeline:
        def __init__(self, config, max_workers=None):
            self.config = config
            self.max_workers = max_workers
            self.notifier = FakeNotifier()
            self.analyzer = "analyzer"
            self.search_service = "search"
            calls.append(("pipeline", max_workers))

        def run(self, stock_codes=None, dry_run=False, send_notification=True):
            calls.append(("run", stock_codes, dry_run, send_notification))
            return [result]

    class FakeFeishuDoc:
        def is_configured(self):
            return True

        def create_daily_doc(self, title, content):
            calls.append(("feishu", title, content))
            return "https://feishu.example/doc"

    monkeypatch.setattr(main_module, "StockAnalysisPipeline", FakePipeline)
    monkeypatch.setattr(main_module, "run_market_review", lambda **kwargs: calls.append(("market", kwargs)) or "market report")
    monkeypatch.setattr(main_module, "FeishuDocManager", lambda: FakeFeishuDoc())

    config = SimpleNamespace(market_review_enabled=True, email_receivers=["admin@example.com"])
    args = SimpleNamespace(workers=2, dry_run=False, no_notify=False, no_market_review=False)

    main_module.run_full_analysis(config, args, stock_codes=["000001"])

    assert ("pipeline", 2) in calls
    assert ("run", ["000001"], False, True) in calls
    assert any(call[0] == "market" for call in calls)
    assert any(call[0] == "feishu" and "market report" in call[2] for call in calls)
