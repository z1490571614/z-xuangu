"""
默认竞价接力 V2 离线回测服务。
"""
import json
from typing import Any, Dict, Optional

from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine import lightgbm_service
from backend.services.model_engine.default_auction_model_evaluator import evaluate_topk


TARGET_LABELS: Dict[str, str] = {
    "default_auction_t0_limit_lgbm": "label_t0_limit_success",
    "default_auction_t1_premium_lgbm": "label_t1_premium_success",
    "default_auction_t1_continue_lgbm": "label_t1_continue_limit",
}


def run_default_auction_relay_backtest(
    db,
    start_date: str,
    end_date: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    targets = {
        model_name: run_default_auction_target_backtest(
            db,
            model_name=model_name,
            label_column=label_column,
            start_date=start_date,
            end_date=end_date,
            version=version,
        )
        for model_name, label_column in TARGET_LABELS.items()
    }
    return {
        "model_name": "default_auction_relay_v2",
        "start_date": start_date,
        "end_date": end_date,
        "targets": targets,
    }


def run_default_auction_target_backtest(
    db,
    model_name: str,
    label_column: str,
    start_date: str,
    end_date: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    mv = _find_model_version(db, model_name, version)
    feature_cols = _json_loads(mv.feature_cols, [])
    feature_units = _json_loads(mv.params, {}).get("feature_units", {})
    rows = (
        db.query(DefaultAuctionTrainingSample)
        .filter(
            DefaultAuctionTrainingSample.trade_date >= start_date,
            DefaultAuctionTrainingSample.trade_date <= end_date,
        )
        .order_by(DefaultAuctionTrainingSample.trade_date.asc(), DefaultAuctionTrainingSample.ts_code.asc())
        .all()
    )

    eval_rows = []
    prediction_failed_count = 0
    for sample in rows:
        features = _json_loads(sample.feature_json, {})
        label = getattr(sample, label_column, None)
        prob = None
        try:
            prob = lightgbm_service._predict_with_model_path(
                model_name,
                mv.model_path,
                feature_cols,
                features,
                feature_units,
            )
        except Exception:
            prob = None
        if prob is None:
            prediction_failed_count += 1
            continue
        eval_rows.append(
            {
                "trade_date": sample.trade_date,
                "ts_code": sample.ts_code,
                "prob": prob,
                "label": label,
            }
        )

    metrics = evaluate_topk(eval_rows)
    return {
        "model_name": model_name,
        "version": mv.version,
        "label_column": label_column,
        "start_date": start_date,
        "end_date": end_date,
        "raw_sample_count": len(rows),
        "prediction_failed_count": prediction_failed_count,
        "metrics": metrics,
    }


def _find_model_version(db, model_name: str, version: Optional[str]) -> ModelVersion:
    query = db.query(ModelVersion).filter(ModelVersion.model_name == model_name)
    if version:
        query = query.filter(ModelVersion.version == version)
    else:
        query = query.filter(ModelVersion.is_active == 1)
    mv = query.order_by(ModelVersion.id.desc()).first()
    if mv is None:
        raise ValueError(f"模型版本不存在: {model_name} {version or 'active'}")
    return mv


def _json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback
