"""
默认选股的数据库日线 + 实时 Tushare 竞价通道。

日线结构指标和封板率只使用已入库的 stock_daily_data 批量计算；
竞价指标仍实时同步 Tushare stk_auction 后从 stock_auction_open 读取。
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from backend.database import SessionLocal
from backend.models.seal_rate import StockDailyData
from backend.services.auction_data_service import AuctionDataService, calculate_auction_metrics
from backend.services.daily_basic_fallback import get_daily_basic_with_previous_fallback
from backend.services.tdx_selector import TdxStockResult
from backend.services.tdx_local_selector import is_common_a_share_ts_code

logger = logging.getLogger(__name__)


def _clean_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class DefaultDbTushareSelectorService:
    """用 stock_daily_data 批量计算结构条件，再叠加实时 stk_auction 竞价条件。"""

    def __init__(
        self,
        auction_service: Optional[Any] = None,
        session_factory=SessionLocal,
    ):
        self.auction_service = auction_service or AuctionDataService()
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal

    def select(
        self,
        trade_date: str,
        max_circ_mv: float = 2000,
        max_close_price: float = 500,
        min_limit_up_count: int = 3,
        period_days: int = 100,
        data_collector: Optional[Any] = None,
        auction_ratio_min: float = 4.0,
        auction_ratio_max: float = 30.0,
        auction_turnover_rate_min: float = 0.5,
        auction_turnover_rate_max: float = 10.0,
    ) -> Dict[str, Any]:
        start = time.time()
        logger.info("========== 阶段1：数据库日线 + 实时Tushare竞价选股 | 日期=%s ==========", trade_date)

        db = self.session_factory()
        try:
            trading_dates = self._load_recent_daily_dates(db, trade_date, max(period_days, 11))
            if not trading_dates:
                return self._empty_result(start, "stock_daily_data 无可用日线")

            latest_daily_date = trading_dates[-1]
            daily_candidates = self._select_from_daily_cache(
                db=db,
                trading_dates=trading_dates,
                latest_daily_date=latest_daily_date,
                max_close_price=max_close_price,
                min_limit_up_count=min_limit_up_count,
                period_days=period_days,
                data_collector=data_collector,
                trade_date=trade_date,
                max_circ_mv=max_circ_mv,
            )
        finally:
            if self._owns_session:
                db.close()

        ts_codes = [stock.ts_code for stock in daily_candidates]
        synced_count = self.auction_service.sync_auction_open(trade_date)
        auction_features = self.auction_service.batch_get_auction_features(trade_date, ts_codes)
        realtime_fallback_features = self._build_realtime_auction_features(
            daily_candidates,
            auction_features,
            data_collector,
        )
        if realtime_fallback_features:
            auction_features = {**realtime_fallback_features, **auction_features}

        passed = []
        funnel = {
            "daily_candidates": len(daily_candidates),
            "auction_synced": synced_count,
            "auction_realtime_fallback": len(realtime_fallback_features),
            "has_auction": 0,
            "auction_ratio_pass": 0,
            "auction_turnover_pass": 0,
        }
        missing_auction = []
        for stock in daily_candidates:
            features = auction_features.get(stock.ts_code)
            if not features:
                if len(missing_auction) < 10:
                    missing_auction.append(stock.ts_code)
                continue
            funnel["has_auction"] += 1

            auction_ratio = _clean_float(features.get("auction_ratio"))
            if auction_ratio is None or not (auction_ratio_min <= auction_ratio <= auction_ratio_max):
                continue
            funnel["auction_ratio_pass"] += 1

            auction_turnover_rate = _clean_float(features.get("auction_turnover_rate"))
            if auction_turnover_rate is None or not (
                auction_turnover_rate_min <= auction_turnover_rate <= auction_turnover_rate_max
            ):
                continue
            funnel["auction_turnover_pass"] += 1

            stock.auction_ratio = auction_ratio
            stock.auction_turnover_rate = auction_turnover_rate
            stock.extra_data.update(
                {
                    "auction_amount": features.get("auction_amount"),
                    "auction_volume": features.get("auction_volume"),
                    "auction_pre_close": features.get("auction_pre_close"),
                    "auction_source": features.get("auction_source"),
                }
            )
            passed.append(stock)

        if missing_auction:
            logger.warning("数据库日线通道存在竞价数据缺失，示例: %s", ",".join(missing_auction))
        if realtime_fallback_features:
            logger.warning(
                "Tushare竞价缺失，已使用通达信实时行情兜底计算竞价特征: %s/%s",
                len(realtime_fallback_features),
                len(daily_candidates),
            )

        execution_time = time.time() - start
        logger.info(
            "数据库日线+实时竞价选股完成: 日线候选=%s, 有竞价=%s, 竞昨比通过=%s, 最终=%s, 耗时=%.2fs",
            funnel["daily_candidates"],
            funnel["has_auction"],
            funnel["auction_ratio_pass"],
            len(passed),
            execution_time,
        )
        return {
            "stocks": passed,
            "total_count": len(passed),
            "execution_time": execution_time,
            "source": "stock_daily_tushare",
            "task_results": [
                {
                    "task_id": "db_tushare_default",
                    "task_name": "数据库日线+实时Tushare竞价选股",
                    "query": "stock_daily_data批量筛选 + 实时stk_auction竞价过滤",
                    "stocks": passed,
                    "total_count": len(passed),
                    "execution_time": execution_time,
                    "funnel": funnel,
                }
            ],
        }

    def _empty_result(self, start: float, reason: str) -> Dict[str, Any]:
        logger.warning("数据库日线+实时竞价选股为空: %s", reason)
        return {
            "stocks": [],
            "total_count": 0,
            "execution_time": time.time() - start,
            "source": "stock_daily_tushare",
            "task_results": [{"task_id": "db_tushare_default", "error": reason, "stocks": []}],
        }

    def _load_recent_daily_dates(self, db, trade_date: str, required_days: int) -> List[str]:
        rows = (
            db.query(StockDailyData.trade_date)
            .filter(StockDailyData.trade_date <= trade_date)
            .distinct()
            .order_by(StockDailyData.trade_date.desc())
            .limit(required_days)
            .all()
        )
        return sorted(row[0] for row in rows if row[0])

    def _select_from_daily_cache(
        self,
        db,
        trading_dates: List[str],
        latest_daily_date: str,
        max_close_price: float,
        min_limit_up_count: int,
        period_days: int,
        data_collector: Optional[Any],
        trade_date: str,
        max_circ_mv: float,
    ) -> List[TdxStockResult]:
        rows = (
            db.query(StockDailyData)
            .filter(StockDailyData.trade_date.in_(trading_dates))
            .order_by(StockDailyData.ts_code.asc(), StockDailyData.trade_date.asc())
            .all()
        )
        rows_by_code: Dict[str, List[StockDailyData]] = defaultdict(list)
        for row in rows:
            if is_common_a_share_ts_code(row.ts_code):
                rows_by_code[row.ts_code].append(row)

        daily_basic_map = self._build_daily_basic_map(data_collector, trade_date, max_circ_mv)
        stock_info = self._build_stock_info_map(data_collector)

        selected = []
        for ts_code, stock_rows in rows_by_code.items():
            latest = stock_rows[-1]
            if latest.trade_date != latest_daily_date:
                continue
            if latest.close is None or latest.close >= max_close_price:
                continue
            daily_basic = daily_basic_map.get(ts_code, {})
            circ_mv = daily_basic.get("circ_mv")
            if circ_mv is not None and circ_mv >= max_circ_mv:
                continue
            if len(stock_rows) < 11:
                continue
            base_10d = stock_rows[-11].close
            if base_10d is None or base_10d <= 0 or latest.close < base_10d:
                continue

            period_rows = stock_rows[-period_days:] if len(stock_rows) >= period_days else stock_rows[:]
            seal = self._calculate_seal_metrics(period_rows)
            if seal["limit_up_days"] < min_limit_up_count:
                continue

            info = stock_info.get(ts_code, {})
            rise_10d_pct = round((latest.close - base_10d) / base_10d * 100, 2)
            selected.append(
                TdxStockResult(
                    ts_code=ts_code,
                    name=info.get("name", ""),
                    close=latest.close,
                    change_pct=latest.pct_chg,
                    pre_change_pct=latest.pct_chg,
                    limit_up_count=seal["limit_up_days"],
                    seal_rate=seal["seal_rate"],
                    rise_10d_pct=rise_10d_pct,
                    industry=info.get("industry"),
                    extra_data={
                        "daily_source": "stock_daily_data",
                        "latest_daily_date": latest_daily_date,
                        "touch_days": seal["touch_days"],
                        "limit_up_days": seal["limit_up_days"],
                        "seal_rate": seal["seal_rate"],
                        "seal_rate_data_complete": 1 if len(period_rows) >= period_days else 0,
                        "circ_mv": circ_mv,
                        "previous_daily_vol": latest.vol,
                        "float_share": daily_basic.get("float_share"),
                        "free_share": daily_basic.get("free_share"),
                    },
                )
            )
        return selected

    def _calculate_seal_metrics(self, rows: Iterable[StockDailyData]) -> Dict[str, Any]:
        touch_days = 0
        limit_up_days = 0
        for row in rows:
            if row.high is None or row.close is None or row.up_limit is None:
                continue
            if row.high >= row.up_limit - 0.01:
                touch_days += 1
                if row.close >= row.up_limit - 0.01:
                    limit_up_days += 1
        return {
            "touch_days": touch_days,
            "limit_up_days": limit_up_days,
            "seal_rate": round(limit_up_days / touch_days * 100, 2) if touch_days > 0 else None,
        }

    def _build_daily_basic_map(
        self,
        data_collector: Optional[Any],
        trade_date: str,
        max_circ_mv: float,
    ) -> Dict[str, Dict[str, Optional[float]]]:
        if data_collector is None:
            return {}
        try:
            calendar = self._collector_calendar(data_collector, trade_date)
            df = get_daily_basic_with_previous_fallback(
                data_collector,
                trade_date,
                calendar=calendar,
                purpose="数据库日线选股市值过滤",
            )
            if df is None or df.empty:
                return {}
            result = {}
            for row in df.to_dict("records"):
                ts_code = row.get("ts_code")
                circ_mv = _clean_float(row.get("circ_mv"))
                if ts_code:
                    result[ts_code] = {
                        "circ_mv": circ_mv / 10000 if circ_mv is not None else None,
                        "float_share": _clean_float(row.get("float_share")),
                        "free_share": _clean_float(row.get("free_share")),
                    }
            return result
        except Exception as e:
            logger.warning("数据库日线选股获取市值失败: %s", e)
            return {}

    def _build_circ_mv_map(
        self,
        data_collector: Optional[Any],
        trade_date: str,
        max_circ_mv: float,
    ) -> Dict[str, float]:
        daily_basic_map = self._build_daily_basic_map(data_collector, trade_date, max_circ_mv)
        return {
            ts_code: values["circ_mv"]
            for ts_code, values in daily_basic_map.items()
            if values.get("circ_mv") is not None
        }

    def _build_realtime_auction_features(
        self,
        daily_candidates: List[TdxStockResult],
        existing_features: Dict[str, Dict[str, Any]],
        data_collector: Optional[Any],
    ) -> Dict[str, Dict[str, Any]]:
        if data_collector is None or not hasattr(data_collector, "get_realtime_quotes"):
            return {}

        missing_stocks = [
            stock
            for stock in daily_candidates
            if stock.ts_code and stock.ts_code not in existing_features
        ]
        if not missing_stocks:
            return {}

        try:
            realtime = data_collector.get_realtime_quotes([stock.ts_code for stock in missing_stocks])
        except Exception as e:
            logger.warning("通达信实时行情竞价兜底失败: %s", e)
            return {}

        fallback = {}
        for stock in missing_stocks:
            rt = realtime.get(stock.ts_code)
            if not rt:
                continue
            auction_volume = _clean_float(rt.get("volume"))
            if auction_volume is None:
                volume_hand = _clean_float(rt.get("volume_hand") or rt.get("total_hand"))
                auction_volume = volume_hand * 100 if volume_hand is not None else None
            if auction_volume is None or auction_volume <= 0:
                continue

            extra = stock.extra_data or {}
            metrics = calculate_auction_metrics(
                auction_volume,
                extra.get("previous_daily_vol"),
                extra.get("float_share"),
                extra.get("free_share"),
            )
            if metrics["auction_ratio"] is None or metrics["auction_turnover_rate"] is None:
                continue

            fallback[stock.ts_code] = {
                "price": rt.get("open") or rt.get("close"),
                "auction_volume": auction_volume,
                "auction_amount": rt.get("amount"),
                "auction_pre_close": rt.get("pre_close"),
                "auction_ratio": metrics["auction_ratio"],
                "auction_turnover_rate": metrics["auction_turnover_rate"],
                "auction_source": "tdx_realtime_quote_fallback",
            }
        return fallback

    def _collector_calendar(self, data_collector: Any, trade_date: str) -> set[str]:
        try:
            year = int(trade_date[:4])
            try:
                return set(data_collector.get_trading_calendar(year)) | set(data_collector.get_trading_calendar(year - 1))
            except TypeError:
                return set(data_collector.get_trading_calendar())
        except Exception:
            return set()

    def _build_stock_info_map(self, data_collector: Optional[Any]) -> Dict[str, Dict[str, Any]]:
        if data_collector is None or not hasattr(data_collector, "get_stock_basic"):
            return {}
        try:
            df = data_collector.get_stock_basic()
            if df is None or df.empty:
                return {}
            result = {}
            for row in df.to_dict("records"):
                ts_code = row.get("ts_code")
                if ts_code:
                    result[ts_code] = {"name": row.get("name"), "industry": row.get("industry")}
            return result
        except Exception as e:
            logger.warning("数据库日线选股获取股票名称失败: %s", e)
            return {}
