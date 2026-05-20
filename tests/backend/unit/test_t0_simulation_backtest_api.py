import subprocess
import sys

from backend.database import Base, engine
from backend.models import T0SimulationBacktestDaily, T0SimulationBacktestRun, T0SimulationBacktestTrade
from backend.models.seal_rate import StockDailyData


def _reset_api_data(db):
    Base.metadata.create_all(bind=engine)
    db.query(T0SimulationBacktestTrade).delete()
    db.query(T0SimulationBacktestDaily).delete()
    db.query(T0SimulationBacktestRun).delete()
    db.query(StockDailyData).delete()
    db.commit()


def test_t0_simulation_backtest_request_import_has_no_pydantic_model_namespace_warning():
    result = subprocess.run(
        [sys.executable, "-W", "error::UserWarning", "-c", "import backend.main"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "protected namespace" not in result.stderr


def test_t0_simulation_backtest_api_creates_lists_and_gets_detail(client, monkeypatch, db):
    from backend.api import backtest

    _reset_api_data(db)
    executed = []

    def fake_run(run_db, run_id):
        executed.append(run_id)
        return {"id": run_id}

    monkeypatch.setattr(backtest, "run_t0_simulation_backtest", fake_run)

    resp = client.post(
        "/api/v1/backtest/t0-simulation/runs",
        json={
            "start_date": "20240501",
            "end_date": "20240510",
            "initial_cash": 100000,
            "buy_top_n": 2,
            "max_positions": 4,
            "min_buy_prob_pct": 55,
            "min_open_change_pct": -3,
            "max_open_change_pct": 8,
            "take_profit_pct": 8,
            "high_profit_hold_pct": 15,
            "profit_pullback_pct": 6,
            "stop_loss_pct": -5,
            "max_holding_days": 3,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["run_id"] in executed

    listing = client.get("/api/v1/backtest/t0-simulation/runs?limit=5")
    assert listing.status_code == 200
    assert any(item["id"] == data["run_id"] for item in listing.json()["data"])

    detail = client.get(f"/api/v1/backtest/t0-simulation/runs/{data['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == data["run_id"]
    assert detail.json()["data"]["initial_cash"] == 100000
    assert detail.json()["data"]["sample_source"] == "replay_backtest"
    assert detail.json()["data"]["min_buy_prob_pct"] == 55
    assert detail.json()["data"]["min_open_change_pct"] == -3
    assert detail.json()["data"]["max_open_change_pct"] == 8
    assert detail.json()["data"]["high_profit_hold_pct"] == 15
    assert detail.json()["data"]["profit_pullback_pct"] == 6
    assert detail.json()["data"]["progress"] == 0.0
    assert detail.json()["data"]["processed_trade_days"] == 0
    assert detail.json()["data"]["total_trade_days"] == 0
    assert detail.json()["data"]["processed_trade_date"] is None
    assert detail.json()["data"]["daily"] == []
    assert detail.json()["data"]["trades"] == []


def test_t0_simulation_backtest_api_rejects_invalid_params(client):
    resp = client.post(
        "/api/v1/backtest/t0-simulation/runs",
        json={
            "start_date": "20240510",
            "end_date": "20240501",
            "initial_cash": 100000,
        },
    )

    assert resp.status_code == 422


def test_t0_simulation_backtest_api_requests_cancel_for_running_run(client, db):
    _reset_api_data(db)
    run = T0SimulationBacktestRun(
        status="running",
        start_date="20240501",
        end_date="20240510",
        model_name="default_auction_t0_limit_lgbm",
        sample_source="real_selected",
        initial_cash=100000,
        buy_top_n=2,
        max_positions=4,
        take_profit_pct=8,
        stop_loss_pct=-5,
        max_holding_days=3,
        cost_json="{}",
        summary_json="{}",
    )
    db.add(run)
    db.commit()

    resp = client.post(f"/api/v1/backtest/t0-simulation/runs/{run.id}/cancel")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancel_requested"
