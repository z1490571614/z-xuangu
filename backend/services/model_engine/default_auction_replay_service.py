"""
默认竞价策略历史回放入口。

首版只定义模型中心需要的可测试接口。真实回放优先复用已落库的默认策略结果和历史竞价数据，
不得引入新闻、公告、舆情或 AI 文本特征。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.models import SelectionRecord, SelectedStock, StockAuctionOpen, StockFeatureSnapshot
from backend.models.seal_rate import StockDailyData
from backend.services.tdx_local_selector import get_limit_price, is_common_a_share_ts_code


DEFAULT_AUCTION_RATIO_MIN = 4.0
DEFAULT_AUCTION_RATIO_MAX = 30.0
DEFAULT_AUCTION_TURNOVER_MIN = 0.5
DEFAULT_AUCTION_TURNOVER_MAX = 10.0
DEFAULT_MAX_CLOSE_PRICE = 500.0
DEFAULT_MIN_LIMIT_UP_COUNT = 3
DEFAULT_MIN_SEAL_RATE = 80.0
DEFAULT_MIN_OPEN_CHANGE_PCT = -3.0


def _in_range(value: Any, min_value: float, max_value: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return min_value <= number <= max_value


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(price: Any, base: Any) -> float | None:
    price_value = _number(price)
    base_value = _number(base)
    if price_value is None or base_value is None or base_value <= 0:
        return None
    return (price_value - base_value) / base_value * 100


def _structural_filter_reasons(snapshot: StockFeatureSnapshot | None) -> List[str]:
    if snapshot is None:
        return ["missing_feature_snapshot"]
    reasons: List[str] = []
    limit_count = _number(snapshot.limit_up_count_100d)
    rise_10d = _number(snapshot.rise_10d_pct)
    circ_mv = _number(snapshot.circ_mv)
    if limit_count is None or limit_count < 3:
        reasons.append("limit_up_count_below_default")
    if rise_10d is None or rise_10d < 0:
        reasons.append("rise_10d_not_positive")
    if circ_mv is not None and circ_mv >= 2000:
        reasons.append("circ_mv_above_default")
    return reasons


def _snapshot_market_value_reasons(snapshot: StockFeatureSnapshot | None) -> List[str]:
    circ_mv = _number(getattr(snapshot, "circ_mv", None)) if snapshot is not None else None
    return ["circ_mv_above_default"] if circ_mv is not None and circ_mv >= 2000 else []


def _calculate_seal_metrics(rows: List[Any]) -> Dict[str, Any]:
    touch_days = 0
    limit_up_days = 0
    for row in rows:
        high = _number(getattr(row, "high", None))
        close = _number(getattr(row, "close", None))
        up_limit = _number(getattr(row, "up_limit", None))
        if high is None or up_limit is None:
            continue
        if high >= up_limit - 0.01:
            touch_days += 1
            if close is not None and close >= up_limit - 0.01:
                limit_up_days += 1
    seal_rate = round(limit_up_days / touch_days * 100, 2) if touch_days > 0 else None
    return {
        "touch_days": touch_days,
        "limit_up_days": limit_up_days,
        "seal_rate": seal_rate,
    }


def calculate_daily_default_metrics(
    ts_code: str,
    rows: List[Any],
    trade_date: str | None = None,
) -> Dict[str, Any] | None:
    if len(rows) < 11:
        return None

    ordered = sorted(rows, key=lambda row: row.trade_date)
    pre_change_rows = [row for row in ordered if trade_date is None or row.trade_date < trade_date]
    pre_change_pct = None
    if len(pre_change_rows) >= 2:
        pre_change_pct = _pct_change(pre_change_rows[-1].close, pre_change_rows[-2].close)
        if pre_change_pct is not None:
            pre_change_pct = round(pre_change_pct, 2)
    latest_close = _number(ordered[-1].close)
    base_close = _number(ordered[-11].close)
    if latest_close is None:
        return {"filter_reasons": ["missing_daily_close"]}

    reasons: List[str] = []
    if latest_close >= DEFAULT_MAX_CLOSE_PRICE:
        reasons.append("close_price_above_default")
    if base_close is None or latest_close < base_close:
        reasons.append("rise_10d_not_positive")

    code = ts_code.split(".")[0]
    last_100 = ordered[-101:] if len(ordered) >= 101 else ordered
    limit_count = 0
    for index in range(1, len(last_100)):
        prev_close = _number(last_100[index - 1].close)
        close = _number(last_100[index].close)
        if prev_close is None or close is None:
            continue
        if abs(close - get_limit_price(code, prev_close)) < 0.01:
            limit_count += 1
    if limit_count < DEFAULT_MIN_LIMIT_UP_COUNT:
        reasons.append("limit_up_count_below_default")
    seal_metrics = _calculate_seal_metrics(ordered[-100:])
    rise_10d_pct = None
    if base_close is not None and base_close > 0:
        rise_10d_pct = round((latest_close - base_close) / base_close * 100, 2)
    return {
        "filter_reasons": reasons,
        "limit_up_count": limit_count,
        "touch_days": seal_metrics["touch_days"],
        "limit_up_days": seal_metrics["limit_up_days"],
        "seal_rate": seal_metrics["seal_rate"],
        "rise_10d_pct": rise_10d_pct,
        "pre_change_pct": pre_change_pct,
    }


class DefaultAuctionReplayService:
    def __init__(self, db: Session):
        self.db = db

    def get_recent_real_selection_days(
        self,
        limit: int = 5,
        end_date: str | None = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(SelectionRecord).filter(SelectionRecord.total_count > 0)
        if end_date:
            query = query.filter(SelectionRecord.trade_date <= end_date)
        records = query.order_by(SelectionRecord.trade_date.desc(), SelectionRecord.id.desc()).all()
        result = []
        seen_trade_dates = set()
        for record in records:
            if record.trade_date in seen_trade_dates:
                continue
            seen_trade_dates.add(record.trade_date)
            result.append(
                {
                    "trade_date": record.trade_date,
                    "record_id": record.id,
                    "real_codes": [
                        stock.ts_code
                        for stock in self.db.query(SelectedStock)
                        .filter(SelectedStock.record_id == record.id)
                        .order_by(SelectedStock.id.asc())
                        .all()
                    ],
                }
            )
            if len(result) >= limit:
                break
        return result

    def replay_trade_date(self, trade_date: str) -> Dict[str, Any]:
        auction_rows = (
            self.db.query(StockAuctionOpen)
            .filter(StockAuctionOpen.trade_date == trade_date)
            .order_by(
                StockAuctionOpen.auction_ratio.desc(),
                StockAuctionOpen.auction_turnover_rate.desc(),
                StockAuctionOpen.ts_code.asc(),
            )
            .all()
        )
        if not auction_rows:
            return {
                "trade_date": trade_date,
                "replay_codes": [],
                "diagnostics": ["no_independent_replay_source"],
                "replay_source": None,
                "filter_diagnostics": {},
            }

        candidate_rows = []
        early_filter_diagnostics: Dict[str, List[str]] = {}
        for row in auction_rows:
            if not row.ts_code:
                continue
            reasons = []
            if not is_common_a_share_ts_code(row.ts_code):
                early_filter_diagnostics[row.ts_code] = ["not_common_a_share"]
                continue
            if not _in_range(row.auction_ratio, DEFAULT_AUCTION_RATIO_MIN, DEFAULT_AUCTION_RATIO_MAX):
                reasons.append("auction_ratio_out_of_default_range")
            if not _in_range(row.auction_turnover_rate, DEFAULT_AUCTION_TURNOVER_MIN, DEFAULT_AUCTION_TURNOVER_MAX):
                reasons.append("auction_turnover_out_of_default_range")
            if reasons:
                early_filter_diagnostics[row.ts_code] = reasons
                continue
            candidate_rows.append(row)

        snapshots = {
            row.ts_code: row
            for row in self.db.query(StockFeatureSnapshot)
            .filter(StockFeatureSnapshot.trade_date == trade_date)
            .all()
        }
        daily_default_metrics = self.load_daily_default_metrics(
            trade_date,
            [row.ts_code for row in candidate_rows],
        )
        use_structural_filters = bool(snapshots)
        replay_codes = []
        filter_diagnostics: Dict[str, List[str]] = dict(early_filter_diagnostics)
        for row in candidate_rows:
            reasons = []
            daily_metrics = daily_default_metrics.get(row.ts_code)
            if daily_metrics is None:
                if use_structural_filters:
                    reasons.extend(_structural_filter_reasons(snapshots.get(row.ts_code)))
                else:
                    reasons.append("missing_daily_history")
            else:
                reasons.extend(daily_metrics.get("filter_reasons") or [])
                if use_structural_filters:
                    reasons.extend(_snapshot_market_value_reasons(snapshots.get(row.ts_code)))
            if daily_metrics is not None:
                seal_rate = daily_metrics.get("seal_rate")
                if seal_rate is not None and seal_rate < DEFAULT_MIN_SEAL_RATE:
                    reasons.append("seal_rate_below_default")
            open_change_pct = _pct_change(row.price, row.pre_close)
            if open_change_pct is None:
                reasons.append("missing_open_change_pct")
            elif open_change_pct < DEFAULT_MIN_OPEN_CHANGE_PCT:
                reasons.append("open_change_below_default")
            if reasons:
                filter_diagnostics[row.ts_code] = reasons
                continue
            replay_codes.append(row.ts_code)

        diagnostics = []
        if not replay_codes:
            diagnostics.append("no_replay_candidate_after_default_auction_filters")
        return {
            "trade_date": trade_date,
            "replay_codes": replay_codes,
            "diagnostics": diagnostics,
            "replay_source": "stock_auction_open",
            "filter_diagnostics": filter_diagnostics,
        }

    def load_daily_default_metrics(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Dict[str, Any] | None]:
        codes = sorted(set(ts_codes))
        metrics_by_code: Dict[str, Dict[str, Any] | None] = {code: None for code in codes}
        if not codes:
            return metrics_by_code
        start_date = (datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=260)).strftime("%Y%m%d")
        rows = (
            self.db.query(
                StockDailyData.ts_code,
                StockDailyData.trade_date,
                StockDailyData.close,
                StockDailyData.high,
                StockDailyData.up_limit,
            )
            .filter(
                StockDailyData.ts_code.in_(codes),
                StockDailyData.trade_date >= start_date,
                StockDailyData.trade_date < trade_date,
            )
            .order_by(StockDailyData.ts_code.asc(), StockDailyData.trade_date.desc())
            .all()
        )
        rows_by_code: Dict[str, List[Any]] = {code: [] for code in codes}
        for row in rows:
            bucket = rows_by_code.get(row.ts_code)
            if bucket is not None and len(bucket) < 101:
                bucket.append(row)
        for ts_code, code_rows in rows_by_code.items():
            metrics_by_code[ts_code] = calculate_daily_default_metrics(ts_code, code_rows, trade_date)
        return metrics_by_code
