"""
默认竞价接力 V2 训练样本构建。

只复用 SelectionRecord + SelectedStock 的结构化字段，不引入新闻、公告、
舆情或 AI 文本特征，避免标签和文本信息反哺模型。
"""
import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models import (
    DefaultAuctionTrainingSample,
    SelectionRecord,
    SelectedStock,
    StockAuctionOpen,
    StockFeatureSnapshot,
)
from backend.models.seal_rate import StockDailyData
from backend.services.model_engine.default_auction_label_builder import (
    build_t0_limit_audit,
    build_t1_continue_audit,
    build_t1_premium_label,
)
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.tdx_local_selector import get_limit_price


FEATURE_FIELDS = (
    "auction_ratio",
    "auction_turnover_rate",
    "auction_amount",
    "auction_volume",
    "open_change_pct",
    "pre_change_pct",
    "limit_up_count",
    "touch_days",
    "limit_up_days",
    "seal_rate",
    "rise_10d_pct",
    "circ_mv",
    "prev_turnover_rate",
    "lu_tag",
    "lu_status",
    "lu_open_num",
    "limit_up_suc_rate",
    "rule_score",
    "final_score",
    "score_level",
    "market_limit_up_count",
    "market_limit_down_count",
    "market_max_connected_board",
    "market_zhaban_rate",
    "market_emotion_score",
    "sector_strength",
    "sector_limit_up_count",
    "sector_rank",
    "is_sector_front_runner",
    "sector_change_pct",
    "leader_strength_score",
    "retreat_risk_score",
    "health_score",
    "leader_level_encoded",
    "cycle_stage_encoded",
    "risk_total_score",
    "market_score",
    "chip_score",
    "capital_score",
    "lhb_score",
    "sector_score",
    "technical_score",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def _risk_tags_count(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return len(parsed) if isinstance(parsed, list) else 0
        except Exception:
            return 0
    return 0


def _apply_daily_metrics(features: Dict[str, Any], daily_metrics: Optional[Dict[str, Any]]) -> None:
    if daily_metrics is None:
        return
    features.update(
        {
            "limit_up_count": daily_metrics.get("limit_up_count"),
            "touch_days": daily_metrics.get("touch_days"),
            "limit_up_days": daily_metrics.get("limit_up_days"),
            "seal_rate": daily_metrics.get("seal_rate"),
            "rise_10d_pct": daily_metrics.get("rise_10d_pct"),
        }
    )
    if daily_metrics.get("pre_change_pct") is not None:
        features["pre_change_pct"] = daily_metrics.get("pre_change_pct")


def _build_feature_json(stock: SelectedStock, daily_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    for field in FEATURE_FIELDS:
        value = getattr(stock, field, None)
        features[field] = _json_safe(value)
    features["risk_tags_count"] = _risk_tags_count(getattr(stock, "risk_tags", None))
    _apply_daily_metrics(features, daily_metrics)
    return features


def _apply_auction_open_features(features: Dict[str, Any], auction: Optional[StockAuctionOpen]) -> None:
    if auction is None:
        return
    if auction.auction_ratio is not None:
        features["auction_ratio"] = _json_safe(auction.auction_ratio)
    if auction.auction_turnover_rate is not None:
        features["auction_turnover_rate"] = _json_safe(auction.auction_turnover_rate)
    if auction.amount is not None:
        features["auction_amount"] = _json_safe(auction.amount)
    if auction.vol is not None:
        features["auction_volume"] = _json_safe(auction.vol)
    open_change_pct = _pct_change(auction.price, auction.pre_close)
    if open_change_pct is not None:
        features["open_change_pct"] = open_change_pct


def build_selected_stock_feature_payloads(
    db: Session,
    record: SelectionRecord,
    stocks: List[SelectedStock],
) -> Dict[str, Dict[str, Any]]:
    """
    为真实选股记录组装默认竞价模型特征。

    真实选股表只保存展示字段；模型需要的竞价成交额/量与市场情绪上下文来自
    `stock_auction_open` 和本地日线缓存。训练样本构建与预测刷新必须共用这个入口，
    避免一边特征完整、一边预测缺失。
    """
    ts_codes = [stock.ts_code for stock in stocks if stock.ts_code]
    if not ts_codes:
        return {}

    auctions = {
        row.ts_code: row
        for row in db.query(StockAuctionOpen)
        .filter(StockAuctionOpen.trade_date == record.trade_date, StockAuctionOpen.ts_code.in_(ts_codes))
        .all()
    }
    daily_default_metrics = DefaultAuctionReplayService(db).load_daily_default_metrics(record.trade_date, ts_codes)
    market_context = _build_market_contexts(db, [record.trade_date]).get(record.trade_date)
    payloads: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        if not stock.ts_code:
            continue
        auction = auctions.get(stock.ts_code)
        features = _build_feature_json(stock, daily_default_metrics.get(stock.ts_code))
        _apply_auction_open_features(features, auction)
        if market_context is not None:
            features.update(market_context)
        payloads[stock.ts_code] = {
            "features": features,
            "auction_source": auction.source if auction is not None and auction.source else "selected_stock",
        }
    return payloads


def _dump_json(value: Dict[str, Any]) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False, default=str)


def _pct_change(price: Any, base: Any) -> Optional[float]:
    try:
        price_value = float(price)
        base_value = float(base)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price_value) or not math.isfinite(base_value) or base_value <= 0:
        return None
    return round((price_value - base_value) / base_value * 100, 4)


def _row_get(row: Any, key: str) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _limit_price(ts_code: str, row: Any) -> Optional[float]:
    pre_close = _row_get(row, "pre_close")
    try:
        if pre_close is None:
            return None
        return get_limit_price(ts_code.split(".")[0], float(pre_close))
    except (TypeError, ValueError):
        return None


def _known_trade_dates(
    db: Session,
    start_date: str,
    end_date: str,
    daily_rows: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> list[str]:
    dates = {
        item[0]
        for item in db.query(StockAuctionOpen.trade_date)
        .filter(StockAuctionOpen.trade_date >= start_date, StockAuctionOpen.trade_date <= end_date)
        .distinct()
        .all()
        if item[0]
    }
    if daily_rows:
        dates.update(date for date, _code in daily_rows if start_date <= date)
    else:
        daily_dates = [
            item[0]
            for item in db.query(StockDailyData.trade_date)
            .filter(StockDailyData.trade_date >= start_date)
            .distinct()
            .order_by(StockDailyData.trade_date.asc())
            .all()
            if item[0]
        ]
        dates.update(date for date in daily_dates if date <= end_date)
        for date in daily_dates:
            if date > end_date:
                dates.add(date)
                break
    return sorted(dates)


def _next_trade_date(current: str, known_dates: Iterable[str]) -> Optional[str]:
    for date in sorted(set(known_dates)):
        if date > current:
            return date
    return None


def _auction_feature_json(
    row: StockAuctionOpen,
    snapshot: StockFeatureSnapshot | None = None,
    daily_metrics: Optional[Dict[str, Any]] = None,
    market_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    features = {
        "auction_ratio": row.auction_ratio,
        "auction_turnover_rate": row.auction_turnover_rate,
        "open_change_pct": _pct_change(row.price, row.pre_close),
        "pre_change_pct": None,
        "auction_amount": row.amount,
        "auction_volume": row.vol,
    }
    for field in FEATURE_FIELDS:
        features.setdefault(field, None)
    features["risk_tags_count"] = 0
    if snapshot is not None:
        features.update(
            {
                "limit_up_count": snapshot.limit_up_count_100d,
                "seal_rate": snapshot.seal_rate_100d,
                "rise_10d_pct": snapshot.rise_10d_pct,
                "circ_mv": snapshot.circ_mv,
                "pre_change_pct": snapshot.pre_change_pct,
                "auction_ratio": row.auction_ratio if row.auction_ratio is not None else snapshot.auction_ratio,
                "auction_turnover_rate": (
                    row.auction_turnover_rate
                    if row.auction_turnover_rate is not None
                    else snapshot.auction_turnover_rate
                ),
            }
        )
    _apply_daily_metrics(features, daily_metrics)
    if market_context is not None:
        features.update(market_context)
    return features


def _is_limit_up_row(row: Any) -> bool:
    high = _row_get(row, "high")
    close = _row_get(row, "close")
    up_limit = _row_get(row, "up_limit")
    try:
        return high is not None and close is not None and up_limit is not None and float(close) >= float(up_limit) - 0.01
    except (TypeError, ValueError):
        return False


def _touches_limit_up(row: Any) -> bool:
    high = _row_get(row, "high")
    up_limit = _row_get(row, "up_limit")
    try:
        return high is not None and up_limit is not None and float(high) >= float(up_limit) - 0.01
    except (TypeError, ValueError):
        return False


def _is_limit_down_row(row: Any) -> bool:
    close = _row_get(row, "close")
    down_limit = _row_get(row, "down_limit")
    try:
        return close is not None and down_limit is not None and float(close) <= float(down_limit) + 0.01
    except (TypeError, ValueError):
        return False


def _build_market_contexts(
    db: Session,
    trade_dates: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    dates = sorted({date for date in trade_dates if date})
    if not dates:
        return {}
    min_date = dates[0]
    max_date = dates[-1]
    all_dates = [
        item[0]
        for item in db.query(StockDailyData.trade_date)
        .filter(StockDailyData.trade_date <= max_date)
        .distinct()
        .order_by(StockDailyData.trade_date.asc())
        .all()
        if item[0]
    ]
    useful_dates = [date for date in all_dates if date <= max_date]
    warmup_dates = useful_dates[-(len(dates) + 30) :] if len(useful_dates) > len(dates) + 30 else useful_dates
    if min_date in useful_dates:
        first_index = useful_dates.index(min_date)
        warmup_dates = useful_dates[max(0, first_index - 30) :]
    rows = (
        db.query(
            StockDailyData.ts_code,
            StockDailyData.trade_date,
            StockDailyData.high,
            StockDailyData.close,
            StockDailyData.up_limit,
            StockDailyData.down_limit,
        )
        .filter(StockDailyData.trade_date.in_(warmup_dates))
        .order_by(StockDailyData.trade_date.asc(), StockDailyData.ts_code.asc())
        .all()
    )
    rows_by_date: Dict[str, List[Any]] = {}
    for row in rows:
        rows_by_date.setdefault(row.trade_date, []).append(row)

    consecutive_by_code: Dict[str, int] = {}
    raw_context_by_date: Dict[str, Dict[str, Any]] = {}
    for date in warmup_dates:
        day_rows = rows_by_date.get(date, [])
        limit_up_count = 0
        limit_down_count = 0
        touch_count = 0
        max_connected = 0
        seen_codes = set()
        for row in day_rows:
            seen_codes.add(row.ts_code)
            touched = _touches_limit_up(row)
            sealed = _is_limit_up_row(row)
            if touched:
                touch_count += 1
            if sealed:
                limit_up_count += 1
                consecutive_by_code[row.ts_code] = consecutive_by_code.get(row.ts_code, 0) + 1
                max_connected = max(max_connected, consecutive_by_code[row.ts_code])
            else:
                consecutive_by_code[row.ts_code] = 0
            if _is_limit_down_row(row):
                limit_down_count += 1
        for code in list(consecutive_by_code):
            if code not in seen_codes:
                consecutive_by_code[code] = 0
        zhaban_count = max(0, touch_count - limit_up_count)
        zhaban_rate = round(zhaban_count / touch_count * 100, 4) if touch_count else 0.0
        emotion_score = round(limit_up_count - limit_down_count - zhaban_rate / 10, 4)
        raw_context_by_date[date] = {
            "market_limit_up_count": limit_up_count,
            "market_limit_down_count": limit_down_count,
            "market_max_connected_board": max_connected,
            "market_zhaban_rate": zhaban_rate,
            "market_emotion_score": emotion_score,
        }

    contexts: Dict[str, Dict[str, Any]] = {}
    for trade_date in dates:
        previous_dates = [date for date in warmup_dates if date < trade_date]
        if not previous_dates:
            continue
        previous_date = previous_dates[-1]
        contexts[trade_date] = dict(raw_context_by_date.get(previous_date) or {})
        contexts[trade_date]["market_context_date"] = previous_date
    return contexts


def _load_daily_rows_for_codes(
    db: Session,
    trade_dates: Iterable[str | None],
    ts_codes: Iterable[str],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    dates = sorted({date for date in trade_dates if date})
    codes = sorted({code for code in ts_codes if code})
    if not dates or not codes:
        return {}
    rows = (
        db.query(StockDailyData)
        .filter(StockDailyData.trade_date.in_(dates), StockDailyData.ts_code.in_(codes))
        .all()
    )
    return {
        (row.trade_date, row.ts_code): {
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "pre_close": row.pre_close,
            "up_limit": row.up_limit,
        }
        for row in rows
    }


def _delete_shadowed_replay_sample(
    db: Session,
    strategy_version: str,
    trade_date: str,
    ts_code: str,
) -> int:
    rows = (
        db.query(DefaultAuctionTrainingSample)
        .filter(
            DefaultAuctionTrainingSample.strategy_version == strategy_version,
            DefaultAuctionTrainingSample.trade_date == trade_date,
            DefaultAuctionTrainingSample.ts_code == ts_code,
            DefaultAuctionTrainingSample.sample_source == "replay_backtest",
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    return len(rows)


def _has_real_selected_sample(
    db: Session,
    strategy_version: str,
    trade_date: str,
    ts_code: str,
) -> bool:
    return (
        db.query(DefaultAuctionTrainingSample.id)
        .filter(
            DefaultAuctionTrainingSample.strategy_version == strategy_version,
            DefaultAuctionTrainingSample.trade_date == trade_date,
            DefaultAuctionTrainingSample.ts_code == ts_code,
            DefaultAuctionTrainingSample.sample_source == "real_selected",
        )
        .first()
        is not None
    )


def _apply_market_labels(
    sample: DefaultAuctionTrainingSample,
    ts_code: str,
    trade_date: str,
    next_trade_date: Optional[str],
    daily_rows: Optional[Dict[Tuple[str, str], Dict[str, Any]]],
) -> None:
    daily_rows = daily_rows or {}
    t0_row = daily_rows.get((trade_date, ts_code))
    t1_row = daily_rows.get((next_trade_date, ts_code)) if next_trade_date else None

    t0_limit = _limit_price(ts_code, t0_row)
    t0_audit = build_t0_limit_audit(t0_row, t0_limit)
    sample.label_t0_limit_success = t0_audit["label_t0_limit_success"]
    sample.is_t0_limit_up = t0_audit["is_t0_limit_up"]
    sample.is_t0_one_line_limit_up = t0_audit["is_t0_one_line_limit_up"]
    sample.t0_high_return = _pct_change(_row_get(t0_row, "high"), _row_get(t0_row, "pre_close"))
    sample.t0_close_return = _pct_change(_row_get(t0_row, "close"), _row_get(t0_row, "pre_close"))

    sample.label_t1_premium_success = build_t1_premium_label(t1_row)
    t1_limit = _limit_price(ts_code, t1_row)
    t1_audit = build_t1_continue_audit(t1_row, t1_limit)
    sample.label_t1_continue_limit = t1_audit["label_t1_continue_limit"]
    sample.is_t1_limit_up = t1_audit["is_t1_limit_up"]
    sample.is_t1_one_line_limit_up = t1_audit["is_t1_one_line_limit_up"]
    sample.t1_open_return = _pct_change(_row_get(t1_row, "open"), _row_get(t1_row, "pre_close"))
    sample.t1_high_return = _pct_change(_row_get(t1_row, "high"), _row_get(t1_row, "pre_close"))
    sample.t1_close_return = _pct_change(_row_get(t1_row, "close"), _row_get(t1_row, "pre_close"))


def build_samples_from_replay_range(
    db: Session,
    start_date: str,
    end_date: str,
    sample_source: str = "replay_backtest",
    strategy_version: str = "default_auction_v2",
    daily_rows: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """
    从独立历史竞价回放结果构建默认竞价接力样本。

    `daily_rows` 是可选行情口径输入，key 为 `(trade_date, ts_code)`。缺行情时标签保持
    None，避免伪造训练标签。
    """
    result = {"created_count": 0, "updated_count": 0, "skipped_count": 0, "deleted_count": 0}
    known_dates = _known_trade_dates(db, start_date, end_date, daily_rows)
    replay_service = DefaultAuctionReplayService(db)
    market_contexts = _build_market_contexts(db, known_dates)
    touched_keys: set[tuple[str, str]] = set()

    try:
        for trade_date in [date for date in known_dates if start_date <= date <= end_date]:
            replay = replay_service.replay_trade_date(trade_date)
            replay_codes = set(replay.get("replay_codes") or [])
            if not replay_codes:
                continue
            next_date = _next_trade_date(trade_date, known_dates)
            market_daily_rows = daily_rows or _load_daily_rows_for_codes(
                db,
                [trade_date, next_date],
                replay_codes,
            )
            auction_rows = (
                db.query(StockAuctionOpen)
                .filter(StockAuctionOpen.trade_date == trade_date, StockAuctionOpen.ts_code.in_(replay_codes))
                .order_by(StockAuctionOpen.ts_code.asc())
                .all()
            )
            snapshots = {
                row.ts_code: row
                for row in db.query(StockFeatureSnapshot)
                .filter(StockFeatureSnapshot.trade_date == trade_date, StockFeatureSnapshot.ts_code.in_(replay_codes))
                .all()
            }
            daily_default_metrics = replay_service.load_daily_default_metrics(trade_date, replay_codes)
            for auction in auction_rows:
                if sample_source == "replay_backtest" and _has_real_selected_sample(
                    db,
                    strategy_version,
                    trade_date,
                    auction.ts_code,
                ):
                    result["deleted_count"] += _delete_shadowed_replay_sample(
                        db,
                        strategy_version,
                        trade_date,
                        auction.ts_code,
                    )
                    result["skipped_count"] += 1
                    continue
                existing = (
                    db.query(DefaultAuctionTrainingSample)
                    .filter(
                        DefaultAuctionTrainingSample.strategy_version == strategy_version,
                        DefaultAuctionTrainingSample.trade_date == trade_date,
                        DefaultAuctionTrainingSample.ts_code == auction.ts_code,
                        DefaultAuctionTrainingSample.sample_source == sample_source,
                    )
                    .first()
                )
                if existing is None:
                    existing = DefaultAuctionTrainingSample(
                        strategy_version=strategy_version,
                        trade_date=trade_date,
                        ts_code=auction.ts_code,
                        sample_source=sample_source,
                    )
                    db.add(existing)
                    result["created_count"] += 1
                else:
                    result["updated_count"] += 1
                touched_keys.add((trade_date, auction.ts_code))

                existing.name = existing.name or ""
                existing.strategy_name = "default"
                existing.replay_source = replay.get("replay_source") or "stock_auction_open"
                existing.auction_source = auction.source or "stock_auction_open"
                existing.auction_ratio_unit = "percent"
                existing.auction_turnover_rate_basis = "free_float"
                existing.feature_snapshot_time = f"{trade_date}T09:25:00"
                existing.feature_json = _dump_json(
                    _auction_feature_json(
                        auction,
                        snapshots.get(auction.ts_code),
                        daily_default_metrics.get(auction.ts_code),
                        market_contexts.get(trade_date),
                    )
                )
                _apply_market_labels(existing, auction.ts_code, trade_date, next_date, market_daily_rows)
        stale_samples = (
            db.query(DefaultAuctionTrainingSample)
            .filter(
                DefaultAuctionTrainingSample.strategy_version == strategy_version,
                DefaultAuctionTrainingSample.sample_source == sample_source,
                DefaultAuctionTrainingSample.trade_date >= start_date,
                DefaultAuctionTrainingSample.trade_date <= end_date,
            )
            .all()
        )
        for stale in stale_samples:
            if (stale.trade_date, stale.ts_code) in touched_keys:
                continue
            db.delete(stale)
            result["deleted_count"] += 1
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def build_samples_from_selected_record(
    db: Session,
    selection_record_id: int,
    sample_source: str = "real_selected",
    strategy_version: str = "default_auction_v2",
) -> Dict[str, int]:
    """
    从已落库默认选股记录构建训练样本。

    按唯一约束字段显式查询后 upsert，避免在没有完整业务主键上下文时盲目 merge。
    """
    try:
        result = {"created_count": 0, "updated_count": 0, "skipped_count": 0, "deleted_count": 0}
        record = db.query(SelectionRecord).filter(SelectionRecord.id == selection_record_id).first()
        if record is None:
            result["skipped_count"] += 1
            return result

        stocks = (
            db.query(SelectedStock)
            .filter(SelectedStock.record_id == selection_record_id)
            .order_by(SelectedStock.id.asc())
            .all()
        )
        ts_codes = [stock.ts_code for stock in stocks if stock.ts_code]
        known_dates = _known_trade_dates(db, record.trade_date, record.trade_date)
        next_date = _next_trade_date(record.trade_date, known_dates)
        daily_rows = _load_daily_rows_for_codes(db, [record.trade_date, next_date], ts_codes)
        feature_payloads = build_selected_stock_feature_payloads(db, record, stocks)

        seen_samples: Dict[tuple[str, str, str, str], DefaultAuctionTrainingSample] = {}
        for stock in stocks:
            if not stock.ts_code:
                result["skipped_count"] += 1
                continue

            key = (strategy_version, record.trade_date, stock.ts_code, sample_source)
            existing = seen_samples.get(key)
            if existing is None:
                existing = (
                    db.query(DefaultAuctionTrainingSample)
                    .filter(
                        DefaultAuctionTrainingSample.strategy_version == strategy_version,
                        DefaultAuctionTrainingSample.trade_date == record.trade_date,
                        DefaultAuctionTrainingSample.ts_code == stock.ts_code,
                        DefaultAuctionTrainingSample.sample_source == sample_source,
                    )
                    .first()
                )
            if existing is None:
                existing = DefaultAuctionTrainingSample(
                    strategy_version=strategy_version,
                    trade_date=record.trade_date,
                    ts_code=stock.ts_code,
                    sample_source=sample_source,
                )
                db.add(existing)
                result["created_count"] += 1
            else:
                result["updated_count"] += 1
            seen_samples[key] = existing
            if sample_source == "real_selected":
                result["deleted_count"] += _delete_shadowed_replay_sample(
                    db,
                    strategy_version,
                    record.trade_date,
                    stock.ts_code,
                )

            feature_payload = feature_payloads.get(stock.ts_code, {})
            features = feature_payload.get("features") or _build_feature_json(stock)
            existing.name = stock.name
            existing.strategy_name = "default"
            existing.auction_source = feature_payload.get("auction_source") or "selected_stock"
            existing.auction_ratio_unit = "percent"
            existing.auction_turnover_rate_basis = "free_float"
            existing.feature_snapshot_time = (
                record.execute_time.isoformat(timespec="seconds")
                if getattr(record, "execute_time", None)
                else None
            )
            existing.feature_json = _dump_json(features)
            _apply_market_labels(existing, stock.ts_code, record.trade_date, next_date, daily_rows)

        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
