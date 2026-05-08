"""评分调度器——按事件类型分发到各规则模块"""
from typing import Dict, Any, Tuple

from backend.services.news_sentiment.rules.performance import score_performance, get_performance_risk_flags
from backend.services.news_sentiment.rules.restructure import score_restructure
from backend.services.news_sentiment.rules.holding_change import (
    score_reduce_holding, score_increase_holding, get_certainty_for_holding,
)
from backend.services.news_sentiment.rules.buyback import score_buyback, get_certainty_for_buyback
from backend.services.news_sentiment.rules.order_contract import score_order_contract, get_certainty_for_order
from backend.services.news_sentiment.rules.regulatory import (
    score_regulatory, score_inquiry, score_litigation, score_unlock, score_pledge,
)
from backend.services.news_sentiment.rules.process import (
    score_policy, score_product_tech, score_capacity, score_personnel,
    score_clarification, score_abnormal_movement, score_risk_warning, score_process,
)
from backend.services.news_sentiment.constants import CERTAINTY_TYPES


def score_event(event_type: str, text: str, facts: Dict[str, Any]) -> Tuple[float, str, list, str]:
    """返回 (raw_score, event_subtype, risk_flags, certainty)"""
    certainty = "unknown"
    risk_flags = []
    matched_rules = []
    event_subtype = ""
    score = 0.0

    if event_type == "performance":
        result = score_performance(facts, text)
        score = result["raw_score"]
        risk_flags = get_performance_risk_flags(facts, text)
        matched_rules.extend(result["matched_rules"])
        if facts.get("is_turnaround"):
            event_subtype = "turnaround"
        elif facts.get("net_profit_yoy") is not None and facts["net_profit_yoy"] >= 100:
            event_subtype = "net_profit_growth"
        elif facts.get("net_profit_yoy") is not None and facts["net_profit_yoy"] < -50:
            event_subtype = "net_profit_drop"

    elif event_type == "restructure":
        score = score_restructure(text, facts)
        if "终止" in text or "失败" in text:
            event_subtype = "termination"
        elif "不构成重大调整" in text:
            event_subtype = "minor_adjustment"
        elif "筹划" in text:
            event_subtype = "planning"
        elif "拟收购" in text or "拟购买" in text:
            event_subtype = "planned_acquire"

    elif event_type == "reduce_holding":
        score = score_reduce_holding(facts)
        certainty = get_certainty_for_holding(text)
        if facts.get("is_clearance"):
            event_subtype = "clearance"
        elif facts.get("is_passive"):
            event_subtype = "passive"
        else:
            event_subtype = "voluntary"

    elif event_type == "increase_holding":
        score = score_increase_holding(facts, text)
        certainty = get_certainty_for_holding(text)

    elif event_type == "buyback":
        score = score_buyback(facts, text)
        certainty = get_certainty_for_buyback(text)

    elif event_type == "order_contract":
        score = score_order_contract(facts, text)
        certainty = get_certainty_for_order(text)

    elif event_type == "regulatory":
        score = score_regulatory(text, facts)
        certainty = "completed"

    elif event_type == "inquiry":
        score = score_inquiry(text, facts)

    elif event_type == "risk_warning":
        score = score_risk_warning(text)
        event_subtype = "trading_risk_warning"
        certainty = "completed"

    elif event_type == "litigation":
        score = score_litigation(text, facts)

    elif event_type == "unlock":
        score = score_unlock(facts)

    elif event_type == "pledge":
        score = score_pledge(text)

    elif event_type == "policy":
        score = score_policy(text)
        certainty = "known"

    elif event_type == "product_tech":
        score = score_product_tech(text)

    elif event_type == "capacity":
        score = score_capacity(text)

    elif event_type == "personnel":
        score = score_personnel(text)

    elif event_type == "clarification":
        score = score_clarification(text)

    elif event_type == "abnormal_movement":
        score = score_abnormal_movement(text)

    elif event_type == "process":
        score = score_process(text)
        certainty = "completed"

    return score, event_subtype, risk_flags, certainty


def merge_event_scores(event_scores: list) -> Tuple[float, str, list]:
    """合并多事件分数"""
    positive_score = sum(s for s in event_scores if s > 0)
    negative_score = sum(s for s in event_scores if s < 0)
    min_negative = min(event_scores) if event_scores else 0

    risk_flags = []
    if min_negative <= -3.0 and positive_score > 0:
        final_score = min_negative + positive_score * 0.2
        risk_flags.append("positive_event_overridden_by_major_risk")
    elif positive_score > 0 and negative_score < 0:
        final_score = positive_score + negative_score
    else:
        final_score = positive_score + negative_score

    final_score = max(-5.0, min(5.0, final_score))
    return final_score, risk_flags
