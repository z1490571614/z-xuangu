"""新闻舆情公告情感判定底层模块

事件驱动的纯规则情感判定引擎。
不调用AI大模型，不绑定任何策略。

用法：
    from backend.services.news_sentiment.analyzer import analyze_news_event
    result = analyze_news_event({"title": "...", "content": "..."})
"""
from backend.services.news_sentiment.analyzer import analyze_news_event, analyze_news_batch
from backend.services.news_sentiment.constants import SENTIMENT, EVENT_TYPES, CERTAINTY_TYPES

__all__ = ["analyze_news_event", "analyze_news_batch", "SENTIMENT", "EVENT_TYPES", "CERTAINTY_TYPES"]
