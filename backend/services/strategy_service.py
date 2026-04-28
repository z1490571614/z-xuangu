"""
选股策略模板管理服务

功能:
1. 策略模板 CRUD 操作
2. 预置模板初始化
3. 策略参数验证
4. 策略启用/禁用
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from backend.models import StrategyTemplate
from backend.database import SessionLocal

logger = logging.getLogger(__name__)


DEFAULT_STRATEGY_TEMPLATES = [
    {
        "name": "默认策略",
        "description": "平衡型选股策略，适合大多数场景。综合考量市值、价格、趋势、涨停强度和竞价活跃度。",
        "task_template": "default",
        "is_system": True,
        "is_enabled": True,
        "sort_order": 1,
        "conditions_config": {
            "basic_filter": {
                "exclude_st": True,
                "exclude_suspended": True,
                "exclude_bse": True,
                "label": "非ST非停牌非北交所股票",
            },
            "market_cap": {
                "max_market_cap": 2000,
                "label": "流通市值小于2000亿",
            },
            "price": {
                "max_close_price": 500,
                "label": "昨日收盘价小于500元",
            },
            "trend": {
                "min_rise_days": 10,
                "label": "近10日股价上涨",
            },
            "limit_up": {
                "min_limit_up_count": 3,
                "limit_up_days": 100,
                "min_seal_rate": 80,
                "label": "近100日涨停≥3次，封板率≥80%",
            },
            "call_auction": {
                "call_auction_ratio_min": 4,
                "call_auction_ratio_max": 30,
                "turnover_rate_min": 0.5,
                "turnover_rate_max": 10,
                "label": "竞昨比4%-30%，换手率0.5%-10%",
            },
            "open_change": {
                "min_open_change_pct": -3,
                "label": "开盘涨幅≥-3%",
            },
        },
    },
    {
        "name": "保守策略",
        "description": "严格筛选策略，适合风险厌恶型投资者。要求更高的涨停次数和封板成功率，较小的市值和价格范围。",
        "task_template": "conservative",
        "is_system": True,
        "is_enabled": True,
        "sort_order": 2,
        "conditions_config": {
            "basic_filter": {
                "exclude_st": True,
                "exclude_suspended": True,
                "exclude_bse": True,
                "label": "非ST非停牌非北交所股票",
            },
            "market_cap": {
                "max_market_cap": 1000,
                "label": "流通市值小于1000亿",
            },
            "price": {
                "max_close_price": 100,
                "label": "昨日收盘价小于100元",
            },
            "trend": {
                "min_rise_days": 15,
                "label": "近15日股价上涨",
            },
            "limit_up": {
                "min_limit_up_count": 5,
                "limit_up_days": 100,
                "min_seal_rate": 95,
                "label": "近100日涨停≥5次，封板率≥95%",
            },
            "call_auction": {
                "call_auction_ratio_min": 5,
                "call_auction_ratio_max": 20,
                "turnover_rate_min": 1,
                "turnover_rate_max": 5,
                "label": "竞昨比5%-20%，换手率1%-5%",
            },
            "open_change": {
                "min_open_change_pct": -2,
                "label": "开盘涨幅≥-2%",
            },
        },
    },
    {
        "name": "激进策略",
        "description": "宽松筛选策略，适合风险偏好型投资者。降低筛选门槛，寻找更多潜在机会。",
        "task_template": "aggressive",
        "is_system": True,
        "is_enabled": True,
        "sort_order": 3,
        "conditions_config": {
            "basic_filter": {
                "exclude_st": True,
                "exclude_suspended": True,
                "exclude_bse": True,
                "label": "非ST非停牌非北交所股票",
            },
            "market_cap": {
                "max_market_cap": 500,
                "label": "流通市值小于500亿",
            },
            "price": {
                "max_close_price": 200,
                "label": "昨日收盘价小于200元",
            },
            "trend": {
                "min_rise_days": 5,
                "label": "近5日股价上涨",
            },
            "limit_up": {
                "min_limit_up_count": 3,
                "limit_up_days": 100,
                "min_seal_rate": 80,
                "label": "近100日涨停≥3次，封板率≥80%",
            },
            "call_auction": {
                "call_auction_ratio_min": 10,
                "call_auction_ratio_max": 30,
                "turnover_rate_min": 2,
                "turnover_rate_max": 10,
                "label": "竞昨比10%-30%，换手率2%-10%",
            },
            "open_change": {
                "min_open_change_pct": -5,
                "label": "开盘涨幅≥-5%",
            },
        },
    },
]


class StrategyTemplateService:
    """策略模板管理服务"""

    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()

    def initialize_default_strategies(self) -> int:
        """
        初始化（或更新）预置策略模板

        Returns:
            处理的策略数量
        """
        processed_count = 0

        for template_data in DEFAULT_STRATEGY_TEMPLATES:
            existing = (
                self.db.query(StrategyTemplate)
                .filter(StrategyTemplate.name == template_data["name"])
                .first()
            )

            if existing:
                for key, value in template_data.items():
                    setattr(existing, key, value)
                logger.info(f"更新预置策略模板: {template_data['name']}")
            else:
                strategy = StrategyTemplate(**template_data)
                self.db.add(strategy)
                logger.info(f"创建预置策略模板: {template_data['name']}")
            processed_count += 1

        try:
            self.db.commit()
            logger.info(f"策略模板初始化完成，共处理 {processed_count} 个")
        except Exception as e:
            self.db.rollback()
            logger.error(f"策略模板初始化失败: {e}", exc_info=True)
            raise

        return processed_count

    def get_all_strategies(
        self, include_disabled: bool = False
    ) -> List[StrategyTemplate]:
        """获取所有策略模板"""
        query = self.db.query(StrategyTemplate).order_by(
            StrategyTemplate.sort_order, StrategyTemplate.id
        )

        if not include_disabled:
            query = query.filter(StrategyTemplate.is_enabled == True)

        return query.all()

    def get_strategy(self, strategy_id: int) -> Optional[StrategyTemplate]:
        """根据ID获取策略"""
        return (
            self.db.query(StrategyTemplate)
            .filter(StrategyTemplate.id == strategy_id)
            .first()
        )

    def get_strategy_by_name(self, name: str) -> Optional[StrategyTemplate]:
        """根据名称获取策略"""
        return (
            self.db.query(StrategyTemplate)
            .filter(StrategyTemplate.name == name)
            .first()
        )

    def create_strategy(self, data: Dict[str, Any]) -> StrategyTemplate:
        """
        创建自定义策略

        Args:
            data: 策略数据字典

        Returns:
            创建的策略对象
        """
        required_fields = ["name", "task_template", "conditions_config"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"缺少必填字段: {field}")

        if self.get_strategy_by_name(data["name"]):
            raise ValueError(f"策略名称已存在: {data['name']}")

        strategy = StrategyTemplate(
            name=data["name"],
            description=data.get("description", ""),
            task_template=data["task_template"],
            is_system=False,
            is_enabled=data.get("is_enabled", True),
            conditions_config=data["conditions_config"],
            strategy_params=data.get("strategy_params"),
            sort_order=data.get("sort_order", 99),
        )

        self.db.add(strategy)
        self.db.commit()
        self.db.refresh(strategy)

        logger.info(f"创建自定义策略: ID={strategy.id}, Name={strategy.name}")
        return strategy

    def update_strategy(
        self, strategy_id: int, data: Dict[str, Any]
    ) -> StrategyTemplate:
        """
        更新策略

        Args:
            strategy_id: 策略ID
            data: 更新数据字典

        Returns:
            更新后的策略对象
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: ID={strategy_id}")

        if strategy.is_system and "name" in data:
            raise ValueError("系统预置模板不允许修改名称")

        updateable_fields = [
            "description",
            "is_enabled",
            "conditions_config",
            "strategy_params",
            "sort_order",
        ]

        if not strategy.is_system:
            updateable_fields.append("name")

        for field in updateable_fields:
            if field in data:
                setattr(strategy, field, data[field])

        strategy.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(strategy)

        logger.info(f"更新策略: ID={strategy_id}, Name={strategy.name}")
        return strategy

    def delete_strategy(self, strategy_id: int) -> bool:
        """
        删除策略

        Args:
            strategy_id: 策略ID

        Returns:
            是否删除成功
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: ID={strategy_id}")

        if strategy.is_system:
            raise ValueError("系统预置模板不允许删除")

        name = strategy.name
        self.db.delete(strategy)
        self.db.commit()

        logger.info(f"删除策略: ID={strategy_id}, Name={name}")
        return True

    def toggle_strategy(self, strategy_id: int) -> StrategyTemplate:
        """
        切换策略启用/禁用状态

        Args:
            strategy_id: 策略ID

        Returns:
            更新后的策略对象
        """
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: ID={strategy_id}")

        strategy.is_enabled = not strategy.is_enabled
        strategy.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(strategy)

        status = "启用" if strategy.is_enabled else "禁用"
        logger.info(f"{status}策略: ID={strategy_id}, Name={strategy.name}")
        return strategy

    def validate_conditions_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证条件配置是否有效

        Args:
            config: 条件配置字典

        Returns:
            (是否有效, 错误信息)
        """
        required_conditions = ["market_cap", "price", "trend", "limit_up", "call_auction"]

        for cond_name in required_conditions:
            if cond_name not in config:
                continue

            cond_config = config[cond_name]

            if cond_name == "market_cap":
                max_mv = cond_config.get("max_market_cap")
                if max_mv is None or max_mv <= 0:
                    return False, f"市值条件的最大值必须大于0"

            elif cond_name == "price":
                max_price = cond_config.get("max_close_price")
                if max_price is None or max_price <= 0:
                    return False, f"价格条件的最大值必须大于0"

            elif cond_name == "trend":
                days = cond_config.get("min_rise_days")
                if days is None or days <= 0:
                    return False, f"趋势条件的天数必须大于0"

            elif cond_name == "limit_up":
                count = cond_config.get("min_limit_up_count")
                if count is not None and count < 0:
                    return False, f"涨停次数不能为负数"

            elif cond_name == "call_auction":
                ratio_min = cond_config.get("call_auction_ratio_min")
                ratio_max = cond_config.get("call_auction_ratio_max")
                tr_min = cond_config.get("turnover_rate_min")
                tr_max = cond_config.get("turnover_rate_max")

                if ratio_min is not None and ratio_max is not None:
                    if ratio_min >= ratio_max:
                        return False, f"竞昨比最小值必须小于最大值"
                if tr_min is not None and tr_max is not None:
                    if tr_min >= tr_max:
                        return False, f"换手率最小值必须小于最大值"

        return True, ""

    def build_selection_task_from_template(
        self, strategy: StrategyTemplate
    ) -> Dict[str, Any]:
        """
        根据策略模板构建选股任务配置

        Args:
            strategy: 策略模板对象

        Returns:
            选股任务配置字典 (可用于通达信MCP查询)
        """
        from backend.services.tdx_selector import (
            BasicFilterCondition,
            MarketCapCondition,
            PriceCondition,
            TrendCondition,
            LimitUpCondition,
            CallAuctionCondition,
            SelectionTask,
        )

        config = strategy.conditions_config or {}
        conditions = []

        if "basic_filter" in config:
            bf_config = config["basic_filter"]
            conditions.append(
                BasicFilterCondition(
                    exclude_st=bf_config.get("exclude_st", True),
                    exclude_suspended=bf_config.get("exclude_suspended", True),
                    exclude_bse=bf_config.get("exclude_bse", True),
                )
            )

        if "market_cap" in config:
            mc_config = config["market_cap"]
            conditions.append(
                MarketCapCondition(max_market_cap=mc_config.get("max_market_cap", 2000))
            )

        if "price" in config:
            p_config = config["price"]
            conditions.append(
                PriceCondition(max_close_price=p_config.get("max_close_price", 500))
            )

        if "trend" in config:
            t_config = config["trend"]
            conditions.append(
                TrendCondition(min_rise_days=t_config.get("min_rise_days", 10))
            )

        if "limit_up" in config:
            lu_config = config["limit_up"]
            conditions.append(
                LimitUpCondition(
                    min_limit_up_count=lu_config.get("min_limit_up_count", 3),
                    limit_up_days=lu_config.get("limit_up_days", 100),
                )
            )

        if "call_auction" in config:
            ca_config = config["call_auction"]
            conditions.append(
                CallAuctionCondition(
                    call_auction_ratio_min=ca_config.get("call_auction_ratio_min", 4) / 100,
                    call_auction_ratio_max=ca_config.get("call_auction_ratio_max", 30) / 100,
                    turnover_rate_min=ca_config.get("turnover_rate_min", 0.5) / 100,
                    turnover_rate_max=ca_config.get("turnover_rate_max", 10) / 100,
                )
            )

        task = SelectionTask(
            task_id=f"custom_{strategy.id}",
            task_name=strategy.name,
            conditions=conditions,
        )

        return {
            "task": task,
            "query": task.build_query(),
            "conditions_count": len(conditions),
        }

    def close(self):
        """关闭数据库连接"""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def init_strategy_templates():
    """初始化策略模板 (应用启动时调用)"""
    service = StrategyTemplateService()
    try:
        count = service.initialize_default_strategies()
        logger.info(f"策略模板初始化完成，共 {count} 个新模板")
        return count
    finally:
        service.close()
