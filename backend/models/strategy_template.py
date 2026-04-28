"""
选股策略模板模型

支持策略的持久化存储和管理：
- 预置策略模板（系统内置）
- 用户自定义策略
- 策略参数配置
- 启用/禁用状态
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON
from sqlalchemy.sql import func
from backend.database import Base


class StrategyTemplate(Base):
    """选股策略模板表"""

    __tablename__ = "strategy_template"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True, comment="策略名称")
    description = Column(Text, nullable=True, comment="策略描述")

    task_template = Column(
        String(50),
        nullable=False,
        default="custom",
        comment="任务模板类型: default/conservative/aggressive/custom",
    )

    is_system = Column(
        Boolean,
        default=False,
        comment="是否为系统预置模板（不可删除）",
    )

    is_enabled = Column(
        Boolean,
        default=True,
        comment="是否启用",
    )

    conditions_config = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="选股条件配置 (JSON格式)",
    )

    strategy_params = Column(
        JSON,
        nullable=True,
        comment="策略参数 (JSON格式，用于高级自定义)",
    )

    sort_order = Column(Integer, default=0, comment="排序顺序")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<StrategyTemplate(id={self.id}, name={self.name}, template={self.task_template})>"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_template": self.task_template,
            "is_system": self.is_system,
            "is_enabled": self.is_enabled,
            "conditions_config": self.conditions_config or {},
            "strategy_params": self.strategy_params or {},
            "sort_order": self.sort_order,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }
