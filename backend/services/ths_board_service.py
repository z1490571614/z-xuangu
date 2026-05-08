"""
同花顺个股板块关系按需持久化服务
"""
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.database import SessionLocal
from backend.models.stock_ths_board import StockThsBoardMember, ThsBoardIndex
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)

VALID_BOARD_TYPES = {"N", "I", "TH"}
BOARD_CODE_PREFIXES = ("881", "884", "885", "886")


class ThsBoardService:
    """维护同花顺板块指数词典和入选股票板块关系"""

    _shared_catalog_cache: Optional[List[Dict[str, Any]]] = None

    def __init__(self):
        self._pro = None
        self._hot_board_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    @classmethod
    def clear_catalog_cache(cls) -> None:
        """清空进程内板块词典缓存，测试或启动同步后使用。"""
        cls._shared_catalog_cache = None

    def sync_board_index_catalog(self, force: bool = True) -> Dict[str, int]:
        """启动时同步一次同花顺概念/行业指数到数据库。

        运行期匹配只读 ths_board_index，不在每次归因时调用 Tushare。
        """
        stats = {"fetched": 0, "saved": 0, "failed": 0}
        db = SessionLocal()
        try:
            for board_type in ("N", "I"):
                try:
                    df = self.pro.ths_index(type=board_type)
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(f"同步同花顺{board_type}板块指数失败: {e}")
                    continue
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    code = str(row.get("ts_code", "") or "").strip()
                    name = str(row.get("name", "") or "").strip()
                    if not code or not name or not self._is_relevant_board_code(code):
                        continue
                    row_type = str(row.get("type", "") or board_type).strip() or board_type
                    if row_type and row_type not in VALID_BOARD_TYPES:
                        continue
                    stats["fetched"] += 1
                    self._upsert_board_index(db, {
                        "board_code": code,
                        "board_name": name,
                        "board_type": row_type,
                        "source": f"ths_index_{board_type}",
                        "raw_json": json.dumps(row.to_dict(), ensure_ascii=False, default=str),
                    })
                    stats["saved"] += 1
            db.commit()
            self.clear_catalog_cache()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return stats

    def get_board_index_catalog(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        """从数据库读取同花顺板块词典，进程内缓存，避免重复查库。"""
        if not force_reload and self.__class__._shared_catalog_cache is not None:
            return self.__class__._shared_catalog_cache

        db = SessionLocal()
        try:
            rows = db.query(ThsBoardIndex).filter(
                ThsBoardIndex.is_active.is_(True),
            ).order_by(ThsBoardIndex.board_type.asc(), ThsBoardIndex.board_name.asc()).all()
            catalog = [
                {
                    "ts_code": row.board_code,
                    "name": row.board_name,
                    "type": row.board_type or "",
                    "source": row.source or "ths_board_index",
                    "clean_name": self._clean_text(row.board_name),
                }
                for row in rows
                if self._is_relevant_board_code(row.board_code) and row.board_name
            ]
            self.__class__._shared_catalog_cache = catalog
            return catalog
        finally:
            db.close()

    def normalize_board_terms(self, text: str, source: str = "", top_n: int = 5) -> List[Dict[str, Any]]:
        """将新闻主题/涨停标签/行业字段归一到同花顺标准板块。

        仅使用启动时同步到 ths_board_index 的本地词典，不触发 Tushare 请求。
        """
        terms = self._split_terms(text)
        if not terms:
            return []

        matches: Dict[str, Dict[str, Any]] = {}
        catalog = self.get_board_index_catalog()
        for term in terms:
            clean_term = self._clean_text(term)
            if len(clean_term) < 2:
                continue
            for board in catalog:
                clean_name = board.get("clean_name", "")
                score, reason = self._board_name_match_score(clean_term, clean_name, board.get("name", ""))
                if score <= 0:
                    continue
                existing = matches.get(board["ts_code"])
                if existing and existing["match_score"] >= score:
                    continue
                matches[board["ts_code"]] = {
                    "ts_code": board["ts_code"],
                    "name": board["name"],
                    "type": board.get("type", ""),
                    "match_score": score,
                    "matched_from": source or "ths_board_index",
                    "match_reasons": [f"{source or '文本'}“{term}”{reason}"],
                }

        return sorted(
            matches.values(),
            key=lambda item: (item.get("match_score", 0), len(item.get("name", ""))),
            reverse=True,
        )[:top_n]

    def get_stock_boards(
        self,
        ts_code: str,
        trade_date: Optional[str] = None,
        refresh_if_missing: bool = False,
    ) -> List[Dict[str, Any]]:
        """从DB读取个股板块关系，必要时按需刷新单股"""
        db = SessionLocal()
        try:
            rows = self._query_stock_boards(db, ts_code, trade_date)
            if rows:
                return [self._row_to_dict(r) for r in rows]
        finally:
            db.close()

        if refresh_if_missing and trade_date:
            return self.refresh_stock_boards(ts_code, trade_date)
        return []

    def refresh_for_stocks(self, stocks: Iterable[Dict[str, Any]], trade_date: str) -> Dict[str, int]:
        """选股完成后批量刷新入选股票板块关系"""
        stats = {"stocks": 0, "boards": 0, "failed": 0}
        for stock in stocks:
            ts_code = stock.get("ts_code")
            if not ts_code:
                continue
            stats["stocks"] += 1
            try:
                boards = self.refresh_stock_boards(ts_code, trade_date)
                stats["boards"] += len(boards)
            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"刷新同花顺板块关系失败 {ts_code}: {e}")
        return stats

    def refresh_stock_boards(self, ts_code: str, trade_date: str) -> List[Dict[str, Any]]:
        """调用 ths_member 刷新单只股票在指定交易日的板块关系"""
        if self.pro is None:
            return []

        try:
            member_df = self.pro.ths_member(con_code=ts_code, fields="ts_code,con_code,con_name,is_new")
        except Exception as e:
            logger.warning(f"获取个股同花顺板块失败 {ts_code}: {e}")
            return []

        if member_df is None or member_df.empty:
            logger.debug(f"同花顺板块关系为空: {ts_code}")
            return []

        hot_map = self._get_hot_board_map(trade_date)
        boards: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        db = SessionLocal()
        try:
            for _, row in member_df.iterrows():
                board_code = str(row.get("ts_code", "") or "").strip()
                if not board_code or board_code in seen:
                    continue
                if not self._is_relevant_board_code(board_code):
                    continue
                seen.add(board_code)

                meta = self._resolve_board_meta(db, board_code, hot_map)
                if not meta:
                    continue

                board = {
                    "ts_code": meta["board_code"],
                    "name": meta["board_name"],
                    "type": meta.get("board_type", ""),
                    "is_new": str(row.get("is_new", "") or ""),
                    "source": "stock_ths_board_member",
                }
                self._upsert_member(db, ts_code, trade_date, board, "ths_member")
                boards.append(board)
            self._deactivate_missing_members(db, ts_code, trade_date, seen)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return boards

    def _query_stock_boards(self, db, ts_code: str, trade_date: Optional[str]):
        query = db.query(StockThsBoardMember).filter(
            StockThsBoardMember.ts_code == ts_code,
            StockThsBoardMember.is_active.is_(True),
        )
        if trade_date:
            query = query.filter(StockThsBoardMember.trade_date == trade_date)
        rows = query.order_by(StockThsBoardMember.trade_date.desc(), StockThsBoardMember.id.asc()).all()
        return [row for row in rows if self._is_relevant_board_code(row.board_code)]

    @staticmethod
    def _row_to_dict(row: StockThsBoardMember) -> Dict[str, Any]:
        return {
            "ts_code": row.board_code,
            "name": row.board_name,
            "type": row.board_type or "",
            "source": "stock_ths_board_member",
        }

    def _get_hot_board_map(self, trade_date: str) -> Dict[str, Dict[str, Any]]:
        if trade_date in self._hot_board_cache:
            return self._hot_board_cache[trade_date]

        result: Dict[str, Dict[str, Any]] = {}
        try:
            df = self.pro.limit_cpt_list(trade_date=trade_date)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get("ts_code", "") or "")
                    if code:
                        result[code] = {
                            "board_code": code,
                            "board_name": str(row.get("name", "") or ""),
                            "board_type": str(row.get("type", "") or ""),
                            "source": "limit_cpt_list",
                        }
        except Exception as e:
            logger.warning(f"获取热点板块名称映射失败: {e}")

        self._hot_board_cache[trade_date] = result
        return result

    def _resolve_board_meta(
        self,
        db,
        board_code: str,
        hot_map: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        existing = db.query(ThsBoardIndex).filter(
            ThsBoardIndex.board_code == board_code,
            ThsBoardIndex.is_active.is_(True),
        ).first()
        if existing:
            return {
                "board_code": existing.board_code,
                "board_name": existing.board_name,
                "board_type": existing.board_type or "",
                "source": "ths_board_index",
            }

        meta = hot_map.get(board_code)
        if not meta:
            meta = self._fetch_board_meta(board_code)
        if not meta or not meta.get("board_name"):
            return None

        self._upsert_board_index(db, meta)
        return meta

    @staticmethod
    def _is_relevant_board_code(board_code: str) -> bool:
        return str(board_code or "").startswith(BOARD_CODE_PREFIXES)

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:]+", "", str(text or ""))

    @staticmethod
    def _split_terms(text: str) -> List[str]:
        terms = re.split(r"[+＋,，/、;；|｜\s]+", str(text or ""))
        cleaned = []
        for term in terms:
            term = term.strip()
            if len(term) >= 2:
                cleaned.append(term)
        return cleaned

    @staticmethod
    def _board_name_match_score(clean_term: str, clean_name: str, display_name: str) -> tuple[int, str]:
        if not clean_term or not clean_name:
            return 0, ""
        if clean_term == clean_name:
            return 120, f"精确归一到{display_name}"
        if len(clean_name) >= 3 and clean_name in clean_term:
            return 95, f"包含标准板块{display_name}"
        if len(clean_term) >= 3 and clean_term in clean_name:
            return 82, f"模糊归一到{display_name}"
        if len(clean_term) >= 4 and len(clean_name) >= 4:
            ratio = SequenceMatcher(None, clean_term, clean_name).ratio()
            if ratio >= 0.58:
                return int(70 * ratio), f"相似归一到{display_name}"
        return 0, ""

    def _fetch_board_meta(self, board_code: str) -> Optional[Dict[str, Any]]:
        try:
            df = self.pro.ths_index(ts_code=board_code)
            if df is None or df.empty:
                return None
            row = df.iloc[0]
            board_type = str(row.get("type", "") or "")
            if board_type and board_type not in VALID_BOARD_TYPES:
                return None
            return {
                "board_code": str(row.get("ts_code", "") or board_code),
                "board_name": str(row.get("name", "") or ""),
                "board_type": board_type,
                "source": "ths_index_by_code",
                "raw_json": json.dumps(row.to_dict(), ensure_ascii=False, default=str),
            }
        except Exception as e:
            logger.debug(f"按需解析板块名称失败 {board_code}: {e}")
            return None

    @staticmethod
    def _upsert_board_index(db, meta: Dict[str, Any]) -> None:
        code = meta.get("board_code")
        if not code:
            return
        row = db.query(ThsBoardIndex).filter(ThsBoardIndex.board_code == code).first()
        if row:
            row.board_name = meta.get("board_name") or row.board_name
            row.board_type = meta.get("board_type") or row.board_type
            row.source = meta.get("source") or row.source
            row.raw_json = meta.get("raw_json") or row.raw_json
            row.is_active = True
        else:
            db.add(ThsBoardIndex(
                board_code=code,
                board_name=meta.get("board_name", ""),
                board_type=meta.get("board_type", ""),
                source=meta.get("source", "ths_index"),
                raw_json=meta.get("raw_json"),
                is_active=True,
            ))

    @staticmethod
    def _upsert_member(db, ts_code: str, trade_date: str, board: Dict[str, Any], matched_from: str) -> None:
        row = db.query(StockThsBoardMember).filter(
            StockThsBoardMember.ts_code == ts_code,
            StockThsBoardMember.trade_date == trade_date,
            StockThsBoardMember.board_code == board["ts_code"],
        ).first()
        if row:
            row.board_name = board.get("name") or row.board_name
            row.board_type = board.get("type") or row.board_type
            row.matched_from = matched_from
            row.is_active = True
        else:
            db.add(StockThsBoardMember(
                ts_code=ts_code,
                trade_date=trade_date,
                board_code=board["ts_code"],
                board_name=board.get("name", ""),
                board_type=board.get("type", ""),
                matched_from=matched_from,
                is_active=True,
            ))

    @staticmethod
    def _deactivate_missing_members(db, ts_code: str, trade_date: str, active_codes: Set[str]) -> None:
        rows = db.query(StockThsBoardMember).filter(
            StockThsBoardMember.ts_code == ts_code,
            StockThsBoardMember.trade_date == trade_date,
        ).all()
        for row in rows:
            if row.board_code not in active_codes or not ThsBoardService._is_relevant_board_code(row.board_code):
                row.is_active = False


def refresh_stock_ths_boards(stocks: Iterable[Dict[str, Any]], trade_date: str) -> Dict[str, int]:
    return ThsBoardService().refresh_for_stocks(stocks, trade_date)
