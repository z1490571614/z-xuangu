"""
默认竞价接力 V2 三目标标签辅助函数。
"""
from typing import Any, Optional


EPSILON = 1e-6


def _get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    getter = getattr(row, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            pass
    return getattr(row, key, default)


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _near_limit_threshold(limit_price: Any) -> Optional[float]:
    price = _num(limit_price)
    if price is None or price <= 0:
        return None
    return price * 0.997


def _is_one_line_limit_up(row: Any, limit_price: Any) -> Optional[int]:
    high = _num(_get(row, "high"))
    threshold = _near_limit_threshold(limit_price)
    prices = [_num(_get(row, key)) for key in ("open", "high", "low", "close")]
    if threshold is None or high is None or any(price is None for price in prices):
        return None
    return int(high + EPSILON >= float(limit_price) and all(price >= threshold for price in prices))


def build_t0_limit_label(row: Any, limit_price: Any) -> Optional[int]:
    """T 日真实触板且收板记为成功；未知标签返回 None。"""
    limit = _num(limit_price)
    close_threshold = _near_limit_threshold(limit)
    high = _num(_get(row, "high"))
    close = _num(_get(row, "close"))
    if limit is None or close_threshold is None or high is None or close is None:
        return None
    return int(high + EPSILON >= limit and close >= close_threshold)


def build_t0_limit_audit(row: Any, limit_price: Any) -> dict[str, Optional[int]]:
    label = build_t0_limit_label(row, limit_price)
    return {
        "label_t0_limit_success": label,
        "is_t0_limit_up": label,
        "is_t0_one_line_limit_up": _is_one_line_limit_up(row, limit_price),
    }


def _return_pct(row: Any, direct_keys: tuple[str, ...], price_key: str) -> Optional[float]:
    for key in direct_keys:
        value = _num(_get(row, key))
        if value is not None:
            return value
    price = _num(_get(row, price_key))
    pre_close = _num(_get(row, "pre_close"))
    if price is None or pre_close is None or pre_close <= 0:
        return None
    return (price - pre_close) / pre_close * 100


def build_t1_premium_label(
    row: Any,
    open_threshold: float = 3,
    high_threshold: float = 5,
    close_threshold: float = 3,
) -> Optional[int]:
    """T+1 开盘、高点、收盘任一溢价达到阈值记为成功；未知返回 None。"""
    open_return = _return_pct(row, ("t1_open_return", "open_return"), "open")
    high_return = _return_pct(row, ("t1_high_return", "high_return"), "high")
    close_return = _return_pct(row, ("t1_close_return", "close_return"), "close")
    known_returns = [
        value
        for value in (open_return, high_return, close_return)
        if value is not None
    ]
    if not known_returns:
        return None
    return int(
        (open_return is not None and open_return >= open_threshold)
        or (high_return is not None and high_return >= high_threshold)
        or (close_return is not None and close_return >= close_threshold)
    )


def build_t1_continue_label(row: Any, limit_price: Any) -> Optional[int]:
    """T+1 真实触板且收板记为连板成功；未知标签返回 None。"""
    limit = _num(limit_price)
    close_threshold = _near_limit_threshold(limit)
    high = _num(_get(row, "high"))
    close = _num(_get(row, "close"))
    if limit is None or close_threshold is None or high is None or close is None:
        return None
    return int(high + EPSILON >= limit and close >= close_threshold)


def build_t1_continue_audit(row: Any, limit_price: Any) -> dict[str, Optional[int]]:
    label = build_t1_continue_label(row, limit_price)
    return {
        "label_t1_continue_limit": label,
        "is_t1_limit_up": label,
        "is_t1_one_line_limit_up": _is_one_line_limit_up(row, limit_price),
    }
