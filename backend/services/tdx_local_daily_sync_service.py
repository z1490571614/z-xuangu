"""
通达信本地日线入库服务。

将 vipdoc/{sh,sz}/lday/*.day 同步到 stock_daily_data，供回测和训练快速查询。
"""
import logging
from typing import Any, Dict, Iterable, Optional

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import SessionLocal
from backend.models.seal_rate import StockDailyData
from backend.services.tdx_local_selector import TdxLocalSelectorService, get_limit_ratio

logger = logging.getLogger(__name__)


class TdxLocalDailySyncService:
    """把通达信本地 .day 文件同步到 stock_daily_data。"""

    def __init__(
        self,
        tdx_vipdoc_path: Optional[str] = None,
        session_factory=SessionLocal,
        local_service: Optional[TdxLocalSelectorService] = None,
    ):
        self.local_service = local_service or TdxLocalSelectorService(tdx_vipdoc_path=tdx_vipdoc_path)
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal

    def sync_range(
        self,
        start_date: str,
        end_date: str,
        ts_codes: Optional[Iterable[str]] = None,
        commit_every: int = 5000,
    ) -> Dict[str, Any]:
        """同步指定日期区间的本地通达信日线。"""
        db = self.session_factory()
        rows_synced = 0
        stocks_scanned = 0
        stocks_with_rows = 0
        batch = []
        try:
            targets = list(ts_codes) if ts_codes is not None else self.local_service._list_local_ts_codes()
            for ts_code in targets:
                stocks_scanned += 1
                df = self.local_service.get_daily_data(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if df is None or df.empty:
                    continue
                stocks_with_rows += 1
                for row in df.to_dict("records"):
                    values = self._row_to_values(row)
                    if not values:
                        continue
                    batch.append(values)
                    rows_synced += 1
                    if commit_every > 0 and len(batch) >= commit_every:
                        self._flush_batch(db, batch)
                        batch.clear()
            if batch:
                self._flush_batch(db, batch)
            db.commit()
            return {
                "start_date": start_date,
                "end_date": end_date,
                "stocks_scanned": stocks_scanned,
                "stocks_with_rows": stocks_with_rows,
                "rows_synced": rows_synced,
            }
        except Exception:
            db.rollback()
            logger.exception(f"同步通达信本地日线失败: {start_date}~{end_date}")
            return {
                "start_date": start_date,
                "end_date": end_date,
                "stocks_scanned": stocks_scanned,
                "stocks_with_rows": stocks_with_rows,
                "rows_synced": 0,
            }
        finally:
            if self._owns_session:
                db.close()

    @classmethod
    def _flush_batch(cls, db, rows: list[Dict[str, Any]]) -> None:
        if not rows:
            return
        stmt = sqlite_insert(StockDailyData).values(rows)
        update_cols = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "pre_close": stmt.excluded.pre_close,
            "change": stmt.excluded.change,
            "pct_chg": stmt.excluded.pct_chg,
            "up_limit": stmt.excluded.up_limit,
            "down_limit": stmt.excluded.down_limit,
            "vol": stmt.excluded.vol,
            "amount": stmt.excluded.amount,
            "adj_factor": stmt.excluded.adj_factor,
            "is_adj": stmt.excluded.is_adj,
        }
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["ts_code", "trade_date"],
                set_=update_cols,
            )
        )
        db.commit()

    @staticmethod
    def _row_to_values(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ts_code = row.get("ts_code")
        trade_date = row.get("trade_date")
        if not ts_code or not trade_date:
            return None
        pre_close = _num(row.get("pre_close"))
        ratio = get_limit_ratio(str(ts_code).split(".")[0])
        return {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": _num(row.get("close")),
            "pre_close": pre_close,
            "change": _num(row.get("change")),
            "pct_chg": _num(row.get("pct_chg")),
            "vol": _num(row.get("vol")),
            "amount": _num(row.get("amount")),
            "up_limit": round(pre_close * (1 + ratio), 2) if pre_close else None,
            "down_limit": round(pre_close * (1 - ratio), 2) if pre_close else None,
            "adj_factor": None,
            "is_adj": 0,
        }


def _num(value):
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
