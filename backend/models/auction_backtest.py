"""
竞价增强回测数据模型。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class StockAuctionOpen(Base):
    """历史开盘集合竞价数据。"""
    __tablename__ = "stock_auction_open"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    open = Column(Float)           # 废弃(stk_auction_o专属), 保留兼容
    high = Column(Float)           # 废弃, 保留兼容
    low = Column(Float)            # 废弃, 保留兼容
    close = Column(Float)          # 废弃, 保留兼容
    vwap = Column(Float)           # 废弃, 保留兼容
    price = Column(Float)          # stk_auction.price 竞价成交均价
    vol = Column(Float)            # stk_auction.vol 竞价成交量(股)
    amount = Column(Float)         # stk_auction.amount 竞价成交额
    pre_close = Column(Float)      # stk_auction.pre_close 前收盘价
    auction_ratio = Column(Float)
    auction_turnover_rate = Column(Float)
    source = Column(String(30), default="tushare_stk_auction")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("trade_date", "ts_code", name="_auction_open_ts_date_uc"),
        Index("idx_auction_open_date_code", "trade_date", "ts_code"),
    )
