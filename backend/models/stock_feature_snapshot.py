"""
候选股特征快照模型 - 用于LightGBM训练
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Index, UniqueConstraint, Text
from sqlalchemy.sql import func
from backend.database import Base


class StockFeatureSnapshot(Base):
    """候选股特征快照表"""
    __tablename__ = "stock_feature_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))

    # 9维特征
    limit_up_count_100d = Column(Integer)  # 100日涨停次数
    seal_rate_100d = Column(Float)  # 100日封板率
    rise_10d_pct = Column(Float)  # 近10日涨幅
    pre_change_pct = Column(Float)  # 昨日涨幅
    open_change_pct = Column(Float)  # 今日开盘涨幅
    auction_turnover_rate = Column(Float)  # 竞价换手率
    auction_ratio = Column(Float)  # 竞昨比
    sector_avg_pct = Column(Float)  # 板块平均涨幅
    circ_mv = Column(Float)  # 流通市值(亿)

    # 标签
    label_success = Column(Integer)  # 1=成功,0=失败
    close_return = Column(Float)  # 当日收盘涨幅
    high_return = Column(Float)  # 当日最高涨幅
    low_return = Column(Float)  # 当日最低涨幅

    # 竞价数据
    auction_volume = Column(Float)  # 竞价成交手数
    yesterday_volume = Column(Float)  # 昨日全天成交手数

    # 元数据
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('trade_date', 'ts_code', name='_feature_ts_date_uc'),
        Index('idx_feature_date_label', 'trade_date', 'label_success'),
    )


class StockDetailSnapshot(Base):
    """个股详情缓存表"""
    __tablename__ = "stock_detail_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))

    # 综合概览
    close_price = Column(Float)
    change_pct = Column(Float)
    pre_change_pct = Column(Float)
    open_change_pct = Column(Float)
    circ_mv = Column(Float)
    industry = Column(String(100))
    concept = Column(String(200))

    # 评分
    rule_score = Column(Float)
    model_score = Column(Float)
    final_score = Column(Float)
    score_level = Column(String(10))
    score_breakdown = Column(Text)  # JSON
    reasons = Column(Text)  # JSON array
    risk_tags = Column(Text)  # JSON array
    next_day_plan = Column(Text)  # JSON

    # 新闻摘要
    news_summary = Column(Text)  # JSON array
    news_sentiment = Column(String(20))  # positive/negative/neutral

    # 涨停异动
    limit_up_count = Column(Integer)
    touch_days = Column(Integer)
    limit_up_days = Column(Integer)
    seal_rate = Column(Float)
    rise_10d_pct_val = Column(Float)

    # 元数据
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('trade_date', 'ts_code', name='_detail_ts_date_uc'),
    )


class ModelVersion(Base):
    """LightGBM模型版本管理表"""
    __tablename__ = "model_version"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    train_start_date = Column(String(10))
    train_end_date = Column(String(10))
    feature_cols = Column(Text)  # JSON array
    model_metrics = Column(Text)  # JSON
    model_path = Column(String(500))
    params = Column(Text)  # JSON
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_model_active', 'model_name', 'is_active'),
    )
