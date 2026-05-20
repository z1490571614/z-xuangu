from backend.models import SelectedStock, SelectionRecord
from backend.services import stock_selector
from backend.services.stock_selector import StockSelectorService


def test_save_selection_result_triggers_default_auction_relay_refresh(db, monkeypatch):
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()

    calls = []
    monkeypatch.setattr(
        stock_selector,
        "_trigger_default_auction_relay_prediction_refresh",
        lambda record_id: calls.append(record_id),
        raising=False,
    )

    selector = object.__new__(StockSelectorService)
    record_id = selector.save_selection_result(
        {
            "trade_date": "20260508",
            "passed_count": 1,
            "execution_time": 1.2,
            "stocks": [
                {
                    "ts_code": "000001.SZ",
                    "name": "测试股",
                    "open_change_pct": 5.2,
                }
            ],
        }
    )

    saved = db.query(SelectedStock).filter_by(record_id=record_id).one()
    assert saved.ts_code == "000001.SZ"
    assert calls == [record_id]
