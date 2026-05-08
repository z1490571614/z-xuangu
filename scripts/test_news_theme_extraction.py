"""从现有新闻库抽取新闻-主题-股票关系样本。"""
import sys
import json
from pathlib import Path
from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models import SelectedStock
from backend.services.news_database import get_session, NewsData
from backend.services.news_theme_extractor import NewsThemeExtractor


def load_stock_aliases():
    db = SessionLocal()
    try:
        aliases = {}
        rows = db.query(SelectedStock.name, SelectedStock.ts_code).filter(
            SelectedStock.name.isnot(None),
            SelectedStock.ts_code.isnot(None),
        ).distinct().all()
        for name, ts_code in rows:
            clean = NewsThemeExtractor.normalize_stock_name(name)
            if clean:
                aliases[clean] = ts_code
        return aliases
    finally:
        db.close()


def main(limit=800):
    extractor = NewsThemeExtractor(load_stock_aliases())
    session = get_session()
    try:
        patterns = [
            "概念", "板块", "方向", "产业链", "赛道", "题材",
            "盘初", "早盘", "午后", "尾盘", "拉升", "走强",
            "活跃", "爆发", "回落", "走低", "跟涨", "跟跌",
        ]
        filters = []
        for pattern in patterns:
            filters.append(NewsData.title.like(f"%{pattern}%"))
            filters.append(NewsData.content.like(f"%{pattern}%"))

        rows = session.query(NewsData).filter(or_(*filters)).order_by(
            NewsData.publish_time.desc()
        ).limit(limit).all()

        relations = []
        matched_news = 0
        for row in rows:
            news = {
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "publish_time": row.publish_time,
                "source": row.source,
            }
            extracted = extractor.extract(news)
            if extracted:
                matched_news += 1
                relations.extend(extracted)

        by_stock = {}
        by_theme = {}
        for item in relations:
            if item["stock_name"]:
                by_stock.setdefault(item["stock_name"], []).append(item)
            by_theme[item["normalized_theme_name"]] = by_theme.get(item["normalized_theme_name"], 0) + 1

        summary = {
            "scanned_news": len(rows),
            "matched_news": matched_news,
            "relations": len(relations),
            "top_themes": sorted(by_theme.items(), key=lambda x: x[1], reverse=True)[:30],
            "stocks": {
                stock: items[:10]
                for stock, items in sorted(by_stock.items(), key=lambda x: len(x[1]), reverse=True)
            },
            "samples": relations[:200],
        }

        out = Path("data/news_theme_extraction_sample.json")
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        print(f"scanned_news={summary['scanned_news']}")
        print(f"matched_news={summary['matched_news']}")
        print(f"relations={summary['relations']}")
        print(f"output={out.resolve()}")
        print("top_themes:")
        for theme, count in summary["top_themes"][:15]:
            print(f"  {theme}: {count}")
        print("top_stocks:")
        for stock, items in list(summary["stocks"].items())[:15]:
            print(f"  {stock}: {len(items)}")
            first = items[0]
            print(f"    {first['normalized_theme_name']} / {first['role']} / {first['action']} / {first['title']}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
