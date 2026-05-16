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
from backend.models import StockFeatureSnapshot, ModelVersion, LeaderMainT0TrainingSample

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

LEADER_MAIN_T0_MODEL_NAME = "leader_main_t0_lgbm"
LEADER_MAIN_T0_FEATURE_COLS = [
    "limit_up_streak",
    "limit_up_count_100d",
    "seal_rate_100d",
    "rise_10d_pct",
    "pre_change_pct",
    "open_change_pct",
    "auction_ratio",
    "auction_turnover_rate",
    "circ_mv",
]

LEADER_MAIN_T0_THRESHOLD_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
DEFAULT_LEADER_MAIN_T0_PARAMS = {
    "test_size": 0.10,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "num_leaves": 31,
    "is_unbalance": True,
    "max_depth": -1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "early_stopping_rounds": 50,
    "random_seed": 42,
}

# joblib 为可选依赖，用于模型持久化
try:
    import joblib
    _HAS_JOBlIB = True
except ImportError:
    joblib = None
    _HAS_JOBlIB = False
    logger.warning("joblib 未安装，LightGBM 模型将无法保存/加载。请执行: pip install joblib")

try:
    import shap as _shap
    _HAS_SHAP = True
except ImportError:
    _shap = None
    _HAS_SHAP = False


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


def _normalize_auction_ratio_fraction(value: Any) -> Any:
    try:
        if value is None:
            return value
        ratio = float(value)
    except (TypeError, ValueError):
        return value
    if ratio > 1:
        return ratio / 100
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
    feature_units = feature_units or {}
    values = []
    for col in feature_cols:
        value = features.get(col, 0)
        if model_name == LEADER_MAIN_T0_MODEL_NAME and col == "auction_ratio":
            unit = feature_units.get("auction_ratio")
            if unit == "percent":
                value = _normalize_auction_ratio_percent(value)
            else:
                # Legacy leader_main_t0 models were trained with 0.04~0.30.
                value = _normalize_auction_ratio_fraction(value)
        values.append(value)
    return values


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
    row = np.array([_normalize_features_for_model(model_name, feature_cols, features, feature_units)])
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
        rows = [
            _normalize_features_for_model(model_name, feature_cols, stock, feature_units)
            for stock in stocks_data
        ]
        probs = model.predict_proba(np.array(rows))[:, 1]
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


def evaluate_leader_main_t0_thresholds(
    y_true,
    y_prob,
    eval_df: Optional[pd.DataFrame] = None,
    thresholds: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """评估不同概率阈值下的命中数、查准率、召回率与收益近似。"""
    from sklearn.metrics import accuracy_score, precision_score, recall_score

    y_true_arr = np.asarray(y_true)
    y_prob_arr = np.asarray(y_prob)
    results: List[Dict[str, Any]] = []
    for threshold in thresholds or LEADER_MAIN_T0_THRESHOLD_GRID:
        y_pred = (y_prob_arr >= threshold).astype(int)
        picked_mask = y_pred == 1
        picked = eval_df[picked_mask] if eval_df is not None else None
        avg_return = None
        max_drawdown_like = None
        if picked is not None and not picked.empty:
            if "t0_close_return" in picked.columns:
                avg_return = round(float(pd.to_numeric(picked["t0_close_return"], errors="coerce").mean()), 4)
            if "t0_low_return" in picked.columns:
                max_drawdown_like = round(float(pd.to_numeric(picked["t0_low_return"], errors="coerce").min()), 4)
        results.append(
            {
                "threshold": round(float(threshold), 2),
                "precision": round(float(precision_score(y_true_arr, y_pred, zero_division=0)), 4),
                "recall": round(float(recall_score(y_true_arr, y_pred, zero_division=0)), 4),
                "hit_count": int(picked_mask.sum()),
                "avg_return": avg_return,
                "max_drawdown_like": max_drawdown_like,
                "accuracy": round(float(accuracy_score(y_true_arr, y_pred)), 4),
            }
        )
    return results


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


def _compute_shap_importance(model, X, feature_cols: List[str]) -> Optional[Dict[str, float]]:
    """计算 SHAP 特征重要性（mean|SHAP|），shap 不可用时返回 None。"""
    if not _HAS_SHAP or _shap is None or X is None or len(X) == 0:
        return None
    try:
        explainer = _shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        mean_abs = np.abs(shap_values).mean(axis=0)
        return {col: round(float(v), 6) for col, v in zip(feature_cols, mean_abs)}
    except Exception as e:
        logger.warning(f"SHAP计算失败: {e}")
        return None


def explain_leader_main_t0_prediction(features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """对单次龙头T+0预测输出 SHAP 特征贡献。

    Returns:
        {"prediction": 概率值, "base_value": 基准值, "contributions": {特征: 贡献值}}
    """
    if not _HAS_SHAP or _shap is None:
        return None
    db = SessionLocal()
    try:
        mv = db.query(ModelVersion).filter(
            ModelVersion.model_name == LEADER_MAIN_T0_MODEL_NAME,
            ModelVersion.is_active == 1,
        ).order_by(ModelVersion.id.desc()).first()
        if mv is None or not mv.model_path or not os.path.exists(mv.model_path):
            return None
        feature_cols = _load_json_list(mv.feature_cols)
        if not feature_cols:
            return None
        joblib = _get_joblib()
        if joblib is None:
            return None
        model = joblib.load(mv.model_path)
        explainer = _shap.TreeExplainer(model)
        row = np.array([[features.get(col, 0) for col in feature_cols]])
        shap_values = explainer.shap_values(row)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        prob = model.predict_proba(row)[0, 1]
        return {
            "prediction": round(float(prob) * 100, 2),
            "base_value": round(float(explainer.expected_value), 4)
            if not isinstance(explainer.expected_value, list)
            else round(float(explainer.expected_value[1]), 4),
            "contributions": {
                col: round(float(shap_values[0, i]), 6)
                for i, col in enumerate(feature_cols)
            },
        }
    except Exception as e:
        logger.error(f"SHAP解释失败: {e}")
        return None
    finally:
        db.close()


def _time_series_cv(
    df: pd.DataFrame,
    feature_cols: List[str],
    dates: List[str],
    n_folds: int = 3,
    min_train_samples: int = 30,
    min_test_samples: int = 5,
) -> Optional[List[Dict[str, Any]]]:
    """滚动窗口时间序列交叉验证。

    将日期按时间顺序切为 n_folds+1 段，每段依次作为测试集，
    该段之前的所有数据作为训练集。返回各折指标列表。
    日期数或样本数不足时返回 None，降级为单次切分。
    """
    if len(dates) < (n_folds + 1) * 2:
        return None

    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

    fold_size = max(1, len(dates) // (n_folds + 1))
    fold_metrics: List[Dict[str, Any]] = []

    for i in range(1, n_folds + 1):
        split_idx = i * fold_size
        train_dates = set(dates[:split_idx])
        test_dates_set = set(dates[split_idx : split_idx + fold_size])

        train_fold = df[df["trade_date"].isin(train_dates)]
        test_fold = df[df["trade_date"].isin(test_dates_set)]

        if len(train_fold) < min_train_samples or len(test_fold) < min_test_samples:
            continue
        if train_fold["label_t0_limit_success"].nunique() < 2:
            continue
        if test_fold["label_t0_limit_success"].nunique() < 2:
            continue

        model = lgb.LGBMClassifier(
            objective="binary",
            boosting_type="gbdt",
            learning_rate=0.05,
            num_leaves=31,
            n_estimators=500,
            subsample=0.8,
            colsample_bytree=0.8,
            metric="auc",
            random_state=42,
            verbose=-1,
            is_unbalance=True,
        )
        model.fit(
            train_fold[feature_cols].values,
            train_fold["label_t0_limit_success"].values,
        )

        y_true = test_fold["label_t0_limit_success"].values
        y_prob = model.predict_proba(test_fold[feature_cols].values)[:, 1]
        y_pred = (y_prob > 0.5).astype(int)

        fold_metrics.append({
            "fold": i,
            "train_samples": int(len(train_fold)),
            "test_samples": int(len(test_fold)),
            "train_date_range": [min(train_dates), max(train_dates)],
            "test_date_range": [min(test_dates_set), max(test_dates_set)],
            "auc": round(float(roc_auc_score(y_true, y_prob)), 4),
            "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "threshold_evaluation": evaluate_leader_main_t0_thresholds(
                y_true, y_prob, test_fold,
            ),
        })

    if not fold_metrics:
        return None

    aucs = [m["auc"] for m in fold_metrics if m["auc"] is not None]
    return {
        "folds": fold_metrics,
        "n_folds": len(fold_metrics),
        "auc_mean": round(float(np.mean(aucs)), 4) if aucs else None,
        "auc_std": round(float(np.std(aucs)), 4) if aucs else None,
    }


def _train_leader_main_t0_lgbm_impl(
    start_date: str,
    end_date: str,
    config: Dict[str, Any],
    activate: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    训练龙头主升 T+0 非一字涨停成功率模型。

    样本限定为候选池内已打标签数据，按交易日期 70/20/10 切分。
    """
    db = SessionLocal()
    try:
        records = db.query(LeaderMainT0TrainingSample).filter(
            LeaderMainT0TrainingSample.trade_date.between(start_date, end_date),
            LeaderMainT0TrainingSample.label_t0_limit_success.isnot(None),
        ).all()
        if not records:
            logger.warning(f"无可用龙头主升T+0训练数据 ({start_date} ~ {end_date})")
            return None

        data = []
        for r in records:
            row = {col: getattr(r, col, None) for col in LEADER_MAIN_T0_FEATURE_COLS}
            row["label_t0_limit_success"] = r.label_t0_limit_success
            row["trade_date"] = r.trade_date
            row["t0_close_return"] = r.t0_close_return
            row["t0_low_return"] = r.t0_low_return
            data.append(row)

        df = pd.DataFrame(data).dropna(subset=["label_t0_limit_success"])
        for col in LEADER_MAIN_T0_FEATURE_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["auction_ratio"] = df["auction_ratio"].apply(_normalize_auction_ratio_percent)
        df["label_t0_limit_success"] = pd.to_numeric(
            df["label_t0_limit_success"],
            errors="coerce",
        )
        df = df.dropna(subset=["label_t0_limit_success"])
        if len(df) < 100:
            logger.warning(f"龙头主升T+0训练样本不足: {len(df)} (需要≥100)")
            return None

        import lightgbm as lgb
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

        joblib = _get_joblib()
        if joblib is None:
            logger.warning("joblib未安装，跳过模型保存")
            return None

        dates = sorted(df["trade_date"].unique())

        # ---------- 滚动窗口交叉验证 ----------
        cv_metrics = _time_series_cv(
            df,
            LEADER_MAIN_T0_FEATURE_COLS,
            dates,
            n_folds=3,
            min_train_samples=30,
            min_test_samples=5,
        )

        # ---------- 最终模型：70/20/10 时间序列切分 ----------
        train_end = max(1, int(len(dates) * 0.7))
        val_end = max(train_end + 1, int(len(dates) * 0.9))
        train_dates = set(dates[:train_end])
        val_dates = set(dates[train_end:val_end])
        test_dates = set(dates[val_end:]) or val_dates

        train_df = df[df["trade_date"].isin(train_dates)]
        val_df = df[df["trade_date"].isin(val_dates)]
        test_df = df[df["trade_date"].isin(test_dates)]

        model = lgb.LGBMClassifier(
            objective="binary",
            boosting_type="gbdt",
            learning_rate=config["learning_rate"],
            num_leaves=config["num_leaves"],
            n_estimators=config["n_estimators"],
            subsample=config["subsample"],
            colsample_bytree=config["colsample_bytree"],
            max_depth=config["max_depth"],
            metric="auc",
            random_state=config["random_seed"],
            verbose=-1,
            is_unbalance=config["is_unbalance"],
        )
        model.fit(
            train_df[LEADER_MAIN_T0_FEATURE_COLS].values,
            train_df["label_t0_limit_success"].values,
            eval_set=[(val_df[LEADER_MAIN_T0_FEATURE_COLS].values, val_df["label_t0_limit_success"].values)],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(config["early_stopping_rounds"]), lgb.log_evaluation(0)],
        )

        y_test = test_df["label_t0_limit_success"].values
        y_prob = model.predict_proba(test_df[LEADER_MAIN_T0_FEATURE_COLS].values)[:, 1]
        y_pred = (y_prob > 0.5).astype(int)
        metrics = {
            "auc": round(float(roc_auc_score(y_test, y_prob)), 4) if len(set(y_test)) > 1 else None,
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
            "sample_count": int(len(df)),
            "train_dates": len(train_dates),
            "validation_dates": len(val_dates),
            "test_dates": len(test_dates),
            "threshold_evaluation": evaluate_leader_main_t0_thresholds(
                y_test,
                y_prob,
                test_df,
            ),
            "feature_importance": dict(zip(LEADER_MAIN_T0_FEATURE_COLS, model.feature_importances_.tolist())),
            "shap_importance": _compute_shap_importance(
                model, test_df[LEADER_MAIN_T0_FEATURE_COLS].values, LEADER_MAIN_T0_FEATURE_COLS
            ),
            "rolling_cv": cv_metrics,
        }

        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = os.path.join(MODEL_DIR, f"{LEADER_MAIN_T0_MODEL_NAME}_{version}.pkl")
        joblib.dump(model, model_path)

        if activate:
            db.query(ModelVersion).filter(
                ModelVersion.model_name == LEADER_MAIN_T0_MODEL_NAME,
                ModelVersion.is_active == 1,
            ).update({"is_active": 0})
        mv = ModelVersion(
            model_name=LEADER_MAIN_T0_MODEL_NAME,
            version=version,
            train_start_date=start_date,
            train_end_date=end_date,
            feature_cols=json.dumps(LEADER_MAIN_T0_FEATURE_COLS, ensure_ascii=False),
            model_metrics=json.dumps(metrics, ensure_ascii=False),
            model_path=model_path,
            params=json.dumps(
                {
                    "model_params": model.get_params(),
                    "label_rule": "non_one_line and touched_limit and closed_limit",
                    "split": "date_ordered_70_20_10",
                    "cv": "rolling_window_3_fold" if cv_metrics else "single_split",
                    "feature_units": {"auction_ratio": "percent"},
                    "training_params": config,
                },
                ensure_ascii=False,
            ),
            is_active=1 if activate else 0,
        )
        db.add(mv)
        db.commit()
        logger.info(f"龙头主升T+0模型训练完成: 样本={len(df)}, 模型={model_path}")
        return {
            "model_path": model_path,
            "version": version,
            "metrics": metrics,
            "params": config,
        }
    except ImportError:
        logger.error("lightgbm或sklearn未安装，跳过训练")
        return None
    except Exception as e:
        logger.error(f"龙头主升T+0模型训练失败: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def train_leader_main_t0_lgbm_configurable(
    start_date: str,
    end_date: str,
    params: Optional[Dict[str, Any]] = None,
    activate: bool = True,
) -> Optional[Dict[str, Any]]:
    config = {**DEFAULT_LEADER_MAIN_T0_PARAMS, **(params or {})}
    return _train_leader_main_t0_lgbm_impl(start_date, end_date, config, activate=activate)


def train_leader_main_t0_lgbm(start_date: str, end_date: str) -> Optional[str]:
    result = train_leader_main_t0_lgbm_configurable(start_date, end_date, activate=True)
    return result.get("model_path") if result else None


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
        row = np.array([[features.get(col, 0) for col in FEATURE_COLS]])
        prob = model.predict_proba(row)[0, 1]
        return round(float(prob) * 100, 2)
    except Exception as e:
        logger.error(f"LightGBM预测失败: {e}")
        return None


def nightly_train():
    """夜间自动训练——同时更新 active_auction_lgbm 和 leader_main_t0_lgbm。"""
    end_date = datetime.now().strftime('%Y%m%d')
    from datetime import timedelta
    start = datetime.now() - timedelta(days=730)
    start_date = start.strftime('%Y%m%d')
    logger.info(f"夜间训练开始: {start_date} ~ {end_date}")
    result_active = train_lightgbm(start_date, end_date)
    result_t0 = train_leader_main_t0_lgbm(start_date, end_date)
    return {"active_auction_lgbm": result_active, "leader_main_t0_lgbm": result_t0}


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
        probs = model.predict_proba(np.array(rows))[:, 1]

        for s, prob in zip(stocks_data, probs):
            s["model_score"] = round(float(prob) * 100, 2)
        return stocks_data
    except Exception as e:
        logger.error(f"批量预测失败: {e}")
        for s in stocks_data:
            s["model_score"] = None
        return stocks_data


def batch_predict_leader_main_t0(stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """为龙头主升候选股添加 T+0 非一字涨停成功率，不影响原 final_score。"""
    return batch_predict_model(
        LEADER_MAIN_T0_MODEL_NAME,
        stocks_data,
        "t0_limit_success_prob",
    )
