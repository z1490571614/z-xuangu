"""股票别名映射服务。

优先复用本地已有数据，给新闻主题抽取提供 股票简称/全称/代码 -> ts_code 的映射。
"""
import logging
import re
from typing import Dict, Iterable, Optional

from sqlalchemy import text

from backend.database import SessionLocal
from backend.models import SelectedStock
from backend.services.news_theme_extractor import NewsThemeExtractor

logger = logging.getLogger(__name__)


EXCLUDE_NAME_WORDS = (
    "指数", "ETF", "基金", "转债", "国债", "可转债", "创业板指",
    "科创50", "沪深300", "中证", "上证", "深证", "板块", "概念",
)


class StockAliasService:
    """构建新闻抽取用股票别名表。"""

    @classmethod
    def load_aliases(cls, db=None, include_stock_basic: bool = True) -> Dict[str, str]:
        owns_session = db is None
        db = db or SessionLocal()
        try:
            aliases: Dict[str, str] = {}
            aliases.update(cls._load_from_selected_stock(db))
            if include_stock_basic:
                aliases.update(cls._load_from_optional_stock_basic(db))
            return aliases
        finally:
            if owns_session:
                db.close()

    @classmethod
    def _load_from_selected_stock(cls, db) -> Dict[str, str]:
        rows = db.query(SelectedStock.ts_code, SelectedStock.name).filter(
            SelectedStock.ts_code.isnot(None),
            SelectedStock.name.isnot(None),
        ).distinct().all()
        return cls.build_aliases_from_rows(rows)

    @classmethod
    def _load_from_optional_stock_basic(cls, db) -> Dict[str, str]:
        try:
            rows = db.execute(text(
                "SELECT ts_code, symbol, name, fullname, list_status "
                "FROM stock_basic WHERE list_status = 'L'"
            )).mappings().all()
        except Exception as e:
            logger.debug(f"本地 stock_basic 不可用，使用 selected_stock 别名: {e}")
            return {}
        return cls.build_aliases_from_rows(rows)

    @classmethod
    def build_aliases_from_rows(cls, rows: Iterable) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for row in rows:
            ts_code = cls._get(row, "ts_code")
            if not ts_code:
                continue
            if cls._get(row, "list_status") and cls._get(row, "list_status") != "L":
                continue

            names = [
                cls._get(row, "name"),
                cls._get(row, "fullname"),
                cls._get(row, "symbol"),
                ts_code,
            ]
            for name in names:
                normalized = NewsThemeExtractor.normalize_stock_name(name)
                if cls._is_valid_alias(normalized):
                    aliases[normalized] = ts_code
        return aliases

    @staticmethod
    def _get(row, key: str) -> Optional[str]:
        if isinstance(row, dict):
            value = row.get(key)
        else:
            value = getattr(row, key, None)
            if value is None and hasattr(row, "_mapping"):
                value = row._mapping.get(key)
        return str(value or "").strip()

    @staticmethod
    def _is_valid_alias(alias: str) -> bool:
        if not alias or len(alias) < 2 or len(alias) > 40:
            return False
        if any(word in alias for word in EXCLUDE_NAME_WORDS):
            return False
        if re.fullmatch(r"\d{6}", alias) or re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", alias):
            return True
        if not re.search(r"[\u4e00-\u9fffA-Za-z]", alias):
            return False
        return True


def get_stock_alias_service() -> StockAliasService:
    return StockAliasService()
