"""
封板率数据模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Index, UniqueConstraint
from sqlalchemy.sql import func
from backend.database import Base


class StockDailyData(Base):
    """股票日线数据表（前复权）"""
    __tablename__ = "stock_daily_data"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    pre_close = Column(Float)
    change = Column(Float)
    pct_chg = Column(Float)
    up_limit = Column(Float)  # 涨停价
    down_limit = Column(Float)  # 跌停价
    vol = Column(Float)
    amount = Column(Float)
    adj_factor = Column(Float)  # 复权因子
    is_adj = Column(Integer, default=1)  # 是否已复权：1=前复权，0=未复权
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='_ts_code_date_uc'),
        Index('idx_ts_code_trade_date', 'ts_code', 'trade_date'),
    )


class SealRateCache(Base):
    """封板率计算结果缓存"""
    __tablename__ = "seal_rate_cache"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)  # 计算基准日
    period_days = Column(Integer, nullable=False, default=100)  # 计算周期（交易日）
    touch_days = Column(Integer, default=0)  # 区间触板天数
    limit_up_days = Column(Integer, default=0)  # 区间涨停天数
    seal_rate = Column(Float)  # 封板率 (limit_up_days / touch_days)
    start_date = Column(String(10))  # 周期起始日期
    end_date = Column(String(10))  # 周期结束日期
    data_complete = Column(Integer, default=1)  # 数据完整性：1=完整，0=部分缺失
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', 'period_days', name='_ts_code_date_period_uc'),
        Index('idx_cache_ts_trade_period', 'ts_code', 'trade_date', 'period_days'),
    )
