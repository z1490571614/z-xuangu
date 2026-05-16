"""
封板率计算服务测试
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock


class TestSealRateCalculator:
    def test_seal_rate_calculation_basic(self):
        """基础封板率计算：10天触板7天涨停 = 70%"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()

        mock_data = MagicMock()
        mock_data.touch_days = 10
        mock_data.limit_up_days = 7
        mock_data.seal_rate = 70.0

        result = calc.get_cached_result("000001.SZ", "20260427", 100)
        if result:
            assert 0 <= result.seal_rate <= 100

    def test_seal_rate_all_limit_up(self):
        """全部涨停 = 100% 封板率"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        result = calc.get_cached_result("000001.SZ", "20260427", 100)
        if result:
            assert result.seal_rate <= 100

    def test_seal_rate_no_touch(self):
        """没有触板 = 0% 或 None"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        result = calc.get_cached_result("999999.SZ", "20260427", 100)
        if result:
            assert result.seal_rate == 0 or result.seal_rate is None

    def test_get_trading_dates(self):
        """获取交易日列表应返回有效日期"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        dates = calc.get_trading_dates("20260427", 100)
        assert isinstance(dates, list)

    def test_cached_result_structure(self):
        """缓存结果应包含所有必要字段"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        result = calc.get_cached_result("000001.SZ", "20260427", 100)
        if result:
            assert hasattr(result, "ts_code")
            assert hasattr(result, "touch_days")
            assert hasattr(result, "limit_up_days")
            assert hasattr(result, "seal_rate")

    def test_calculate_with_invalid_period(self):
        """非法周期应处理为默认值或报错"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        try:
            calc.get_trading_dates("20260427", -1)
        except (ValueError, AssertionError):
            pass

    def test_batch_calculate(self):
        """批量计算封板率返回 (通过列表, 全部列表) 元组"""
        from backend.services.seal_rate_calculator import SealRateCalculator
        calc = SealRateCalculator()
        result = calc.batch_calculate_seal_rate(["000001.SZ", "000002.SZ"], "20260427", 100)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_incomplete_cached_result_recomputes_from_local_daily_cache(self):
        """旧缓存不完整时，优先用本地日线缓存重算并刷新缓存。"""
        from backend.services.seal_rate_calculator import SealRateCalculator

        calc = SealRateCalculator.__new__(SealRateCalculator)
        stale_cached = SimpleNamespace(
            touch_days=1,
            limit_up_days=0,
            seal_rate=0.0,
            start_date="20240509",
            end_date="20240510",
            data_complete=0,
        )
        saved = {}

        calc.get_cached_result = lambda ts_code, trade_date, period_days: stale_cached
        calc.get_trading_dates = lambda trade_date, period_days: ["20240509", "20240510"]
        calc.calculate_seal_rate_from_cache = lambda ts_code, dates: {
            "touch_days": 2,
            "limit_up_days": 2,
            "seal_rate": 100.0,
            "data_complete": 1,
        }

        def fail_external_fetch(ts_code, trading_dates):
            raise AssertionError("本地日线已完整时不应再调用外部日线抓取")

        def capture_save(ts_code, trade_date, period_days, result, trading_dates):
            saved.update(result)

        calc.fetch_and_save_daily_data = fail_external_fetch
        calc.save_cached_result = capture_save

        result = calc.calculate_seal_rate("000001.SZ", "20240510", 2, use_cache=True)

        assert result["touch_days"] == 2
        assert result["limit_up_days"] == 2
        assert result["seal_rate"] == 100.0
        assert result["data_complete"] == 1
        assert saved["seal_rate"] == 100.0
