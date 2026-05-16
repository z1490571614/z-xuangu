import json

from backend.database import Base, engine
from backend.models import ModelVersion, SelectedStock, SelectionRecord
from backend.services.model_engine import model_management_service


def test_list_models_groups_versions_and_marks_active_available(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(ModelVersion).delete()
    db.commit()
    model_path = tmp_path / "leader_main_t0.pkl"
    model_path.write_bytes(b"fake")
    db.add_all([
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v1",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"precision": 0.51}, ensure_ascii=False),
            model_path=str(model_path),
            is_active=1,
        ),
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v0",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"precision": 0.44}, ensure_ascii=False),
            model_path=str(tmp_path / "missing.pkl"),
            is_active=0,
        ),
    ])
    db.commit()

    result = model_management_service.list_models(db)

    model = result["models"]["leader_main_t0_lgbm"]
    assert model["active_version"]["version"] == "v1"
    assert model["active_version"]["available"] is True
    assert [item["version"] for item in model["versions"]] == ["v1", "v0"]


def test_activate_model_version_deactivates_previous_active(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(ModelVersion).delete()
    db.commit()
    old_path = tmp_path / "old.pkl"
    new_path = tmp_path / "new.pkl"
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")
    db.add_all([
        ModelVersion(model_name="leader_main_t0_lgbm", version="old", model_path=str(old_path), is_active=1),
        ModelVersion(model_name="leader_main_t0_lgbm", version="new", model_path=str(new_path), is_active=0),
    ])
    db.commit()

    result = model_management_service.activate_model_version(db, "leader_main_t0_lgbm", "new")

    assert result["active_version"] == "new"
    assert db.query(ModelVersion).filter_by(model_name="leader_main_t0_lgbm", version="old").one().is_active == 0
    assert db.query(ModelVersion).filter_by(model_name="leader_main_t0_lgbm", version="new").one().is_active == 1


def test_refresh_record_predictions_updates_leader_t0_fields(db, monkeypatch, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(ModelVersion).delete()
    db.commit()
    model_path = tmp_path / "leader_main_t0.pkl"
    model_path.write_bytes(b"fake")
    db.add(
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v1",
            feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
            model_path=str(model_path),
            params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
            is_active=1,
        )
    )
    stock = SelectedStock(
        record_id=46,
        ts_code="000001.SZ",
        name="测试股票",
        auction_ratio=8.1,
        auction_turnover_rate=0.8,
    )
    db.add(SelectionRecord(id=46, trade_date="20260515", status="completed", total_count=1))
    db.add(stock)
    db.commit()

    captured = {}

    def fake_predict(model_name, path, feature_cols, features, feature_units):
        captured["model_name"] = model_name
        captured["path"] = path
        captured["feature_cols"] = feature_cols
        captured["features"] = features
        captured["feature_units"] = feature_units
        return 67.89

    monkeypatch.setattr(model_management_service.lightgbm_service, "_predict_with_model_path", fake_predict)

    result = model_management_service.refresh_record_predictions(db, "leader_main_t0_lgbm", 46)

    db.refresh(stock)
    assert result["updated_count"] == 1
    assert float(stock.t0_limit_success_prob) == 67.89
    assert stock.t0_limit_success_model_version == "v1"
    assert captured["feature_cols"] == ["auction_ratio", "auction_turnover_rate"]
    assert captured["feature_units"] == {"auction_ratio": "percent"}


def test_models_api_returns_model_center_payload(client, db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(ModelVersion).delete()
    db.commit()
    model_path = tmp_path / "leader_main_t0.pkl"
    model_path.write_bytes(b"fake")
    db.add(
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v1",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"auc": 0.69}, ensure_ascii=False),
            model_path=str(model_path),
            is_active=1,
        )
    )
    db.commit()

    resp = client.get("/api/v1/models")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["models"]["leader_main_t0_lgbm"]["active_version"]["version"] == "v1"


def test_training_job_api_creates_and_reads_job(client, db, monkeypatch):
    from backend.api import model_management
    from backend.models import ModelTrainingJob

    db.query(ModelTrainingJob).delete()
    db.commit()
    monkeypatch.setattr(model_management, "run_training_job_sync", lambda _job_id: None)

    resp = client.post(
        "/api/v1/models/leader_main_t0_lgbm/training-jobs",
        json={
            "start_date": "20250101",
            "end_date": "20260508",
            "mode": "test",
            "auto_activate": False,
            "params": {"learning_rate": 0.03},
            "acceptance": {"min_precision": 0.5, "min_hit_count": 30},
        },
    )

    assert resp.status_code == 200
    job_id = resp.json()["data"]["job_id"]

    detail = client.get(f"/api/v1/models/training-jobs/{job_id}")

    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["status"] == "pending"
    assert data["params"]["learning_rate"] == 0.03
