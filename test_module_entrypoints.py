import runpy
import pathlib
from pathlib import Path
from types import SimpleNamespace

import akshare as ak
import config as config_module
import pandas as pd


def test_local_demo_entrypoints_run_without_external_services(monkeypatch, capsys, tmp_path):
    repo = Path(__file__).resolve().parent

    cleared_keys = [
        "STOCK_LIST",
        "TUSHARE_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "TAVILY_API_KEYS",
        "SERPAPI_API_KEYS",
        "WECHAT_WEBHOOK_URL",
        "FEISHU_WEBHOOK_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "EMAIL_SENDER",
        "EMAIL_PASSWORD",
        "EMAIL_RECEIVERS",
        "CUSTOM_WEBHOOK_URLS",
    ]
    for key in cleared_keys:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stock_analysis.db"))

    config_module.Config.reset_instance()
    config_ns = runpy.run_path(str(repo / "config.py"), run_name="__main__")
    db_url = config_ns["Config"](database_path=str(tmp_path / "nested" / "stock.db")).get_db_url()
    assert db_url.startswith("sqlite:///")
    assert (tmp_path / "nested").exists()

    fake_config = SimpleNamespace(
        openai_api_key="",
        openai_base_url="",
        openai_model="",
        llm_request_delay=0,
        llm_max_retries=1,
        llm_retry_delay=0,
    )
    monkeypatch.setattr(config_module, "get_config", lambda: fake_config)

    runpy.run_path(str(repo / "analyzer.py"), run_name="__main__")
    runpy.run_path(str(repo / "stock_analyzer.py"), run_name="__main__")

    output = capsys.readouterr().out
    assert "sqlite" in db_url
    assert "000001" in output
    assert output


def test_notification_demo_entrypoint_writes_report_to_tmp_path(monkeypatch, capsys, tmp_path):
    repo = Path(__file__).resolve().parent
    for key in [
        "WECHAT_WEBHOOK_URL",
        "FEISHU_WEBHOOK_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "EMAIL_SENDER",
        "EMAIL_PASSWORD",
        "EMAIL_RECEIVERS",
        "CUSTOM_WEBHOOK_URLS",
    ]:
        monkeypatch.setenv(key, "")
    config_module.Config.reset_instance()

    original_path = pathlib.Path

    def redirected_path(value="."):
        if str(value).endswith("notification.py"):
            return tmp_path / "notification.py"
        return original_path(value)

    monkeypatch.setattr(pathlib, "Path", redirected_path)

    runpy.run_path(str(repo / "notification.py"), run_name="__main__")

    output = capsys.readouterr().out
    reports = list((tmp_path / "reports").glob("report_*.md"))
    assert reports
    assert "===" in output


def test_market_analyzer_demo_entrypoint_uses_mocked_akshare(monkeypatch, capsys):
    repo = Path(__file__).resolve().parent
    col_code = "\u4ee3\u7801"
    col_price = "\u6700\u65b0\u4ef7"
    col_change_amount = "\u6da8\u8dcc\u989d"
    col_change = "\u6da8\u8dcc\u5e45"
    col_open_today = "\u4eca\u5f00"
    col_high = "\u6700\u9ad8"
    col_low = "\u6700\u4f4e"
    col_prev_close = "\u6628\u6536"
    col_volume = "\u6210\u4ea4\u91cf"
    col_amount = "\u6210\u4ea4\u989d"
    col_sector_name = "\u677f\u5757\u540d\u79f0"
    col_today_net_buy = "\u4eca\u65e5\u51c0\u4e70\u989d"

    monkeypatch.setattr(
        ak,
        "stock_zh_index_spot_em",
        lambda: pd.DataFrame(
            {
                col_code: ["000001", "399001", "399006", "000688", "000016", "000300"],
                col_price: [3000, 10000, 2200, 900, 2500, 3600],
                col_change_amount: [10, 20, -5, 1, 3, 8],
                col_change: [0.5, 1.2, -0.3, 0.1, 0.2, 0.4],
                col_open_today: [2990, 9900, 2210, 899, 2490, 3590],
                col_high: [3010, 10100, 2220, 910, 2510, 3610],
                col_low: [2980, 9800, 2180, 890, 2480, 3580],
                col_prev_close: [2990, 9980, 2205, 899, 2497, 3592],
                col_volume: [100, 200, 300, 400, 500, 600],
                col_amount: [1e8, 2e8, 3e8, 4e8, 5e8, 6e8],
            }
        ),
    )
    monkeypatch.setattr(
        ak,
        "stock_zh_a_spot_em",
        lambda: pd.DataFrame({col_change: [10.0, -10.0, 0.0, 2.0], col_amount: [1e8, 2e8, 3e8, 4e8]}),
    )
    monkeypatch.setattr(
        ak,
        "stock_board_industry_name_em",
        lambda: pd.DataFrame({col_sector_name: ["Tech", "Banks", "Energy"], col_change: [3.0, -2.0, 1.0]}),
    )
    monkeypatch.setattr(
        ak,
        "stock_hsgt_north_net_flow_in_em",
        lambda symbol=None: pd.DataFrame({col_today_net_buy: [3e8]}),
        raising=False,
    )

    runpy.run_path(str(repo / "market_analyzer.py"), run_name="__main__")

    output = capsys.readouterr().out
    assert "3000.00" in output
    assert "Tech" in output
