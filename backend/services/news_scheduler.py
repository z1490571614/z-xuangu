"""
新闻采集定时调度服务
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from backend.services.news_collector import get_news_collector, get_news_cleaner

logger = logging.getLogger(__name__)


class NewsScheduler:
    """
    新闻调度器 - 管理定时抓取和清理任务
    """

    def __init__(self):
        self.running = False
        self.thread = None
        self.collect_interval = 3600  # 每小时抓取一次（秒）
        self.clean_interval = 86400   # 每天清理一次（秒）
        self.last_collect_time = None
        self.last_clean_time = None

    def _collect_news(self):
        """执行新闻采集任务"""
        try:
            collector = get_news_collector()
            result = collector.fetch_all_sources_recent()
            collector.close()

            logger.info(f"新闻采集完成: {result}")
            self.last_collect_time = datetime.now()

        except Exception as e:
            logger.error(f"新闻采集失败: {e}")

    def _clean_news(self):
        """执行新闻清理任务"""
        try:
            cleaner = get_news_cleaner()
            result = cleaner.clean_expired_news(days_to_keep=5)
            cleaner.close()

            if result.get("status") == "success":
                logger.info(f"新闻清理完成: 删除{result['deleted_count']}条记录")
            else:
                logger.error(f"新闻清理失败: {result.get('error')}")

            self.last_clean_time = datetime.now()

        except Exception as e:
            logger.error(f"新闻清理失败: {e}")

    def _scheduler_loop(self):
        """调度器主循环"""
        while self.running:
            now = datetime.now()

            # 执行新闻采集（每小时）
            if self.last_collect_time is None or \
               (now - self.last_collect_time).total_seconds() >= self.collect_interval:
                self._collect_news()

            # 执行新闻清理（每天，在收盘后执行）
            if self.last_clean_time is None or \
               (now - self.last_clean_time).total_seconds() >= self.clean_interval:
                # 检查是否是交易日且时间在18:00之后（收盘后）
                if now.hour >= 18:
                    self._clean_news()

            # 等待1分钟后再次检查
            time.sleep(60)

    def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("调度器已经在运行")
            return

        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        logger.info("新闻调度器已启动")

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("新闻调度器已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            "running": self.running,
            "collect_interval_hours": self.collect_interval / 3600,
            "clean_interval_days": self.clean_interval / 86400,
            "last_collect_time": self.last_collect_time.isoformat() if self.last_collect_time else None,
            "last_clean_time": self.last_clean_time.isoformat() if self.last_clean_time else None,
            "next_collect_time": (self.last_collect_time + timedelta(hours=1)).isoformat() 
                                if self.last_collect_time else None,
            "next_clean_time": (self.last_clean_time + timedelta(days=1)).isoformat() 
                               if self.last_clean_time else None
        }


def get_news_scheduler() -> NewsScheduler:
    """获取新闻调度器实例（单例）"""
    if not hasattr(get_news_scheduler, "_instance"):
        get_news_scheduler._instance = NewsScheduler()
    return get_news_scheduler._instance