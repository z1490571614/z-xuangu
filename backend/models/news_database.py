"""
新闻数据库模型 - 永久性新闻存储系统
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Boolean, UniqueConstraint, Index
)
from datetime import datetime

# 从news_db导入Base，避免循环导入
from backend.database.news_db import Base


class NewsData(Base):
    """
    新闻数据表 - 存储所有抓取的新闻数据
    """
    __tablename__ = 'news_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False, comment='新闻标题')
    content = Column(Text, nullable=True, comment='新闻内容')
    publish_time = Column(DateTime, nullable=False, comment='发布时间')
    source = Column(String(20), nullable=False, comment='新闻来源(cls/10jqka/yicai等)')
    source_name = Column(String(50), nullable=False, comment='来源名称')
    title_hash = Column(String(64), nullable=False, comment='标题MD5哈希，用于去重')
    url = Column(String(500), nullable=True, comment='新闻链接')
    news_category = Column(String(100), nullable=True, comment='新闻分类')
    sentiment_type = Column(String(20), nullable=True, comment='情感类型(positive/negative/neutral)')
    sentiment_score = Column(Float, nullable=True, comment='情感分数')
    created_at = Column(DateTime, default=datetime.now, comment='入库时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 索引优化
    __table_args__ = (
        UniqueConstraint('title_hash', 'source', 'publish_time', name='uq_news_unique'),
        Index('idx_news_publish_time', 'publish_time'),
        Index('idx_news_source', 'source'),
        Index('idx_news_title_hash', 'title_hash'),
        Index('idx_news_created_at', 'created_at'),
    )


class NewsSource(Base):
    """
    新闻来源配置表 - 管理新闻源配置
    """
    __tablename__ = 'news_source'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_code = Column(String(20), unique=True, nullable=False, comment='来源代码(cls/10jqka等)')
    source_name = Column(String(50), nullable=False, comment='来源名称')
    enabled = Column(Boolean, default=True, comment='是否启用')
    last_fetch_time = Column(DateTime, nullable=True, comment='最后抓取时间')
    fetch_interval_minutes = Column(Integer, default=60, comment='抓取间隔(分钟)')
    max_fetch_count = Column(Integer, default=1500, comment='单次最大抓取数量')
    priority = Column(Integer, default=10, comment='优先级(数字越小优先级越高)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class NewsCleanupLog(Base):
    """
    数据清理日志表 - 记录数据清理任务的执行情况
    """
    __tablename__ = 'news_cleanup_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleanup_time = Column(DateTime, nullable=False, comment='清理执行时间')
    deleted_count = Column(Integer, default=0, comment='删除的记录数')
    before_count = Column(Integer, default=0, comment='清理前记录数')
    after_count = Column(Integer, default=0, comment='清理后记录数')
    days_to_keep = Column(Integer, default=5, comment='保留的交易天数')
    status = Column(String(20), nullable=False, comment='执行状态(success/failed)')
    error_message = Column(Text, nullable=True, comment='错误信息')
    duration_seconds = Column(Float, nullable=True, comment='执行耗时(秒)')


class NewsFetchLog(Base):
    """
    新闻抓取日志表 - 记录每次抓取任务的执行情况
    """
    __tablename__ = 'news_fetch_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(20), nullable=False, comment='新闻来源')
    start_time = Column(DateTime, nullable=False, comment='抓取开始时间')
    end_time = Column(DateTime, nullable=True, comment='抓取结束时间')
    total_fetched = Column(Integer, default=0, comment='抓取总数')
    new_count = Column(Integer, default=0, comment='新增记录数')
    duplicate_count = Column(Integer, default=0, comment='重复记录数')
    failed_count = Column(Integer, default=0, comment='失败记录数')
    status = Column(String(20), nullable=False, comment='执行状态(running/success/failed)')
    error_message = Column(Text, nullable=True, comment='错误信息')
    duration_seconds = Column(Float, nullable=True, comment='执行耗时(秒)')