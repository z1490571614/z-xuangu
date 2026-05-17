"""
默认竞价接力模型特征质量和训练归因。
"""
from math import isfinite
from typing import Any, Dict, List, Optional


CATEGORICAL_FEATURES = {"score_level", "lu_tag", "lu_status"}
RESERVED_KEYS = {
    "trade_date",
    "ts_code",
    "name",
    "label",
    "prob",
    "prediction",
    "sample_source",
    "strategy_name",
    "strategy_version",
}

BUCKETS = {
    "auction_ratio": [(0, 8, "<8"), (8, 15, "8-15"), (15, 30, "15-30"), (30, None, "30+")],
    "auction_turnover_rate": [(0.5, 1, "0.5-1"), (1, 3, "1-3"), (3, 5, "3-5"), (5, 10, "5-10"), (10, None, "10+")],
    "open_change_pct": [(None, -3, "<-3"), (-3, 0, "-3-0"), (0, 3, "0-3"), (3, 7, "3-7"), (7, None, "7+")],
    "seal_rate": [(None, 60, "<60"), (60, 80, "60-80"), (80, 90, "80-90"), (90, None, "90+")],
    "rise_10d_pct": [(None, 0, "<0"), (0, 10, "0-10"), (10, 30, "10-30"), (30, None, "30+")],
    "health_score": [(None, 50, "<50"), (50, 65, "50-65"), (65, 80, "65-80"), (80, None, "80+")],
}

REJECT_REASON_TEXT = {
    "top3_lift_below_threshold": "Top3提升不足",
    "top5_lift_below_threshold": "Top5提升不足",
    "topk_positive_count_below_threshold": "TopK正例数不足",
    "auc_below_threshold": "AUC低于验收线",
}


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _safe_float(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _label_value(value: Any) -> Optional[int]:
    number = _safe_float(value)
    if number is None:
        return None
    return 1 if number > 0 else 0


def _round_rate(value: float) -> float:
    return round(float(value), 4)


def _auto_feature_names(rows: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key in seen or key in RESERVED_KEYS:
                continue
            seen.add(key)
            names.append(key)
    return names


def _categorical_stats(rows: List[Dict[str, Any]], feature_name: str) -> Dict[str, Any]:
    total = len(rows)
    values = [row.get(feature_name) for row in rows]
    missing_count = sum(1 for value in values if _is_missing(value))
    non_missing = [str(value) for value in values if not _is_missing(value)]
    return {
        "type": "categorical",
        "status": "ignored",
        "reason": "categorical",
        "missing_count": missing_count,
        "missing_rate": _round_rate(missing_count / total) if total else 1.0,
        "unique_count": len(set(non_missing)),
    }


def build_feature_quality_report(
    rows: List[Dict[str, Any]],
    feature_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    rows = rows or []
    feature_names = feature_names if feature_names is not None else _auto_feature_names(rows)
    features: Dict[str, Dict[str, Any]] = {}
    usable_features: List[str] = []
    dropped_features: List[str] = []
    ignored_features: List[str] = []
    total = len(rows)

    for feature_name in feature_names:
        if feature_name in CATEGORICAL_FEATURES:
            features[feature_name] = _categorical_stats(rows, feature_name)
            ignored_features.append(feature_name)
            continue

        values = [row.get(feature_name) for row in rows]
        missing_count = sum(1 for value in values if _is_missing(value))
        numbers = [_safe_float(value) for value in values]
        valid_numbers = [number for number in numbers if number is not None]
        invalid_count = sum(
            1
            for value, number in zip(values, numbers)
            if not _is_missing(value) and number is None
        )
        zero_count = sum(1 for number in valid_numbers if number == 0)
        unique_count = len(set(valid_numbers))
        unavailable_count = missing_count + invalid_count
        missing_rate = _round_rate(unavailable_count / total) if total else 1.0
        zero_rate = _round_rate(zero_count / len(valid_numbers)) if valid_numbers else 1.0

        reason = ""
        if total == 0:
            reason = "no_samples"
        elif not valid_numbers:
            reason = "high_missing"
        elif unique_count <= 1:
            reason = "constant"
        elif missing_rate >= 0.6:
            reason = "high_missing"

        should_drop = bool(reason)
        if should_drop:
            dropped_features.append(feature_name)
        else:
            usable_features.append(feature_name)

        features[feature_name] = {
            "type": "numeric",
            "status": "dropped" if should_drop else "usable",
            "reason": reason,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "valid_count": len(valid_numbers),
            "missing_rate": missing_rate,
            "zero_rate": zero_rate,
            "unique_count": unique_count,
            "min": min(valid_numbers) if valid_numbers else None,
            "max": max(valid_numbers) if valid_numbers else None,
        }

    return {
        "sample_count": total,
        "features": features,
        "usable_features": usable_features,
        "dropped_features": dropped_features,
        "ignored_features": ignored_features,
    }


def _bucket_name(feature_name: str, value: Any) -> Optional[str]:
    number = _safe_float(value)
    if number is None:
        return None
    for lower, upper, name in BUCKETS.get(feature_name, []):
        lower_ok = lower is None or number >= lower
        upper_ok = upper is None or number < upper
        if lower_ok and upper_ok:
            return name
    return None


def build_bucket_report(
    rows: List[Dict[str, Any]],
    feature_names: Optional[List[str]] = None,
    label_key: str = "label",
    prob_key: str = "prob",
) -> List[Dict[str, Any]]:
    known_rows: List[Dict[str, Any]] = []
    for row in rows or []:
        label = _label_value(row.get(label_key))
        if label is None:
            continue
        normalized = dict(row)
        normalized["_label"] = label
        normalized["_prob"] = _safe_float(row.get(prob_key)) or 0.0
        known_rows.append(normalized)

    if not known_rows:
        return []

    feature_names = feature_names or list(BUCKETS)
    baseline_rate = sum(item["_label"] for item in known_rows) / len(known_rows)
    report: List[Dict[str, Any]] = []

    for feature_name in feature_names:
        if feature_name not in BUCKETS:
            continue
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for row in known_rows:
            bucket = _bucket_name(feature_name, row.get(feature_name))
            if bucket is None:
                continue
            buckets.setdefault(bucket, []).append(row)

        for _, _, bucket in BUCKETS[feature_name]:
            items = buckets.get(bucket, [])
            if not items:
                continue
            positive_count = sum(item["_label"] for item in items)
            positive_rate = positive_count / len(items)
            top_items = sorted(items, key=lambda item: item["_prob"], reverse=True)[:5]
            bucket_top5_positive_rate = sum(item["_label"] for item in top_items) / len(top_items) if top_items else 0.0
            report.append(
                {
                    "feature_name": feature_name,
                    "bucket": bucket,
                    "sample_count": len(items),
                    "positive_count": positive_count,
                    "positive_rate": _round_rate(positive_rate),
                    "baseline_rate": _round_rate(baseline_rate),
                    "lift": _round_rate(positive_rate - baseline_rate),
                    "bucket_top5_positive_rate": _round_rate(bucket_top5_positive_rate),
                    "topk_positive_rate": _round_rate(bucket_top5_positive_rate),
                    "conclusion": "高于基准" if positive_rate > baseline_rate else "不高于基准",
                }
            )

    return report


def _importance_value(value: Any) -> float:
    number = _safe_float(value)
    return number if number is not None else 0.0


def _format_failure_summary(reject_reasons: List[str]) -> str:
    if not reject_reasons:
        return "验收通过，暂无失败原因"
    labels = [REJECT_REASON_TEXT.get(reason, reason) for reason in reject_reasons]
    return "；".join(labels)


def build_training_attribution(
    feature_importance: Dict[str, float],
    bucket_report: List[Dict[str, Any]],
    reject_reasons: List[str],
) -> Dict[str, Any]:
    feature_importance = feature_importance or {}
    bucket_report = bucket_report or []
    reject_reasons = reject_reasons or []
    sorted_features = sorted(
        feature_importance.items(),
        key=lambda item: _importance_value(item[1]),
        reverse=True,
    )
    top_positive_features = [name for name, value in sorted_features if _importance_value(value) > 0][:8]
    noise_features = [name for name, value in sorted_features if _importance_value(value) == 0]
    best_buckets = sorted(bucket_report, key=lambda item: _importance_value(item.get("lift")), reverse=True)[:8]
    worst_buckets = sorted(bucket_report, key=lambda item: _importance_value(item.get("lift")))[:8]

    return {
        "top_positive_features": top_positive_features,
        "top_negative_features": [],
        "unstable_features": [],
        "noise_features": noise_features,
        "best_buckets": best_buckets,
        "worst_buckets": worst_buckets,
        "failure_reasons": reject_reasons,
        "failure_summary": _format_failure_summary(reject_reasons),
        "next_attempt_suggestions": ["尝试更保守参数或扩大训练样本"] if reject_reasons else [],
    }
