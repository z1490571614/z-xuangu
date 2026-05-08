import pandas as pd

from backend.database import Base, engine, SessionLocal
from backend.models.stock_ths_board import ThsBoardIndex
from backend.services.dc_board_service import DcBoardService
from backend.services.dragon_leader.data.theme_context import ThemeContext
from backend.services.ths_board_service import ThsBoardService


def setup_function():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ThsBoardIndex).delete()
        db.commit()
    finally:
        db.close()
    ThsBoardService.clear_catalog_cache()


def test_theme_context_reads_stock_boards_from_dc_service(monkeypatch):
    calls = {"count": 0}

    def fake_get_stock_boards(self, ts_code, trade_date=None, refresh_if_missing=False):
        calls["count"] += 1
        assert ts_code == "002081.SZ"
        assert trade_date == "20260507"
        assert refresh_if_missing is True
        return [{"ts_code": "BK0821.DC", "name": "物业管理", "type": "概念板块", "source": "eastmoney"}]

    monkeypatch.setattr(DcBoardService, "get_stock_boards", fake_get_stock_boards)

    concepts = ThemeContext().get_stock_concepts("002081.SZ", "20260507")

    assert concepts == [{"ts_code": "BK0821.DC", "name": "物业管理", "type": "概念板块"}]
    assert calls["count"] == 1


def test_resolve_board_meta_uses_single_code_lookup_not_full_index(monkeypatch):
    class FakePro:
        def __init__(self):
            self.calls = []

        def ths_index(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs == {"ts_code": "885915.TI"}
            return pd.DataFrame([{
                "ts_code": "885915.TI",
                "name": "物业管理",
                "type": "N",
                "count": 178,
            }])

    svc = ThsBoardService()
    fake_pro = FakePro()
    svc._pro = fake_pro

    meta = svc._fetch_board_meta("885915.TI")

    assert meta["board_code"] == "885915.TI"
    assert meta["board_name"] == "物业管理"
    assert fake_pro.calls == [{"ts_code": "885915.TI"}]


def test_sync_board_index_catalog_updates_concept_and_industry_once():
    class FakePro:
        def __init__(self):
            self.calls = []

        def ths_index(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs == {"type": "N"}:
                return pd.DataFrame([{
                    "ts_code": "886950.TI",
                    "name": "算力租赁",
                    "type": "N",
                    "count": 12,
                }])
            if kwargs == {"type": "I"}:
                return pd.DataFrame([{
                    "ts_code": "881950.TI",
                    "name": "通信设备",
                    "type": "I",
                    "count": 80,
                }])
            return pd.DataFrame()

    svc = ThsBoardService()
    fake_pro = FakePro()
    svc._pro = fake_pro

    stats = svc.sync_board_index_catalog(force=True)

    assert stats["fetched"] == 2
    assert fake_pro.calls == [{"type": "N"}, {"type": "I"}]

    db = SessionLocal()
    try:
        rows = {
            row.board_code: row.board_name
            for row in db.query(ThsBoardIndex).filter(
                ThsBoardIndex.board_code.in_(["886950.TI", "881950.TI"])
            ).all()
        }
    finally:
        db.close()

    assert rows == {"886950.TI": "算力租赁", "881950.TI": "通信设备"}


def test_normalize_board_terms_reads_db_without_tushare_calls():
    db = SessionLocal()
    try:
        db.merge(ThsBoardIndex(
            board_code="886951.TI",
            board_name="算力租赁",
            board_type="N",
            source="test",
            is_active=True,
        ))
        db.merge(ThsBoardIndex(
            board_code="885951.TI",
            board_name="人工智能",
            board_type="N",
            source="test",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    class NoNetworkPro:
        def ths_index(self, **kwargs):
            raise AssertionError("normalize_board_terms must not call Tushare")

    svc = ThsBoardService()
    svc._pro = NoNetworkPro()
    svc.clear_catalog_cache()

    matches = svc.normalize_board_terms("智算租赁服务", source="news_theme", top_n=3)

    assert matches[0]["name"] == "算力租赁"
    assert matches[0]["matched_from"] == "news_theme"
