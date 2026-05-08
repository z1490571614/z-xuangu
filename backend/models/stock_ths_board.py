"""
同花顺板块按需持久化模型
"""
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class ThsBoardIndex(Base):
    """按需保存用到过的同花顺板块代码和名称"""
    __tablename__ = "ths_board_index"

    id = Column(Integer, primary_key=True, index=True)
    board_code = Column(String(20), nullable=False, unique=True, index=True)
    board_name = Column(String(100), nullable=False)
    board_type = Column(String(20), nullable=True)
    source = Column(String(32), default="ths_index")
    raw_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StockThsBoardMember(Base):
    """选股结果驱动的个股-同花顺板块关系"""
    __tablename__ = "stock_ths_board_member"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    board_code = Column(String(20), nullable=False, index=True)
    board_name = Column(String(100), nullable=False)
    board_type = Column(String(20), nullable=True, index=True)
    matched_from = Column(String(32), default="ths_member")
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", "board_code", name="uk_stock_ths_board"),
        Index("idx_stock_ths_board_date_code", "trade_date", "ts_code"),
    )
