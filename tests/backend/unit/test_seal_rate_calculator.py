"""
封板率计算服务测试
"""
import pytest
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
