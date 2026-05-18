import math

import pandas as pd

from backend.database import Base, engine
from backend.models.auction_backtest import StockAuctionOpen
from backend.models.seal_rate import StockDailyData
from backend.services.auction_data_service import (
    AuctionDataService,
    calculate_auction_metrics,
)


def test_calculate_auction_metrics_converts_tushare_units():
    metrics = calculate_auction_metrics(
        auction_vol=819000,
        previous_daily_vol=100000,
        float_share=9870,
    )

    assert metrics["auction_ratio"] == 8.19
    assert math.isclose(metrics["auction_turnover_rate"], 0.83, abs_tol=0.01)


def test_calculate_auction_metrics_prefers_free_share_for_auction_turnover():
    metrics = calculate_auction_metrics(
        auction_vol=819000,
        previous_daily_vol=100000,
        float_share=9870,
        free_share=5000,
    )

    assert metrics["auction_ratio"] == 8.19
    assert math.isclose(metrics["auction_turnover_rate"], 1.64, abs_tol=0.01)


def test_calculate_auction_metrics_degrades_when_denominator_missing():
    metrics = calculate_auction_metrics(
        auction_vol=819000,
        previous_daily_vol=0,
        float_share=None,
    )

    assert metrics["auction_ratio"] is None
    assert metrics["auction_turnover_rate"] is None


def test_sync_auction_open_upserts_without_duplicate_rows(db):
    Base.metadata.create_all(bind=engine)

    class FakeCollector:
        def get_trading_calendar(self):
            return {"20240509", "20240510"}

        def get_stk_auction_open(self, trade_date):
            assert trade_date == "20240510"
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "price": 10.5,
                        "vol": 819000,
                        "amount": 8600000,
                        "pre_close": 10.0,
                    }
                ]
            )

        def get_daily_data(self, trade_date=None, start_date=None, end_date=None, **kwargs):
            assert trade_date == "20240509"
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "vol": 100000,
                    }
                ]
            )

        def get_daily_basic(self, trade_date=None):
            assert trade_date == "20240510"
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "float_share": 9870,
                        "free_share": 5000,
                    }
                ]
            )

    service = AuctionDataService(collector=FakeCollector(), session_factory=lambda: db)

    assert service.sync_auction_open("20240510") == 1
    assert service.sync_auction_open("20240510") == 1

    rows = db.query(StockAuctionOpen).filter_by(trade_date="20240510", ts_code="000001.SZ").all()
    assert len(rows) == 1
    assert rows[0].source == "tushare_stk_auction"
    assert rows[0].auction_ratio == 8.19
    assert math.isclose(rows[0].auction_turnover_rate, 1.64, abs_tol=0.01)


def test_sync_auction_open_falls_back_to_previous_daily_basic_when_trade_date_empty(db):
    Base.metadata.create_all(bind=engine)
    daily_basic_dates = []

    class FakeCollector:
        def get_trading_calendar(self, year=None):
            return {"20240509", "20240510"}

        def get_stk_auction_open(self, trade_date):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "price": 10.5,
                        "vol": 819000,
                        "amount": 8600000,
                        "pre_close": 10.0,
                    }
                ]
            )

        def get_daily_data(self, trade_date=None, **kwargs):
            assert trade_date == "20240509"
            return pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": trade_date, "vol": 100000}])

        def get_daily_basic(self, trade_date=None):
            daily_basic_dates.append(trade_date)
            if trade_date == "20240510":
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "float_share": 9870,
                        "free_share": 5000,
                    }
                ]
            )

    service = AuctionDataService(collector=FakeCollector(), session_factory=lambda: db)

    assert service.sync_auction_open("20240510") == 1

    row = db.query(StockAuctionOpen).filter_by(trade_date="20240510", ts_code="000001.SZ").first()
    assert daily_basic_dates == ["20240510", "20240509"]
    assert math.isclose(row.auction_turnover_rate, 1.64, abs_tol=0.01)


def test_sync_auction_open_uses_trade_date_year_calendar(db):
    Base.metadata.create_all(bind=engine)
    calls = []

    class FakeCollector:
        def get_trading_calendar(self, year=None):
            calls.append(year)
            if year == 2024:
                return {"20240509", "20240510"}
            return {"20260102"}

        def get_stk_auction_open(self, trade_date):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": trade_date,
                        "price": 10.5,
                        "vol": 819000,
                        "amount": 8600000,
                        "pre_close": 10.0,
                    }
                ]
            )

        def get_daily_data(self, trade_date=None, **kwargs):
            assert trade_date == "20240509"
            return pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": trade_date, "vol": 100000}])

        def get_daily_basic(self, trade_date=None):
            return pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": trade_date, "float_share": 9870, "free_share": 5000}])

    service = AuctionDataService(collector=FakeCollector(), session_factory=lambda: db)

    assert service.sync_auction_open("20240510") == 1
    assert calls == [2024, 2023]


def test_recalculate_auction_ratios_from_daily_cache(db):
    Base.metadata.create_all(bind=engine)
    db.add(
        StockDailyData(
            ts_code="999001.SZ",
            trade_date="20991230",
            open=10,
            high=11,
            low=9,
            close=10,
            vol=100000,
            is_adj=0,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20991231",
            ts_code="999001.SZ",
            price=10.5,
            vol=819000,
            pre_close=10.0,
            auction_ratio=0.08,
            auction_turnover_rate=0.83,
        )
    )
    db.commit()

    service = AuctionDataService(collector=object(), session_factory=lambda: db)

    result = service.recalculate_auction_ratios_from_daily_cache("20991231", "20991231")

    row = db.query(StockAuctionOpen).filter_by(trade_date="20991231", ts_code="999001.SZ").first()
    assert result["updated_count"] == 1
    assert result["missing_count"] == 0
    assert result["trade_dates"] == ["20991231"]
    assert row.auction_ratio == 8.19
    assert math.isclose(row.auction_turnover_rate, 0.83, abs_tol=0.01)


def test_daily_basic_request_includes_float_share(monkeypatch):
    from backend.services.data_collector import TushareDataCollector

    captured = {}

    class FakePro:
        def daily_basic(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame()

    collector = TushareDataCollector.__new__(TushareDataCollector)
    collector._last_pro = FakePro()

    collector.get_daily_basic(trade_date="20240510")

    assert "float_share" in captured["fields"]
    assert "free_share" in captured["fields"]


def test_get_stk_auction_open_uses_stk_auction_returns_raw_fields():
    from backend.services.data_collector import TushareDataCollector

    captured = {}

    class FakePro:
        def stk_auction(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002929.SZ",
                        "trade_date": "20260508",
                        "vol": 691900,
                        "price": 78.23,
                        "amount": 54127337,
                        "pre_close": 71.12,
                        "turnover_rate": 0.326464,
                        "volume_ratio": 3.90231,
                        "float_share": 21193.8,
                    }
                ]
            )

    collector = TushareDataCollector.__new__(TushareDataCollector)
    collector._last_pro = FakePro()

    df = collector.get_stk_auction_open("20260508")

    assert captured["trade_date"] == "20260508"
    assert "price" in captured["fields"]
    assert df.loc[0, "vol"] == 691900
    assert df.loc[0, "price"] == 78.23
    assert df.loc[0, "pre_close"] == 71.12
    assert df.loc[0, "turnover_rate"] == 0.326464
    assert "open" not in df.columns


def test_trading_calendar_cache_is_scoped_by_year():
    from backend.services.data_collector import TushareDataCollector

    calls = []

    class FakePro:
        def trade_cal(self, exchange, start_date, end_date, is_open):
            calls.append((start_date, end_date))
            year = start_date[:4]
            return pd.DataFrame([{"cal_date": f"{year}0102"}])

    collector = TushareDataCollector.__new__(TushareDataCollector)
    collector._trading_calendar_cache = None
    collector._last_pro = FakePro()

    assert collector.get_trading_calendar(2025) == {"20250102"}
    assert collector.get_trading_calendar(2026) == {"20260102"}
    assert collector.get_trading_calendar(2025) == {"20250102"}
    assert calls == [("20250101", "20251231"), ("20260101", "20261231")]
