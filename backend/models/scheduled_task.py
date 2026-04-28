"""
定时任务模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class ScheduledTask(Base):
    """定时任务表"""
    __tablename__ = "scheduled_task"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)
    last_run_time = Column(DateTime, nullable=True)
    next_run_time = Column(DateTime, nullable=True)
    config = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ScheduledTask(id={self.id}, name={self.name}, enabled={self.enabled})>"
