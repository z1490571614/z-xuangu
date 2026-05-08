#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理异动解读数据库，删除所有旧记录
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import StockAnomalyInterpretation

def main():
    print("=" * 70)
    print("清理异动解读数据库")
    print("=" * 70)

    db = SessionLocal()
    try:
        count = db.query(StockAnomalyInterpretation).count()
        print(f"\n当前数据库中有 {count} 条记录")

        if count > 0:
            print("\n正在删除所有旧记录...")
            deleted = db.query(StockAnomalyInterpretation).delete()
            db.commit()
            print(f"✅ 成功删除 {deleted} 条记录")
        else:
            print("✅ 数据库已经是空的")

        new_count = db.query(StockAnomalyInterpretation).count()
        print(f"\n清理后数据库中有 {new_count} 条记录")

        print("\n" + "=" * 70)
        print("清理完成！现在可以重启服务测试了")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
