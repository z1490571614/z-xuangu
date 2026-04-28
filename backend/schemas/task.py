"""
任务相关数据模型
"""
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class TaskCreate(BaseModel):
    """创建任务请求"""

    name: str = Field(description="任务名称")
    task_type: str = Field(description="任务类型")
    cron_expression: str = Field(description="Cron表达式")
    config: Optional[str] = Field(default=None, description="任务配置(JSON字符串)")
    description: Optional[str] = Field(default=None, description="任务描述")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "每日选股任务",
                "task_type": "stock_selection",
                "cron_expression": "25 9 * * 1-5",
                "config": "{}",
                "description": "每个交易日9:25执行选股"
            }
        }


class TaskUpdate(BaseModel):
    """更新任务请求"""

    name: Optional[str] = Field(default=None, description="任务名称")
    cron_expression: Optional[str] = Field(default=None, description="Cron表达式")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    config: Optional[str] = Field(default=None, description="任务配置")
    description: Optional[str] = Field(default=None, description="任务描述")


class TaskResponse(BaseModel):
    """任务响应"""

    id: int = Field(description="任务ID")
    name: str = Field(description="任务名称")
    task_type: str = Field(description="任务类型")
    cron_expression: str = Field(description="Cron表达式")
    enabled: bool = Field(description="是否启用")
    last_run_time: Optional[datetime] = Field(default=None, description="上次运行时间")
    next_run_time: Optional[datetime] = Field(default=None, description="下次运行时间")
    description: Optional[str] = Field(default=None, description="任务描述")

    class Config:
        from_attributes = True


class TaskLogResponse(BaseModel):
    """任务日志响应"""

    id: int = Field(description="日志ID")
    task_type: str = Field(description="任务类型")
    trigger_time: datetime = Field(description="触发时间")
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    status: str = Field(description="状态")
    error_message: Optional[str] = Field(default=None, description="错误信息")

    class Config:
        from_attributes = True
