import json

import backend.main as main
from backend.database import Base, engine
from backend.models import ModelVersion


def test_model_status_returns_active_model_versions(client, db):
    Base.metadata.create_all(bind=engine)
    db.add(
        ModelVersion(
            model_name="active_auction_lgbm",
            version="v20240510",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"auc": 0.71}, ensure_ascii=False),
            model_path="models/active_auction_lgbm.pkl",
            is_active=1,
        )
    )
    db.commit()

    resp = client.get("/api/v1/model/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["models"]["active_auction_lgbm"]["version"] == "v20240510"
    assert data["models"]["active_auction_lgbm"]["feature_cols"] == ["auction_ratio"]
    assert data["models"]["active_auction_lgbm"]["metrics"]["auc"] == 0.71


def test_model_status_enabled_when_active_model_file_exists(client, db, monkeypatch, tmp_path):
    Base.metadata.create_all(bind=engine)
    model_path = str(tmp_path / "active_auction_lgbm.pkl")
    db.add(
        ModelVersion(
            model_name="active_auction_lgbm_status_enabled",
            version="v20260509",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"auc": 0.72}, ensure_ascii=False),
            model_path=model_path,
            is_active=1,
        )
    )
    db.commit()
    monkeypatch.setattr(main._os.path, "exists", lambda path: path == model_path)

    resp = client.get("/api/v1/model/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert data["model_path"] == model_path
