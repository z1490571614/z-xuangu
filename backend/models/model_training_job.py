"""
模型训练任务表。
"""
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class ModelTrainingJob(Base):
    __tablename__ = "model_training_job"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    phase = Column(String(50), nullable=False, default="prepare")
    progress = Column(Integer, nullable=False, default=0)
    mode = Column(String(20), nullable=False, default="test")
    auto_activate = Column(Integer, nullable=False, default=0)
    train_start_date = Column(String(10), nullable=False)
    train_end_date = Column(String(10), nullable=False)
    params_json = Column(Text)
    acceptance_json = Column(Text)
    attempts_json = Column(Text)
    logs_json = Column(Text)
    best_model_version = Column(String(255))
    best_model_path = Column(String(500))
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
