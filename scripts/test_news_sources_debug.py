#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试新闻数据源 - 检查财联社和同花顺的数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.tushare_news import get_news_service
from datetime import datetime, timedelta

def main():
    print("=" * 70)
    print("测试新闻数据源")
    print("=" * 70)

    news_service = get_news_service()
    
    if not news_service.available:
        print("❌ Tushare服务不可用！")
        return
    
    # 使用当前日期
    today = datetime.now()
    trade_date = today.strftime("%Y%m%d")
    
    print(f"\n测试日期: {trade_date}")
    
    # 测试获取5天的数据
    print("\n1. 测试获取原始新闻（不按股票过滤）:")
    
    # 获取时间范围
    start_date = (today - timedelta(days=5)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")
    
    print(f"时间范围: {start_date} 到 {end_date}")
    
    # 直接调用获取新闻的方法
    sources = ["cls", "10jqka"]
    for source in sources:
        print(f"\n  获取 {source} 的新闻...")
        news = news_service._fetch_news_from_source(source, start_date, end_date)
        print(f"  结果: {len(news)} 条")
        if news:
            print(f"  第一条标题: {news[0]['title'][:50]}...")
            print(f"  发布时间: {news[0]['publish_time']}")
    
    # 测试带股票过滤
    print("\n2. 测试带股票过滤（铭普光磁）:")
    result = news_service.get_stock_news_v2(
        ts_code="002902.SZ",
        stock_name="铭普光磁",
        trade_date=trade_date,
        limit=20,
        deduplicate=True
    )
    
    news_list = result.get("data", {}).get("news_list", [])
    print(f"\n  总共获取到 {len(news_list)} 条新闻")
    
    # 统计各源数量
    source_count = {}
    for news in news_list:
        src = news.get('source', 'unknown')
        source_count[src] = source_count.get(src, 0) + 1
    
    print(f"\n  各源统计:")
    for src, cnt in source_count.items():
        print(f"    {src}: {cnt}条")
    
    # 打印前10条
    print("\n  前10条新闻:")
    for i, news in enumerate(news_list[:10]):
        src = news.get('source', 'unknown')
        title = news.get('title', '')
        time = news.get('publish_time', '')
        print(f"    {i+1:2d}. [{src}] {time[:16]} {title[:40]}...")

if __name__ == "__main__":
    main()