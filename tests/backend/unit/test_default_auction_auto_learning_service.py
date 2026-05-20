import json

import pytest

from backend.database import Base, engine
from backend.models import DefaultAuctionAutoLearningRun, SelectionRecord, SelectedStock


def _make_service(db, **deps):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningCreate,
        DefaultAuctionAutoLearningService,
    )

    service = DefaultAuctionAutoLearningService(session_factory=lambda: db, **deps)
    request = DefaultAuctionAutoLearningCreate(
        start_date="20240501",
        end_date="20240510",
        selected_record_ids=[9101],
        refresh_record_ids=[9101],
        sync_daily=True,
        sync_minute=True,
        recalculate_auction_ratios=True,
        validate_replay=True,
        build_real_samples=True,
        build_replay_samples=True,
        audit_training_data=True,
        run_training=True,
        run_backtest=True,
        auto_activate=True,
        refresh_predictions=True,
        params={"max_retrain_attempts": 1},
        acceptance={"max_prediction_failed_count": 0},
    )
    return service, request


def test_create_auto_learning_run_saves_options_and_defaults(db):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningCreate,
        create_auto_learning_run,
    )

    Base.metadata.create_all(bind=engine)
    run = create_auto_learning_run(
        db,
        DefaultAuctionAutoLearningCreate(start_date="20240501", end_date="20240510"),
    )

    assert run.id is not None
    assert run.status == "pending"
    assert run.phase == "prepare"
    assert run.progress == 0
    options = json.loads(run.options_json)
    assert options["audit_training_data"] is True
    assert options["run_training"] is False
    assert json.loads(run.logs_json)[0]["message"] == "自动学习运行已创建"


def test_create_auto_learning_run_reuses_active_run_and_allows_finished_rerun(db):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningCreate,
        create_auto_learning_run,
        create_or_reuse_auto_learning_run,
    )

    db.query(DefaultAuctionAutoLearningRun).delete()
    db.commit()

    first, first_created = create_or_reuse_auto_learning_run(
        db,
        DefaultAuctionAutoLearningCreate(start_date="20240501", end_date="20240510"),
    )
    second, second_created = create_or_reuse_auto_learning_run(
        db,
        DefaultAuctionAutoLearningCreate(start_date="20240511", end_date="20240512"),
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert db.query(DefaultAuctionAutoLearningRun).count() == 1

    first.status = "passed"
    db.commit()
    third = create_auto_learning_run(
        db,
        DefaultAuctionAutoLearningCreate(start_date="20240511", end_date="20240512"),
    )

    assert third.id != first.id
    assert db.query(DefaultAuctionAutoLearningRun).count() == 2


def test_create_auto_learning_run_rejects_invalid_activation_contract(db):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningCreate,
        create_auto_learning_run,
    )

    with pytest.raises(ValueError, match="auto_activate"):
        create_auto_learning_run(
            db,
            DefaultAuctionAutoLearningCreate(
                start_date="20240501",
                end_date="20240510",
                auto_activate=True,
                audit_training_data=True,
                run_training=True,
                run_backtest=False,
            ),
        )


def test_auto_learning_success_runs_all_stages_and_activates(db):
    from backend.models import ModelTrainingJob
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningService,
        create_auto_learning_run,
    )

    Base.metadata.create_all(bind=engine)
    db.add(SelectionRecord(id=9101, trade_date="20240510", status="success", total_count=1))
    db.add(SelectedStock(record_id=9101, ts_code="000001.SZ", name="平安银行"))
    db.commit()
    calls = []

    class FakeDaily:
        def sync_range(self, *args, **kwargs):
            calls.append(("daily", args, kwargs))
            return {"rows_synced": 10}

    class FakeMinute:
        def sync_range(self, *args, **kwargs):
            calls.append(("minute", args, kwargs))
            return {"rows_synced": 20}

    class FakeAuction:
        def recalculate_auction_ratios_from_daily_cache(self, start_date, end_date):
            calls.append(("recalc", start_date, end_date))
            return {"updated_count": 5}

    def fake_train(job_id):
        job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).one()
        job.status = "passed"
        job.phase = "accepted"
        job.progress = 100
        job.acceptance_json = json.dumps(
            {
                "targets": {
                    "default_auction_t0_limit_lgbm": {"accepted": True, "version": "v_t0"},
                    "default_auction_t1_premium_lgbm": {"accepted": True, "version": "v_premium"},
                    "default_auction_t1_continue_lgbm": {"accepted": True, "version": "v_continue"},
                },
                "all_accepted": True,
            }
        )
        db.commit()

    service = DefaultAuctionAutoLearningService(
        session_factory=lambda: db,
        daily_sync_factory=lambda path: FakeDaily(),
        minute_sync_factory=lambda path: FakeMinute(),
        auction_service_factory=lambda: FakeAuction(),
        validate_replay_func=lambda db, recent_days, end_date=None: {"accepted": True, "daily": []},
        build_real_sample_func=lambda db, record_id, source: {"created_count": 1, "record_id": record_id},
        build_replay_sample_func=lambda db, start, end, source: {"created_count": 3},
        audit_func=lambda db: {"ok": True, "errors": []},
        create_job_func=lambda db, start_date, end_date, params, auto_activate: ModelTrainingJob(
            model_name="default_auction_relay_v2",
            status="pending",
            phase="prepare",
            progress=0,
            train_start_date=start_date,
            train_end_date=end_date,
            params_json=json.dumps(params),
            acceptance_json="{}",
            attempts_json="[]",
            logs_json="[]",
        ),
        run_training_func=fake_train,
        diagnostics_func=lambda db, job_id: {
            "id": job_id,
            "status": "passed",
            "acceptance": json.loads(db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).one().acceptance_json),
        },
        backtest_func=lambda db, start_date, end_date, target_versions=None, version=None: {
            "targets": {
                "default_auction_t0_limit_lgbm": {"prediction_failed_count": 0, "metrics": {"auc": 0.7}},
                "default_auction_t1_premium_lgbm": {"prediction_failed_count": 0, "metrics": {"auc": 0.65}},
                "default_auction_t1_continue_lgbm": {"prediction_failed_count": 0, "metrics": {"auc": 0.66}},
            }
        },
        activate_func=lambda db, model_name, version: {"model_name": model_name, "version": version},
        refresh_func=lambda db, model_name, record_id, version=None: {"updated_count": 1, "failed_count": 0},
    )
    run = create_auto_learning_run(db, _make_service(db)[1])

    service.run_auto_learning(run.id)

    refreshed = db.query(DefaultAuctionAutoLearningRun).filter_by(id=run.id).one()
    assert refreshed.status == "passed"
    assert refreshed.phase == "finish"
    assert refreshed.progress == 100
    stage_results = json.loads(refreshed.stage_results_json)
    assert stage_results["daily_sync"]["rows_synced"] == 10
    assert stage_results["sample_build"]["real"]["created_count"] == 1
    assert json.loads(refreshed.activated_versions_json) == {
        "default_auction_t0_limit_lgbm": "v_t0",
        "default_auction_t1_premium_lgbm": "v_premium",
        "default_auction_t1_continue_lgbm": "v_continue",
    }
    assert json.loads(refreshed.refreshed_record_ids_json) == [9101]


def test_replay_validation_failure_blocks_sample_training_and_activation(db):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        create_auto_learning_run,
    )

    calls = []
    service, request = _make_service(
        db,
        validate_replay_func=lambda db, recent_days, end_date=None: {
            "accepted": False,
            "reject_reasons": ["low_recall"],
        },
        build_replay_sample_func=lambda *args, **kwargs: calls.append("build_replay"),
        create_job_func=lambda *args, **kwargs: calls.append("train"),
        activate_func=lambda *args, **kwargs: calls.append("activate"),
    )
    run = create_auto_learning_run(db, request)

    service.run_auto_learning(run.id)

    refreshed = db.query(DefaultAuctionAutoLearningRun).filter_by(id=run.id).one()
    assert refreshed.status == "failed"
    assert refreshed.phase == "validate_replay"
    assert "回放验收未通过" in refreshed.error_message
    assert calls == []


def test_request_cancel_pending_run_marks_cancelled(db):
    from backend.services.model_engine.default_auction_auto_learning_service import (
        DefaultAuctionAutoLearningCreate,
        create_auto_learning_run,
        request_cancel_auto_learning_run,
    )

    run = create_auto_learning_run(
        db,
        DefaultAuctionAutoLearningCreate(start_date="20240501", end_date="20240510"),
    )

    payload = request_cancel_auto_learning_run(db, run.id)

    assert payload["status"] == "cancelled"
    assert db.query(DefaultAuctionAutoLearningRun).filter_by(id=run.id).one().status == "cancelled"
