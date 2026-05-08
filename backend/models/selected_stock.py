"""
股票详情模型
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, DECIMAL
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
    close = Column(Float, nullable=True)
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

    # 涨停榜单（同花顺）数据
    lu_desc = Column(Text, nullable=True)               # 涨停原因
    lu_tag = Column(String(50), nullable=True)           # 涨停标签（如"5天3板"）
    lu_status = Column(String(50), nullable=True)        # 涨停状态（如"换手板"）
    lu_open_num = Column(Integer, nullable=True)         # 打开次数
    limit_up_suc_rate = Column(Float, nullable=True)     # 近一年涨停封板率
    latest_lu_date = Column(String(8), nullable=True)    # 最新涨停日期（YYYYMMDD）

    # 每日基本面数据
    prev_turnover_rate = Column(Float, nullable=True)    # 上一日换手率（%）

    # 评分字段
    rule_score = Column(DECIMAL(5, 2), nullable=True)
    model_score = Column(DECIMAL(5, 2), nullable=True)
    t0_limit_success_prob = Column(DECIMAL(5, 2), nullable=True)
    final_score = Column(DECIMAL(5, 2), nullable=True)
    score_level = Column(String(20), nullable=True)
    score_breakdown = Column(Text, nullable=True)  # JSON
    reasons = Column(Text, nullable=True)
    risk_tags = Column(Text, nullable=True)  # JSON array
    next_day_plan = Column(Text, nullable=True)
    model_version = Column(String(50), nullable=True)
    t0_limit_success_model_version = Column(String(50), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    record = relationship("SelectionRecord", back_populates="stocks")

    def __repr__(self):
        return f"<SelectedStock(id={self.id}, ts_code={self.ts_code}, name={self.name})>"
