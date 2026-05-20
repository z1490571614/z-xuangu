"""
当日涨停模型日线模拟盘回测服务。
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, object_session

from backend.database import SessionLocal
from backend.models import (
    DefaultAuctionTrainingSample,
    ModelVersion,
    T0SimulationBacktestDaily,
    T0SimulationBacktestRun,
    T0SimulationBacktestTrade,
)
from backend.models.seal_rate import StockDailyData
from backend.services.model_engine import lightgbm_service


MODEL_NAME = "default_auction_t0_limit_lgbm"
BUY_TIME = "09:30"
SELL_TIME = "15:00"
VALID_SAMPLE_SOURCES = {"real_selected", "replay_backtest", "all"}


@dataclass
class T0SimulationBacktestCreate:
    start_date: str
    end_date: str
    model_version: Optional[str] = None
    sample_source: str = "replay_backtest"
    initial_cash: float = 100000.0
    buy_top_n: int = 2
    max_positions: int = 4
    min_buy_prob_pct: float = 50.0
    min_open_change_pct: float = -3.0
    max_open_change_pct: float = 7.0
    take_profit_pct: float = 13.0
    high_profit_hold_pct: float = 13.0
    profit_pullback_pct: float = 5.0
    stop_loss_pct: float = -5.0
    max_holding_days: int = 3
    force_close_on_end: bool = False
    cost: Dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        for name in ("start_date", "end_date"):
            value = getattr(self, name)
            if not value.isdigit() or len(value) != 8:
                raise ValueError(f"{name} 必须是8位日期YYYYMMDD")
        if self.start_date > self.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        if self.sample_source not in VALID_SAMPLE_SOURCES:
            raise ValueError("sample_source 必须是 real_selected/replay_backtest/all")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash 必须大于0")
        if self.buy_top_n <= 0:
            raise ValueError("buy_top_n 必须大于0")
        if self.max_positions <= 0:
            raise ValueError("max_positions 必须大于0")
        if self.buy_top_n > self.max_positions:
            raise ValueError("buy_top_n 不能大于 max_positions")
        if self.min_buy_prob_pct < 0 or self.min_buy_prob_pct > 100:
            raise ValueError("min_buy_prob_pct 必须在0到100之间")
        if self.min_open_change_pct > self.max_open_change_pct:
            raise ValueError("min_open_change_pct 不能大于 max_open_change_pct")
        if self.max_holding_days <= 0:
            raise ValueError("max_holding_days 必须大于0")
        if self.high_profit_hold_pct <= 0:
            raise ValueError("high_profit_hold_pct 必须大于0")
        if self.profit_pullback_pct <= 0:
            raise ValueError("profit_pullback_pct 必须大于0")


def create_t0_simulation_backtest_run(db: Session, request: T0SimulationBacktestCreate) -> T0SimulationBacktestRun:
    request.validate()
    run = T0SimulationBacktestRun(
        status="pending",
        start_date=request.start_date,
        end_date=request.end_date,
        model_name=MODEL_NAME,
        model_version=request.model_version,
        sample_source=request.sample_source,
        initial_cash=float(request.initial_cash),
        buy_top_n=int(request.buy_top_n),
        max_positions=int(request.max_positions),
        min_buy_prob_pct=float(request.min_buy_prob_pct),
        min_open_change_pct=float(request.min_open_change_pct),
        max_open_change_pct=float(request.max_open_change_pct),
        take_profit_pct=float(request.take_profit_pct),
        high_profit_hold_pct=float(request.high_profit_hold_pct),
        profit_pullback_pct=float(request.profit_pullback_pct),
        stop_loss_pct=float(request.stop_loss_pct),
        max_holding_days=int(request.max_holding_days),
        force_close_on_end=1 if request.force_close_on_end else 0,
        cost_json=_dump_json(request.cost or {}),
        summary_json="{}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_t0_simulation_backtest(db: Optional[Session], run_id: int) -> Dict[str, Any]:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        run = db.query(T0SimulationBacktestRun).filter(T0SimulationBacktestRun.id == run_id).first()
        if run is None:
            raise ValueError(f"回测运行不存在: {run_id}")
        if run.status in {"cancel_requested", "canceled"}:
            run.status = "canceled"
            run.finished_at = datetime.now()
            db.commit()
            return get_t0_simulation_backtest_run(db, run.id)
        run.status = "running"
        run.started_at = datetime.now()
        run.error_message = None
        db.query(T0SimulationBacktestDaily).filter(T0SimulationBacktestDaily.run_id == run.id).delete()
        db.query(T0SimulationBacktestTrade).filter(T0SimulationBacktestTrade.run_id == run.id).delete()
        db.commit()

        try:
            payload = _execute_backtest(db, run)
            run.status = "canceled" if payload.get("canceled") else "passed"
            run.summary_json = _dump_json(payload["summary"])
            run.finished_at = datetime.now()
            db.commit()
            return get_t0_simulation_backtest_run(db, run.id)
        except Exception as exc:
            db.rollback()
            failed = db.query(T0SimulationBacktestRun).filter(T0SimulationBacktestRun.id == run_id).first()
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)
                failed.finished_at = datetime.now()
                db.commit()
                return get_t0_simulation_backtest_run(db, failed.id)
            raise
    finally:
        if owns_session:
            db.close()


def list_t0_simulation_backtest_runs(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        db.query(T0SimulationBacktestRun)
        .order_by(T0SimulationBacktestRun.id.desc())
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    return [_run_payload(row, db) for row in rows]


def request_cancel_t0_simulation_backtest_run(db: Session, run_id: int) -> Dict[str, Any]:
    run = db.query(T0SimulationBacktestRun).filter(T0SimulationBacktestRun.id == run_id).first()
    if run is None:
        raise ValueError(f"回测运行不存在: {run_id}")
    if run.status in {"pending", "running"}:
        run.status = "cancel_requested"
        db.commit()
        db.refresh(run)
    return _run_payload(run, db)


def get_t0_simulation_backtest_run(db: Session, run_id: int) -> Dict[str, Any]:
    run = db.query(T0SimulationBacktestRun).filter(T0SimulationBacktestRun.id == run_id).first()
    if run is None:
        raise ValueError(f"回测运行不存在: {run_id}")
    daily = (
        db.query(T0SimulationBacktestDaily)
        .filter(T0SimulationBacktestDaily.run_id == run.id)
        .order_by(T0SimulationBacktestDaily.trade_date.asc())
        .all()
    )
    trades = (
        db.query(T0SimulationBacktestTrade)
        .filter(T0SimulationBacktestTrade.run_id == run.id)
        .order_by(T0SimulationBacktestTrade.buy_date.asc(), T0SimulationBacktestTrade.rank.asc(), T0SimulationBacktestTrade.id.asc())
        .all()
    )
    payload = _run_payload(run, db)
    payload["daily"] = [_daily_payload(row) for row in daily]
    payload["trades"] = [_trade_payload(row) for row in trades]
    return payload


def _execute_backtest(db: Session, run: T0SimulationBacktestRun) -> Dict[str, Any]:
    mv = _find_model_version(db, run.model_version)
    run.resolved_model_version = mv.version
    feature_cols = _json_loads(mv.feature_cols, [])
    feature_units = (_json_loads(mv.params, {}) or {}).get("feature_units") or {}
    cost = _json_loads(run.cost_json, {})
    stats = {
        "skipped_buy_count": 0,
        "skipped_low_prob_count": 0,
        "skipped_low_open_change_count": 0,
        "skipped_high_open_change_count": 0,
        "skipped_one_line_limit_up_count": 0,
        "prediction_failed_count": 0,
        "missing_price_count": 0,
    }
    samples_by_date = _load_samples_by_date(db, run)
    if not samples_by_date:
        raise ValueError("日期区间内没有可回测样本")

    trade_dates = _load_trade_dates(db, run)
    if not trade_dates:
        raise ValueError("日期区间内没有日线数据")

    prices = _load_prices(db, run)
    cash = float(run.initial_cash)
    prev_equity = cash
    peak_equity = cash
    positions: List[Dict[str, Any]] = []
    closed_returns: List[float] = []
    closed_profit_amounts: List[float] = []
    canceled = False

    for trade_date in trade_dates:
        if _is_cancel_requested(db, run.id):
            canceled = True
            break
        positions, cash = _sell_pending_next_open(
            positions,
            trade_date,
            trade_dates,
            prices,
            cost,
            stats,
            closed_returns,
            closed_profit_amounts,
            cash,
        )
        candidates = _filter_by_min_buy_probability(
            _predict_candidates(samples_by_date.get(trade_date, []), mv, feature_cols, feature_units, stats),
            run,
            stats,
        )
        held_codes = {position["ts_code"] for position in positions}
        buy_slots = max(0, int(run.max_positions) - len(positions))
        selected = []
        for item in candidates:
            if len(selected) >= min(int(run.buy_top_n), buy_slots):
                break
            if item["ts_code"] in held_codes:
                continue
            buy_price = prices.get((trade_date, item["ts_code"]))
            if _is_below_min_open_change(item, buy_price, run):
                stats["skipped_buy_count"] += 1
                stats["skipped_low_open_change_count"] += 1
                continue
            if _is_above_max_open_change(item, buy_price, run):
                stats["skipped_buy_count"] += 1
                stats["skipped_high_open_change_count"] += 1
                continue
            if _is_one_line_limit_up_candidate(item, buy_price):
                stats["skipped_buy_count"] += 1
                stats["skipped_one_line_limit_up_count"] += 1
                continue
            selected.append(item)
        stats["skipped_buy_count"] += max(0, min(int(run.buy_top_n), len(candidates)) - len(selected)) if buy_slots == 0 else 0

        for rank, candidate in enumerate(selected, start=1):
            price = prices.get((trade_date, candidate["ts_code"]))
            if price is None or not _valid_price(price.open):
                stats["missing_price_count"] += 1
                stats["skipped_buy_count"] += 1
                continue
            target_amount = _round_money(prev_equity / float(run.max_positions))
            buy_amount = min(cash, target_amount)
            if buy_amount <= 0:
                stats["skipped_buy_count"] += 1
                continue
            cash = _round_money(cash - buy_amount)
            trade = T0SimulationBacktestTrade(
                run_id=run.id,
                ts_code=candidate["ts_code"],
                name=candidate["name"],
                model_prob=candidate["prob"],
                rank=rank,
                buy_date=trade_date,
                buy_time=BUY_TIME,
                buy_price=float(price.open),
                buy_amount=buy_amount,
                holding_days=0,
                status="open",
            )
            db.add(trade)
            db.flush()
            positions.append(
                {
                    "trade": trade,
                    "ts_code": candidate["ts_code"],
                    "buy_date": trade_date,
                    "buy_price": float(price.open),
                    "buy_amount": buy_amount,
                    "shares": buy_amount / float(price.open),
                    "last_close": float(price.close) if _valid_price(price.close) else float(price.open),
                }
            )

        still_open = []
        for position in positions:
            if position.get("pending_sell_reason"):
                position["trade"].holding_days = _holding_days(trade_dates, position["buy_date"], trade_date)
                still_open.append(position)
                continue
            close_price = prices.get((trade_date, position["ts_code"]))
            if close_price is None or not _valid_price(close_price.close):
                stats["missing_price_count"] += 1
                still_open.append(position)
                continue
            position["last_close"] = float(close_price.close)
            holding_days = _holding_days(trade_dates, position["buy_date"], trade_date)
            raw_return = (float(close_price.close) - position["buy_price"]) / position["buy_price"] * 100.0
            position["highest_profit_pct"] = max(float(position.get("highest_profit_pct", raw_return)), raw_return)
            reason = _sell_reason(raw_return, holding_days, run, close_price, position)
            if reason == "stop_loss" and _is_limit_down_close(close_price):
                position["trade"].holding_days = holding_days
                position["pending_sell_reason"] = "stop_loss_next_open"
                still_open.append(position)
                continue
            if reason is None and run.force_close_on_end and trade_date == run.end_date:
                reason = "end_of_backtest"
            if reason is None:
                position["trade"].holding_days = holding_days
                still_open.append(position)
                continue
            net_return = _net_return(raw_return, cost)
            profit_amount = _round_money(position["buy_amount"] * net_return / 100.0)
            cash = _round_money(cash + position["buy_amount"] + profit_amount)
            trade = position["trade"]
            trade.sell_date = trade_date
            trade.sell_time = SELL_TIME
            trade.sell_price = float(close_price.close)
            trade.holding_days = holding_days
            trade.return_pct = _round_pct(net_return)
            trade.profit_amount = profit_amount
            trade.sell_reason = reason
            trade.status = "closed"
            closed_returns.append(_round_pct(net_return))
            closed_profit_amounts.append(profit_amount)
        positions = still_open

        market_value = 0.0
        for position in positions:
            close_price = prices.get((trade_date, position["ts_code"]))
            if close_price is not None and _valid_price(close_price.close):
                position["last_close"] = float(close_price.close)
            valuation_price = position.get("last_close")
            if _valid_price(valuation_price):
                market_value += position["shares"] * float(valuation_price)
        market_value = _round_money(market_value)
        equity = _round_money(cash + market_value)
        daily_return = _round_pct((equity - prev_equity) / prev_equity * 100.0) if prev_equity > 0 else 0.0
        peak_equity = max(peak_equity, equity)
        drawdown = _round_pct((equity - peak_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0
        db.add(
            T0SimulationBacktestDaily(
                run_id=run.id,
                trade_date=trade_date,
                cash=cash,
                market_value=market_value,
                equity=equity,
                daily_return_pct=daily_return,
                drawdown_pct=drawdown,
                position_count=len(positions),
            )
        )
        prev_equity = equity
        db.commit()

    summary = _build_summary(run, prev_equity, positions, closed_returns, closed_profit_amounts, stats, db)
    db.commit()
    return {"summary": summary, "canceled": canceled}


def _sell_pending_next_open(
    positions: List[Dict[str, Any]],
    trade_date: str,
    trade_dates: List[str],
    prices: Dict[tuple, StockDailyData],
    cost: Dict[str, Any],
    stats: Dict[str, int],
    closed_returns: List[float],
    closed_profit_amounts: List[float],
    cash: float,
) -> Tuple[List[Dict[str, Any]], float]:
    still_open = []
    for position in positions:
        reason = position.get("pending_sell_reason")
        if reason != "stop_loss_next_open":
            still_open.append(position)
            continue
        open_price = prices.get((trade_date, position["ts_code"]))
        if open_price is None or not _valid_price(open_price.open):
            stats["missing_price_count"] += 1
            still_open.append(position)
            continue
        if _is_limit_down_open(open_price):
            still_open.append(position)
            continue
        raw_return = (float(open_price.open) - position["buy_price"]) / position["buy_price"] * 100.0
        net_return = _net_return(raw_return, cost)
        profit_amount = _round_money(position["buy_amount"] * net_return / 100.0)
        cash = _round_money(cash + position["buy_amount"] + profit_amount)
        trade = position["trade"]
        trade.sell_date = trade_date
        trade.sell_time = BUY_TIME
        trade.sell_price = float(open_price.open)
        trade.holding_days = _holding_days(trade_dates, position["buy_date"], trade_date)
        trade.return_pct = _round_pct(net_return)
        trade.profit_amount = profit_amount
        trade.sell_reason = reason
        trade.status = "closed"
        closed_returns.append(_round_pct(net_return))
        closed_profit_amounts.append(profit_amount)
    return still_open, cash


def _load_samples_by_date(db: Session, run: T0SimulationBacktestRun) -> Dict[str, List[DefaultAuctionTrainingSample]]:
    query = db.query(DefaultAuctionTrainingSample).filter(
        DefaultAuctionTrainingSample.strategy_version == "default_auction_v2",
        DefaultAuctionTrainingSample.trade_date >= run.start_date,
        DefaultAuctionTrainingSample.trade_date <= run.end_date,
        DefaultAuctionTrainingSample.ts_code.like("%.S_"),
    )
    if run.sample_source != "all":
        query = query.filter(DefaultAuctionTrainingSample.sample_source == run.sample_source)
    rows = query.order_by(DefaultAuctionTrainingSample.trade_date.asc(), DefaultAuctionTrainingSample.ts_code.asc()).all()
    dedup: Dict[tuple, DefaultAuctionTrainingSample] = {}
    for row in rows:
        if row.ts_code.endswith(".BJ"):
            continue
        key = (row.trade_date, row.ts_code)
        if key not in dedup or row.sample_source == "real_selected":
            dedup[key] = row
    grouped: Dict[str, List[DefaultAuctionTrainingSample]] = {}
    for row in dedup.values():
        grouped.setdefault(row.trade_date, []).append(row)
    return grouped


def _load_trade_dates(db: Session, run: T0SimulationBacktestRun) -> List[str]:
    rows = (
        db.query(StockDailyData.trade_date)
        .filter(StockDailyData.trade_date >= run.start_date, StockDailyData.trade_date <= run.end_date)
        .distinct()
        .order_by(StockDailyData.trade_date.asc())
        .all()
    )
    return [row[0] for row in rows]


def _load_prices(db: Session, run: T0SimulationBacktestRun) -> Dict[tuple, StockDailyData]:
    rows = (
        db.query(StockDailyData)
        .filter(StockDailyData.trade_date >= run.start_date, StockDailyData.trade_date <= run.end_date)
        .all()
    )
    return {(row.trade_date, row.ts_code): row for row in rows}


def _predict_candidates(samples, mv, feature_cols, feature_units, stats) -> List[Dict[str, Any]]:
    candidates = []
    for sample in samples:
        features = _json_loads(sample.feature_json, {})
        try:
            prob = lightgbm_service._predict_with_model_path(
                MODEL_NAME,
                mv.model_path,
                feature_cols,
                features,
                feature_units,
            )
        except Exception:
            stats["prediction_failed_count"] += 1
            continue
        if prob is None:
            stats["prediction_failed_count"] += 1
            continue
        candidates.append(
            {
                "trade_date": sample.trade_date,
                "ts_code": sample.ts_code,
                "name": sample.name,
                "prob": float(prob),
                "open_change_pct": features.get("open_change_pct"),
                "is_one_line_limit_up": int(sample.is_t0_one_line_limit_up or 0),
            }
        )
    return sorted(candidates, key=lambda item: item["prob"], reverse=True)


def _filter_by_min_buy_probability(
    candidates: List[Dict[str, Any]],
    run: T0SimulationBacktestRun,
    stats: Dict[str, int],
) -> List[Dict[str, Any]]:
    threshold = float(getattr(run, "min_buy_prob_pct", 50.0) or 0.0)
    eligible = [item for item in candidates if float(item.get("prob") or 0.0) >= threshold]
    skipped = len(candidates) - len(eligible)
    if skipped > 0:
        stats["skipped_buy_count"] += skipped
        stats["skipped_low_prob_count"] += skipped
    return eligible


def _is_below_min_open_change(
    candidate: Dict[str, Any],
    price: Optional[StockDailyData],
    run: T0SimulationBacktestRun,
) -> bool:
    threshold = getattr(run, "min_open_change_pct", -3.0)
    if threshold is None:
        return False
    open_change = _get_open_change_pct(candidate, price)
    return open_change is not None and open_change < float(threshold)


def _is_above_max_open_change(
    candidate: Dict[str, Any],
    price: Optional[StockDailyData],
    run: T0SimulationBacktestRun,
) -> bool:
    threshold = getattr(run, "max_open_change_pct", 7.0)
    if threshold is None:
        return False
    open_change = _get_open_change_pct(candidate, price)
    return open_change is not None and open_change > float(threshold)


def _get_open_change_pct(candidate: Dict[str, Any], price: Optional[StockDailyData]) -> Optional[float]:
    open_change = _optional_float(candidate.get("open_change_pct"))
    if open_change is None and price is not None and _valid_price(price.open) and _valid_price(price.pre_close):
        pre_close = float(price.pre_close)
        if pre_close > 0:
            open_change = (float(price.open) - pre_close) / pre_close * 100.0
    return open_change


def _optional_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _find_model_version(db: Session, version: Optional[str]) -> ModelVersion:
    query = db.query(ModelVersion).filter(ModelVersion.model_name == MODEL_NAME)
    if version:
        query = query.filter(ModelVersion.version == version)
    else:
        query = query.filter(ModelVersion.is_active == 1)
    mv = query.order_by(ModelVersion.id.desc()).first()
    if mv is None:
        raise ValueError(f"模型版本不存在: {MODEL_NAME} {version or 'active'}")
    return mv


def _sell_reason(
    raw_return: float,
    holding_days: int,
    run: T0SimulationBacktestRun,
    close_price: StockDailyData,
    position: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if _is_limit_up_close(close_price):
        return None
    if raw_return <= float(run.stop_loss_pct):
        return "stop_loss"
    highest_profit = raw_return
    if position is not None:
        highest_profit = float(position.get("highest_profit_pct", raw_return))
    high_profit_hold_pct = float(getattr(run, "high_profit_hold_pct", 13.0) or 13.0)
    profit_pullback_pct = float(getattr(run, "profit_pullback_pct", 5.0) or 5.0)
    if highest_profit > high_profit_hold_pct and highest_profit - raw_return >= profit_pullback_pct:
        return "profit_pullback"
    if holding_days >= int(run.max_holding_days):
        if highest_profit > high_profit_hold_pct:
            return None
        return "max_holding_days"
    return None


def _is_one_line_limit_up_candidate(candidate: Dict[str, Any], price: Optional[StockDailyData]) -> bool:
    if int(candidate.get("is_one_line_limit_up") or 0) == 1:
        return True
    if price is None:
        return False
    if not all(_valid_price(getattr(price, key, None)) for key in ("open", "high", "low", "close", "up_limit")):
        return False
    up_limit = float(price.up_limit)
    values = [float(price.open), float(price.high), float(price.low), float(price.close)]
    return all(_price_ge_limit(value, up_limit) for value in values)


def _is_limit_up_close(price: StockDailyData) -> bool:
    if _valid_price(getattr(price, "up_limit", None)):
        return _price_ge_limit(float(price.close), float(price.up_limit))
    pct_chg = getattr(price, "pct_chg", None)
    try:
        return float(pct_chg) >= 9.8
    except (TypeError, ValueError):
        return False


def _is_limit_down_close(price: StockDailyData) -> bool:
    if _valid_price(getattr(price, "down_limit", None)):
        return float(price.close) <= float(price.down_limit) + 0.001
    pct_chg = getattr(price, "pct_chg", None)
    try:
        return float(pct_chg) <= -9.8
    except (TypeError, ValueError):
        return False


def _is_limit_down_open(price: StockDailyData) -> bool:
    if _valid_price(getattr(price, "down_limit", None)):
        return float(price.open) <= float(price.down_limit) + 0.001
    return _is_limit_down_close(price)


def _is_cancel_requested(db: Session, run_id: int) -> bool:
    db.expire_all()
    status = db.query(T0SimulationBacktestRun.status).filter(T0SimulationBacktestRun.id == run_id).scalar()
    return status == "cancel_requested"


def _price_ge_limit(value: float, up_limit: float) -> bool:
    return value >= up_limit - 0.001


def _holding_days(trade_dates: List[str], buy_date: str, trade_date: str) -> int:
    return len([date for date in trade_dates if buy_date <= date <= trade_date])


def _net_return(raw_return: float, cost: Dict[str, Any]) -> float:
    buy_fee = _safe_float(cost.get("buy_fee_pct"))
    sell_fee = _safe_float(cost.get("sell_fee_pct"))
    slippage = _safe_float(cost.get("slippage_pct"))
    return raw_return - buy_fee - sell_fee - slippage * 2


def _build_summary(run, final_equity, positions, closed_returns, closed_profit_amounts, stats, db) -> Dict[str, Any]:
    daily_rows = db.query(T0SimulationBacktestDaily).filter(T0SimulationBacktestDaily.run_id == run.id).all()
    drawdowns = [row.drawdown_pct for row in daily_rows]
    wins = [value for value in closed_returns if value > 0]
    return {
        "initial_cash": _round_money(run.initial_cash),
        "final_equity": _round_money(final_equity),
        "total_return_pct": _round_pct((final_equity - run.initial_cash) / run.initial_cash * 100.0),
        "total_profit_amount": _round_money(final_equity - run.initial_cash),
        "max_drawdown_pct": min(drawdowns) if drawdowns else 0.0,
        "trade_count": len(closed_returns),
        "open_position_count": len(positions),
        "win_rate": _round_rate(len(wins) / len(closed_returns)) if closed_returns else 0.0,
        "avg_trade_return_pct": _round_pct(mean(closed_returns)) if closed_returns else 0.0,
        "best_trade_return_pct": max(closed_returns) if closed_returns else 0.0,
        "worst_trade_return_pct": min(closed_returns) if closed_returns else 0.0,
        "skipped_buy_count": stats["skipped_buy_count"],
        "skipped_low_prob_count": stats.get("skipped_low_prob_count", 0),
        "skipped_low_open_change_count": stats.get("skipped_low_open_change_count", 0),
        "skipped_high_open_change_count": stats.get("skipped_high_open_change_count", 0),
        "skipped_one_line_limit_up_count": stats.get("skipped_one_line_limit_up_count", 0),
        "prediction_failed_count": stats["prediction_failed_count"],
        "missing_price_count": stats["missing_price_count"],
        "closed_profit_amount": _round_money(sum(closed_profit_amounts)),
    }


def _run_payload(run: T0SimulationBacktestRun, db: Optional[Session] = None) -> Dict[str, Any]:
    progress = _progress_payload(db or object_session(run), run)
    return {
        "id": run.id,
        "status": run.status,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "model_name": run.model_name,
        "model_version": run.model_version,
        "resolved_model_version": run.resolved_model_version,
        "sample_source": run.sample_source,
        "initial_cash": run.initial_cash,
        "buy_top_n": run.buy_top_n,
        "max_positions": run.max_positions,
        "min_buy_prob_pct": run.min_buy_prob_pct,
        "min_open_change_pct": run.min_open_change_pct,
        "max_open_change_pct": run.max_open_change_pct,
        "take_profit_pct": run.take_profit_pct,
        "high_profit_hold_pct": run.high_profit_hold_pct,
        "profit_pullback_pct": run.profit_pullback_pct,
        "stop_loss_pct": run.stop_loss_pct,
        "max_holding_days": run.max_holding_days,
        "force_close_on_end": bool(run.force_close_on_end),
        "cost": _json_loads(run.cost_json, {}),
        "summary": _json_loads(run.summary_json, {}),
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        **progress,
    }


def _progress_payload(db: Optional[Session], run: T0SimulationBacktestRun) -> Dict[str, Any]:
    if db is None or run.id is None:
        return {
            "progress": 0.0,
            "processed_trade_days": 0,
            "total_trade_days": 0,
            "processed_trade_date": None,
        }
    processed_trade_days = (
        db.query(T0SimulationBacktestDaily)
        .filter(T0SimulationBacktestDaily.run_id == run.id)
        .count()
    )
    processed_trade_date_row = (
        db.query(T0SimulationBacktestDaily.trade_date)
        .filter(T0SimulationBacktestDaily.run_id == run.id)
        .order_by(T0SimulationBacktestDaily.trade_date.desc())
        .first()
    )
    total_trade_days = (
        db.query(StockDailyData.trade_date)
        .filter(StockDailyData.trade_date >= run.start_date, StockDailyData.trade_date <= run.end_date)
        .distinct()
        .count()
    )
    if total_trade_days <= 0:
        progress = 100.0 if run.status == "passed" else 0.0
    elif run.status == "passed":
        progress = 100.0
    else:
        progress = round(min(processed_trade_days, total_trade_days) / total_trade_days * 100.0, 2)
    return {
        "progress": progress,
        "processed_trade_days": processed_trade_days,
        "total_trade_days": total_trade_days,
        "processed_trade_date": processed_trade_date_row[0] if processed_trade_date_row else None,
    }


def _daily_payload(row: T0SimulationBacktestDaily) -> Dict[str, Any]:
    return {
        "trade_date": row.trade_date,
        "cash": row.cash,
        "market_value": row.market_value,
        "equity": row.equity,
        "daily_return_pct": row.daily_return_pct,
        "drawdown_pct": row.drawdown_pct,
        "position_count": row.position_count,
    }


def _trade_payload(row: T0SimulationBacktestTrade) -> Dict[str, Any]:
    return {
        "trade_id": row.id,
        "ts_code": row.ts_code,
        "name": row.name,
        "model_prob": row.model_prob,
        "rank": row.rank,
        "buy_date": row.buy_date,
        "buy_time": row.buy_time,
        "buy_price": row.buy_price,
        "buy_amount": row.buy_amount,
        "sell_date": row.sell_date,
        "sell_time": row.sell_time,
        "sell_price": row.sell_price,
        "holding_days": row.holding_days,
        "return_pct": row.return_pct,
        "profit_amount": row.profit_amount,
        "sell_reason": row.sell_reason,
        "status": row.status,
    }


def _valid_price(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number > 0


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _round_pct(value: float) -> float:
    return round(float(value), 4)


def _round_rate(value: float) -> float:
    return round(float(value), 4)


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback
