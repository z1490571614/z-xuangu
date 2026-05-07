"""
龙虎榜席位评分模块

直接使用 lhb_service.analyze_lhb() 的结果 + seat_library 的席位判断函数，
不重复创建分类逻辑。
"""
import logging
from typing import Dict, Any, List, Optional

from backend.services.seat_library import (
    is_premium_seat, is_institutional_seat,
    is_knock_seat, is_scatter_seat, is_quant_seat,
)

logger = logging.getLogger(__name__)


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
    buy_list = lhb_data.get("buy_top5", [])
    sell_list = lhb_data.get("sell_top5", [])

    # ---- 买入席位加分 ----
    for seat in buy_list:
        exalter = seat.get("exalter", "")
        # 使用 seat_library 已有判断函数
        if is_premium_seat(exalter):
            bonus_score += 8
            bonus_tips.append(f"高溢价游资买入({exalter[:12]}...)")
        elif is_institutional_seat(exalter):
            bonus_score += 5
            bonus_tips.append(f"机构买入({exalter[:12]}...)")

    # ---- 卖出席位扣分 ----
    for seat in sell_list:
        exalter = seat.get("exalter", "")
        if is_knock_seat(exalter):
            penalty_score -= 12
            penalty_tips.append(f"核按钮席位卖出({exalter[:12]}...)")
        elif is_scatter_seat(exalter):
            penalty_score -= 4
            penalty_tips.append(f"散户席位卖出({exalter[:12]}...)")
        elif is_quant_seat(exalter):
            penalty_score -= 6
            penalty_tips.append(f"量化席位卖出({exalter[:12]}...)")

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
    if buy_list and len(buy_list) >= 3:
        scatter_count = sum(1 for s in buy_list[:3] if is_scatter_seat(s.get("exalter", "")))
        premium_count = sum(1 for s in buy_list[:3] if is_premium_seat(s.get("exalter", "")))
        if scatter_count >= 2:
            penalty_score -= 3
            penalty_tips.append("散户集中买入（需警惕次日抛压）")
        elif premium_count >= 2:
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
