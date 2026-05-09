from pathlib import Path

from backend.database import Base, engine
from backend.models.auction_backtest import LeaderMainT0TrainingSample


def test_sync_auction_open_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeAuctionDataService:
        def sync_auction_open(self, trade_date):
            assert trade_date == "20240510"
            return 321

    monkeypatch.setattr(backtest_api, "AuctionDataService", FakeAuctionDataService)

    resp = client.post("/api/v1/backtest/auction/sync", json={"trade_date": "20240510"})

    assert resp.status_code == 200
    assert resp.json()["data"] == {"trade_date": "20240510", "synced_count": 321}


def test_sync_auction_open_range_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeAuctionDataService:
        def sync_auction_open_date_range(self, start_date, end_date):
            assert (start_date, end_date) == ("20240510", "20240512")
            return {"trade_dates": ["20240510", "20240511"], "synced_count": 456}

    monkeypatch.setattr(backtest_api, "AuctionDataService", FakeAuctionDataService)

    resp = client.post(
        "/api/v1/backtest/auction/sync-range",
        json={"start_date": "20240510", "end_date": "20240512"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["trade_dates"] == ["20240510", "20240511"]
    assert resp.json()["data"]["synced_count"] == 456


def test_sync_tdx_local_daily_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeSyncService:
        def sync_range(self, start_date, end_date, ts_codes=None):
            assert (start_date, end_date) == ("20260507", "20260508")
            assert ts_codes == ["000001.SZ", "000002.SZ"]
            return {
                "start_date": start_date,
                "end_date": end_date,
                "stocks_scanned": 2,
                "stocks_with_rows": 2,
                "rows_synced": 4,
            }

    monkeypatch.setattr(backtest_api, "TdxLocalDailySyncService", lambda: FakeSyncService())

    resp = client.post(
        "/api/v1/backtest/tdx-local-daily/sync",
        json={"start_date": "20260507", "end_date": "20260508", "ts_codes": ["000001.SZ", "000002.SZ"]},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["rows_synced"] == 4
    assert resp.json()["data"]["stocks_scanned"] == 2


def test_recalculate_auction_ratios_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeAuctionDataService:
        def recalculate_auction_ratios_from_daily_cache(self, start_date, end_date):
            assert (start_date, end_date) == ("20260507", "20260508")
            return {
                "start_date": start_date,
                "end_date": end_date,
                "trade_dates": ["20260507", "20260508"],
                "updated_count": 100,
                "missing_count": 3,
            }

    monkeypatch.setattr(backtest_api, "AuctionDataService", FakeAuctionDataService)

    resp = client.post(
        "/api/v1/backtest/auction/recalculate-ratios",
        json={"start_date": "20260507", "end_date": "20260508"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 100
    assert resp.json()["data"]["missing_count"] == 3


def test_build_leader_main_t0_samples_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeBuilder:
        def build_leader_main_t0_range(self, trade_dates):
            assert trade_dates == ["20240510", "20240511"]
            return 12

    monkeypatch.setattr(backtest_api, "LeaderMainT0FeatureBuilder", FakeBuilder)

    resp = client.post(
        "/api/v1/backtest/leader-main-t0/build",
        json={"trade_dates": ["20240510", "20240511"]},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["saved_count"] == 12


def test_build_leader_main_t0_labels_endpoint(client, monkeypatch):
    from backend.api import backtest as backtest_api

    class FakeLabelBuilder:
        def build_leader_main_t0_labels(self, start_date, end_date):
            assert (start_date, end_date) == ("20240501", "20240510")
            return 9

    monkeypatch.setattr(backtest_api, "LeaderMainT0LabelBuilder", FakeLabelBuilder)

    resp = client.post(
        "/api/v1/backtest/leader-main-t0/labels",
        json={"start_date": "20240501", "end_date": "20240510"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 9


def test_train_leader_main_t0_endpoint(client, monkeypatch, tmp_path):
    from backend.api import backtest as backtest_api

    model_path = tmp_path / "leader_main_t0_lgbm.pkl"
    model_path.write_text("fake")

    def fake_train(start_date, end_date):
        assert (start_date, end_date) == ("20240101", "20240510")
        return str(model_path)

    monkeypatch.setattr(backtest_api, "train_leader_main_t0_lgbm", fake_train)

    resp = client.post(
        "/api/v1/backtest/leader-main-t0/train",
        json={"start_date": "20240101", "end_date": "20240510"},
    )

    assert resp.status_code == 200
    assert Path(resp.json()["data"]["model_path"]).name == "leader_main_t0_lgbm.pkl"


def test_run_leader_main_t0_pipeline_endpoint(client, monkeypatch, tmp_path):
    from backend.api import backtest as backtest_api

    model_path = tmp_path / "leader_main_t0_lgbm.pkl"
    model_path.write_text("fake")

    class FakeAuctionDataService:
        def sync_auction_open_date_range(self, start_date, end_date):
            assert (start_date, end_date) == ("20240501", "20240510")
            return {"trade_dates": ["20240508", "20240509", "20240510"], "synced_count": 300}

    class FakeBuilder:
        def build_leader_main_t0_range(self, trade_dates):
            assert trade_dates == ["20240508", "20240509", "20240510"]
            return 21

    class FakeLabelBuilder:
        def build_leader_main_t0_labels(self, start_date, end_date):
            assert (start_date, end_date) == ("20240501", "20240510")
            return 18

    def fake_train(start_date, end_date):
        assert (start_date, end_date) == ("20240501", "20240510")
        return str(model_path)

    monkeypatch.setattr(backtest_api, "AuctionDataService", FakeAuctionDataService)
    monkeypatch.setattr(backtest_api, "LeaderMainT0FeatureBuilder", FakeBuilder)
    monkeypatch.setattr(backtest_api, "LeaderMainT0LabelBuilder", FakeLabelBuilder)
    monkeypatch.setattr(backtest_api, "train_leader_main_t0_lgbm", fake_train)

    resp = client.post(
        "/api/v1/backtest/leader-main-t0/run",
        json={"start_date": "20240501", "end_date": "20240510", "train_model": True},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["synced_count"] == 300
    assert data["saved_count"] == 21
    assert data["updated_count"] == 18
    assert Path(data["model_path"]).name == "leader_main_t0_lgbm.pkl"


def test_list_leader_main_t0_samples_endpoint(client, db):
    Base.metadata.create_all(bind=engine)
    db.add(
        LeaderMainT0TrainingSample(
            trade_date="20991231",
            ts_code="999001.SZ",
            name="平安银行",
            auction_ratio=8.19,
            auction_turnover_rate=0.83,
            rule_score=88,
            label_t0_limit_success=1,
            t0_high_return=10.01,
            feature_json='{"filter_status": "included"}',
        )
    )
    db.commit()

    resp = client.get(
        "/api/v1/backtest/leader-main-t0/samples",
        params={"start_date": "20991231", "end_date": "20991231", "page": 1, "page_size": 20},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["samples"][0]["ts_code"] == "999001.SZ"
    assert data["samples"][0]["label_t0_limit_success"] == 1
    assert data["samples"][0]["feature"]["filter_status"] == "included"
