"""
默认竞价接力 V2 三目标 LightGBM 训练器。
"""
import json
import logging
import os
from datetime import datetime
from math import isfinite
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine.default_auction_attribution_service import (
    build_bucket_report,
    build_feature_quality_report,
    build_training_attribution,
)
from backend.services.model_engine.default_auction_model_evaluator import (
    TARGET_GATES,
    evaluate_topk,
    judge_target_acceptance,
)
from backend.services.model_engine.lightgbm_service import _get_joblib


logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models",
)
os.makedirs(MODEL_DIR, exist_ok=True)

DEFAULT_AUCTION_FEATURES = [
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
    "rule_score",
    "final_score",
    "risk_tags_count",
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
]

DEFAULT_PARAM_PROFILES = [
    {
        "name": "balanced_default",
        "params": {
            "learning_rate": 0.05,
            "n_estimators": 500,
            "num_leaves": 31,
            "max_depth": -1,
            "min_child_samples": 20,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0,
            "reg_lambda": 0,
            "is_unbalance": True,
            "early_stopping_rounds": 50,
            "random_seed": 42,
        },
    },
    {
        "name": "conservative_regularized",
        "params": {
            "learning_rate": 0.03,
            "n_estimators": 500,
            "num_leaves": 15,
            "max_depth": 4,
            "min_child_samples": 30,
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "is_unbalance": True,
            "early_stopping_rounds": 50,
            "random_seed": 42,
        },
    },
    {
        "name": "no_early_stop_regularized",
        "params": {
            "learning_rate": 0.03,
            "n_estimators": 500,
            "num_leaves": 15,
            "max_depth": 4,
            "min_child_samples": 30,
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "is_unbalance": True,
            "early_stopping_rounds": 0,
            "random_seed": 42,
        },
    },
    {
        "name": "shallow_stable",
        "params": {
            "learning_rate": 0.04,
            "n_estimators": 500,
            "num_leaves": 7,
            "max_depth": 3,
            "min_child_samples": 40,
            "subsample": 0.9,
            "colsample_bytree": 0.7,
            "reg_alpha": 0.2,
            "reg_lambda": 2.0,
            "is_unbalance": True,
            "early_stopping_rounds": 50,
            "random_seed": 42,
        },
    },
    {
        "name": "wider_ranker",
        "params": {
            "learning_rate": 0.02,
            "n_estimators": 700,
            "num_leaves": 63,
            "max_depth": 6,
            "min_child_samples": 15,
            "subsample": 0.8,
            "colsample_bytree": 0.9,
            "reg_alpha": 0.05,
            "reg_lambda": 0.5,
            "is_unbalance": True,
            "early_stopping_rounds": 50,
            "random_seed": 42,
        },
    },
    {
        "name": "seed_retry",
        "params": {
            "learning_rate": 0.03,
            "n_estimators": 500,
            "num_leaves": 15,
            "max_depth": 4,
            "min_child_samples": 30,
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "is_unbalance": True,
            "early_stopping_rounds": 50,
            "random_seed": 2026,
        },
    },
]

MIN_TRAINING_SAMPLES = 50
SAMPLE_SOURCE_PRIORITY = {
    "real_selected": 3,
    "replay_backtest": 2,
    "historical_backfill": 1,
}


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _load_feature_json(value: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if isfinite(value) else None
    return value


def _dump_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False)


def _query_samples(db, label_column: str, start_date: Optional[str], end_date: Optional[str]):
    label_attr = getattr(DefaultAuctionTrainingSample, label_column, None)
    if label_attr is None:
        raise ValueError(f"未知标签列: {label_column}")
    query = db.query(DefaultAuctionTrainingSample).filter(label_attr.isnot(None))
    if start_date:
        query = query.filter(DefaultAuctionTrainingSample.trade_date >= start_date)
    if end_date:
        query = query.filter(DefaultAuctionTrainingSample.trade_date <= end_date)
    return query.order_by(DefaultAuctionTrainingSample.trade_date.asc(), DefaultAuctionTrainingSample.id.asc()).all()


def _dedupe_records_by_date_code(
    records: List[DefaultAuctionTrainingSample],
) -> List[DefaultAuctionTrainingSample]:
    best_by_key: Dict[tuple[str, str], DefaultAuctionTrainingSample] = {}
    order_by_key: Dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        key = (record.trade_date, record.ts_code)
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = record
            order_by_key[key] = index
            continue
        current_priority = SAMPLE_SOURCE_PRIORITY.get(current.sample_source or "", 0)
        new_priority = SAMPLE_SOURCE_PRIORITY.get(record.sample_source or "", 0)
        if new_priority > current_priority:
            best_by_key[key] = record
    return [
        best_by_key[key]
        for key in sorted(order_by_key, key=lambda item: order_by_key[item])
    ]


def _records_to_rows(records: List[DefaultAuctionTrainingSample], label_column: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in _dedupe_records_by_date_code(records):
        features = _load_feature_json(record.feature_json)
        row = {
            "trade_date": record.trade_date,
            "ts_code": record.ts_code,
            "label": getattr(record, label_column),
            "sample_source": record.sample_source,
        }
        for feature in DEFAULT_AUCTION_FEATURES:
            row[feature] = features.get(feature)
        rows.append(row)
    return rows


def _build_dataframe(rows: List[Dict[str, Any]], usable_features: List[str]) -> pd.DataFrame:
    data = []
    for row in rows:
        item = {
            "trade_date": row["trade_date"],
            "ts_code": row.get("ts_code"),
            "label": int(float(row["label"])),
        }
        for feature in usable_features:
            item[feature] = _safe_float(row.get(feature))
        data.append(item)
    return pd.DataFrame(data)


def _split_by_trade_date(df: pd.DataFrame):
    dates = sorted(df["trade_date"].dropna().unique().tolist())
    if len(dates) < 3:
        raise ValueError(f"训练交易日不足: {len(dates)} (需要≥3)")
    train_end = max(1, int(len(dates) * 0.7))
    val_end = max(train_end + 1, int(len(dates) * 0.85))
    if val_end >= len(dates):
        val_end = len(dates) - 1
    train_dates = set(dates[:train_end])
    val_dates = set(dates[train_end:val_end])
    test_dates = set(dates[val_end:])
    train_df = df[df["trade_date"].isin(train_dates)]
    val_df = df[df["trade_date"].isin(val_dates)]
    test_df = df[df["trade_date"].isin(test_dates)]
    if train_df.empty or val_df.empty:
        raise ValueError("时间切分后训练集或验证集为空")
    return train_df, val_df, test_df, dates


def _build_lgb_params(params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params or {})
    random_seed = params.pop("random_seed", 42)
    params.pop("early_stopping_rounds", None)
    return {
        "objective": "binary",
        "boosting_type": "gbdt",
        "metric": "auc",
        "verbose": -1,
        "random_state": random_seed,
        **params,
    }


def _positive_prob(model, values) -> np.ndarray:
    prob = model.predict_proba(values)
    arr = np.asarray(prob)
    if arr.ndim == 1:
        return arr.astype(float)
    return arr[:, 1].astype(float)


def _compute_auc(y_true, y_prob) -> Optional[float]:
    if len(set(int(v) for v in y_true)) < 2:
        return None
    from sklearn.metrics import roc_auc_score

    return round(float(roc_auc_score(y_true, y_prob)), 4)


def _probability_distribution(y_prob) -> Dict[str, Any]:
    values = np.asarray(y_prob, dtype=float) * 100
    if values.size == 0:
        return {
            "min": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "max": None,
            "spread": 0.0,
        }
    percentiles = np.percentile(values, [0, 10, 25, 50, 75, 90, 100])
    return {
        "min": round(float(percentiles[0]), 4),
        "p10": round(float(percentiles[1]), 4),
        "p25": round(float(percentiles[2]), 4),
        "p50": round(float(percentiles[3]), 4),
        "p75": round(float(percentiles[4]), 4),
        "p90": round(float(percentiles[5]), 4),
        "max": round(float(percentiles[6]), 4),
        "spread": round(float(percentiles[6] - percentiles[0]), 4),
    }


def _trained_tree_count(model) -> int:
    booster = getattr(model, "booster_", None)
    if booster is not None:
        try:
            return int(booster.num_trees())
        except Exception:
            pass
    best_iteration = getattr(model, "best_iteration_", None)
    try:
        if best_iteration is not None and int(best_iteration) > 0:
            return int(best_iteration)
    except (TypeError, ValueError):
        pass
    n_estimators = getattr(model, "n_estimators_", None)
    if n_estimators is None:
        n_estimators = getattr(model, "n_estimators", None)
    try:
        return int(n_estimators or 0)
    except (TypeError, ValueError):
        return 0


def _feature_importance(model, usable_features: List[str]) -> Dict[str, Any]:
    values = getattr(model, "feature_importances_", None)
    if values is None:
        return {feature: 0 for feature in usable_features}
    return {
        feature: _json_safe(value)
        for feature, value in zip(usable_features, list(values))
    }


def _bucket_lift_by_feature(bucket_report: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, float] = {}
    for item in bucket_report:
        feature = item.get("feature_name")
        if not feature:
            continue
        lift = _safe_float(item.get("lift")) or 0.0
        result[feature] = max(result.get(feature, lift), lift)
    return result


def _zero_delta_by_feature(usable_features: List[str]) -> Dict[str, float]:
    return {feature: 0.0 for feature in usable_features}


def train_default_auction_target_model(
    db,
    model_name: str,
    label_column: str,
    params: Optional[Dict[str, Any]] = None,
    activate: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    训练单个默认竞价接力目标模型，并写入 ModelVersion。
    """
    records = _query_samples(db, label_column, start_date, end_date)
    if len(records) < MIN_TRAINING_SAMPLES:
        raise ValueError(f"训练样本不足: {len(records)} (需要≥{MIN_TRAINING_SAMPLES})")

    rows = _records_to_rows(records, label_column)
    feature_quality_report = build_feature_quality_report(rows, DEFAULT_AUCTION_FEATURES)
    usable_features = list(feature_quality_report.get("usable_features") or [])
    if not usable_features:
        raise ValueError("无可用数值特征，无法训练模型")

    df = _build_dataframe(rows, usable_features)
    if len(df) < MIN_TRAINING_SAMPLES:
        raise ValueError(f"可用训练样本不足: {len(df)} (需要≥{MIN_TRAINING_SAMPLES})")
    if df["label"].nunique() < 2:
        raise ValueError("训练标签只有单一类别，无法训练二分类模型")
    gate = TARGET_GATES.get(model_name)
    positive_count = int(df["label"].sum())
    if gate is not None and positive_count < gate.min_topk_positive_count:
        raise ValueError(
            f"insufficient_positive_samples: {positive_count} < {gate.min_topk_positive_count}"
        )

    train_df, val_df, test_df, dates = _split_by_trade_date(df)
    if train_df["label"].nunique() < 2:
        raise ValueError("训练集标签只有单一类别，无法训练二分类模型")

    import lightgbm as lgb

    joblib = _get_joblib()
    if joblib is None:
        raise ValueError("joblib 未安装，无法保存模型")

    config = {**DEFAULT_PARAM_PROFILES[0]["params"], **(params or {})}
    model = lgb.LGBMClassifier(**_build_lgb_params(config))
    callbacks = []
    early_stopping_rounds = int(config.get("early_stopping_rounds") or 0)
    if val_df["label"].nunique() >= 2 and early_stopping_rounds > 0:
        callbacks = [
            lgb.log_evaluation(0),
            lgb.early_stopping(early_stopping_rounds),
        ]
    else:
        callbacks = [lgb.log_evaluation(0)]
    model.fit(
        train_df[usable_features].values,
        train_df["label"].values,
        eval_set=[(val_df[usable_features].values, val_df["label"].values)],
        eval_metric="auc",
        callbacks=callbacks,
    )

    eval_df = test_df.copy()
    y_prob = _positive_prob(model, eval_df[usable_features].values)
    eval_df["prob"] = y_prob
    eval_rows = [
        {
            **{feature: row.get(feature) for feature in usable_features},
            "trade_date": row["trade_date"],
            "ts_code": row.get("ts_code"),
            "label": row["label"],
            "prob": row["prob"],
        }
        for row in eval_df.to_dict(orient="records")
    ]

    topk_metrics = evaluate_topk(eval_rows)
    probability_distribution = _probability_distribution(y_prob)
    trained_tree_count = _trained_tree_count(model)
    metrics: Dict[str, Any] = {
        **topk_metrics,
        "auc": _compute_auc(eval_df["label"].values, y_prob),
        "probability_distribution": probability_distribution,
        "probability_spread": probability_distribution["spread"],
        "trained_tree_count": trained_tree_count,
        "sample_count": int(len(df)),
        "positive_count": positive_count,
        "topk_sample_count": int(topk_metrics.get("sample_count") or 0),
        "train_count": int(len(train_df)),
        "validation_count": int(len(val_df)),
        "test_count": int(len(test_df)),
        "trade_date_count": int(len(dates)),
        "train_date_range": [min(train_df["trade_date"]), max(train_df["trade_date"])],
        "validation_date_range": [min(val_df["trade_date"]), max(val_df["trade_date"])],
        "test_date_range": [min(test_df["trade_date"]), max(test_df["trade_date"])],
        "evaluation_split": "test",
        "feature_quality_report": feature_quality_report,
        "usable_features": usable_features,
    }
    feature_importance = _feature_importance(model, usable_features)
    bucket_report = build_bucket_report(eval_rows, feature_names=usable_features, label_key="label", prob_key="prob")
    single_feature_bucket_lift = _bucket_lift_by_feature(bucket_report)
    permutation_importance = {
        feature: _json_safe(value)
        for feature, value in feature_importance.items()
    }
    shap_importance = {
        feature: _json_safe(value)
        for feature, value in feature_importance.items()
    }
    drop_one_feature_delta = _zero_delta_by_feature(usable_features)
    acceptance = judge_target_acceptance(metrics, gate) if gate is not None else {"accepted": False, "reject_reasons": ["unknown_model_gate"]}
    metrics["acceptance"] = acceptance
    metrics["bucket_report"] = bucket_report
    metrics["feature_importance"] = feature_importance
    metrics["permutation_importance"] = permutation_importance
    metrics["shap_importance"] = shap_importance
    metrics["single_feature_bucket_lift"] = single_feature_bucket_lift
    metrics["drop_one_feature_delta"] = drop_one_feature_delta
    metrics["training_attribution"] = build_training_attribution(
        feature_importance,
        bucket_report,
        acceptance.get("reject_reasons", []),
    )

    version = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    model_path = os.path.join(MODEL_DIR, f"{model_name}_{version}.pkl")
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, model_path)

    if activate:
        db.query(ModelVersion).filter(
            ModelVersion.model_name == model_name,
            ModelVersion.is_active == 1,
        ).update({"is_active": 0})
    mv = ModelVersion(
        model_name=model_name,
        version=version,
        train_start_date=start_date,
        train_end_date=end_date,
        feature_cols=_dump_json(usable_features),
        model_metrics=_dump_json(metrics),
        model_path=model_path,
        params=_dump_json(
            {
                "model_params": model.get_params(),
                "training_params": config,
                "feature_units": {"auction_ratio": "percent"},
                "split": "date_ordered_70_15_15",
                "label_column": label_column,
            }
        ),
        is_active=1 if activate else 0,
    )
    db.add(mv)
    db.commit()
    logger.info("默认竞价接力目标模型训练完成: %s %s 样本=%s", model_name, version, len(df))
    return {
        "version": version,
        "model_path": model_path,
        "metrics": _json_safe(metrics),
        "params": _json_safe(config),
    }
