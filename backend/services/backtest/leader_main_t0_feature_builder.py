"""
龙头主升 T+0 候选特征构建。
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from backend.database import SessionLocal
from backend.models import StockFeatureSnapshot
from backend.models.auction_backtest import LeaderMainT0TrainingSample, StockAuctionOpen
from backend.services.data_collector import TushareDataCollector
from backend.services.scoring.rule_score_service import RuleScoreService
from backend.services.backtest.leader_main_t0_label_builder import calculate_limit_up_price

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "max_circ_mv": 2000,
    "max_prev_close": 500,
    "min_rise_10d_pct": 0,
    "min_limit_up_count_100d": 3,
    "min_seal_rate_100d": 80,
    "min_open_change_pct": -3,
    "min_limit_up_streak": None,
    "max_market_height_rank": None,
    "min_turnover_rate": None,
    "min_chinext_turnover_rate": None,
    "require_prev_day_volume_ge_prev2": False,
    "require_ma5_gt_ma10": False,
    "min_sector_change_pct": None,
    "min_sector_limit_up_count": None,
    "min_auction_ratio": 4,
    "max_auction_ratio": 30,
    "min_auction_turnover_rate": 0.5,
    "max_auction_turnover_rate": 10,
}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_auction_ratio_percent(value: Any) -> Optional[float]:
    """Return auction_ratio as percentage points: 8.19 means 8.19%."""
    ratio = _num(value)
    if ratio is None:
        return None
    if 0 < ratio < 1:
        return round(ratio * 100, 4)
    return ratio


def _is_chinext_or_star(ts_code: str) -> bool:
    code = (ts_code or "").split(".")[0]
    return code.startswith(("300", "301", "688", "689"))


def _reject_reasons(feature: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    ts_code = feature.get("ts_code", "")

    checks = [
        (feature.get("is_st"), "ST股票"),
        (feature.get("is_suspended"), "当日停牌或无成交"),
        (feature.get("is_bj"), "北交所股票"),
        (_num(feature.get("circ_mv"), 0) >= config["max_circ_mv"], "流通市值不小于2000亿"),
        (_num(feature.get("prev_close"), 0) >= config["max_prev_close"], "T-1收盘价不小于500"),
        (_num(feature.get("rise_10d_pct"), -999) <= config["min_rise_10d_pct"], "近10日股价未上涨"),
        (_num(feature.get("limit_up_count_100d"), 0) < config["min_limit_up_count_100d"], "100日涨停次数不足"),
    ]
    reasons.extend(reason for failed, reason in checks if failed)

    min_seal_rate = config.get("min_seal_rate_100d")
    if min_seal_rate is not None and _num(feature.get("seal_rate_100d"), -1) < min_seal_rate:
        reasons.append(f"封板率低于{min_seal_rate:g}%")

    min_open_change_pct = config.get("min_open_change_pct")
    open_change_pct = _num(feature.get("open_change_pct"))
    if min_open_change_pct is not None and open_change_pct is not None and open_change_pct < min_open_change_pct:
        reasons.append(f"开盘跌幅低于{min_open_change_pct:g}%")

    min_limit_up_streak = config.get("min_limit_up_streak")
    if min_limit_up_streak is not None and _num(feature.get("limit_up_streak"), 0) < min_limit_up_streak:
        reasons.append("T-1连板高度不足")

    max_market_height_rank = config.get("max_market_height_rank")
    if max_market_height_rank is not None and _num(feature.get("market_height_rank"), 999) > max_market_height_rank:
        reasons.append("市场高度排名不在前10")

    turnover_min = (
        config.get("min_chinext_turnover_rate")
        if _is_chinext_or_star(ts_code)
        else config.get("min_turnover_rate")
    )
    if turnover_min is not None and _num(feature.get("yesterday_turnover_rate"), 0) < turnover_min:
        reasons.append("T-1真实换手不足")

    if config.get("require_prev_day_volume_ge_prev2") and not bool(feature.get("prev_day_volume_ge_prev2")):
        reasons.append("T-1涨停日成交量小于T-2")

    if config.get("require_ma5_gt_ma10") and not bool(feature.get("ma5_gt_ma10")):
        reasons.append("均线趋势不满足MA5>=MA10")

    min_sector_change_pct = config.get("min_sector_change_pct")
    if min_sector_change_pct is not None and _num(feature.get("sector_change_pct"), 0) < min_sector_change_pct:
        reasons.append("板块涨幅不足2%")

    min_sector_limit_up_count = config.get("min_sector_limit_up_count")
    if min_sector_limit_up_count is not None and _num(feature.get("sector_limit_up_count"), 0) < min_sector_limit_up_count:
        reasons.append("板块涨停数不足3")

    auction_ratio = normalize_auction_ratio_percent(feature.get("auction_ratio"))
    if auction_ratio is None or not (config["min_auction_ratio"] <= auction_ratio <= config["max_auction_ratio"]):
        reasons.append("竞昨比不在4%-30%")

    auction_turnover_rate = _num(feature.get("auction_turnover_rate"))
    if auction_turnover_rate is None or not (
        config["min_auction_turnover_rate"]
        <= auction_turnover_rate
        <= config["max_auction_turnover_rate"]
    ):
        reasons.append("竞价换手率不在0.5%-10%")

    return reasons


def filter_leader_main_t0_candidates(
    features: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    candidates: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for feature in features:
        item = dict(feature)
        reasons = _reject_reasons(item, cfg)
        item["filter_reasons"] = reasons
        if reasons:
            item["filter_status"] = "rejected"
            rejected.append(item)
        else:
            item["filter_status"] = "included"
            candidates.append(item)
    return {"candidates": candidates, "rejected": rejected}


class LeaderMainT0FeatureBuilder:
    """构建并保存龙头主升 T+0 候选特征样本。"""

    def __init__(self, collector: Optional[Any] = None, session_factory=SessionLocal):
        self.collector = collector or TushareDataCollector()
        self.session_factory = session_factory
        self._owns_session = session_factory is SessionLocal
        self._daily_history_cache: Dict[str, pd.DataFrame] = {}

    def build_leader_main_t0_features_for_date(self, trade_date: str) -> List[Dict[str, Any]]:
        """
        用已落库竞价数据生成当日候选基础特征。

        特征只使用 T-1 及以前日线/基础指标，以及 T 日集合竞价数据。
        """
        db = self.session_factory()
        try:
            snapshot_features = self._build_features_from_feature_snapshots(db, trade_date)
            if snapshot_features:
                return snapshot_features

            auctions = db.query(StockAuctionOpen).filter(StockAuctionOpen.trade_date == trade_date).all()
            if not auctions:
                return []

            history_days = self._get_history_days(trade_date, 130)
            if not history_days:
                return []
            prev_date = history_days[-1]

            daily_df = self._fetch_daily_history(history_days)
            if daily_df is None or daily_df.empty:
                return []

            trade_daily_df = self.collector.get_daily_data(trade_date=trade_date)
            trade_daily_map = self._map_by_code(trade_daily_df) if trade_daily_df is not None else {}

            prev_basic_df = self.collector.get_daily_basic(trade_date=prev_date)
            stock_basic_df = self.collector.get_stock_basic()
            daily_by_code = self._group_daily(daily_df)
            prev_basic_map = self._map_by_code(prev_basic_df)
            stock_basic_map = self._map_by_code(stock_basic_df)
            streaks = {
                ts_code: self._limit_up_streak(rows)
                for ts_code, rows in daily_by_code.items()
            }
            rank_by_code = self._market_height_rank(streaks)

            features = []
            for auction in auctions:
                rows = daily_by_code.get(auction.ts_code, [])
                if not rows:
                    continue
                prev_row = rows[-1]
                prev2_row = rows[-2] if len(rows) >= 2 else None
                prev_close = _num(prev_row.get("close"))
                basic = prev_basic_map.get(auction.ts_code, {})
                stock_basic = stock_basic_map.get(auction.ts_code, {})
                limit_count_100d = self._limit_up_count(rows[-101:] if len(rows) > 101 else rows)
                seal_rate_100d = self._seal_rate(rows[-101:] if len(rows) > 101 else rows)
                rise_5d_pct = self._rise_pct(rows, 5)
                rise_10d_pct = self._rise_pct(rows, 10)
                ma5 = self._ma(rows, 5)
                ma10 = self._ma(rows, 10)
                trade_daily_row = trade_daily_map.get(auction.ts_code, {})
                daily_open = _num(trade_daily_row.get("open"))
                daily_pre_close = _num(trade_daily_row.get("pre_close"))
                open_change_pct = None
                if daily_open and daily_pre_close and daily_pre_close > 0:
                    open_change_pct = round((daily_open - daily_pre_close) / daily_pre_close * 100, 2)

                auction_vwap_gap_pct = None

                feature = {
                    "trade_date": trade_date,
                    "ts_code": auction.ts_code,
                    "name": stock_basic.get("name"),
                    "is_st": "ST" in str(stock_basic.get("name") or ""),
                    "is_suspended": False,
                    "is_bj": auction.ts_code.endswith(".BJ") or stock_basic.get("market") == "北交所",
                    "circ_mv": round(_num(basic.get("circ_mv"), 0) / 10000, 2) if basic.get("circ_mv") else None,
                    "prev_close": prev_close,
                    "pre_change_pct": _num(prev_row.get("pct_chg")),
                    "open_change_pct": open_change_pct,
                    "auction_ratio": normalize_auction_ratio_percent(auction.auction_ratio),
                    "auction_turnover_rate": auction.auction_turnover_rate,
                    "auction_amount": auction.amount,
                    "auction_volume": auction.vol,
                    "auction_amount_to_circ_mv": self._amount_to_circ_mv(auction.amount, basic.get("circ_mv")),
                    "auction_vwap_gap_pct": auction_vwap_gap_pct,
                    "limit_up_streak": streaks.get(auction.ts_code, 0),
                    "market_height_rank": rank_by_code.get(auction.ts_code, 999),
                    "limit_up_count_100d": limit_count_100d,
                    "seal_rate_100d": seal_rate_100d,
                    "rise_5d_pct": rise_5d_pct,
                    "rise_10d_pct": rise_10d_pct,
                    "yesterday_turnover_rate": _num(basic.get("turnover_rate")),
                    "yesterday_amount": _num(prev_row.get("amount")),
                    "yesterday_volume_ratio": _num(basic.get("volume_ratio")),
                    "ma5_gap_pct": self._gap_pct(prev_close, ma5),
                    "ma10_gap_pct": self._gap_pct(prev_close, ma10),
                    "ma5_gt_ma10": ma5 is not None and ma10 is not None and ma5 >= ma10,
                    "prev_day_volume_ge_prev2": (
                        prev2_row is not None
                        and _num(prev_row.get("vol"), 0) >= _num(prev2_row.get("vol"), 0)
                    ),
                    "sector_change_pct": 0,
                    "sector_limit_up_count": 0,
                    "feature_missing_flags": ["sector_strength"],
                }
                feature["rule_score"] = score_candidate_rule(feature)
                features.append(feature)
            return filter_leader_main_t0_candidates(
                features,
                {
                    "min_sector_change_pct": 0,
                    "min_sector_limit_up_count": 0,
                },
            )["candidates"]
        finally:
            if self._owns_session:
                db.close()

    def _build_features_from_feature_snapshots(self, db, trade_date: str) -> List[Dict[str, Any]]:
        snapshots = (
            db.query(StockFeatureSnapshot)
            .filter(StockFeatureSnapshot.trade_date == trade_date)
            .order_by(StockFeatureSnapshot.id.asc())
            .all()
        )
        if not snapshots:
            return []

        features = [self._feature_from_snapshot(row) for row in snapshots]
        return filter_leader_main_t0_candidates(features)["candidates"]

    @staticmethod
    def _feature_from_snapshot(row: StockFeatureSnapshot) -> Dict[str, Any]:
        feature = {
            "trade_date": row.trade_date,
            "ts_code": row.ts_code,
            "name": row.name,
            "source": "stock_feature_snapshot",
            "is_st": "ST" in str(row.name or ""),
            "is_suspended": False,
            "is_bj": (row.ts_code or "").endswith(".BJ"),
            "circ_mv": row.circ_mv,
            "prev_close": None,
            "pre_change_pct": row.pre_change_pct,
            "open_change_pct": row.open_change_pct,
            "auction_ratio": normalize_auction_ratio_percent(row.auction_ratio),
            "auction_turnover_rate": row.auction_turnover_rate,
            "auction_amount": None,
            "auction_volume": row.auction_volume,
            "auction_amount_to_circ_mv": None,
            "auction_vwap_gap_pct": None,
            "limit_up_streak": None,
            "market_height_rank": None,
            "limit_up_count_100d": row.limit_up_count_100d,
            "seal_rate_100d": row.seal_rate_100d,
            "rise_5d_pct": None,
            "rise_10d_pct": row.rise_10d_pct,
            "yesterday_turnover_rate": None,
            "yesterday_amount": None,
            "yesterday_volume_ratio": None,
            "ma5_gap_pct": None,
            "ma10_gap_pct": None,
            "ma5_gt_ma10": None,
            "prev_day_volume_ge_prev2": None,
            "sector_change_pct": row.sector_avg_pct,
            "sector_limit_up_count": None,
            "feature_missing_flags": ["snapshot_optional_fields"],
        }
        feature["rule_score"] = score_candidate_rule(feature)
        return feature

    def save_training_samples(self, trade_date: str, features: List[Dict[str, Any]]) -> int:
        db = self.session_factory()
        saved = 0
        try:
            feature_codes = {
                feature.get("ts_code")
                for feature in features
                if feature.get("ts_code")
            }
            sync_snapshot_source = bool(feature_codes) and all(
                feature.get("source") == "stock_feature_snapshot"
                for feature in features
            )

            for feature in features:
                feature = dict(feature)
                feature["auction_ratio"] = normalize_auction_ratio_percent(feature.get("auction_ratio"))
                ts_code = feature.get("ts_code")
                if not ts_code:
                    continue
                existing = db.query(LeaderMainT0TrainingSample).filter(
                    LeaderMainT0TrainingSample.trade_date == trade_date,
                    LeaderMainT0TrainingSample.ts_code == ts_code,
                ).first()
                if existing is None:
                    existing = LeaderMainT0TrainingSample(
                        strategy_version="leader_main_t0",
                        trade_date=trade_date,
                        ts_code=ts_code,
                    )
                    db.add(existing)

                self._apply_feature(existing, feature)
                existing.feature_json = json.dumps(feature, ensure_ascii=False)
                existing.updated_at = datetime.now()
                saved += 1

            if sync_snapshot_source:
                db.query(LeaderMainT0TrainingSample).filter(
                    LeaderMainT0TrainingSample.trade_date == trade_date,
                    LeaderMainT0TrainingSample.strategy_version == "leader_main_t0",
                    LeaderMainT0TrainingSample.ts_code.notin_(feature_codes),
                ).delete(synchronize_session=False)
            db.commit()
            return saved
        except Exception:
            db.rollback()
            logger.exception(f"保存 {trade_date} 龙头主升T+0样本失败")
            return 0
        finally:
            if self._owns_session:
                db.close()

    def build_leader_main_t0_range(self, trade_dates: Iterable[str]) -> int:
        saved = 0
        for trade_date in trade_dates:
            features = self.build_leader_main_t0_features_for_date(trade_date)
            saved += self.save_training_samples(trade_date, features)
        return saved

    @staticmethod
    def _apply_feature(sample: LeaderMainT0TrainingSample, feature: Dict[str, Any]) -> None:
        sample.name = feature.get("name")
        sample.limit_up_streak = feature.get("limit_up_streak")
        sample.market_height_rank = feature.get("market_height_rank")
        sample.limit_up_count_100d = feature.get("limit_up_count_100d")
        sample.seal_rate_100d = feature.get("seal_rate_100d")
        sample.rise_5d_pct = feature.get("rise_5d_pct")
        sample.rise_10d_pct = feature.get("rise_10d_pct")
        sample.pre_change_pct = feature.get("pre_change_pct")
        sample.open_change_pct = feature.get("open_change_pct")
        sample.auction_ratio = normalize_auction_ratio_percent(feature.get("auction_ratio"))
        sample.auction_turnover_rate = feature.get("auction_turnover_rate")
        sample.auction_amount = feature.get("auction_amount")
        sample.auction_vwap_gap_pct = feature.get("auction_vwap_gap_pct")
        sample.circ_mv = feature.get("circ_mv")
        sample.sector_change_pct = feature.get("sector_change_pct")
        sample.sector_limit_up_count = feature.get("sector_limit_up_count")
        sample.sector_hot_rank = feature.get("sector_hot_rank")
        sample.rule_score = feature.get("rule_score")

    @staticmethod
    def _map_by_code(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        if df is None or df.empty or "ts_code" not in df.columns:
            return {}
        return {row["ts_code"]: row for row in df.to_dict("records") if row.get("ts_code")}

    def _fetch_daily_history(self, trade_dates: List[str]) -> pd.DataFrame:
        frames = []
        for trade_date in sorted(trade_dates):
            if trade_date not in self._daily_history_cache:
                df = self.collector.get_daily_data(trade_date=trade_date)
                self._daily_history_cache[trade_date] = df if df is not None else pd.DataFrame()
            df = self._daily_history_cache[trade_date]
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _get_history_days(self, trade_date: str, count: int) -> List[str]:
        year = int(trade_date[:4])
        calendar = set()
        for y in (year - 1, year):
            try:
                calendar.update(self.collector.get_trading_calendar(y))
            except TypeError:
                calendar.update(self.collector.get_trading_calendar())
        return sorted(d for d in calendar if d < trade_date)[-count:]

    @staticmethod
    def _group_daily(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        if df is None or df.empty:
            return {}
        data: Dict[str, List[Dict[str, Any]]] = {}
        for row in df.sort_values(["ts_code", "trade_date"]).to_dict("records"):
            data.setdefault(row["ts_code"], []).append(row)
        return data

    @staticmethod
    def _is_limit_up(ts_code: str, row: Dict[str, Any]) -> bool:
        pre_close = _num(row.get("pre_close"))
        close = _num(row.get("close"))
        if not pre_close or pre_close <= 0 or close is None:
            return False
        return close >= calculate_limit_up_price(ts_code, pre_close) * 0.997

    def _limit_up_count(self, rows: List[Dict[str, Any]]) -> int:
        return sum(1 for row in rows if self._is_limit_up(row.get("ts_code", ""), row))

    def _touch_limit_count(self, rows: List[Dict[str, Any]]) -> int:
        return sum(1 for row in rows if self._is_touch_limit(row.get("ts_code", ""), row))

    def _seal_rate(self, rows: List[Dict[str, Any]]) -> Optional[float]:
        touch_count = self._touch_limit_count(rows)
        if touch_count <= 0:
            return None
        return round(self._limit_up_count(rows) / touch_count * 100, 2)

    def _limit_up_streak(self, rows: List[Dict[str, Any]]) -> int:
        streak = 0
        for row in reversed(rows):
            if self._is_limit_up(row.get("ts_code", ""), row):
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _is_touch_limit(ts_code: str, row: Dict[str, Any]) -> bool:
        pre_close = _num(row.get("pre_close"))
        high = _num(row.get("high"))
        if not pre_close or pre_close <= 0 or high is None:
            return False
        return high >= calculate_limit_up_price(ts_code, pre_close) * 0.997

    @staticmethod
    def _market_height_rank(streaks: Dict[str, int]) -> Dict[str, int]:
        ordered = sorted(
            ((ts_code, streak) for ts_code, streak in streaks.items() if streak > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        return {ts_code: rank + 1 for rank, (ts_code, _) in enumerate(ordered)}

    @staticmethod
    def _rise_pct(rows: List[Dict[str, Any]], days: int) -> Optional[float]:
        if len(rows) <= days:
            return None
        current = _num(rows[-1].get("close"))
        base = _num(rows[-days - 1].get("close"))
        if not current or not base:
            return None
        return round((current - base) / base * 100, 2)

    @staticmethod
    def _ma(rows: List[Dict[str, Any]], days: int) -> Optional[float]:
        if len(rows) < days:
            return None
        closes = [_num(row.get("close")) for row in rows[-days:]]
        if any(value is None for value in closes):
            return None
        return sum(closes) / days

    @staticmethod
    def _gap_pct(price: Optional[float], ma: Optional[float]) -> Optional[float]:
        if price is None or ma is None or ma == 0:
            return None
        return round((price - ma) / ma * 100, 2)

    @staticmethod
    def _amount_to_circ_mv(amount: Optional[float], circ_mv: Any) -> Optional[float]:
        circ_mv_f = _num(circ_mv)
        amount_f = _num(amount)
        if not amount_f or not circ_mv_f:
            return None
        return round(amount_f / (circ_mv_f * 10000), 6)


def score_candidate_rule(feature: Dict[str, Any]) -> float:
    """复用现有规则评分服务，供回测输出排序用。"""
    result = RuleScoreService.calculate(
        limit_up_count=feature.get("limit_up_count_100d"),
        seal_rate=feature.get("seal_rate_100d"),
        rise_10d_pct=feature.get("rise_10d_pct"),
        pre_change_pct=feature.get("pre_change_pct"),
        open_change_pct=feature.get("open_change_pct"),
        auction_ratio=normalize_auction_ratio_percent(feature.get("auction_ratio")),
        auction_turnover_rate=feature.get("auction_turnover_rate"),
        circ_mv=feature.get("circ_mv"),
    )
    return result.get("rule_score", 0)
