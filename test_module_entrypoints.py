import runpy
import pathlib
from pathlib import Path
from types import SimpleNamespace

import config as config_module


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
