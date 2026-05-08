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
