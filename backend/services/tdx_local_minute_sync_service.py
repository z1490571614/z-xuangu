"""
通达信本地分钟线入库服务。

读取 vipdoc/{sh,sz}/{fzline,minline} 下的 .lc1/.lc5 文件，写入 stock_minute_bar。
"""
import logging
import os
import struct
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import SessionLocal
from backend.models.local_market_data import StockMinuteBar
from backend.services.tdx_local_selector import is_common_a_share_ts_code

logger = logging.getLogger(__name__)

LC_RECORD_SIZE = 32


class TdxLocalMinuteSyncService:
    """同步通达信本地 .lc1/.lc5 分钟线到数据库。"""

    def __init__(
        self,
        tdx_vipdoc_path: Optional[str] = None,
        session_factory=SessionLocal,
    ):
        self.tdx_vipdoc_path = tdx_vipdoc_path or os.getenv("TDX_VIPDOC_PATH", r"G:\new_tdx\vipdoc")
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal

    def read_minute_rows(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        interval: int = 1,
    ) -> List[Dict[str, Any]]:
        """读取指定股票和日期区间的本地分钟线。"""
        path = self._ts_code_to_lc_path(ts_code, interval)
        if not path or not os.path.exists(path):
            return []
        source = f"tdx_lc{interval}"
        rows: List[Dict[str, Any]] = []
        for item in self._read_lc_file(path):
            trade_date = item["trade_date"]
            if trade_date < start_date or trade_date > end_date:
                continue
            rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "trade_time": item["trade_time"],
                    "bar_time": item["bar_time"],
                    "interval": interval,
                    "open": item["open"],
                    "high": item["high"],
                    "low": item["low"],
                    "close": item["close"],
                    "vol": item["vol"],
                    "amount": item["amount"],
                    "source": source,
                }
            )
        return rows

    def sync_range(
        self,
        start_date: str,
        end_date: str,
        ts_codes: Optional[Iterable[str]] = None,
        interval: int = 1,
        commit_every: int = 5000,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """同步指定日期区间的本地通达信分钟线。"""
        db = self.session_factory()
        rows_synced = 0
        rows_skipped_existing = 0
        stocks_scanned = 0
        stocks_with_rows = 0
        batch: List[Dict[str, Any]] = []
        try:
            targets = list(ts_codes) if ts_codes is not None else self._list_local_ts_codes(interval)
            for ts_code in targets:
                stocks_scanned += 1
                rows = self.read_minute_rows(ts_code, start_date, end_date, interval=interval)
                if not rows:
                    continue
                if skip_existing:
                    existing_bar_times = self._existing_bar_times(db, ts_code, start_date, end_date, interval)
                    if existing_bar_times:
                        before_count = len(rows)
                        rows = [row for row in rows if row["bar_time"] not in existing_bar_times]
                        rows_skipped_existing += before_count - len(rows)
                        if not rows:
                            continue
                stocks_with_rows += 1
                for row in rows:
                    batch.append(row)
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
                "interval": interval,
                "stocks_scanned": stocks_scanned,
                "stocks_with_rows": stocks_with_rows,
                "rows_synced": rows_synced,
                "rows_skipped_existing": rows_skipped_existing,
            }
        except Exception:
            db.rollback()
            logger.exception("同步通达信本地分钟线失败: %s~%s interval=%s", start_date, end_date, interval)
            return {
                "start_date": start_date,
                "end_date": end_date,
                "interval": interval,
                "stocks_scanned": stocks_scanned,
                "stocks_with_rows": stocks_with_rows,
                "rows_synced": 0,
                "rows_skipped_existing": rows_skipped_existing,
            }
        finally:
            if self._owns_session:
                db.close()

    @staticmethod
    def _existing_bar_times(db, ts_code: str, start_date: str, end_date: str, interval: int) -> set[str]:
        rows = (
            db.query(StockMinuteBar.bar_time)
            .filter(
                StockMinuteBar.ts_code == ts_code,
                StockMinuteBar.trade_date >= start_date,
                StockMinuteBar.trade_date <= end_date,
                StockMinuteBar.interval == interval,
            )
            .all()
        )
        return {row[0] for row in rows if row[0]}

    @classmethod
    def _flush_batch(cls, db, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        stmt = sqlite_insert(StockMinuteBar).values(rows)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["ts_code", "bar_time", "interval"],
                set_={
                    "trade_date": stmt.excluded.trade_date,
                    "trade_time": stmt.excluded.trade_time,
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "vol": stmt.excluded.vol,
                    "amount": stmt.excluded.amount,
                    "source": stmt.excluded.source,
                },
            )
        )
        db.commit()

    def _ts_code_to_lc_path(self, ts_code: str, interval: int) -> Optional[str]:
        if "." not in ts_code:
            return None
        code, suffix = ts_code.split(".", 1)
        market = suffix.lower()
        if market not in {"sh", "sz"}:
            return None
        filename = f"{market}{code}.lc{interval}"
        folders = ["fzline", "minline"] if interval == 1 else ["minline", "fzline"]
        for folder in folders:
            path = os.path.join(self.tdx_vipdoc_path, market, folder, filename)
            if os.path.exists(path):
                return path
        return os.path.join(self.tdx_vipdoc_path, market, folders[0], filename)

    def _list_local_ts_codes(self, interval: int) -> List[str]:
        codes: List[str] = []
        for market, suffix in [("sh", "SH"), ("sz", "SZ")]:
            for folder in ["fzline", "minline"]:
                root = os.path.join(self.tdx_vipdoc_path, market, folder)
                if not os.path.isdir(root):
                    continue
                for filename in os.listdir(root):
                    prefix = f"{market}"
                    ext = f".lc{interval}"
                    if not filename.startswith(prefix) or not filename.endswith(ext):
                        continue
                    code = filename[len(prefix) : -len(ext)]
                    ts_code = f"{code}.{suffix}"
                    if is_common_a_share_ts_code(ts_code):
                        codes.append(ts_code)
        return sorted(set(codes))

    @staticmethod
    def _read_lc_file(path: str) -> List[Dict[str, Any]]:
        with open(path, "rb") as f:
            data = f.read()
        rows: List[Dict[str, Any]] = []
        for offset in range(0, len(data) - LC_RECORD_SIZE + 1, LC_RECORD_SIZE):
            date_value, minute_value, open_, high, low, close, amount, vol, _ = struct.unpack_from(
                "<HHfffffII", data, offset
            )
            decoded = _decode_lc_datetime(date_value, minute_value)
            if decoded is None:
                continue
            trade_date, trade_time, bar_time = decoded
            rows.append(
                {
                    "trade_date": trade_date,
                    "trade_time": trade_time,
                    "bar_time": bar_time,
                    "open": round(float(open_), 4),
                    "high": round(float(high), 4),
                    "low": round(float(low), 4),
                    "close": round(float(close), 4),
                    "amount": round(float(amount), 4),
                    "vol": float(vol),
                }
            )
        return rows


def _decode_lc_datetime(date_value: int, minute_value: int) -> Optional[tuple[str, str, str]]:
    year = int(date_value / 2048) + 2004
    remainder = int(date_value % 2048)
    month = int(remainder / 100)
    day = int(remainder % 100)
    hour = int(minute_value / 60)
    minute = int(minute_value % 60)
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    trade_date = f"{year:04d}{month:02d}{day:02d}"
    trade_time = f"{hour:02d}:{minute:02d}"
    bar_time = f"{year:04d}-{month:02d}-{day:02d} {trade_time}:00"
    return trade_date, trade_time, bar_time
