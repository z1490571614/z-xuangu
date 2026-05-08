from backend.database import Base, engine
from backend.models import SelectedStock, SelectionRecord


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
