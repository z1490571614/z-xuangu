"""
股票详情模型
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.database import Base


class SelectedStock(Base):
    """选中的股票详情表"""
    __tablename__ = "selected_stock"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("selection_record.id"), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50), nullable=True)
    close_price = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    pre_change_pct = Column(Float, nullable=True)
    open_change_pct = Column(Float, nullable=True)
    auction_ratio = Column(Float, nullable=True)
    auction_turnover_rate = Column(Float, nullable=True)
    industry = Column(String(100), nullable=True)
    concept = Column(String(200), nullable=True)
    board_type = Column(String(50), nullable=True)
    limit_up_count = Column(Integer, nullable=True)
    touch_days = Column(Integer, nullable=True)
    limit_up_days = Column(Integer, nullable=True)
    seal_rate = Column(Float, nullable=True)
    rise_10d_pct = Column(Float, nullable=True)
    circ_mv = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    record = relationship("SelectionRecord", back_populates="stocks")

    def __repr__(self):
        return f"<SelectedStock(id={self.id}, ts_code={self.ts_code}, name={self.name})>"
