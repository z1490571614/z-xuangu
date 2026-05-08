"""
清理所有旧的综合概览缓存，让新代码自动使用AI或新fallback重新生成
用法: conda activate xuangu && python clear_brief_cache.py
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env', override=True)

from backend.database import SessionLocal
from backend.models import StockOverviewBrief

db = SessionLocal()
try:
    deleted = db.query(StockOverviewBrief).delete()
    db.commit()
    print(f"已清理 {deleted} 条旧的综合概览缓存记录")
    print("下次打开个股详情时将重新生成")
except Exception as e:
    db.rollback()
    print(f"清理失败: {e}")
finally:
    db.close()
