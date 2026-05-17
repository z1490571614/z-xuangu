"""
默认竞价接力 V2 训练样本。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class DefaultAuctionTrainingSample(Base):
    __tablename__ = "default_auction_training_sample"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))
    strategy_name = Column(String(50), nullable=False, default="default")
    strategy_version = Column(String(50), nullable=False, default="default_auction_v2")
    sample_source = Column(String(30), nullable=False)
    replay_source = Column(String(30))
    matched_recent_real_sample = Column(Integer, default=0)
    auction_source = Column(String(50))
    auction_ratio_unit = Column(String(20), default="percent")
    auction_turnover_rate_basis = Column(String(50))
    feature_snapshot_time = Column(String(30))
    feature_json = Column(Text, nullable=False)
    label_t0_limit_success = Column(Integer)
    label_t1_premium_success = Column(Integer)
    label_t1_continue_limit = Column(Integer)
    t0_high_return = Column(Float)
    t0_close_return = Column(Float)
    t1_open_return = Column(Float)
    t1_high_return = Column(Float)
    t1_close_return = Column(Float)
    is_t0_limit_up = Column(Integer)
    is_t1_limit_up = Column(Integer)
    is_t0_one_line_limit_up = Column(Integer)
    is_t1_one_line_limit_up = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "strategy_version",
            "trade_date",
            "ts_code",
            "sample_source",
            name="uk_default_auction_sample",
        ),
        Index("idx_default_auction_sample_date", "trade_date"),
        Index(
            "idx_default_auction_sample_labels",
            "label_t0_limit_success",
            "label_t1_premium_success",
            "label_t1_continue_limit",
        ),
    )
