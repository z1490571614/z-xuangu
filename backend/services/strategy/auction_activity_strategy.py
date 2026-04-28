"""
竞价活跃度策略
"""
from typing import Optional, Dict, Any
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry
)


@StrategyRegistry.register(name="竞价活跃度", category="量化分析")
class AuctionActivityStrategy(BaseStrategy):
    """竞价活跃度策略"""

    name = "竞价活跃度"
    category = "量化分析"
    default_params = {
        'min_volume_ratio': 1.5,
        'min_turnover_rate': 2.0
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        执行竞价活跃度过滤

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        volume_ratio = stock_data.auction_volume_ratio
        turnover_rate = stock_data.auction_turnover_rate

        if volume_ratio is None and turnover_rate is None:
            return StrategyResult(
                passed=True,
                score=50,
                reason="竞价数据不可用，默认通过"
            )

        min_volume = self.get_param('min_volume_ratio')
        min_turnover = self.get_param('min_turnover_rate')

        fail_reasons = []

        if volume_ratio is not None and min_volume is not None:
            if volume_ratio < min_volume:
                fail_reasons.append(
                    f"竞价量比 {volume_ratio:.2f} 小于最小值 {min_volume}"
                )

        if turnover_rate is not None and min_turnover is not None:
            if turnover_rate < min_turnover:
                fail_reasons.append(
                    f"竞价换手率 {turnover_rate:.2f}% 小于最小值 {min_turnover}%"
                )

        if fail_reasons:
            return StrategyResult(
                passed=False,
                reason="; ".join(fail_reasons),
                metrics={
                    'auction_volume_ratio': volume_ratio,
                    'auction_turnover_rate': turnover_rate
                }
            )

        volume_score = min(volume_ratio / 3 * 50, 50) if volume_ratio else 25
        turnover_score = min(turnover_rate / 5 * 50, 50) if turnover_rate else 25
        score = (volume_score + turnover_score) / 2

        return StrategyResult(
            passed=True,
            score=score,
            metrics={
                'auction_volume_ratio': volume_ratio,
                'auction_turnover_rate': turnover_rate
            }
        )
