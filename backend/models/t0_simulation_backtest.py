"""
当日涨停模型日线模拟盘回测模型。
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class T0SimulationBacktestRun(Base):
    __tablename__ = "t0_simulation_backtest_run"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), nullable=False, default="pending")
    start_date = Column(String(10), nullable=False, index=True)
    end_date = Column(String(10), nullable=False, index=True)
    model_name = Column(String(80), nullable=False, default="default_auction_t0_limit_lgbm")
    model_version = Column(String(80))
    resolved_model_version = Column(String(80))
    sample_source = Column(String(30), nullable=False, default="real_selected")
    initial_cash = Column(Float, nullable=False, default=100000.0)
    buy_top_n = Column(Integer, nullable=False, default=2)
    max_positions = Column(Integer, nullable=False, default=4)
    min_buy_prob_pct = Column(Float, nullable=False, default=50.0)
    min_open_change_pct = Column(Float, nullable=False, default=-3.0)
    max_open_change_pct = Column(Float, nullable=False, default=7.0)
    take_profit_pct = Column(Float, nullable=False, default=8.0)
    high_profit_hold_pct = Column(Float, nullable=False, default=13.0)
    profit_pullback_pct = Column(Float, nullable=False, default=5.0)
    stop_loss_pct = Column(Float, nullable=False, default=-5.0)
    max_holding_days = Column(Integer, nullable=False, default=3)
    force_close_on_end = Column(Integer, nullable=False, default=0)
    cost_json = Column(Text, nullable=False, default="{}")
    summary_json = Column(Text, nullable=False, default="{}")
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_t0_sim_backtest_run_status", "status"),
        Index("idx_t0_sim_backtest_run_created", "created_at"),
        Index("idx_t0_sim_backtest_run_date", "start_date", "end_date"),
    )


class T0SimulationBacktestDaily(Base):
    __tablename__ = "t0_simulation_backtest_daily"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("t0_simulation_backtest_run.id"), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    cash = Column(Float, nullable=False, default=0.0)
    market_value = Column(Float, nullable=False, default=0.0)
    equity = Column(Float, nullable=False, default=0.0)
    daily_return_pct = Column(Float, nullable=False, default=0.0)
    drawdown_pct = Column(Float, nullable=False, default=0.0)
    position_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("run_id", "trade_date", name="uk_t0_sim_backtest_daily"),
    )


class T0SimulationBacktestTrade(Base):
    __tablename__ = "t0_simulation_backtest_trade"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("t0_simulation_backtest_run.id"), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))
    model_prob = Column(Float)
    rank = Column(Integer)
    buy_date = Column(String(10), nullable=False, index=True)
    buy_time = Column(String(5), nullable=False, default="09:30")
    buy_price = Column(Float, nullable=False)
    buy_amount = Column(Float, nullable=False)
    sell_date = Column(String(10))
    sell_time = Column(String(5))
    sell_price = Column(Float)
    holding_days = Column(Integer, nullable=False, default=0)
    return_pct = Column(Float)
    profit_amount = Column(Float)
    sell_reason = Column(String(30))
    status = Column(String(20), nullable=False, default="open")

    __table_args__ = (
        Index("idx_t0_sim_backtest_trade_run", "run_id"),
        Index("idx_t0_sim_backtest_trade_buy_date", "buy_date"),
        Index("idx_t0_sim_backtest_trade_stock", "ts_code"),
    )
