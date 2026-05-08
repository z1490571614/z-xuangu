"""
添加同花顺涨停榜单 + 上一日换手率字段到 selected_stock 表
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
    """执行迁移：添加新字段"""
    print("=" * 60)
    print("  迁移：添加同花顺涨停榜单 + 上一日换手率字段")
    print("=" * 60)

    conn = engine.connect()
    try:
        result = conn.execute(text("SELECT COUNT(*) AS cnt FROM pragma_table_info('selected_stock') WHERE name='lu_desc'"))
        row = result.fetchone()
        if row and row[0] > 0:
            print("  lu_desc 字段已存在，跳过迁移")
            return

        print("\n  添加 lu_desc (涨停原因)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN lu_desc TEXT"))

        print("  添加 lu_tag (涨停标签)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN lu_tag VARCHAR(50)"))

        print("  添加 lu_status (涨停状态)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN lu_status VARCHAR(50)"))

        print("  添加 lu_open_num (打开次数)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN lu_open_num INTEGER"))

        print("  添加 limit_up_suc_rate (近一年涨停封板率)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN limit_up_suc_rate FLOAT"))

        print("  添加 prev_turnover_rate (上一日换手率)...")
        conn.execute(text("ALTER TABLE selected_stock ADD COLUMN prev_turnover_rate FLOAT"))

        conn.commit()
        print("\n  所有字段添加成功！")
    except Exception as e:
        conn.rollback()
        print(f"\n  迁移失败: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
