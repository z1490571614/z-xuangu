"""
竞价增强回测与龙头主升 T+0 训练样本模型。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class StockAuctionOpen(Base):
    """历史开盘集合竞价数据。"""
    __tablename__ = "stock_auction_open"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    vwap = Column(Float)
    auction_ratio = Column(Float)
    auction_turnover_rate = Column(Float)
    source = Column(String(30), default="tushare_stk_auction_o")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("trade_date", "ts_code", name="_auction_open_ts_date_uc"),
        Index("idx_auction_open_date_code", "trade_date", "ts_code"),
    )


class LeaderMainT0TrainingSample(Base):
    """龙头主升 T+0 非一字涨停训练样本。"""
    __tablename__ = "leader_main_t0_training_sample"

    id = Column(Integer, primary_key=True, index=True)
    strategy_version = Column(String(50), nullable=False, default="leader_main_t0")
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))
    limit_up_streak = Column(Integer)
    market_height_rank = Column(Integer)
    limit_up_count_100d = Column(Integer)
    seal_rate_100d = Column(Float)
    rise_5d_pct = Column(Float)
    rise_10d_pct = Column(Float)
    pre_change_pct = Column(Float)
    open_change_pct = Column(Float)
    auction_ratio = Column(Float)
    auction_turnover_rate = Column(Float)
    auction_amount = Column(Float)
    auction_vwap_gap_pct = Column(Float)
    circ_mv = Column(Float)
    sector_change_pct = Column(Float)
    sector_limit_up_count = Column(Integer)
    sector_hot_rank = Column(Integer)
    rule_score = Column(Float)
    label_t0_limit_success = Column(Integer)
    t0_touched_limit = Column(Integer)
    t0_closed_limit = Column(Integer)
    is_one_line_limit_up = Column(Integer)
    t0_high_return = Column(Float)
    t0_close_return = Column(Float)
    t0_low_return = Column(Float)
    feature_json = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("trade_date", "ts_code", name="_leader_t0_ts_date_uc"),
        Index("idx_leader_t0_date_label", "trade_date", "label_t0_limit_success"),
    )
