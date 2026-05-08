import pandas as pd

from backend.database import Base, engine, SessionLocal
from backend.models.board import BoardDailySnapshot, BoardIndex, StockBoardMember
from backend.services.dc_board_service import DcBoardService


class FakeDcPro:
    def __init__(self):
        self.calls = []

    def dc_index(self, **kwargs):
        self.calls.append(("dc_index", kwargs))
        if kwargs.get("idx_type") == "概念板块":
            return pd.DataFrame([
                {
                    "ts_code": "BK1160.DC",
                    "trade_date": kwargs.get("trade_date"),
                    "name": "算力租赁",
                    "idx_type": "概念板块",
                    "pct_change": 1.2,
                    "turnover_rate": 3.4,
                }
            ])
        if kwargs.get("idx_type") == "行业板块":
            return pd.DataFrame([
                {
                    "ts_code": "BK0448.DC",
                    "trade_date": kwargs.get("trade_date"),
                    "name": "通信设备",
                    "idx_type": "行业板块",
                    "pct_change": -0.8,
                    "turnover_rate": 1.5,
                }
            ])
        return pd.DataFrame()

    def dc_member(self, **kwargs):
        self.calls.append(("dc_member", kwargs))
        assert kwargs == {"con_code": "000889.SZ", "trade_date": "20260507"}
        return pd.DataFrame([
            {
                "trade_date": "20260507",
                "ts_code": "BK1160.DC",
                "con_code": "000889.SZ",
                "name": "中嘉博创",
            }
        ])

    def dc_daily(self, **kwargs):
        self.calls.append(("dc_daily", kwargs))
        assert kwargs == {"ts_code": "BK1160.DC", "trade_date": "20260507"}
        return pd.DataFrame([
            {
                "ts_code": "BK1160.DC",
                "trade_date": "20260507",
                "pct_change": -2.1,
                "amount": 3200000000,
                "turnover_rate": 4.8,
            }
        ])

    def moneyflow_ind_dc(self, **kwargs):
        self.calls.append(("moneyflow_ind_dc", kwargs))
        assert kwargs == {"ts_code": "BK1160.DC", "trade_date": "20260507"}
        return pd.DataFrame([
            {
                "ts_code": "BK1160.DC",
                "trade_date": "20260507",
                "name": "算力租赁",
                "net_amount": -320000000,
                "rank": 86,
            }
        ])


def setup_module():
    Base.metadata.create_all(bind=engine)


def setup_function():
    db = SessionLocal()
    try:
        db.query(BoardDailySnapshot).delete()
        db.query(StockBoardMember).delete()
        db.query(BoardIndex).delete()
        db.commit()
    finally:
        db.close()
    DcBoardService.clear_catalog_cache()


def test_sync_board_index_catalog_uses_dc_index_once_per_board_type():
    svc = DcBoardService()
    fake = FakeDcPro()
    svc._pro = fake

    stats = svc.sync_board_index_catalog("20260507")

    assert stats["fetched"] == 2
    assert stats["saved"] == 2
    assert fake.calls == [
        ("dc_index", {"trade_date": "20260507", "idx_type": "概念板块"}),
        ("dc_index", {"trade_date": "20260507", "idx_type": "行业板块"}),
        ("dc_index", {"trade_date": "20260507", "idx_type": "地域板块"}),
    ]


def test_normalize_board_terms_reads_local_catalog_without_tushare_calls():
    db = SessionLocal()
    try:
        db.add(BoardIndex(
            board_code="BK1160.DC",
            board_name="算力租赁",
            board_type="概念板块",
            source="eastmoney",
            trade_date="20260507",
            is_active=True,
        ))
        db.add(BoardIndex(
            board_code="BK0448.DC",
            board_name="通信设备",
            board_type="行业板块",
            source="eastmoney",
            trade_date="20260507",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    class NoNetworkPro:
        def dc_index(self, **kwargs):
            raise AssertionError("normalize_board_terms must read local catalog only")

    svc = DcBoardService()
    svc._pro = NoNetworkPro()

    matches = svc.normalize_board_terms("智算租赁服务+算力服务", source="news_theme", top_n=3)

    assert matches[0]["ts_code"] == "BK1160.DC"
    assert matches[0]["name"] == "算力租赁"
    assert matches[0]["matched_from"] == "news_theme"


def test_normalize_computing_rental_alias_to_eastmoney_computing_concept():
    db = SessionLocal()
    try:
        db.add(BoardIndex(
            board_code="BK1134.DC",
            board_name="算力概念",
            board_type="概念板块",
            source="eastmoney",
            trade_date="20260508",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    svc = DcBoardService()

    matches = svc.normalize_board_terms("算力租赁+智算租赁服务", source="limit_tag", top_n=3)

    assert matches[0]["ts_code"] == "BK1134.DC"
    assert matches[0]["name"] == "算力概念"
    assert any("算力" in reason for reason in matches[0]["match_reasons"])


def test_normalize_board_terms_uses_generated_aliases():
    db = SessionLocal()
    try:
        db.add(BoardIndex(
            board_code="BK1134.DC",
            board_name="算力概念",
            board_type="概念板块",
            source="eastmoney",
            trade_date="20260508",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    svc = DcBoardService()

    matches = svc.normalize_board_terms("算力销售", source="limit_tag", top_n=3)

    assert matches[0]["ts_code"] == "BK1134.DC"
    assert matches[0]["name"] == "算力概念"


def test_refresh_stock_boards_persists_eastmoney_membership():
    db = SessionLocal()
    try:
        db.add(BoardIndex(
            board_code="BK1160.DC",
            board_name="算力租赁",
            board_type="概念板块",
            source="eastmoney",
            trade_date="20260507",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    svc = DcBoardService()
    fake = FakeDcPro()
    svc._pro = fake

    boards = svc.refresh_stock_boards("000889.SZ", "20260507")

    assert boards == [{
        "ts_code": "BK1160.DC",
        "name": "算力租赁",
        "type": "概念板块",
        "source": "eastmoney",
        "matched_from": "dc_member",
    }]


def test_get_board_daily_fetches_once_then_uses_snapshot_cache():
    svc = DcBoardService()
    fake = FakeDcPro()
    svc._pro = fake

    first = svc.get_board_daily("BK1160.DC", "20260507")
    second = svc.get_board_daily("BK1160.DC", "20260507")

    assert first["pct_chg"] == -2.1
    assert first["amount"] == 3200000000
    assert second["pct_chg"] == -2.1
    assert [name for name, _ in fake.calls].count("dc_daily") == 1


def test_get_board_moneyflow_returns_yuan_and_yi_units():
    svc = DcBoardService()
    fake = FakeDcPro()
    svc._pro = fake

    moneyflow = svc.get_board_moneyflow("BK1160.DC", "20260507")

    assert moneyflow["net_amount"] == -320000000
    assert moneyflow["net_amount_yi"] == -3.2
    assert moneyflow["rank"] == 86
