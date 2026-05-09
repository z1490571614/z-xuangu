import json
import sys
from types import SimpleNamespace

import numpy as np

from backend.models import ModelVersion, LeaderMainT0TrainingSample
from backend.services.model_engine import lightgbm_service


def test_predict_model_uses_active_model_version_feature_columns(db, monkeypatch, tmp_path):
    model_path = tmp_path / "fake_model.pkl"
    model_path.write_text("fake")

    db.add(
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v1",
            feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
            model_path=str(model_path),
            is_active=1,
        )
    )
    db.commit()

    captured = {}

    class FakeModel:
        def predict_proba(self, rows):
            captured["rows"] = rows.tolist()
            return [[0.2, 0.8]]

    class FakeJoblib:
        def load(self, path):
            assert path == str(model_path)
            return FakeModel()

    monkeypatch.setattr(lightgbm_service, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(lightgbm_service, "SessionLocal", lambda: db)

    prob = lightgbm_service.predict_model(
        "leader_main_t0_lgbm",
        {
            "auction_ratio": 8.19,
            "auction_turnover_rate": 0.83,
            "circ_mv": 120,
        },
    )

    assert prob == 80.0
    assert captured["rows"] == [[8.19, 0.83]]


def test_predict_model_degrades_when_active_model_missing(db, monkeypatch):
    monkeypatch.setattr(lightgbm_service, "SessionLocal", lambda: db)

    assert lightgbm_service.predict_model("leader_main_t0_lgbm", {"auction_ratio": 8.19}) is None


def test_train_leader_main_t0_keeps_rows_with_missing_optional_features(db, monkeypatch, tmp_path):
    for i in range(100):
        db.add(
            LeaderMainT0TrainingSample(
                strategy_version="leader_main_t0",
                trade_date=f"209901{(i // 10) + 1:02d}",
                ts_code=f"900{i:03d}.SZ",
                limit_up_streak=1,
                market_height_rank=5,
                limit_up_count_100d=4,
                seal_rate_100d=None,
                rise_5d_pct=8.0,
                rise_10d_pct=12.0,
                pre_change_pct=9.8,
                open_change_pct=5.0,
                auction_ratio=8.0,
                auction_turnover_rate=0.8,
                auction_amount=5000.0,
                auction_vwap_gap_pct=0.2,
                circ_mv=120.0,
                sector_change_pct=0.0,
                sector_limit_up_count=0,
                sector_hot_rank=None,
                label_t0_limit_success=i % 2,
            )
        )
    db.commit()

    captured = {}

    class FakeModel:
        def __init__(self, **params):
            self.params = params
            self.feature_importances_ = np.zeros(len(lightgbm_service.LEADER_MAIN_T0_FEATURE_COLS), dtype=int)

        def fit(self, X, y, **kwargs):
            captured["train_shape"] = X.shape
            return self

        def predict_proba(self, X):
            return np.array([[0.4, 0.6] for _ in range(len(X))])

        def get_params(self):
            return self.params

    class FakeJoblib:
        def dump(self, model, path):
            with open(path, "wb") as f:
                f.write(b"fake")

    monkeypatch.setitem(
        sys.modules,
        "lightgbm",
        SimpleNamespace(
            LGBMClassifier=FakeModel,
            early_stopping=lambda *_args, **_kwargs: None,
            log_evaluation=lambda *_args, **_kwargs: None,
        ),
    )
    monkeypatch.setitem(sys.modules, "sklearn", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "sklearn.metrics",
        SimpleNamespace(
            accuracy_score=lambda y_true, y_pred: 0.5,
            precision_score=lambda y_true, y_pred, zero_division=0: 0.5,
            recall_score=lambda y_true, y_pred, zero_division=0: 0.5,
            roc_auc_score=lambda y_true, y_prob: 0.5,
        ),
    )
    monkeypatch.setattr(lightgbm_service, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(lightgbm_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(lightgbm_service, "MODEL_DIR", str(tmp_path))

    model_path = lightgbm_service.train_leader_main_t0_lgbm("20990101", "20990110")

    assert model_path is not None
    assert captured["train_shape"][0] == 70
    mv = db.query(ModelVersion).filter_by(
        model_name="leader_main_t0_lgbm",
        train_start_date="20990101",
        train_end_date="20990110",
        is_active=1,
    ).one()
    assert json.loads(mv.model_metrics)["sample_count"] == 100
    threshold_eval = json.loads(mv.model_metrics)["threshold_evaluation"]
    assert threshold_eval[0]["threshold"] == 0.1
    assert threshold_eval[-1]["threshold"] == 0.5
    assert threshold_eval[-1]["hit_count"] == 10
    assert threshold_eval[-1]["precision"] == 0.5
