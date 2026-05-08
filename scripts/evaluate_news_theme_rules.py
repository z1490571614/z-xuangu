"""评估新闻主题抽取和股票主题归因效果。

只读本地新闻库和最新选股结果，不调用外部 API。
"""
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import SelectedStock, SelectionRecord
from backend.services.integrated_news_service import IntegratedNewsService
from backend.services.news_database import NewsData, get_session
from backend.services.stock_alias_service import StockAliasService
from backend.services.theme_alias_resolver import ThemeAliasResolver
from backend.services.theme_attribution_scorer import ThemeAttributionScorer


def _split_terms(text: str):
    for sep in ("+", "＋", "、", "/", ";", "；", "|", "｜"):
        text = str(text or "").replace(sep, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _load_latest_selected_stocks(limit: int):
    db = SessionLocal()
    try:
        rec = db.query(SelectionRecord).filter(
            SelectionRecord.status == "success"
        ).order_by(
            SelectionRecord.trade_date.desc(),
            SelectionRecord.id.desc(),
        ).first()
        if not rec:
            return "", []
        rows = db.query(SelectedStock).filter(
            SelectedStock.record_id == rec.id
        ).limit(limit).all()
        return rec.trade_date, rows
    finally:
        db.close()


def _load_market_news_rows(limit: int):
    patterns = [
        "概念", "板块", "方向", "产业链", "赛道", "题材",
        "盘初", "早盘", "午后", "尾盘", "拉升", "走强",
        "走高", "活跃", "爆发", "回落", "走低", "跟涨", "跟跌",
    ]
    filters = []
    for pattern in patterns:
        filters.append(NewsData.title.like(f"%{pattern}%"))
        filters.append(NewsData.content.like(f"%{pattern}%"))

    session = get_session()
    try:
        return session.query(NewsData).filter(or_(*filters)).order_by(
            NewsData.publish_time.desc()
        ).limit(limit).all()
    finally:
        session.close()


def evaluate(stock_limit: int = 80, news_limit: int = 1000):
    trade_date, stocks = _load_latest_selected_stocks(stock_limit)
    rows = _load_market_news_rows(news_limit)
    aliases = StockAliasService.load_aliases()

    svc = IntegratedNewsService.__new__(IntegratedNewsService)
    relations = svc.extract_theme_relations_from_rows(rows, aliases)

    by_stock = defaultdict(list)
    for relation in relations:
        by_stock[relation["ts_code"]].append(relation)

    scorer = ThemeAttributionScorer()
    resolver = ThemeAliasResolver()
    stock_results = []
    for stock in stocks:
        rels = by_stock.get(stock.ts_code, [])
        result = scorer.score(
            ts_code=stock.ts_code,
            stock_name=stock.name or "",
            trade_date=trade_date,
            lu_desc=stock.lu_desc or "",
            news_relations=rels,
            static_concepts=_split_terms(stock.concept or ""),
            industry=stock.industry or "",
        )
        stock_results.append({
            "ts_code": stock.ts_code,
            "name": stock.name,
            "lu_desc": stock.lu_desc or "",
            "concept": stock.concept or "",
            "industry": stock.industry or "",
            "relation_count": len(rels),
            "primary_theme": result["primary_theme"],
            "theme_score": result["theme_score"],
            "confidence": result["confidence"],
            "relation_themes": sorted({r["normalized_theme_name"] for r in rels})[:8],
            "sample_titles": [r["title"] for r in rels[:3]],
            "sample_roles": [
                f"{r['normalized_theme_name']}/{r['role']}/{r['action']}"
                for r in rels[:3]
            ],
        })

    selected_count = len(stock_results)
    with_rel = [item for item in stock_results if item["relation_count"] > 0]
    with_primary = [item for item in stock_results if item["primary_theme"]]

    suspicious = []
    for item in with_rel:
        context = f"{item['lu_desc']} {item['concept']} {item['industry']}"
        context_themes = {
            resolved["normalized_theme_name"]
            for term in _split_terms(context)
            for resolved in resolver.resolve_many(term)
        }
        primary_theme = item["primary_theme"] or ""
        relation_themes = item["relation_themes"]
        if primary_theme and primary_theme not in context and primary_theme not in context_themes and not any(
            theme and (theme in context or theme in context_themes) for theme in relation_themes
        ):
            suspicious.append(item)

    return {
        "trade_date": trade_date,
        "selected_stock_count": selected_count,
        "market_news_scanned": len(rows),
        "relations_total": len(relations),
        "relation_stock_count_all_aliases": len(by_stock),
        "selected_with_news_relation_count": len(with_rel),
        "selected_with_news_relation_rate": round(len(with_rel) / selected_count, 4) if selected_count else 0,
        "selected_with_primary_theme_count": len(with_primary),
        "selected_with_primary_theme_rate": round(len(with_primary) / selected_count, 4) if selected_count else 0,
        "confidence_counts": dict(Counter(item["confidence"] for item in stock_results)),
        "top_relation_themes": Counter(r["normalized_theme_name"] for r in relations).most_common(20),
        "top_relation_stocks": Counter(r["stock_name"] for r in relations).most_common(20),
        "high_confidence_samples": [item for item in stock_results if item["confidence"] == "high"][:20],
        "medium_confidence_samples": [item for item in stock_results if item["confidence"] == "medium"][:20],
        "low_confidence_samples": [item for item in stock_results if item["confidence"] == "low"][:20],
        "no_primary_samples": [item for item in stock_results if not item["primary_theme"]][:20],
        "suspicious_samples": suspicious[:20],
    }


def main():
    report = evaluate()
    out = Path("data/news_theme_eval_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, default=str))
    print(f"REPORT={out.resolve()}")


if __name__ == "__main__":
    main()
