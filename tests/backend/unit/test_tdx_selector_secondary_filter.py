from backend.services.tdx_selector import TdxSelectorService, create_default_task
from backend.services.stock_selector import StockSelectorService


def test_phase1_does_not_filter_on_phase2_metrics():
    calls = []

    def fake_mcp(**kwargs):
        calls.append(kwargs)
        return {
            "meta": {"code": 0, "total": 1},
            "headers": [
                "POS", "market", "sec_code", "sec_name", "now_price", "chg0#",
                "所属行业", "涨停次数", "竞昨比", "竞价换手率",
            ],
            "data": [[1, "SZ", "000889", "中嘉博创", 12.34, 10.02, "通信设备", 0, 0.01, 0.01]],
        }

    result = TdxSelectorService()._execute_task(create_default_task(), fake_mcp)

    assert result["total_count"] == 1
    assert result["stocks"][0].ts_code == "000889.SZ"
    assert result["stocks"][0].auction_ratio == 1.0
    assert result["stocks"][0].auction_turnover_rate == 0.01
    assert "并显示竞昨比、竞价换手率、涨停次数、近10日涨幅" in calls[0]["question"]


def test_auction_turnover_keeps_percent_unit_when_below_one():
    def fake_mcp(**kwargs):
        return {
            "meta": {"code": 0, "total": 1},
            "headers": [
                "POS", "market", "sec_code", "sec_name", "now_price", "chg0#",
                "涨停次数", "竞昨比", "竞价换手率",
            ],
            "data": [[1, "SZ", "002951", "金时科技", 16.71, 0.12, 9, 0.0819, 0.65]],
        }

    result = TdxSelectorService()._execute_task(create_default_task(), fake_mcp)
    stock = result["stocks"][0]

    assert stock.auction_ratio == 8.19
    assert stock.auction_turnover_rate == 0.65


def test_phase1_uses_requested_tasks_without_duplicate_default():
    calls = []

    def fake_mcp(**kwargs):
        calls.append(kwargs)
        return {
            "meta": {"code": 0, "total": 0},
            "headers": [],
            "data": [],
        }

    service = StockSelectorService()
    result = service._execute_phase1([create_default_task()], fake_mcp, "20260508")

    assert result.success is True
    assert len(calls) == 1


def test_merge_fills_limit_up_count_from_seal_rate_when_mcp_omits_it(monkeypatch):
    def no_local_fallback(self, phase1_stocks, trade_date, seal_rates):
        return {}

    monkeypatch.setattr(
        StockSelectorService,
        "_build_phase1_metric_fallbacks",
        no_local_fallback,
    )

    phase1 = {
        "stocks": [
            type("Stock", (), {
                "ts_code": "000889.SZ",
                "name": "中嘉博创",
                "close": 5.0,
                "change_pct": 10.0,
                "pre_change_pct": None,
                "open_change_pct": None,
                "auction_ratio": None,
                "auction_turnover_rate": None,
                "limit_up_count": None,
                "rise_10d_pct": None,
                "industry": "通信设备",
                "concept": None,
            })()
        ]
    }
    phase2 = {"analysis": {"000889.SZ": {"circ_mv": 100000}}}
    phase3 = {"seal_rates": {"000889.SZ": {"touch_days": 5, "limit_up_days": 3, "seal_rate": 60.0}}}

    merged = StockSelectorService()._merge_results(
        phase1,
        phase2,
        phase3,
        min_open_change_pct=None,
        min_seal_rate=None,
        trade_date="20260508",
    )

    assert merged[0]["limit_up_count"] == 3


def test_merge_keeps_auction_metrics_out_of_phase2(monkeypatch):
    def no_local_fallback(self, phase1_stocks, trade_date, seal_rates):
        return {}

    monkeypatch.setattr(
        StockSelectorService,
        "_build_phase1_metric_fallbacks",
        no_local_fallback,
    )

    phase1 = {
        "stocks": [
            type("Stock", (), {
                "ts_code": "000889.SZ",
                "name": "中嘉博创",
                "close": 5.0,
                "change_pct": 10.0,
                "pre_change_pct": None,
                "open_change_pct": None,
                "auction_ratio": None,
                "auction_turnover_rate": None,
                "limit_up_count": 3,
                "rise_10d_pct": 12.0,
                "industry": "通信设备",
                "concept": None,
            })()
        ]
    }
    phase2 = {
        "analysis": {
            "000889.SZ": {
                "auction_ratio": 8.5,
                "auction_turnover_rate": 1.2,
                "circ_mv": 100000,
            }
        }
    }
    phase3 = {"seal_rates": {}}

    merged = StockSelectorService()._merge_results(
        phase1,
        phase2,
        phase3,
        min_open_change_pct=None,
        min_seal_rate=None,
        trade_date="20260508",
    )

    assert merged[0]["auction_ratio"] is None
    assert merged[0]["auction_turnover_rate"] is None


def test_merge_fills_blank_local_stock_name_from_phase2_stock_basic(monkeypatch):
    def no_local_fallback(self, phase1_stocks, trade_date, seal_rates):
        return {}

    monkeypatch.setattr(
        StockSelectorService,
        "_build_phase1_metric_fallbacks",
        no_local_fallback,
    )

    phase1 = {
        "stocks": [
            type("Stock", (), {
                "ts_code": "002181.SZ",
                "name": "",
                "close": 10.0,
                "change_pct": 5.0,
                "pre_change_pct": 1.0,
                "open_change_pct": 2.0,
                "auction_ratio": 4.67,
                "auction_turnover_rate": 1.27,
                "limit_up_count": 3,
                "rise_10d_pct": 12.0,
                "industry": None,
                "concept": None,
            })()
        ]
    }
    phase2 = {"analysis": {"002181.SZ": {"name": "粤传媒", "industry": "文化传媒", "circ_mv": 100000}}}

    merged = StockSelectorService()._merge_results(
        phase1,
        phase2,
        {"seal_rates": {}},
        min_open_change_pct=None,
        min_seal_rate=None,
        trade_date="20260518",
    )

    assert merged[0]["name"] == "粤传媒"


def test_merge_overwrites_daily_change_with_realtime_phase2_change(monkeypatch):
    def no_local_fallback(self, phase1_stocks, trade_date, seal_rates):
        return {}

    monkeypatch.setattr(
        StockSelectorService,
        "_build_phase1_metric_fallbacks",
        no_local_fallback,
    )

    phase1 = {
        "stocks": [
            type("Stock", (), {
                "ts_code": "002181.SZ",
                "name": "粤传媒",
                "close": 10.0,
                "change_pct": 5.0,
                "pre_change_pct": 5.0,
                "open_change_pct": 2.0,
                "auction_ratio": 4.67,
                "auction_turnover_rate": 1.27,
                "limit_up_count": 3,
                "rise_10d_pct": 12.0,
                "industry": "文化传媒",
                "concept": None,
            })()
        ]
    }
    phase2 = {
        "analysis": {
            "002181.SZ": {
                "close": 10.8,
                "change_pct": 8.0,
                "pre_change_pct": 5.0,
                "open_change_pct": 3.0,
                "circ_mv": 100000,
            }
        }
    }

    merged = StockSelectorService()._merge_results(
        phase1,
        phase2,
        {"seal_rates": {}},
        min_open_change_pct=None,
        min_seal_rate=None,
        trade_date="20260518",
    )

    assert merged[0]["close"] == 10.8
    assert merged[0]["close_price"] == 10.8
    assert merged[0]["change_pct"] == 8.0
    assert merged[0]["pre_change_pct"] == 5.0
