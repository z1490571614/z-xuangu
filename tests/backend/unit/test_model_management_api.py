import json

from backend.database import Base, engine
from backend.models import ModelTrainingJob, ModelVersion, SelectedStock, SelectionRecord, StockAuctionOpen
from backend.models.seal_rate import StockDailyData
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


def test_activate_default_auction_target_rejects_unaccepted_attempt(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(ModelTrainingJob).delete()
    db.query(ModelVersion).delete()
    db.commit()
    model_path = tmp_path / "rejected.pkl"
    model_path.write_bytes(b"fake")
    db.add(
        ModelVersion(
            model_name="default_auction_t1_continue_lgbm",
            version="rejected_continue",
            model_path=str(model_path),
            is_active=0,
        )
    )
    db.add(
        ModelTrainingJob(
            model_name="default_auction_relay_v2",
            status="passed",
            phase="accepted",
            progress=100,
            train_start_date="20250101",
            train_end_date="20260508",
            acceptance_json=json.dumps(
                {
                    "targets": {
                        "default_auction_t1_continue_lgbm": {
                            "version": "accepted_continue",
                            "accepted": True,
                        }
                    },
                    "activation": {"accepted": True},
                },
                ensure_ascii=False,
            ),
            attempts_json="[]",
            logs_json="[]",
        )
    )
    db.commit()

    try:
        model_management_service.activate_model_version(
            db,
            "default_auction_t1_continue_lgbm",
            "rejected_continue",
        )
    except ValueError as exc:
        assert "未通过默认竞价接力三目标验收" in str(exc)
    else:
        raise AssertionError("expected rejected default auction target activation to fail")

    assert db.query(ModelVersion).filter_by(version="rejected_continue").one().is_active == 0


def test_activate_default_auction_target_activates_whole_accepted_relay_set(db, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(ModelTrainingJob).delete()
    db.query(ModelVersion).delete()
    db.commit()

    accepted_versions = {
        "default_auction_t0_limit_lgbm": "t0_good",
        "default_auction_t1_premium_lgbm": "premium_good",
        "default_auction_t1_continue_lgbm": "continue_good",
    }
    stale_versions = {
        "default_auction_t0_limit_lgbm": "t0_stale",
        "default_auction_t1_premium_lgbm": "premium_stale",
        "default_auction_t1_continue_lgbm": "continue_stale",
    }
    for versions, active in ((accepted_versions, 0), (stale_versions, 1)):
        for model_name, version in versions.items():
            model_path = tmp_path / f"{version}.pkl"
            model_path.write_bytes(b"fake")
            db.add(
                ModelVersion(
                    model_name=model_name,
                    version=version,
                    model_path=str(model_path),
                    is_active=active,
                )
            )
    db.add(
        ModelTrainingJob(
            model_name="default_auction_relay_v2",
            status="passed",
            phase="accepted",
            progress=100,
            train_start_date="20250101",
            train_end_date="20260508",
            acceptance_json=json.dumps(
                {
                    "targets": {
                        model_name: {"version": version, "accepted": True}
                        for model_name, version in accepted_versions.items()
                    },
                    "activation": {"accepted": True},
                },
                ensure_ascii=False,
            ),
            attempts_json="[]",
            logs_json="[]",
        )
    )
    db.commit()

    result = model_management_service.activate_model_version(
        db,
        "default_auction_t1_continue_lgbm",
        "continue_good",
    )

    assert result["model_name"] == "default_auction_relay_v2"
    assert result["active_version"] == "t0_good|premium_good|continue_good"
    for model_name, version in accepted_versions.items():
        assert db.query(ModelVersion).filter_by(model_name=model_name, version=version).one().is_active == 1
    for model_name, version in stale_versions.items():
        assert db.query(ModelVersion).filter_by(model_name=model_name, version=version).one().is_active == 0


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


def test_refresh_default_auction_relay_predictions_merges_auction_and_market_features(db, monkeypatch, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockDailyData).delete()
    db.query(ModelVersion).delete()
    db.commit()

    target_models = [
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    ]
    for model_name in target_models:
        model_path = tmp_path / f"{model_name}.pkl"
        model_path.write_bytes(b"fake")
        db.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_v1",
                feature_cols=json.dumps(
                    [
                        "auction_ratio",
                        "auction_turnover_rate",
                        "auction_amount",
                        "auction_volume",
                        "market_limit_up_count",
                        "market_limit_down_count",
                        "market_max_connected_board",
                        "market_zhaban_rate",
                        "market_emotion_score",
                    ],
                    ensure_ascii=False,
                ),
                model_path=str(model_path),
                params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
                is_active=1,
            )
        )
    db.add(SelectionRecord(id=47, trade_date="20260508", status="completed", total_count=1))
    db.add(
        SelectedStock(
            record_id=47,
            ts_code="000001.SZ",
            name="真实预测股",
            auction_ratio=8.1,
            auction_turnover_rate=0.8,
            open_change_pct=4.0,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000001.SZ",
            price=10.4,
            vol=222000,
            amount=2308800,
            pre_close=10.0,
            auction_ratio=8.1,
            auction_turnover_rate=0.8,
            source="tushare_stk_auction",
        )
    )
    db.add_all(
        [
            StockDailyData(
                trade_date="20260507",
                ts_code="000100.SZ",
                high=11.0,
                close=11.0,
                up_limit=11.0,
                down_limit=9.0,
                is_adj=0,
            ),
            StockDailyData(
                trade_date="20260507",
                ts_code="000101.SZ",
                high=10.0,
                close=9.0,
                up_limit=11.0,
                down_limit=9.0,
                is_adj=0,
            ),
            StockDailyData(
                trade_date="20260507",
                ts_code="000102.SZ",
                high=11.0,
                close=10.2,
                up_limit=11.0,
                down_limit=9.0,
                is_adj=0,
            ),
        ]
    )
    db.commit()

    captured = {}

    def fake_predict(model_name, path, feature_cols, features, feature_units):
        captured[model_name] = dict(features)
        return {
            "default_auction_t0_limit_lgbm": 61.0,
            "default_auction_t1_premium_lgbm": 53.0,
            "default_auction_t1_continue_lgbm": 28.0,
        }[model_name]

    monkeypatch.setattr(model_management_service.lightgbm_service, "_predict_with_model_path", fake_predict)

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 47)

    assert result["updated_count"] == 1
    for features in captured.values():
        assert features["auction_amount"] == 2308800
        assert features["auction_volume"] == 222000
        assert features["market_limit_up_count"] == 1
        assert features["market_limit_down_count"] == 1
        assert features["market_max_connected_board"] == 1
        assert features["market_zhaban_rate"] == 50.0
        assert features["market_emotion_score"] == -5.0


def test_refresh_default_auction_relay_predictions_rejects_missing_critical_features(db, monkeypatch, tmp_path):
    Base.metadata.create_all(bind=engine)
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockDailyData).delete()
    db.query(ModelVersion).delete()
    db.commit()

    feature_cols = [
        "auction_ratio",
        "auction_turnover_rate",
        "auction_amount",
        "auction_volume",
        "market_limit_up_count",
        "market_limit_down_count",
        "market_max_connected_board",
        "market_zhaban_rate",
        "market_emotion_score",
    ]
    for model_name in [
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    ]:
        model_path = tmp_path / f"{model_name}.pkl"
        model_path.write_bytes(b"fake")
        db.add(
            ModelVersion(
                model_name=model_name,
                version=f"{model_name}_v1",
                feature_cols=json.dumps(feature_cols, ensure_ascii=False),
                model_path=str(model_path),
                is_active=1,
            )
        )
    db.add(SelectionRecord(id=48, trade_date="20260508", status="completed", total_count=1))
    db.add(
        SelectedStock(
            record_id=48,
            ts_code="000002.SZ",
            name="缺关键特征股",
            auction_ratio=8.1,
            auction_turnover_rate=0.8,
        )
    )
    db.commit()

    def fail_if_predicts(*args, **kwargs):
        raise AssertionError("关键特征缺失时不应该调用模型预测")

    monkeypatch.setattr(model_management_service.lightgbm_service, "_predict_with_model_path", fail_if_predicts)

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 48)

    stock = db.query(SelectedStock).filter_by(record_id=48, ts_code="000002.SZ").one()
    assert result["updated_count"] == 0
    assert result["failed"][0]["ts_code"] == "000002.SZ"
    assert result["failed"][0]["error"] == "默认竞价接力预测关键特征缺失"
    assert set(result["failed"][0]["missing_features"]) == {
        "auction_amount",
        "auction_volume",
        "market_limit_up_count",
        "market_limit_down_count",
        "market_max_connected_board",
        "market_zhaban_rate",
        "market_emotion_score",
    }
    assert stock.default_relay_score is None


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
