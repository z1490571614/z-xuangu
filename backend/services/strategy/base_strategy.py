"""
选股策略基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class StockData:
    """股票数据类"""
    ts_code: str
    name: Optional[str] = None
    close: Optional[float] = None
    pct_chg: Optional[float] = None
    circ_mv: Optional[float] = None
    total_mv: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    limit_up_count: Optional[int] = None
    limit_success_rate: Optional[float] = None
    auction_volume_ratio: Optional[float] = None
    auction_turnover_rate: Optional[float] = None
    price_change_10d: Optional[float] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """策略执行结果"""
    passed: bool
    score: float = 0.0
    reason: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """选股策略基类"""

    name: str = "BaseStrategy"
    category: str = "base"
    default_params: Dict[str, Any] = {}

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化策略

        Args:
            params: 策略参数
        """
        self.params = self.default_params.copy()
        if params:
            self.params.update(params)

    @abstractmethod
    def filter(self, stock_data: StockData) -> StrategyResult:
        """
        核心过滤方法

        Args:
            stock_data: 股票数据

        Returns:
            策略执行结果
        """
        pass

    def validate_params(self) -> bool:
        """
        验证参数是否有效

        Returns:
            参数是否有效
        """
        return True

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        获取参数值

        Args:
            key: 参数键
            default: 默认值

        Returns:
            参数值
        """
        return self.params.get(key, default)


class StrategyRegistry:
    """策略注册表"""

    _strategies: Dict[str, type] = {}

    @classmethod
    def register(cls, name: Optional[str] = None, category: Optional[str] = None):
        """
        策略注册装饰器

        Args:
            name: 策略名称
            category: 策略类别

        Returns:
            装饰器函数
        """
        def decorator(strategy_class: type):
            strategy_name = name or strategy_class.name
            cls._strategies[strategy_name] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def get_strategy(cls, name: str) -> Optional[type]:
        """
        获取策略类

        Args:
            name: 策略名称

        Returns:
            策略类
        """
        return cls._strategies.get(name)

    @classmethod
    def list_strategies(cls) -> List[str]:
        """
        列出所有注册的策略

        Returns:
            策略名称列表
        """
        return list(cls._strategies.keys())


class StrategyManager:
    """策略管理器"""

    def __init__(self):
        """初始化策略管理器"""
        self.strategies: Dict[str, BaseStrategy] = {}

    def add_strategy(self, name: str, strategy: BaseStrategy) -> None:
        """
        添加策略

        Args:
            name: 策略名称
            strategy: 策略实例
        """
        self.strategies[name] = strategy

    def remove_strategy(self, name: str) -> None:
        """
        移除策略

        Args:
            name: 策略名称
        """
        if name in self.strategies:
            del self.strategies[name]

    def execute(self, stock_pool: List[StockData]) -> Dict[str, Any]:
        """
        执行策略组合

        Args:
            stock_pool: 股票池数据

        Returns:
            执行结果
        """
        passed_stocks: List[StockData] = []
        failed_stocks: List[Dict[str, Any]] = []

        for stock in stock_pool:
            all_passed = True
            fail_reasons = []

            for strategy_name, strategy in self.strategies.items():
                result = strategy.filter(stock)
                if not result.passed:
                    all_passed = False
                    if result.reason:
                        fail_reasons.append(f"{strategy_name}: {result.reason}")
                    break

            if all_passed:
                passed_stocks.append(stock)
            else:
                failed_stocks.append({
                    'ts_code': stock.ts_code,
                    'name': stock.name,
                    'reasons': fail_reasons
                })

        return {
            'passed_stocks': passed_stocks,
            'failed_stocks': failed_stocks,
            'total_count': len(stock_pool),
            'passed_count': len(passed_stocks),
            'pass_rate': len(passed_stocks) / len(stock_pool) if stock_pool else 0
        }

    def clear(self) -> None:
        """清空所有策略"""
        self.strategies.clear()
