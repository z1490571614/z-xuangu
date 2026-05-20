from backend.database import Base, engine
from backend.models import SelectedStock, SelectionRecord, StockAuctionOpen


def test_selection_detail_returns_default_auction_model_fields(client, db):
    Base.metadata.create_all(bind=engine)
    record = SelectionRecord(trade_date="20240512", total_count=1, status="success")
    db.add(record)
    db.flush()
    db.add(
        SelectedStock(
            record_id=record.id,
            ts_code="000004.SZ",
            name="测试股票",
            rule_score=80,
            final_score=80,
            default_t0_limit_prob=61.2,
            default_t1_premium_prob=52.3,
            default_t1_continue_prob=18.4,
            default_relay_score=39.8,
            default_relay_model_version="t0_v1|premium_v1|continue_v1",
        )
    )
    db.commit()

    resp = client.get(f"/api/v1/stock/results/{record.id}")

    assert resp.status_code == 200
    stock = resp.json()["data"]["stocks"][0]
    assert "t0_limit_success_prob" not in stock
    assert "t0_limit_success_model_version" not in stock
    assert stock["default_t0_limit_prob"] == 61.2
    assert stock["default_t1_premium_prob"] == 52.3
    assert stock["default_t1_continue_prob"] == 18.4
    assert stock["default_relay_score"] == 39.8
    assert stock["default_relay_model_version"] == "t0_v1|premium_v1|continue_v1"
    assert "t0_model_disclaimer" not in resp.json()["data"]


def test_selection_detail_does_not_fill_mcp_auction_metrics_from_local_auction_table(client, db):
    Base.metadata.create_all(bind=engine)
    record = SelectionRecord(trade_date="20990101", total_count=1, status="success")
    db.add(record)
    db.flush()
    db.add(
        SelectedStock(
            record_id=record.id,
            ts_code="999001.SZ",
            name="竞价缺失股",
            auction_ratio=None,
            auction_turnover_rate=None,
        )
    )
    db.add(
        StockAuctionOpen(
            trade_date="20990101",
            ts_code="999001.SZ",
            auction_ratio=12.34,
            auction_turnover_rate=1.23,
        )
    )
    db.commit()

    resp = client.get(f"/api/v1/stock/results/{record.id}")

    assert resp.status_code == 200
    stock = resp.json()["data"]["stocks"][0]
    assert stock["auction_ratio"] is None
    assert stock["auction_turnover_rate"] is None
