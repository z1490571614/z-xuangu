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
