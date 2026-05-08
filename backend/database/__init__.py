"""
数据库模块

包含主数据库和新闻数据库的统一入口
"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/xuangu.db")

_is_sqlite = "sqlite" in DATABASE_URL

pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))
pool_pre_ping = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=QueuePool,
    pool_size=pool_size,
    max_overflow=max_overflow if not _is_sqlite else 0,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle,
    pool_pre_ping=pool_pre_ping,
    echo=False,
)
logger.info(
    f"数据库连接池配置: pool_size={pool_size}, max_overflow={max_overflow}, "
    f"pool_timeout={pool_timeout}, pool_recycle={pool_recycle}"
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA foreign_keys=ON")
    if _is_sqlite:
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 导入新闻数据库相关函数
from .news_db import init_news_tables, get_session, close_session, get_engine

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_news_tables",
    "get_session",
    "close_session",
    "get_engine"
]