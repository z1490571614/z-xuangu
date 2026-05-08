"""
异动解读表数据库迁移脚本
添加同花顺1:1复刻所需的新字段
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.database import engine

def migrate():
    print("开始迁移异动解读表...")
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("PRAGMA table_info(stock_anomaly_interpretation)"))
        columns = [row[1] for row in result.fetchall()]
        print(f"当前表字段: {columns}")
        
        # 添加新字段
        if 'core_tags_line' not in columns:
            conn.execute(text("ALTER TABLE stock_anomaly_interpretation ADD COLUMN core_tags_line VARCHAR(255)"))
            print("✅ 已添加 core_tags_line 字段")
        
        if 'industry_reason' not in columns:
            conn.execute(text("ALTER TABLE stock_anomaly_interpretation ADD COLUMN industry_reason TEXT"))
            print("✅ 已添加 industry_reason 字段")
        
        if 'company_reasons_json' not in columns:
            conn.execute(text("ALTER TABLE stock_anomaly_interpretation ADD COLUMN company_reasons_json TEXT"))
            print("✅ 已添加 company_reasons_json 字段")
        
        if 'market_background' not in columns:
            conn.execute(text("ALTER TABLE stock_anomaly_interpretation ADD COLUMN market_background VARCHAR(255)"))
            print("✅ 已添加 market_background 字段")
        
        if 'news_window_type' not in columns:
            conn.execute(text("ALTER TABLE stock_anomaly_interpretation ADD COLUMN news_window_type VARCHAR(50)"))
            print("✅ 已添加 news_window_type 字段")
        
        conn.commit()
        print("\n迁移完成！")

if __name__ == "__main__":
    migrate()
