import pandas as pd
import pytest

from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager, STANDARD_COLUMNS


class FakeFetcher(BaseFetcher):
    name = "FakeFetcher"
    priority = 10

    def __init__(self, raw_df=None, *, priority=10, name="FakeFetcher", error=None):
        self.raw_df = raw_df
        self.priority = priority
        self.name = name
        self.error = error
        self.calls = []

    def _fetch_raw_data(self, stock_code, start_date, end_date):
        self.calls.append((stock_code, start_date, end_date))
        if self.error:
            raise self.error
        return self.raw_df.copy()

    def _normalize_data(self, df, stock_code):
        normalized = df.copy()
        normalized["code"] = stock_code
        keep_cols = ["code"] + STANDARD_COLUMNS
        return normalized[[column for column in keep_cols if column in normalized.columns]]


def test_base_fetcher_cleans_sorts_and_calculates_indicators():
    raw_df = pd.DataFrame(
        {
            "date": ["2026-01-03", "2026-01-01", "2026-01-02", "2026-01-04"],
            "open": ["12", "10", "11", "13"],
            "high": ["12.5", "10.5", "11.5", "13.5"],
            "low": ["11.5", "9.5", "10.5", "12.5"],
            "close": ["12", "10", "11", None],
            "volume": ["300", "100", "200", "400"],
            "amount": ["3600", "1000", "2200", "5200"],
            "pct_chg": ["2.0", "0.0", "1.0", "3.0"],
        }
    )
    fetcher = FakeFetcher(raw_df)

    result = fetcher.get_daily_data("000001", end_date="2026-01-05", days=2)

    assert fetcher.calls == [("000001", "2026-01-01", "2026-01-05")]
    assert result["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert result["close"].tolist() == [10, 11, 12]
    assert result["ma5"].tolist() == [10.0, 10.5, 11.0]
    assert result["ma10"].tolist() == [10.0, 10.5, 11.0]
    assert result["ma20"].tolist() == [10.0, 10.5, 11.0]
    assert result["volume_ratio"].tolist() == [1.0, 2.0, 2.0]


def test_base_fetcher_raises_data_fetch_error_for_empty_raw_data():
    fetcher = FakeFetcher(pd.DataFrame())

    with pytest.raises(DataFetchError) as excinfo:
        fetcher.get_daily_data("000001", start_date="2026-01-01", end_date="2026-01-05")

    assert "000001" in str(excinfo.value)


def test_data_fetcher_manager_orders_fetchers_and_fails_over():
    failing = FakeFetcher(
        pd.DataFrame(),
        priority=1,
        name="failing",
        error=RuntimeError("temporary outage"),
    )
    succeeding = FakeFetcher(
        pd.DataFrame(
            {
                "date": ["2026-01-01"],
                "open": [10],
                "high": [11],
                "low": [9],
                "close": [10],
                "volume": [100],
                "amount": [1000],
                "pct_chg": [0],
            }
        ),
        priority=2,
        name="succeeding",
    )

    manager = DataFetcherManager(fetchers=[succeeding, failing])
    result, source = manager.get_daily_data("000001", start_date="2026-01-01", end_date="2026-01-02")

    assert manager.available_fetchers == ["failing", "succeeding"]
    assert source == "succeeding"
    assert result.iloc[0]["code"] == "000001"
    assert failing.calls
    assert succeeding.calls


def test_data_fetcher_manager_reports_all_failures():
    first = FakeFetcher(pd.DataFrame(), priority=1, name="first", error=RuntimeError("first failed"))
    second = FakeFetcher(pd.DataFrame(), priority=2, name="second", error=RuntimeError("second failed"))
    manager = DataFetcherManager(fetchers=[first, second])

    with pytest.raises(DataFetchError) as excinfo:
        manager.get_daily_data("000001", start_date="2026-01-01", end_date="2026-01-02")

    message = str(excinfo.value)
    assert "first failed" in message
    assert "second failed" in message


def test_data_fetcher_manager_reports_empty_provider_results():
    class EmptyFetcher:
        def __init__(self, name, priority):
            self.name = name
            self.priority = priority
            self.calls = []

        def get_daily_data(self, **kwargs):
            self.calls.append(kwargs)
            return pd.DataFrame()

    first = EmptyFetcher("empty-first", 1)
    second = EmptyFetcher("empty-second", 2)
    manager = DataFetcherManager(fetchers=[first, second])

    with pytest.raises(DataFetchError) as excinfo:
        manager.get_daily_data("000001", start_date="2026-01-01", end_date="2026-01-02")

    message = str(excinfo.value)
    assert "empty-first" in message
    assert "empty-second" in message
    assert "返回空数据" in message
    assert first.calls
    assert second.calls
