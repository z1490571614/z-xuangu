"""
模型中心管理服务。
"""
import json
import os
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.models import ModelVersion, SelectedStock
from backend.services.model_engine import lightgbm_service


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


def activate_model_version(db: Session, model_name: str, version: str) -> Dict[str, Any]:
    mv = _get_model_version(db, model_name, version)
    db.query(ModelVersion).filter(ModelVersion.model_name == model_name).update({"is_active": 0})
    mv.is_active = 1
    db.commit()
    return {
        "model_name": model_name,
        "active_version": version,
        "message": f"已激活模型版本 {version}",
    }


def _stock_to_features(stock: SelectedStock) -> Dict[str, Any]:
    return {
        column.name: getattr(stock, column.name)
        for column in SelectedStock.__table__.columns
    }


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

    updated_count = 0
    failed = []
    try:
        for stock in stocks:
            features = _stock_to_features(stock)
            probs: Dict[str, float] = {}
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
                    _stock_to_features(stock),
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
