import math

import pandas as pd

from backend.database import Base, engine
from backend.models.seal_rate import StockDailyData
from backend.services.default_db_tushare_selector import DefaultDbTushareSelectorService


class FakeAuctionService:
    def __init__(self):
        self.synced = []

    def sync_auction_open(self, trade_date):
        self.synced.append(trade_date)
        return 2

    def batch_get_auction_features(self, trade_date, ts_codes):
        return {
            "000001.SZ": {
                "auction_ratio": 8.0,
                "auction_turnover_rate": 1.2,
                "auction_amount": 1000000,
                "auction_volume": 100000,
                "auction_source": "tushare_stk_auction",
            },
            "000002.SZ": {
                "auction_ratio": 2.0,
                "auction_turnover_rate": 1.2,
                "auction_amount": 1000000,
                "auction_volume": 100000,
                "auction_source": "tushare_stk_auction",
            },
        }


class EmptyAuctionService:
    def __init__(self):
        self.synced = []

    def sync_auction_open(self, trade_date):
        self.synced.append(trade_date)
        return 0

    def batch_get_auction_features(self, trade_date, ts_codes):
        return {}


class FakeCollector:
    def get_trading_calendar(self, year=None):
        return {f"202405{day:02d}" for day in range(1, 12)}

    def get_daily_basic(self, trade_date=None):
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": trade_date,
                    "circ_mv": 1000000,
                    "float_share": 1000,
                    "free_share": 1000,
                },
                {
                    "ts_code": "000002.SZ",
                    "trade_date": trade_date,
                    "circ_mv": 1000000,
                    "float_share": 1000,
                    "free_share": 1000,
                },
                {
                    "ts_code": "000003.SZ",
                    "trade_date": trade_date,
                    "circ_mv": 1000000,
                    "float_share": 1000,
                    "free_share": 1000,
                },
            ]
        )

    def get_stock_basic(self):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "数据库通过股", "industry": "传媒"},
                {"ts_code": "000002.SZ", "name": "竞价失败股", "industry": "医药"},
                {"ts_code": "000003.SZ", "name": "实时竞价兜底股", "industry": "电子"},
            ]
        )

    def get_realtime_quotes(self, ts_codes):
        return {
            "000001.SZ": {
                "open": 10.8,
                "pre_close": 10.0,
                "close": 10.9,
                "volume_hand": 8000,
                "amount": 8880000,
            },
            "000003.SZ": {
                "open": 30.8,
                "pre_close": 30.0,
                "close": 30.9,
                "volume_hand": 8000,
                "amount": 24640000,
            }
        }


def _add_daily_rows(db, ts_code: str, base_close: float):
    for idx, day in enumerate(range(1, 12), start=1):
        close = base_close + idx * 0.1
        is_limit = day in {7, 9, 11}
        up_limit = close if is_limit else close + 1.0
        db.add(
            StockDailyData(
                ts_code=ts_code,
                trade_date=f"202405{day:02d}",
                open=close - 0.1,
                high=up_limit if is_limit else close + 0.2,
                low=close - 0.2,
                close=close,
                pre_close=close - 0.1,
                pct_chg=1.0,
                up_limit=up_limit,
                vol=100000,
                amount=1000000,
                is_adj=0,
            )
        )


def _clear_daily_rows(db):
    db.query(StockDailyData).delete()
    db.commit()


def test_default_db_tushare_selector_uses_stock_daily_data_and_realtime_auction(db):
    Base.metadata.create_all(bind=engine)
    _clear_daily_rows(db)
    _add_daily_rows(db, "000001.SZ", 10)
    _add_daily_rows(db, "000002.SZ", 20)
    db.commit()

    auction_service = FakeAuctionService()
    selector = DefaultDbTushareSelectorService(
        auction_service=auction_service,
        session_factory=lambda: db,
    )

    result = selector.select(
        trade_date="20240511",
        period_days=5,
        min_limit_up_count=2,
        data_collector=FakeCollector(),
    )

    assert auction_service.synced == ["20240511"]
    assert result["source"] == "stock_daily_tushare"
    assert result["total_count"] == 1
    stock = result["stocks"][0]
    assert stock.ts_code == "000001.SZ"
    assert stock.name == "数据库通过股"
    assert stock.limit_up_count == 3
    assert stock.extra_data["touch_days"] == 3
    assert stock.extra_data["limit_up_days"] == 3
    assert math.isclose(stock.extra_data["seal_rate"], 100.0)
    assert stock.auction_ratio == 8.0
    assert stock.auction_turnover_rate == 1.2


def test_default_db_tushare_selector_falls_back_to_realtime_quotes_when_tushare_auction_empty(db):
    Base.metadata.create_all(bind=engine)
    _clear_daily_rows(db)
    _add_daily_rows(db, "000003.SZ", 30)
    db.commit()

    auction_service = EmptyAuctionService()
    selector = DefaultDbTushareSelectorService(
        auction_service=auction_service,
        session_factory=lambda: db,
    )

    result = selector.select(
        trade_date="20240511",
        period_days=5,
        min_limit_up_count=2,
        data_collector=FakeCollector(),
    )

    assert auction_service.synced == ["20240511"]
    assert result["total_count"] == 1
    assert result["task_results"][0]["funnel"]["auction_realtime_fallback"] == 1
    stock = result["stocks"][0]
    assert stock.ts_code == "000003.SZ"
    assert stock.auction_ratio == 8.0
    assert stock.auction_turnover_rate == 8.0
    assert stock.extra_data["auction_source"] == "tdx_realtime_quote_fallback"
