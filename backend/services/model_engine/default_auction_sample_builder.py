"""
默认竞价接力 V2 训练样本构建。

只复用 SelectionRecord + SelectedStock 的结构化字段，不引入新闻、公告、
舆情或 AI 文本特征，避免标签和文本信息反哺模型。
"""
import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.models import DefaultAuctionTrainingSample, SelectionRecord, SelectedStock


FEATURE_FIELDS = (
    "auction_ratio",
    "auction_turnover_rate",
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


def _build_feature_json(stock: SelectedStock) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    for field in FEATURE_FIELDS:
        value = getattr(stock, field, None)
        features[field] = _json_safe(value)
    features["risk_tags_count"] = _risk_tags_count(getattr(stock, "risk_tags", None))
    return features


def _dump_json(value: Dict[str, Any]) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False, default=str)


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
        result = {"created_count": 0, "updated_count": 0, "skipped_count": 0}
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

            features = _build_feature_json(stock)
            existing.name = stock.name
            existing.strategy_name = "default"
            existing.auction_source = "selected_stock"
            existing.auction_ratio_unit = "percent"
            existing.auction_turnover_rate_basis = "free_float"
            existing.feature_snapshot_time = (
                record.execute_time.isoformat(timespec="seconds")
                if getattr(record, "execute_time", None)
                else None
            )
            existing.feature_json = _dump_json(features)

        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
