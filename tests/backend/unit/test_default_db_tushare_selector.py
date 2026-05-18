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


class FakeCollector:
    def get_trading_calendar(self, year=None):
        return {f"202405{day:02d}" for day in range(1, 12)}

    def get_daily_basic(self, trade_date=None):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": trade_date, "circ_mv": 1000000},
                {"ts_code": "000002.SZ", "trade_date": trade_date, "circ_mv": 1000000},
            ]
        )

    def get_stock_basic(self):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "name": "数据库通过股", "industry": "传媒"},
                {"ts_code": "000002.SZ", "name": "竞价失败股", "industry": "医药"},
            ]
        )


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


def test_default_db_tushare_selector_uses_stock_daily_data_and_realtime_auction(db):
    Base.metadata.create_all(bind=engine)
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
