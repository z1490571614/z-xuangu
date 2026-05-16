from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.database.schema_migrations import ensure_runtime_columns
from backend.services import risk_breakdown_service
from backend.services.risk_breakdown_service import RiskBreakdownService


RISK_CONTEXT_COLUMNS = {
    "news_tips",
    "sector_context",
    "lhb_strength_evidence",
    "lhb_risk_evidence",
    "strength_evidence",
    "risk_evidence",
}


def test_risk_breakdown_persists_sector_context_and_lhb_evidence(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(risk_breakdown_service, "SessionLocal", TestSessionLocal)

    svc = RiskBreakdownService()
    data = {
        "total_score": 32,
        "risk_level": "中",
        "market_score": 1,
        "chip_score": 2,
        "news_score": 3,
        "capital_score": 4,
        "lhb_score": 5,
        "sector_score": 6,
        "technical_score": 7,
        "market_tips": ["大盘偏弱"],
        "chip_tips": ["筹码压力"],
        "news_tips": ["公告风险"],
        "capital_tips": ["资金流出"],
        "lhb_tips": ["核按钮席位"],
        "sector_tips": ["算力租赁板块下跌2.1%，题材承接转弱"],
        "technical_tips": ["RSI偏高"],
        "risk_summary": "风险中等，需观察确认",
        "warning_tip": "",
        "sector_context": {
            "primary_board": {"code": "BK1160.DC", "name": "算力租赁", "source": "eastmoney"},
            "board_pct_chg": -2.1,
            "money_net_amount_yi": -3.2,
            "limit_up_count": 2,
            "member_count": 80,
            "strength_score": 42,
        },
        "lhb_strength_evidence": [{
            "type": "premium_buy",
            "label": "高溢价席位买入",
            "seats": ["大连黄河路"],
            "score_effect": "抵扣龙虎风险，进入强势依据",
        }],
        "lhb_risk_evidence": [{
            "type": "dump_sell",
            "label": "砸盘席位卖出",
            "seats": ["华泰成都南一环路"],
            "score_effect": "增加龙虎风险",
        }],
        "strength_evidence": ["高溢价席位买入：大连黄河路"],
        "risk_evidence": ["砸盘席位卖出：华泰成都南一环路"],
    }

    svc._save_to_db("000889.SZ", "20260508", data)
    cached = svc._get_from_db("000889.SZ", "20260508")

    assert cached["sector_context"]["primary_board"]["code"] == "BK1160.DC"
    assert cached["lhb_strength_evidence"][0]["seats"] == ["大连黄河路"]
    assert cached["lhb_risk_evidence"][0]["seats"] == ["华泰成都南一环路"]
    assert cached["strength_evidence"] == ["高溢价席位买入：大连黄河路"]
    assert cached["risk_evidence"] == ["砸盘席位卖出：华泰成都南一环路"]


def test_runtime_migration_adds_missing_risk_context_columns_idempotently(tmp_path):
    db_path = tmp_path / "risk.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE stock_risk_breakdown (
                id INTEGER PRIMARY KEY,
                ts_code VARCHAR(20),
                trade_date VARCHAR(10),
                total_score INTEGER,
                risk_level VARCHAR(16)
            )
        """)

    ensure_runtime_columns(engine)
    ensure_runtime_columns(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("stock_risk_breakdown")}
    assert RISK_CONTEXT_COLUMNS.issubset(columns)
