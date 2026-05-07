"""
龙虎榜数据模型 - 永久存储
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index, UniqueConstraint
from sqlalchemy.sql import func
from backend.database import Base


class StockLhb(Base):
    """龙虎榜数据表（永久存储，不删除可回溯）"""
    __tablename__ = "stock_lhb"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)

    # 上榜基本信息
    reason = Column(String(100))
    change_pct = Column(Float)
    amount = Column(Float)
    turnover_rate = Column(Float)
    lhb_type = Column(String(16), default="当日榜")

    # 资金汇总
    buy_amount = Column(Float)
    sell_amount = Column(Float)
    net_amount = Column(Float)
    net_rate = Column(Float)
    amount_rate = Column(Float)

    # 分析结论
    main_type = Column(String(16))
    action_tag = Column(String(32))

    # 明细JSON
    detail_json = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uk_lhb_ts_date"),
        Index("idx_lhb_trade_date", "trade_date"),
        Index("idx_lhb_ts_code", "ts_code"),
    )
