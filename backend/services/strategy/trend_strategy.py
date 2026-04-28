"""
趋势策略
"""
from typing import Optional, Dict, Any
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry
)


@StrategyRegistry.register(name="趋势过滤", category="技术分析")
class TrendStrategy(BaseStrategy):
    """趋势过滤策略"""

    name = "趋势过滤"
    category = "技术分析"
    default_params = {
        'min_change_10d': -20,
        'max_change_10d': 50
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        执行趋势过滤

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        price_change = stock_data.price_change_10d

        if price_change is None:
            return StrategyResult(
                passed=False,
                reason="缺少10日涨跌幅数据"
            )

        min_change = self.get_param('min_change_10d')
        max_change = self.get_param('max_change_10d')

        if min_change is not None and price_change < min_change:
            return StrategyResult(
                passed=False,
                reason=f"10日涨跌幅 {price_change:.2f}% 小于最小值 {min_change}%",
                metrics={'price_change_10d': price_change}
            )

        if max_change is not None and price_change > max_change:
            return StrategyResult(
                passed=False,
                reason=f"10日涨跌幅 {price_change:.2f}% 大于最大值 {max_change}%",
                metrics={'price_change_10d': price_change}
            )

        if price_change > 0:
            score = 50 + min(price_change, 30)
        else:
            score = 50 + price_change

        return StrategyResult(
            passed=True,
            score=max(0, score),
            metrics={'price_change_10d': price_change}
        )
