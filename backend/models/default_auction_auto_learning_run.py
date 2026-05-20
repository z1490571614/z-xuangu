"""
默认竞价接力 V2 手动自动学习运行记录。
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class DefaultAuctionAutoLearningRun(Base):
    __tablename__ = "default_auction_auto_learning_run"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    phase = Column(String(50), nullable=False, default="prepare", index=True)
    progress = Column(Integer, nullable=False, default=0)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)
    tdx_vipdoc_path = Column(String(500))
    ts_codes_json = Column(Text)
    selected_record_ids_json = Column(Text)
    options_json = Column(Text, nullable=False)
    stage_results_json = Column(Text, nullable=False, default="{}")
    audit_json = Column(Text)
    training_job_id = Column(Integer)
    training_diagnostics_json = Column(Text)
    backtest_json = Column(Text)
    activated_versions_json = Column(Text)
    refreshed_record_ids_json = Column(Text)
    logs_json = Column(Text, nullable=False, default="[]")
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_default_auction_auto_learning_status", "status"),
        Index("idx_default_auction_auto_learning_created", "created_at"),
        Index("idx_default_auction_auto_learning_phase", "phase"),
    )
