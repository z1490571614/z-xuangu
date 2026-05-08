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
