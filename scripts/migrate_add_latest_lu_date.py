"""
添加 latest_lu_date 字段到 selected_stock 表
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

from sqlalchemy import text
from backend.database import engine

def migrate():
    print("=" * 60)
    print("  迁移：添加 latest_lu_date 字段")
    print("=" * 60)

    conn = engine.connect()
    try:
        result = conn.execute(text("SELECT COUNT(*) AS cnt FROM pragma_table_info('selected_stock') WHERE name='latest_lu_date'"))
        row = result.fetchone()
        if row and row[0] > 0:
            print("  latest_lu_date 字段已存在，跳过迁移")
            return

        print("  添加 latest_lu_date (最新涨停日期)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN latest_lu_date VARCHAR(8)"))
        conn.commit()
        print("\n  字段添加成功！")
    except Exception as e:
        conn.rollback()
        print(f"\n  迁移失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
