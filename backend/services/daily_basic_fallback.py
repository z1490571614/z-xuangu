"""每日指标数据的交易日前向回退读取工具。"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _previous_trade_dates(trade_date: str, calendar: Optional[Iterable[str]], max_lookback: int) -> list[str]:
    if not calendar:
        return []
    dates = sorted(str(d) for d in calendar if str(d) < trade_date)
    return list(reversed(dates[-max_lookback:]))


def get_daily_basic_with_previous_fallback(
    collector: Any,
    trade_date: str,
    calendar: Optional[Iterable[str]] = None,
    max_lookback: int = 5,
    purpose: str = "每日指标",
) -> pd.DataFrame:
    """
    读取 daily_basic；当选股日盘中尚未发布当日数据时，回退到最近可用交易日。

    这不是伪造数据：流通市值、流通股本、自由流通股本使用最近一次 Tushare
    已发布的官方 daily_basic，用于盘中选股的市值和竞价换手率分母。
    """
    tried = []
    for candidate in [trade_date] + _previous_trade_dates(trade_date, calendar, max_lookback):
        if candidate in tried:
            continue
        tried.append(candidate)
        df = collector.get_daily_basic(trade_date=candidate)
        if df is not None and not df.empty:
            if candidate != trade_date:
                logger.warning(
                    "%s: %s daily_basic 为空，已回退到最近可用交易日 %s",
                    purpose,
                    trade_date,
                    candidate,
                )
            return df

    logger.warning("%s: 未获取到 %s 及前 %s 个交易日的 daily_basic", purpose, trade_date, max_lookback)
    return pd.DataFrame()
