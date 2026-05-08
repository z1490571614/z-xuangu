"""
异动解读ORM模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.sql import func
from backend.database import Base


class StockAnomalyInterpretation(Base):
    """股票异动解读表"""
    __tablename__ = "stock_anomaly_interpretation"

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    stock_name = Column(String(100))
    trade_date = Column(String(10), nullable=False, index=True)

    # 旧版字段（保留兼容）
    summary_title = Column(String(255))
    summary_text = Column(Text)
    main_reasons_json = Column(Text)
    event_cards_json = Column(Text)
    tags_json = Column(Text)
    risk_notes_json = Column(Text)
    data_sources_json = Column(Text)

    # 同花顺1:1复刻字段（新版）
    core_tags_line = Column(String(255), comment="核心标签行（用+连接）")
    industry_reason = Column(Text, comment="行业原因（板块宏观驱动）")
    company_reasons_json = Column(Text, comment="公司原因数组（JSON）")
    market_background = Column(String(255), comment="行情背景")
    news_window_type = Column(String(50), comment="新闻窗口类型")

    generated_by = Column(String(50))
    data_status = Column(String(50))
    disclaimer = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_anomaly_stock_date", "stock_code", "trade_date"),
        Index("idx_anomaly_trade_date", "trade_date"),
    )
