import os
import struct

from backend.database import Base, engine
from backend.models.local_market_data import StockMinuteBar
from backend.services.tdx_local_minute_sync_service import TdxLocalMinuteSyncService


def _encode_tdx_minute_date(year: int, month: int, day: int) -> int:
    return (year - 2004) * 2048 + month * 100 + day


def _write_lc_file(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for row in rows:
            f.write(
                struct.pack(
                    "<HHfffffII",
                    _encode_tdx_minute_date(row["year"], row["month"], row["day"]),
                    row["hour"] * 60 + row["minute"],
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["amount"]),
                    int(row["vol"]),
                    0,
                )
            )


def test_tdx_local_minute_reads_lc1_file_as_rows(tmp_path):
    lc_path = tmp_path / "sz" / "fzline" / "sz000001.lc1"
    _write_lc_file(
        lc_path,
        [
            {
                "year": 2024,
                "month": 5,
                "day": 10,
                "hour": 9,
                "minute": 31,
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "vol": 10000,
                "amount": 102000,
            },
            {
                "year": 2024,
                "month": 5,
                "day": 10,
                "hour": 9,
                "minute": 32,
                "open": 10.2,
                "high": 10.4,
                "low": 10.1,
                "close": 10.35,
                "vol": 12000,
                "amount": 123000,
            },
        ],
    )
    service = TdxLocalMinuteSyncService(tdx_vipdoc_path=str(tmp_path))

    rows = service.read_minute_rows("000001.SZ", "20240510", "20240510", interval=1)

    assert rows == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "20240510",
            "trade_time": "09:31",
            "bar_time": "2024-05-10 09:31:00",
            "interval": 1,
            "open": 10.1,
            "high": 10.3,
            "low": 10.0,
            "close": 10.2,
            "vol": 10000.0,
            "amount": 102000.0,
            "source": "tdx_lc1",
        },
        {
            "ts_code": "000001.SZ",
            "trade_date": "20240510",
            "trade_time": "09:32",
            "bar_time": "2024-05-10 09:32:00",
            "interval": 1,
            "open": 10.2,
            "high": 10.4,
            "low": 10.1,
            "close": 10.35,
            "vol": 12000.0,
            "amount": 123000.0,
            "source": "tdx_lc1",
        },
    ]


def test_sync_local_minute_upserts_to_stock_minute_bar(tmp_path, db):
    Base.metadata.create_all(bind=engine)
    db.query(StockMinuteBar).filter(StockMinuteBar.ts_code == "000001.SZ").delete()
    db.commit()
    lc_path = tmp_path / "sz" / "fzline" / "sz000001.lc1"
    _write_lc_file(
        lc_path,
        [
            {
                "year": 2024,
                "month": 5,
                "day": 10,
                "hour": 9,
                "minute": 31,
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "vol": 10000,
                "amount": 102000,
            }
        ],
    )
    service = TdxLocalMinuteSyncService(tdx_vipdoc_path=str(tmp_path), session_factory=lambda: db)

    result = service.sync_range("20240510", "20240510", ts_codes=["000001.SZ"], interval=1)
    again = service.sync_range("20240510", "20240510", ts_codes=["000001.SZ"], interval=1)

    rows = db.query(StockMinuteBar).filter_by(ts_code="000001.SZ").all()
    assert result["rows_synced"] == 1
    assert result["rows_skipped_existing"] == 0
    assert again["rows_synced"] == 0
    assert again["rows_skipped_existing"] == 1
    assert len(rows) == 1
    assert rows[0].trade_date == "20240510"
    assert rows[0].trade_time == "09:31"
    assert rows[0].interval == 1
    assert rows[0].source == "tdx_lc1"
