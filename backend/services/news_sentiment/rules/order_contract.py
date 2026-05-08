"""订单合同规则"""
from typing import Dict, Any


def score_order_contract(facts: Dict[str, Any], text: str) -> float:
    score = 0.0
    ratio = facts.get("contract_to_revenue_ratio")
    if ratio is not None:
        if ratio >= 0.5:
            score += 3.5
        elif ratio >= 0.2:
            score += 2.5
        elif ratio >= 0.1:
            score += 1.5
        elif ratio >= 0.03:
            score += 0.5
    else:
        score += 0.5
    return score


def get_certainty_for_order(text: str) -> str:
    if "框架协议" in text:
        return "framework"
    if "存在不确定性" in text:
        return "uncertain"
    if "中标" in text or "签订合同" in text or "签署" in text:
        return "signed"
    return "unknown"
