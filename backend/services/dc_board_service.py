"""
东方财富板块服务。

负责把新闻主题、涨停标签、选股行业等文本统一归一到东财板块，
并为风险拆解和龙头题材提供同一套板块行情、资金、强度上下文。
"""
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.database import SessionLocal
from backend.models.board import (
    BoardDailySnapshot,
    BoardIndex,
    BoardStrengthSnapshot,
    StockBoardMember,
)
from backend.utils.tushare_client import get_tushare_pro

logger = logging.getLogger(__name__)

EASTMONEY_SOURCE = "eastmoney"
DC_BOARD_TYPES = ("概念板块", "行业板块", "地域板块")
LOW_PRIORITY_BOARD_TYPES = {"地域板块", "地域", "area", "AREA"}

BOARD_ALIASES: Dict[str, List[str]] = {
    "算力租赁": ["智算租赁", "智算租赁服务", "算力服务", "算力租赁服务"],
    "人工智能": ["AI", "AIGC", "AI应用"],
    "通信设备": ["通信", "通讯设备", "通信服务"],
}


class DcBoardService:
    """维护东财板块词典、个股成分关系与板块快照。"""

    _shared_catalog_cache: Optional[List[Dict[str, Any]]] = None

    def __init__(self):
        self._pro = None
        self._moneyflow_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    @classmethod
    def clear_catalog_cache(cls) -> None:
        cls._shared_catalog_cache = None

    def sync_board_index_catalog(self, trade_date: str) -> Dict[str, int]:
        """同步东财板块词典。

        该方法由启动或显式任务调用；运行期归一只读本地库。
        """
        stats = {"fetched": 0, "saved": 0, "failed": 0}
        db = SessionLocal()
        try:
            for board_type in DC_BOARD_TYPES:
                try:
                    df = self.pro.dc_index(trade_date=trade_date, idx_type=board_type)
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning(f"同步东财{board_type}失败: {e}")
                    continue
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    code = self._first_present(row, "ts_code", "board_code", "index_code")
                    name = self._first_present(row, "name", "board_name", "index_name")
                    if not code or not name:
                        continue
                    row_type = self._first_present(row, "idx_type", "board_type", "type", default=board_type)
                    stats["fetched"] += 1
                    self._upsert_board_index(db, {
                        "board_code": code,
                        "board_name": name,
                        "board_type": row_type or board_type,
                        "source": EASTMONEY_SOURCE,
                        "trade_date": trade_date,
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

    def refresh_stock_boards(self, stocks_or_ts_code: Iterable[Dict[str, Any]] | str, trade_date: str) -> Dict[str, int] | List[Dict[str, Any]]:
        """预热入选股票的东财板块关系。

        兼容单股字符串和选股结果列表，便于风险拆解按需刷新与选股后批量预热共用。
        """
        if isinstance(stocks_or_ts_code, str):
            return self._refresh_one_stock_boards(stocks_or_ts_code, trade_date)

        stats = {"stocks": 0, "boards": 0, "failed": 0}
        for stock in stocks_or_ts_code:
            ts_code = stock.get("ts_code")
            if not ts_code:
                continue
            stats["stocks"] += 1
            try:
                boards = self._refresh_one_stock_boards(ts_code, trade_date)
                stats["boards"] += len(boards)
            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"刷新东财板块关系失败 {ts_code}: {e}")
        return stats

    def get_stock_boards(
        self,
        ts_code: str,
        trade_date: Optional[str] = None,
        refresh_if_missing: bool = False,
    ) -> List[Dict[str, Any]]:
        """读取个股东财板块关系，缺失时按需刷新单股。"""
        db = SessionLocal()
        try:
            rows = self._query_stock_boards(db, ts_code, trade_date)
            if rows:
                return [self._member_row_to_dict(row) for row in rows]
        finally:
            db.close()

        if refresh_if_missing and trade_date:
            return self._refresh_one_stock_boards(ts_code, trade_date)
        return []

    def normalize_board_terms(self, text: str, source: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """将主题文本归一到东财标准板块，仅使用本地词典。"""
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
                score, reason = self._board_name_match_score(clean_term, board)
                if score <= 0:
                    continue
                if self._is_low_priority(board):
                    score -= 20
                existing = matches.get(board["ts_code"])
                if existing and existing["match_score"] >= score:
                    continue
                matches[board["ts_code"]] = {
                    "ts_code": board["ts_code"],
                    "name": board["name"],
                    "type": board.get("type", ""),
                    "source": EASTMONEY_SOURCE,
                    "match_score": score,
                    "matched_from": source or "text",
                    "match_reasons": [f"{source or '文本'}“{term}”{reason}"],
                }

        return sorted(
            matches.values(),
            key=lambda item: (item.get("match_score", 0), -self._type_sort_penalty(item.get("type", ""))),
            reverse=True,
        )[:top_n]

    def get_board_daily(self, board_code: str, trade_date: str) -> Dict[str, Any]:
        """获取东财板块行情，优先读本地快照。"""
        db = SessionLocal()
        try:
            row = db.query(BoardDailySnapshot).filter(
                BoardDailySnapshot.board_code == board_code,
                BoardDailySnapshot.trade_date == trade_date,
            ).first()
            if row:
                return self._daily_row_to_dict(row)
        finally:
            db.close()

        try:
            df = self.pro.dc_daily(ts_code=board_code, trade_date=trade_date)
        except Exception as e:
            logger.warning(f"获取东财板块行情失败 {board_code}: {e}")
            return {}
        if df is None or df.empty:
            return {}

        row = df.iloc[0]
        data = {
            "board_code": board_code,
            "trade_date": trade_date,
            "pct_chg": self._to_float(self._first_present(row, "pct_change", "pct_chg")),
            "amount": self._to_float(self._first_present(row, "amount", "成交额")),
            "turnover_rate": self._to_float(self._first_present(row, "turnover_rate", "换手率")),
            "rank": self._to_int(self._first_present(row, "rank", "排名")),
            "raw_json": json.dumps(row.to_dict(), ensure_ascii=False, default=str),
        }
        self._upsert_daily_snapshot(data)
        return data

    def get_board_moneyflow(self, board_code: str, trade_date: str) -> Dict[str, Any]:
        """获取东财板块资金流，进程内缓存，缺失时降级为空。"""
        cache_key = f"{board_code}_{trade_date}"
        if cache_key in self._moneyflow_cache:
            return self._moneyflow_cache[cache_key]

        try:
            df = self.pro.moneyflow_ind_dc(ts_code=board_code, trade_date=trade_date)
        except Exception as e:
            logger.warning(f"获取东财板块资金流失败 {board_code}: {e}")
            return {}
        if df is None or df.empty:
            return {}

        row = df.iloc[0]
        net_amount = self._to_float(self._first_present(row, "net_amount", "main_net_amount", "主力净流入"))
        result = {
            "board_code": board_code,
            "trade_date": trade_date,
            "net_amount": net_amount,
            "net_amount_yi": round(net_amount / 100000000, 2),
            "rank": self._to_int(self._first_present(row, "rank", "排名")),
            "raw_json": row.to_dict(),
        }
        self._moneyflow_cache[cache_key] = result
        return result

    def get_board_strength(self, board_code: str, trade_date: str) -> Dict[str, Any]:
        """读取或计算板块强度快照。"""
        db = SessionLocal()
        try:
            row = db.query(BoardStrengthSnapshot).filter(
                BoardStrengthSnapshot.board_code == board_code,
                BoardStrengthSnapshot.trade_date == trade_date,
            ).first()
            if row:
                return self._strength_row_to_dict(row)
        finally:
            db.close()

        daily = self.get_board_daily(board_code, trade_date)
        money = self.get_board_moneyflow(board_code, trade_date)
        member_count = len(self._get_board_members(board_code, trade_date))
        limit_up_count = self._get_limit_up_count(board_code, trade_date)
        board_pct = daily.get("pct_chg", 0) or 0
        net_amount = money.get("net_amount", 0) or 0
        strength_score = max(0, min(100, 50 + board_pct * 8 + limit_up_count * 4 + money.get("net_amount_yi", 0) * 1.5))
        snapshot = {
            "board_code": board_code,
            "trade_date": trade_date,
            "limit_up_count": limit_up_count,
            "limit_up_member_count": limit_up_count,
            "member_count": member_count,
            "avg_member_pct": 0,
            "top_member_pct": 0,
            "board_pct_chg": board_pct,
            "money_net_amount": net_amount,
            "strength_score": round(strength_score, 1),
            "raw_json": json.dumps({"daily": daily, "moneyflow": money}, ensure_ascii=False, default=str),
        }
        self._upsert_strength_snapshot(snapshot)
        return snapshot

    def get_hot_boards(self, trade_date: str, limit: int = 50) -> List[Dict[str, Any]]:
        """以东财强度快照作为龙头题材热板块来源。"""
        db = SessionLocal()
        try:
            rows = db.query(BoardStrengthSnapshot).filter(
                BoardStrengthSnapshot.trade_date == trade_date,
            ).order_by(BoardStrengthSnapshot.strength_score.desc()).limit(limit).all()
            return [self._strength_row_to_hot_board(row, idx + 1) for idx, row in enumerate(rows)]
        finally:
            db.close()

    def get_board_index_catalog(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        if not force_reload and self.__class__._shared_catalog_cache is not None:
            return self.__class__._shared_catalog_cache

        db = SessionLocal()
        try:
            rows = db.query(BoardIndex).filter(
                BoardIndex.source == EASTMONEY_SOURCE,
                BoardIndex.is_active.is_(True),
            ).order_by(BoardIndex.board_type.asc(), BoardIndex.board_name.asc()).all()
            catalog = [
                {
                    "ts_code": row.board_code,
                    "name": row.board_name,
                    "type": row.board_type or "",
                    "source": row.source or EASTMONEY_SOURCE,
                    "clean_name": self._clean_text(row.board_name),
                    "aliases": [self._clean_text(a) for a in BOARD_ALIASES.get(row.board_name, [])],
                }
                for row in rows
                if row.board_code and row.board_name
            ]
            self.__class__._shared_catalog_cache = catalog
            return catalog
        finally:
            db.close()

    def _refresh_one_stock_boards(self, ts_code: str, trade_date: str) -> List[Dict[str, Any]]:
        try:
            df = self.pro.dc_member(con_code=ts_code, trade_date=trade_date)
        except Exception as e:
            logger.warning(f"获取个股东财板块失败 {ts_code}: {e}")
            return []
        if df is None or df.empty:
            return []

        boards: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        db = SessionLocal()
        try:
            for _, row in df.iterrows():
                board_code = self._first_present(row, "ts_code", "board_code", "index_code")
                if not board_code or board_code in seen:
                    continue
                seen.add(board_code)
                meta = self._resolve_board_meta(db, board_code, trade_date, row)
                if not meta:
                    continue
                board = {
                    "ts_code": meta["board_code"],
                    "name": meta["board_name"],
                    "type": meta.get("board_type", ""),
                    "source": EASTMONEY_SOURCE,
                    "matched_from": "dc_member",
                }
                self._upsert_member(db, ts_code, trade_date, board, "dc_member")
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
        query = db.query(StockBoardMember).filter(
            StockBoardMember.ts_code == ts_code,
            StockBoardMember.source == EASTMONEY_SOURCE,
            StockBoardMember.is_active.is_(True),
        )
        if trade_date:
            query = query.filter(StockBoardMember.trade_date == trade_date)
        return query.order_by(StockBoardMember.trade_date.desc(), StockBoardMember.id.asc()).all()

    def _resolve_board_meta(self, db, board_code: str, trade_date: str, member_row: Any) -> Optional[Dict[str, Any]]:
        existing = db.query(BoardIndex).filter(
            BoardIndex.board_code == board_code,
            BoardIndex.source == EASTMONEY_SOURCE,
            BoardIndex.is_active.is_(True),
        ).first()
        if existing:
            return {
                "board_code": existing.board_code,
                "board_name": existing.board_name,
                "board_type": existing.board_type or "",
            }

        name = self._first_present(member_row, "board_name", "index_name", "name")
        board_type = self._first_present(member_row, "idx_type", "board_type", "type", default="")
        if not name:
            return None
        meta = {
            "board_code": board_code,
            "board_name": name,
            "board_type": board_type,
            "source": EASTMONEY_SOURCE,
            "trade_date": trade_date,
            "raw_json": json.dumps(member_row.to_dict(), ensure_ascii=False, default=str),
        }
        self._upsert_board_index(db, meta)
        return meta

    def _get_board_members(self, board_code: str, trade_date: str) -> List[str]:
        db = SessionLocal()
        try:
            return [
                row.ts_code for row in db.query(StockBoardMember).filter(
                    StockBoardMember.board_code == board_code,
                    StockBoardMember.trade_date == trade_date,
                    StockBoardMember.is_active.is_(True),
                ).all()
            ]
        finally:
            db.close()

    def _get_limit_up_count(self, board_code: str, trade_date: str) -> int:
        members = set(self._get_board_members(board_code, trade_date))
        if not members:
            return 0
        try:
            df = self.pro.limit_list_d(trade_date=trade_date)
        except Exception:
            return 0
        if df is None or df.empty:
            return 0
        code_col = "ts_code" if "ts_code" in df.columns else "code"
        return int(sum(1 for code in df[code_col].astype(str).tolist() if code in members))

    @staticmethod
    def _member_row_to_dict(row: StockBoardMember) -> Dict[str, Any]:
        return {
            "ts_code": row.board_code,
            "name": row.board_name,
            "type": row.board_type or "",
            "source": row.source or EASTMONEY_SOURCE,
            "matched_from": row.matched_from or "dc_member",
        }

    @staticmethod
    def _daily_row_to_dict(row: BoardDailySnapshot) -> Dict[str, Any]:
        return {
            "board_code": row.board_code,
            "trade_date": row.trade_date,
            "pct_chg": row.pct_chg or 0,
            "amount": row.amount or 0,
            "turnover_rate": row.turnover_rate or 0,
            "rank": row.rank,
        }

    @staticmethod
    def _strength_row_to_dict(row: BoardStrengthSnapshot) -> Dict[str, Any]:
        return {
            "board_code": row.board_code,
            "trade_date": row.trade_date,
            "limit_up_count": row.limit_up_count or 0,
            "limit_up_member_count": row.limit_up_member_count or 0,
            "member_count": row.member_count or 0,
            "avg_member_pct": row.avg_member_pct or 0,
            "top_member_pct": row.top_member_pct or 0,
            "board_pct_chg": row.board_pct_chg or 0,
            "money_net_amount": row.money_net_amount or 0,
            "strength_score": row.strength_score or 0,
        }

    def _strength_row_to_hot_board(self, row: BoardStrengthSnapshot, rank: int) -> Dict[str, Any]:
        meta = self._get_board_meta_from_db(row.board_code)
        return {
            "rank": rank,
            "name": meta.get("board_name", row.board_code),
            "ts_code": row.board_code,
            "up_nums": row.limit_up_count or 0,
            "cons_nums": row.limit_up_member_count or 0,
            "up_stat": "",
            "days": 0,
            "pct_chg": row.board_pct_chg or 0,
            "strength_score": row.strength_score or 0,
            "matched_from": "dc_strength_snapshot",
        }

    def _get_board_meta_from_db(self, board_code: str) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.query(BoardIndex).filter(BoardIndex.board_code == board_code).first()
            if not row:
                return {}
            return {"board_name": row.board_name, "board_type": row.board_type or ""}
        finally:
            db.close()

    @staticmethod
    def _upsert_board_index(db, meta: Dict[str, Any]) -> None:
        code = meta.get("board_code")
        if not code:
            return
        row = db.query(BoardIndex).filter(BoardIndex.board_code == code).first()
        if row:
            row.board_name = meta.get("board_name") or row.board_name
            row.board_type = meta.get("board_type") or row.board_type
            row.source = meta.get("source") or row.source
            row.trade_date = meta.get("trade_date") or row.trade_date
            row.raw_json = meta.get("raw_json") or row.raw_json
            row.is_active = True
        else:
            db.add(BoardIndex(
                board_code=code,
                board_name=meta.get("board_name", ""),
                board_type=meta.get("board_type", ""),
                source=meta.get("source", EASTMONEY_SOURCE),
                trade_date=meta.get("trade_date"),
                raw_json=meta.get("raw_json"),
                is_active=True,
            ))

    @staticmethod
    def _upsert_member(db, ts_code: str, trade_date: str, board: Dict[str, Any], matched_from: str) -> None:
        row = db.query(StockBoardMember).filter(
            StockBoardMember.ts_code == ts_code,
            StockBoardMember.trade_date == trade_date,
            StockBoardMember.board_code == board["ts_code"],
        ).first()
        if row:
            row.board_name = board.get("name") or row.board_name
            row.board_type = board.get("type") or row.board_type
            row.source = EASTMONEY_SOURCE
            row.matched_from = matched_from
            row.is_active = True
        else:
            db.add(StockBoardMember(
                ts_code=ts_code,
                trade_date=trade_date,
                board_code=board["ts_code"],
                board_name=board.get("name", ""),
                board_type=board.get("type", ""),
                source=EASTMONEY_SOURCE,
                matched_from=matched_from,
                is_active=True,
            ))

    @staticmethod
    def _deactivate_missing_members(db, ts_code: str, trade_date: str, active_codes: Set[str]) -> None:
        rows = db.query(StockBoardMember).filter(
            StockBoardMember.ts_code == ts_code,
            StockBoardMember.trade_date == trade_date,
            StockBoardMember.source == EASTMONEY_SOURCE,
        ).all()
        for row in rows:
            if row.board_code not in active_codes:
                row.is_active = False

    @staticmethod
    def _upsert_daily_snapshot(data: Dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            row = db.query(BoardDailySnapshot).filter(
                BoardDailySnapshot.board_code == data["board_code"],
                BoardDailySnapshot.trade_date == data["trade_date"],
            ).first()
            if row:
                row.pct_chg = data.get("pct_chg", row.pct_chg)
                row.amount = data.get("amount", row.amount)
                row.turnover_rate = data.get("turnover_rate", row.turnover_rate)
                row.rank = data.get("rank", row.rank)
                row.raw_json = data.get("raw_json") or row.raw_json
            else:
                db.add(BoardDailySnapshot(**data))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _upsert_strength_snapshot(data: Dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            row = db.query(BoardStrengthSnapshot).filter(
                BoardStrengthSnapshot.board_code == data["board_code"],
                BoardStrengthSnapshot.trade_date == data["trade_date"],
            ).first()
            if row:
                for key, value in data.items():
                    setattr(row, key, value)
            else:
                db.add(BoardStrengthSnapshot(**data))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _first_present(row: Any, *fields: str, default: str = "") -> Any:
        for field in fields:
            try:
                value = row.get(field)
            except Exception:
                value = None
            if value is not None and str(value) != "nan" and str(value).strip() != "":
                return str(value).strip() if not isinstance(value, (int, float)) else value
        return default

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:]+", "", str(text or "")).upper()

    @staticmethod
    def _split_terms(text: str) -> List[str]:
        terms = re.split(r"[+＋,，/、;；|｜\s]+", str(text or ""))
        return [term.strip() for term in terms if len(term.strip()) >= 2]

    def _board_name_match_score(self, clean_term: str, board: Dict[str, Any]) -> tuple[int, str]:
        clean_name = board.get("clean_name", "")
        display_name = board.get("name", "")
        aliases = board.get("aliases", [])
        candidates = [(clean_name, display_name)] + [(alias, display_name) for alias in aliases]
        for clean_candidate, label in candidates:
            if not clean_term or not clean_candidate:
                continue
            if clean_term == clean_candidate:
                return 130, f"命中{label}"
            if len(clean_candidate) >= 3 and clean_candidate in clean_term:
                return 105, f"命中{label}"
            if len(clean_term) >= 3 and clean_term in clean_candidate:
                return 90, f"命中{label}"
            if len(clean_term) >= 4 and len(clean_candidate) >= 4:
                ratio = SequenceMatcher(None, clean_term, clean_candidate).ratio()
                if ratio >= 0.58:
                    return int(75 * ratio), f"相似命中{label}"
        return 0, ""

    @staticmethod
    def _is_low_priority(board: Dict[str, Any]) -> bool:
        return str(board.get("type", "")) in LOW_PRIORITY_BOARD_TYPES

    @staticmethod
    def _type_sort_penalty(board_type: str) -> int:
        if board_type in LOW_PRIORITY_BOARD_TYPES:
            return 20
        if "行业" in str(board_type):
            return 5
        return 0

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            if value in (None, ""):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None


def refresh_stock_dc_boards(stocks: Iterable[Dict[str, Any]], trade_date: str) -> Dict[str, int]:
    result = DcBoardService().refresh_stock_boards(stocks, trade_date)
    return result if isinstance(result, dict) else {"stocks": 1, "boards": len(result), "failed": 0}
