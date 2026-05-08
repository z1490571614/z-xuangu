#!/usr/bin/env python3
"""
新闻数据库初始化脚本（完整版）
使用分段抓取突破Tushare 1500条限制
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from backend.services.news_collector import init_news_db, get_news_collector


def init_historical_data():
    """初始化历史新闻数据（使用分段抓取）"""
    print("=" * 60)
    print("新闻数据库初始化脚本（完整版）")
    print("=" * 60)

    # 1. 创建数据库表
    print("\n📦 步骤1: 创建数据库表")
    init_news_db()
    print("   ✅ 数据库表创建完成")

    # 2. 初始化新闻采集器
    print("\n📡 步骤2: 初始化新闻采集器")
    collector = get_news_collector()
    print("   ✅ 新闻采集器初始化完成")

    # 3. 定义历史数据时间范围
    start_date = "20260425"
    end_date = "20260429"
    segment_hours = 6  # 每6小时分段抓取
    print(f"\n📅 步骤3: 设置历史数据时间范围")
    print(f"   开始日期: {start_date}")
    print(f"   结束日期: {end_date}")
    print(f"   分段间隔: {segment_hours}小时")

    # 4. 抓取历史数据
    sources = ["cls", "10jqka"]
    total_new = 0
    total_duplicate = 0
    total_fetched = 0

    print(f"\n🔄 步骤4: 使用分段抓取获取历史新闻数据")
    for source in sources:
        print(f"\n   📡 正在抓取 {source}...")
        print(f"   └─ 分段间隔: {segment_hours}小时")
        try:
            result = collector.fetch_historical_data(
                source, 
                start_date, 
                end_date,
                segment_hours=segment_hours
            )
            print(f"      抓取总数: {result['total_fetched']}")
            print(f"      新增记录: {result['new_count']}")
            print(f"      重复记录: {result['duplicate_count']}")
            total_fetched += result['total_fetched']
            total_new += result['new_count']
            total_duplicate += result['duplicate_count']
        except Exception as e:
            print(f"      ❌ 抓取失败: {e}")

    # 5. 统计结果
    print("\n📊 步骤5: 统计结果")
    total_count = collector.get_news_count()
    print(f"   数据库总记录数: {total_count}")
    print(f"   本次抓取总数: {total_fetched}")
    print(f"   本次新增记录: {total_new}")
    print(f"   重复记录: {total_duplicate}")

    # 6. 按来源统计
    print("\n📈 按来源统计:")
    for source in sources:
        count = collector.get_news_count(source)
        print(f"   • {source}: {count} 条")

    collector.close()

    print("\n🎉 新闻数据库初始化完成!")
    print("=" * 60)


if __name__ == "__main__":
    init_historical_data()