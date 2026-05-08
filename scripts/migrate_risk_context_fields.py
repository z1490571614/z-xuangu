"""
为 stock_risk_breakdown 补充东财板块上下文与龙虎榜证据字段。

幂等执行：
    python scripts/migrate_risk_context_fields.py
"""
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "xuangu.db"


COLUMNS = {
    "sector_context": "TEXT",
    "lhb_strength_evidence": "TEXT",
    "lhb_risk_evidence": "TEXT",
    "strength_evidence": "TEXT",
    "risk_evidence": "TEXT",
}


def _sqlite_path_from_url(url: str) -> Path:
    if not url or not url.startswith("sqlite:///"):
        return DEFAULT_DB
    raw = url.replace("sqlite:///", "", 1)
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def migrate(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(stock_risk_breakdown)")
        existing = {row[1] for row in cur.fetchall()}
        added = []
        for name, column_type in COLUMNS.items():
            if name in existing:
                continue
            cur.execute(f"ALTER TABLE stock_risk_breakdown ADD COLUMN {name} {column_type}")
            added.append(name)
        conn.commit()
        return added
    finally:
        conn.close()


def main() -> None:
    db_path = _sqlite_path_from_url(os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}"))
    if not db_path.exists():
        print(f"数据库不存在，跳过: {db_path}")
        return
    added = migrate(db_path)
    if added:
        print(f"已添加字段: {', '.join(added)}")
    else:
        print("字段已存在，无需迁移")


if __name__ == "__main__":
    main()
