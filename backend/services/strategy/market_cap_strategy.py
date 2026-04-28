"""
市值策略
"""
from typing import Optional, Dict, Any
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry
)


@StrategyRegistry.register(name="市值过滤", category="基础过滤")
class MarketCapStrategy(BaseStrategy):
    """市值过滤策略"""

    name = "市值过滤"
    category = "基础过滤"
    default_params = {
        'min_circ_mv': None,
        'max_circ_mv': 2000
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        执行市值过滤

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        circ_mv = stock_data.circ_mv

        if circ_mv is None:
            return StrategyResult(
                passed=False,
                reason="缺少流通市值数据"
            )

        circ_mv_yi = circ_mv / 10000

        min_mv = self.get_param('min_circ_mv')
        max_mv = self.get_param('max_circ_mv')

        if min_mv is not None and circ_mv_yi < min_mv:
            return StrategyResult(
                passed=False,
                reason=f"流通市值 {circ_mv_yi:.2f}亿 小于最小值 {min_mv}亿",
                metrics={'circ_mv': circ_mv_yi}
            )

        if max_mv is not None and circ_mv_yi > max_mv:
            return StrategyResult(
                passed=False,
                reason=f"流通市值 {circ_mv_yi:.2f}亿 大于最大值 {max_mv}亿",
                metrics={'circ_mv': circ_mv_yi}
            )

        score = 100 - (circ_mv_yi / max_mv * 50) if max_mv else 50

        return StrategyResult(
            passed=True,
            score=score,
            metrics={'circ_mv': circ_mv_yi}
        )
