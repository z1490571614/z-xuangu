from backend.database import Base, engine
from backend.models import SelectedStock, SelectionRecord, StockAuctionOpen


def test_selection_detail_returns_t0_model_fields(client, db):
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
            t0_limit_success_prob=72.5,
            t0_limit_success_model_version="v1",
        )
    )
    db.commit()

    resp = client.get(f"/api/v1/stock/results/{record.id}")

    assert resp.status_code == 200
    stock = resp.json()["data"]["stocks"][0]
    assert stock["t0_limit_success_prob"] == 72.5
    assert stock["t0_limit_success_model_version"] == "v1"
    disclaimer = resp.json()["data"]["t0_model_disclaimer"]
    assert "仅作排序参考" in disclaimer
    assert "不构成投资建议" in disclaimer


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
