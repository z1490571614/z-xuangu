"""
评分V2风险拆解表 - 风险评分各维度拆解
"""
from sqlalchemy import Column, Integer, Float, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class StockRiskBreakdownV2(Base):
    __tablename__ = "stock_risk_breakdown_v2"

    id = Column(Integer, primary_key=True, index=True)
    score_id = Column(Integer, nullable=False, index=True)

    high_position_risk = Column(Float)
    open_board_risk = Column(Float)
    liquidity_risk = Column(Float)
    sentiment_risk = Column(Float)
    sector_laggard_risk = Column(Float)
    news_risk = Column(Float)
    capital_structure_risk = Column(Float)
    volatility_risk = Column(Float)

    high_position_detail = Column(Text)
    open_board_detail = Column(Text)
    liquidity_detail = Column(Text)
    sentiment_detail = Column(Text)
    sector_laggard_detail = Column(Text)
    news_detail = Column(Text)
    capital_structure_detail = Column(Text)
    volatility_detail = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
