import pandas as pd

from backend.database import Base, engine, SessionLocal
from backend.models.board import (
    BoardIndex,
    DcBoardAlias,
    DcBoardAliasObservation,
    DcBoardAliasSyncState,
)
from backend.services.dc_board_alias_service import DcBoardAliasService
from backend.services.dc_board_service import DcBoardService


class FakeAliasPro:
    def __init__(self):
        self.limit_rows = []

    def limit_list_ths(self, **kwargs):
        return pd.DataFrame(self.limit_rows)

    def dc_index(self, **kwargs):
        if kwargs.get("idx_type") == "概念板块":
            return pd.DataFrame([{
                "ts_code": "BK1134.DC",
                "name": "算力概念",
                "idx_type": "概念板块",
            }])
        return pd.DataFrame()


def setup_module():
    Base.metadata.create_all(bind=engine)


def setup_function():
    db = SessionLocal()
    try:
        db.query(DcBoardAliasSyncState).delete()
        db.query(DcBoardAliasObservation).delete()
        db.query(DcBoardAlias).delete()
        db.query(BoardIndex).delete()
        db.commit()
    finally:
        db.close()
    DcBoardService.clear_catalog_cache()


def test_sync_trade_date_is_idempotent_but_allows_intraday_new_rows():
    fake = FakeAliasPro()
    fake.limit_rows = [
        {"trade_date": "20260508", "ts_code": "000889.SZ", "lu_desc": "算力租赁+通信运维"},
    ]
    svc = DcBoardAliasService(pro=fake)

    first = svc.sync_trade_date("20260508", finalize=False)
    second = svc.sync_trade_date("20260508", finalize=False)
    fake.limit_rows.append(
        {"trade_date": "20260508", "ts_code": "002217.SZ", "lu_desc": "算力租赁+电子纸"}
    )
    third = svc.sync_trade_date("20260508", finalize=False)

    assert first["inserted_observations"] == 1
    assert second["inserted_observations"] == 0
    assert third["inserted_observations"] == 1

    db = SessionLocal()
    try:
        alias = db.query(DcBoardAlias).filter(DcBoardAlias.board_code == "BK1134.DC").one()
        assert alias.alias == "算力租赁"
        assert alias.hit_count == 2
        assert alias.stock_count == 2
        assert alias.review_status == "auto_approved"
        assert db.query(DcBoardAliasObservation).count() == 2
        state = db.query(DcBoardAliasSyncState).filter_by(trade_date="20260508").one()
        assert state.source_row_count == 2
        assert state.inserted_observation_count == 1
    finally:
        db.close()


def test_finalized_trade_date_skips_later_startup_sync():
    fake = FakeAliasPro()
    fake.limit_rows = [
        {"trade_date": "20260508", "ts_code": "000889.SZ", "lu_desc": "算力租赁"},
    ]
    svc = DcBoardAliasService(pro=fake)

    finalized = svc.sync_trade_date("20260508", finalize=True)
    fake.limit_rows.append(
        {"trade_date": "20260508", "ts_code": "002217.SZ", "lu_desc": "算力租赁"}
    )
    skipped = svc.sync_trade_date("20260508", finalize=False)

    assert finalized["inserted_observations"] == 1
    assert skipped["skipped"] == 1
    assert skipped["inserted_observations"] == 0

    db = SessionLocal()
    try:
        assert db.query(DcBoardAliasObservation).count() == 1
        alias = db.query(DcBoardAlias).filter(DcBoardAlias.board_code == "BK1134.DC").one()
        assert alias.hit_count == 1
    finally:
        db.close()


def test_dc_board_service_reads_runtime_db_aliases():
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
        db.add(DcBoardAlias(
            board_code="BK1134.DC",
            board_name="算力概念",
            board_type="概念板块",
            alias="算力销售",
            alias_clean=DcBoardAliasService.clean_alias("算力销售"),
            source="generated",
            confidence_score=118,
            hit_count=2,
            stock_count=1,
            first_seen_date="20260508",
            last_seen_date="20260508",
            review_status="auto_approved",
            is_active=True,
        ))
        db.commit()
    finally:
        db.close()

    matches = DcBoardService().normalize_board_terms("算力销售", source="limit_tag", top_n=3)

    assert matches[0]["ts_code"] == "BK1134.DC"
