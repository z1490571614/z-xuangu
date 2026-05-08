"""多新闻聚合模块"""
from typing import List, Dict, Any


def aggregate_news_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    positive_scores = [r["score"] for r in results if r["score"] > 0]
    negative_scores = [r["score"] for r in results if r["score"] < 0]

    max_positive = max(positive_scores) if positive_scores else 0
    min_negative = min(negative_scores) if negative_scores else 0

    if min_negative <= -3.0:
        final_score = min_negative + max_positive * 0.2
    else:
        final_score = max_positive + min_negative

    final_score = max(-5.0, min(5.0, final_score))

    positive_count = len(positive_scores)
    negative_count = len(negative_scores)
    neutral_count = len(results) - positive_count - negative_count

    from backend.services.news_sentiment.constants import score_to_sentiment
    final_sentiment = score_to_sentiment(final_score, max_positive, min_negative)

    top_positive = None
    top_negative = None
    for r in results:
        if r["score"] > 0 and (top_positive is None or r["score"] > top_positive["score"]):
            top_positive = r
        if r["score"] < 0 and (top_negative is None or r["score"] < top_negative["score"]):
            top_negative = r

    return {
        "ts_code": results[0].get("ts_code", "") if results else "",
        "date": results[0].get("date", "") if results else "",
        "final_sentiment": final_sentiment,
        "final_score": final_score,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "top_positive_event": top_positive,
        "top_negative_event": top_negative,
        "events": results,
    }
