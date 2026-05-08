#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试和修复异动解读数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import StockAnomalyInterpretation
import json

def check_and_fix_records():
    """检查记录并显示信息"""
    db = SessionLocal()
    try:
        print("=" * 70)
        print("检查异动解读数据库记录...")
        print("=" * 70)
        
        records = db.query(StockAnomalyInterpretation).all()
        
        print(f"\n数据库中共有 {len(records)} 条记录")
        
        for idx, record in enumerate(records[-5:], 1):  # 只显示最后5条
            print(f"\n--- 记录 {idx} ---")
            print(f"stock_code: {record.stock_code}")
            print(f"trade_date: {record.trade_date}")
            print(f"data_status: {record.data_status}")
            
            # 检查新版字段
            print(f"core_tags_line: '{record.core_tags_line}' (存在: {record.core_tags_line is not None})")
            print(f"industry_reason: '{record.industry_reason}'")
            print(f"company_reasons_json: '{record.company_reasons_json}'")
            
            if record.core_tags_line:
                print("✅ 这是新版记录！")
            else:
                print("⚠️ 这是旧版记录！")
        
        # 删除所有记录，强制重新生成
        print("\n" + "=" * 70)
        print("正在删除所有旧记录，强制重新生成...")
        print("=" * 70)
        
        delete_count = db.query(StockAnomalyInterpretation).delete()
        db.commit()
        
        print(f"\n✅ 已删除 {delete_count} 条旧记录！")
        
    finally:
        db.close()

def test_generation():
    """测试生成新数据"""
    print("\n" + "=" * 70)
    print("现在测试生成新数据...")
    print("=" * 70)
    
    from backend.services.anomaly_interpretation import get_anomaly_interpretation
    
    ts_code = "603095.SH"
    stock_name = "越剑智能"
    trade_date = "20260429"
    
    print(f"\n正在调用 API...")
    print(f"ts_code: {ts_code}")
    print(f"stock_name: {stock_name}")
    print(f"trade_date: {trade_date}")
    
    result = get_anomaly_interpretation(ts_code, stock_name, trade_date, force_refresh=True)
    
    print("\n" + "=" * 70)
    print("返回结果:")
    print("=" * 70)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 70)
    print("检查新版字段:")
    print("=" * 70)
    if result.get("core_tags_line"):
        print(f"✅ core_tags_line: {result['core_tags_line']}")
    else:
        print("❌ core_tags_line 为空!")
        
    if result.get("company_reasons"):
        print(f"✅ company_reasons: {len(result['company_reasons'])} 条")
        for reason in result['company_reasons']:
            print(f"  - {reason}")
    else:
        print("❌ company_reasons 为空!")
    
    print(f"✅ data_status: {result.get('data_status')}")
    
    print("\n✅ 所有检查完成！")

if __name__ == "__main__":
    check_and_fix_records()
    test_generation()
