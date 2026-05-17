import json

import pytest

from backend.database import Base, engine
from backend.models import ModelTrainingJob, ModelVersion, SelectedStock, SelectionRecord
from backend.services.model_engine import model_management_service


def test_default_auction_replay_validate_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    def fake_validate(db, recent_days):
        captured["recent_days"] = recent_days
        return {"accepted": True, "daily": [], "recent_days": recent_days}

    monkeypatch.setattr(model_management, "validate_default_auction_replay", fake_validate)

    resp = client.post("/api/v1/models/default-auction-replay/validate", json={"recent_days": 3})

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] is True
    assert resp.json()["data"]["recent_days"] == 3
    assert captured["recent_days"] == 3


def test_default_auction_samples_build_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    def fake_build(db, record_id, sample_source):
        captured["record_id"] = record_id
        captured["sample_source"] = sample_source
        return {"created_count": 2, "updated_count": 0, "skipped_count": 0}

    monkeypatch.setattr(model_management, "build_samples_from_selected_record", fake_build)

    resp = client.post(
        "/api/v1/models/default-auction-samples/build",
        json={"record_id": 9001, "sample_source": "real_selected"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["created_count"] == 2
    assert captured == {"record_id": 9001, "sample_source": "real_selected"}


def test_default_auction_relay_train_api_creates_job(client, db, monkeypatch):
    from backend.api import model_management

    db.query(ModelTrainingJob).delete()
    db.commit()
    monkeypatch.setattr(model_management, "run_default_auction_relay_training_job", lambda _job_id: None)

    resp = client.post(
        "/api/v1/models/default-auction-relay/train",
        json={
            "start_date": "20250116",
            "end_date": "20260508",
            "auto_activate": False,
            "params": {"max_retrain_attempts": 1},
        },
    )

    assert resp.status_code == 200
    job_id = resp.json()["data"]["job_id"]
    saved = db.query(ModelTrainingJob).filter_by(id=job_id).one()
    assert saved.model_name == "default_auction_relay_v2"
    assert saved.status == "pending"


def test_default_auction_relay_train_api_rejects_invalid_dates(client, db, monkeypatch):
    from backend.api import model_management

    db.query(ModelTrainingJob).delete()
    db.commit()
    monkeypatch.setattr(model_management, "run_default_auction_relay_training_job", lambda _job_id: None)

    invalid_format = client.post(
        "/api/v1/models/default-auction-relay/train",
        json={
            "start_date": "2026-05-08",
            "end_date": "20260508",
            "auto_activate": False,
            "params": {},
        },
    )
    invalid_range = client.post(
        "/api/v1/models/default-auction-relay/train",
        json={
            "start_date": "20260509",
            "end_date": "20260508",
            "auto_activate": False,
            "params": {},
        },
    )

    assert invalid_format.status_code == 422
    assert invalid_range.status_code == 422
    assert db.query(ModelTrainingJob).count() == 0


def test_default_auction_relay_diagnostics_api(client, db):
    from backend.services.model_engine.default_auction_relay_job_service import (
        create_default_auction_relay_job,
    )

    db.query(ModelTrainingJob).delete()
    db.commit()
    job = create_default_auction_relay_job(
        db,
        start_date="20250116",
        end_date="20260508",
        params={"max_retrain_attempts": 1},
        auto_activate=False,
    )

    resp = client.get(f"/api/v1/models/default-auction-relay/diagnostics/{job.id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == job.id
    assert data["model_name"] == "default_auction_relay_v2"
    assert data["params"]["max_retrain_attempts"] == 1


def test_default_auction_relay_diagnostics_rejects_non_relay_job(client, db):
    db.query(ModelTrainingJob).delete()
    db.commit()
    job = ModelTrainingJob(
        model_name="leader_main_t0_lgbm",
        status="pending",
        phase="prepare",
        progress=0,
        train_start_date="20250116",
        train_end_date="20260508",
        params_json="{}",
        acceptance_json="{}",
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()

    resp = client.get(f"/api/v1/models/default-auction-relay/diagnostics/{job.id}")

    assert resp.status_code == 404
    assert "default_auction_relay_v2" in resp.json()["detail"]


def _clear_refresh_tables(db):
    Base.metadata.create_all(bind=engine)
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(ModelVersion).delete()
    db.commit()


def _add_relay_stock(db, record_id=9100):
    db.add(SelectionRecord(id=record_id, trade_date="20260508", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=record_id,
            ts_code="000001.SZ",
            name="测试股",
            auction_ratio=8.19,
            auction_turnover_rate=0.8,
        )
    )
    db.commit()


def _add_active_target_models(db, tmp_path, missing_model_name=None):
    for model_name in [
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    ]:
        if model_name == missing_model_name:
            continue
        path = tmp_path / f"{model_name}.pkl"
        path.write_bytes(b"fake")
        db.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_v1",
                feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
                model_path=str(path),
                params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
                is_active=1,
            )
        )
    db.commit()


def test_list_models_includes_default_auction_relay_composite(db, tmp_path):
    _clear_refresh_tables(db)
    _add_active_target_models(db, tmp_path)

    result = model_management_service.list_models(db)

    relay = result["models"]["default_auction_relay_v2"]
    assert relay["is_composite"] is True
    assert relay["active_version"] == (
        "default_auction_t0_limit_lgbm_v1|"
        "default_auction_t1_premium_lgbm_v1|"
        "default_auction_t1_continue_lgbm_v1"
    )
    assert [item["model_name"] for item in relay["target_models"]] == [
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    ]


def test_refresh_default_auction_relay_predictions_writes_three_probs(db, monkeypatch, tmp_path):
    _clear_refresh_tables(db)
    _add_relay_stock(db, record_id=9100)
    _add_active_target_models(db, tmp_path)

    probs = {
        "default_auction_t0_limit_lgbm": 40.0,
        "default_auction_t1_premium_lgbm": 50.0,
        "default_auction_t1_continue_lgbm": 60.0,
    }
    monkeypatch.setattr(
        model_management_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: probs[model_name],
    )

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9100)

    stock = db.query(SelectedStock).filter_by(record_id=9100).one()
    assert result["updated_count"] == 1
    assert result["versions"] == {
        "default_auction_t0_limit_lgbm": "default_auction_t0_limit_lgbm_v1",
        "default_auction_t1_premium_lgbm": "default_auction_t1_premium_lgbm_v1",
        "default_auction_t1_continue_lgbm": "default_auction_t1_continue_lgbm_v1",
    }
    assert float(stock.default_t0_limit_prob) == 40.0
    assert float(stock.default_t1_premium_prob) == 50.0
    assert float(stock.default_t1_continue_prob) == 60.0
    assert float(stock.default_relay_score) == 51.5
    assert stock.default_relay_model_version == (
        "default_auction_t0_limit_lgbm_v1|"
        "default_auction_t1_premium_lgbm_v1|"
        "default_auction_t1_continue_lgbm_v1"
    )


def test_refresh_default_auction_relay_requires_all_active_targets_before_writing(db, tmp_path):
    _clear_refresh_tables(db)
    _add_relay_stock(db, record_id=9101)
    _add_active_target_models(db, tmp_path, missing_model_name="default_auction_t1_continue_lgbm")

    with pytest.raises(ValueError, match="default_auction_t1_continue_lgbm"):
        model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9101)

    stock = db.query(SelectedStock).filter_by(record_id=9101).one()
    assert stock.default_t0_limit_prob is None
    assert stock.default_t1_premium_prob is None
    assert stock.default_t1_continue_prob is None
    assert stock.default_relay_score is None
    assert stock.default_relay_model_version is None


def test_refresh_default_auction_relay_failed_target_reports_context(db, monkeypatch, tmp_path):
    _clear_refresh_tables(db)
    _add_relay_stock(db, record_id=9102)
    _add_active_target_models(db, tmp_path)

    def fake_predict(model_name, path, cols, features, units):
        if model_name == "default_auction_t1_premium_lgbm":
            raise RuntimeError("premium boom")
        return 40.0

    monkeypatch.setattr(
        model_management_service.lightgbm_service,
        "_predict_with_model_path",
        fake_predict,
    )

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9102)

    failed = result["failed"][0]
    stock = db.query(SelectedStock).filter_by(record_id=9102).one()
    assert result["updated_count"] == 0
    assert failed["ts_code"] == "000001.SZ"
    assert failed["target_model_name"] == "default_auction_t1_premium_lgbm"
    assert failed["version"] == "default_auction_t1_premium_lgbm_v1"
    assert failed["model_path"].endswith("default_auction_t1_premium_lgbm.pkl")
    assert failed["error"] == "premium boom"
    assert stock.default_t0_limit_prob is None
    assert stock.default_relay_score is None


def test_default_auction_model_center_field_lengths_are_sufficient():
    assert SelectedStock.__table__.columns.default_relay_model_version.type.length >= 255
    assert ModelTrainingJob.__table__.columns.best_model_version.type.length >= 255
