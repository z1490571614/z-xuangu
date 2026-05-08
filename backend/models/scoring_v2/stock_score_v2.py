"""
评分V2主表 - 每次选股后最终评分结果
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from sqlalchemy.sql import func
from backend.database import Base


class StockScoreV2(Base):
    __tablename__ = "stock_score_v2"

    id = Column(Integer, primary_key=True, index=True)
    selection_record_id = Column(Integer, nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    stock_name = Column(String(100))
    trade_date = Column(String(10), nullable=False, index=True)

    alpha_score = Column(Float)
    risk_score = Column(Float)
    model_score = Column(Float)
    expected_return_score = Column(Float)
    raw_score = Column(Float)
    final_score = Column(Float, index=True)
    score_grade = Column(String(10))

    model_success_prob = Column(Float)
    model_expected_return = Column(Float)
    model_expected_drawdown = Column(Float)
    reward_risk_ratio = Column(Float)

    action_level = Column(String(50))
    position_suggestion = Column(String(100))
    entry_suggestion = Column(Text)
    stop_loss_suggestion = Column(Text)
    take_profit_suggestion = Column(Text)

    explanation = Column(Text)
    risk_flags = Column(Text)
    model_version = Column(String(100))
    score_version = Column(String(100))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_sv2_trade_date', 'trade_date'),
        Index('idx_sv2_stock_code', 'stock_code'),
        Index('idx_sv2_record_id', 'selection_record_id'),
        Index('idx_sv2_final_score', 'final_score'),
    )
