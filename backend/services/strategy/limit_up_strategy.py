"""
涨停强度策略
"""
from typing import Optional, Dict, Any
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry
)


@StrategyRegistry.register(name="涨停强度", category="量化分析")
class LimitUpStrengthStrategy(BaseStrategy):
    """涨停强度策略"""

    name = "涨停强度"
    category = "量化分析"
    default_params = {
        'min_limit_count': 3,
        'min_success_rate': 90.0
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        执行涨停强度过滤

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        limit_count = stock_data.limit_up_count
        success_rate = stock_data.limit_success_rate

        if limit_count is None:
            return StrategyResult(
                passed=False,
                reason="缺少涨停次数数据"
            )

        min_count = self.get_param('min_limit_count')

        if limit_count < min_count:
            return StrategyResult(
                passed=False,
                reason=f"近100日涨停次数 {limit_count}次 小于最小值 {min_count}次",
                metrics={'limit_up_count': limit_count}
            )

        if success_rate is not None:
            min_rate = self.get_param('min_success_rate')
            if success_rate < min_rate:
                return StrategyResult(
                    passed=False,
                    reason=f"封板成功率 {success_rate:.1f}% 小于最小值 {min_rate}%",
                    metrics={
                        'limit_up_count': limit_count,
                        'limit_success_rate': success_rate
                    }
                )

        count_score = min(limit_count / 10 * 50, 50)
        rate_score = (success_rate / 100 * 50) if success_rate else 25
        score = count_score + rate_score

        return StrategyResult(
            passed=True,
            score=score,
            metrics={
                'limit_up_count': limit_count,
                'limit_success_rate': success_rate
            }
        )
