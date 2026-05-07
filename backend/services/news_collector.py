"""
新闻采集服务 - 永久性新闻数据库系统核心服务
"""
import os
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import tushare as ts
from sqlalchemy.exc import IntegrityError

from backend.services.news_database import (
    NewsData, NewsSource, NewsFetchLog, NewsCleanupLog,
    init_news_tables, get_session, close_session, get_text
)
from backend.utils.trading_date import get_recent_trading_days, is_trading_day
from backend.utils.tushare_client import get_tushare_pro, get_tushare_token

logger = logging.getLogger(__name__)

# 新闻来源映射
SOURCE_MAP = {
    "cls": "财联社",
    "10jqka": "同花顺",
}


class NewsCollector:
    """
    新闻采集器 - 负责从Tushare获取新闻并存储到数据库
    """

    def __init__(self):
        self.token = get_tushare_token()
        self.pro = get_tushare_pro(self.token) if self.token else None
        self.session = get_session()
        self._init_sources()

    def _init_sources(self):
        """初始化新闻来源配置 - 仅保留财联社和同花顺"""
        active_codes = {"cls", "10jqka"}
        for code, name in SOURCE_MAP.items():
            existing = self.session.query(NewsSource).filter_by(source_code=code).first()
            if not existing:
                source = NewsSource(
                    source_code=code,
                    source_name=name,
                    enabled=True,
                    fetch_interval_minutes=60,
                    max_fetch_count=1500,
                    priority=10
                )
                self.session.add(source)
        # 禁用不再使用的数据源（第一财经、新浪财经、东方财富）
        self.session.query(NewsSource).filter(
            ~NewsSource.source_code.in_(active_codes)
        ).update({"enabled": False})
        self.session.commit()

    @staticmethod
    def _calculate_title_hash(title: str) -> str:
        """计算标题的MD5哈希值用于去重"""
        return hashlib.md5(title.encode('utf-8')).hexdigest()

    def _fetch_news_from_tushare(self, source: str, start_time: str, end_time: str) -> List[Dict]:
        """从Tushare获取指定时间范围的新闻"""
        if not self.pro:
            logger.error("Tushare token未配置")
            return []

        try:
            df = self.pro.news(src=source, start_date=start_time, end_date=end_time)
            if df is None or df.empty:
                return []

            news_list = []
            for _, row in df.iterrows():
                news_item = {
                    "title": str(row.get("title", "")),
                    "content": str(row.get("content", "")),
                    "publish_time": row.get("datetime", ""),
                    "source": source,
                    "source_name": SOURCE_MAP.get(source, source),
                    "url": str(row.get("url", "")),
                    "news_category": str(row.get("channels", ""))
                }
                news_list.append(news_item)

            return news_list

        except Exception as e:
            logger.error(f"从Tushare获取{source}新闻失败: {e}")
            return []

    def _is_duplicate(self, title_hash: str, source: str, publish_time: datetime) -> bool:
        """检查是否为重复新闻"""
        query = self.session.query(NewsData).filter(
            NewsData.title_hash == title_hash,
            NewsData.source == source,
            NewsData.publish_time >= publish_time - timedelta(minutes=5),
            NewsData.publish_time <= publish_time + timedelta(minutes=5)
        )
        return query.first() is not None

    def _save_news_batch(self, news_items: List[Dict]) -> Tuple[int, int]:
        """批量保存新闻数据，返回(新增数, 重复数)"""
        new_count = 0
        duplicate_count = 0
        current_batch = []

        for item in news_items:
            try:
                # 解析发布时间
                publish_time_str = item.get("publish_time", "")
                if publish_time_str:
                    try:
                        publish_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            publish_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
                        except ValueError:
                            publish_time = datetime.now()
                else:
                    publish_time = datetime.now()

                # 计算标题哈希
                title_hash = self._calculate_title_hash(item["title"])

                # 检查重复（先查询，避免触发唯一约束）
                if self._is_duplicate(title_hash, item["source"], publish_time):
                    duplicate_count += 1
                    continue

                # 创建新闻记录
                news_data = NewsData(
                    title=item["title"],
                    content=item.get("content", ""),
                    publish_time=publish_time,
                    source=item["source"],
                    source_name=item["source_name"],
                    title_hash=title_hash,
                    url=item.get("url"),
                    news_category=item.get("news_category"),
                )

                current_batch.append(news_data)

            except Exception as e:
                logger.error(f"处理新闻失败: {e}")

            # 每50条提交一次
            if len(current_batch) >= 50:
                try:
                    self.session.add_all(current_batch)
                    self.session.commit()
                    new_count += len(current_batch)
                    current_batch = []
                except IntegrityError:
                    # 批量提交失败，改为逐条提交
                    self.session.rollback()
                    for news_data in current_batch:
                        try:
                            self.session.add(news_data)
                            self.session.commit()
                            new_count += 1
                        except IntegrityError:
                            self.session.rollback()
                            duplicate_count += 1
                        except Exception as e:
                            self.session.rollback()
                            logger.error(f"逐条保存失败: {e}")
                    current_batch = []
                except Exception as e:
                    logger.error(f"批量保存失败: {e}")
                    self.session.rollback()
                    current_batch = []

        # 提交剩余的记录
        if current_batch:
            try:
                self.session.add_all(current_batch)
                self.session.commit()
                new_count += len(current_batch)
            except IntegrityError:
                self.session.rollback()
                for news_data in current_batch:
                    try:
                        self.session.add(news_data)
                        self.session.commit()
                        new_count += 1
                    except IntegrityError:
                        self.session.rollback()
                        duplicate_count += 1
                    except Exception as e:
                        self.session.rollback()
                        logger.error(f"逐条保存失败: {e}")
            except Exception as e:
                logger.error(f"保存剩余记录失败: {e}")
                self.session.rollback()

        return new_count, duplicate_count

    def fetch_and_store(self, source: str, start_time: str, end_time: str) -> Dict[str, int]:
        """
        获取指定时间范围的新闻并存储到数据库
        """
        log_entry = NewsFetchLog(
            source=source,
            start_time=datetime.now(),
            status="running"
        )
        self.session.add(log_entry)
        self.session.commit()

        try:
            # 获取新闻
            news_list = self._fetch_news_from_tushare(source, start_time, end_time)

            # 保存到数据库
            new_count, duplicate_count = self._save_news_batch(news_list)

            # 更新来源的最后抓取时间
            source_config = self.session.query(NewsSource).filter_by(source_code=source).first()
            if source_config:
                source_config.last_fetch_time = datetime.now()
                self.session.commit()

            # 更新日志
            log_entry.end_time = datetime.now()
            log_entry.total_fetched = len(news_list)
            log_entry.new_count = new_count
            log_entry.duplicate_count = duplicate_count
            log_entry.status = "success"
            log_entry.duration_seconds = (log_entry.end_time - log_entry.start_time).total_seconds()
            self.session.commit()

            return {
                "total_fetched": len(news_list),
                "new_count": new_count,
                "duplicate_count": duplicate_count
            }

        except Exception as e:
            log_entry.end_time = datetime.now()
            log_entry.status = "failed"
            log_entry.error_message = str(e)
            log_entry.duration_seconds = (log_entry.end_time - log_entry.start_time).total_seconds()
            self.session.commit()
            logger.error(f"抓取{source}新闻失败: {e}")
            raise

    def fetch_recent_hour(self, source: str) -> Dict[str, int]:
        """
        增量抓取最近一小时的新闻
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

        return self.fetch_and_store(source, start_str, end_str)

    def fetch_historical_data(self, source: str, start_date: str, end_date: str, segment_hours: int = 6) -> Dict[str, int]:
        """
        获取历史数据（用于初始化）
        
        Args:
            source: 新闻来源
            start_date: 开始日期，可以是 YYYYMMDD 或 YYYY-MM-DD 格式
            end_date: 结束日期，可以是 YYYYMMDD 或 YYYY-MM-DD 格式
            segment_hours: 分段时间间隔（小时），默认为6小时，用于突破Tushare 1500条限制
        """
        # 统一日期格式为 YYYY-MM-DD
        if len(start_date) == 8 and start_date.isdigit():
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8 and end_date.isdigit():
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
            
        # 解析开始和结束时间
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # 包含结束日期的23:59:59
        
        total_fetched = 0
        total_new = 0
        total_duplicate = 0
        
        # 按时间分段抓取
        current_dt = start_dt
        while current_dt < end_dt:
            # 计算分段结束时间
            segment_end = current_dt + timedelta(hours=segment_hours)
            if segment_end > end_dt:
                segment_end = end_dt
            
            start_str = current_dt.strftime("%Y-%m-%d %H:%M:%S")
            end_str = segment_end.strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info(f"抓取 {source} 数据: {start_str} 到 {end_str}")
            
            try:
                result = self.fetch_and_store(source, start_str, end_str)
                total_fetched += result.get('total_fetched', 0)
                total_new += result.get('new_count', 0)
                total_duplicate += result.get('duplicate_count', 0)
            except Exception as e:
                logger.error(f"抓取分段 {start_str} 到 {end_str} 失败: {e}")
            
            # 移动到下一个分段
            current_dt = segment_end
        
        return {
            "total_fetched": total_fetched,
            "new_count": total_new,
            "duplicate_count": total_duplicate
        }

    def fetch_all_sources_recent(self) -> Dict[str, Any]:
        """
        抓取所有启用的新闻源的最近一小时数据
        """
        results = {}
        sources = self.session.query(NewsSource).filter_by(enabled=True).all()

        for source in sources:
            try:
                result = self.fetch_recent_hour(source.source_code)
                results[source.source_code] = {
                    "source_name": source.source_name,
                    **result
                }
            except Exception as e:
                results[source.source_code] = {
                    "source_name": source.source_name,
                    "error": str(e)
                }

        return results

    def get_news_count(self, source: Optional[str] = None) -> int:
        """获取数据库中新闻总数"""
        query = self.session.query(NewsData)
        if source:
            query = query.filter(NewsData.source == source)
        return query.count()

    def get_latest_publish_time(self, source: str) -> Optional[datetime]:
        """获取指定来源的最新新闻发布时间"""
        result = self.session.query(NewsData.publish_time)\
            .filter(NewsData.source == source)\
            .order_by(NewsData.publish_time.desc())\
            .first()
        return result[0] if result else None

    def close(self):
        """关闭会话"""
        self.session.close()


class NewsCleaner:
    """
    新闻清理器 - 负责删除过期的新闻数据
    """

    def __init__(self):
        self.session = get_session()

    def clean_expired_news(self, days_to_keep: int = 5) -> Dict[str, Any]:
        """
        清理超过指定交易天数的新闻数据
        """
        start_time = datetime.now()

        # 获取需要保留的最早交易日
        recent_days = get_recent_trading_days(days_to_keep)
        if not recent_days:
            return {"error": "无法获取交易日历"}

        earliest_day = min(recent_days)
        earliest_datetime = datetime.strptime(earliest_day, "%Y%m%d")

        # 获取清理前的记录数
        before_count = self.session.query(NewsData).count()

        # 删除过期新闻
        deleted_count = 0
        try:
            # 分批删除，避免锁表
            batch_size = 1000
            while True:
                # 获取一批过期记录的ID
                expired_ids = self.session.query(NewsData.id)\
                    .filter(NewsData.publish_time < earliest_datetime)\
                    .limit(batch_size)\
                    .all()

                if not expired_ids:
                    break

                id_list = [str(row[0]) for row in expired_ids]
                # 使用原生SQL批量删除
                delete_sql = get_text(f"DELETE FROM news_data WHERE id IN ({','.join(id_list)})")
                result = self.session.execute(delete_sql)
                deleted_count += result.rowcount
                self.session.commit()

            # 记录清理日志
            after_count = self.session.query(NewsData).count()
            duration = (datetime.now() - start_time).total_seconds()

            log_entry = NewsCleanupLog(
                cleanup_time=datetime.now(),
                deleted_count=deleted_count,
                before_count=before_count,
                after_count=after_count,
                days_to_keep=days_to_keep,
                status="success",
                duration_seconds=duration
            )
            self.session.add(log_entry)
            self.session.commit()

            return {
                "deleted_count": deleted_count,
                "before_count": before_count,
                "after_count": after_count,
                "earliest_kept_date": earliest_day,
                "duration_seconds": round(duration, 2),
                "status": "success"
            }

        except Exception as e:
            self.session.rollback()
            log_entry = NewsCleanupLog(
                cleanup_time=datetime.now(),
                deleted_count=0,
                before_count=before_count,
                after_count=before_count,
                days_to_keep=days_to_keep,
                status="failed",
                error_message=str(e)
            )
            self.session.add(log_entry)
            self.session.commit()

            return {
                "error": str(e),
                "status": "failed"
            }

    def close(self):
        """关闭会话"""
        self.session.close()


def get_news_collector() -> NewsCollector:
    """获取新闻采集器实例"""
    return NewsCollector()


def get_news_cleaner() -> NewsCleaner:
    """获取新闻清理器实例"""
    return NewsCleaner()


def init_news_db():
    """初始化新闻数据库表"""
    init_news_tables()
