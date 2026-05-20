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


def test_removed_leader_main_t0_endpoints_return_not_found(client):
    resp = client.post(
        "/api/v1/backtest/leader-main-t0/train",
        json={"start_date": "20240101", "end_date": "20240510"},
    )

    assert resp.status_code == 404
