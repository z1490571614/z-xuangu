from backend.database import SessionLocal
from backend.models import SelectionRecord, SelectedStock
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.model_engine.replay_validation_service import (
    ReplayValidationConfig,
    compare_daily_lists,
    validate_replay_against_real,
)


def setup_function():
    db = SessionLocal()
    try:
        db.query(SelectedStock).delete()
        db.query(SelectionRecord).delete()
        db.commit()
    finally:
        db.close()


def test_compare_daily_lists_computes_overlap_metrics():
    result = compare_daily_lists(
        trade_date="20260508",
        real_codes=["000001.SZ", "000002.SZ", "000003.SZ"],
        replay_codes=["000002.SZ", "000003.SZ", "000004.SZ"],
    )

    assert result["recall"] == 0.6667
    assert result["precision"] == 0.6667
    assert result["jaccard"] == 0.5
    assert result["count_error"] == 0.0
    assert result["intersection"] == ["000002.SZ", "000003.SZ"]


def test_validate_replay_rejects_low_overlap():
    days = [
        {"trade_date": "20260508", "real_codes": ["A", "B", "C"], "replay_codes": ["A", "X", "Y"]},
        {"trade_date": "20260515", "real_codes": ["D", "E", "F"], "replay_codes": ["D", "Y", "Z"]},
    ]
    config = ReplayValidationConfig(min_avg_recall=0.8, min_avg_jaccard=0.6, max_daily_count_error=0.3)

    result = validate_replay_against_real(days, config)

    assert result["accepted"] is False
    assert "avg_recall_below_threshold" in result["reject_reasons"]
    assert "avg_jaccard_below_threshold" in result["reject_reasons"]


def test_validate_replay_rejects_duplicate_replay_codes():
    result = compare_daily_lists(
        trade_date="20260508",
        real_codes=["000001.SZ", "000002.SZ"],
        replay_codes=["000001.SZ", "000001.SZ", "000002.SZ"],
    )

    assert result["duplicate_real_codes"] == []
    assert result["duplicate_replay_codes"] == ["000001.SZ"]

    validation = validate_replay_against_real(
        [{"trade_date": "20260508", "real_codes": ["000001.SZ", "000002.SZ"], "replay_codes": ["000001.SZ", "000001.SZ", "000002.SZ"]}]
    )

    assert validation["accepted"] is False
    assert "duplicate_codes_detected" in validation["reject_reasons"]


def test_validate_replay_rejects_duplicate_real_codes():
    result = compare_daily_lists(
        trade_date="20260508",
        real_codes=["000001.SZ", "000001.SZ", "000002.SZ"],
        replay_codes=["000001.SZ", "000002.SZ"],
    )

    assert result["duplicate_real_codes"] == ["000001.SZ"]
    assert result["duplicate_replay_codes"] == []

    validation = validate_replay_against_real(
        [{"trade_date": "20260508", "real_codes": ["000001.SZ", "000001.SZ", "000002.SZ"], "replay_codes": ["000001.SZ", "000002.SZ"]}]
    )

    assert validation["accepted"] is False
    assert "duplicate_codes_detected" in validation["reject_reasons"]


def test_validate_replay_accepts_matching_lists():
    result = validate_replay_against_real(
        [
            {"trade_date": "20260508", "real_codes": ["000001.SZ", "000002.SZ"], "replay_codes": ["000001.SZ", "000002.SZ"]},
            {"trade_date": "20260515", "real_codes": ["000003.SZ", "000004.SZ"], "replay_codes": ["000003.SZ", "000004.SZ"]},
        ]
    )

    assert result["accepted"] is True
    assert result["reject_reasons"] == []
    assert result["avg_recall"] == 1.0
    assert result["avg_jaccard"] == 1.0
    assert result["max_count_error"] == 0.0


def test_get_recent_real_selection_days_deduplicates_trade_date_with_latest_record():
    db = SessionLocal()
    try:
        other_date_record = SelectionRecord(trade_date="20260508", total_count=1, status="success")
        older_record = SelectionRecord(trade_date="20260515", total_count=1, status="success")
        latest_record = SelectionRecord(trade_date="20260515", total_count=1, status="success")
        db.add_all([other_date_record, older_record, latest_record])
        db.flush()
        db.add_all(
            [
                SelectedStock(record_id=other_date_record.id, ts_code="000001.SZ"),
                SelectedStock(record_id=older_record.id, ts_code="000001.SZ"),
                SelectedStock(record_id=latest_record.id, ts_code="000002.SZ"),
            ]
        )
        db.commit()

        result = DefaultAuctionReplayService(db).get_recent_real_selection_days(limit=2)

        assert [item["trade_date"] for item in result] == ["20260515", "20260508"]
        assert len({item["trade_date"] for item in result}) == 2
        assert result[0]["record_id"] == latest_record.id
        assert result[0]["real_codes"] == ["000002.SZ"]
    finally:
        db.close()


def test_replay_trade_date_uses_latest_record_for_same_trade_date():
    db = SessionLocal()
    try:
        older_record = SelectionRecord(trade_date="20260508", total_count=1, status="success")
        latest_record = SelectionRecord(trade_date="20260508", total_count=2, status="success")
        db.add_all([older_record, latest_record])
        db.flush()
        db.add_all(
            [
                SelectedStock(record_id=older_record.id, ts_code="000001.SZ"),
                SelectedStock(record_id=latest_record.id, ts_code="000002.SZ"),
                SelectedStock(record_id=latest_record.id, ts_code="000003.SZ"),
            ]
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert latest_record.id > older_record.id
        assert result["trade_date"] == "20260508"
        assert result["replay_codes"] == ["000002.SZ", "000003.SZ"]
        assert result["diagnostics"] == []
        assert result["replay_source"] == "historical_backfill"
    finally:
        db.close()
