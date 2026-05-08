"""增持/减持规则"""
from typing import Dict, Any


def score_reduce_holding(facts: Dict[str, Any]) -> float:
    score = 0.0
    htype = facts.get("holder_type")
    if htype in ["控股股东", "实际控制人", "实控人"]:
        score -= 2.5
    elif htype in ["董事", "高管", "董监高", "重要股东"]:
        score -= 1.5
    else:
        score -= 1.0
    ratio = facts.get("reduce_ratio")
    if ratio is not None:
        if ratio >= 5:
            score -= 2.5
        elif ratio >= 2:
            score -= 1.5
        elif ratio >= 1:
            score -= 0.8
    if facts.get("is_clearance"):
        score -= 2.0
    if facts.get("is_passive"):
        score *= 0.5
    if facts.get("is_completed"):
        score += 0.5
    return score


def score_increase_holding(facts: Dict[str, Any], text: str) -> float:
    score = 0.0
    htype = facts.get("holder_type")
    if htype in ["控股股东", "实际控制人", "实控人", "董事长"]:
        score += 1.5
    elif htype in ["董监高", "高管"]:
        score += 1.0
    else:
        score += 0.5
    amount = facts.get("increase_amount")
    if amount is not None:
        if amount >= 100_000_000:
            score += 1.5
        elif amount >= 30_000_000:
            score += 1.0
        elif amount >= 5_000_000:
            score += 0.3
    return score


def get_certainty_for_holding(text: str) -> str:
    if "拟增持" in text or "计划增持" in text or "拟减持" in text or "计划减持" in text:
        return "planned"
    if "增持完成" in text or "已增持" in text or "减持计划实施完毕" in text:
        return "completed"
    return "unknown"
