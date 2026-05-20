import json
from datetime import datetime

from backend.models import DefaultAuctionTrainingSample, StockAuctionOpen, StockMinuteBar, SystemConfig
from backend.models.seal_rate import StockDailyData


class FakeDailySync:
    def __init__(self, calls):
        self.calls = calls

    def sync_range(self, start_date, end_date, ts_codes=None, commit_every=5000):
        self.calls.append(("daily", start_date, end_date, ts_codes, commit_every))
        return {"rows_synced": 3, "stocks_with_rows": 2}


class FakeMinuteSync:
    def __init__(self, calls):
        self.calls = calls

    def sync_range(
        self,
        start_date,
        end_date,
        ts_codes=None,
        interval=1,
        commit_every=5000,
    ):
        self.calls.append(("minute", start_date, end_date, ts_codes, interval, commit_every))
        return {"rows_synced": 8, "rows_skipped_existing": 0, "stocks_with_rows": 2}


class FakeAuctionSync:
    def __init__(self, calls):
        self.calls = calls

    def sync_auction_open(self, trade_date):
        self.calls.append(("auction", trade_date))
        return 2

    def recalculate_auction_ratios_from_daily_cache(self, start_date, end_date):
        self.calls.append(("recalculate", start_date, end_date))
        return {"updated_count": 2, "missing_count": 0}


def test_startup_sync_writes_raw_data_state_and_does_not_create_training_samples(db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        DefaultAuctionRawDataSyncService,
        RAW_SYNC_STATE_KEY,
    )

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()
    calls = []
    service = DefaultAuctionRawDataSyncService(
        session_factory=lambda: db,
        trade_date_provider=lambda: "20240510",
        daily_sync_factory=lambda: FakeDailySync(calls),
        minute_sync_factory=lambda: FakeMinuteSync(calls),
        auction_service_factory=lambda: FakeAuctionSync(calls),
        now_provider=lambda: datetime(2024, 5, 11, 8, 30),
    )

    result = service.run_once_if_needed(trigger="startup")

    assert result["status"] == "success"
    assert result["trade_date"] == "20240510"
    assert calls == [
        ("daily", "20240510", "20240510", None, 5000),
        ("minute", "20240510", "20240510", None, 1, 5000),
        ("auction", "20240510"),
        ("recalculate", "20240510", "20240510"),
    ]
    assert db.query(DefaultAuctionTrainingSample).count() == 0

    state = db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).first()
    assert state is not None
    payload = json.loads(state.value)
    assert payload["trade_date"] == "20240510"
    assert payload["status"] == "success"
    assert payload["trigger"] == "startup"


def test_startup_sync_before_23_uses_previous_completed_trading_day(db, monkeypatch):
    from backend.services.model_engine import default_auction_raw_data_sync_service as raw_sync

    db.query(SystemConfig).filter(SystemConfig.key == raw_sync.RAW_SYNC_STATE_KEY).delete()
    db.commit()
    monkeypatch.setattr(raw_sync, "get_previous_trading_day", lambda trade_date: "20260518")
    calls = []
    service = raw_sync.DefaultAuctionRawDataSyncService(
        session_factory=lambda: db,
        trade_date_provider=lambda: "20260519",
        daily_sync_factory=lambda: FakeDailySync(calls),
        minute_sync_factory=lambda: FakeMinuteSync(calls),
        auction_service_factory=lambda: FakeAuctionSync(calls),
        now_provider=lambda: datetime(2026, 5, 19, 0, 30),
    )

    result = service.run_once_if_needed(trigger="startup")

    assert result["status"] == "success"
    assert result["trade_date"] == "20260518"
    assert calls == [
        ("daily", "20260518", "20260518", None, 5000),
        ("minute", "20260518", "20260518", None, 1, 5000),
        ("auction", "20260518"),
        ("recalculate", "20260518", "20260518"),
    ]


def test_startup_sync_marks_success_when_raw_data_already_present(db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        DefaultAuctionRawDataSyncService,
        RAW_SYNC_STATE_KEY,
    )

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockMinuteBar).delete()
    db.query(StockDailyData).delete()
    db.add(
        SystemConfig(
            key=RAW_SYNC_STATE_KEY,
            value=json.dumps({"trade_date": "20260519", "status": "failed"}),
            value_type="json",
        )
    )
    db.add(StockDailyData(trade_date="20260518", ts_code="000001.SZ", open=10, close=10))
    db.add(StockMinuteBar(trade_date="20260518", ts_code="000001.SZ", trade_time="09:31", bar_time="2026-05-18 09:31:00"))
    db.add(StockAuctionOpen(trade_date="20260518", ts_code="000001.SZ"))
    db.commit()
    calls = []
    service = DefaultAuctionRawDataSyncService(
        session_factory=lambda: db,
        trade_date_provider=lambda: "20260518",
        daily_sync_factory=lambda: FakeDailySync(calls),
        minute_sync_factory=lambda: FakeMinuteSync(calls),
        auction_service_factory=lambda: FakeAuctionSync(calls),
        now_provider=lambda: datetime(2026, 5, 19, 0, 40),
    )

    result = service.run_once_if_needed(trigger="startup")

    assert result["status"] == "success"
    assert result["trade_date"] == "20260518"
    assert result["reason"] == "raw_data_already_present"
    assert result["stage_results"]["daily_sync"]["rows_existing"] == 1
    assert calls == []


def test_startup_sync_skips_when_same_trade_date_already_succeeded(db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        DefaultAuctionRawDataSyncService,
        RAW_SYNC_STATE_KEY,
    )

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.add(
        SystemConfig(
            key=RAW_SYNC_STATE_KEY,
            value=json.dumps({"trade_date": "20240510", "status": "success"}),
            value_type="json",
        )
    )
    db.commit()
    calls = []
    service = DefaultAuctionRawDataSyncService(
        session_factory=lambda: db,
        trade_date_provider=lambda: "20240510",
        daily_sync_factory=lambda: FakeDailySync(calls),
        minute_sync_factory=lambda: FakeMinuteSync(calls),
        auction_service_factory=lambda: FakeAuctionSync(calls),
    )

    result = service.run_once_if_needed(trigger="startup")

    assert result == {"status": "skipped", "trade_date": "20240510", "reason": "already_synced"}
    assert calls == []


def test_raw_data_sync_state_returns_display_payload(db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        RAW_SYNC_STATE_KEY,
        get_default_auction_raw_data_sync_state,
    )

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockMinuteBar).delete()
    db.query(StockDailyData).delete()
    db.add(StockDailyData(trade_date="20240511", ts_code="000001.SZ", open=10, close=10))
    db.add(StockMinuteBar(trade_date="20240510", ts_code="000001.SZ", trade_time="09:31", bar_time="2024-05-10 09:31:00"))
    db.add(StockAuctionOpen(trade_date="20240512", ts_code="000001.SZ"))
    db.add(
        SystemConfig(
            key=RAW_SYNC_STATE_KEY,
            value=json.dumps(
                {
                    "trade_date": "20240510",
                    "status": "success",
                    "trigger": "daily_2300",
                    "finished_at": "2024-05-10T23:05:00",
                    "stage_results": {"daily_sync": {"rows_synced": 3}},
                },
                ensure_ascii=False,
            ),
            value_type="json",
        )
    )
    db.commit()

    result = get_default_auction_raw_data_sync_state(db)

    assert result["trade_date"] == "20240510"
    assert result["synced_to_date"] == "20240510"
    assert result["status"] == "success"
    assert result["trigger"] == "daily_2300"
    assert result["data_max_dates"] == {"daily": "20240511", "minute": "20240510", "auction": "20240512"}
    assert result["stage_results"]["daily_sync"]["rows_synced"] == 3


def test_raw_data_sync_state_returns_not_synced_when_missing(db):
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        RAW_SYNC_STATE_KEY,
        get_default_auction_raw_data_sync_state,
    )

    db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).delete()
    db.commit()

    result = get_default_auction_raw_data_sync_state(db)

    assert result["trade_date"] is None
    assert result["status"] == "not_synced"
    assert result["stage_results"] == {}


def test_scheduler_registers_daily_23_job_and_startup_async():
    from backend.services.model_engine.default_auction_raw_data_sync_service import (
        DefaultAuctionRawDataSyncScheduler,
    )

    class FakeScheduler:
        def __init__(self):
            self.running = False
            self.jobs = []

        def add_job(self, func, trigger, id, replace_existing, max_instances, coalesce):
            self.jobs.append(
                {
                    "func": func,
                    "trigger": trigger,
                    "id": id,
                    "replace_existing": replace_existing,
                    "max_instances": max_instances,
                    "coalesce": coalesce,
                }
            )

        def start(self):
            self.running = True

        def shutdown(self, wait=False):
            self.running = False

    fake_scheduler = FakeScheduler()
    service_calls = []

    class FakeService:
        def run_once_if_needed(self, trigger):
            service_calls.append(trigger)
            return {"status": "success"}

    wrapper = DefaultAuctionRawDataSyncScheduler(
        scheduler=fake_scheduler,
        service_factory=lambda: FakeService(),
    )

    wrapper.start()
    fake_scheduler.jobs[0]["func"]()

    assert fake_scheduler.running is True
    assert fake_scheduler.jobs[0]["id"] == "default_auction_raw_data_sync_2300"
    assert "23" in str(fake_scheduler.jobs[0]["trigger"])
    assert service_calls == ["daily_2300"]
