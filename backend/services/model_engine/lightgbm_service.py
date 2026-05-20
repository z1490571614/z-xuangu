"""
LightGBM 训练与预测服务
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import pandas as pd
import numpy as np
from sqlalchemy import create_engine

from backend.database import SessionLocal
from backend.models import StockFeatureSnapshot, ModelVersion

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'models')
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLS = [
    'limit_up_count_100d',
    'seal_rate_100d',
    'rise_10d_pct',
    'pre_change_pct',
    'open_change_pct',
    'auction_turnover_rate',
    'auction_ratio',
    'circ_mv',
]

# joblib 为可选依赖，用于模型持久化
try:
    import joblib
    _HAS_JOBlIB = True
except ImportError:
    joblib = None
    _HAS_JOBlIB = False
    logger.warning("joblib 未安装，LightGBM 模型将无法保存/加载。请执行: pip install joblib")

def _get_joblib():
    if not _HAS_JOBlIB:
        try:
            import joblib as jl
            globals()['joblib'] = jl
            globals()['_HAS_JOBlIB'] = True
            return jl
        except ImportError:
            return None
    return joblib


def _load_json_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _load_json_dict(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_auction_ratio_percent(value: Any) -> Any:
    try:
        if value is None:
            return value
        ratio = float(value)
    except (TypeError, ValueError):
        return value
    if 0 < ratio < 1:
        return round(ratio * 100, 4)
    return ratio


def _feature_units_from_model_version(mv: Optional[ModelVersion]) -> Dict[str, str]:
    params = _load_json_dict(getattr(mv, "params", None))
    feature_units = params.get("feature_units")
    return feature_units if isinstance(feature_units, dict) else {}


def _normalize_features_for_model(
    model_name: str,
    feature_cols: List[str],
    features: Dict[str, Any],
    feature_units: Optional[Dict[str, str]] = None,
) -> List[Any]:
    values = []
    for col in feature_cols:
        values.append(features.get(col, 0))
    return values


def _build_feature_frame_for_model(
    model_name: str,
    feature_cols: List[str],
    rows: List[Dict[str, Any]],
    feature_units: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    values = [
        _normalize_features_for_model(model_name, feature_cols, row, feature_units)
        for row in rows
    ]
    return pd.DataFrame(values, columns=feature_cols)


def get_active_model_version(model_name: str) -> Optional[ModelVersion]:
    db = SessionLocal()
    try:
        return db.query(ModelVersion).filter(
            ModelVersion.model_name == model_name,
            ModelVersion.is_active == 1,
        ).order_by(ModelVersion.id.desc()).first()
    finally:
        db.close()


def _predict_with_model_path(
    model_name: str,
    model_path: str,
    feature_cols: List[str],
    features: Dict[str, Any],
    feature_units: Optional[Dict[str, str]] = None,
) -> Optional[float]:
    if not model_path or not os.path.exists(model_path) or not feature_cols:
        return None
    joblib = _get_joblib()
    if joblib is None:
        logger.warning("joblib未安装，无法加载模型")
        return None
    model = joblib.load(model_path)
    row = _build_feature_frame_for_model(model_name, feature_cols, [features], feature_units)
    prob_result = model.predict_proba(row)
    try:
        prob = prob_result[0, 1]
    except (TypeError, IndexError):
        prob = prob_result[0][1]
    return round(float(prob) * 100, 2)


def predict_model(model_name: str, features: Dict[str, Any]) -> Optional[float]:
    """
    按模型版本表中的 active 版本预测，特征列完全读取 ModelVersion.feature_cols。
    """
    db = SessionLocal()
    try:
        mv = db.query(ModelVersion).filter(
            ModelVersion.model_name == model_name,
            ModelVersion.is_active == 1,
        ).order_by(ModelVersion.id.desc()).first()
        if mv is None:
            logger.warning(f"{model_name} active模型不存在，返回None")
            return None
        feature_cols = _load_json_list(mv.feature_cols)
        return _predict_with_model_path(
            model_name,
            mv.model_path,
            feature_cols,
            features,
            _feature_units_from_model_version(mv),
        )
    except Exception as e:
        logger.error(f"{model_name}预测失败: {e}")
        return None
    finally:
        db.close()


def batch_predict_model(
    model_name: str,
    stocks_data: List[Dict[str, Any]],
    output_key: str,
) -> List[Dict[str, Any]]:
    """批量预测，模型不可用时按 output_key 写入 None。"""
    if not stocks_data:
        return stocks_data
    db = SessionLocal()
    try:
        mv = db.query(ModelVersion).filter(
            ModelVersion.model_name == model_name,
            ModelVersion.is_active == 1,
        ).order_by(ModelVersion.id.desc()).first()
        if mv is None:
            for stock in stocks_data:
                stock[output_key] = None
            return stocks_data
        feature_cols = _load_json_list(mv.feature_cols)
        if not feature_cols or not mv.model_path or not os.path.exists(mv.model_path):
            for stock in stocks_data:
                stock[output_key] = None
            return stocks_data
        joblib = _get_joblib()
        if joblib is None:
            for stock in stocks_data:
                stock[output_key] = None
            return stocks_data
        model = joblib.load(mv.model_path)
        feature_units = _feature_units_from_model_version(mv)
        frame = _build_feature_frame_for_model(model_name, feature_cols, stocks_data, feature_units)
        probs = np.asarray(model.predict_proba(frame))[:, 1]
        for stock, prob in zip(stocks_data, probs):
            stock[output_key] = round(float(prob) * 100, 2)
            stock[f"{output_key}_model_version"] = mv.version
        return stocks_data
    except Exception as e:
        logger.error(f"{model_name}批量预测失败: {e}")
        for stock in stocks_data:
            stock[output_key] = None
        return stocks_data
    finally:
        db.close()


def train_lightgbm(start_date: str, end_date: str) -> Optional[str]:
    """
    使用历史特征数据训练LightGBM模型
    严格时间序列切分，避免数据泄露

    Returns:
        model_path: 保存的模型路径
    """
    db = SessionLocal()
    try:
        records = db.query(StockFeatureSnapshot).filter(
            StockFeatureSnapshot.trade_date.between(start_date, end_date),
            StockFeatureSnapshot.label_success.isnot(None),
        ).all()

        if not records:
            logger.warning(f"无可用训练数据 ({start_date} ~ {end_date})")
            return None

        data = []
        for r in records:
            row = {col: getattr(r, col) for col in FEATURE_COLS}
            row['label_success'] = r.label_success
            row['trade_date'] = r.trade_date
            data.append(row)

        df = pd.DataFrame(data)
        df = df.dropna(subset=FEATURE_COLS + ['label_success'])

        if len(df) < 100:
            logger.warning(f"训练样本不足: {len(df)} (需要≥100)")
            return None

        dates = sorted(df['trade_date'].unique())
        split_idx = int(len(dates) * 0.8)
        train_dates = set(dates[:split_idx])
        val_dates = set(dates[split_idx:])

        train_df = df[df['trade_date'].isin(train_dates)]
        val_df = df[df['trade_date'].isin(val_dates)]

        X_train = train_df[FEATURE_COLS].values
        y_train = train_df['label_success'].values
        X_val = val_df[FEATURE_COLS].values
        y_val = val_df['label_success'].values

        import lightgbm as lgb
        joblib = _get_joblib()
        if joblib is None:
            logger.warning("joblib未安装，跳过模型保存")
            return None
        model = lgb.LGBMClassifier(
            objective='binary',
            boosting_type='gbdt',
            learning_rate=0.05,
            num_leaves=31,
            max_depth=-1,
            n_estimators=500,
            subsample=0.8,
            colsample_bytree=0.8,
            metric='auc',
            random_state=42,
            verbose=-1,
        )

        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            eval_metric='auc',
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )

        # 评估
        from sklearn.metrics import roc_auc_score, accuracy_score
        y_pred = model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, y_pred)
        acc = accuracy_score(y_val, (y_pred > 0.5).astype(int))

        # 保存模型
        version = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_name = f"active_auction_lgbm_{version}.pkl"
        model_path = os.path.join(MODEL_DIR, model_name)
        _get_joblib().dump(model, model_path)

        # 保存当前为默认
        latest_path = os.path.join(MODEL_DIR, "active_auction_lgbm.pkl")
        _get_joblib().dump(model, latest_path)

        # 记录模型版本
        feature_importance = dict(zip(FEATURE_COLS, model.feature_importances_.tolist()))
        mv = ModelVersion(
            model_name="active_auction_lgbm",
            version=version,
            train_start_date=start_date,
            train_end_date=end_date,
            feature_cols=json.dumps(FEATURE_COLS, ensure_ascii=False),
            model_metrics=json.dumps({"auc": round(auc, 4), "accuracy": round(acc, 4)}, ensure_ascii=False),
            model_path=model_path,
            params=json.dumps(model.get_params(), ensure_ascii=False),
            is_active=1,
        )
        db.add(mv)
        db.commit()

        logger.info(f"LightGBM训练完成: AUC={auc:.4f}, ACC={acc:.4f}, 样本={len(df)}, 模型={model_path}")
        return model_path

    except ImportError:
        logger.error("lightgbm未安装，跳过训练")
        return None
    except Exception as e:
        logger.error(f"LightGBM训练失败: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def predict_lightgbm(features: Dict[str, Any]) -> Optional[float]:
    """
    使用最新模型预测

    Args:
        features: 特征字典

    Returns:
        model_score: 模型预测得分(0-100)
    """
    version_score = predict_model("active_auction_lgbm", features)
    if version_score is not None:
        return version_score

    model_path = os.path.join(MODEL_DIR, "active_auction_lgbm.pkl")
    if not os.path.exists(model_path):
        logger.warning("LightGBM模型不存在，返回None")
        return None

    try:
        joblib = _get_joblib()
        if joblib is None:
            logger.warning("joblib未安装，无法加载模型")
            return None
        model = joblib.load(model_path)
        row = pd.DataFrame([[features.get(col, 0) for col in FEATURE_COLS]], columns=FEATURE_COLS)
        prob = model.predict_proba(row)[0, 1]
        return round(float(prob) * 100, 2)
    except Exception as e:
        logger.error(f"LightGBM预测失败: {e}")
        return None


def nightly_train():
    """夜间自动训练 active_auction_lgbm。"""
    end_date = datetime.now().strftime('%Y%m%d')
    from datetime import timedelta
    start = datetime.now() - timedelta(days=730)
    start_date = start.strftime('%Y%m%d')
    logger.info(f"夜间训练开始: {start_date} ~ {end_date}")
    result_active = train_lightgbm(start_date, end_date)
    return {"active_auction_lgbm": result_active}


def batch_predict_before_selection(stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    选股前批量预测
    对候选股列表添加model_score
    """
    model_path = os.path.join(MODEL_DIR, "active_auction_lgbm.pkl")
    if not os.path.exists(model_path):
        for s in stocks_data:
            s["model_score"] = None
        return stocks_data

    try:
        joblib = _get_joblib()
        if joblib is None:
            for s in stocks_data:
                s["model_score"] = None
            return stocks_data
        model = joblib.load(model_path)
        rows = []
        for s in stocks_data:
            rows.append([s.get(col, 0) for col in FEATURE_COLS])
        frame = pd.DataFrame(rows, columns=FEATURE_COLS)
        probs = np.asarray(model.predict_proba(frame))[:, 1]

        for s, prob in zip(stocks_data, probs):
            s["model_score"] = round(float(prob) * 100, 2)
        return stocks_data
    except Exception as e:
        logger.error(f"批量预测失败: {e}")
        for s in stocks_data:
            s["model_score"] = None
        return stocks_data
