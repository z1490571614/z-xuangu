"""
默认竞价策略回放验收。
"""
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class ReplayValidationConfig:
    min_avg_recall: float = 0.80
    min_avg_jaccard: float = 0.60
    max_daily_count_error: float = 0.30

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _round_rate(value: float) -> float:
    return round(float(value), 4)


def _find_duplicates(codes: List[str]) -> List[str]:
    return sorted(code for code, count in Counter(codes).items() if count > 1)


def compare_daily_lists(trade_date: str, real_codes: List[str], replay_codes: List[str]) -> Dict[str, Any]:
    real_set = set(real_codes)
    replay_set = set(replay_codes)
    intersection = sorted(real_set & replay_set)
    union = real_set | replay_set
    real_count = len(real_set)
    replay_count = len(replay_set)
    recall = len(intersection) / real_count if real_count else 0
    precision = len(intersection) / replay_count if replay_count else 0
    jaccard = len(intersection) / len(union) if union else 0
    count_error = abs(replay_count - real_count) / max(real_count, 1)
    return {
        "trade_date": trade_date,
        "real_count": real_count,
        "replay_count": replay_count,
        "intersection_count": len(intersection),
        "intersection": intersection,
        "missing_from_replay": sorted(real_set - replay_set),
        "extra_in_replay": sorted(replay_set - real_set),
        "duplicate_real_codes": _find_duplicates(real_codes),
        "duplicate_replay_codes": _find_duplicates(replay_codes),
        "recall": _round_rate(recall),
        "precision": _round_rate(precision),
        "jaccard": _round_rate(jaccard),
        "count_error": _round_rate(count_error),
    }


def validate_replay_against_real(days: List[Dict[str, Any]], config: ReplayValidationConfig | None = None) -> Dict[str, Any]:
    config = config or ReplayValidationConfig()
    daily = [
        compare_daily_lists(item["trade_date"], item.get("real_codes", []), item.get("replay_codes", []))
        for item in days
    ]
    avg_recall = _round_rate(sum(item["recall"] for item in daily) / len(daily)) if daily else 0
    avg_jaccard = _round_rate(sum(item["jaccard"] for item in daily) / len(daily)) if daily else 0
    max_count_error = max((item["count_error"] for item in daily), default=1)
    reject_reasons = []
    if avg_recall < config.min_avg_recall:
        reject_reasons.append("avg_recall_below_threshold")
    if avg_jaccard < config.min_avg_jaccard:
        reject_reasons.append("avg_jaccard_below_threshold")
    if max_count_error > config.max_daily_count_error:
        reject_reasons.append("daily_count_error_above_threshold")
    if any(item["duplicate_real_codes"] or item["duplicate_replay_codes"] for item in daily):
        reject_reasons.append("duplicate_codes_detected")
    return {
        "accepted": not reject_reasons,
        "reject_reasons": reject_reasons,
        "avg_recall": avg_recall,
        "avg_jaccard": avg_jaccard,
        "max_count_error": _round_rate(max_count_error),
        "daily": daily,
        "config": config.to_dict(),
    }
