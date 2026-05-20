"""
默认竞价接力 T1 溢价模型诊断。
"""
import json
import math
import os
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine.default_auction_model_trainer import (
    _build_dataframe,
    _query_samples,
    _records_to_rows,
)
from backend.services.model_engine.lightgbm_service import _get_joblib


MODEL_NAME = "default_auction_t1_premium_lgbm"
LABEL_COLUMN = "label_t1_premium_success"
COMPRESSED_PROBABILITY_SPREAD_THRESHOLD = 5.0


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _round(value: Optional[float]) -> Optional[float]:
    return round(float(value), 4) if value is not None else None


def describe_numeric(values: Iterable[Any]) -> Optional[Dict[str, Any]]:
    valid = [_safe_float(value) for value in values]
    numbers = [float(value) for value in valid if value is not None]
    if not numbers:
        return None
    return {
        "count": len(numbers),
        "min": _round(min(numbers)),
        "p10": _round(_percentile(numbers, 10)),
        "p25": _round(_percentile(numbers, 25)),
        "avg": _round(mean(numbers)),
        "p50": _round(_percentile(numbers, 50)),
        "p75": _round(_percentile(numbers, 75)),
        "p90": _round(_percentile(numbers, 90)),
        "max": _round(max(numbers)),
    }


def _label_distribution(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    labels = [int(row["label"]) for row in rows if row.get("label") is not None]
    positive = sum(labels)
    total = len(labels)
    return {
        "total": total,
        "positive": positive,
        "negative": total - positive,
        "positive_rate": _round(positive / total) if total else None,
    }


def _label_distribution_by_source(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for source in sorted({row.get("sample_source") or "" for row in rows}):
        source_rows = [row for row in rows if (row.get("sample_source") or "") == source]
        result[source or "unknown"] = _label_distribution(source_rows)
    return result


def build_prediction_bucket_summary(
    probabilities: Iterable[Any],
    labels: Iterable[Any],
    bucket_count: int = 5,
) -> Dict[str, Any]:
    pairs = [
        (float(probability), int(label))
        for probability, label in zip(probabilities, labels)
        if _safe_float(probability) is not None and label is not None
    ]
    if not pairs:
        return {
            "baseline_rate": None,
            "probability_spread": None,
            "buckets": [],
        }
    pairs.sort(key=lambda item: item[0])
    baseline = sum(label for _probability, label in pairs) / len(pairs)
    bucket_count = max(1, min(bucket_count, len(pairs)))
    buckets = []
    for index in range(bucket_count):
        start = math.floor(index * len(pairs) / bucket_count)
        end = math.floor((index + 1) * len(pairs) / bucket_count)
        part = pairs[start:end]
        if not part:
            continue
        probabilities_part = [probability for probability, _label in part]
        labels_part = [label for _probability, label in part]
        hit_rate = sum(labels_part) / len(labels_part)
        buckets.append(
            {
                "bucket": f"bottom_{index + 1}" if index < bucket_count - 1 else "top_1",
                "count": len(part),
                "prob_min": _round(min(probabilities_part)),
                "prob_max": _round(max(probabilities_part)),
                "prob_avg": _round(mean(probabilities_part)),
                "hit_rate": _round(hit_rate),
                "lift": _round(hit_rate - baseline),
            }
        )
    probabilities_all = [probability for probability, _label in pairs]
    return {
        "baseline_rate": _round(baseline),
        "probability_spread": _round(max(probabilities_all) - min(probabilities_all)),
        "buckets": buckets,
    }


def _active_model_payload(db: Session) -> Dict[str, Any]:
    version = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_name == MODEL_NAME, ModelVersion.is_active == 1)
        .order_by(ModelVersion.id.desc())
        .first()
    )
    if version is None:
        return {"exists": False}
    return {
        "exists": True,
        "version": version.version,
        "train_start_date": version.train_start_date,
        "train_end_date": version.train_end_date,
        "model_path": version.model_path,
        "model_file_exists": bool(version.model_path and os.path.exists(version.model_path)),
        "feature_cols": _load_json(version.feature_cols, []),
        "metrics": _load_json(version.model_metrics, {}),
        "params": _load_json(version.params, {}),
    }


def _load_json(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except Exception:
        return fallback
    return parsed if parsed is not None else fallback


def _predict_active_model(active_model: Dict[str, Any], rows: List[Dict[str, Any]]) -> Optional[List[float]]:
    if not active_model.get("model_file_exists"):
        return None
    feature_cols = active_model.get("feature_cols") or []
    if not feature_cols:
        return None
    model_path = active_model.get("model_path")
    if not model_path:
        return None
    joblib = _get_joblib()
    model = joblib.load(model_path)
    dataframe = _build_dataframe(rows, feature_cols)
    probabilities = model.predict_proba(dataframe[feature_cols].fillna(0.0))[:, 1] * 100
    return [float(value) for value in probabilities]


def _return_distribution_by_label(db: Session) -> Dict[str, Any]:
    records = db.query(DefaultAuctionTrainingSample).filter(
        DefaultAuctionTrainingSample.label_t1_premium_success.isnot(None)
    ).all()
    result: Dict[str, Any] = {}
    for label in (0, 1):
        subset = [record for record in records if int(record.label_t1_premium_success) == label]
        result[str(label)] = {
            "count": len(subset),
            "t1_open_return": describe_numeric(record.t1_open_return for record in subset),
            "t1_high_return": describe_numeric(record.t1_high_return for record in subset),
            "t1_close_return": describe_numeric(record.t1_close_return for record in subset),
        }
    return result


def _build_findings(
    active_model: Dict[str, Any],
    rows: List[Dict[str, Any]],
    prediction_diagnostics: Optional[Dict[str, Any]],
) -> List[str]:
    findings = []
    active_sample_count = (active_model.get("metrics") or {}).get("sample_count")
    active_acceptance = ((active_model.get("metrics") or {}).get("acceptance") or {})
    current_start = rows[0]["trade_date"] if rows else None
    train_start = active_model.get("train_start_date")
    if active_sample_count is not None and len(rows) > int(active_sample_count) * 1.5:
        if (
            active_acceptance.get("accepted") is True
            and train_start is not None
            and current_start is not None
            and str(train_start) > str(current_start)
        ):
            findings.append("active_model_uses_recent_rolling_window")
        else:
            findings.append("active_model_trained_on_stale_smaller_sample_set")
    spread = None
    if prediction_diagnostics:
        spread = (prediction_diagnostics.get("bucket_summary") or {}).get("probability_spread")
    if spread is not None and spread < COMPRESSED_PROBABILITY_SPREAD_THRESHOLD:
        findings.append("active_probability_spread_too_narrow")
    distribution = _label_distribution(rows)
    positive_rate = distribution.get("positive_rate")
    if positive_rate is not None and 0.45 <= positive_rate <= 0.55:
        findings.append("t1_premium_label_is_balanced_not_imbalanced")
    return findings


def diagnose_t1_premium_model(
    db: Session,
    prediction_probabilities: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    records = _query_samples(db, LABEL_COLUMN, None, None)
    rows = _records_to_rows(records, LABEL_COLUMN)
    active_model = _active_model_payload(db)
    labels = [int(row["label"]) for row in rows if row.get("label") is not None]

    probabilities = (
        [float(value) for value in prediction_probabilities]
        if prediction_probabilities is not None
        else _predict_active_model(active_model, rows)
    )
    prediction_diagnostics = None
    if probabilities is not None:
        prediction_diagnostics = {
            "distribution": describe_numeric(probabilities),
            "bucket_summary": build_prediction_bucket_summary(probabilities, labels),
        }

    result = {
        "target": MODEL_NAME,
        "label_column": LABEL_COLUMN,
        "label_rule": "T+1 open>=3% OR high>=5% OR close>=3%",
        "active_model": active_model,
        "current_samples": {
            "raw_count": len(records),
            "dedup_count": len(rows),
            "date_range": [
                rows[0]["trade_date"] if rows else None,
                rows[-1]["trade_date"] if rows else None,
            ],
        },
        "label_distribution": _label_distribution(rows),
        "label_distribution_by_source": _label_distribution_by_source(rows),
        "return_distribution_by_label": _return_distribution_by_label(db),
        "prediction_diagnostics": prediction_diagnostics,
    }
    result["findings"] = _build_findings(active_model, rows, prediction_diagnostics)
    result["recommendations"] = _recommendations(result["findings"])
    return result


def _recommendations(findings: List[str]) -> List[str]:
    recommendations = []
    if "active_model_trained_on_stale_smaller_sample_set" in findings:
        recommendations.append("用当前补全后的 default_auction_training_sample 重新训练 T1 溢价模型")
    if "active_probability_spread_too_narrow" in findings:
        recommendations.append("重训后必须验收概率分层，不只验收 AUC；若概率仍压缩，增加校准或改为展示排序分")
    if "t1_premium_label_is_balanced_not_imbalanced" in findings:
        recommendations.append("不要把问题归因于正负样本不均衡，优先检查标签口径和特征解释力")
    return recommendations
