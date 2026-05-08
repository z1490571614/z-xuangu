"""
新闻数据库模型和连接管理 - 完全独立，避免循环导入
"""
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Float,
    Boolean, UniqueConstraint, Index, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# 创建独立的Base
Base = declarative_base()


class NewsData(Base):
    __tablename__ = 'news_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=True)
    publish_time = Column(DateTime, nullable=False)
    source = Column(String(20), nullable=False)
    source_name = Column(String(50), nullable=False)
    title_hash = Column(String(64), nullable=False)
    url = Column(String(500), nullable=True)
    news_category = Column(String(100), nullable=True)
    sentiment_type = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('title_hash', 'source', 'publish_time', name='uq_news_unique'),
        Index('idx_news_publish_time', 'publish_time'),
        Index('idx_news_source', 'source'),
        Index('idx_news_title_hash', 'title_hash'),
        Index('idx_news_created_at', 'created_at'),
    )


class NewsThemeRelation(Base):
    __tablename__ = 'news_theme_relation'

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, nullable=False)
    trade_date = Column(String(8), nullable=True)
    publish_time = Column(DateTime, nullable=True)
    source = Column(String(20), nullable=True)
    title = Column(Text, nullable=True)
    theme_name = Column(String(100), nullable=False)
    normalized_theme_name = Column(String(100), nullable=False)
    ts_code = Column(String(20), nullable=False)
    stock_name = Column(String(50), nullable=False)
    role = Column(String(20), nullable=True)
    action = Column(String(50), nullable=True)
    action_strength = Column(Integer, default=0)
    time_phrase = Column(String(20), nullable=True)
    sentiment_for_theme = Column(String(20), nullable=True)
    confidence = Column(Float, default=0)
    credibility_level = Column(String(20), nullable=True)
    evidence = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('news_id', 'normalized_theme_name', 'ts_code', name='uq_news_theme_stock'),
        Index('idx_news_theme_relation_stock_date', 'ts_code', 'trade_date'),
        Index('idx_news_theme_relation_theme', 'normalized_theme_name'),
    )


class NewsStockThemeAttribution(Base):
    __tablename__ = 'stock_theme_attribution'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False)
    stock_name = Column(String(50), nullable=True)
    trade_date = Column(String(8), nullable=False)
    primary_theme = Column(String(100), nullable=True)
    theme_score = Column(Integer, default=0)
    confidence = Column(String(20), nullable=True)
    candidate_themes_json = Column(Text, nullable=True)
    evidence_list_json = Column(Text, nullable=True)
    explanation_lines_json = Column(Text, nullable=True)
    stock_sentiment_policy = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uq_stock_theme_attribution'),
        Index('idx_stock_theme_attribution_stock_date', 'ts_code', 'trade_date'),
        Index('idx_stock_theme_attribution_theme', 'primary_theme'),
    )


class NewsSource(Base):
    __tablename__ = 'news_source'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_code = Column(String(20), unique=True, nullable=False)
    source_name = Column(String(50), nullable=False)
    enabled = Column(Boolean, default=True)
    last_fetch_time = Column(DateTime, nullable=True)
    fetch_interval_minutes = Column(Integer, default=60)
    max_fetch_count = Column(Integer, default=1500)
    priority = Column(Integer, default=10)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class NewsCleanupLog(Base):
    __tablename__ = 'news_cleanup_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cleanup_time = Column(DateTime, nullable=False)
    deleted_count = Column(Integer, default=0)
    before_count = Column(Integer, default=0)
    after_count = Column(Integer, default=0)
    days_to_keep = Column(Integer, default=5)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)


class NewsFetchLog(Base):
    __tablename__ = 'news_fetch_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(20), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    total_fetched = Column(Integer, default=0)
    new_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)


# 数据库连接配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/xuangu.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Session = scoped_session(SessionFactory)


def init_news_tables():
    Base.metadata.create_all(bind=engine)


def get_session():
    return Session()


def close_session(session):
    if session:
        session.close()


def get_engine():
    return engine


def get_text(sql):
    return text(sql)


# 导出模型供其他模块使用
__all__ = [
    "Base", "NewsData", "NewsThemeRelation", "NewsStockThemeAttribution",
    "NewsSource", "NewsCleanupLog", "NewsFetchLog",
    "init_news_tables", "get_session", "close_session", "get_engine", "get_text"
]
