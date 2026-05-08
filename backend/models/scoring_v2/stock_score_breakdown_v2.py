"""
评分V2拆解表 - Alpha评分各维度拆解
"""
from sqlalchemy import Column, Integer, Float, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class StockScoreBreakdownV2(Base):
    __tablename__ = "stock_score_breakdown_v2"

    id = Column(Integer, primary_key=True, index=True)
    score_id = Column(Integer, nullable=False, index=True)

    limitup_structure_score = Column(Float)
    seal_quality_score = Column(Float)
    auction_strength_score = Column(Float)
    trend_momentum_score = Column(Float)
    volume_price_score = Column(Float)
    sector_strength_score = Column(Float)

    limitup_structure_detail = Column(Text)
    seal_quality_detail = Column(Text)
    auction_strength_detail = Column(Text)
    trend_momentum_detail = Column(Text)
    volume_price_detail = Column(Text)
    sector_strength_detail = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
