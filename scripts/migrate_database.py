"""
数据库迁移脚本 - 添加新字段到selected_stock表
"""
import sqlite3
import os
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "data" / "xuangu.db"

def migrate_database():
    """迁移数据库，添加新字段"""
    print("=" * 80)
    print("🔄 开始数据库迁移")
    print("=" * 80)
    
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        print("   将在首次运行时自动创建")
        return
    
    print(f"✅ 数据库文件存在: {DB_PATH}")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 获取现有表结构
    cursor.execute("PRAGMA table_info(selected_stock)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    print(f"\n📋 现有字段: {existing_columns}")
    
    # 需要添加的新字段
    new_columns = {
        "pre_change_pct": "REAL",
        "open_change_pct": "REAL",
        "auction_ratio": "REAL",
        "auction_turnover_rate": "REAL",
        "industry": "TEXT",
        "concept": "TEXT",
        "board_type": "TEXT",
        "limit_up_count": "INTEGER",
        "seal_rate": "REAL",
        "rise_10d_pct": "REAL",
    }
    
    # 添加缺失的字段
    added_count = 0
    for col_name, col_type in new_columns.items():
        if col_name not in existing_columns:
            try:
                sql = f"ALTER TABLE selected_stock ADD COLUMN {col_name} {col_type}"
                print(f"  ➕ 添加字段: {col_name} ({col_type})")
                cursor.execute(sql)
                added_count += 1
            except Exception as e:
                print(f"  ❌ 添加字段失败 {col_name}: {e}")
    
    if added_count > 0:
        conn.commit()
        print(f"\n✅ 成功添加 {added_count} 个新字段")
    else:
        print(f"\n✅ 所有字段已存在，无需迁移")
    
    # 验证表结构
    cursor.execute("PRAGMA table_info(selected_stock)")
    final_columns = {row[1] for row in cursor.fetchall()}
    print(f"\n📋 最终字段: {final_columns}")
    
    conn.close()
    print("\n" + "=" * 80)
    print("✅ 数据库迁移完成")
    print("=" * 80)

if __name__ == "__main__":
    migrate_database()
