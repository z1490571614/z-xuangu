from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.services.integrated_news_service import IntegratedNewsService
from backend.services.news_database import Base, NewsStockThemeAttribution, NewsThemeRelation


def test_extract_theme_relations_from_news_rows_for_target_stock():
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    rows = [
        SimpleNamespace(
            id=1,
            title="PCB概念股盘初拉升，博敏电子涨停",
            content="PCB概念股盘初拉升，博敏电子涨停，广合科技、合力泰、国际复材跟涨。",
            publish_time=datetime(2026, 5, 7, 9, 30),
            source="cls",
        )
    ]

    relations = service.extract_theme_relations_from_rows(
        rows,
        stock_aliases={"合力泰": "002217.SZ"},
        target_ts_code="002217.SZ",
    )

    assert len(relations) == 1
    assert relations[0]["normalized_theme_name"] == "PCB"
    assert relations[0]["stock_name"] == "合力泰"
    assert relations[0]["role"] == "follow"
    assert relations[0]["action"] == "跟涨"


def test_build_theme_attribution_keeps_sector_news_out_of_stock_sentiment():
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    rows = [
        SimpleNamespace(
            id=2,
            title="PCB概念股盘初拉升，博敏电子涨停",
            content="PCB概念股盘初拉升，博敏电子涨停，广合科技、合力泰、国际复材跟涨。",
            publish_time=datetime(2026, 5, 7, 9, 30),
            source="cls",
        )
    ]

    result = service.build_theme_attribution_from_rows(
        rows,
        ts_code="002217.SZ",
        stock_name="合力泰",
        trade_date="20260507",
        stock_aliases={"合力泰": "002217.SZ"},
        hot_boards=[{"name": "PCB概念", "rank": 2, "up_nums": 6}],
        static_concepts=["华为概念"],
    )

    assert result["primary_theme"] == "PCB概念"
    assert result["theme_score"] >= 60
    assert result["theme_relations"][0]["sentiment_for_theme"] == "positive"
    assert result["stock_sentiment_policy"] == "sector_news_neutral"
    assert any("不构成个股利好" in item["note"] for item in result["evidence_list"])


def test_save_theme_relations_upserts_by_news_theme_and_stock():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    service.session = session

    relation = {
        "news_id": 1,
        "publish_time": "2026-05-07 09:30:00",
        "source": "cls",
        "title": "PCB概念股盘初拉升，博敏电子涨停",
        "theme_name": "PCB概念",
        "normalized_theme_name": "PCB概念",
        "ts_code": "002217.SZ",
        "stock_name": "合力泰",
        "role": "follow",
        "action": "跟涨",
        "action_strength": 4,
        "time_phrase": "盘初",
        "sentiment_for_theme": "positive",
        "confidence": 0.9,
        "evidence": "合力泰跟涨",
    }

    assert service.save_theme_relations([relation], trade_date="20260507") == 1
    relation["action_strength"] = 5
    assert service.save_theme_relations([relation], trade_date="20260507") == 1

    rows = session.query(NewsThemeRelation).all()
    assert len(rows) == 1
    assert rows[0].normalized_theme_name == "PCB概念"
    assert rows[0].action_strength == 5


def test_get_stock_theme_attribution_prefers_cached_relations():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    service.session = session

    service.save_theme_relations([
        {
            "news_id": 3,
            "publish_time": "2026-05-07 09:30:00",
            "source": "cls",
            "title": "PCB概念股盘初拉升，博敏电子涨停",
            "theme_name": "PCB概念",
            "normalized_theme_name": "PCB概念",
            "ts_code": "002217.SZ",
            "stock_name": "合力泰",
            "role": "follow",
            "action": "跟涨",
            "action_strength": 4,
            "time_phrase": "盘初",
            "sentiment_for_theme": "positive",
            "confidence": 0.9,
            "credibility_level": "medium",
            "evidence": "合力泰跟涨",
        }
    ], trade_date="20260507")

    service.ensure_recent_data = lambda: None
    service.get_market_theme_news_rows = lambda limit=300: (_ for _ in ()).throw(AssertionError("不应扫描新闻"))

    result = service.get_stock_theme_attribution(
        ts_code="002217.SZ",
        stock_name="合力泰",
        trade_date="20260507",
        ensure_recent=False,
        hot_boards=[{"name": "PCB概念", "rank": 2, "up_nums": 6}],
    )

    assert result["primary_theme"] == "PCB概念"
    assert result["theme_relations"][0]["credibility_level"] == "medium"
    assert result["scanned_news_count"] == 0
    assert result["cache_hit"] is True


def test_get_stock_theme_attribution_force_refresh_ignores_cached_relations():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    service.session = session

    service.save_theme_relations([
        {
            "news_id": 4,
            "publish_time": "2026-05-07 09:30:00",
            "source": "cls",
            "title": "旧题材新闻",
            "theme_name": "旧题材",
            "normalized_theme_name": "旧题材",
            "ts_code": "002217.SZ",
            "stock_name": "合力泰",
            "role": "mentioned",
            "action": "",
            "confidence": 0.5,
        }
    ], trade_date="20260507")

    service.get_market_theme_news_rows = lambda limit=300: [
        SimpleNamespace(
            id=5,
            title="PCB概念股盘初拉升，博敏电子涨停",
            content="PCB概念股盘初拉升，博敏电子涨停，广合科技、合力泰跟涨。",
            publish_time=datetime(2026, 5, 7, 9, 30),
            source="cls",
        )
    ]

    result = service.get_stock_theme_attribution(
        ts_code="002217.SZ",
        stock_name="合力泰",
        trade_date="20260507",
        ensure_recent=False,
        force_refresh=True,
        hot_boards=[{"name": "PCB概念", "rank": 2, "up_nums": 6}],
    )

    assert result["primary_theme"] == "PCB概念"
    assert result["scanned_news_count"] == 1
    assert result["cache_hit"] is False


def test_stock_theme_attribution_cache_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    service = IntegratedNewsService.__new__(IntegratedNewsService)
    service.session = session

    data = {
        "ts_code": "002217.SZ",
        "stock_name": "合力泰",
        "trade_date": "20260507",
        "primary_theme": "PCB概念",
        "theme_score": 72,
        "confidence": "high",
        "candidate_themes": [{"theme_name": "PCB概念", "score": 72}],
        "evidence_list": [{"source": "新闻主题关系", "detail": "点名合力泰跟涨"}],
        "explanation_lines": ["主跟随题材：PCB概念"],
    }

    assert service.save_stock_theme_attribution(data) == 1
    data["theme_score"] = 80
    assert service.save_stock_theme_attribution(data) == 1

    cached = service.get_cached_stock_theme_attribution("002217.SZ", "20260507")
    rows = session.query(NewsStockThemeAttribution).all()

    assert len(rows) == 1
    assert cached["primary_theme"] == "PCB概念"
    assert cached["theme_score"] == 80
    assert cached["candidate_themes"][0]["theme_name"] == "PCB概念"
