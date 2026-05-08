"""东财板块动态别名服务。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from backend.database import SessionLocal
from backend.models.board import DcBoardAlias, DcBoardAliasObservation, DcBoardAliasSyncState
from backend.utils.tushare_client import get_tushare_pro
from scripts.generate_dc_board_aliases import (
    AUTO_SCORE_THRESHOLD,
    REVIEW_SCORE_THRESHOLD,
    fetch_dc_boards,
    score_tag_board_match,
    split_lu_desc_tags,
)

logger = logging.getLogger(__name__)

ACTIVE_REVIEW_STATUSES = {"auto_approved", "reviewed", "manual"}


class DcBoardAliasService:
    """同步和读取东财板块动态别名。"""

    def __init__(self, pro: Any = None):
        self._pro = pro

    @property
    def pro(self):
        if self._pro is None:
            self._pro = get_tushare_pro()
        return self._pro

    @staticmethod
    def clean_alias(text: str) -> str:
        return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:._-]+", "", str(text or "")).upper()

    def get_active_aliases(self) -> Dict[str, List[str]]:
        """读取运行期可参与线上匹配的别名。"""
        db = SessionLocal()
        try:
            rows = db.query(DcBoardAlias).filter(
                DcBoardAlias.is_active.is_(True),
                DcBoardAlias.review_status.in_(ACTIVE_REVIEW_STATUSES),
            ).order_by(DcBoardAlias.board_name.asc(), DcBoardAlias.hit_count.desc()).all()
            result: Dict[str, List[str]] = {}
            for row in rows:
                aliases = result.setdefault(row.board_name, [])
                if row.alias and row.alias not in aliases:
                    aliases.append(row.alias)
            return result
        finally:
            db.close()

    def sync_trade_date(self, trade_date: str, finalize: bool = False) -> Dict[str, int]:
        """同步指定交易日涨停标签别名。

        当天可多次调用；通过 observation 唯一键只新增新出现的股票/标签/板块组合。
        """
        if self._is_finalized(trade_date):
            return {"source_rows": 0, "inserted_observations": 0, "alias_count": 0, "skipped": 1}

        boards = fetch_dc_boards(self.pro, trade_date)
        if not boards:
            self._upsert_sync_state(trade_date, "failed", 0, 0, 0, "东财板块为空", finalize=False)
            return {"source_rows": 0, "inserted_observations": 0, "alias_count": 0}

        try:
            df = self.pro.limit_list_ths(trade_date=trade_date, limit_type="涨停池")
        except Exception as e:
            self._upsert_sync_state(trade_date, "failed", 0, 0, 0, str(e), finalize=False)
            logger.warning(f"同步东财动态别名失败 {trade_date}: {e}")
            return {"source_rows": 0, "inserted_observations": 0, "alias_count": 0}

        if df is None or df.empty:
            self._upsert_sync_state(trade_date, "empty", 0, 0, 0, "", finalize=finalize)
            return {"source_rows": 0, "inserted_observations": 0, "alias_count": 0}

        candidates = self._build_observation_candidates(trade_date, df.to_dict("records"), boards)
        inserted = self._insert_observations(candidates)
        self._refresh_alias_summaries({(c["board_code"], c["alias_clean"]) for c in candidates})
        self._upsert_sync_state(
            trade_date,
            "finalized" if finalize else "synced",
            len(df),
            len({str(row.get("ts_code", "") or "") for row in df.to_dict("records") if row.get("ts_code")}),
            inserted,
            "",
            finalize=finalize,
        )

        try:
            from backend.services.dc_board_service import DcBoardService
            DcBoardService.clear_catalog_cache()
        except Exception:
            pass

        return {
            "source_rows": len(df),
            "inserted_observations": inserted,
            "alias_count": len(candidates),
        }

    def _is_finalized(self, trade_date: str) -> bool:
        db = SessionLocal()
        try:
            row = db.query(DcBoardAliasSyncState).filter(
                DcBoardAliasSyncState.trade_date == trade_date,
                DcBoardAliasSyncState.finalized_at.isnot(None),
            ).first()
            return row is not None
        finally:
            db.close()

    def _build_observation_candidates(
        self,
        trade_date: str,
        rows: Iterable[Dict[str, Any]],
        boards: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            ts_code = str(row.get("ts_code", "") or "")
            if not ts_code:
                continue
            for tag in split_lu_desc_tags(str(row.get("lu_desc", "") or "")):
                best = self._best_match(tag, boards)
                if not best:
                    continue
                board, score, reason = best
                alias_clean = self.clean_alias(tag)
                key = (trade_date, ts_code, board["ts_code"], alias_clean)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "board_code": board["ts_code"],
                    "board_name": board["name"],
                    "board_type": board.get("type", ""),
                    "alias": tag,
                    "alias_clean": alias_clean,
                    "confidence_score": score,
                    "match_reason": reason,
                })
        return candidates

    def _best_match(self, tag: str, boards: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], int, str] | None:
        best: Tuple[Dict[str, Any], int, str] | None = None
        for board in boards:
            score, reason = score_tag_board_match(tag, board)
            if score < REVIEW_SCORE_THRESHOLD:
                continue
            if best is None or score > best[1]:
                best = (board, score, reason)
        return best

    def _insert_observations(self, candidates: List[Dict[str, Any]]) -> int:
        inserted = 0
        db = SessionLocal()
        try:
            for item in candidates:
                exists = db.query(DcBoardAliasObservation.id).filter(
                    DcBoardAliasObservation.trade_date == item["trade_date"],
                    DcBoardAliasObservation.ts_code == item["ts_code"],
                    DcBoardAliasObservation.board_code == item["board_code"],
                    DcBoardAliasObservation.alias_clean == item["alias_clean"],
                ).first()
                if exists:
                    continue
                db.add(DcBoardAliasObservation(**item))
                inserted += 1
            db.commit()
            return inserted
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _refresh_alias_summaries(self, keys: Iterable[Tuple[str, str]]) -> None:
        db = SessionLocal()
        try:
            for board_code, alias_clean in keys:
                rows = db.query(DcBoardAliasObservation).filter(
                    DcBoardAliasObservation.board_code == board_code,
                    DcBoardAliasObservation.alias_clean == alias_clean,
                ).all()
                if not rows:
                    continue
                first = rows[0]
                trade_dates = [row.trade_date for row in rows if row.trade_date]
                stocks = sorted({row.ts_code for row in rows if row.ts_code})
                best_score = max(float(row.confidence_score or 0) for row in rows)
                best_reason = max(rows, key=lambda row: float(row.confidence_score or 0)).match_reason
                alias = db.query(DcBoardAlias).filter(
                    DcBoardAlias.board_code == board_code,
                    DcBoardAlias.alias_clean == alias_clean,
                ).first()
                if not alias:
                    alias = DcBoardAlias(
                        board_code=first.board_code,
                        alias=first.alias,
                        alias_clean=first.alias_clean,
                        source="generated",
                    )
                    db.add(alias)
                alias.board_name = first.board_name
                alias.board_type = first.board_type
                alias.confidence_score = best_score
                alias.match_reason = best_reason
                alias.hit_count = len(rows)
                alias.stock_count = len(stocks)
                alias.first_seen_date = min(trade_dates) if trade_dates else None
                alias.last_seen_date = max(trade_dates) if trade_dates else None
                alias.sample_stocks_json = json.dumps(stocks[:12], ensure_ascii=False)
                if alias.review_status not in {"manual", "reviewed", "rejected"}:
                    alias.review_status = "auto_approved" if best_score >= AUTO_SCORE_THRESHOLD else "pending_review"
                alias.is_active = alias.review_status != "rejected"
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _upsert_sync_state(
        self,
        trade_date: str,
        status: str,
        source_row_count: int,
        observed_stock_count: int,
        inserted_observation_count: int,
        error_message: str,
        finalize: bool,
    ) -> None:
        db = SessionLocal()
        try:
            row = db.query(DcBoardAliasSyncState).filter(
                DcBoardAliasSyncState.trade_date == trade_date,
            ).first()
            if not row:
                row = DcBoardAliasSyncState(trade_date=trade_date, source="limit_list_ths")
                db.add(row)
            row.status = status
            row.source_row_count = source_row_count
            row.observed_stock_count = observed_stock_count
            row.inserted_observation_count = inserted_observation_count
            row.error_message = error_message or None
            row.last_synced_at = datetime.now()
            if finalize:
                row.finalized_at = datetime.now()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
