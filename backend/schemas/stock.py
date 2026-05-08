"""
选股相关数据模型
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class SelectRequest(BaseModel):
    """选股请求"""
    trade_date: Optional[str] = Field(default=None, description="交易日期（YYYYMMDD格式）")
    notify: bool = Field(default=False, description="是否发送通知")
    task_template: Optional[str] = Field(default="default", description="任务模板：default/conservative/aggressive")
    custom_tasks: Optional[List[Any]] = Field(default=None, description="自定义任务")
    strategy_id: Optional[int] = Field(default=None, description="策略ID")
    min_seal_rate: Optional[float] = Field(default=None, description="最小封板率（%）")
    period_days: int = Field(default=100, description="封板率计算周期")
    min_open_change_pct: Optional[float] = Field(default=-3.0, description="最小开盘涨幅（%）")

    class Config:
        json_schema_extra = {
            "example": {
                "trade_date": "20240119",
                "notify": False,
                "task_template": "default"
            }
        }


class StockInfo(BaseModel):
    """股票信息"""
    ts_code: str = Field(description="股票代码")
    name: Optional[str] = Field(default=None, description="股票名称")
    close_price: Optional[float] = Field(default=None, description="收盘价")
    change_pct: Optional[float] = Field(default=None, description="涨跌幅（%）")
    pre_change_pct: Optional[float] = Field(default=None, description="昨涨幅（%）")
    open_change_pct: Optional[float] = Field(default=None, description="开涨幅（%）")
    auction_ratio: Optional[float] = Field(default=None, description="竞昨比（%）")
    auction_turnover_rate: Optional[float] = Field(default=None, description="竞价换手率（%）")
    limit_up_count: Optional[int] = Field(default=None, description="近百日涨停次数")
    touch_days: Optional[int] = Field(default=None, description="近百日触板天数")
    limit_up_days: Optional[int] = Field(default=None, description="近百日涨停天数")
    seal_rate: Optional[float] = Field(default=None, description="封板率（%）")
    rise_10d_pct: Optional[float] = Field(default=None, description="10日涨幅（%）")
    circ_mv: Optional[float] = Field(default=None, description="流通市值（亿）")
    industry: Optional[str] = Field(default=None, description="所属行业")
    concept: Optional[str] = Field(default=None, description="概念板块")

    # 涨停榜单（同花顺）数据
    lu_desc: Optional[str] = Field(default=None, description="涨停原因")
    lu_tag: Optional[str] = Field(default=None, description="涨停标签（如5天3板）")
    lu_status: Optional[str] = Field(default=None, description="涨停状态（如换手板）")
    lu_open_num: Optional[int] = Field(default=None, description="打开次数")
    limit_up_suc_rate: Optional[float] = Field(default=None, description="近一年涨停封板率")
    latest_lu_date: Optional[str] = Field(default=None, description="最新涨停日期")

    # 每日基本面数据
    prev_turnover_rate: Optional[float] = Field(default=None, description="上一日换手率（%）")


class SelectionResult(BaseModel):
    """选股结果"""
    record_id: Optional[int] = Field(default=None, description="记录ID")
    trade_date: str = Field(description="交易日期")
    total_count: int = Field(description="阶段1选出股票数")
    passed_count: int = Field(description="最终通过筛选股票数")
    pass_rate: Optional[float] = Field(default=None, description="通过率")
    stocks: List[StockInfo] = Field(default_factory=list, description="股票列表")
    execution_time: Optional[float] = Field(default=None, description="执行时间（秒）")
    notification_sent: Optional[bool] = Field(default=None, description="是否已发送通知")
    phase1: Optional[dict] = Field(default=None, description="阶段1信息")
    phase2: Optional[dict] = Field(default=None, description="阶段2信息")
    phase3: Optional[dict] = Field(default=None, description="阶段3信息")


class SelectionRecordResponse(BaseModel):
    """选股记录响应"""
    id: int = Field(description="记录ID")
    execute_time: str = Field(description="执行时间")
    trade_date: str = Field(description="交易日期")
    total_count: int = Field(description="股票数量")
    status: str = Field(description="状态")
    execution_time: Optional[float] = Field(default=None, description="执行时间（秒）")
    notification_sent: bool = Field(default=False, description="是否已发送通知")

    class Config:
        from_attributes = True
