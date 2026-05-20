"""
默认竞价接力 V2 训练数据完整性审计。

只读检查，不构建样本、不训练模型、不修改数据库。
"""
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import DefaultAuctionTrainingSample, ModelTrainingJob
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.model_engine.replay_validation_service import validate_replay_against_real
from backend.services.tdx_local_selector import is_common_a_share_ts_code


REQUIRED_DEFAULT_AUCTION_FEATURES = (
    "auction_ratio",
    "auction_turnover_rate",
    "open_change_pct",
    "limit_up_count",
    "touch_days",
    "limit_up_days",
    "seal_rate",
    "rise_10d_pct",
)

TARGET_LABELS = (
    "label_t0_limit_success",
    "label_t1_premium_success",
    "label_t1_continue_limit",
)


@dataclass
class TrainingDataAuditConfig:
    strategy_version: str = "default_auction_v2"
    recent_real_days: int = 5
    min_replay_days: int = 60
    min_replay_samples: int = 300
    max_replay_avg_per_day: float = 15.0
    max_replay_daily_count: int = 40
    require_replay_validation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _round(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _sample_summary(samples: List[DefaultAuctionTrainingSample]) -> Dict[str, Any]:
    by_source: Dict[str, Dict[str, Any]] = {}
    source_dates: Dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        bucket = by_source.setdefault(
            sample.sample_source,
            {
                "count": 0,
                "distinct_trade_dates": 0,
                "min_trade_date": None,
                "max_trade_date": None,
            },
        )
        bucket["count"] += 1
        source_dates[sample.sample_source].add(sample.trade_date)
        bucket["min_trade_date"] = (
            sample.trade_date
            if bucket["min_trade_date"] is None
            else min(bucket["min_trade_date"], sample.trade_date)
        )
        bucket["max_trade_date"] = (
            sample.trade_date
            if bucket["max_trade_date"] is None
            else max(bucket["max_trade_date"], sample.trade_date)
        )
    for source, dates in source_dates.items():
        by_source[source]["distinct_trade_dates"] = len(dates)
    return {
        "total_count": len(samples),
        "by_source": by_source,
    }


def _daily_stats(samples: Iterable[DefaultAuctionTrainingSample], source: str) -> Dict[str, Any]:
    counts = Counter(sample.trade_date for sample in samples if sample.sample_source == source)
    values = list(counts.values())
    if not values:
        return {
            "trade_date_count": 0,
            "avg_count": 0,
            "max_count": 0,
            "min_count": 0,
            "top_dates": [],
        }
    return {
        "trade_date_count": len(values),
        "avg_count": _round(sum(values) / len(values)),
        "max_count": max(values),
        "min_count": min(values),
        "top_dates": [
            {"trade_date": trade_date, "count": count}
            for trade_date, count in counts.most_common(10)
        ],
    }


def _feature_missing_counts(samples: Iterable[DefaultAuctionTrainingSample]) -> Dict[str, int]:
    missing = {feature: 0 for feature in REQUIRED_DEFAULT_AUCTION_FEATURES}
    for sample in samples:
        features = _load_json(sample.feature_json, {})
        for feature in REQUIRED_DEFAULT_AUCTION_FEATURES:
            if _is_missing(features.get(feature)):
                missing[feature] += 1
    return missing


def _label_coverage(samples: List[DefaultAuctionTrainingSample]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    total = len(samples)
    for label in TARGET_LABELS:
        missing = sum(1 for sample in samples if getattr(sample, label, None) is None)
        positive = sum(1 for sample in samples if getattr(sample, label, None) == 1)
        known = total - missing
        result[label] = {
            "known_count": known,
            "missing_count": missing,
            "positive_count": positive,
            "positive_rate": _round(positive / known) if known else None,
        }
    return result


def _code_quality(samples: Iterable[DefaultAuctionTrainingSample]) -> Dict[str, Any]:
    seen = sorted({sample.ts_code for sample in samples if sample.ts_code})
    non_a_share = [code for code in seen if not is_common_a_share_ts_code(code)]
    return {
        "distinct_codes": len(seen),
        "non_a_share_codes": non_a_share[:50],
        "non_a_share_count": len(non_a_share),
    }


def _duplicate_keys(db: Session, strategy_version: str) -> List[Dict[str, Any]]:
    rows = (
        db.query(
            DefaultAuctionTrainingSample.strategy_version,
            DefaultAuctionTrainingSample.trade_date,
            DefaultAuctionTrainingSample.ts_code,
            DefaultAuctionTrainingSample.sample_source,
            func.count(DefaultAuctionTrainingSample.id).label("count"),
        )
        .filter(DefaultAuctionTrainingSample.strategy_version == strategy_version)
        .group_by(
            DefaultAuctionTrainingSample.strategy_version,
            DefaultAuctionTrainingSample.trade_date,
            DefaultAuctionTrainingSample.ts_code,
            DefaultAuctionTrainingSample.sample_source,
        )
        .having(func.count(DefaultAuctionTrainingSample.id) > 1)
        .all()
    )
    return [
        {
            "strategy_version": row.strategy_version,
            "trade_date": row.trade_date,
            "ts_code": row.ts_code,
            "sample_source": row.sample_source,
            "count": row.count,
        }
        for row in rows
    ]


def _cross_source_duplicate_keys(samples: Iterable[DefaultAuctionTrainingSample]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str, str], set[str]] = defaultdict(set)
    counts: Counter[tuple[str, str, str]] = Counter()
    for sample in samples:
        key = (sample.strategy_version, sample.trade_date, sample.ts_code)
        grouped[key].add(sample.sample_source)
        counts[key] += 1
    result = []
    for key, sources in sorted(grouped.items()):
        if len(sources) <= 1:
            continue
        strategy_version, trade_date, ts_code = key
        result.append(
            {
                "strategy_version": strategy_version,
                "trade_date": trade_date,
                "ts_code": ts_code,
                "sample_sources": sorted(sources),
                "count": counts[key],
            }
        )
    return result


def _replay_validation(db: Session, config: TrainingDataAuditConfig) -> Dict[str, Any]:
    if not config.require_replay_validation:
        return {
            "checked": False,
            "accepted": None,
            "reason": "disabled_by_config",
        }

    service = DefaultAuctionReplayService(db)
    days = []
    for item in service.get_recent_real_selection_days(limit=config.recent_real_days):
        replay = service.replay_trade_date(item["trade_date"])
        days.append({**item, "replay_codes": replay.get("replay_codes") or []})

    if not days:
        return {
            "checked": True,
            "accepted": False,
            "reject_reasons": ["no_recent_real_selection_days"],
            "daily": [],
        }

    validation = validate_replay_against_real(days)
    validation["checked"] = True
    return validation


def _latest_training_job(db: Session) -> Dict[str, Any]:
    job = (
        db.query(ModelTrainingJob)
        .filter(ModelTrainingJob.model_name == "default_auction_relay_v2")
        .order_by(ModelTrainingJob.id.desc())
        .first()
    )
    if job is None:
        return {"exists": False}
    acceptance = _load_json(job.acceptance_json, {})
    return {
        "exists": True,
        "id": job.id,
        "status": job.status,
        "phase": job.phase,
        "error_message": job.error_message,
        "acceptance": acceptance,
    }


def audit_default_auction_training_data(
    db: Session,
    config: TrainingDataAuditConfig | None = None,
) -> Dict[str, Any]:
    config = config or TrainingDataAuditConfig()
    samples = (
        db.query(DefaultAuctionTrainingSample)
        .filter(DefaultAuctionTrainingSample.strategy_version == config.strategy_version)
        .order_by(DefaultAuctionTrainingSample.trade_date.asc(), DefaultAuctionTrainingSample.id.asc())
        .all()
    )
    errors: List[str] = []
    warnings: List[str] = []

    summary = _sample_summary(samples)
    replay_stats = _daily_stats(samples, "replay_backtest")
    feature_missing = _feature_missing_counts(samples)
    label_coverage = _label_coverage(samples)
    code_quality = _code_quality(samples)
    duplicates = _duplicate_keys(db, config.strategy_version)
    cross_source_duplicates = _cross_source_duplicate_keys(samples)
    replay_validation = _replay_validation(db, config)
    latest_job = _latest_training_job(db)

    replay_source = summary["by_source"].get("replay_backtest", {})
    if replay_source.get("count", 0) < config.min_replay_samples:
        errors.append("replay_sample_count_below_threshold")
    if replay_source.get("distinct_trade_dates", 0) < config.min_replay_days:
        errors.append("replay_trade_date_count_below_threshold")
    if replay_stats["avg_count"] > config.max_replay_avg_per_day:
        errors.append("replay_avg_count_above_threshold")
    if replay_stats["max_count"] > config.max_replay_daily_count:
        errors.append("replay_daily_count_above_threshold")
    if any(count > 0 for count in feature_missing.values()):
        errors.append("required_feature_missing")
    if code_quality["non_a_share_count"] > 0:
        errors.append("non_a_share_sample_detected")
    if duplicates:
        errors.append("duplicate_training_sample_keys")
    if cross_source_duplicates:
        warnings.append("cross_source_duplicate_date_code")
    if replay_validation.get("checked") and not replay_validation.get("accepted"):
        errors.append("replay_validation_failed")
    if not latest_job.get("exists"):
        warnings.append("default_auction_relay_training_job_missing")
    elif latest_job.get("status") != "passed":
        warnings.append("latest_training_job_not_passed")

    return {
        "ok": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "config": config.to_dict(),
        "sample_summary": summary,
        "replay_daily_stats": replay_stats,
        "feature_missing_counts": feature_missing,
        "label_coverage": label_coverage,
        "code_quality": code_quality,
        "duplicate_keys": duplicates,
        "cross_source_duplicate_keys": cross_source_duplicates,
        "replay_validation": replay_validation,
        "latest_training_job": latest_job,
    }
