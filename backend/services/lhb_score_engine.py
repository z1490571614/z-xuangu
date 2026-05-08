"""统一龙虎榜席位方向分析。

本模块只负责把龙虎榜明细归一成可复用特征，不直接决定 alpha 或风险分。
上层评分模块再按各自语义把这些特征映射成分数。
"""
from typing import Any, Dict

from backend.services.seat_library import match_seat_tag


DUMP_TAGS = {"核按钮", "量化", "散户"}


def get_lhb_seat_net_buy(seat: Dict[str, Any]) -> float:
    """优先使用席位净买额，缺失时由买入额-卖出额推导。"""
    for key in ("net_buy", "net_amount", "net_buy_amount"):
        value = seat.get(key)
        if value is not None:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                pass
    try:
        return float(seat.get("buy", 0) or 0) - float(seat.get("sell", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def analyze_lhb_seat_effects(lhb_data: Dict[str, Any]) -> Dict[str, Any]:
    """把龙虎榜席位拆成统一方向特征。"""
    buy_top5 = lhb_data.get("buy_top5", []) or []
    sell_top5 = lhb_data.get("sell_top5", []) or []

    result: Dict[str, Any] = {
        "premium_net_buy": [],
        "premium_net_sell": [],
        "dump_net_buy": [],
        "dump_net_sell": [],
        "all_seats": [],
        "buy_top3_scatter_count": 0,
        "buy_top3_premium_count": 0,
    }

    for index, seat in enumerate(buy_top5 + sell_top5):
        exalter = seat.get("exalter", "")
        tag, detail_type = match_seat_tag(exalter)
        net_buy = get_lhb_seat_net_buy(seat)
        source_side = "buy" if index < len(buy_top5) else "sell"
        item = {
            "exalter": exalter,
            "tag": tag,
            "detail_type": detail_type,
            "net_buy": net_buy,
            "source_side": source_side,
            "raw": seat,
        }
        result["all_seats"].append(item)

        if tag == "高溢价":
            if net_buy >= 0:
                result["premium_net_buy"].append(item)
            else:
                result["premium_net_sell"].append(item)
        elif tag in DUMP_TAGS:
            if net_buy > 0:
                result["dump_net_buy"].append(item)
            else:
                result["dump_net_sell"].append(item)

    for seat in buy_top5[:3]:
        tag, _ = match_seat_tag(seat.get("exalter", ""))
        if tag == "散户":
            result["buy_top3_scatter_count"] += 1
        elif tag == "高溢价":
            result["buy_top3_premium_count"] += 1

    return result
