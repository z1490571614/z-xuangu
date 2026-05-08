import json

from backend.database import Base, engine
from backend.models import ModelVersion


def test_model_status_returns_active_model_versions(client, db):
    Base.metadata.create_all(bind=engine)
    db.add(
        ModelVersion(
            model_name="leader_main_t0_lgbm",
            version="v20240510",
            feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
            model_metrics=json.dumps({"auc": 0.71}, ensure_ascii=False),
            model_path="models/leader_main_t0_lgbm.pkl",
            is_active=1,
        )
    )
    db.commit()

    resp = client.get("/api/v1/model/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["models"]["leader_main_t0_lgbm"]["version"] == "v20240510"
    assert data["models"]["leader_main_t0_lgbm"]["feature_cols"] == ["auction_ratio"]
    assert data["models"]["leader_main_t0_lgbm"]["metrics"]["auc"] == 0.71
