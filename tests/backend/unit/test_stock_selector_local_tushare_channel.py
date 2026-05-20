import math

import pandas as pd

from backend.services.stock_selector import StockSelectorService


class FakeLocalTushareSelector:
    def select(self, **kwargs):
        return {
            "stocks": [
                type(
                    "Stock",
                    (),
                    {
                        "ts_code": "000001.SZ",
                        "name": "通道股",
                        "close": 10.0,
                        "change_pct": 5.0,
                        "pre_change_pct": 2.0,
                        "open_change_pct": 4.0,
                        "auction_ratio": 8.0,
                        "auction_turnover_rate": 1.0,
                        "industry": None,
                        "concept": None,
                        "board_type": None,
                        "limit_up_count": 4,
                        "seal_rate": None,
                        "rise_10d_pct": 12.0,
                        "market": None,
                        "extra_data": {},
                    },
                )()
            ],
            "total_count": 1,
            "execution_time": 0.1,
            "source": "tdx_local_tushare",
            "task_results": [{"task_id": "local_tushare_default"}],
        }


def test_phase1_uses_local_tushare_channel_without_calling_mcp(monkeypatch):
    service = object.__new__(StockSelectorService)
    service.collector = object()
    service._get_trade_date = lambda: "20260518"

    monkeypatch.setenv("DEFAULT_SELECTION_CHANNEL", "local_tushare")
    monkeypatch.setattr(
        "backend.services.stock_selector.DefaultLocalTushareSelectorService",
        lambda: FakeLocalTushareSelector(),
        raising=False,
    )

    def fail_mcp(*args, **kwargs):
        raise AssertionError("local_tushare 通道不应该调用 MCP")

    phase = service._execute_phase1([], fail_mcp, "20260518")

    assert phase.success is True
    assert phase.source == "tdx_local_tushare"
    assert phase.data["total_count"] == 1


class FakeDbTushareSelector:
    def select(self, **kwargs):
        return {
            "stocks": [
                type(
                    "Stock",
                    (),
                    {
                        "ts_code": "000001.SZ",
                        "name": "数据库通道股",
                        "close": 10.0,
                        "change_pct": 5.0,
                        "pre_change_pct": 2.0,
                        "open_change_pct": 4.0,
                        "auction_ratio": 8.0,
                        "auction_turnover_rate": 1.0,
                        "industry": None,
                        "concept": None,
                        "board_type": None,
                        "limit_up_count": 4,
                        "seal_rate": 100.0,
                        "rise_10d_pct": 12.0,
                        "market": None,
                        "extra_data": {"touch_days": 4, "limit_up_days": 4, "seal_rate": 100.0},
                    },
                )()
            ],
            "total_count": 1,
            "execution_time": 0.1,
            "source": "stock_daily_tushare",
            "task_results": [{"task_id": "db_tushare_default"}],
        }


def test_phase1_uses_db_tushare_channel_without_calling_mcp(monkeypatch):
    service = object.__new__(StockSelectorService)
    service.collector = object()
    service._get_trade_date = lambda: "20260518"

    monkeypatch.setattr(
        "backend.services.stock_selector.DefaultDbTushareSelectorService",
        lambda: FakeDbTushareSelector(),
        raising=False,
    )

    def fail_mcp(*args, **kwargs):
        raise AssertionError("db_tushare 通道不应该调用 MCP")

    phase = service._execute_phase1([], fail_mcp, "20260518", "db_tushare")

    assert phase.success is True
    assert phase.source == "stock_daily_tushare"
    assert phase.data["total_count"] == 1


def test_phase3_reuses_db_tushare_precomputed_seal_rates(monkeypatch):
    service = object.__new__(StockSelectorService)

    class FailSealCalculator:
        def calculate_seal_rate(self, *args, **kwargs):
            raise AssertionError("已有数据库日线通道封板率时不应该逐只重算")

    service.seal_calculator = FailSealCalculator()
    phase1_data = {
        "source": "stock_daily_tushare",
        "stocks": [
            type(
                "Stock",
                (),
                {
                    "ts_code": "000001.SZ",
                    "extra_data": {
                        "touch_days": 4,
                        "limit_up_days": 4,
                        "seal_rate": 100.0,
                    },
                },
            )()
        ],
    }

    phase = service._execute_phase3(phase1_data, "20260518", 80.0, 100)

    assert phase.success is True
    assert phase.source == "stock_daily_data"
    assert phase.data["seal_rates"]["000001.SZ"]["seal_rate"] == 100.0


def test_phase2_daily_basic_falls_back_to_previous_trade_date():
    service = object.__new__(StockSelectorService)

    class FakePro:
        def daily(self, **kwargs):
            return pd.DataFrame()

    class FakeCollector:
        def __init__(self):
            self.daily_basic_calls = []

        def get_daily_basic(self, trade_date=None):
            self.daily_basic_calls.append(trade_date)
            if trade_date == "20260520":
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "pe": 12.3,
                        "pe_ttm": 13.4,
                        "pb": 1.5,
                        "turnover_rate": 2.6,
                        "volume_ratio": 1.2,
                        "total_mv": 100000,
                        "circ_mv": 80000,
                    }
                ]
            )

        def get_stock_basic(self):
            return pd.DataFrame()

        def get_trading_calendar(self):
            return {"20260519", "20260520"}

        def get_realtime_quotes(self, ts_codes):
            return {}

        def _get_pro(self):
            return FakePro()

    collector = FakeCollector()
    service.collector = collector
    phase1_data = {
        "stocks": [
            type("Stock", (), {"ts_code": "000001.SZ"})(),
        ]
    }

    phase = service._execute_phase2(phase1_data, "20260520")

    assert phase.success is True
    assert collector.daily_basic_calls[:2] == ["20260520", "20260519"]
    assert phase.data["analysis"]["000001.SZ"]["pe"] == 12.3
    assert phase.data["analysis"]["000001.SZ"]["circ_mv"] == 80000


def test_phase2_realtime_quotes_only_fill_missing_price_fields():
    service = object.__new__(StockSelectorService)

    class FakePro:
        def daily(self, **kwargs):
            return pd.DataFrame()

    class FakeCollector:
        def __init__(self):
            self.realtime_calls = []

        def get_daily_basic(self, trade_date=None):
            return pd.DataFrame()

        def get_stock_basic(self):
            return pd.DataFrame()

        def get_trading_calendar(self):
            return {"20260519", "20260520"}

        def get_realtime_quotes(self, ts_codes):
            self.realtime_calls.append(ts_codes)
            return {
                "000002.SZ": {
                    "open": 20.8,
                    "pre_close": 20.0,
                    "close": 21.0,
                }
            }

        def _get_pro(self):
            return FakePro()

    collector = FakeCollector()
    service.collector = collector
    phase1_data = {
        "stocks": [
            type(
                "Stock",
                (),
                {
                    "ts_code": "000001.SZ",
                    "close": 10.5,
                    "change_pct": 5.0,
                    "open_change_pct": 4.0,
                },
            )(),
            type(
                "Stock",
                (),
                {
                    "ts_code": "000002.SZ",
                    "close": None,
                    "change_pct": None,
                    "open_change_pct": None,
                },
            )(),
        ]
    }

    phase = service._execute_phase2(phase1_data, "20260520")

    assert phase.success is True
    assert collector.realtime_calls == [["000002.SZ"]]
    assert phase.data["analysis"]["000002.SZ"]["close"] == 21.0
    assert phase.data["analysis"]["000002.SZ"]["change_pct"] == 5.0
    assert math.isclose(phase.data["analysis"]["000002.SZ"]["open_change_pct"], 4.0)


def test_merge_results_keeps_phase1_mcp_price_fields_when_phase2_has_values():
    service = object.__new__(StockSelectorService)
    service._build_phase1_metric_fallbacks = lambda *args, **kwargs: {}

    stock = type(
        "Stock",
        (),
        {
            "ts_code": "000001.SZ",
            "name": "MCP股票",
            "close": 10.5,
            "change_pct": 5.0,
            "pre_change_pct": 2.0,
            "open_change_pct": 4.0,
            "auction_ratio": 8.0,
            "auction_turnover_rate": 1.0,
            "limit_up_count": 3,
            "rise_10d_pct": 12.0,
            "industry": None,
            "concept": None,
            "board_type": None,
            "market": None,
            "extra_data": {},
        },
    )()

    merged = service._merge_results(
        {"source": "tdx_mcp", "stocks": [stock]},
        {
            "analysis": {
                "000001.SZ": {
                    "close": 9.9,
                    "change_pct": -1.0,
                    "pre_change_pct": -2.0,
                    "open_change_pct": -3.0,
                    "industry": "电子",
                }
            }
        },
        {"seal_rates": {}},
        min_open_change_pct=None,
        min_seal_rate=None,
        trade_date="20260520",
    )

    assert len(merged) == 1
    assert merged[0]["close"] == 10.5
    assert merged[0]["close_price"] == 10.5
    assert merged[0]["change_pct"] == 5.0
    assert merged[0]["pre_change_pct"] == 2.0
    assert merged[0]["open_change_pct"] == 4.0
    assert merged[0]["industry"] == "电子"
