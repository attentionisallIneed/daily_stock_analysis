from datetime import date, timedelta

import pandas as pd
import pytest

from storage import DatabaseManager, StockDaily


@pytest.fixture
def db():
    DatabaseManager.reset_instance()
    manager = DatabaseManager("sqlite:///:memory:")
    yield manager
    DatabaseManager.reset_instance()


def _daily_frame(rows):
    return pd.DataFrame(rows)


def test_stock_daily_to_dict_includes_market_fields():
    row_date = date(2026, 1, 2)
    record = StockDaily(
        code="000001",
        date=row_date,
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume=1000,
        amount=10500,
        pct_chg=1.2,
        ma5=10.1,
        ma10=10.0,
        ma20=9.8,
        volume_ratio=1.5,
        data_source="unit",
    )

    assert repr(record) == "<StockDaily(code=000001, date=2026-01-02, close=10.5)>"
    assert record.to_dict() == {
        "code": "000001",
        "date": row_date,
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10.5,
        "volume": 1000,
        "amount": 10500,
        "pct_chg": 1.2,
        "ma5": 10.1,
        "ma10": 10.0,
        "ma20": 9.8,
        "volume_ratio": 1.5,
        "data_source": "unit",
    }


def test_database_manager_saves_updates_and_queries_daily_data(db):
    today = date.today()
    yesterday = today - timedelta(days=1)
    rows = _daily_frame(
        [
            {
                "date": yesterday.isoformat(),
                "open": 9.5,
                "high": 10.5,
                "low": 9.0,
                "close": 10.0,
                "volume": 100,
                "amount": 1000,
                "pct_chg": 0.5,
                "ma5": 9.8,
                "ma10": 9.6,
                "ma20": 9.4,
                "volume_ratio": 1.0,
            },
            {
                "date": pd.Timestamp(today),
                "open": 10.5,
                "high": 12.0,
                "low": 10.0,
                "close": 11.0,
                "volume": 250,
                "amount": 2750,
                "pct_chg": 10.0,
                "ma5": 10.5,
                "ma10": 10.0,
                "ma20": 9.5,
                "volume_ratio": 2.5,
            },
        ]
    )

    assert db.save_daily_data(rows, "000001", "unit") == 2
    assert db.has_today_data("000001", today) is True
    assert db.has_today_data("000002", today) is False

    latest = db.get_latest_data("000001", days=2)
    assert [item.date for item in latest] == [today, yesterday]

    ranged = db.get_data_range("000001", yesterday, today)
    assert [item.date for item in ranged] == [yesterday, today]

    update = _daily_frame(
        [
            {
                "date": today.isoformat(),
                "open": 10.5,
                "high": 12.5,
                "low": 10.0,
                "close": 12.0,
                "volume": 300,
                "amount": 3600,
                "pct_chg": 12.0,
                "ma5": 11.0,
                "ma10": 10.5,
                "ma20": 10.0,
                "volume_ratio": 3.0,
            }
        ]
    )
    assert db.save_daily_data(update, "000001", "updated") == 0
    assert db.get_latest_data("000001", days=1)[0].close == 12.0


def test_database_manager_builds_analysis_context_with_recent_and_raw_data(db):
    today = date.today()
    rows = []
    for offset in range(3):
        row_date = today - timedelta(days=2 - offset)
        rows.append(
            {
                "date": row_date,
                "open": 10 + offset,
                "high": 11 + offset,
                "low": 9 + offset,
                "close": 10 + offset,
                "volume": 100 * (offset + 1),
                "amount": 1000 * (offset + 1),
                "pct_chg": offset,
                "ma5": 9 + offset,
                "ma10": 8 + offset,
                "ma20": 7 + offset,
                "volume_ratio": 1 + offset,
            }
        )
    db.save_daily_data(_daily_frame(rows), "000001", "unit")

    context = db.get_analysis_context("000001", target_date=today)

    assert context["code"] == "000001"
    assert context["date"] == today.isoformat()
    assert context["today"]["close"] == 12
    assert context["yesterday"]["close"] == 11
    assert context["volume_change_ratio"] == 1.5
    assert context["price_change_ratio"] == 9.09
    assert len(context["raw_data"]) == 3
    assert context["raw_data"][0]["date"] == today - timedelta(days=2)
    assert context["ma_status"]


def test_database_manager_handles_empty_inputs_and_missing_context(db):
    assert db.save_daily_data(pd.DataFrame(), "000001", "unit") == 0
    assert db.save_daily_data(None, "000001", "unit") == 0
    assert db.get_analysis_context("000001") is None
