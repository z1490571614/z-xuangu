"""
创建/升级 news_theme_relation 表。

用于缓存新闻主题抽取结果，服务个股板块归因；失败不影响实时抽取。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from sqlalchemy import text

from backend.services.news_database import Base, NewsStockThemeAttribution, NewsThemeRelation, get_engine


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
    ), {"table_name": table_name}).fetchone()
    return row is not None


def _columns(conn, table_name: str) -> set:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def migrate():
    print("=" * 60)
    print("  迁移：创建/升级 news_theme_relation 表")
    print("=" * 60)

    engine = get_engine()
    Base.metadata.create_all(bind=engine, tables=[
        NewsThemeRelation.__table__,
        NewsStockThemeAttribution.__table__,
    ])

    with engine.connect() as conn:
        if not _table_exists(conn, "news_theme_relation"):
            raise RuntimeError("news_theme_relation 表创建失败")
        if not _table_exists(conn, "stock_theme_attribution"):
            raise RuntimeError("stock_theme_attribution 表创建失败")

        columns = _columns(conn, "news_theme_relation")
        if "credibility_level" not in columns:
            print("  添加 credibility_level 字段...")
            conn.execute(text("ALTER TABLE news_theme_relation ADD COLUMN credibility_level VARCHAR(20)"))
            conn.commit()
        else:
            print("  credibility_level 字段已存在，跳过")

    print("\n  迁移完成！")


if __name__ == "__main__":
    migrate()
