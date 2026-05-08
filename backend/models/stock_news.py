"""
新闻舆情数据模型 - 用于存储新闻及其去重、情感分类信息
"""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Index
from sqlalchemy.sql import func
from backend.database import Base


class StockNews(Base):
    """股票新闻数据表"""
    __tablename__ = "stock_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True, comment="股票代码")
    stock_name = Column(String(50), comment="股票名称")
    
    # 新闻基础信息
    title = Column(Text, nullable=False, comment="新闻标题")
    content = Column(Text, comment="新闻内容")
    url = Column(String(500), comment="新闻链接")
    source = Column(String(50), comment="新闻来源")
    publish_time = Column(String(50), comment="发布时间字符串")
    publish_datetime = Column(DateTime, comment="发布时间(标准格式)")
    
    # 去重相关字段
    title_hash = Column(String(32), index=True, comment="标题MD5哈希(一级去重)")
    content_simhash = Column(Integer, index=True, comment="内容SimHash(二级去重)")
    event_id = Column(String(64), index=True, comment="事件唯一ID(三级去重)")
    
    # 情感分类相关字段
    sentiment_type = Column(String(16), index=True, comment="情感类型: positive/negative/neutral")
    sentiment_confidence = Column(Float, comment="情感置信度(0-1)")
    news_category = Column(String(16), index=True, comment="新闻类型: 个股/行业/市场")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 索引
    __table_args__ = (
        Index("idx_stock_news_ts_publish", "ts_code", "publish_datetime"),
    )
