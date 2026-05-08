"""
新闻数据库连接管理 - 独立于主数据库
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base

# 创建独立的Base
Base = declarative_base()

# 获取数据库URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/xuangu.db")

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# 创建会话工厂
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建线程安全的会话
Session = scoped_session(SessionFactory)


def init_news_tables():
    """
    初始化新闻数据库表
    """
    Base.metadata.create_all(bind=engine)


def get_session():
    """
    获取数据库会话
    """
    return Session()


def close_session(session):
    """
    关闭数据库会话
    """
    if session:
        session.close()


def get_engine():
    """
    获取数据库引擎
    """
    return engine


def get_base():
    """
    获取Base类
    """
    return Base