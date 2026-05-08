import pandas as pd

from backend.database import Base, engine
from backend.models.auction_backtest import LeaderMainT0TrainingSample
from backend.services.backtest.leader_main_t0_label_builder import LeaderMainT0LabelBuilder


def test_label_builder_updates_labels_without_touching_features(db):
    Base.metadata.create_all(bind=engine)
    db.add(
        LeaderMainT0TrainingSample(
            trade_date="20240511",
            ts_code="000003.SZ",
            name="平安银行",
            auction_ratio=8.19,
            label_t0_limit_success=None,
        )
    )
    db.commit()

    class FakeCollector:
        def get_daily_data(self, trade_date=None, **kwargs):
            assert trade_date == "20240511"
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000003.SZ",
                        "trade_date": trade_date,
                        "open": 9.45,
                        "high": 10.0,
                        "low": 9.4,
                        "close": 9.98,
                        "pre_close": 9.09,
                    }
                ]
            )

    builder = LeaderMainT0LabelBuilder(collector=FakeCollector(), session_factory=lambda: db)

    assert builder.build_leader_main_t0_labels("20240511", "20240511") == 1

    row = db.query(LeaderMainT0TrainingSample).filter_by(
        trade_date="20240511",
        ts_code="000003.SZ",
    ).one()
    assert row.auction_ratio == 8.19
    assert row.label_t0_limit_success == 1
    assert row.t0_touched_limit == 1
    assert row.t0_closed_limit == 1
    assert row.is_one_line_limit_up == 0
