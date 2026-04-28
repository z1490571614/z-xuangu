"""
选股策略模块
"""
from backend.services.strategy.base_strategy import (
    BaseStrategy,
    StockData,
    StrategyResult,
    StrategyRegistry,
    StrategyManager
)
from backend.services.strategy.market_cap_strategy import MarketCapStrategy
from backend.services.strategy.price_strategy import PriceStrategy
from backend.services.strategy.trend_strategy import TrendStrategy
from backend.services.strategy.limit_up_strategy import LimitUpStrengthStrategy
from backend.services.strategy.auction_activity_strategy import AuctionActivityStrategy

__all__ = [
    "BaseStrategy",
    "StockData",
    "StrategyResult",
    "StrategyRegistry",
    "StrategyManager",
    "MarketCapStrategy",
    "PriceStrategy",
    "TrendStrategy",
    "LimitUpStrengthStrategy",
    "AuctionActivityStrategy",
]
