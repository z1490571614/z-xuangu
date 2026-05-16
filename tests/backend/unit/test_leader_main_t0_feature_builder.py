import json

import pandas as pd

from backend.database import Base, engine
from backend.models import StockFeatureSnapshot
from backend.models.auction_backtest import LeaderMainT0TrainingSample, StockAuctionOpen
from backend.services.backtest.leader_main_t0_feature_builder import (
    LeaderMainT0FeatureBuilder,
    filter_leader_main_t0_candidates,
)


def _valid_feature(**overrides):
    data = {
        "trade_date": "20240510",
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "is_st": False,
        "is_suspended": False,
        "is_bj": False,
        "circ_mv": 120,
        "prev_close": 10,
        "rise_10d_pct": 12,
        "limit_up_count_100d": 4,
        "seal_rate_100d": 88,
        "limit_up_streak": 2,
        "market_height_rank": 5,
        "yesterday_turnover_rate": 4,
        "prev_day_volume_ge_prev2": True,
        "ma5_gt_ma10": True,
        "sector_change_pct": 2.5,
        "sector_limit_up_count": 4,
        "auction_ratio": 8.19,
        "auction_turnover_rate": 0.83,
        "open_change_pct": 5.1,
        "pre_change_pct": 9.98,
    }
    data.update(overrides)
    return data


def test_filter_leader_main_t0_candidates_keeps_valid_candidate_and_reasons_rejections():
    valid = _valid_feature()
    weak_auction = _valid_feature(ts_code="000002.SZ", auction_ratio=2)

    result = filter_leader_main_t0_candidates([valid, weak_auction])

    assert [item["ts_code"] for item in result["candidates"]] == ["000001.SZ"]
    assert result["candidates"][0]["filter_status"] == "included"
    assert result["rejected"][0]["ts_code"] == "000002.SZ"
    assert "竞昨比不在4%-30%" in result["rejected"][0]["filter_reasons"]


def test_filter_leader_main_t0_candidates_uses_production_selection_conditions_not_extra_leader_filters():
    production_valid = _valid_feature(
        ts_code="600707.SH",
        limit_up_streak=1,
        market_height_rank=67,
        yesterday_turnover_rate=1.2,
        prev_day_volume_ge_prev2=False,
        ma5_gt_ma10=False,
        sector_change_pct=0,
        sector_limit_up_count=0,
        seal_rate_100d=100,
        open_change_pct=0.51,
    )

    result = filter_leader_main_t0_candidates([production_valid])

    assert [item["ts_code"] for item in result["candidates"]] == ["600707.SH"]


def test_filter_leader_main_t0_candidates_rejects_like_production_post_filters():
    low_seal = _valid_feature(ts_code="600130.SH", seal_rate_100d=66.67)
    weak_open = _valid_feature(ts_code="002081.SZ", seal_rate_100d=91.67, open_change_pct=-3.5)

    result = filter_leader_main_t0_candidates([low_seal, weak_open])

    reasons = {item["ts_code"]: item["filter_reasons"] for item in result["rejected"]}
    assert "封板率低于80%" in reasons["600130.SH"]
    assert "开盘跌幅低于-3%" in reasons["002081.SZ"]


def test_save_training_samples_upserts_feature_json_without_duplicates(db):
    Base.metadata.create_all(bind=engine)
    builder = LeaderMainT0FeatureBuilder(session_factory=lambda: db)
    feature = _valid_feature(rule_score=88, auction_ratio=0.0819)

    assert builder.save_training_samples("20240510", [feature]) == 1
    assert builder.save_training_samples("20240510", [feature]) == 1

    rows = db.query(LeaderMainT0TrainingSample).filter_by(
        trade_date="20240510",
        ts_code="000001.SZ",
    ).all()
    assert len(rows) == 1
    assert rows[0].strategy_version == "leader_main_t0"
    assert rows[0].rule_score == 88
    assert json.loads(rows[0].feature_json)["auction_ratio"] == 8.19


def test_save_training_samples_removes_stale_rows_when_source_is_feature_snapshot(db):
    Base.metadata.create_all(bind=engine)
    db.add(
        LeaderMainT0TrainingSample(
            strategy_version="leader_main_t0",
            trade_date="20240510",
            ts_code="000999.SZ",
        )
    )
    db.commit()

    feature = _valid_feature(ts_code="000001.SZ", source="stock_feature_snapshot")

    builder = LeaderMainT0FeatureBuilder(session_factory=lambda: db)
    assert builder.save_training_samples("20240510", [feature]) == 1

    rows = db.query(LeaderMainT0TrainingSample).filter_by(trade_date="20240510").all()
    assert [row.ts_code for row in rows] == ["000001.SZ"]


def test_build_features_for_date_prefers_production_feature_snapshot(db):
    Base.metadata.create_all(bind=engine)
    db.add(
        StockFeatureSnapshot(
            trade_date="20991224",
            ts_code="000889.SZ",
            name="中嘉博创",
            limit_up_count_100d=11,
            seal_rate_100d=84.62,
            rise_10d_pct=16.09,
            pre_change_pct=1.2,
            open_change_pct=5.79,
            auction_ratio=0.2487,
            auction_turnover_rate=1.89,
            circ_mv=47.05,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20991224",
            ts_code="002929.SZ",
            auction_ratio=0.5143,
            auction_turnover_rate=2.38,
        )
    )
    db.commit()

    builder = LeaderMainT0FeatureBuilder(session_factory=lambda: db)
    features = builder.build_leader_main_t0_features_for_date("20991224")

    assert [feature["ts_code"] for feature in features] == ["000889.SZ"]
    assert features[0]["auction_ratio"] == 24.87
    assert features[0]["auction_turnover_rate"] == 1.89
    assert features[0]["source"] == "stock_feature_snapshot"


def test_fetch_daily_history_requests_each_trade_date_to_avoid_tushare_row_cap():
    calls = []

    class FakeCollector:
        def get_daily_data(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": kwargs["trade_date"],
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "pre_close": 9.5,
                        "pct_chg": 5,
                        "vol": 100,
                        "amount": 1000,
                    }
                ]
            )

    builder = LeaderMainT0FeatureBuilder(collector=FakeCollector())
    df = builder._fetch_daily_history(["20240508", "20240509"])

    assert [call["trade_date"] for call in calls] == ["20240508", "20240509"]
    assert len(df) == 2


def test_fetch_daily_history_reuses_cached_trade_dates():
    calls = []

    class FakeCollector:
        def get_daily_data(self, **kwargs):
            calls.append(kwargs["trade_date"])
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": kwargs["trade_date"],
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "pre_close": 9.5,
                        "pct_chg": 5,
                        "vol": 100,
                        "amount": 1000,
                    }
                ]
            )

    builder = LeaderMainT0FeatureBuilder(collector=FakeCollector())

    first = builder._fetch_daily_history(["20240508", "20240509"])
    second = builder._fetch_daily_history(["20240509", "20240510"])

    assert calls == ["20240508", "20240509", "20240510"]
    assert len(first) == 2
    assert len(second) == 2


def test_get_history_days_unions_current_and_previous_year_calendar():
    class FakeCollector:
        def get_trading_calendar(self, year=None):
            if year == 2025:
                return {"20251230", "20251231"}
            if year == 2026:
                return {"20260102", "20260105", "20260106"}
            return set()

    builder = LeaderMainT0FeatureBuilder(collector=FakeCollector())

    assert builder._get_history_days("20260106", 4) == [
        "20251230",
        "20251231",
        "20260102",
        "20260105",
    ]
