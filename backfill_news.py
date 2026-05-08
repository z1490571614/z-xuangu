"""
历史新闻补采脚本 - 补全指定日期范围内财联社和同花顺的新闻数据
用法: conda activate xuangu && python backfill_news.py
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（必须在任何模块导入前执行，确保环境变量生效）
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path, override=True)

from backend.services.news_database import get_session, NewsData, init_news_tables
from backend.services.news_collector import get_news_collector
from backend.utils.trading_date import get_recent_trading_days

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 验证环境变量
token = os.getenv("TUSHARE_TOKEN", "")
if not token:
    logger.error("TUSHARE_TOKEN 未配置，请在 .env 文件中设置")
    sys.exit(1)
logger.info(f"Tushare Token: {token[:20]}... (已加载)")

# 只补这两个核心数据源
SOURCES = [
    ("cls", "财联社"),
    ("10jqka", "同花顺"),
]


def get_source_date_range(source: str, session) -> tuple:
    """获取指定数据源在数据库中的日期范围"""
    first = session.query(NewsData.publish_time)\
        .filter(NewsData.source == source)\
        .order_by(NewsData.publish_time.asc()).first()
    last = session.query(NewsData.publish_time)\
        .filter(NewsData.source == source)\
        .order_by(NewsData.publish_time.desc()).first()
    return (first[0] if first else None, last[0] if last else None)


def main():
    init_news_tables()
    session = get_session()

    # 获取最近5个交易日
    trading_days = get_recent_trading_days(5)
    if not trading_days:
        logger.error("无法获取交易日历")
        sys.exit(1)

    earliest_needed = min(trading_days)
    logger.info(f"需要覆盖的最早交易日: {earliest_needed}")
    logger.info(f"交易日列表: {trading_days}")

    collector = get_news_collector()

    for source_code, source_name in SOURCES:
        logger.info(f"\n======= {source_name} ({source_code}) =======")

        # 查询已有数据的时间范围
        first_time, last_time = get_source_date_range(source_code, session)
        if first_time:
            logger.info(f"  已有数据: {first_time.strftime('%Y-%m-%d %H:%M')} ~ {last_time.strftime('%Y-%m-%d %H:%M')}")
        else:
            logger.info(f"  该数据源无数据，需要全量补采")

        # 计算补采起止日期
        start_date = earliest_needed[:8]
        end_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"  补采范围: {start_date} ~ {end_date}")

        try:
            result = collector.fetch_historical_data(source_code, start_date, end_date, segment_hours=6)
            logger.info(f"  {source_name} 补采完成: 获取{result['total_fetched']}条, 新增{result['new_count']}条, 重复{result['duplicate_count']}条")
        except Exception as e:
            logger.error(f"  {source_name} 补采失败: {e}")

    collector.close()
    session.close()

    # 汇总
    session = get_session()
    for source_code, source_name in SOURCES:
        count = session.query(NewsData).filter(NewsData.source == source_code).count()
        logger.info(f"  {source_name} 总数: {count} 条")
    session.close()

    logger.info("\n======= 补采完成 =======")


if __name__ == "__main__":
    main()
