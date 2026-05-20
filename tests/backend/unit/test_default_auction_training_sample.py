import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect

from backend.database import Base, engine
from backend.database.schema_migrations import ensure_runtime_columns
from backend.models import (
    DefaultAuctionTrainingSample,
    SelectionRecord,
    SelectedStock,
    StockAuctionOpen,
    StockFeatureSnapshot,
)
from backend.models.seal_rate import SealRateCache, StockDailyData
from backend.services.model_engine.default_auction_label_builder import (
    build_t0_limit_audit,
    build_t0_limit_label,
    build_t1_continue_audit,
    build_t1_continue_label,
    build_t1_premium_label,
)
from backend.services.model_engine.default_auction_sample_builder import (
    build_samples_from_replay_range,
    build_samples_from_selected_record,
)
from backend.services.tdx_local_selector import get_limit_price


def _add_default_replay_daily_rows(db, ts_code: str, end_date: str):
    code = ts_code.split(".")[0]
    start = datetime.strptime(end_date, "%Y%m%d").date() - timedelta(days=100)
    prev_close = 10.0
    for index in range(101):
        close = get_limit_price(code, prev_close) if index in {20, 50, 80} else prev_close
        trade_date = (start + timedelta(days=index)).strftime("%Y%m%d")
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code=ts_code,
                open=close,
                high=close,
                low=close,
                close=close,
                pre_close=prev_close,
                up_limit=get_limit_price(code, prev_close),
                is_adj=0,
            )
        )
        prev_close = close


def test_default_auction_training_sample_is_registered(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()

    sample = DefaultAuctionTrainingSample(
        trade_date="20260508",
        ts_code="000001.SZ",
        name="测试股",
        strategy_name="default",
        strategy_version="default_auction_v2",
        sample_source="replay_backtest",
        replay_source="local_replay",
        auction_source="stock_auction_open",
        auction_ratio_unit="percent",
        auction_turnover_rate_basis="free_float",
        feature_snapshot_time="2026-05-08T09:31:00",
        feature_json=json.dumps({"auction_ratio": 8.19}, ensure_ascii=False),
        label_t0_limit_success=1,
        label_t1_premium_success=0,
        label_t1_continue_limit=0,
    )
    db.add(sample)
    db.commit()

    saved = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000001.SZ").one()
    assert saved.strategy_version == "default_auction_v2"
    assert json.loads(saved.feature_json)["auction_ratio"] == 8.19


def test_selected_stock_has_default_auction_relay_prediction_fields():
    columns = {column.name for column in SelectedStock.__table__.columns}
    assert "default_t0_limit_prob" in columns
    assert "default_t1_premium_prob" in columns
    assert "default_t1_continue_prob" in columns
    assert "default_relay_score" in columns
    assert "default_relay_model_version" in columns


def test_build_samples_from_selected_record_excludes_news_features(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9001, trade_date="20260508", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9001,
            ts_code="000001.SZ",
            name="测试股",
            auction_ratio=8.19,
            auction_turnover_rate=0.8,
            open_change_pct=4.2,
            pre_change_pct=9.8,
            limit_up_count=5,
            touch_days=8,
            limit_up_days=6,
            seal_rate=80,
            rise_10d_pct=12,
            circ_mv=120,
            rule_score=70,
            final_score=82,
            score_level="A",
            risk_tags='["资金分歧"]',
            prev_turnover_rate=18.5,
            lu_tag="首板",
            lu_status="换手板",
            lu_open_num=2,
            limit_up_suc_rate=66.6,
            reasons="不应进入训练特征的AI文本",
            next_day_plan="不应进入训练特征的开盘预案",
        )
    )
    db.commit()

    result = build_samples_from_selected_record(db, 9001, sample_source="real_selected")

    assert result["created_count"] == 1
    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000001.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["auction_ratio"] == 8.19
    assert features["risk_tags_count"] == 1
    assert features["prev_turnover_rate"] == 18.5
    assert features["lu_tag"] == "首板"
    assert features["lu_status"] == "换手板"
    assert features["lu_open_num"] == 2
    assert features["limit_up_suc_rate"] == 66.6
    assert "market_limit_up_count" in features
    assert "sector_strength" in features
    assert "leader_strength_score" in features
    assert "retreat_risk_score" in features
    assert "technical_score" in features
    assert "risk_tags" not in features
    assert "has_negative_news" not in features
    assert "announcement_alpha_score" not in features
    assert "reasons" not in features
    assert "next_day_plan" not in features


def test_build_samples_from_selected_record_merges_auction_open_amount_and_volume(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9006, trade_date="20260513", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9006,
            ts_code="000007.SZ",
            name="真实竞价样本",
            auction_ratio=6.2,
            auction_turnover_rate=0.9,
            open_change_pct=3.8,
            pre_change_pct=9.9,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260513",
            ts_code="000007.SZ",
            price=10.38,
            vol=123456,
            amount=1281488.88,
            pre_close=10.0,
            auction_ratio=6.2,
            auction_turnover_rate=0.9,
            source="tushare_stk_auction",
        )
    )
    db.commit()

    build_samples_from_selected_record(db, 9006, sample_source="real_selected")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000007.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["auction_amount"] == 1281488.88
    assert features["auction_volume"] == 123456
    assert sample.auction_source == "tushare_stk_auction"


def test_build_samples_from_selected_record_applies_market_labels_and_daily_seal_features(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000030.SZ").delete()
    db.commit()
    db.add(SelectionRecord(id=9010, trade_date="20260508", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9010,
            ts_code="000030.SZ",
            name="真实样本",
            auction_ratio=8.5,
            auction_turnover_rate=1.1,
            open_change_pct=4.0,
            pre_change_pct=6.0,
            limit_up_count=None,
            touch_days=None,
            limit_up_days=None,
            seal_rate=None,
            rise_10d_pct=None,
        )
    )

    code = "000030"
    prev_close = 10.0
    dates = [
        "20260416",
        "20260417",
        "20260420",
        "20260421",
        "20260424",
        "20260427",
        "20260428",
        "20260429",
        "20260430",
        "20260506",
        "20260507",
        "20260508",
    ]
    for index, trade_date in enumerate(dates):
        up_limit = get_limit_price(code, prev_close)
        is_limit = index in {2, 5, 10, 11}
        close = up_limit if is_limit else prev_close + 0.1
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code="000030.SZ",
                open=prev_close,
                high=up_limit if is_limit else close,
                low=prev_close,
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
                is_adj=0,
            )
        )
        prev_close = close
    next_up_limit = get_limit_price(code, prev_close)
    db.add(
        StockDailyData(
            trade_date="20260511",
            ts_code="000030.SZ",
            open=round(prev_close * 1.04, 2),
            high=next_up_limit,
            low=round(prev_close * 1.03, 2),
            close=next_up_limit,
            pre_close=prev_close,
            up_limit=next_up_limit,
            is_adj=0,
        )
    )
    db.commit()

    build_samples_from_selected_record(db, 9010, sample_source="real_selected")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000030.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["limit_up_count"] == 3
    assert features["touch_days"] == 3
    assert features["limit_up_days"] == 3
    assert features["seal_rate"] == 100.0
    assert features["rise_10d_pct"] is not None
    assert sample.label_t0_limit_success == 1
    assert sample.label_t1_premium_success == 1
    assert sample.label_t1_continue_limit == 1
    assert sample.t1_open_return >= 3


def test_build_samples_from_selected_record_upserts_without_duplicates(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9002, trade_date="20260509", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9002,
            ts_code="000002.SZ",
            name="测试股二",
            auction_ratio=6.5,
            auction_turnover_rate=1.2,
            open_change_pct=3.1,
            pre_change_pct=4.8,
            limit_up_count=4,
            touch_days=5,
            limit_up_days=4,
            seal_rate=80,
            rise_10d_pct=9,
            circ_mv=90,
            rule_score=60,
            final_score=72,
            score_level="B",
            risk_tags='["低风险"]',
        )
    )
    db.commit()

    first = build_samples_from_selected_record(db, 9002, sample_source="real_selected")
    stock = db.query(SelectedStock).filter_by(record_id=9002, ts_code="000002.SZ").one()
    stock.final_score = 75
    db.commit()
    second = build_samples_from_selected_record(db, 9002, sample_source="real_selected")

    rows = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000002.SZ").all()
    assert first["created_count"] == 1
    assert second["updated_count"] == 1
    assert len(rows) == 1
    assert json.loads(rows[0].feature_json)["final_score"] == 75.0


def test_build_samples_from_selected_record_counts_invalid_risk_tags_as_zero(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9003, trade_date="20260510", status="success", total_count=2))
    db.add(
        SelectedStock(
            record_id=9003,
            ts_code="000003.SZ",
            name="非法JSON",
            auction_ratio=5,
            auction_turnover_rate=1,
            risk_tags="{bad json",
        )
    )
    db.add(
        SelectedStock(
            record_id=9003,
            ts_code="000004.SZ",
            name="非列表JSON",
            auction_ratio=7,
            auction_turnover_rate=1,
            risk_tags='{"risk": "资金分歧"}',
        )
    )
    db.commit()

    result = build_samples_from_selected_record(db, 9003, sample_source="real_selected")

    assert result["created_count"] == 2
    samples = {
        row.ts_code: json.loads(row.feature_json)
        for row in db.query(DefaultAuctionTrainingSample).filter(
            DefaultAuctionTrainingSample.trade_date == "20260510"
        )
    }
    assert samples["000003.SZ"]["risk_tags_count"] == 0
    assert samples["000004.SZ"]["risk_tags_count"] == 0


def test_build_samples_from_selected_record_dedupes_duplicate_ts_code_in_batch(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9004, trade_date="20260511", status="success", total_count=2))
    db.add(
        SelectedStock(
            record_id=9004,
            ts_code="000005.SZ",
            name="重复前",
            auction_ratio=5,
            auction_turnover_rate=1,
            final_score=60,
            risk_tags='["旧"]',
        )
    )
    db.add(
        SelectedStock(
            record_id=9004,
            ts_code="000005.SZ",
            name="重复后",
            auction_ratio=9,
            auction_turnover_rate=2,
            final_score=88,
            risk_tags='["新", "资金"]',
        )
    )
    db.commit()

    result = build_samples_from_selected_record(db, 9004, sample_source="real_selected")

    rows = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000005.SZ").all()
    assert result["created_count"] == 1
    assert result["updated_count"] == 1
    assert len(rows) == 1
    features = json.loads(rows[0].feature_json)
    assert features["auction_ratio"] == 9
    assert features["final_score"] == 88.0
    assert features["risk_tags_count"] == 2


def test_build_samples_from_selected_record_writes_standard_json_for_nan_and_inf(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9005, trade_date="20260512", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9005,
            ts_code="000006.SZ",
            name="非标准浮点",
            auction_ratio=float("nan"),
            auction_turnover_rate=float("inf"),
            open_change_pct=float("-inf"),
        )
    )
    db.commit()

    build_samples_from_selected_record(db, 9005, sample_source="real_selected")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000006.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["auction_ratio"] is None
    assert features["auction_turnover_rate"] is None
    assert features["open_change_pct"] is None
    json.dumps(features, allow_nan=False)


def test_build_samples_from_replay_range_writes_features_and_three_labels(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000001.SZ",
            price=10.4,
            vol=100000,
            amount=1040000,
            pre_close=10.0,
            auction_ratio=8.19,
            auction_turnover_rate=0.8,
            source="stock_auction_open",
        )
    )
    db.add(
        StockFeatureSnapshot(
            trade_date="20260508",
            ts_code="000001.SZ",
            limit_up_count_100d=5,
            seal_rate_100d=88,
            rise_10d_pct=12,
            circ_mv=120,
            pre_change_pct=9.8,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260509",
            ts_code="000001.SZ",
            price=11.1,
            vol=120000,
            amount=1332000,
            pre_close=10.0,
            auction_ratio=9.1,
            auction_turnover_rate=1.2,
            source="stock_auction_open",
        )
    )
    db.commit()

    daily_rows = {
        ("20260508", "000001.SZ"): {
            "open": 10.4,
            "high": 11.0,
            "low": 10.2,
            "close": 11.0,
            "pre_close": 10.0,
        },
        ("20260509", "000001.SZ"): {
            "open": 11.4,
            "high": 12.1,
            "low": 11.2,
            "close": 12.1,
            "pre_close": 11.0,
        },
    }

    result = build_samples_from_replay_range(
        db,
        start_date="20260508",
        end_date="20260508",
        daily_rows=daily_rows,
    )

    sample = db.query(DefaultAuctionTrainingSample).filter_by(
        trade_date="20260508",
        ts_code="000001.SZ",
        sample_source="replay_backtest",
    ).one()
    features = json.loads(sample.feature_json)
    assert result == {"created_count": 1, "updated_count": 0, "skipped_count": 0, "deleted_count": 0}
    assert sample.strategy_name == "default"
    assert sample.strategy_version == "default_auction_v2"
    assert sample.replay_source == "stock_auction_open"
    assert sample.auction_source == "stock_auction_open"
    assert sample.auction_ratio_unit == "percent"
    assert sample.auction_turnover_rate_basis == "free_float"
    assert features["auction_ratio"] == 8.19
    assert features["auction_turnover_rate"] == 0.8
    assert features["auction_volume"] == 100000
    assert features["auction_amount"] == 1040000
    assert features["open_change_pct"] == 4.0
    assert features["limit_up_count"] == 5
    assert features["seal_rate"] == 88
    assert features["rise_10d_pct"] == 12
    assert features["circ_mv"] == 120
    assert features["pre_change_pct"] == 9.8
    assert sample.label_t0_limit_success == 1
    assert sample.label_t1_premium_success == 1
    assert sample.label_t1_continue_limit == 1
    assert sample.is_t0_one_line_limit_up == 0
    assert sample.is_t1_one_line_limit_up == 0
    assert sample.t1_open_return > 3


def test_build_samples_from_replay_range_loads_daily_cache_when_daily_rows_not_supplied(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000010.SZ").delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000010.SZ",
            price=10.4,
            vol=100000,
            amount=1040000,
            pre_close=10.0,
            auction_ratio=8.19,
            auction_turnover_rate=0.8,
            source="stock_auction_open",
        )
    )
    db.add(
        StockFeatureSnapshot(
            trade_date="20260508",
            ts_code="000010.SZ",
            limit_up_count_100d=5,
            seal_rate_100d=88,
            rise_10d_pct=12,
            circ_mv=120,
            pre_change_pct=9.8,
        )
    )
    db.add_all(
        [
            StockDailyData(
                trade_date="20260508",
                ts_code="000010.SZ",
                open=10.4,
                high=11.0,
                low=10.2,
                close=11.0,
                pre_close=10.0,
                up_limit=11.0,
                is_adj=0,
            ),
            StockDailyData(
                trade_date="20260511",
                ts_code="000010.SZ",
                open=11.4,
                high=12.1,
                low=11.2,
                close=12.1,
                pre_close=11.0,
                up_limit=12.1,
                is_adj=0,
            ),
        ]
    )
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000010.SZ").one()
    assert sample.label_t0_limit_success == 1
    assert sample.label_t1_premium_success == 1
    assert sample.label_t1_continue_limit == 1
    assert sample.t0_high_return == 10.0
    assert sample.t1_open_return > 3


def test_build_samples_from_replay_range_calculates_seal_features_from_daily_cache(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000020.SZ").delete()
    db.query(SealRateCache).filter(SealRateCache.ts_code == "000020.SZ").delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000020.SZ",
            price=10.4,
            pre_close=10.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    _add_default_replay_daily_rows(db, "000020.SZ", "20260508")
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000020.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["limit_up_count"] == 3
    assert features["touch_days"] == 3
    assert features["limit_up_days"] == 3
    assert features["seal_rate"] == 100.0
    assert features["rise_10d_pct"] == 0.0


def test_build_samples_from_replay_range_calculates_pre_change_from_previous_daily_close(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000021.SZ").delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000021.SZ",
            price=12.6,
            pre_close=12.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    closes = [8.0, 8.8, 9.68, 9.8, 10.78, 11.86, 11.9, 13.09, 13.2, 10.0, 12.0]
    dates = [
        "20260421",
        "20260422",
        "20260423",
        "20260424",
        "20260427",
        "20260428",
        "20260429",
        "20260430",
        "20260505",
        "20260506",
        "20260507",
    ]
    prev_close = 7.27
    for trade_date, close in zip(dates, closes):
        up_limit = get_limit_price("000021", prev_close)
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code="000021.SZ",
                open=close,
                high=up_limit if close >= up_limit - 0.01 else close,
                low=min(prev_close, close),
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
                is_adj=0,
            )
        )
        prev_close = close
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000021.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["pre_change_pct"] == 20.0


def test_build_samples_from_replay_range_does_not_use_trade_day_close_for_replay_filters(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000022.SZ").delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000022.SZ",
            price=12.6,
            pre_close=12.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    closes = [8.0, 8.8, 9.68, 9.8, 10.78, 11.86, 11.9, 13.09, 13.2, 10.0, 12.0]
    dates = [
        "20260421",
        "20260422",
        "20260423",
        "20260424",
        "20260427",
        "20260428",
        "20260429",
        "20260430",
        "20260505",
        "20260506",
        "20260507",
    ]
    prev_close = 7.27
    for trade_date, close in zip(dates, closes):
        up_limit = get_limit_price("000022", prev_close)
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code="000022.SZ",
                open=close,
                high=up_limit if close >= up_limit - 0.01 else close,
                low=min(prev_close, close),
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
                is_adj=0,
            )
        )
        prev_close = close
    db.add(
        StockDailyData(
            trade_date="20260508",
            ts_code="000022.SZ",
            open=6.0,
            high=6.1,
            low=5.5,
            close=6.0,
            pre_close=12.0,
            up_limit=get_limit_price("000022", 12.0),
            is_adj=0,
        )
    )
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000022.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["rise_10d_pct"] == 50.0


def test_build_samples_from_replay_range_deletes_stale_replay_samples(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code.in_(["000023.SZ", "000024.SZ"])).delete()
    db.commit()
    db.add(
        DefaultAuctionTrainingSample(
            strategy_version="default_auction_v2",
            trade_date="20260508",
            ts_code="000024.SZ",
            sample_source="replay_backtest",
            strategy_name="default",
            feature_json="{}",
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000023.SZ",
            price=12.6,
            pre_close=12.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    closes = [8.0, 8.8, 9.68, 9.8, 10.78, 11.86, 11.9, 13.09, 13.2, 10.0, 12.0]
    dates = [
        "20260421",
        "20260422",
        "20260423",
        "20260424",
        "20260427",
        "20260428",
        "20260429",
        "20260430",
        "20260505",
        "20260506",
        "20260507",
    ]
    prev_close = 7.27
    for trade_date, close in zip(dates, closes):
        up_limit = get_limit_price("000023", prev_close)
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code="000023.SZ",
                open=close,
                high=up_limit if close >= up_limit - 0.01 else close,
                low=min(prev_close, close),
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
                is_adj=0,
            )
        )
        prev_close = close
    db.commit()

    result = build_samples_from_replay_range(db, "20260508", "20260508")

    assert result["deleted_count"] == 1
    assert db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000023.SZ").count() == 1
    assert db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000024.SZ").count() == 0


def test_build_samples_from_replay_range_skips_code_already_backed_by_real_selection(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000026.SZ").delete()
    db.commit()
    db.add(
        DefaultAuctionTrainingSample(
            strategy_version="default_auction_v2",
            trade_date="20260508",
            ts_code="000026.SZ",
            sample_source="real_selected",
            strategy_name="default",
            feature_json=json.dumps({"auction_ratio": 9.0}, ensure_ascii=False),
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000026.SZ",
            price=12.6,
            pre_close=12.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    _add_default_replay_daily_rows(db, "000026.SZ", "20260508")
    db.commit()

    result = build_samples_from_replay_range(db, "20260508", "20260508")

    rows = db.query(DefaultAuctionTrainingSample).filter_by(
        trade_date="20260508",
        ts_code="000026.SZ",
    ).all()
    assert result["created_count"] == 0
    assert result["skipped_count"] == 1
    assert [(row.sample_source, json.loads(row.feature_json)["auction_ratio"]) for row in rows] == [
        ("real_selected", 9.0)
    ]


def test_build_samples_from_selected_record_removes_shadowed_replay_sample(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9011, trade_date="20260508", status="success", total_count=1))
    db.add(
        SelectedStock(
            record_id=9011,
            ts_code="000027.SZ",
            name="真实样本",
            auction_ratio=9.5,
            auction_turnover_rate=1.2,
            open_change_pct=4.8,
        )
    )
    db.add(
        DefaultAuctionTrainingSample(
            strategy_version="default_auction_v2",
            trade_date="20260508",
            ts_code="000027.SZ",
            sample_source="replay_backtest",
            strategy_name="default",
            feature_json=json.dumps({"auction_ratio": 7.0}, ensure_ascii=False),
        )
    )
    db.commit()

    result = build_samples_from_selected_record(db, 9011, sample_source="real_selected")

    rows = db.query(DefaultAuctionTrainingSample).filter_by(
        trade_date="20260508",
        ts_code="000027.SZ",
    ).all()
    assert result["created_count"] == 1
    assert result["deleted_count"] == 1
    assert [(row.sample_source, json.loads(row.feature_json)["auction_ratio"]) for row in rows] == [
        ("real_selected", 9.5)
    ]


def test_build_samples_from_replay_range_combines_snapshot_and_daily_metrics(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.ts_code == "000025.SZ").delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000025.SZ",
            price=12.6,
            pre_close=12.0,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    db.add(
        StockFeatureSnapshot(
            trade_date="20260508",
            ts_code="000025.SZ",
            limit_up_count_100d=4,
            seal_rate_100d=82,
            rise_10d_pct=18,
            circ_mv=88.0,
        )
    )
    closes = [8.0, 8.8, 9.68, 9.8, 10.78, 11.86, 11.9, 13.09, 13.2, 10.0, 12.0]
    dates = [
        "20260421",
        "20260422",
        "20260423",
        "20260424",
        "20260427",
        "20260428",
        "20260429",
        "20260430",
        "20260505",
        "20260506",
        "20260507",
    ]
    prev_close = 7.27
    for trade_date, close in zip(dates, closes):
        up_limit = get_limit_price("000025", prev_close)
        db.add(
            StockDailyData(
                trade_date=trade_date,
                ts_code="000025.SZ",
                open=close,
                high=up_limit if close >= up_limit - 0.01 else close,
                low=min(prev_close, close),
                close=close,
                pre_close=prev_close,
                up_limit=up_limit,
                is_adj=0,
            )
        )
        prev_close = close
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000025.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["circ_mv"] == 88.0
    assert features["limit_up_count"] == 5
    assert features["seal_rate"] is not None
    assert features["rise_10d_pct"] is not None


def test_build_samples_from_replay_range_writes_previous_market_context(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.query(StockDailyData).filter(StockDailyData.trade_date.in_(["20260507", "20260508"])).delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000001.SZ",
            price=10.4,
            pre_close=10.0,
            auction_ratio=8.19,
            auction_turnover_rate=0.8,
            source="stock_auction_open",
        )
    )
    db.add(
        StockFeatureSnapshot(
            trade_date="20260508",
            ts_code="000001.SZ",
            limit_up_count_100d=5,
            seal_rate_100d=88,
            rise_10d_pct=12,
            circ_mv=120,
        )
    )
    db.add_all(
        [
            StockDailyData(
                trade_date="20260507",
                ts_code="000001.SZ",
                high=11.0,
                close=11.0,
                pre_close=10.0,
                up_limit=11.0,
                down_limit=9.0,
            ),
            StockDailyData(
                trade_date="20260507",
                ts_code="000002.SZ",
                high=11.0,
                close=10.2,
                pre_close=10.0,
                up_limit=11.0,
                down_limit=9.0,
            ),
            StockDailyData(
                trade_date="20260507",
                ts_code="000003.SZ",
                high=10.0,
                close=9.0,
                pre_close=10.0,
                up_limit=11.0,
                down_limit=9.0,
            ),
        ]
    )
    db.commit()

    build_samples_from_replay_range(db, "20260508", "20260508")

    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000001.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["market_limit_up_count"] == 1
    assert features["market_limit_down_count"] == 1
    assert features["market_zhaban_rate"] == 50.0
    assert features["market_max_connected_board"] == 1
    assert features["market_emotion_score"] == -5.0


def test_build_samples_from_replay_range_skips_replay_when_daily_structure_is_missing(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(StockAuctionOpen).delete()
    db.query(StockFeatureSnapshot).delete()
    db.commit()
    db.add(
        StockAuctionOpen(
            trade_date="20260508",
            ts_code="000002.SZ",
            pre_close=10,
            auction_ratio=8,
            auction_turnover_rate=1,
            source="stock_auction_open",
        )
    )
    db.commit()

    result = build_samples_from_replay_range(db, "20260508", "20260508", daily_rows={})

    assert result == {"created_count": 0, "updated_count": 0, "skipped_count": 0, "deleted_count": 0}
    assert db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000002.SZ").count() == 0


def test_default_auction_label_builders_handle_basic_judgements():
    assert build_t0_limit_label({"high": 10.02, "close": 10.0}, limit_price=10.0) == 1
    assert build_t0_limit_label({"high": 10.02, "close": 9.7}, limit_price=10.0) == 0
    assert build_t0_limit_label({"high": 9.98, "close": 9.98}, limit_price=10.0) == 0

    assert build_t1_premium_label({"open_return": 3.1, "high_return": 1, "close_return": 0}) == 1
    assert build_t1_premium_label({"open": 10.2, "high": 10.6, "close": 10.1, "pre_close": 10}) == 1
    assert build_t1_premium_label({"open_return": 1, "high_return": 4.9, "close_return": 2.9}) == 0

    assert build_t1_continue_label({"high": 11.0, "close": 11.0}, limit_price=11.0) == 1
    assert build_t1_continue_label({"high": 10.98, "close": 11.0}, limit_price=11.0) == 0
    assert build_t1_continue_label({"high": 11.0, "close": 10.5}, limit_price=11.0) == 0


def test_default_auction_limit_labels_return_none_for_unknown_inputs():
    assert build_t0_limit_label({"close": 10.0}, limit_price=10.0) is None
    assert build_t0_limit_label({"high": 10.0}, limit_price=10.0) is None
    assert build_t0_limit_label({"high": 10.0, "close": 10.0}, limit_price=None) is None
    assert build_t1_premium_label(None) is None
    assert build_t1_premium_label({"open": 10.2, "high": 10.6, "close": 10.1}) is None
    assert build_t1_premium_label({"open_return": None, "high_return": None, "close_return": None}) is None
    assert build_t1_continue_label({"close": 10.0}, limit_price=10.0) is None
    assert build_t1_continue_label({"high": 10.0}, limit_price=10.0) is None
    assert build_t1_continue_label({"high": 10.0, "close": 10.0}, limit_price=None) is None


def test_default_auction_limit_audit_builders_return_label_and_state_fields():
    t0 = build_t0_limit_audit({"open": 10.0, "high": 10.0, "low": 9.6, "close": 9.98}, 10.0)
    assert t0 == {
        "label_t0_limit_success": 1,
        "is_t0_limit_up": 1,
        "is_t0_one_line_limit_up": 0,
    }

    t1 = build_t1_continue_audit({"open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0}, 11.0)
    assert t1 == {
        "label_t1_continue_limit": 1,
        "is_t1_limit_up": 1,
        "is_t1_one_line_limit_up": 1,
    }

    assert build_t0_limit_audit({"close": 10.0}, 10.0)["label_t0_limit_success"] is None
    assert build_t1_continue_audit({"close": 11.0}, 11.0)["label_t1_continue_limit"] is None


def test_runtime_migration_adds_missing_default_auction_training_sample_columns(tmp_path):
    db_path = tmp_path / "default_auction.db"
    migration_engine = create_engine(f"sqlite:///{db_path}")
    with migration_engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE default_auction_training_sample (
                id INTEGER PRIMARY KEY,
                trade_date VARCHAR(10),
                ts_code VARCHAR(20),
                strategy_version VARCHAR(50),
                sample_source VARCHAR(30),
                feature_json TEXT
            )
        """)

    ensure_runtime_columns(migration_engine)
    ensure_runtime_columns(migration_engine)

    columns = {
        column["name"]
        for column in inspect(migration_engine).get_columns("default_auction_training_sample")
    }
    assert {
        "t0_high_return",
        "t0_close_return",
        "t1_open_return",
        "t1_high_return",
        "t1_close_return",
        "is_t0_limit_up",
        "is_t0_one_line_limit_up",
        "is_t1_limit_up",
        "is_t1_one_line_limit_up",
    }.issubset(columns)
