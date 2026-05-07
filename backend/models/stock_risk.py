"""
风险拆解模型 - 6大维度量化风险，永久存储
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index, UniqueConstraint
from sqlalchemy.sql import func
from backend.database import Base


class StockRiskBreakdown(Base):
    """风险拆解表（永久存储，可回溯历史风险走势）"""
    __tablename__ = "stock_risk_breakdown"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)

    # 总风险
    total_score = Column(Integer, nullable=False)
    risk_level = Column(String(16), nullable=False)

    # 6大维度得分（announcement_score 复用为 news_score）
    market_score = Column(Integer)
    chip_score = Column(Integer)
    announcement_score = Column(Integer)  # 复用为 news_score（舆情&公告综合）
    capital_score = Column(Integer)
    sentiment_score = Column(Integer)     # 不再使用，保留兼容
    lhb_score = Column(Integer)
    sector_score = Column(Integer)

    # 各维度风险明细(JSON)
    market_tips = Column(Text)
    chip_tips = Column(Text)
    announcement_tips = Column(Text)  # 复用为 news_tips
    capital_tips = Column(Text)
    sentiment_tips = Column(Text)     # 不再使用，保留兼容
    lhb_tips = Column(Text)
    sector_tips = Column(Text)
    news_tips = Column(Text)          # 新增：舆情&公告明细

    # 风险标签 + 高危预警
    risk_summary = Column(String(255))
    warning_tip = Column(String(255))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uk_risk_ts_date"),
        Index("idx_risk_trade_date", "trade_date"),
        Index("idx_risk_ts_code", "ts_code"),
    )


class DragonLeaderScore(Base):
    """龙头战法评分表（永久存储，可回溯历史走势）"""
    __tablename__ = "dragon_leader_score"

    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)

    # 三大核心分数
    leader_strength_score = Column(Integer, nullable=False)
    retreat_risk_score = Column(Integer, nullable=False)
    health_score = Column(Integer, nullable=False)

    # 评级
    leader_level = Column(String(16))
    risk_level = Column(String(16))
    health_level = Column(String(16))
    cycle_stage = Column(String(16))

    # Alpha 加成
    announcement_alpha_score = Column(Integer)
    lhb_alpha_score = Column(Integer)

    # 完整 JSON 输出（避免字段爆炸）
    full_result_json = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uk_dl_ts_date"),
        Index("idx_dl_trade_date", "trade_date"),
        Index("idx_dl_ts_code", "ts_code"),
    )
