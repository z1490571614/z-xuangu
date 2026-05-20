import json

import pytest

from backend.database import Base, engine
from backend.models import (
    DefaultAuctionAutoLearningRun,
    DefaultAuctionTrainingSample,
    ModelTrainingJob,
    ModelVersion,
    SelectedStock,
    SelectionRecord,
    SystemConfig,
)
from backend.models.auction_backtest import StockAuctionOpen
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


def test_default_auction_raw_data_sync_state_api(client, db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import RAW_SYNC_STATE_KEY

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.add(
        SystemConfig(
            key=RAW_SYNC_STATE_KEY,
            value=json.dumps(
                {
                    "trade_date": "20260518",
                    "status": "success",
                    "trigger": "startup",
                    "finished_at": "2026-05-18T08:01:00",
                },
                ensure_ascii=False,
            ),
            value_type="json",
        )
    )
    db.commit()

    resp = client.get("/api/v1/models/default-auction-relay/raw-data-sync-state")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["trade_date"] == "20260518"
    assert data["status"] == "success"
    assert data["trigger"] == "startup"


def test_default_auction_auto_learning_run_api_creates_lists_gets_and_cancels(client, monkeypatch, db):
    from backend.api import model_management

    db.query(DefaultAuctionAutoLearningRun).delete()
    db.commit()

    executed = []

    def fake_run_auto_learning(run_id):
        executed.append(run_id)

    monkeypatch.setattr(model_management, "run_auto_learning", fake_run_auto_learning)

    resp = client.post(
        "/api/v1/models/default-auction-relay/auto-learning/runs",
        json={
            "start_date": "20240501",
            "end_date": "20240510",
            "sync_daily": False,
            "sync_minute": False,
            "recalculate_auction_ratios": True,
            "audit_training_data": True,
            "run_training": False,
            "run_backtest": False,
            "auto_activate": False,
        },
    )

    assert resp.status_code == 200
    run_id = resp.json()["data"]["run_id"]
    assert resp.json()["data"]["status"] == "pending"
    assert resp.json()["data"]["reused"] is False
    assert executed == [run_id]

    repeat = client.post(
        "/api/v1/models/default-auction-relay/auto-learning/runs",
        json={
            "start_date": "20240511",
            "end_date": "20240512",
            "sync_daily": False,
            "sync_minute": False,
            "recalculate_auction_ratios": True,
            "audit_training_data": True,
            "run_training": False,
            "run_backtest": False,
            "auto_activate": False,
        },
    )

    assert repeat.status_code == 200
    assert repeat.json()["data"]["run_id"] == run_id
    assert repeat.json()["data"]["status"] == "pending"
    assert repeat.json()["data"]["reused"] is True
    assert executed == [run_id]

    detail = client.get(f"/api/v1/models/default-auction-relay/auto-learning/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == run_id
    assert detail.json()["data"]["options"]["recalculate_auction_ratios"] is True

    listing = client.get("/api/v1/models/default-auction-relay/auto-learning/runs?limit=5")
    assert listing.status_code == 200
    assert any(item["id"] == run_id for item in listing.json()["data"])

    cancel = client.post(f"/api/v1/models/default-auction-relay/auto-learning/runs/{run_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancelled"


def test_default_auction_auto_learning_api_rejects_bad_activation_contract(client):
    resp = client.post(
        "/api/v1/models/default-auction-relay/auto-learning/runs",
        json={
            "start_date": "20240501",
            "end_date": "20240510",
            "run_training": True,
            "run_backtest": False,
            "audit_training_data": True,
            "auto_activate": True,
        },
    )

    assert resp.status_code == 422
    assert "auto_activate" in resp.json()["detail"]


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


def test_default_auction_replay_build_samples_doc_route(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    def fake_build(db, record_id, sample_source):
        captured["record_id"] = record_id
        captured["sample_source"] = sample_source
        return {"created_count": 1, "updated_count": 0, "skipped_count": 0}

    monkeypatch.setattr(model_management, "build_samples_from_selected_record", fake_build)

    resp = client.post(
        "/api/v1/models/default-auction-replay/build-samples",
        json={"record_id": 9002, "sample_source": "real_selected"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["created_count"] == 1
    assert captured == {"record_id": 9002, "sample_source": "real_selected"}


def test_default_auction_replay_build_samples_doc_route_supports_date_range(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    def fake_build_range(db, start_date, end_date, sample_source):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["sample_source"] = sample_source
        return {"created_count": 3, "updated_count": 0, "skipped_count": 0}

    monkeypatch.setattr(model_management, "build_samples_from_replay_range", fake_build_range)
    def fake_validate(db, recent_days, end_date=None):
        captured["validation_end_date"] = end_date
        return {"accepted": True, "daily": []}

    monkeypatch.setattr(model_management, "validate_default_auction_replay", fake_validate)

    resp = client.post(
        "/api/v1/models/default-auction-replay/build-samples",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "sample_source": "replay_backtest",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["created_count"] == 3
    assert captured == {
        "start_date": "20260501",
        "end_date": "20260508",
        "sample_source": "replay_backtest",
        "validation_end_date": "20260508",
    }


def test_default_auction_replay_build_samples_rejects_when_replay_validation_fails(client, monkeypatch):
    from backend.api import model_management

    called = {"build": False}
    monkeypatch.setattr(
        model_management,
        "validate_default_auction_replay",
        lambda db, recent_days, end_date=None: {"accepted": False, "reject_reasons": ["avg_recall_below_threshold"]},
    )

    def fake_build_range(*args, **kwargs):
        called["build"] = True
        return {"created_count": 1}

    monkeypatch.setattr(model_management, "build_samples_from_replay_range", fake_build_range)

    resp = client.post(
        "/api/v1/models/default-auction-replay/build-samples",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "sample_source": "replay_backtest",
        },
    )

    assert resp.status_code == 422
    assert "回放验收未通过" in resp.json()["detail"]
    assert called["build"] is False


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


def test_default_auction_relay_pipeline_scopes_minute_sync_to_training_sample_codes(client, db, monkeypatch):
    from backend.api import model_management

    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()
    db.add_all(
        [
            DefaultAuctionTrainingSample(
                strategy_version="default_auction_v2",
                trade_date="20260507",
                ts_code="000111.SZ",
                sample_source="replay_backtest",
                strategy_name="default",
                feature_json="{}",
            ),
            DefaultAuctionTrainingSample(
                strategy_version="default_auction_v2",
                trade_date="20260508",
                ts_code="600222.SH",
                sample_source="real_selected",
                strategy_name="default",
                feature_json="{}",
            ),
        ]
    )
    db.commit()
    captured = {}

    class FakeDailySync:
        def __init__(self, tdx_vipdoc_path=None):
            pass

        def sync_range(self, start_date, end_date, ts_codes=None, commit_every=5000):
            return {"rows_synced": 0, "ts_codes": ts_codes}

    class FakeMinuteSync:
        def __init__(self, tdx_vipdoc_path=None):
            pass

        def sync_range(self, start_date, end_date, ts_codes=None, interval=1, commit_every=5000):
            captured["minute_ts_codes"] = ts_codes
            return {"rows_synced": 0, "ts_codes": ts_codes}

    monkeypatch.setattr(model_management, "TdxLocalDailySyncService", FakeDailySync)
    monkeypatch.setattr(model_management, "TdxLocalMinuteSyncService", FakeMinuteSync)
    monkeypatch.setattr(
        model_management,
        "validate_default_auction_replay",
        lambda db, recent_days, end_date=None: {"accepted": True, "daily": []},
    )
    monkeypatch.setattr(
        model_management,
        "build_samples_from_replay_range",
        lambda db, start_date, end_date, sample_source: {"created_count": 0, "updated_count": 0, "skipped_count": 0},
    )

    resp = client.post(
        "/api/v1/models/default-auction-relay/rebuild-pipeline",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "sync_daily": False,
            "sync_minute": True,
            "recalculate_auction_ratios": False,
            "validate_replay": False,
            "build_samples": True,
        },
    )

    assert resp.status_code == 200
    assert captured["minute_ts_codes"] == ["000111.SZ", "600222.SH"]


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
        model_name="active_auction_lgbm",
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
    db.query(StockAuctionOpen).delete()
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


def test_refresh_default_auction_relay_predictions_enriches_missing_auction_features_from_open_cache(
    db,
    monkeypatch,
    tmp_path,
):
    _clear_refresh_tables(db)
    db.add(SelectionRecord(id=9105, trade_date="20260508", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9105,
            ts_code="000001.SZ",
            name="测试股",
            auction_ratio=None,
            auction_turnover_rate=None,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000001.SZ",
            auction_ratio=8.88,
            auction_turnover_rate=1.23,
        )
    )
    db.commit()
    _add_active_target_models(db, tmp_path)

    seen_features = []

    def fake_predict(model_name, path, cols, features, units):
        seen_features.append(dict(features))
        return 50.0

    monkeypatch.setattr(
        model_management_service.lightgbm_service,
        "_predict_with_model_path",
        fake_predict,
    )

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9105)

    stock = db.query(SelectedStock).filter_by(record_id=9105).one()
    assert result["updated_count"] == 1
    assert seen_features
    assert all(features["auction_ratio"] == 8.88 for features in seen_features)
    assert all(features["auction_turnover_rate"] == 1.23 for features in seen_features)
    assert float(stock.auction_ratio) == 8.88
    assert float(stock.auction_turnover_rate) == 1.23


def test_default_auction_relay_refresh_predictions_doc_route(client, db, monkeypatch, tmp_path):
    _clear_refresh_tables(db)
    _add_relay_stock(db, record_id=9103)
    _add_active_target_models(db, tmp_path)

    probs = {
        "default_auction_t0_limit_lgbm": 30.0,
        "default_auction_t1_premium_lgbm": 40.0,
        "default_auction_t1_continue_lgbm": 50.0,
    }
    monkeypatch.setattr(
        model_management_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: probs[model_name],
    )

    resp = client.post(
        "/api/v1/models/default-auction-relay/refresh-predictions",
        json={"record_id": 9103},
    )

    stock = db.query(SelectedStock).filter_by(record_id=9103).one()
    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 1
    assert float(stock.default_t0_limit_prob) == 30.0
    assert float(stock.default_t1_premium_prob) == 40.0
    assert float(stock.default_t1_continue_prob) == 50.0
    assert float(stock.default_relay_score) == 41.5


def test_default_auction_sync_local_daily_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    class FakeDailySync:
        def __init__(self, tdx_vipdoc_path=None):
            captured["tdx_vipdoc_path"] = tdx_vipdoc_path

        def sync_range(self, start_date, end_date, ts_codes=None, commit_every=5000):
            captured["daily"] = {
                "start_date": start_date,
                "end_date": end_date,
                "ts_codes": ts_codes,
                "commit_every": commit_every,
            }
            return {"rows_synced": 12, "stocks_scanned": 2}

    monkeypatch.setattr(model_management, "TdxLocalDailySyncService", FakeDailySync)

    resp = client.post(
        "/api/v1/models/default-auction-relay/sync-local-daily",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "ts_codes": ["000001.SZ"],
            "tdx_vipdoc_path": "X:/tdx/vipdoc",
            "commit_every": 100,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["rows_synced"] == 12
    assert captured["tdx_vipdoc_path"] == "X:/tdx/vipdoc"
    assert captured["daily"]["ts_codes"] == ["000001.SZ"]
    assert captured["daily"]["commit_every"] == 100


def test_default_auction_sync_local_minute_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    class FakeMinuteSync:
        def __init__(self, tdx_vipdoc_path=None):
            captured["tdx_vipdoc_path"] = tdx_vipdoc_path

        def sync_range(self, start_date, end_date, ts_codes=None, interval=1, commit_every=5000):
            captured["minute"] = {
                "start_date": start_date,
                "end_date": end_date,
                "ts_codes": ts_codes,
                "interval": interval,
                "commit_every": commit_every,
            }
            return {"rows_synced": 240, "stocks_scanned": 1, "interval": interval}

    monkeypatch.setattr(model_management, "TdxLocalMinuteSyncService", FakeMinuteSync)

    resp = client.post(
        "/api/v1/models/default-auction-relay/sync-local-minute",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "ts_codes": ["000001.SZ"],
            "interval": 1,
            "commit_every": 100,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["rows_synced"] == 240
    assert captured["minute"]["interval"] == 1


def test_default_auction_recalculate_auction_ratios_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    class FakeAuctionDataService:
        def recalculate_auction_ratios_from_daily_cache(self, start_date, end_date):
            captured["start_date"] = start_date
            captured["end_date"] = end_date
            return {"updated_count": 12, "missing_count": 1}

    monkeypatch.setattr(model_management, "AuctionDataService", FakeAuctionDataService)

    resp = client.post(
        "/api/v1/models/default-auction-relay/recalculate-auction-ratios",
        json={"start_date": "20260501", "end_date": "20260508"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 12
    assert captured == {"start_date": "20260501", "end_date": "20260508"}


def test_default_auction_rebuild_pipeline_api_runs_data_and_sample_stages(client, db, monkeypatch):
    from backend.api import model_management

    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()
    calls = []

    class FakeDailySync:
        def __init__(self, tdx_vipdoc_path=None):
            calls.append(("daily_init", tdx_vipdoc_path))

        def sync_range(self, start_date, end_date, ts_codes=None, commit_every=5000):
            calls.append(("daily_sync", start_date, end_date, ts_codes, commit_every))
            return {"rows_synced": 2}

    class FakeMinuteSync:
        def __init__(self, tdx_vipdoc_path=None):
            calls.append(("minute_init", tdx_vipdoc_path))

        def sync_range(self, start_date, end_date, ts_codes=None, interval=1, commit_every=5000):
            calls.append(("minute_sync", start_date, end_date, ts_codes, interval, commit_every))
            return {"rows_synced": 120}

    class FakeAuctionDataService:
        def recalculate_auction_ratios_from_daily_cache(self, start_date, end_date):
            calls.append(("auction_recalc", start_date, end_date))
            return {"updated_count": 20}

    monkeypatch.setattr(model_management, "TdxLocalDailySyncService", FakeDailySync)
    monkeypatch.setattr(model_management, "TdxLocalMinuteSyncService", FakeMinuteSync)
    monkeypatch.setattr(model_management, "AuctionDataService", FakeAuctionDataService)
    monkeypatch.setattr(model_management, "validate_default_auction_replay", lambda db, recent_days, end_date=None: {"accepted": True})
    monkeypatch.setattr(
        model_management,
        "build_samples_from_replay_range",
        lambda db, start_date, end_date, sample_source: {"created_count": 3, "sample_source": sample_source},
    )

    resp = client.post(
        "/api/v1/models/default-auction-relay/rebuild-pipeline",
        json={
            "start_date": "20260501",
            "end_date": "20260508",
            "sync_daily": True,
            "sync_minute": True,
            "recalculate_auction_ratios": True,
            "build_samples": True,
            "run_training": False,
            "tdx_vipdoc_path": "X:/tdx/vipdoc",
            "minute_interval": 1,
            "commit_every": 50,
        },
    )

    data = resp.json()["data"]
    assert resp.status_code == 200
    assert data["daily_sync"]["rows_synced"] == 2
    assert data["minute_sync"]["rows_synced"] == 120
    assert data["auction_ratio_recalc"]["updated_count"] == 20
    assert data["replay_validation"]["accepted"] is True
    assert data["sample_build"]["created_count"] == 3
    assert data["training_job"] is None
    assert ("daily_sync", "20260501", "20260508", None, 50) in calls
    assert ("minute_sync", "20260501", "20260508", [], 1, 50) in calls
    assert ("auction_recalc", "20260501", "20260508") in calls


def test_default_auction_relay_backtest_api(client, monkeypatch):
    from backend.api import model_management

    captured = {}

    def fake_backtest(db, start_date, end_date, version=None):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["version"] = version
        return {
            "model_name": "default_auction_relay_v2",
            "targets": {
                "default_auction_t0_limit_lgbm": {"metrics": {"top1_rate": 1.0}},
            },
        }

    monkeypatch.setattr(model_management, "run_default_auction_relay_backtest", fake_backtest)

    resp = client.post(
        "/api/v1/models/default-auction-relay/backtest",
        json={"start_date": "20260501", "end_date": "20260508", "version": "v1"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["targets"]["default_auction_t0_limit_lgbm"]["metrics"]["top1_rate"] == 1.0
    assert captured == {"start_date": "20260501", "end_date": "20260508", "version": "v1"}


def test_refresh_default_auction_relay_predictions_returns_explanations(db, monkeypatch, tmp_path):
    _clear_refresh_tables(db)
    _add_relay_stock(db, record_id=9104)
    _add_active_target_models(db, tmp_path)
    target = db.query(ModelVersion).filter_by(model_name="default_auction_t1_premium_lgbm").one()
    target.model_metrics = json.dumps(
        {
            "feature_importance": {"auction_ratio": 10, "auction_turnover_rate": 0},
            "bucket_report": [
                {
                    "feature_name": "auction_ratio",
                    "bucket": "8-15",
                    "lift": 0.2,
                    "conclusion": "高于基准",
                }
            ],
        },
        ensure_ascii=False,
    )
    db.commit()

    probs = {
        "default_auction_t0_limit_lgbm": 30.0,
        "default_auction_t1_premium_lgbm": 40.0,
        "default_auction_t1_continue_lgbm": 50.0,
    }
    monkeypatch.setattr(
        model_management_service.lightgbm_service,
        "_predict_with_model_path",
        lambda model_name, path, cols, features, units: probs[model_name],
    )

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9104)

    explanation = result["explanations"][0]
    assert explanation["ts_code"] == "000001.SZ"
    assert explanation["targets"]["default_auction_t1_premium_lgbm"]["probability"] == 40.0
    assert explanation["targets"]["default_auction_t1_premium_lgbm"]["bucket_explanations"][0]["bucket"] == "8-15"
    assert any(
        "auction_ratio" in item
        for item in explanation["targets"]["default_auction_t1_premium_lgbm"]["positive_factors"]
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
