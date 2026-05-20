from backend.services.data_collector import TushareDataCollector


def test_get_realtime_quotes_splits_large_batches(monkeypatch):
    requested_batches = []

    class FakeResponse:
        def __init__(self, codes):
            self.codes = codes

        def raise_for_status(self):
            return None

        def json(self):
            if len(self.codes) > 60:
                return {
                    "code": -1,
                    "message": f"获取行情失败: 预期{len(self.codes)}个，实际80个",
                    "data": None,
                }
            return {
                "code": 0,
                "message": "success",
                "data": [
                    {
                        "Code": code,
                        "K": {
                            "Open": 10800,
                            "Last": 10000,
                            "Close": 10900,
                            "High": 11000,
                            "Low": 9900,
                        },
                        "TotalHand": 123,
                        "Amount": 456000,
                        "ServerTime": "092500",
                    }
                    for code in self.codes
                ],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params):
            codes = params["code"].split(",")
            requested_batches.append(codes)
            return FakeResponse(codes)

    monkeypatch.setenv("REALTIME_QUOTE_BATCH_SIZE", "60")
    monkeypatch.setattr("backend.services.data_collector.httpx.Client", FakeClient)

    collector = object.__new__(TushareDataCollector)
    ts_codes = [f"{idx:06d}.SZ" for idx in range(1, 126)]

    quotes = collector.get_realtime_quotes(ts_codes)

    assert [len(batch) for batch in requested_batches] == [60, 60, 5]
    assert len(quotes) == 125
    assert quotes["000001.SZ"]["open"] == 10.8
    assert quotes["000001.SZ"]["pre_close"] == 10.0
    assert quotes["000001.SZ"]["volume_hand"] == 123
    assert quotes["000001.SZ"]["volume"] == 12300
    assert quotes["000125.SZ"]["amount"] == 456000
