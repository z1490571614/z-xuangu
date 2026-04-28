"""
价格策略
"""
from typing import Optional, Dict, Any
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry
)


@StrategyRegistry.register(name="价格过滤", category="基础过滤")
class PriceStrategy(BaseStrategy):
    """价格过滤策略"""

    name = "价格过滤"
    category = "基础过滤"
    default_params = {
        'min_price': None,
        'max_price': 500
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        执行价格过滤

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        close = stock_data.close

        if close is None:
            return StrategyResult(
                passed=False,
                reason="缺少收盘价数据"
            )

        min_price = self.get_param('min_price')
        max_price = self.get_param('max_price')

        if min_price is not None and close < min_price:
            return StrategyResult(
                passed=False,
                reason=f"收盘价 {close:.2f}元 小于最小值 {min_price}元",
                metrics={'close': close}
            )

        if max_price is not None and close > max_price:
            return StrategyResult(
                passed=False,
                reason=f"收盘价 {close:.2f}元 大于最大值 {max_price}元",
                metrics={'close': close}
            )

        score = 100 - (close / max_price * 50) if max_price else 50

        return StrategyResult(
            passed=True,
            score=score,
            metrics={'close': close}
        )
