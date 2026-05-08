"""回购规则"""
from typing import Dict, Any


def score_buyback(facts: Dict[str, Any], text: str) -> float:
    score = 0.0
    ratio = facts.get("buyback_ratio_to_market_cap")
    if ratio is not None:
        if ratio >= 0.03:
            score += 2.5
        elif ratio >= 0.01:
            score += 1.5
        elif ratio >= 0.003:
            score += 0.5
    else:
        score += 0.5
    return score


def get_certainty_for_buyback(text: str) -> str:
    if "拟回购" in text or "回购方案" in text:
        return "planned"
    if "已回购" in text or "回购完成" in text:
        return "completed"
    return "unknown"
