import os
import struct

import pandas as pd

from backend.services.data_collector import TushareDataCollector
from backend.services.tdx_local_selector import TdxLocalSelectorService


def _write_day_file(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for row in rows:
            f.write(
                struct.pack(
                    "<IIIIIfII",
                    row["date"],
                    int(row["open"] * 100),
                    int(row["high"] * 100),
                    int(row["low"] * 100),
                    int(row["close"] * 100),
                    float(row.get("amount", 0)),
                    int(row.get("vol", 0)),
                    0,
                )
            )


def test_tdx_local_daily_reads_day_file_as_tushare_shape(tmp_path):
    day_path = tmp_path / "sz" / "lday" / "sz000001.day"
    _write_day_file(
        day_path,
        [
            {"date": 20240509, "open": 9.8, "high": 10.2, "low": 9.7, "close": 10.0, "vol": 1000, "amount": 10000},
            {"date": 20240510, "open": 10.1, "high": 11.0, "low": 10.0, "close": 10.9, "vol": 1200, "amount": 12000},
        ],
    )
    service = TdxLocalSelectorService(tdx_vipdoc_path=str(tmp_path))

    df = service.get_daily_data(ts_code="000001.SZ", trade_date="20240510")

    assert df.to_dict("records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "20240510",
            "open": 10.1,
            "high": 11.0,
            "low": 10.0,
            "close": 10.9,
            "pre_close": 10.0,
            "change": 0.9,
            "pct_chg": 9.0,
            "vol": 1200,
            "amount": 12000.0,
        }
    ]


def test_get_daily_data_prefers_tdx_local_before_tushare(monkeypatch):
    class FakeLocal:
        def get_daily_data(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": kwargs["trade_date"],
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                        "pre_close": 10,
                        "change": 0.5,
                        "pct_chg": 5,
                        "vol": 1000,
                        "amount": 10000,
                    }
                ]
            )

    class FakePro:
        def daily(self, **kwargs):
            raise AssertionError("Tushare daily should not be called when local daily exists")

    collector = TushareDataCollector.__new__(TushareDataCollector)
    collector._last_pro = FakePro()
    collector._tdx_local_daily = FakeLocal()

    df = collector.get_daily_data(trade_date="20240510")

    assert len(df) == 1
    assert df.iloc[0]["ts_code"] == "000001.SZ"


def test_get_daily_data_falls_back_to_tushare_when_local_empty():
    class FakeLocal:
        def get_daily_data(self, **kwargs):
            return pd.DataFrame()

    class FakePro:
        def daily(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000002.SZ",
                        "trade_date": kwargs["trade_date"],
                        "open": 20,
                        "high": 21,
                        "low": 19,
                        "close": 20.5,
                    }
                ]
            )

    collector = TushareDataCollector.__new__(TushareDataCollector)
    collector._last_pro = FakePro()
    collector._tdx_local_daily = FakeLocal()

    df = collector.get_daily_data(trade_date="20240510")

    assert len(df) == 1
    assert df.iloc[0]["ts_code"] == "000002.SZ"
