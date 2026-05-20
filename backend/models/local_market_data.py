"""
本地行情数据模型。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class StockMinuteBar(Base):
    """通达信本地分钟线。"""

    __tablename__ = "stock_minute_bar"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    trade_time = Column(String(5), nullable=False)
    bar_time = Column(String(19), nullable=False, index=True)
    interval = Column(Integer, nullable=False, default=1)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    source = Column(String(30), nullable=False, default="tdx_lc1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "bar_time", "interval", name="uk_stock_minute_bar_code_time_interval"),
        Index("idx_stock_minute_bar_date_code", "trade_date", "ts_code"),
        Index("idx_stock_minute_bar_code_time", "ts_code", "bar_time"),
    )
