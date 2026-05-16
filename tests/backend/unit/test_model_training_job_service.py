import json

import pytest

from backend.database import Base, engine
from backend.models import ModelTrainingJob
from backend.models import ModelVersion
from backend.services.model_engine.training_job_service import (
    AcceptanceCriteria,
    TrainingParams,
    choose_acceptance_threshold,
    create_training_job,
    get_training_job,
    run_training_job_sync,
    validate_training_params,
)


def test_model_training_job_model_is_registered(db):
    Base.metadata.create_all(bind=engine)
    db.query(ModelTrainingJob).delete()
    db.commit()

    job = ModelTrainingJob(
        model_name="leader_main_t0_lgbm",
        status="pending",
        phase="prepare",
        progress=0,
        train_start_date="20250101",
        train_end_date="20260508",
        params_json=json.dumps({"learning_rate": 0.05}, ensure_ascii=False),
        acceptance_json=json.dumps({"min_precision": 0.5}, ensure_ascii=False),
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()

    saved = db.query(ModelTrainingJob).filter_by(model_name="leader_main_t0_lgbm").one()
    assert saved.status == "pending"
    assert saved.phase == "prepare"
    assert saved.progress == 0


def test_training_params_defaults_are_safe():
    params = TrainingParams()
    assert params.learning_rate == 0.05
    assert params.n_estimators == 500
    assert params.num_leaves == 31
    assert params.is_unbalance is True
    assert params.early_stopping_rounds == 50


def test_validate_training_params_rejects_invalid_ranges():
    params = TrainingParams(learning_rate=2.0)
    with pytest.raises(ValueError, match="learning_rate"):
        validate_training_params(params)


def test_choose_acceptance_threshold_prefers_passing_threshold_with_more_hits():
    criteria = AcceptanceCriteria(min_precision=0.5, min_hit_count=30, threshold=0.5)
    evaluation = [
        {"threshold": 0.4, "precision": 0.52, "hit_count": 45, "recall": 0.4},
        {"threshold": 0.5, "precision": 0.48, "hit_count": 60, "recall": 0.5},
        {"threshold": 0.6, "precision": 0.61, "hit_count": 20, "recall": 0.2},
    ]

    accepted = choose_acceptance_threshold(evaluation, criteria)

    assert accepted["accepted"] is True
    assert accepted["threshold"] == 0.4
    assert accepted["precision"] == 0.52
    assert accepted["hit_count"] == 45


def test_choose_acceptance_threshold_rejects_when_no_threshold_passes():
    criteria = AcceptanceCriteria(min_precision=0.5, min_hit_count=30, threshold=0.5)
    evaluation = [
        {"threshold": 0.4, "precision": 0.49, "hit_count": 45},
        {"threshold": 0.6, "precision": 0.61, "hit_count": 20},
    ]

    accepted = choose_acceptance_threshold(evaluation, criteria)

    assert accepted["accepted"] is False
    assert accepted["reason"] == "未找到同时满足胜率和命中数的阈值"


def test_create_training_job_persists_params_and_acceptance(db):
    db.query(ModelTrainingJob).delete()
    db.commit()

    job = create_training_job(
        db,
        model_name="leader_main_t0_lgbm",
        start_date="20250101",
        end_date="20260508",
        params=TrainingParams(learning_rate=0.03),
        acceptance=AcceptanceCriteria(min_precision=0.55, min_hit_count=20),
        mode="test",
        auto_activate=False,
    )

    saved = get_training_job(db, job.id)
    assert saved["status"] == "pending"
    assert saved["params"]["learning_rate"] == 0.03
    assert saved["acceptance"]["min_precision"] == 0.55
    assert saved["mode"] == "test"


def test_run_training_job_retrains_until_acceptance(db, monkeypatch, tmp_path):
    db.query(ModelTrainingJob).delete()
    db.query(ModelVersion).delete()
    db.commit()
    job = create_training_job(
        db,
        model_name="leader_main_t0_lgbm",
        start_date="20250101",
        end_date="20260508",
        params=TrainingParams(),
        acceptance=AcceptanceCriteria(min_precision=0.5, min_hit_count=30, max_retrain_attempts=2),
        mode="formal",
        auto_activate=True,
    )

    from backend.services.model_engine import training_job_service

    attempts = []

    def fake_train(start_date, end_date, params, activate):
        attempt_no = len(attempts) + 1
        attempts.append({"start_date": start_date, "end_date": end_date, "params": params, "activate": activate})
        version = f"v{attempt_no}"
        model_path = tmp_path / f"{version}.pkl"
        model_path.write_bytes(b"fake")
        db.add(
            ModelVersion(
                model_name="leader_main_t0_lgbm",
                version=version,
                feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
                model_metrics=json.dumps({}, ensure_ascii=False),
                model_path=str(model_path),
                is_active=0,
            )
        )
        db.commit()
        threshold_evaluation = [
            {"threshold": 0.5, "precision": 0.45, "hit_count": 50}
        ] if attempt_no == 1 else [
            {"threshold": 0.5, "precision": 0.56, "hit_count": 35}
        ]
        return {
            "version": version,
            "model_path": str(model_path),
            "metrics": {"threshold_evaluation": threshold_evaluation},
            "params": params,
        }

    monkeypatch.setattr(training_job_service.lightgbm_service, "train_leader_main_t0_lgbm_configurable", fake_train)
    monkeypatch.setattr(training_job_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(training_job_service, "_broadcast_job_update", lambda _payload: None)

    run_training_job_sync(job.id)

    payload = get_training_job(db, job.id)
    assert payload["status"] == "passed"
    assert payload["progress"] == 100
    assert payload["best_model_version"] == "v2"
    assert len(payload["attempts"]) == 2
    assert payload["attempts"][0]["accepted"] is False
    assert payload["attempts"][1]["accepted"] is True
    assert attempts[0]["activate"] is False
    assert db.query(ModelVersion).filter_by(model_name="leader_main_t0_lgbm", version="v2").one().is_active == 1
