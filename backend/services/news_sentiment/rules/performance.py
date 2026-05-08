"""业绩类规则——同比优先，环比只做修正，小幅下降输出 weak_negative"""
from typing import Dict, Any


def score_performance(facts: Dict[str, Any], text: str = "") -> Dict[str, Any]:
    scores = []
    matched_rules = []
    reason_parts = []
    final_score = 0.0

    revenue_yoy = facts.get("revenue_yoy")
    net_profit_yoy = facts.get("net_profit_yoy")
    is_qoq_turnaround = facts.get("is_qoq_turnaround", False)

    # 营收同比
    if revenue_yoy is not None:
        if revenue_yoy < 0:
            if revenue_yoy <= -20:
                final_score -= 1.0
                matched_rules.append("REVENUE_YOY_DROP_GE_20")
            else:
                final_score -= 0.3
                matched_rules.append("REVENUE_YOY_DROP_LT_20")
            reason_parts.append(f"营业收入同比下降{abs(revenue_yoy)}%")
        elif revenue_yoy > 0:
            if revenue_yoy >= 20:
                final_score += 0.8
                matched_rules.append("REVENUE_YOY_GROWTH_GE_20")
            else:
                final_score += 0.3
                matched_rules.append("REVENUE_YOY_GROWTH_LT_20")
            reason_parts.append(f"营业收入同比增长{revenue_yoy}%")

    # 净利润同比
    if net_profit_yoy is not None:
        if net_profit_yoy < 0:
            if net_profit_yoy <= -80:
                final_score -= 3.0
                matched_rules.append("NET_PROFIT_YOY_DROP_GE_80")
            elif net_profit_yoy <= -50:
                final_score -= 2.0
                matched_rules.append("NET_PROFIT_YOY_DROP_GE_50")
            elif net_profit_yoy <= -20:
                final_score -= 1.0
                matched_rules.append("NET_PROFIT_YOY_DROP_GE_20")
            else:
                final_score -= 0.6
                matched_rules.append("NET_PROFIT_YOY_DROP_LT_20")
            reason_parts.append(f"净利润同比下降{abs(net_profit_yoy)}%")
        elif net_profit_yoy > 0:
            if net_profit_yoy >= 300:
                final_score += 4.0
                matched_rules.append("NET_PROFIT_YOY_GROWTH_GE_300")
            elif net_profit_yoy >= 100:
                final_score += 3.0
                matched_rules.append("NET_PROFIT_YOY_GROWTH_GE_100")
            elif net_profit_yoy >= 50:
                final_score += 2.0
                matched_rules.append("NET_PROFIT_YOY_GROWTH_GE_50")
            elif net_profit_yoy >= 20:
                final_score += 1.0
                matched_rules.append("NET_PROFIT_YOY_GROWTH_GE_20")
            else:
                final_score += 0.4
                matched_rules.append("NET_PROFIT_YOY_GROWTH_LT_20")
            reason_parts.append(f"净利润同比增长{net_profit_yoy}%")

    # 环比扭亏只能弱修正
    if is_qoq_turnaround:
        if (net_profit_yoy is not None and net_profit_yoy < 0) or (revenue_yoy is not None and revenue_yoy < 0):
            final_score += 0.2
            matched_rules.append("QOQ_TURNAROUND_WEAK_OFFSET")
            reason_parts.append("环比扭亏为盈，但同比仍下降，仅作为弱改善项")
        else:
            final_score += 0.8
            matched_rules.append("QOQ_TURNAROUND_POSITIVE")
            reason_parts.append("环比扭亏为盈")

    # 营收和净利润同比均下降，不允许转正
    if (
        revenue_yoy is not None and revenue_yoy < 0
        and net_profit_yoy is not None and net_profit_yoy < 0
        and final_score >= 0
    ):
        final_score = -0.3
        matched_rules.append("FORCE_NEGATIVE_WHEN_BOTH_DROP")
        reason_parts.append("营业收入和净利润同比均下降")

    # 其他语义
    if facts.get("is_turnaround"):
        final_score += 2.5
        matched_rules.append("IS_TURNAROUND")
        reason_parts.append("扭亏为盈")
    if facts.get("is_loss"):
        final_score -= 2.0
        matched_rules.append("IS_LOSS")
    if facts.get("is_loss_reducing"):
        final_score += 0.8
        matched_rules.append("IS_LOSS_REDUCING")
    if facts.get("is_loss_expanding"):
        final_score -= 2.5
        matched_rules.append("IS_LOSS_EXPANDING")
    if facts.get("is_non_recurring_gain"):
        final_score -= 0.8
        matched_rules.append("NON_RECURRING_GAIN")
    if facts.get("is_above_expectation"):
        final_score += 1.0
        matched_rules.append("ABOVE_EXPECTATION")
    if facts.get("is_below_expectation"):
        final_score -= 1.5
        matched_rules.append("BELOW_EXPECTATION")

    final_score = max(-5.0, min(5.0, final_score))

    return {
        "raw_score": final_score,
        "matched_rules": matched_rules,
        "reason_parts": reason_parts,
    }


def get_performance_risk_flags(facts: Dict[str, Any], text: str) -> list:
    flags = []
    if facts.get("net_profit_yoy") is not None and facts.get("deducted_profit_yoy") is None:
        flags.append("missing_deducted_profit_yoy")
    if "非经常性损益" in text:
        flags.append("non_recurring_gain_risk")
    return flags
