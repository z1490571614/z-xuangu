"""
交易日工具函数
"""
from datetime import date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def is_trading_day(check_date: date, trading_calendar: Optional[set] = None) -> bool:
    """
    判断是否为交易日

    Args:
        check_date: 待检查的日期
        trading_calendar: 交易日历集合（YYYYMMDD格式），如果为None则使用简单逻辑

    Returns:
        是否为交易日
    """
    if trading_calendar:
        date_str = check_date.strftime('%Y%m%d')
        return date_str in trading_calendar

    return check_date.weekday() < 5


def get_latest_trading_day(
    before_date: Optional[date] = None,
    trading_calendar: Optional[set] = None,
    max_days_back: int = 30
) -> str:
    """
    获取最新的交易日

    Args:
        before_date: 基准日期，None表示今天
        trading_calendar: 交易日历集合
        max_days_back: 最大回溯天数

    Returns:
        最新交易日（YYYYMMDD格式）
    """
    if before_date is None:
        before_date = date.today()

    for i in range(max_days_back):
        check_date = before_date - timedelta(days=i)
        if is_trading_day(check_date, trading_calendar):
            return check_date.strftime('%Y%m%d')

    logger.warning(f"在最近{max_days_back}天内未找到交易日，返回基准日期")
    return before_date.strftime('%Y%m%d')


def get_previous_trading_day(
    current_date: str,
    trading_calendar: Optional[set] = None
) -> str:
    """
    获取前一个交易日

    Args:
        current_date: 当前交易日（YYYYMMDD格式）
        trading_calendar: 交易日历集合

    Returns:
        前一个交易日（YYYYMMDD格式）
    """
    year = int(current_date[:4])
    month = int(current_date[4:6])
    day = int(current_date[6:8])
    check_date = date(year, month, day)

    for i in range(1, 30):
        prev_date = check_date - timedelta(days=i)
        if is_trading_day(prev_date, trading_calendar):
            return prev_date.strftime('%Y%m%d')

    return current_date
