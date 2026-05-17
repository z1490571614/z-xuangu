import json

from sqlalchemy import create_engine, inspect

from backend.database import Base, engine
from backend.database.schema_migrations import ensure_runtime_columns
from backend.models import DefaultAuctionTrainingSample, SelectionRecord, SelectedStock
from backend.services.model_engine.default_auction_label_builder import (
    build_t0_limit_audit,
    build_t0_limit_label,
    build_t1_continue_audit,
    build_t1_continue_label,
    build_t1_premium_label,
)
from backend.services.model_engine.default_auction_sample_builder import (
    build_samples_from_selected_record,
)


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
    assert "risk_tags" not in features
    assert "has_negative_news" not in features
    assert "announcement_alpha_score" not in features
    assert "reasons" not in features
    assert "next_day_plan" not in features


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
