from datetime import datetime, timedelta

from backend.database import SessionLocal
from backend.models import SelectionRecord, SelectedStock, StockAuctionOpen, StockFeatureSnapshot
from backend.models.seal_rate import SealRateCache, StockDailyData
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.model_engine.replay_validation_service import (
    ReplayValidationConfig,
    compare_daily_lists,
    validate_replay_against_real,
)
from backend.services.tdx_local_selector import get_limit_price


def _add_daily_closes(db, ts_code, end_date, closes):
    code = ts_code.split(".")[0]
    start = datetime.strptime(end_date, "%Y%m%d").date() - timedelta(days=len(closes) - 1)
    for index, close in enumerate(closes):
        trade_date = (start + timedelta(days=index)).strftime("%Y%m%d")
        pre_close = closes[index - 1] if index else close
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code=ts_code,
                close=close,
                high=close,
                pre_close=pre_close,
                up_limit=get_limit_price(code, pre_close),
            )
        )


def _add_daily_bars_with_touch_days(db, ts_code, end_date, touch_indexes, sealed_indexes, length=101):
    code = ts_code.split(".")[0]
    start = datetime.strptime(end_date, "%Y%m%d").date() - timedelta(days=length - 1)
    prev_close = 10.0
    for index in range(length):
        up_limit = get_limit_price(code, prev_close)
        if index in touch_indexes:
            high = up_limit
            close = up_limit if index in sealed_indexes else prev_close
        else:
            high = prev_close
            close = prev_close
        db.add(
            StockDailyData(
                trade_date=(start + timedelta(days=index)).strftime("%Y%m%d"),
                ts_code=ts_code,
                high=high,
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
            )
        )
        prev_close = close


def _daily_closes_with_limit_days(ts_code, length=101, limit_day_indexes=(), start_close=10.0):
    code = ts_code.split(".")[0]
    closes = []
    prev_close = start_close
    for index in range(length):
        close = get_limit_price(code, prev_close) if index in limit_day_indexes else prev_close
        closes.append(close)
        prev_close = close
    return closes


def setup_function():
    db = SessionLocal()
    try:
        db.query(SelectedStock).delete()
        db.query(SelectionRecord).delete()
        db.query(StockAuctionOpen).delete()
        db.query(StockFeatureSnapshot).delete()
        db.query(StockDailyData).delete()
        db.query(SealRateCache).delete()
        db.commit()
    finally:
        db.close()


def teardown_function():
    db = SessionLocal()
    try:
        db.query(SelectedStock).delete()
        db.query(SelectionRecord).delete()
        db.query(StockAuctionOpen).delete()
        db.query(StockFeatureSnapshot).delete()
        db.query(StockDailyData).delete()
        db.query(SealRateCache).delete()
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
    assert result["top5_overlap"] == 0.4
    assert result["top10_overlap"] == 0.2
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


def test_get_recent_real_selection_days_filters_by_end_date():
    db = SessionLocal()
    try:
        later_record = SelectionRecord(trade_date="20260515", total_count=1, status="success")
        target_record = SelectionRecord(trade_date="20260508", total_count=1, status="success")
        earlier_record = SelectionRecord(trade_date="20260507", total_count=1, status="success")
        db.add_all([later_record, target_record, earlier_record])
        db.flush()
        db.add_all(
            [
                SelectedStock(record_id=later_record.id, ts_code="000003.SZ"),
                SelectedStock(record_id=target_record.id, ts_code="000002.SZ"),
                SelectedStock(record_id=earlier_record.id, ts_code="000001.SZ"),
            ]
        )
        db.commit()

        result = DefaultAuctionReplayService(db).get_recent_real_selection_days(limit=5, end_date="20260508")

        assert [item["trade_date"] for item in result] == ["20260508", "20260507"]
        assert all(item["trade_date"] <= "20260508" for item in result)
    finally:
        db.close()


def test_replay_trade_date_does_not_echo_real_selection_without_independent_source():
    db = SessionLocal()
    try:
        record = SelectionRecord(trade_date="20260508", total_count=2, status="success")
        db.add(record)
        db.flush()
        db.add_all(
            [
                SelectedStock(record_id=record.id, ts_code="000002.SZ"),
                SelectedStock(record_id=record.id, ts_code="000003.SZ"),
            ]
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["trade_date"] == "20260508"
        assert result["replay_codes"] == []
        assert "no_independent_replay_source" in result["diagnostics"]
        assert result["replay_source"] is None
    finally:
        db.close()


def test_replay_trade_date_uses_stock_auction_open_as_independent_source():
    db = SessionLocal()
    try:
        db.add_all(
            [
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="000001.SZ",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8.19,
                    auction_turnover_rate=0.8,
                    source="tushare_stk_auction",
                ),
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="000002.SZ",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=35.0,
                    auction_turnover_rate=0.8,
                    source="tushare_stk_auction",
                ),
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="000003.SZ",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8.19,
                    auction_turnover_rate=12.0,
                    source="tushare_stk_auction",
                ),
            ]
        )
        db.commit()
        _add_daily_closes(
            db,
            "000001.SZ",
            "20260508",
            _daily_closes_with_limit_days("000001.SZ", limit_day_indexes={20, 50, 80}),
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["trade_date"] == "20260508"
        assert result["replay_codes"] == ["000001.SZ"]
        assert result["replay_source"] == "stock_auction_open"
        assert result["diagnostics"] == []
    finally:
        db.close()


def test_replay_trade_date_ignores_non_common_a_share_codes():
    db = SessionLocal()
    try:
        db.add_all(
            [
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="000001.SZ",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                ),
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="510300.SH",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                ),
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code="430001.BJ",
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                ),
            ]
        )
        db.commit()
        _add_daily_closes(
            db,
            "000001.SZ",
            "20260508",
            _daily_closes_with_limit_days("000001.SZ", limit_day_indexes={20, 50, 80}),
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["replay_codes"] == ["000001.SZ"]
        assert result["filter_diagnostics"]["510300.SH"] == ["not_common_a_share"]
        assert result["filter_diagnostics"]["430001.BJ"] == ["not_common_a_share"]
    finally:
        db.close()


def test_replay_trade_date_applies_daily_structural_filters_without_snapshots():
    db = SessionLocal()
    try:
        for code in ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"]:
            db.add(
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code=code,
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                )
            )

        _add_daily_closes(
            db,
            "000001.SZ",
            "20260508",
            _daily_closes_with_limit_days("000001.SZ", limit_day_indexes={20, 50, 80}),
        )
        _add_daily_closes(
            db,
            "000002.SZ",
            "20260508",
            _daily_closes_with_limit_days("000002.SZ", limit_day_indexes=set()),
        )
        falling_closes = _daily_closes_with_limit_days("000003.SZ", limit_day_indexes={20, 50, 80})
        falling_closes[-2] = falling_closes[-12] - 1
        _add_daily_closes(db, "000003.SZ", "20260508", falling_closes)
        expensive_closes = _daily_closes_with_limit_days("000004.SZ", limit_day_indexes={20, 50, 80}, start_close=600)
        _add_daily_closes(db, "000004.SZ", "20260508", expensive_closes)
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["replay_codes"] == ["000001.SZ"]
        assert result["filter_diagnostics"]["000002.SZ"] == ["limit_up_count_below_default"]
        assert result["filter_diagnostics"]["000003.SZ"] == ["rise_10d_not_positive"]
        assert result["filter_diagnostics"]["000004.SZ"] == ["close_price_above_default"]
    finally:
        db.close()


def test_replay_trade_date_applies_structural_filters_when_snapshots_exist():
    db = SessionLocal()
    try:
        for code in ["000001.SZ", "000002.SZ", "000003.SZ"]:
            db.add(
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code=code,
                    price=10.2,
                    pre_close=10.0,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                )
            )
        db.add_all(
            [
                StockFeatureSnapshot(
                    trade_date="20260508",
                    ts_code="000001.SZ",
                    limit_up_count_100d=3,
                    rise_10d_pct=5,
                    circ_mv=100,
                    close_return=0,
                ),
                StockFeatureSnapshot(
                    trade_date="20260508",
                    ts_code="000002.SZ",
                    limit_up_count_100d=2,
                    rise_10d_pct=5,
                    circ_mv=100,
                    close_return=0,
                ),
                StockFeatureSnapshot(
                    trade_date="20260508",
                    ts_code="000003.SZ",
                    limit_up_count_100d=3,
                    rise_10d_pct=-1,
                    circ_mv=100,
                    close_return=0,
                ),
            ]
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["replay_codes"] == ["000001.SZ"]
        assert result["filter_diagnostics"]["000002.SZ"] == ["limit_up_count_below_default"]
        assert result["filter_diagnostics"]["000003.SZ"] == ["rise_10d_not_positive"]
    finally:
        db.close()


def test_replay_trade_date_prefers_daily_cache_for_trend_when_snapshot_rise_is_stale():
    db = SessionLocal()
    try:
        db.add(
            StockAuctionOpen(
                trade_date="20260511",
                ts_code="000001.SZ",
                price=10.2,
                pre_close=10.0,
                auction_ratio=8,
                auction_turnover_rate=1,
                source="stock_auction_open",
            )
        )
        db.add(
            StockFeatureSnapshot(
                trade_date="20260511",
                ts_code="000001.SZ",
                limit_up_count_100d=3,
                rise_10d_pct=-1,
                circ_mv=100,
                close_return=0,
            )
        )
        _add_daily_closes(
            db,
            "000001.SZ",
            "20260511",
            _daily_closes_with_limit_days("000001.SZ", limit_day_indexes={20, 50, 80}),
        )
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260511")

        assert result["replay_codes"] == ["000001.SZ"]
        assert "000001.SZ" not in result["filter_diagnostics"]
    finally:
        db.close()


def test_replay_trade_date_applies_default_seal_rate_and_open_change_filters():
    db = SessionLocal()
    try:
        rows = [
            ("000001.SZ", 10.2, 10.0),
            ("000002.SZ", 10.2, 10.0),
            ("000003.SZ", 9.69, 10.0),
            ("000004.SZ", 10.2, 10.0),
        ]
        for code, price, pre_close in rows:
            db.add(
                StockAuctionOpen(
                    trade_date="20260508",
                    ts_code=code,
                    price=price,
                    pre_close=pre_close,
                    auction_ratio=8,
                    auction_turnover_rate=1,
                    source="stock_auction_open",
                )
            )
        _add_daily_bars_with_touch_days(db, "000001.SZ", "20260508", {20, 50, 80}, {20, 50, 80})
        _add_daily_bars_with_touch_days(db, "000002.SZ", "20260508", {20, 35, 50, 65, 80}, {20, 50, 80})
        _add_daily_bars_with_touch_days(db, "000003.SZ", "20260508", {20, 50, 80}, {20, 50, 80})
        _add_daily_bars_with_touch_days(db, "000004.SZ", "20260508", {20, 50, 80}, {20, 50, 80})
        db.commit()

        result = DefaultAuctionReplayService(db).replay_trade_date("20260508")

        assert result["replay_codes"] == ["000001.SZ", "000004.SZ"]
        assert result["filter_diagnostics"]["000002.SZ"] == ["seal_rate_below_default"]
        assert result["filter_diagnostics"]["000003.SZ"] == ["open_change_below_default"]
        assert "000004.SZ" not in result["filter_diagnostics"]
    finally:
        db.close()
