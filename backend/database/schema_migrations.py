"""
轻量级 SQLite schema 补丁。
"""
import logging
from typing import Dict

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def ensure_runtime_columns(engine) -> None:
    """补齐 create_all 不会自动添加的既有表字段。"""
    if engine.dialect.name != "sqlite":
        return

    additions: Dict[str, Dict[str, str]] = {
        "stock_auction_open": {
            "price": "FLOAT",
            "pre_close": "FLOAT",
        },
        "selected_stock": {
            "t0_limit_success_prob": "NUMERIC(5, 2)",
            "t0_limit_success_model_version": "VARCHAR(50)",
            "default_t0_limit_prob": "NUMERIC(5, 2)",
            "default_t1_premium_prob": "NUMERIC(5, 2)",
            "default_t1_continue_prob": "NUMERIC(5, 2)",
            "default_relay_score": "NUMERIC(5, 2)",
            "default_relay_model_version": "VARCHAR(255)",
        },
        "stock_risk_breakdown": {
            "market_score": "INTEGER",
            "chip_score": "INTEGER",
            "announcement_score": "INTEGER",
            "capital_score": "INTEGER",
            "sentiment_score": "INTEGER",
            "lhb_score": "INTEGER",
            "sector_score": "INTEGER",
            "market_tips": "TEXT",
            "chip_tips": "TEXT",
            "announcement_tips": "TEXT",
            "capital_tips": "TEXT",
            "sentiment_tips": "TEXT",
            "lhb_tips": "TEXT",
            "sector_tips": "TEXT",
            "news_tips": "TEXT",
            "sector_context": "TEXT",
            "lhb_strength_evidence": "TEXT",
            "lhb_risk_evidence": "TEXT",
            "strength_evidence": "TEXT",
            "risk_evidence": "TEXT",
            "risk_summary": "VARCHAR(255)",
            "warning_tip": "VARCHAR(255)",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "model_training_job": {
            "mode": "VARCHAR(20) NOT NULL DEFAULT 'test'",
            "auto_activate": "INTEGER NOT NULL DEFAULT 0",
            "best_model_version": "VARCHAR(255)",
        },
        "default_auction_training_sample": {
            "trade_date": "VARCHAR(10)",
            "ts_code": "VARCHAR(20)",
            "name": "VARCHAR(50)",
            "strategy_name": "VARCHAR(50)",
            "strategy_version": "VARCHAR(50)",
            "sample_source": "VARCHAR(30)",
            "replay_source": "VARCHAR(30)",
            "matched_recent_real_sample": "INTEGER",
            "auction_source": "VARCHAR(50)",
            "auction_ratio_unit": "VARCHAR(20)",
            "auction_turnover_rate_basis": "VARCHAR(50)",
            "feature_snapshot_time": "VARCHAR(30)",
            "feature_json": "TEXT",
            "label_t0_limit_success": "INTEGER",
            "label_t1_premium_success": "INTEGER",
            "label_t1_continue_limit": "INTEGER",
            "t0_high_return": "FLOAT",
            "t0_close_return": "FLOAT",
            "t1_open_return": "FLOAT",
            "t1_high_return": "FLOAT",
            "t1_close_return": "FLOAT",
            "is_t0_limit_up": "INTEGER",
            "is_t1_limit_up": "INTEGER",
            "is_t0_one_line_limit_up": "INTEGER",
            "is_t1_one_line_limit_up": "INTEGER",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "default_auction_training_sample" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE default_auction_training_sample (
                    id INTEGER NOT NULL PRIMARY KEY,
                    trade_date VARCHAR(10) NOT NULL,
                    ts_code VARCHAR(20) NOT NULL,
                    name VARCHAR(50),
                    strategy_name VARCHAR(50) NOT NULL,
                    strategy_version VARCHAR(50) NOT NULL,
                    sample_source VARCHAR(30) NOT NULL,
                    replay_source VARCHAR(30),
                    matched_recent_real_sample INTEGER,
                    auction_source VARCHAR(50),
                    auction_ratio_unit VARCHAR(20),
                    auction_turnover_rate_basis VARCHAR(50),
                    feature_snapshot_time VARCHAR(30),
                    feature_json TEXT NOT NULL,
                    label_t0_limit_success INTEGER,
                    label_t1_premium_success INTEGER,
                    label_t1_continue_limit INTEGER,
                    t0_high_return FLOAT,
                    t0_close_return FLOAT,
                    t1_open_return FLOAT,
                    t1_high_return FLOAT,
                    t1_close_return FLOAT,
                    is_t0_limit_up INTEGER,
                    is_t1_limit_up INTEGER,
                    is_t0_one_line_limit_up INTEGER,
                    is_t1_one_line_limit_up INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uk_default_auction_sample UNIQUE (
                        strategy_version,
                        trade_date,
                        ts_code,
                        sample_source
                    )
                )
            """))
            conn.execute(text("CREATE INDEX ix_default_auction_training_sample_id ON default_auction_training_sample (id)"))
            conn.execute(text("CREATE INDEX ix_default_auction_training_sample_trade_date ON default_auction_training_sample (trade_date)"))
            conn.execute(text("CREATE INDEX ix_default_auction_training_sample_ts_code ON default_auction_training_sample (ts_code)"))
            conn.execute(text("CREATE INDEX idx_default_auction_sample_date ON default_auction_training_sample (trade_date)"))
            conn.execute(text("""
                CREATE INDEX idx_default_auction_sample_labels
                ON default_auction_training_sample (
                    label_t0_limit_success,
                    label_t1_premium_success,
                    label_t1_continue_limit
                )
            """))
            logger.info("数据库表已补齐: default_auction_training_sample")
            existing_tables.add("default_auction_training_sample")

        if "model_training_job" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE model_training_job (
                    id INTEGER NOT NULL PRIMARY KEY,
                    model_name VARCHAR(100) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    phase VARCHAR(50) NOT NULL,
                    progress INTEGER NOT NULL,
                    mode VARCHAR(20) NOT NULL DEFAULT 'test',
                    auto_activate INTEGER NOT NULL DEFAULT 0,
                    train_start_date VARCHAR(10) NOT NULL,
                    train_end_date VARCHAR(10) NOT NULL,
                    params_json TEXT,
                    acceptance_json TEXT,
                    attempts_json TEXT,
                    logs_json TEXT,
                    best_model_version VARCHAR(255),
                    best_model_path VARCHAR(500),
                    error_message TEXT,
                    started_at DATETIME,
                    finished_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX ix_model_training_job_id ON model_training_job (id)"))
            conn.execute(text("CREATE INDEX ix_model_training_job_model_name ON model_training_job (model_name)"))
            conn.execute(text("CREATE INDEX ix_model_training_job_status ON model_training_job (status)"))
            logger.info("数据库表已补齐: model_training_job")
            existing_tables.add("model_training_job")

        if "stock_minute_bar" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE stock_minute_bar (
                    id INTEGER NOT NULL PRIMARY KEY,
                    ts_code VARCHAR(20) NOT NULL,
                    trade_date VARCHAR(10) NOT NULL,
                    trade_time VARCHAR(5) NOT NULL,
                    bar_time VARCHAR(19) NOT NULL,
                    interval INTEGER NOT NULL DEFAULT 1,
                    open FLOAT,
                    high FLOAT,
                    low FLOAT,
                    close FLOAT,
                    vol FLOAT,
                    amount FLOAT,
                    source VARCHAR(30) NOT NULL DEFAULT 'tdx_lc1',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uk_stock_minute_bar_code_time_interval UNIQUE (
                        ts_code,
                        bar_time,
                        interval
                    )
                )
            """))
            conn.execute(text("CREATE INDEX ix_stock_minute_bar_id ON stock_minute_bar (id)"))
            conn.execute(text("CREATE INDEX ix_stock_minute_bar_ts_code ON stock_minute_bar (ts_code)"))
            conn.execute(text("CREATE INDEX ix_stock_minute_bar_trade_date ON stock_minute_bar (trade_date)"))
            conn.execute(text("CREATE INDEX ix_stock_minute_bar_bar_time ON stock_minute_bar (bar_time)"))
            conn.execute(text("CREATE INDEX idx_stock_minute_bar_date_code ON stock_minute_bar (trade_date, ts_code)"))
            conn.execute(text("CREATE INDEX idx_stock_minute_bar_code_time ON stock_minute_bar (ts_code, bar_time)"))
            logger.info("数据库表已补齐: stock_minute_bar")
            existing_tables.add("stock_minute_bar")

        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                logger.info(f"数据库字段已补齐: {table}.{name}")
