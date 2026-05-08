"""
龙虎榜席位评分模块

直接使用 lhb_service.analyze_lhb() 的结果 + seat_library 的席位判断函数，
不重复创建分类逻辑。
"""
import logging
from typing import Dict, Any, List, Optional

from backend.services.lhb_score_engine import analyze_lhb_seat_effects

logger = logging.getLogger(__name__)


def _premium_alpha_value(seat: Dict[str, Any]) -> int:
    if seat.get("detail_type") in ("机构", "北向"):
        return 5
    return 8


def _premium_alpha_label(seat: Dict[str, Any]) -> str:
    if seat.get("detail_type") == "机构":
        return "机构"
    if seat.get("detail_type") == "北向":
        return "北向"
    return "高溢价游资"


def _dump_alpha_value(seat: Dict[str, Any]) -> int:
    tag = seat.get("tag")
    if tag == "核按钮":
        return 12
    if tag == "量化":
        return 6
    if tag == "散户":
        return 4
    return 0


def calculate_lhb_alpha(lhb_data: Optional[Dict]) -> Dict[str, Any]:
    """
    计算龙虎榜席位净加减分

    使用 lhb_service 已有的 seat_library 函数判断席位类型，
     dragon_leader 专属的权重体系叠加其上。

    Returns:
        {
            "lhb_bonus_score": int,
            "lhb_penalty_score": int,
            "lhb_alpha_score": int,
            "lhb_structure": str,
            "tips": list[str],
            "data_status": str
        }
    """
    if not lhb_data or lhb_data.get("data_status") != "available":
        return {
            "lhb_bonus_score": 0,
            "lhb_penalty_score": 0,
            "lhb_alpha_score": 0,
            "lhb_structure": "暂无龙虎榜数据",
            "tips": ["当日未上龙虎榜，席位因子不参与评分"],
            "data_status": "not_applicable"
        }

    bonus_score = 0
    penalty_score = 0
    bonus_tips: List[str] = []
    penalty_tips: List[str] = []
    effects = analyze_lhb_seat_effects(lhb_data)

    # ---- 席位方向评分：统一使用净买入方向，不再只看买榜/卖榜位置 ----
    for seat in effects["premium_net_buy"]:
        value = _premium_alpha_value(seat)
        label = _premium_alpha_label(seat)
        bonus_score += value
        bonus_tips.append(f"{label}净买入({seat['exalter'][:12]}...)")

    for seat in effects["premium_net_sell"]:
        value = _premium_alpha_value(seat)
        label = _premium_alpha_label(seat)
        penalty_score -= value
        penalty_tips.append(f"{label}净卖出({seat['exalter'][:12]}...)")

    for seat in effects["dump_net_buy"]:
        value = _dump_alpha_value(seat)
        if value:
            penalty_score -= value
            penalty_tips.append(f"{seat['tag']}席位净买入({seat['exalter'][:12]}...)")

    for seat in effects["dump_net_sell"]:
        value = _dump_alpha_value(seat)
        if value:
            bonus_score += value
            bonus_tips.append(f"{seat['tag']}席位净卖出({seat['exalter'][:12]}...)")

    # ---- 买榜结构判断 ----
    net_amount = lhb_data.get("net_amount", 0) or 0
    buy_amount = lhb_data.get("buy_amount", 0) or 0
    sell_amount = lhb_data.get("sell_amount", 0) or 0

    if buy_amount > 0 and sell_amount > 0:
        ratio = buy_amount / sell_amount
        if ratio > 1.5:
            bonus_score += 3
            bonus_tips.append("买榜明显强于卖榜")
        elif ratio < 0.6:
            penalty_score -= 3
            penalty_tips.append("卖榜明显强于买榜")

    if net_amount > 50000000:
        bonus_score += 2
        bonus_tips.append("净买入超5000万")
    elif net_amount < -50000000:
        penalty_score -= 3
        penalty_tips.append("净卖出超5000万")

    # ---- 散户集中买入（需警惕次日抛压） ----
    if effects["all_seats"]:
        if effects["buy_top3_scatter_count"] >= 2:
            penalty_score -= 3
            penalty_tips.append("散户集中买入（需警惕次日抛压）")
        elif effects["buy_top3_premium_count"] >= 2:
            bonus_score += 3
            bonus_tips.append("多路高溢价游资合力")

    alpha_score = bonus_score + penalty_score
    alpha_score = max(-20, min(20, alpha_score))

    tips = bonus_tips[:3] + penalty_tips[:3]

    if not bonus_tips and not penalty_tips:
        structure = "均衡"
    elif bonus_score > abs(penalty_score):
        structure = "偏多"
    elif bonus_score < abs(penalty_score):
        structure = "偏空"
    else:
        structure = "分歧"

    return {
        "lhb_bonus_score": bonus_score,
        "lhb_penalty_score": penalty_score,
        "lhb_alpha_score": alpha_score,
        "lhb_structure": structure,
        "tips": tips,
        "data_status": "available"
    }
