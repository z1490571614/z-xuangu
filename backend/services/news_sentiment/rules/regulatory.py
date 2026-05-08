"""监管处罚规则"""
from typing import Dict, Any


def score_regulatory(text: str, facts: Dict[str, Any]) -> float:
    if "强制退市" in text or "退市风险" in text:
        return -5.0
    if "财务造假" in text or "欺诈发行" in text or "重大违法" in text:
        return -5.0
    if "立案调查" in text or "被立案" in text:
        return -4.0
    if "行政处罚" in text:
        return -3.0
    if "监管措施" in text:
        return -2.0
    return -1.0


def score_inquiry(text: str, facts: Dict[str, Any]) -> float:
    if "年报问询函" in text:
        return -1.5
    if "重组问询函" in text:
        return -1.2
    if "监管函" in text:
        return -1.0
    if "关注函" in text:
        return -0.8
    if "问询回复" in text:
        return 0.2
    return -0.5


def score_litigation(text: str, facts: Dict[str, Any]) -> float:
    score = 0.0
    if "重大诉讼" in text or "重大仲裁" in text:
        score -= 2.0
    elif "诉讼" in text or "仲裁" in text:
        score -= 1.0
    if "胜诉" in text:
        score += 1.0
    if "败诉" in text or "赔偿" in text:
        score -= 1.0
    return score


def score_unlock(facts: Dict[str, Any]) -> float:
    ratio = facts.get("unlock_ratio_to_float_cap")
    if ratio is not None:
        if ratio >= 0.3:
            return -3.0
        elif ratio >= 0.15:
            return -2.0
        elif ratio >= 0.05:
            return -1.0
        elif ratio >= 0.01:
            return -0.3
    return -0.5


def score_pledge(text: str) -> float:
    if "补充质押" in text:
        return -1.0
    if "质押比例较高" in text:
        return -1.5
    if "解除质押" in text:
        return 0.8
    if "质押" in text:
        return -0.5
    return 0.0
