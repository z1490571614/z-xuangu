"""
通用板块体系模型。

东财板块作为新主链路，旧同花顺板块表保留只读兼容。
"""
from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class BoardIndex(Base):
    """板块词典，本地归一匹配只读该表。"""

    __tablename__ = "board_index"

    id = Column(Integer, primary_key=True, index=True)
    board_code = Column(String(32), nullable=False, unique=True, index=True)
    board_name = Column(String(100), nullable=False, index=True)
    board_type = Column(String(32), nullable=True, index=True)
    source = Column(String(32), default="eastmoney", index=True)
    trade_date = Column(String(10), nullable=True, index=True)
    raw_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StockBoardMember(Base):
    """选股结果驱动的个股-板块关系。"""

    __tablename__ = "stock_board_member"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    board_code = Column(String(32), nullable=False, index=True)
    board_name = Column(String(100), nullable=False)
    board_type = Column(String(32), nullable=True, index=True)
    source = Column(String(32), default="eastmoney", index=True)
    matched_from = Column(String(64), default="dc_member")
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", "board_code", name="uk_stock_board_member"),
        Index("idx_stock_board_member_date_code", "trade_date", "ts_code"),
    )


class BoardDailySnapshot(Base):
    """板块行情快照。"""

    __tablename__ = "board_daily_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    board_code = Column(String(32), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    pct_chg = Column(Float, default=0)
    amount = Column(Float, default=0)
    turnover_rate = Column(Float, default=0)
    rank = Column(Integer, nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("board_code", "trade_date", name="uk_board_daily_snapshot"),
        Index("idx_board_daily_trade_date", "trade_date"),
    )


class BoardStrengthSnapshot(Base):
    """板块强度快照，供题材强度与风险拆解共用。"""

    __tablename__ = "board_strength_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    board_code = Column(String(32), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    limit_up_count = Column(Integer, default=0)
    limit_up_member_count = Column(Integer, default=0)
    member_count = Column(Integer, default=0)
    avg_member_pct = Column(Float, default=0)
    top_member_pct = Column(Float, default=0)
    board_pct_chg = Column(Float, default=0)
    money_net_amount = Column(Float, default=0)
    strength_score = Column(Float, default=0)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("board_code", "trade_date", name="uk_board_strength_snapshot"),
        Index("idx_board_strength_trade_date", "trade_date"),
    )
