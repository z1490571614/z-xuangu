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
        "selected_stock": {
            "t0_limit_success_prob": "NUMERIC(5, 2)",
            "t0_limit_success_model_version": "VARCHAR(50)",
        }
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                logger.info(f"数据库字段已补齐: {table}.{name}")
