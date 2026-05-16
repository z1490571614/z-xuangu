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
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
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
                    best_model_version VARCHAR(50),
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

        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                logger.info(f"数据库字段已补齐: {table}.{name}")
