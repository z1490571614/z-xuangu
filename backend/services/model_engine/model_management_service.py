"""
模型中心管理服务。
"""
import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models import ModelTrainingJob, ModelVersion, SelectedStock, SelectionRecord
from backend.models.auction_backtest import StockAuctionOpen
from backend.services.auction_data_service import AuctionDataService
from backend.services.model_engine.default_auction_sample_builder import build_selected_stock_feature_payloads
from backend.services.model_engine import lightgbm_service
from backend.services.model_engine.default_auction_attribution_service import (
    build_single_prediction_attribution,
)


MODEL_OUTPUT_FIELDS: Dict[str, Tuple[str, str]] = {
    "active_auction_lgbm": ("model_score", "model_version"),
    "leader_main_t0_lgbm": ("t0_limit_success_prob", "t0_limit_success_model_version"),
}

DEFAULT_AUCTION_RELAY_MODEL_NAME = "default_auction_relay_v2"
DEFAULT_AUCTION_TARGET_MODELS = (
    ("default_auction_t0_limit_lgbm", "default_t0_limit_prob", 0.25),
    ("default_auction_t1_premium_lgbm", "default_t1_premium_prob", 0.35),
    ("default_auction_t1_continue_lgbm", "default_t1_continue_prob", 0.40),
)
DEFAULT_AUCTION_TARGET_MODEL_NAMES = {
    model_name
    for model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS
}
DEFAULT_AUCTION_CRITICAL_FEATURES = {
    "auction_amount",
    "auction_volume",
    "market_limit_up_count",
    "market_limit_down_count",
    "market_max_connected_board",
    "market_zhaban_rate",
    "market_emotion_score",
}
DEFAULT_AUCTION_OPEN_FEATURES = {
    "auction_ratio",
    "auction_turnover_rate",
    "auction_amount",
    "auction_volume",
}


def _load_json(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _feature_units_from_params(params: Dict[str, Any]) -> Dict[str, str]:
    feature_units = params.get("feature_units")
    return feature_units if isinstance(feature_units, dict) else {}


def _is_missing_feature_value(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, float):
        return not math.isfinite(value)
    return False


def _missing_default_auction_critical_features(
    features: Dict[str, Any],
    required_feature_cols: List[str],
) -> List[str]:
    required = DEFAULT_AUCTION_CRITICAL_FEATURES.intersection(required_feature_cols)
    return sorted(name for name in required if _is_missing_feature_value(features.get(name)))


def _backfill_selected_stock_auction_fields(stock: SelectedStock, features: Dict[str, Any]) -> None:
    for field in ("auction_ratio", "auction_turnover_rate", "open_change_pct"):
        value = features.get(field)
        if value is not None:
            setattr(stock, field, value)


def _needs_auction_open_sync(
    feature_payloads: Dict[str, Dict[str, Any]],
    ts_codes: List[str],
    required_feature_cols: List[str],
) -> bool:
    required = DEFAULT_AUCTION_OPEN_FEATURES.intersection(required_feature_cols)
    if not required:
        return False
    for ts_code in ts_codes:
        features = (feature_payloads.get(ts_code) or {}).get("features") or {}
        if any(_is_missing_feature_value(features.get(feature)) for feature in required):
            return True
    return False


def _version_payload(version: ModelVersion) -> Dict[str, Any]:
    params = _load_json(version.params, {})
    payload = {
        "id": version.id,
        "model_name": version.model_name,
        "version": version.version,
        "train_start_date": version.train_start_date,
        "train_end_date": version.train_end_date,
        "feature_cols": _load_json(version.feature_cols, []),
        "metrics": _load_json(version.model_metrics, {}),
        "model_path": version.model_path,
        "params": params,
        "is_active": bool(version.is_active),
        "available": bool(version.model_path and os.path.exists(version.model_path)),
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }
    return payload


def list_models(db: Session) -> Dict[str, Any]:
    versions = db.query(ModelVersion).order_by(ModelVersion.id.desc()).all()
    models: Dict[str, Dict[str, Any]] = {}
    for mv in versions:
        model = models.setdefault(
            mv.model_name,
            {
                "model_name": mv.model_name,
                "active_version": None,
                "versions": [],
            },
        )
        payload = _version_payload(mv)
        model["versions"].append(payload)
        if mv.is_active:
            model["active_version"] = payload
    for model in models.values():
        model["versions"].sort(key=lambda item: (not item["is_active"], -int(item["id"] or 0)))
    models[DEFAULT_AUCTION_RELAY_MODEL_NAME] = _default_auction_relay_model_payload(db)
    return {"models": models}


def _default_auction_relay_model_payload(db: Session) -> Dict[str, Any]:
    target_models = []
    active_versions = []
    for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS:
        mv = (
            db.query(ModelVersion)
            .filter(ModelVersion.model_name == target_model_name, ModelVersion.is_active == 1)
            .order_by(ModelVersion.id.desc())
            .first()
        )
        if mv is None:
            target_models.append(
                {
                    "model_name": target_model_name,
                    "active_version": None,
                    "version_id": None,
                    "model_path": None,
                    "available": False,
                }
            )
            continue
        target_models.append(
            {
                "model_name": target_model_name,
                "active_version": mv.version,
                "version_id": mv.id,
                "model_path": mv.model_path,
                "available": bool(mv.model_path and os.path.exists(mv.model_path)),
            }
        )
        active_versions.append(mv.version)

    return {
        "model_name": DEFAULT_AUCTION_RELAY_MODEL_NAME,
        "is_composite": True,
        "target_models": target_models,
        "active_version": (
            "|".join(active_versions)
            if len(active_versions) == len(DEFAULT_AUCTION_TARGET_MODELS)
            else None
        ),
        "versions": [],
    }


def _get_model_version(db: Session, model_name: str, version: Optional[str] = None) -> ModelVersion:
    query = db.query(ModelVersion).filter(ModelVersion.model_name == model_name)
    if version:
        mv = query.filter(ModelVersion.version == version).order_by(ModelVersion.id.desc()).first()
    else:
        mv = query.filter(ModelVersion.is_active == 1).order_by(ModelVersion.id.desc()).first()
    if mv is None:
        raise ValueError("模型版本不存在")
    if not mv.model_path or not os.path.exists(mv.model_path):
        raise ValueError("模型文件不存在")
    return mv


def _accepted_default_auction_relay_sets(db: Session) -> List[Dict[str, str]]:
    jobs = (
        db.query(ModelTrainingJob)
        .filter(
            ModelTrainingJob.model_name == DEFAULT_AUCTION_RELAY_MODEL_NAME,
            ModelTrainingJob.status == "passed",
        )
        .order_by(ModelTrainingJob.id.desc())
        .all()
    )
    accepted_sets: List[Dict[str, str]] = []
    for job in jobs:
        acceptance = _load_json(job.acceptance_json, {})
        targets = acceptance.get("targets")
        if not isinstance(targets, dict):
            continue
        relay_set: Dict[str, str] = {}
        complete = True
        for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS:
            payload = targets.get(target_model_name)
            if not isinstance(payload, dict) or payload.get("accepted") is not True or not payload.get("version"):
                complete = False
                break
            relay_set[target_model_name] = str(payload["version"])
        if complete:
            accepted_sets.append(relay_set)
    return accepted_sets


def _activate_default_auction_relay_set(
    db: Session,
    model_name: str,
    version: str,
) -> Dict[str, Any]:
    _get_model_version(db, model_name, version)
    relay_set = next(
        (
            item
            for item in _accepted_default_auction_relay_sets(db)
            if item.get(model_name) == version
        ),
        None,
    )
    if relay_set is None:
        raise ValueError(f"{model_name} {version} 未通过默认竞价接力三目标验收，禁止单独激活")

    versions = {
        target_model_name: _get_model_version(db, target_model_name, target_version)
        for target_model_name, target_version in relay_set.items()
    }
    db.query(ModelVersion).filter(
        ModelVersion.model_name.in_(DEFAULT_AUCTION_TARGET_MODEL_NAMES)
    ).update({"is_active": 0}, synchronize_session=False)
    for target_model_name, mv in versions.items():
        db.query(ModelVersion).filter(
            ModelVersion.model_name == target_model_name,
            ModelVersion.version == mv.version,
        ).update({"is_active": 1}, synchronize_session=False)
    db.commit()

    active_version = "|".join(
        relay_set[target_model_name]
        for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS
    )
    return {
        "model_name": DEFAULT_AUCTION_RELAY_MODEL_NAME,
        "active_version": active_version,
        "target_versions": relay_set,
        "message": f"已按三目标验收组合激活默认竞价接力版本 {active_version}",
    }


def activate_model_version(db: Session, model_name: str, version: str) -> Dict[str, Any]:
    if model_name in DEFAULT_AUCTION_TARGET_MODEL_NAMES:
        return _activate_default_auction_relay_set(db, model_name, version)

    mv = _get_model_version(db, model_name, version)
    db.query(ModelVersion).filter(ModelVersion.model_name == model_name).update({"is_active": 0})
    mv.is_active = 1
    db.commit()
    return {
        "model_name": model_name,
        "active_version": version,
        "message": f"已激活模型版本 {version}",
    }


def _stock_to_features(stock: SelectedStock, db: Optional[Session] = None) -> Dict[str, Any]:
    features = {
        column.name: getattr(stock, column.name)
        for column in SelectedStock.__table__.columns
    }
    if db is None or (
        features.get("auction_ratio") is not None
        and features.get("auction_turnover_rate") is not None
    ):
        return features

    trade_date = getattr(getattr(stock, "record", None), "trade_date", None)
    if not trade_date:
        return features

    auction_open = db.query(StockAuctionOpen).filter(
        StockAuctionOpen.trade_date == trade_date,
        StockAuctionOpen.ts_code == stock.ts_code,
    ).first()
    if auction_open is None:
        return features

    for field in ("auction_ratio", "auction_turnover_rate"):
        if features.get(field) is None:
            value = getattr(auction_open, field, None)
            if value is not None:
                features[field] = value
                setattr(stock, field, value)
    return features


def _get_default_auction_target_versions(db: Session) -> Dict[str, ModelVersion]:
    versions: Dict[str, ModelVersion] = {}
    missing = []
    for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS:
        try:
            versions[target_model_name] = _get_model_version(db, target_model_name)
        except ValueError as exc:
            missing.append(f"{target_model_name}: {exc}")
    if missing:
        raise ValueError("默认竞价接力 active target 模型不完整: " + "; ".join(missing))
    return versions


def _target_explanation(
    model_name: str,
    mv: ModelVersion,
    probability: float,
    features: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = _load_json(mv.model_metrics, {})
    return build_single_prediction_attribution(
        probability=probability,
        model_version=mv.version,
        features=features,
        feature_contributions=_load_json(json.dumps(metrics.get("feature_importance") or {}), {}),
        bucket_report=metrics.get("bucket_report") or [],
        data_quality_warnings=[
            warning
            for warning in metrics.get("data_quality_warnings", [])
            if isinstance(warning, str)
        ],
    )


def _refresh_default_auction_relay_predictions(
    db: Session,
    record_id: int,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    if version:
        raise ValueError("default_auction_relay_v2 仅支持 active target 模型刷新")

    target_versions = _get_default_auction_target_versions(db)
    versions = {
        model_name: mv.version
        for model_name, mv in target_versions.items()
    }
    stocks = db.query(SelectedStock).filter(SelectedStock.record_id == record_id).all()
    if not stocks:
        return {
            "record_id": record_id,
            "model_name": DEFAULT_AUCTION_RELAY_MODEL_NAME,
            "updated_count": 0,
            "failed": [],
            "versions": versions,
        }

    record = db.query(SelectionRecord).filter(SelectionRecord.id == record_id).first()
    feature_payloads = build_selected_stock_feature_payloads(db, record, stocks) if record is not None else {}
    required_feature_cols = sorted(
        {
            feature_col
            for mv in target_versions.values()
            for feature_col in _load_json(mv.feature_cols, [])
        }
    )
    if record is not None and _needs_auction_open_sync(
        feature_payloads,
        [stock.ts_code for stock in stocks],
        required_feature_cols,
    ):
        AuctionDataService().sync_auction_open(record.trade_date)
        db.expire_all()
        feature_payloads = build_selected_stock_feature_payloads(db, record, stocks)

    updated_count = 0
    failed = []
    explanations = []
    try:
        for stock in stocks:
            feature_payload = feature_payloads.get(stock.ts_code, {})
            features = feature_payload.get("features") or _stock_to_features(stock, db)
            missing_features = _missing_default_auction_critical_features(features, required_feature_cols)
            if missing_features:
                failed.append(
                    {
                        "ts_code": stock.ts_code,
                        "error": "默认竞价接力预测关键特征缺失",
                        "missing_features": missing_features,
                    }
                )
                continue
            _backfill_selected_stock_auction_fields(stock, features)
            probs: Dict[str, float] = {}
            target_explanations: Dict[str, Any] = {}
            for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS:
                mv = target_versions[target_model_name]
                params = _load_json(mv.params, {})
                try:
                    probs[target_model_name] = lightgbm_service._predict_with_model_path(
                        target_model_name,
                        mv.model_path,
                        _load_json(mv.feature_cols, []),
                        features,
                        _feature_units_from_params(params),
                    )
                    target_explanations[target_model_name] = _target_explanation(
                        target_model_name,
                        mv,
                        probs[target_model_name],
                        features,
                    )
                except Exception as exc:
                    failed.append(
                        {
                            "ts_code": stock.ts_code,
                            "target_model_name": target_model_name,
                            "version": mv.version,
                            "model_path": mv.model_path,
                            "error": str(exc),
                        }
                    )
                    break
            if len(probs) != len(DEFAULT_AUCTION_TARGET_MODELS):
                continue

            relay_score = round(
                sum(
                    float(probs[target_model_name]) * weight
                    for target_model_name, _field, weight in DEFAULT_AUCTION_TARGET_MODELS
                ),
                2,
            )
            for target_model_name, field, _weight in DEFAULT_AUCTION_TARGET_MODELS:
                setattr(stock, field, probs[target_model_name])
            stock.default_relay_score = relay_score
            stock.default_relay_model_version = "|".join(
                versions[target_model_name]
                for target_model_name, _field, _weight in DEFAULT_AUCTION_TARGET_MODELS
            )
            explanations.append(
                {
                    "ts_code": stock.ts_code,
                    "name": stock.name,
                    "relay_score": relay_score,
                    "targets": target_explanations,
                }
            )
            updated_count += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "record_id": record_id,
        "model_name": DEFAULT_AUCTION_RELAY_MODEL_NAME,
        "updated_count": updated_count,
        "failed": failed,
        "versions": versions,
        "explanations": explanations,
    }


def refresh_record_predictions(
    db: Session,
    model_name: str,
    record_id: int,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    if model_name == DEFAULT_AUCTION_RELAY_MODEL_NAME:
        return _refresh_default_auction_relay_predictions(db, record_id, version)

    if model_name not in MODEL_OUTPUT_FIELDS:
        raise KeyError(model_name)

    mv = _get_model_version(db, model_name, version)
    feature_cols = _load_json(mv.feature_cols, [])
    params = _load_json(mv.params, {})
    feature_units = _feature_units_from_params(params)
    score_field, version_field = MODEL_OUTPUT_FIELDS[model_name]
    stocks = db.query(SelectedStock).filter(SelectedStock.record_id == record_id).all()
    if not stocks:
        return {"record_id": record_id, "updated_count": 0, "failed": []}

    updated_count = 0
    failed = []
    try:
        for stock in stocks:
            try:
                prob = lightgbm_service._predict_with_model_path(
                    model_name,
                    mv.model_path,
                    feature_cols,
                    _stock_to_features(stock, db),
                    feature_units,
                )
                setattr(stock, score_field, prob)
                setattr(stock, version_field, mv.version)
                updated_count += 1
            except Exception as exc:
                failed.append({"ts_code": stock.ts_code, "error": str(exc)})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "record_id": record_id,
        "model_name": model_name,
        "version": mv.version,
        "updated_count": updated_count,
        "failed": failed,
    }
