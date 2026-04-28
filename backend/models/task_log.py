"""
任务日志模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from backend.database import Base


class TaskLog(Base):
    """任务日志表"""
    __tablename__ = "task_log"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(50), nullable=False, index=True)
    trigger_time = Column(DateTime, nullable=False, server_default=func.now())
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<TaskLog(id={self.id}, task_type={self.task_type}, status={self.status})>"
