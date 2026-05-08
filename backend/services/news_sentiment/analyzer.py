"""情感分析主入口

主流程：
normalize → classify_scope → (分流: multi_stock → 局部判断 / single_stock → 事件识别)
         → extract → score_each → merge → apply_certainty → build_output
"""
from typing import Dict, Any, List, Optional

from backend.services.news_sentiment.normalizer import normalize_text
from backend.services.news_sentiment.event_classifier import classify_event_candidates, select_primary_event
from backend.services.news_sentiment.fact_extractor import (
    extract_performance_facts,
    extract_reduce_holding_facts,
    extract_increase_holding_facts,
    extract_buyback_facts,
    extract_order_contract_facts,
    extract_unlock_facts,
)
from backend.services.news_sentiment.scorer import score_event, merge_event_scores
from backend.services.news_sentiment.confidence import calculate_confidence
from backend.services.news_sentiment.constants import (
    CERTAINTY_FACTOR, score_to_impact_level, score_to_sentiment,
    MARKET_CONTEXT_POSITIVE_WORDS,
)
from backend.services.news_sentiment.news_scope import classify_news_scope, extract_target_context


def analyze_news_event(
    news_item: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """分析单条新闻

    Args:
        news_item: 新闻数据字典
        context: 可选上下文（market_cap, float_market_cap, last_year_revenue等）
        debug: 是否输出调试信息

    Returns:
        结构化情感分析结果
    """
    title = news_item.get("title", "")
    content = news_item.get("content", "") or ""
    source = news_item.get("source", "") or ""
    stock_name = news_item.get("stock_name", "") or ""
    context = context or {}

    # 1. 文本标准化
    text = normalize_text(title, content)

    # 1.5 新闻范围分类
    scope_info = classify_news_scope(title, content, stock_name)
    news_scope = scope_info["news_scope"]
    has_target_stock = scope_info.get("has_target_stock", False)

    # === 多股/市场综述分流 ===
    if news_scope in ("multi_stock", "market_overview"):
        return _handle_multi_stock(text, title, content, source, stock_name, news_scope, scope_info, debug)

    # === 单股新闻或未知：正常事件识别 ===
    # 2. 事件识别（全部候选）
    candidates = classify_event_candidates(text)
    primary_event = select_primary_event(candidates)

    # 3. 事实抽取（根据主事件）
    facts = _extract_facts(primary_event, text, context)

    # 4. 评分
    main_raw_score, event_subtype, risk_flags, certainty = score_event(primary_event, text, facts)

    # 所有事件评分（用于冲突合并）
    all_scores = [main_raw_score]
    all_event_details = [(primary_event, main_raw_score)]
    for event_type, _ in candidates:
        if event_type == primary_event:
            continue
        sc, _, _, _ = score_event(event_type, text, _extract_facts(event_type, text, context))
        all_scores.append(sc)
        all_event_details.append((event_type, sc))

    # 5. 多事件合并
    merged_score, merge_risk_flags = merge_event_scores(all_scores)
    risk_flags.extend(merge_risk_flags)

    # 6. 确定性因子
    if certainty == "unknown":
        for word, ctype in [
            ("终止", "completed"), ("完成", "completed"), ("已", "completed"),
            ("存在不确定性", "uncertain"), ("尚存在不确定性", "uncertain"),
            ("拟", "planned"), ("计划", "planned"),
            ("筹划", "preliminary"),
            ("预计", "forecast"),
            ("框架协议", "framework"),
        ]:
            if word in text:
                certainty = ctype
                break

    cf = CERTAINTY_FACTOR.get(certainty, 1.0)

    # 7. 最终分数
    final_score = merged_score * cf
    final_score = max(-5.0, min(5.0, final_score))

    # 8. 情感和影响等级
    positive_scores = [s for s in all_scores if s > 0]
    negative_scores = [s for s in all_scores if s < 0]
    sentiment = score_to_sentiment(final_score, sum(positive_scores) if positive_scores else 0, sum(negative_scores) if negative_scores else 0)
    impact_level = score_to_impact_level(abs(final_score))

    # 9. 理由
    reason = _build_reason(primary_event, sentiment, facts, event_subtype)

    # 10. 匹配规则
    matched_rules = [f"MATCH_{primary_event.upper()}"]
    if event_subtype:
        matched_rules.append(f"SUBTYPE_{event_subtype.upper()}")

    # 11. 构建输出
    result = _build_result(
        news_item, title, sentiment, final_score, main_raw_score,
        primary_event, event_subtype, impact_level, certainty, cf,
        facts, matched_rules, risk_flags, reason,
    )

    if debug:
        result["debug_info"] = {
            "normalized_text": text[:500],
            "news_scope": news_scope,
            "detected_event_candidates": candidates,
            "selected_event_type": primary_event,
            "all_event_scores": all_event_details,
            "raw_score_before_certainty": round(merged_score, 2),
            "certainty_factor": cf,
            "final_score": round(final_score, 2),
        }

    return result


def _handle_multi_stock(text: str, title: str, content: str, source: str,
                        stock_name: str, news_scope: str, scope_info: dict,
                        debug: bool) -> Dict[str, Any]:
    """处理多股/市场综述——不能直接归因给单一股票"""
    # 检查目标股票相关性
    relevance = extract_target_context(text, stock_name)

    if relevance["target_relevance"] == "unrelated":
        sentiment = "unknown" if stock_name else "neutral"
        score = 0.0
        matched_rules = ["MULTI_STOCK_NEWS_NOT_ASSIGNED_TO_SINGLE_STOCK"]
        reason = "文本属于多股盘面综述，不应直接归因为单一股票利好或利空"
        if not stock_name:
            reason += "（未传入目标股票）"
        else:
            matched_rules = ["TARGET_STOCK_NOT_FOUND_IN_MULTI_STOCK_NEWS"]
            reason = f"文本为多股盘面综述，但未提及目标股票{stock_name}，不能归因到该股票"

        result = _build_result(
            {"title": title, "stock_name": stock_name},
            title, sentiment, score, 0.0,
            "unrelated" if stock_name else "market_overview",
            "multi_stock_overview" if not stock_name else "target_stock_not_mentioned",
            "none", "completed", 1.0,
            {"news_scope": news_scope},
            matched_rules, [], reason,
        )
        if debug:
            result["debug_info"] = {
                "normalized_text": text[:500],
                "news_scope": news_scope,
                "scope_info": scope_info,
                "target_relevance": relevance,
            }
        return result

    # 目标股票出现在多股新闻中，也只说明这条综述提到了该股。
    # 这类文本常把多个股票、题材和业绩词混在一起，不能稳定归因给目标股票。
    local_context = relevance.get("target_context", "")
    matched_rules = ["TARGET_STOCK_FOUND_IN_MULTI_STOCK_NEWS"]
    sentiment = "neutral"
    score = 0.0

    reason = "文本属于多股盘面综述，目标股票被提及但不做个股利好/利空归因"

    facts = {
        "target_stock": stock_name,
        "target_context": local_context,
        "news_scope": news_scope,
    }

    result = _build_result(
        {"title": title, "stock_name": stock_name},
        title, sentiment, score, score,
        "market_overview",
        "target_stock_mention",
        score_to_impact_level(abs(score)), "completed", 1.0,
        facts, matched_rules, [], reason,
    )
    if debug:
        result["debug_info"] = {
            "normalized_text": text[:500],
            "news_scope": news_scope,
            "scope_info": scope_info,
            "target_relevance": relevance,
        }
    return result


def _score_local_context(local_context: str, full_text: str) -> float:
    """基于目标股票局部上下文评分"""
    score = 0.0
    if not local_context:
        return 0.0

    # 盘面综述里的涨停、连板、高开、拉升只描述价格行为，不能作为个股新闻利好/利空。
    # 只有明确可归因的基本面/公告事件，才改变情感。
    if "业绩超预期" in local_context or "超预期" in local_context:
        score += 0.8
    if "中标" in local_context or "签订合同" in local_context or "重大合同" in local_context:
        score += 0.8
    if "减持" in local_context or "监管函" in local_context or "立案调查" in local_context:
        score -= 0.8
    if "退市风险" in local_context or "行政处罚" in local_context:
        score -= 1.2

    return max(-1.5, min(1.5, score))


def analyze_news_batch(
    news_items: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """批量分析"""
    return [analyze_news_event(item, context, debug) for item in news_items]


def _extract_facts(event_type: str, text: str, context: dict) -> dict:
    extractors = {
        "performance": extract_performance_facts,
        "reduce_holding": extract_reduce_holding_facts,
        "increase_holding": extract_increase_holding_facts,
        "buyback": lambda t: extract_buyback_facts(t, context),
        "order_contract": lambda t: extract_order_contract_facts(t, context),
        "unlock": lambda t: extract_unlock_facts(t, context),
    }
    extractor = extractors.get(event_type, lambda t: {})
    return extractor(text)


def _build_reason(event_type: str, sentiment: str, facts: dict, event_subtype: str) -> str:
    parts = [f"识别为{event_type}类事件"]
    if facts.get("net_profit_yoy") is not None:
        parts.append(f"净利润同比{facts['net_profit_yoy']:+.2f}%")
    if event_subtype:
        parts.append(f"子类型:{event_subtype}")
    return "，".join(parts)


def _build_result(
    news_item: Dict, title: str, sentiment: str, score: float,
    raw_score: float, event_type: str, event_subtype: str,
    impact_level: str, certainty: str, certainty_factor: float,
    facts: dict, matched_rules: list, risk_flags: list, reason: str,
) -> Dict[str, Any]:
    return {
        "news_id": news_item.get("news_id", ""),
        "stock_name": news_item.get("stock_name", ""),
        "ts_code": news_item.get("ts_code", ""),
        "title": title,
        "sentiment": sentiment,
        "score": round(score, 1),
        "raw_score": round(raw_score, 1),
        "event_type": event_type,
        "event_subtype": event_subtype,
        "impact_level": impact_level,
        "confidence": round(calculate_confidence(event_type, facts, news_item.get("source", ""), len(news_item.get("content", "") or "")), 2),
        "certainty": certainty,
        "certainty_factor": certainty_factor,
        "facts": facts,
        "matched_rules": matched_rules,
        "risk_flags": risk_flags,
        "reason": reason,
    }
