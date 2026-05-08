"""
综合概览简报表 - AI生成/fallback的个股综合简报
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.sql import func
from backend.database import Base


class StockOverviewBrief(Base):
    __tablename__ = "stock_overview_brief"

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    stock_name = Column(String(100))
    trade_date = Column(String(10), nullable=False, index=True)

    brief = Column(Text)
    ai_suggestion = Column(String(50))
    suggestion_reason = Column(Text)

    positive_tags_json = Column(Text)
    negative_tags_json = Column(Text)
    key_points_json = Column(Text)

    input_snapshot_json = Column(Text)
    ai_provider = Column(String(50))
    ai_model = Column(String(100))
    prompt_version = Column(String(100))
    output_status = Column(String(50))
    error_message = Column(Text)

    disclaimer = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_overview_stock_date", "stock_code", "trade_date"),
    )
