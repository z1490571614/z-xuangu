"""
交易日工具函数 - 增强版
集成 Tushare 真实交易日历，支持多种交易日计算
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Set
import logging
import os
from backend.utils.tushare_client import get_tushare_pro, get_tushare_token

logger = logging.getLogger(__name__)

# 缓存交易日历
_trading_calendar_cache = {}
_cache_expire_time = {}


def _get_tushare_calendar(exchange: str = 'SSE') -> Set[str]:
    """
    从 Tushare 获取交易日历
    
    Args:
        exchange: 交易所代码，SSE-上交所, SZSE-深交所
        
    Returns:
        交易日集合（YYYYMMDD格式）
    """
    cache_key = f"calendar_{exchange}"
    
    # 检查缓存是否有效（缓存有效期1天）
    if cache_key in _trading_calendar_cache:
        expire_time = _cache_expire_time.get(cache_key, 0)
        if datetime.now().timestamp() - expire_time < 86400:
            return _trading_calendar_cache[cache_key]
    
    try:
        token = get_tushare_token()
        if not token:
            logger.warning("TUSHARE_TOKEN 未配置，使用简单工作日判断")
            return set()

        pro = get_tushare_pro(token)
        if pro is None:
            logger.warning("TUSHARE_TOKEN 未配置，使用简单工作日判断")
            return set()
        # 获取最近一年的交易日历
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        df = pro.trade_cal(exchange=exchange, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            trading_days = set(df[df['is_open'] == 1]['cal_date'].tolist())
            _trading_calendar_cache[cache_key] = trading_days
            _cache_expire_time[cache_key] = datetime.now().timestamp()
            logger.info(f"从Tushare获取{exchange}交易日历，共{len(trading_days)}天")
            return trading_days
    except Exception as e:
        logger.warning(f"从Tushare获取交易日历失败，使用简单工作日判断: {e}")
    
    return set()


def is_trading_day(check_date: date, trading_calendar: Optional[Set[str]] = None) -> bool:
    """
    判断是否为交易日
    
    Args:
        check_date: 待检查的日期
        trading_calendar: 交易日历集合（YYYYMMDD格式），如果为None则自动获取
    
    Returns:
        是否为交易日
    """
    # 如果提供了交易日历，直接使用
    if trading_calendar:
        date_str = check_date.strftime('%Y%m%d')
        return date_str in trading_calendar
    
    # 尝试从Tushare获取交易日历
    calendar = _get_tushare_calendar()
    if calendar:
        date_str = check_date.strftime('%Y%m%d')
        return date_str in calendar
    
    # 降级到简单判断：周一到周五为交易日
    return check_date.weekday() < 5


def get_latest_trading_day(
    before_date: Optional[date] = None,
    trading_calendar: Optional[Set[str]] = None,
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
    trading_calendar: Optional[Set[str]] = None
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


def get_recent_trading_days(
    count: int,
    end_date: Optional[str] = None,
    trading_calendar: Optional[Set[str]] = None
) -> List[str]:
    """
    获取最近N个交易日
    
    Args:
        count: 交易日数量
        end_date: 结束日期（YYYYMMDD格式），None表示今天
        trading_calendar: 交易日历集合
    
    Returns:
        交易日列表（YYYYMMDD格式，按时间降序）
    """
    if end_date is None:
        end_date = get_latest_trading_day()
    
    year = int(end_date[:4])
    month = int(end_date[4:6])
    day = int(end_date[6:8])
    current_date = date(year, month, day)
    
    trading_days = []
    days_checked = 0
    max_days = count * 3  # 最多检查3倍天数
    
    while len(trading_days) < count and days_checked < max_days:
        if is_trading_day(current_date, trading_calendar):
            trading_days.append(current_date.strftime('%Y%m%d'))
        current_date -= timedelta(days=1)
        days_checked += 1
    
    return trading_days


def get_date_range_for_trading_days(
    trading_days: int,
    reference_date: Optional[str] = None
) -> tuple:
    """
    获取包含指定交易日数量的日期范围
    
    Args:
        trading_days: 需要包含的交易日数量
        reference_date: 参考日期（YYYYMMDD格式），None表示今天
    
    Returns:
        (start_date, end_date) 元组（YYYY-MM-DD HH:MM:SS格式）
    """
    if reference_date is None:
        reference_date = get_latest_trading_day()
    
    # 获取最近N个交易日
    recent_days = get_recent_trading_days(trading_days, reference_date)
    
    if recent_days:
        # 最早的交易日作为开始日期
        start_dt = datetime.strptime(recent_days[-1], '%Y%m%d')
        # 最新的交易日作为结束日期
        end_dt = datetime.strptime(recent_days[0], '%Y%m%d') + timedelta(days=1)
        
        return (
            start_dt.strftime('%Y-%m-%d 00:00:00'),
            end_dt.strftime('%Y-%m-%d 23:59:59')
        )
    
    # 如果没有找到交易日，返回简单的日期范围
    end_date = datetime.strptime(reference_date, '%Y%m%d') if reference_date else datetime.now()
    start_date = end_date - timedelta(days=trading_days * 2)
    
    return (
        start_date.strftime('%Y-%m-%d 00:00:00'),
        end_date.strftime('%Y-%m-%d 23:59:59')
    )

