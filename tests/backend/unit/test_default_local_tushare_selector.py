import pandas as pd

from backend.services.default_local_tushare_selector import DefaultLocalTushareSelectorService


class FakeLocalDaily:
    def select(self, **kwargs):
        return {
            "stocks": [
                type(
                    "Stock",
                    (),
                    {
                        "ts_code": "000001.SZ",
                        "name": "通过股",
                        "close": 10.0,
                        "change_pct": 5.0,
                        "pre_change_pct": 2.0,
                        "open_change_pct": 4.0,
                        "auction_ratio": None,
                        "auction_turnover_rate": None,
                        "industry": None,
                        "concept": None,
                        "board_type": None,
                        "limit_up_count": 4,
                        "seal_rate": None,
                        "rise_10d_pct": 12.0,
                        "market": None,
                        "extra_data": {},
                    },
                )(),
                type(
                    "Stock",
                    (),
                    {
                        "ts_code": "000002.SZ",
                        "name": "竞昨比过低",
                        "close": 11.0,
                        "change_pct": 3.0,
                        "pre_change_pct": 1.0,
                        "open_change_pct": 3.0,
                        "auction_ratio": None,
                        "auction_turnover_rate": None,
                        "industry": None,
                        "concept": None,
                        "board_type": None,
                        "limit_up_count": 5,
                        "seal_rate": None,
                        "rise_10d_pct": 10.0,
                        "market": None,
                        "extra_data": {},
                    },
                )(),
                type(
                    "Stock",
                    (),
                    {
                        "ts_code": "000003.SZ",
                        "name": "换手过高",
                        "close": 12.0,
                        "change_pct": 2.0,
                        "pre_change_pct": 1.0,
                        "open_change_pct": 3.0,
                        "auction_ratio": None,
                        "auction_turnover_rate": None,
                        "industry": None,
                        "concept": None,
                        "board_type": None,
                        "limit_up_count": 5,
                        "seal_rate": None,
                        "rise_10d_pct": 10.0,
                        "market": None,
                        "extra_data": {},
                    },
                )(),
            ],
            "total_count": 3,
            "task_results": [],
        }


class FakeAuctionService:
    def __init__(self):
        self.synced = []

    def sync_auction_open(self, trade_date):
        self.synced.append(trade_date)
        return 3

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
                "auction_ratio": 3.9,
                "auction_turnover_rate": 1.2,
                "auction_amount": 1000000,
                "auction_volume": 100000,
                "auction_source": "tushare_stk_auction",
            },
            "000003.SZ": {
                "auction_ratio": 8.0,
                "auction_turnover_rate": 10.1,
                "auction_amount": 1000000,
                "auction_volume": 100000,
                "auction_source": "tushare_stk_auction",
            },
        }


class FakeCollector:
    def get_daily_basic(self, trade_date=None):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "circ_mv": 1000000},
                {"ts_code": "000002.SZ", "circ_mv": 1000000},
                {"ts_code": "000003.SZ", "circ_mv": 1000000},
            ]
        )


def test_default_local_tushare_selector_filters_by_tushare_auction_fields():
    auction_service = FakeAuctionService()
    selector = DefaultLocalTushareSelectorService(
        local_selector=FakeLocalDaily(),
        auction_service=auction_service,
    )

    result = selector.select(
        trade_date="20260518",
        data_collector=FakeCollector(),
    )

    assert auction_service.synced == ["20260518"]
    assert result["source"] == "tdx_local_tushare"
    assert result["total_count"] == 1
    stock = result["stocks"][0]
    assert stock.ts_code == "000001.SZ"
    assert stock.auction_ratio == 8.0
    assert stock.auction_turnover_rate == 1.2
    assert stock.extra_data["auction_amount"] == 1000000
    assert stock.extra_data["auction_volume"] == 100000
