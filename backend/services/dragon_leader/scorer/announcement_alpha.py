"""
消息面评分模块

使用 news_sentiment 底层引擎进行事件驱动的情感判定。
"""
import logging
from typing import Dict, Any, List

from backend.services.news_sentiment.analyzer import analyze_news_event, analyze_news_batch
from backend.services.news_sentiment.aggregator import aggregate_news_results

logger = logging.getLogger(__name__)

_SENTIMENT_SCORE_MULTIPLIER = 10

ROUNDUP_TITLE_PATTERNS = (
    "新闻精选",
    "晚间新闻精选",
    "早间新闻精选",
    "公告精选",
    "晚间公告",
    "早间公告",
    "盘前必读",
    "投资日历",
)

DIM_LABELS = {
    "financial_risk": "业绩风险",
    "shareholder_risk": "股东风险",
    "st_risk": "ST退市风险",
    "regulatory": "监管风险",
}


def calculate_announcement_alpha(
    news_items: List[Dict]
) -> Dict[str, Any]:
    """
    用 news_sentiment 引擎分析新闻情感

    Returns:
        {
            "good_news_score": int,
            "bad_news_score": int,
            "announcement_alpha_score": int,
            "announcement_bias": str,
            "tips": list[str],
            "dimension_scores": {...},
            "dimension_tips": {...},
            "data_status": str
        }
    """
    if not news_items:
        return {
            "good_news_score": 0,
            "bad_news_score": 0,
            "announcement_alpha_score": 0,
            "announcement_bias": "neutral",
            "tips": ["未获取到新闻数据"],
            "dimension_scores": {"financial_risk": 0, "shareholder_risk": 0, "st_risk": 0, "regulatory": 0},
            "dimension_tips": {},
            "data_status": "missing"
        }

    # 用新引擎逐条分析。合集类新闻不能直接归因为单一股票风险，
    # 除非标题明确点名该股。
    results = []
    for item in news_items:
        if _should_skip_roundup_news(item):
            continue
        result = analyze_news_event(item, debug=False)
        results.append(result)

    if not results:
        return {
            "good_news_score": 0,
            "bad_news_score": 0,
            "announcement_alpha_score": 0,
            "announcement_bias": "neutral",
            "tips": ["未检测到可归因到个股的新闻信号"],
            "dimension_scores": {"financial_risk": 0, "shareholder_risk": 0, "st_risk": 0, "regulatory": 0},
            "dimension_tips": {},
            "data_status": "no_relevant_news"
        }

    # 聚合
    agg = aggregate_news_results(results)

    # 映射到原输出格式
    total_good = 0
    total_bad = 0
    good_tips = []
    bad_tips = []

    dim_scores = {"financial_risk": 0, "shareholder_risk": 0, "st_risk": 0, "regulatory": 0}
    dim_tips = {}

    for r in results:
        score_val = r["score"]
        base = int(abs(score_val) * 2)  # -5~5 → -10~10

        if score_val > 0:
            total_good += base
            good_tips.append(f"{r['event_type']}(+{score_val:.1f})")
            # 维度映射
            dim = _event_to_dim(r["event_type"])
            if dim:
                dim_scores[dim] = dim_scores.get(dim, 0) + base
                if dim not in dim_tips:
                    dim_tips[dim] = []
                dim_tips[dim].append(f"{DIM_LABELS.get(dim, dim)}利好+{base}：{r.get('title', r['event_type'])}")
        elif score_val < 0:
            total_bad += base
            bad_tips.append(f"{r['event_type']}({score_val:.1f})")
            dim = _event_to_dim(r["event_type"])
            if dim:
                dim_scores[dim] = dim_scores.get(dim, 0) - base
                if dim not in dim_tips:
                    dim_tips[dim] = []
                dim_tips[dim].append(f"{DIM_LABELS.get(dim, dim)}利空-{base}：{r.get('title', r['event_type'])}")

    alpha_score = total_good - total_bad
    alpha_score = max(-20, min(20, alpha_score))

    if total_good > 0 and total_bad > 0:
        bias = "mixed"
    elif total_good > 0:
        bias = "positive"
    elif total_bad > 0:
        bias = "negative"
    else:
        bias = "neutral"

    tips = []
    if good_tips:
        tips.append(f"利好: {', '.join(good_tips[:3])} (+{total_good})")
    if bad_tips:
        tips.append(f"利空: {', '.join(bad_tips[:3])} ({-total_bad})")
    if not tips:
        tips.append("未检测到明显利好或利空信号")

    return {
        "good_news_score": total_good,
        "bad_news_score": -total_bad,
        "announcement_alpha_score": alpha_score,
        "announcement_bias": bias,
        "tips": tips,
        "dimension_scores": dim_scores,
        "dimension_tips": dim_tips,
        "data_status": "available"
    }


def _event_to_dim(event_type: str) -> str:
    mapping = {
        "performance": "financial_risk",
        "restructure": "financial_risk",
        "reduce_holding": "shareholder_risk",
        "increase_holding": "shareholder_risk",
        "buyback": "shareholder_risk",
        "unlock": "shareholder_risk",
        "pledge": "shareholder_risk",
        "regulatory": "regulatory",
        "inquiry": "regulatory",
        "litigation": "regulatory",
    }
    return mapping.get(event_type, "")


def _should_skip_roundup_news(item: Dict[str, Any]) -> bool:
    title = str(item.get("title", "") or "")
    stock_name = str(item.get("stock_name", "") or "")
    is_roundup = any(pattern in title for pattern in ROUNDUP_TITLE_PATTERNS)
    if not is_roundup:
        return False
    return bool(stock_name and stock_name not in title)
