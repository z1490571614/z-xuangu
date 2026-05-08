from backend.services.news_theme_extractor import NewsThemeExtractor


def test_extract_sector_news_relation_for_follow_stock():
    extractor = NewsThemeExtractor({"合力泰": "002217.SZ"})
    news = {
        "id": 1,
        "title": "PCB概念股盘初拉升，博敏电子涨停",
        "content": "PCB概念股盘初拉升，博敏电子涨停，广合科技、合力泰、国际复材、强瑞技术、瑞华泰跟涨。",
        "publish_time": "2026-05-07 09:30:00",
        "source": "cls",
    }

    rows = extractor.extract(news)

    assert rows
    row = rows[0]
    assert row["normalized_theme_name"] == "PCB"
    assert row["stock_name"] == "合力泰"
    assert row["ts_code"] == "002217.SZ"
    assert row["role"] == "follow"
    assert row["action"] == "跟涨"
    assert row["sentiment_for_theme"] == "positive"
    assert row["credibility_level"] == "medium"


def test_extract_requires_known_stock_by_default():
    extractor = NewsThemeExtractor({})
    news = {
        "id": 1,
        "title": "算力租赁板块盘初拉升，东阳光涨停",
        "content": "算力租赁板块盘初拉升，东阳光涨停，合力泰跟涨。",
        "publish_time": "2026-05-07 09:30:00",
        "source": "cls",
    }

    assert extractor.extract(news) == []


def test_theme_name_cleanup():
    assert NewsThemeExtractor.normalize_theme_name("其中算力芯片") == "算力芯片"
    assert NewsThemeExtractor.normalize_theme_name("午评：科创50") == "科创50"
    assert NewsThemeExtractor.normalize_theme_name("早盘PCB") == "PCB"


def test_index_theme_is_filtered_from_market_relations():
    extractor = NewsThemeExtractor({"舒华体育": "605299.SH"})
    news = {
        "id": 6,
        "title": "午评：科创50指数半日涨4.71%",
        "content": "科创50指数半日涨4.71%，舒华体育涨停。",
        "publish_time": "2026-05-07 11:30:00",
        "source": "cls",
    }

    assert extractor.extract(news) == []


def test_sentence_level_binding_does_not_cross_assign_themes():
    extractor = NewsThemeExtractor({
        "中嘉博创": "000889.SZ",
        "金螳螂": "002081.SZ",
        "华电辽能": "600396.SH",
    })
    news = {
        "id": 2,
        "title": "多方向高标股活跃",
        "content": (
            "算力租赁方向延续强势，中嘉博创7天4板。"
            "商业航天方向走高，金螳螂12天10板。"
            "绿电方向活跃，华电辽能10天6板。"
        ),
        "publish_time": "2026-05-07 10:00:00",
        "source": "cls",
    }

    rows = extractor.extract(news)
    pairs = {(row["stock_name"], row["normalized_theme_name"]) for row in rows}

    assert ("中嘉博创", "算力租赁") in pairs
    assert ("金螳螂", "商业航天") in pairs
    assert ("华电辽能", "绿电") in pairs
    assert ("金螳螂", "算力租赁") not in pairs
    assert ("中嘉博创", "商业航天") not in pairs


def test_core_high_standard_stock_is_leader_for_backward_theme_sentence():
    extractor = NewsThemeExtractor({"金螳螂": "002081.SZ"})
    news = {
        "id": 3,
        "title": "商业航天方向走高",
        "content": "核心高标金螳螂12天10板，带动商业航天方向走高。",
        "publish_time": "2026-05-07 10:00:00",
        "source": "cls",
    }

    rows = extractor.extract(news)

    assert rows
    assert rows[0]["normalized_theme_name"] == "商业航天"
    assert rows[0]["role"] == "leader"
    assert rows[0]["action"] == "连板"


def test_etf_marketing_news_is_ignored_as_low_credibility_background():
    extractor = NewsThemeExtractor({"合力泰": "002217.SZ"})
    news = {
        "id": 4,
        "title": "PCB主题ETF配置价值凸显，成份股合力泰跟涨",
        "content": "相关ETF方面，PCB主题ETF成交额放大，成份股合力泰跟涨。",
        "publish_time": "2026-05-07 10:00:00",
        "source": "10jqka",
    }

    assert extractor.extract(news) == []


def test_recap_roundup_relation_is_low_credibility():
    extractor = NewsThemeExtractor({"中嘉博创": "000889.SZ"})
    news = {
        "id": 7,
        "title": "昨日行情回顾",
        "content": "算力租赁方向延续强势，中嘉博创7天4板。",
        "publish_time": "2026-05-07 08:00:00",
        "source": "cls",
    }

    rows = extractor.extract(news)

    assert rows
    assert rows[0]["credibility_level"] == "low"


def test_index_only_news_is_ignored_even_when_market_words_hit():
    extractor = NewsThemeExtractor({"合力泰": "002217.SZ"})
    news = {
        "id": 5,
        "title": "三大指数早盘走强，创业板指涨超1%",
        "content": "截至午间收盘，三大指数集体走强，市场成交额放大。",
        "publish_time": "2026-05-07 11:30:00",
        "source": "cls",
    }

    assert extractor.extract(news) == []
