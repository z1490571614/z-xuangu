#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试新闻获取模块 - 检查财联社和同花顺数据源
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.tushare_news import get_news_service
import json

def test_stock(ts_code, stock_name, trade_date):
    print("=" * 70)
    print(f"测试股票: {ts_code} ({stock_name})")
    print("=" * 70)

    news_service = get_news_service()

    print(f"\n获取新闻...")
    result = news_service.get_stock_news_v2(
        ts_code=ts_code,
        stock_name=stock_name,
        trade_date=trade_date,
        limit=30,
        deduplicate=True
    )

    print("\n" + "-" * 70)
    print("新闻获取结果:")
    print("-" * 70)

    print(f"Code: {result.get('code')}")
    print(f"Message: {result.get('message')}")
    
    data = result.get('data', {})
    news_list = data.get('news_list', [])

    print(f"\n总共获取到: {len(news_list)} 条新闻")

    # 统计各源
    source_count = {}
    for news in news_list:
        src = news.get('source', 'unknown')
        source_count[src] = source_count.get(src, 0) + 1

    print(f"\n各源统计:")
    for src, cnt in source_count.items():
        print(f"  {src}: {cnt}条")

    # 打印前10条的源和标题
    print("\n前10条新闻:")
    for i, news in enumerate(news_list[:10]):
        src = news.get('source', 'unknown')
        title = news.get('title', '')
        time = news.get('publish_time', '')
        print(f"{i+1:2d}. [{src}] {time} {title}")

    print("\n" + "=" * 70)

def main():
    # 测试三只股票
    test_stock("002902.SZ", "铭普光磁", "20260430")
    print("\n" * 3)
    test_stock("603095.SH", "越剑智能", "20260430")
    print("\n" * 3)
    test_stock("601789.SH", "际华集团", "20260430")

if __name__ == "__main__":
    main()
