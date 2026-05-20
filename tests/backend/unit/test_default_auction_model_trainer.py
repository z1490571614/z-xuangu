import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.models import DefaultAuctionTrainingSample, ModelTrainingJob, ModelVersion
from backend.services.model_engine import default_auction_model_trainer as trainer


def _clear_model_tables(db):
    db.query(ModelTrainingJob).delete()
    db.query(ModelVersion).delete()
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()


def _add_default_auction_samples(db, count=120):
    for i in range(count):
        db.add(
            DefaultAuctionTrainingSample(
                trade_date=f"209901{(i // 12) + 1:02d}",
                ts_code=f"900{i:03d}.SZ",
                strategy_name="default",
                strategy_version="default_auction_v2",
                sample_source="replay_backtest",
                auction_source="selected_stock",
                auction_ratio_unit="percent",
                auction_turnover_rate_basis="production_default",
                feature_snapshot_time="2099-01-01T09:31:00",
                feature_json=json.dumps(
                    {
                        "auction_ratio": 8 + i % 5,
                        "auction_turnover_rate": 0.8 + (i % 4) * 0.1,
                        "open_change_pct": 4 + (i % 3),
                        "pre_change_pct": 9 + (i % 2),
                        "limit_up_count": 4 + (i % 3),
                        "touch_days": 8 + (i % 4),
                        "limit_up_days": 5 + (i % 3),
                        "seal_rate": 70 + (i % 20),
                        "rise_10d_pct": 10 + (i % 8),
                        "circ_mv": 100 + i,
                        "prev_turnover_rate": 12 + (i % 5),
                        "rule_score": 60 + (i % 10),
                        "final_score": 70 + (i % 10),
                        "risk_tags_count": i % 3,
                        "score_level": "A",
                    },
                    ensure_ascii=False,
                ),
                label_t0_limit_success=i % 2,
                label_t1_premium_success=1 if i % 3 == 0 else 0,
                label_t1_continue_limit=1 if i % 5 == 0 else 0,
            )
        )
    db.commit()


def _patch_fake_lightgbm(monkeypatch, tmp_path):
    class FakeModel:
        def __init__(self, **params):
            self.params = params
            self.feature_importances_ = None

        def fit(self, X, y, **kwargs):
            self.feature_importances_ = np.arange(1, len(X[0]) + 1, dtype=int)
            return self

        def predict_proba(self, X):
            rows = []
            for i in range(len(X)):
                prob = 0.75 if i % 2 == 0 else 0.25
                rows.append([1 - prob, prob])
            return np.array(rows)

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
            early_stopping=lambda rounds: ("early", rounds),
            log_evaluation=lambda period: ("log", period),
        ),
    )
    monkeypatch.setattr(trainer, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(trainer, "MODEL_DIR", str(tmp_path))


def test_default_auction_feature_list_includes_auction_liquidity_and_pre_change():
    assert "auction_amount" in trainer.DEFAULT_AUCTION_FEATURES
    assert "auction_volume" in trainer.DEFAULT_AUCTION_FEATURES
    assert "pre_change_pct" in trainer.DEFAULT_AUCTION_FEATURES


def test_records_to_rows_deduplicates_date_code_preferring_real_selected():
    replay = DefaultAuctionTrainingSample(
        trade_date="20990102",
        ts_code="900001.SZ",
        sample_source="replay_backtest",
        feature_json=json.dumps({"auction_ratio": 8.0}, ensure_ascii=False),
        label_t1_premium_success=0,
    )
    real = DefaultAuctionTrainingSample(
        trade_date="20990102",
        ts_code="900001.SZ",
        sample_source="real_selected",
        feature_json=json.dumps({"auction_ratio": 12.0}, ensure_ascii=False),
        label_t1_premium_success=1,
    )
    other = DefaultAuctionTrainingSample(
        trade_date="20990102",
        ts_code="900002.SZ",
        sample_source="replay_backtest",
        feature_json=json.dumps({"auction_ratio": 9.0}, ensure_ascii=False),
        label_t1_premium_success=0,
    )

    rows = trainer._records_to_rows([replay, real, other], "label_t1_premium_success")

    assert [(row["ts_code"], row["sample_source"], row["auction_ratio"], row["label"]) for row in rows] == [
        ("900001.SZ", "real_selected", 12.0, 1),
        ("900002.SZ", "replay_backtest", 9.0, 0),
    ]


def test_train_target_model_creates_model_version(db, monkeypatch, tmp_path):
    _clear_model_tables(db)
    _add_default_auction_samples(db)
    _patch_fake_lightgbm(monkeypatch, tmp_path)

    result = trainer.train_default_auction_target_model(
        db,
        model_name="default_auction_t0_limit_lgbm",
        label_column="label_t0_limit_success",
        start_date="20990101",
        end_date="20990110",
        params=trainer.DEFAULT_PARAM_PROFILES[0]["params"],
        activate=False,
    )

    assert result["version"]
    assert result["model_path"]
    assert result["metrics"]["sample_count"] == 120
    assert result["metrics"]["validation_count"] > 0
    assert result["metrics"]["test_count"] > 0
    assert result["metrics"]["evaluation_split"] == "test"
    assert result["metrics"]["test_date_range"] == ["20990109", "20990110"]
    assert "feature_quality_report" in result["metrics"]
    assert "training_attribution" in result["metrics"]
    assert "permutation_importance" in result["metrics"]
    assert "shap_importance" in result["metrics"]
    assert "single_feature_bucket_lift" in result["metrics"]
    assert "drop_one_feature_delta" in result["metrics"]
    assert result["metrics"]["feature_quality_report"]["source_mix_ratio"] == {"replay_backtest": 1.0}
    assert "score_level" not in result["metrics"]["usable_features"]
    mv = db.query(ModelVersion).filter_by(model_name="default_auction_t0_limit_lgbm").one()
    assert mv.is_active == 0
    assert json.loads(mv.params)["feature_units"]["auction_ratio"] == "percent"


def test_train_target_model_filters_unknown_labels_before_training(db, monkeypatch, tmp_path):
    _clear_model_tables(db)
    _add_default_auction_samples(db)
    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="900000.SZ").one()
    sample.label_t0_limit_success = None
    db.commit()
    _patch_fake_lightgbm(monkeypatch, tmp_path)

    result = trainer.train_default_auction_target_model(
        db,
        "default_auction_t0_limit_lgbm",
        "label_t0_limit_success",
        params=trainer.DEFAULT_PARAM_PROFILES[0]["params"],
        activate=False,
        start_date="20990101",
        end_date="20990110",
    )

    assert result["metrics"]["sample_count"] == 119


def test_train_target_model_allows_disabling_early_stopping(db, monkeypatch, tmp_path):
    _clear_model_tables(db)
    _add_default_auction_samples(db)
    captured = {"early_stopping_rounds": [], "fit_callbacks": None}

    class FakeModel:
        def __init__(self, **params):
            self.params = params
            self.feature_importances_ = None
            self.best_iteration_ = 25

        def fit(self, X, y, **kwargs):
            self.feature_importances_ = np.arange(1, len(X[0]) + 1, dtype=int)
            captured["fit_callbacks"] = kwargs.get("callbacks")
            return self

        def predict_proba(self, X):
            return np.array([[0.25, 0.75] if i % 2 == 0 else [0.75, 0.25] for i in range(len(X))])

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
            early_stopping=lambda rounds: captured["early_stopping_rounds"].append(rounds) or ("early", rounds),
            log_evaluation=lambda period: ("log", period),
        ),
    )
    monkeypatch.setattr(trainer, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(trainer, "MODEL_DIR", str(tmp_path))

    result = trainer.train_default_auction_target_model(
        db,
        "default_auction_t0_limit_lgbm",
        "label_t0_limit_success",
        params={**trainer.DEFAULT_PARAM_PROFILES[0]["params"], "early_stopping_rounds": 0},
        start_date="20990101",
        end_date="20990110",
    )

    assert captured["early_stopping_rounds"] == []
    assert captured["fit_callbacks"] == [("log", 0)]
    assert result["metrics"]["trained_tree_count"] == 25


def test_train_target_model_raises_when_samples_are_insufficient(db):
    _clear_model_tables(db)
    _add_default_auction_samples(db, count=20)

    with pytest.raises(ValueError, match="训练样本不足"):
        trainer.train_default_auction_target_model(
            db,
            "default_auction_t0_limit_lgbm",
            "label_t0_limit_success",
            params=trainer.DEFAULT_PARAM_PROFILES[0]["params"],
            start_date="20990101",
            end_date="20990110",
        )


def test_train_target_model_reports_insufficient_positive_samples(db):
    _clear_model_tables(db)
    for i in range(80):
        db.add(
            DefaultAuctionTrainingSample(
                trade_date=f"209901{(i // 8) + 1:02d}",
                ts_code=f"910{i:03d}.SZ",
                strategy_name="default",
                strategy_version="default_auction_v2",
                sample_source="replay_backtest",
                feature_json=json.dumps(
                    {
                        "auction_ratio": 8 + i % 5,
                        "auction_turnover_rate": 0.8 + (i % 4) * 0.1,
                        "open_change_pct": 4 + (i % 3),
                        "seal_rate": 70 + (i % 20),
                        "rise_10d_pct": 10 + (i % 8),
                    },
                    ensure_ascii=False,
                ),
                label_t1_continue_limit=1 if i == 0 else 0,
            )
        )
    db.commit()

    with pytest.raises(ValueError, match="insufficient_positive_samples"):
        trainer.train_default_auction_target_model(
            db,
            "default_auction_t1_continue_lgbm",
            "label_t1_continue_limit",
            params=trainer.DEFAULT_PARAM_PROFILES[0]["params"],
            start_date="20990101",
            end_date="20990110",
        )


def test_default_auction_relay_job_trains_three_targets(db, monkeypatch):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    job = ModelTrainingJob(
        model_name="default_auction_relay_v2",
        status="pending",
        phase="prepare",
        progress=0,
        mode="test",
        auto_activate=0,
        train_start_date="20990101",
        train_end_date="20990110",
        params_json='{"max_retrain_attempts": 1}',
        acceptance_json="{}",
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()

    calls = []

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        calls.append((model_name, label_column, activate))
        return {
            "version": model_name + "_v1",
            "model_path": model_name + ".pkl",
            "metrics": {
                "sample_count": 100,
                "baseline_rate": 0.3,
                "top3_rate": 0.5,
                "top5_rate": 0.45,
                "topk_positive_count": 50,
                "auc": 0.7,
                "probability_spread": 20.0,
                "trained_tree_count": 20,
                "bucket_report": [
                    {"feature_name": "auction_ratio", "bucket": "8-15", "positive_rate": 0.5},
                    {"feature_name": "auction_turnover_rate", "bucket": "1-3", "positive_rate": 0.45},
                ],
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    assert payload["status"] == "passed"
    assert len(calls) == 3
    assert all(call[2] is False for call in calls)
    assert all(item["accepted"] for item in payload["acceptance"]["targets"].values())
    report = payload["diagnostic_report"]
    assert set(report) >= {
        "replay_validation_gap",
        "baseline_rates",
        "bucket_report",
        "auction_ratio_bucket_report",
        "auction_turnover_bucket_report",
        "continuation_sample_rates",
        "high_score_low_win_commonality",
        "low_score_high_win_misses",
        "failure_reasons",
    }
    assert report["baseline_rates"]["default_auction_t0_limit_lgbm"] == 0.3
    assert report["auction_ratio_bucket_report"][0]["bucket"] == "8-15"


def test_default_auction_relay_job_rejects_without_activating_versions(db, monkeypatch):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    db.add(
        ModelVersion(
            model_name="default_auction_t0_limit_lgbm",
            version="old_active",
            model_path="old.pkl",
            is_active=1,
        )
    )
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={"max_retrain_attempts": 1},
        auto_activate=True,
    )
    db.commit()

    calls = []

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        calls.append(model_name)
        return {
            "version": model_name + "_bad",
            "model_path": model_name + ".pkl",
            "metrics": {
                "sample_count": 100,
                "baseline_rate": 0.4,
                "top3_rate": 0.41,
                "top5_rate": 0.42,
                "topk_positive_count": 3,
                "auc": 0.51,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    active = db.query(ModelVersion).filter_by(model_name="default_auction_t0_limit_lgbm", is_active=1).one()
    assert payload["status"] == "rejected"
    assert calls == [model_name for model_name, _ in service.TARGET_MODELS]
    assert set(payload["acceptance"]["targets"]) == {model_name for model_name, _ in service.TARGET_MODELS}
    assert active.version == "old_active"


def test_default_auction_relay_job_retries_recent_window_after_full_history_rejects(db, monkeypatch):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={
            "profiles": [{"name": "p1", "params": {"learning_rate": 0.03}}],
            "rolling_window_trade_days": [30],
        },
        auto_activate=False,
    )

    calls = []

    def fake_window_starts(db_arg, label_column, end_date, windows, min_start_date=None):
        return {30: "20990106"}

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        calls.append((model_name, start_date, end_date, params.get("learning_rate")))
        accepted_metrics = {
            "sample_count": 100,
            "baseline_rate": 0.3,
            "top3_rate": 0.5,
            "top5_rate": 0.45,
            "topk_positive_count": 50,
            "auc": 0.7,
            "probability_spread": 20.0,
            "trained_tree_count": 20,
        }
        rejected_metrics = {
            "sample_count": 100,
            "baseline_rate": 0.3,
            "top3_rate": 0.31,
            "top5_rate": 0.32,
            "topk_positive_count": 50,
            "auc": 0.7,
        }
        metrics = accepted_metrics if start_date == "20990106" or model_name != "default_auction_t1_premium_lgbm" else rejected_metrics
        return {
            "version": f"{model_name}_{start_date or 'full'}",
            "model_path": f"{model_name}.pkl",
            "metrics": metrics,
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service, "_rolling_window_start_dates", fake_window_starts)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    t1_attempts = [
        attempt for attempt in payload["attempts"]
        if attempt["target"] == "default_auction_t1_premium_lgbm"
    ]
    assert payload["status"] == "passed"
    assert [attempt["train_start_date"] for attempt in t1_attempts] == ["20990101", "20990106"]
    assert t1_attempts[1]["training_window"] == "rolling_30_trade_days"
    assert payload["acceptance"]["targets"]["default_auction_t1_premium_lgbm"]["version"].endswith("20990106")
    assert ("default_auction_t1_premium_lgbm", "20990106", "20990110", 0.03) in calls


def test_default_auction_relay_auto_activate_sets_three_targets_active_atomically(db, monkeypatch, tmp_path):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    for model_name, _ in service.TARGET_MODELS:
        old_path = tmp_path / f"{model_name}_old.pkl"
        old_path.write_bytes(b"old")
        db.add(
            ModelVersion(
                model_name=model_name,
                version="old_active",
                model_path=str(old_path),
                is_active=1,
            )
        )
    db.commit()
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={"max_retrain_attempts": 1},
        auto_activate=True,
    )

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        model_path = tmp_path / f"{model_name}_new.pkl"
        model_path.write_bytes(b"new")
        db_arg.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_new",
                model_path=str(model_path),
                is_active=0,
            )
        )
        db_arg.commit()
        return {
            "version": f"{model_name}_new",
            "model_path": str(model_path),
            "metrics": {
                "baseline_rate": 0.3,
                "top3_rate": 0.5,
                "top5_rate": 0.45,
                "topk_positive_count": 50,
                "auc": 0.7,
                "probability_spread": 20.0,
                "trained_tree_count": 20,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    assert payload["status"] == "passed"
    assert payload["acceptance"]["activation"]["accepted"] is True
    for model_name, _ in service.TARGET_MODELS:
        active_versions = db.query(ModelVersion).filter_by(model_name=model_name, is_active=1).all()
        inactive_old = db.query(ModelVersion).filter_by(model_name=model_name, version="old_active").one()
        assert [mv.version for mv in active_versions] == [f"{model_name}_new"]
        assert inactive_old.is_active == 0


def test_default_auction_relay_activation_validation_failure_does_not_partially_activate(
    db,
    monkeypatch,
    tmp_path,
):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    for model_name, _ in service.TARGET_MODELS:
        old_path = tmp_path / f"{model_name}_old.pkl"
        old_path.write_bytes(b"old")
        db.add(
            ModelVersion(
                model_name=model_name,
                version="old_active",
                model_path=str(old_path),
                is_active=1,
            )
        )
    db.commit()
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={"max_retrain_attempts": 1},
        auto_activate=True,
    )

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        missing_target = service.TARGET_MODELS[-1][0]
        model_path = tmp_path / f"{model_name}_new.pkl"
        if model_name != missing_target:
            model_path.write_bytes(b"new")
        db_arg.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_new",
                model_path=str(model_path),
                is_active=0,
            )
        )
        db_arg.commit()
        return {
            "version": f"{model_name}_new",
            "model_path": str(model_path),
            "metrics": {
                "baseline_rate": 0.3,
                "top3_rate": 0.5,
                "top5_rate": 0.45,
                "topk_positive_count": 50,
                "auc": 0.7,
                "probability_spread": 20.0,
                "trained_tree_count": 20,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    assert payload["status"] == "rejected"
    assert payload["acceptance"]["activation"]["accepted"] is False
    assert "model_file_missing" in payload["acceptance"]["activation"]["reject_reasons"]
    for model_name, _ in service.TARGET_MODELS:
        active_versions = db.query(ModelVersion).filter_by(model_name=model_name, is_active=1).all()
        assert [mv.version for mv in active_versions] == ["old_active"]


def test_default_auction_relay_profiles_retry_records_diagnostics(db, monkeypatch, tmp_path):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={
            "max_retrain_attempts": 2,
            "profiles": [
                {"name": "first_error", "params": {"learning_rate": 0.01}},
                {"name": "second_pass", "params": {"learning_rate": 0.02}},
            ],
        },
        auto_activate=False,
    )
    calls = []

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        calls.append((model_name, params["learning_rate"]))
        if params["learning_rate"] == 0.01:
            raise ValueError("boom")
        model_path = tmp_path / f"{model_name}_retry.pkl"
        model_path.write_bytes(b"retry")
        db_arg.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_retry",
                model_path=str(model_path),
                is_active=0,
            )
        )
        db_arg.commit()
        return {
            "version": f"{model_name}_retry",
            "model_path": str(model_path),
            "metrics": {
                "baseline_rate": 0.3,
                "top3_rate": 0.5,
                "top5_rate": 0.45,
                "topk_positive_count": 50,
                "auc": 0.7,
                "probability_spread": 20.0,
                "trained_tree_count": 20,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    attempts = payload["attempts"]
    assert payload["status"] == "passed"
    assert len(calls) == 6
    assert len(attempts) == 6
    assert attempts[0]["profile"] == "first_error"
    assert attempts[0]["error"] == "boom"
    assert "training_error" in attempts[0]["reject_reasons"]
    assert "gate" in attempts[0]
    assert attempts[1]["profile"] == "second_pass"
    assert attempts[1]["accepted"] is True
    assert "metrics" in attempts[1]
    assert set(payload["acceptance"]["targets"]) == {name for name, _ in service.TARGET_MODELS}


def test_default_auction_relay_selects_best_accepted_attempt_not_first_pass(db, monkeypatch, tmp_path):
    from backend.services.model_engine import default_auction_relay_job_service as service

    _clear_model_tables(db)
    job = service.create_default_auction_relay_job(
        db,
        start_date="20990101",
        end_date="20990110",
        params={
            "max_retrain_attempts": 2,
            "profiles": [
                {"name": "weak_pass", "params": {"learning_rate": 0.01}},
                {"name": "strong_pass", "params": {"learning_rate": 0.02}},
            ],
        },
        auto_activate=False,
    )
    calls = []

    def fake_train(db_arg, model_name, label_column, params, activate, start_date, end_date):
        calls.append((model_name, params["learning_rate"]))
        is_strong = params["learning_rate"] == 0.02
        return {
            "version": f"{model_name}_{'strong' if is_strong else 'weak'}",
            "model_path": f"{model_name}_{'strong' if is_strong else 'weak'}.pkl",
            "metrics": {
                "baseline_rate": 0.3,
                "top3_rate": 0.52 if is_strong else 0.45,
                "top5_rate": 0.46 if is_strong else 0.40,
                "top3_lift": 0.22 if is_strong else 0.15,
                "top5_lift": 0.16 if is_strong else 0.10,
                "topk_positive_count": 60 if is_strong else 40,
                "auc": 0.72 if is_strong else 0.60,
                "probability_spread": 30.0 if is_strong else 20.0,
                "trained_tree_count": 30 if is_strong else 20,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    service.run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    assert payload["status"] == "passed"
    assert len(calls) == 6
    for model_name, target in payload["acceptance"]["targets"].items():
        assert target["version"] == f"{model_name}_strong"
        assert target["profile"] == "strong_pass"
    assert all("attempt_no" in attempt for attempt in payload["attempts"])
    assert all("param_profile" in attempt for attempt in payload["attempts"])
    assert all("model_version" in attempt for attempt in payload["attempts"] if attempt.get("accepted"))
