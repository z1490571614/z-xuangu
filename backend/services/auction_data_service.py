"""
历史开盘集合竞价数据同步服务。
"""
import logging
from bisect import bisect_left
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from backend.database import SessionLocal
from backend.models.auction_backtest import StockAuctionOpen
from backend.models.seal_rate import StockDailyData
from backend.services.data_collector import TushareDataCollector
from backend.services.daily_basic_fallback import get_daily_basic_with_previous_fallback
from backend.utils.trading_date import get_previous_trading_day

logger = logging.getLogger(__name__)


def _clean_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_auction_metrics(
    auction_vol: Any,
    previous_daily_vol: Any,
    float_share: Any,
    free_share: Any = None,
) -> Dict[str, Optional[float]]:
    """
    计算竞昨比和竞价换手率。

    Tushare daily.vol 单位为手，stk_auction.vol 按股处理。
    auction_ratio 保持生产侧百分数口径：8.19 表示 8.19%。
    daily_basic.float_share/free_share 单位为万股。MCP 条件使用开盘自由换手率，
    因此优先用 free_share，缺失时降级到 float_share。
    """
    auction_vol_f = _clean_number(auction_vol)
    previous_daily_vol_f = _clean_number(previous_daily_vol)
    float_share_f = _clean_number(float_share)
    free_share_f = _clean_number(free_share)

    auction_ratio = None
    if auction_vol_f is not None and previous_daily_vol_f and previous_daily_vol_f > 0:
        auction_ratio = round(auction_vol_f / previous_daily_vol_f, 2)

    auction_turnover_rate = None
    turnover_share_f = free_share_f if free_share_f and free_share_f > 0 else float_share_f
    if auction_vol_f is not None and turnover_share_f and turnover_share_f > 0:
        auction_turnover_rate = round(auction_vol_f / (turnover_share_f * 10000) * 100, 2)

    return {
        "auction_ratio": auction_ratio,
        "auction_turnover_rate": auction_turnover_rate,
    }


class AuctionDataService:
    """同步并读取历史开盘集合竞价特征。"""

    def __init__(self, collector: Optional[Any] = None, session_factory=SessionLocal):
        self.collector = collector or TushareDataCollector()
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal

    def sync_auction_open(self, trade_date: str) -> int:
        calendar = self._get_calendar_for_trade_date(trade_date)
        prev_date = get_previous_trading_day(trade_date, calendar)

        auction_df = self.collector.get_stk_auction_open(trade_date)
        if auction_df is None or auction_df.empty:
            logger.warning(f"{trade_date} 无开盘集合竞价数据")
            return 0

        prev_daily_df = self.collector.get_daily_data(trade_date=prev_date)
        daily_basic_df = get_daily_basic_with_previous_fallback(
            self.collector,
            trade_date,
            calendar=calendar,
            purpose="开盘竞价同步",
        )

        prev_volume_raw = self._map_by_code(prev_daily_df, "vol")
        prev_volume = prev_volume_raw
        float_share = self._map_by_code(daily_basic_df, "float_share")
        free_share = self._map_by_code(daily_basic_df, "free_share")

        db = self.session_factory()
        saved = 0
        try:
            for row in auction_df.to_dict("records"):
                ts_code = row.get("ts_code")
                if not ts_code:
                    continue
                metrics = calculate_auction_metrics(
                    row.get("vol"),
                    prev_volume.get(ts_code),
                    float_share.get(ts_code),
                    free_share.get(ts_code),
                )
                existing = db.query(StockAuctionOpen).filter(
                    StockAuctionOpen.trade_date == trade_date,
                    StockAuctionOpen.ts_code == ts_code,
                ).first()
                if existing is None:
                    existing = StockAuctionOpen(trade_date=trade_date, ts_code=ts_code)
                    db.add(existing)

                existing.price = _clean_number(row.get("price"))
                existing.vol = _clean_number(row.get("vol"))
                existing.amount = _clean_number(row.get("amount"))
                existing.pre_close = _clean_number(row.get("pre_close"))
                existing.auction_ratio = metrics["auction_ratio"]
                existing.auction_turnover_rate = metrics["auction_turnover_rate"]
                existing.source = "tushare_stk_auction"
                existing.updated_at = datetime.now()
                saved += 1
            db.commit()
            return saved
        except Exception:
            db.rollback()
            logger.exception(f"同步 {trade_date} 开盘竞价数据失败")
            return 0
        finally:
            if self._owns_session:
                db.close()

    def sync_auction_open_range(self, trade_dates: Iterable[str]) -> int:
        return sum(self.sync_auction_open(trade_date) for trade_date in trade_dates)

    def sync_auction_open_date_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        calendar = sorted(d for d in self._get_calendar_for_range(start_date, end_date) if start_date <= d <= end_date)
        if not calendar:
            calendar = [start_date] if start_date == end_date else []
        synced_count = self.sync_auction_open_range(calendar)
        return {"trade_dates": calendar, "synced_count": synced_count}

    def _get_calendar_for_trade_date(self, trade_date: str) -> set[str]:
        year = int(trade_date[:4])
        return self._get_calendar_for_year(year) | self._get_calendar_for_year(year - 1)

    def _get_calendar_for_range(self, start_date: str, end_date: str) -> set[str]:
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])
        calendar: set[str] = set()
        for year in range(start_year, end_year + 1):
            calendar.update(self._get_calendar_for_year(year))
        return calendar

    def _get_calendar_for_year(self, year: int) -> set[str]:
        try:
            return set(self.collector.get_trading_calendar(year))
        except TypeError:
            return set(self.collector.get_trading_calendar())

    def recalculate_auction_ratios_from_daily_cache(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """用 stock_daily_data 的 T-1 成交量重算已入库竞价数据的竞昨比。"""
        db = self.session_factory()
        updated = 0
        missing = 0
        try:
            daily_dates = [
                row[0]
                for row in db.query(StockDailyData.trade_date)
                .filter(StockDailyData.trade_date <= end_date)
                .distinct()
                .order_by(StockDailyData.trade_date)
                .all()
            ]
            previous_by_date = {}
            previous = None
            for trade_date in daily_dates:
                previous_by_date[trade_date] = previous
                previous = trade_date

            trade_dates = [
                row[0]
                for row in db.query(StockAuctionOpen.trade_date)
                .filter(StockAuctionOpen.trade_date.between(start_date, end_date))
                .distinct()
                .order_by(StockAuctionOpen.trade_date)
                .all()
            ]
            for trade_date in trade_dates:
                prev_date = previous_by_date.get(trade_date)
                if not prev_date:
                    idx = bisect_left(daily_dates, trade_date)
                    prev_date = daily_dates[idx - 1] if idx > 0 else None
                if not prev_date:
                    missing += db.query(StockAuctionOpen).filter(
                        StockAuctionOpen.trade_date == trade_date
                    ).count()
                    continue
                prev_volume = {
                    row.ts_code: row.vol if row.vol is not None else None
                    for row in db.query(StockDailyData.ts_code, StockDailyData.vol)
                    .filter(StockDailyData.trade_date == prev_date)
                    .all()
                }
                for auction in db.query(StockAuctionOpen).filter(
                    StockAuctionOpen.trade_date == trade_date
                ).all():
                    metrics = calculate_auction_metrics(
                        auction.vol,
                        prev_volume.get(auction.ts_code),
                        None,
                    )
                    if metrics["auction_ratio"] is None:
                        auction.auction_ratio = None
                        missing += 1
                    else:
                        auction.auction_ratio = metrics["auction_ratio"]
                        updated += 1
            db.commit()
            return {
                "start_date": start_date,
                "end_date": end_date,
                "trade_dates": trade_dates,
                "updated_count": updated,
                "missing_count": missing,
            }
        except Exception:
            db.rollback()
            logger.exception(f"重算竞昨比失败: {start_date}~{end_date}")
            return {
                "start_date": start_date,
                "end_date": end_date,
                "trade_dates": [],
                "updated_count": 0,
                "missing_count": missing,
            }
        finally:
            if self._owns_session:
                db.close()

    def get_auction_features(self, trade_date: str, ts_code: str) -> Dict[str, Any]:
        data = self.batch_get_auction_features(trade_date, [ts_code])
        return data.get(ts_code, {})

    def batch_get_auction_features(self, trade_date: str, ts_codes: list[str]) -> Dict[str, Dict[str, Any]]:
        if not ts_codes:
            return {}
        db = self.session_factory()
        try:
            rows = db.query(StockAuctionOpen).filter(
                StockAuctionOpen.trade_date == trade_date,
                StockAuctionOpen.ts_code.in_(ts_codes),
            ).all()
            return {
                r.ts_code: {
                    "price": r.price,
                    "auction_volume": r.vol,
                    "auction_amount": r.amount,
                    "auction_pre_close": r.pre_close,
                    "auction_ratio": r.auction_ratio,
                    "auction_turnover_rate": r.auction_turnover_rate,
                    "auction_source": r.source,
                }
                for r in rows
            }
        finally:
            if self._owns_session:
                db.close()

    @staticmethod
    def _map_by_code(df: pd.DataFrame, column: str) -> Dict[str, Any]:
        if df is None or df.empty or column not in df.columns:
            return {}
        return {row["ts_code"]: row.get(column) for row in df.to_dict("records") if row.get("ts_code")}
