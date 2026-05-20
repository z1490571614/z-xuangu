"""
默认竞价接力模型 TopK 评估和验收闸门。
"""
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Dict, List, Optional


@dataclass
class AcceptanceGate:
    top3_lift: float
    top5_lift: float
    min_topk_positive_count: int
    min_auc: float
    min_probability_spread: float = 0.0
    min_trained_tree_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


TARGET_GATES = {
    "default_auction_t0_limit_lgbm": AcceptanceGate(0.08, 0.05, 20, 0.55),
    "default_auction_t1_premium_lgbm": AcceptanceGate(
        0.10,
        0.06,
        25,
        0.55,
        min_probability_spread=5.0,
        min_trained_tree_count=5,
    ),
    "default_auction_t1_continue_lgbm": AcceptanceGate(0.06, 0.04, 10, 0.53),
}


def _round_rate(value: float) -> float:
    return round(float(value), 4)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _label_value(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return 1 if number > 0 else 0


def _rate(items: List[Dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return _round_rate(sum(int(item["label"]) for item in items) / len(items))


def _empty_metrics(unknown_label_count: int = 0) -> Dict[str, Any]:
    return {
        "sample_count": 0,
        "unknown_label_count": unknown_label_count,
        "invalid_trade_date_count": 0,
        "daily_count": 0,
        "baseline_rate": 0.0,
        "top1_rate": 0.0,
        "top3_rate": 0.0,
        "top5_rate": 0.0,
        "top1_lift": 0.0,
        "top3_lift": 0.0,
        "top5_lift": 0.0,
        "top1_sample_count": 0,
        "top3_sample_count": 0,
        "top5_sample_count": 0,
        "topk_positive_count": 0,
    }


def _trade_date_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def evaluate_topk(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    按交易日分组，按概率降序取每日 top1/top3/top5 并计算相对基准提升。

    `topk_positive_count` 固定表示每日 top5 样本中的正例数量总和。label 为
    None、空字符串或非法数字的样本属于未知标签，不进入基准、胜率和 TopK 排名。
    """
    known_rows: List[Dict[str, Any]] = []
    unknown_label_count = 0
    invalid_trade_date_count = 0
    for row in rows or []:
        label = _label_value(row.get("label"))
        if label is None:
            unknown_label_count += 1
            continue
        trade_date = _trade_date_value(row.get("trade_date"))
        if trade_date is None:
            invalid_trade_date_count += 1
            continue
        normalized = dict(row)
        normalized["label"] = label
        normalized["trade_date"] = trade_date
        normalized["_prob"] = _safe_float(row.get("prob"))
        known_rows.append(normalized)

    if not known_rows:
        result = _empty_metrics(unknown_label_count)
        result["invalid_trade_date_count"] = invalid_trade_date_count
        return result

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in known_rows:
        by_date.setdefault(row["trade_date"], []).append(row)

    top1: List[Dict[str, Any]] = []
    top3: List[Dict[str, Any]] = []
    top5: List[Dict[str, Any]] = []
    for items in by_date.values():
        ranked = sorted(items, key=lambda item: item["_prob"], reverse=True)
        top1.extend(ranked[:1])
        top3.extend(ranked[:3])
        top5.extend(ranked[:5])

    baseline_rate = _rate(known_rows)
    top1_rate = _rate(top1)
    top3_rate = _rate(top3)
    top5_rate = _rate(top5)
    return {
        "sample_count": len(known_rows),
        "unknown_label_count": unknown_label_count,
        "invalid_trade_date_count": invalid_trade_date_count,
        "daily_count": len(by_date),
        "baseline_rate": baseline_rate,
        "top1_rate": top1_rate,
        "top3_rate": top3_rate,
        "top5_rate": top5_rate,
        "top1_lift": _round_rate(top1_rate - baseline_rate),
        "top3_lift": _round_rate(top3_rate - baseline_rate),
        "top5_lift": _round_rate(top5_rate - baseline_rate),
        "top1_sample_count": len(top1),
        "top3_sample_count": len(top3),
        "top5_sample_count": len(top5),
        "topk_positive_count": sum(int(item["label"]) for item in top5),
    }


def _metric_lift(metrics: Dict[str, Any], lift_key: str, rate_key: str) -> float:
    if lift_key in metrics:
        return _safe_float(metrics.get(lift_key))
    return _round_rate(_safe_float(metrics.get(rate_key)) - _safe_float(metrics.get("baseline_rate")))


def judge_target_acceptance(metrics: Dict[str, Any], gate: AcceptanceGate) -> Dict[str, Any]:
    reject_reasons: List[str] = []
    top3_lift = _metric_lift(metrics, "top3_lift", "top3_rate")
    top5_lift = _metric_lift(metrics, "top5_lift", "top5_rate")
    topk_positive_count = int(_safe_float(metrics.get("topk_positive_count")))
    auc = metrics.get("auc")
    probability_spread = _safe_float(metrics.get("probability_spread"))
    trained_tree_count = int(_safe_float(metrics.get("trained_tree_count")))

    tolerance = 1e-9
    if top3_lift + tolerance < gate.top3_lift:
        reject_reasons.append("top3_lift_below_threshold")
    if top5_lift + tolerance < gate.top5_lift:
        reject_reasons.append("top5_lift_below_threshold")
    if topk_positive_count < gate.min_topk_positive_count:
        reject_reasons.append("topk_positive_count_below_threshold")
    if auc is None or _safe_float(auc) < gate.min_auc:
        reject_reasons.append("auc_below_threshold")
    if gate.min_probability_spread > 0 and probability_spread + tolerance < gate.min_probability_spread:
        reject_reasons.append("probability_spread_below_threshold")
    if gate.min_trained_tree_count > 0 and trained_tree_count < gate.min_trained_tree_count:
        reject_reasons.append("trained_tree_count_below_threshold")

    return {
        "accepted": not reject_reasons,
        "reject_reasons": reject_reasons,
        "gate": gate.to_dict(),
    }
