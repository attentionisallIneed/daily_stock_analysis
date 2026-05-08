import config as config_module
from config import Config, get_config


def test_config_loads_typed_values_from_environment(monkeypatch):
    Config.reset_instance()
    monkeypatch.setattr(config_module, "load_dotenv", lambda dotenv_path: None)
    env = {
        "STOCK_LIST": "000001, 600519, ,300750",
        "FEISHU_APP_ID": "app",
        "FEISHU_APP_SECRET": "secret",
        "FEISHU_FOLDER_TOKEN": "folder",
        "TUSHARE_TOKEN": "token",
        "OPENAI_API_KEY": "key",
        "OPENAI_BASE_URL": "https://example.com/v1",
        "OPENAI_MODEL": "model",
        "LLM_REQUEST_DELAY": "0.5",
        "LLM_MAX_RETRIES": "2",
        "LLM_RETRY_DELAY": "1.5",
        "GEMINI_API_KEY": "gemini-key",
        "GEMINI_MODEL": "gemini-model",
        "GEMINI_MODEL_FALLBACK": "gemini-fallback",
        "GEMINI_REQUEST_DELAY": "0.7",
        "GEMINI_MAX_RETRIES": "4",
        "GEMINI_RETRY_DELAY": "2.5",
        "TAVILY_API_KEYS": "t1, t2",
        "SERPAPI_API_KEYS": "s1, s2",
        "WECHAT_WEBHOOK_URL": "https://wechat.example",
        "FEISHU_WEBHOOK_URL": "https://feishu.example",
        "TELEGRAM_BOT_TOKEN": "bot",
        "TELEGRAM_CHAT_ID": "chat",
        "EMAIL_SENDER": "sender@example.com",
        "EMAIL_PASSWORD": "password",
        "EMAIL_RECEIVERS": "a@example.com, b@example.com",
        "CUSTOM_WEBHOOK_URLS": "https://custom.example, https://custom2.example",
        "FEISHU_MAX_BYTES": "12345",
        "WECHAT_MAX_BYTES": "2345",
        "DATABASE_PATH": "./custom.db",
        "LOG_DIR": "./custom-logs",
        "LOG_LEVEL": "DEBUG",
        "MAX_WORKERS": "7",
        "DEBUG": "true",
        "SCHEDULE_ENABLED": "true",
        "SCHEDULE_TIME": "09:30",
        "MARKET_REVIEW_ENABLED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    config = Config.get_instance()

    assert get_config() is config
    assert config.stock_list == ["000001", "600519", "300750"]
    assert config.tavily_api_keys == ["t1", "t2"]
    assert config.serpapi_keys == ["s1", "s2"]
    assert config.email_receivers == ["a@example.com", "b@example.com"]
    assert config.custom_webhook_urls == ["https://custom.example", "https://custom2.example"]
    assert config.llm_request_delay == 0.5
    assert config.llm_max_retries == 2
    assert config.feishu_max_bytes == 12345
    assert config.max_workers == 7
    assert config.debug is True
    assert config.schedule_enabled is True
    assert config.market_review_enabled is False


def test_config_validate_reports_missing_and_accepts_complete_config():
    missing = Config()
    warnings = missing.validate()

    assert len(warnings) >= 6

    complete = Config(
        stock_list=["000001"],
        tushare_token="token",
        openai_api_key="key",
        openai_base_url="https://example.com/v1",
        openai_model="model",
        tavily_api_keys=["tavily"],
        wechat_webhook_url="https://wechat.example",
    )

    assert complete.validate() == []


def test_get_db_url_creates_parent_directory(tmp_path):
    config = Config(database_path=str(tmp_path / "nested" / "stocks.db"))

    url = config.get_db_url()

    assert url.startswith("sqlite:///")
    assert (tmp_path / "nested").is_dir()
