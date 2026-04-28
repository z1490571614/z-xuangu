"""
选股记录模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.database import Base


class SelectionRecord(Base):
    """选股记录表"""
    __tablename__ = "selection_record"

    id = Column(Integer, primary_key=True, index=True)
    execute_time = Column(DateTime, nullable=False, server_default=func.now())
    trade_date = Column(String(10), nullable=False, index=True)
    total_count = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    execution_time = Column(Float, nullable=True)
    notification_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    stocks = relationship("SelectedStock", back_populates="record", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SelectionRecord(id={self.id}, trade_date={self.trade_date}, status={self.status})>"
