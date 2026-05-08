#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试新闻数据源 - 检查各源的数据获取情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trae_db
from backend.services.tushare_news import TushareNewsService
from datetime import datetime, timedelta

def main():
    # 输出到文件
    output_lines = []
    def log(msg):
        print(msg)
        output_lines.append(msg)
    
    log("=" * 70)
    log("调试新闻数据源")
    log("=" * 70)
    
    # 初始化数据库
    trae_db.init_db()
    
    # 创建新闻服务
    news_service = TushareNewsService()
    
    if not news_service.available:
        log("❌ Tushare服务不可用！请检查Token配置！")
        return
    
    # 获取时间范围（5天）
    today = datetime.now()
    start_date = (today - timedelta(days=5)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")
    
    log(f"\n时间范围: {start_date} 到 {end_date}")
    
    # 测试各个数据源
    sources = ["cls", "10jqka"]
    all_results = []
    
    for source in sources:
        log(f"\n{'='*50}")
        log(f"测试数据源: {source}")
        log(f"{'='*50}")
        
        try:
            news = news_service._fetch_news_from_source(source, start_date, end_date)
            log(f"获取到 {len(news)} 条新闻")
            
            if news:
                log("\n前3条新闻:")
                for i, n in enumerate(news[:3]):
                    log(f"{i+1}. [{n.get('publish_time')}] {n.get('title')[:50]}...")
                    log(f"    来源: {n.get('source')}")
            
            all_results.extend(news)
            log(f"\n累计总数: {len(all_results)}")
            
        except Exception as e:
            log(f"❌ 获取失败: {e}")
    
    # 测试过滤功能
    log(f"\n{'='*50}")
    log("测试股票过滤功能")
    log(f"{'='*50}")
    
    if all_results:
        log(f"\n过滤前总数: {len(all_results)}")
        
        # 统计各源数量
        src_counts = {}
        for n in all_results:
            src = n.get('source', 'unknown')
            src_counts[src] = src_counts.get(src, 0) + 1
        log(f"各源数量: {src_counts}")
        
        # 测试过滤
        filtered = news_service._filter_by_stock(all_results, "铭普光磁")
        log(f"\n过滤铭普光磁后: {len(filtered)} 条")
        
        # 统计过滤后各源数量
        src_counts_filtered = {}
        for n in filtered:
            src = n.get('source', 'unknown')
            src_counts_filtered[src] = src_counts_filtered.get(src, 0) + 1
        log(f"过滤后各源数量: {src_counts_filtered}")
        
        # 测试去重
        deduplicated = news_service._deduplicate_news(filtered)
        log(f"\n去重后: {len(deduplicated)} 条")
        
        # 统计去重后各源数量
        src_counts_dedup = {}
        for n in deduplicated:
            src = n.get('source', 'unknown')
            src_counts_dedup[src] = src_counts_dedup.get(src, 0) + 1
        log(f"去重后各源数量: {src_counts_dedup}")
        
        log("\n去重后的新闻:")
        for i, n in enumerate(deduplicated[:5]):
            log(f"{i+1}. [{n.get('source')}] [{n.get('publish_time')}] {n.get('title')[:40]}...")
    
    # 写入文件
    with open('news_debug_output.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    log("\n✅ 输出已保存到 news_debug_output.txt")

if __name__ == "__main__":
    main()