#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查数据库中的新闻和异动解读数据
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'xuangu.db')

def main():
    print("=" * 60)
    print("检查数据库中的新闻和异动解读数据")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查新闻表
    print("\n📊 新闻表 (stock_news):")
    cursor.execute('SELECT COUNT(*) FROM stock_news')
    news_count = cursor.fetchone()[0]
    print(f"  记录数: {news_count}")
    
    cursor.execute('SELECT ts_code, source, COUNT(*) FROM stock_news GROUP BY ts_code, source')
    news_by_source = cursor.fetchall()
    if news_by_source:
        print("  按股票和来源统计:")
        for ts_code, source, count in news_by_source[:10]:
            print(f"    {ts_code} [{source}]: {count}条")
        if len(news_by_source) > 10:
            print(f"    ...还有 {len(news_by_source) - 10} 更多记录")
    
    # 检查异动解读表
    print("\n📊 异动解读表 (anomaly_interpretation):")
    cursor.execute('SELECT COUNT(*) FROM anomaly_interpretation')
    anomaly_count = cursor.fetchone()[0]
    print(f"  记录数: {anomaly_count}")
    
    cursor.execute('SELECT ts_code, core_tags_line, data_status FROM anomaly_interpretation LIMIT 5')
    anomaly_samples = cursor.fetchall()
    if anomaly_samples:
        print("  样本数据:")
        for ts_code, core_tags, status in anomaly_samples:
            core_tags_display = core_tags[:30] if core_tags else "无"
            print(f"    {ts_code}: [{status}] {core_tags_display}")
    
    # 检查综合概览表
    print("\n📊 综合概览表 (overview_brief):")
    cursor.execute('SELECT COUNT(*) FROM overview_brief')
    overview_count = cursor.fetchone()[0]
    print(f"  记录数: {overview_count}")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("检查完成!")

if __name__ == "__main__":
    main()