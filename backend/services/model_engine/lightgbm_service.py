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
    "market_height_rank",
    "limit_up_count_100d",
    "seal_rate_100d",
    "rise_5d_pct",
    "rise_10d_pct",
    "pre_change_pct",
    "open_change_pct",
    "auction_ratio",
    "auction_turnover_rate",
    "circ_mv",
    "sector_change_pct",
    "sector_limit_up_count",
]

LEADER_MAIN_T0_THRESHOLD_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

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
    model_path: str,
    feature_cols: List[str],
    features: Dict[str, Any],
) -> Optional[float]:
    if not model_path or not os.path.exists(model_path) or not feature_cols:
        return None
    joblib = _get_joblib()
    if joblib is None:
        logger.warning("joblib未安装，无法加载模型")
        return None
    model = joblib.load(model_path)
    row = np.array([[features.get(col, 0) for col in feature_cols]])
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
        return _predict_with_model_path(mv.model_path, feature_cols, features)
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
        rows = [[stock.get(col, 0) for col in feature_cols] for stock in stocks_data]
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


def train_leader_main_t0_lgbm(start_date: str, end_date: str) -> Optional[str]:
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
        df["label_t0_limit_success"] = pd.to_numeric(
            df["label_t0_limit_success"],
            errors="coerce",
        )
        df = df.dropna(subset=["label_t0_limit_success"])
        if len(df) < 100:
            logger.warning(f"龙头主升T+0训练样本不足: {len(df)} (需要≥100)")
            return None

        dates = sorted(df["trade_date"].unique())
        train_end = max(1, int(len(dates) * 0.7))
        val_end = max(train_end + 1, int(len(dates) * 0.9))
        train_dates = set(dates[:train_end])
        val_dates = set(dates[train_end:val_end])
        test_dates = set(dates[val_end:]) or val_dates

        train_df = df[df["trade_date"].isin(train_dates)]
        val_df = df[df["trade_date"].isin(val_dates)]
        test_df = df[df["trade_date"].isin(test_dates)]

        import lightgbm as lgb
        joblib = _get_joblib()
        if joblib is None:
            logger.warning("joblib未安装，跳过模型保存")
            return None

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
        )
        model.fit(
            train_df[LEADER_MAIN_T0_FEATURE_COLS].values,
            train_df["label_t0_limit_success"].values,
            eval_set=[(val_df[LEADER_MAIN_T0_FEATURE_COLS].values, val_df["label_t0_limit_success"].values)],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )

        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

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
        }

        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = os.path.join(MODEL_DIR, f"{LEADER_MAIN_T0_MODEL_NAME}_{version}.pkl")
        joblib.dump(model, model_path)

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
                },
                ensure_ascii=False,
            ),
            is_active=1,
        )
        db.add(mv)
        db.commit()
        logger.info(f"龙头主升T+0模型训练完成: 样本={len(df)}, 模型={model_path}")
        return model_path
    except ImportError:
        logger.error("lightgbm或sklearn未安装，跳过训练")
        return None
    except Exception as e:
        logger.error(f"龙头主升T+0模型训练失败: {e}")
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
        row = np.array([[features.get(col, 0) for col in FEATURE_COLS]])
        prob = model.predict_proba(row)[0, 1]
        return round(float(prob) * 100, 2)
    except Exception as e:
        logger.error(f"LightGBM预测失败: {e}")
        return None


def nightly_train():
    """夜间自动训练"""
    end_date = datetime.now().strftime('%Y%m%d')
    from datetime import timedelta
    start = datetime.now() - timedelta(days=730)
    start_date = start.strftime('%Y%m%d')
    logger.info(f"夜间训练开始: {start_date} ~ {end_date}")
    return train_lightgbm(start_date, end_date)


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
