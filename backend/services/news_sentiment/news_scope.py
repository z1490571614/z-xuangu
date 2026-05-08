"""新闻范围识别 + 目标股票相关性判断"""

from typing import Dict, List


MARKET_OVERVIEW_WORDS = [
    "竞价看龙头", "人气板块及个股点评", "市场情绪", "全市场",
    "板块", "产业链", "赛道", "题材", "做多氛围",
    "补涨机会", "市场焦点股", "热门赛道", "盘面",
    "今日市场", "涨停", "跌停", "连板",
]

SINGLE_STOCK_WORDS = [
    "公告称", "公告", "发布公告", "披露",
    "净利润", "营业收入", "归属于上市公司股东",
    "董事会", "股东大会", "减持", "增持", "回购",
    "中标", "签订合同", "重大资产重组",
]


def classify_news_scope(title: str, content: str, stock_name: str = "") -> dict:
    """识别新闻属于单股/多股/市场综述"""
    text = f"{title or ''}。{content or ''}"

    market_hits = [w for w in MARKET_OVERVIEW_WORDS if w in text]
    single_hits = [w for w in SINGLE_STOCK_WORDS if w in text]

    # 多股票结构特征
    has_many_stock_like_phrases = (
        text.count("（") >= 3
        or text.count("板") >= 3
        or text.count("高开") + text.count("低开") + text.count("涨停") >= 3
    )

    has_target_stock = bool(stock_name and stock_name in text)

    if len(market_hits) >= 2 and has_many_stock_like_phrases:
        return {
            "news_scope": "multi_stock",
            "reason": "market_or_sector_overview",
            "market_hits": market_hits,
            "single_hits": single_hits,
            "has_target_stock": has_target_stock,
        }

    if has_target_stock and len(single_hits) >= 1:
        return {
            "news_scope": "single_stock",
            "reason": "single_stock_event",
            "market_hits": market_hits,
            "single_hits": single_hits,
            "has_target_stock": has_target_stock,
        }

    if len(market_hits) >= 2:
        return {
            "news_scope": "market_overview",
            "reason": "market_overview",
            "market_hits": market_hits,
            "single_hits": single_hits,
            "has_target_stock": has_target_stock,
        }

    return {
        "news_scope": "unknown",
        "reason": "scope_uncertain",
        "market_hits": market_hits,
        "single_hits": single_hits,
        "has_target_stock": has_target_stock,
    }


def extract_target_context(text: str, stock_name: str, window: int = 80) -> dict:
    """提取目标股票附近的局部上下文"""
    if not stock_name or stock_name not in text:
        return {
            "target_relevance": "unrelated",
            "target_context": "",
            "reason": "target_stock_not_found",
        }

    idx = text.find(stock_name)
    start = max(0, idx - window)
    end = min(len(text), idx + len(stock_name) + window)
    target_context = text[start:end]

    return {
        "target_relevance": "nearby",
        "target_context": target_context,
        "reason": "target_stock_found_with_local_context",
    }
