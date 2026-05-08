from backend.services.theme_attribution_scorer import ThemeAttributionScorer


def test_news_relation_and_hot_board_beats_static_generic_concept():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="002217.SZ",
        stock_name="合力泰",
        trade_date="20260507",
        lu_desc="",
        news_relations=[
            {
                "ts_code": "002217.SZ",
                "stock_name": "合力泰",
                "normalized_theme_name": "PCB概念",
                "role": "follow",
                "action": "跟涨",
                "title": "PCB概念股盘初拉升，博敏电子涨停",
                "evidence": "合力泰、国际复材跟涨",
                "publish_time": "2026-05-07 09:30:00",
            }
        ],
        hot_boards=[{"name": "PCB概念", "rank": 3, "up_nums": 6}],
        static_concepts=["华为概念", "消费电子"],
    )

    assert result["primary_theme"] == "PCB概念"
    assert result["theme_score"] >= 60
    assert result["confidence"] == "high"
    assert result["candidate_themes"][0]["theme_name"] == "PCB概念"
    assert any("板块归因" in item["note"] for item in result["evidence_list"])


def test_lu_desc_and_news_alignment_boosts_alias_theme():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="002081.SZ",
        stock_name="金螳螂",
        trade_date="20260507",
        lu_desc="商业航天+芯片概念+一带一路",
        news_relations=[
            {
                "ts_code": "002081.SZ",
                "stock_name": "金螳螂",
                "normalized_theme_name": "商业航天",
                "role": "leader",
                "action": "连板",
                "title": "核心高标金螳螂12天10板，带动商业航天方向走高",
                "evidence": "金螳螂12天10板，带动商业航天方向走高",
                "publish_time": "2026-05-07 10:00:00",
            }
        ],
        hot_boards=[{"name": "芯片概念", "rank": 1, "up_nums": 8}],
        static_concepts=["一带一路", "装修装饰"],
    )

    assert result["primary_theme"] == "商业航天"
    assert result["candidate_themes"][0]["theme_name"] == "商业航天"
    assert result["candidate_themes"][0]["score"] > result["candidate_themes"][1]["score"]


def test_explanation_lines_distinguish_theme_attribution_from_stock_good_news():
    scorer = ThemeAttributionScorer()
    result = scorer.score(
        ts_code="002217.SZ",
        stock_name="合力泰",
        trade_date="20260507",
        news_relations=[
            {
                "ts_code": "002217.SZ",
                "stock_name": "合力泰",
                "normalized_theme_name": "PCB概念",
                "role": "follow",
                "action": "跟涨",
                "title": "PCB概念股盘初拉升，博敏电子涨停",
                "evidence": "合力泰跟涨",
                "publish_time": "2026-05-07 09:30:00",
            }
        ],
        hot_boards=[{"name": "PCB概念", "rank": 2, "up_nums": 6}],
    )

    lines = scorer.build_explanation_lines(result)

    assert lines[0] == "主跟随题材：PCB概念"
    assert any("新闻《PCB概念股盘初拉升，博敏电子涨停》点名合力泰跟涨" in line for line in lines)
    assert any("板块归因证据，不构成个股利好/利空判断" in line for line in lines)


def test_low_credibility_recap_relation_is_discounted():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="000889.SZ",
        stock_name="中嘉博创",
        trade_date="20260508",
        news_relations=[
            {
                "ts_code": "000889.SZ",
                "stock_name": "中嘉博创",
                "normalized_theme_name": "覆铜板",
                "role": "mentioned",
                "action": "涨停",
                "title": "昨日行情回顾",
                "publish_time": "2026-05-07 08:00:00",
                "credibility_level": "low",
            }
        ],
    )

    assert result["primary_theme"] == "覆铜板"
    assert result["confidence"] == "low"


def test_news_board_relation_has_priority_over_limit_up_tag_and_static_concepts():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="000889.SZ",
        stock_name="中嘉博创",
        trade_date="20260508",
        lu_desc="5G消息",
        news_relations=[
            {
                "ts_code": "000889.SZ",
                "stock_name": "中嘉博创",
                "normalized_theme_name": "算力租赁",
                "role": "leader",
                "action": "连板",
                "title": "人气板块及个股点评",
                "publish_time": "2026-05-08 09:00:00",
                "credibility_level": "low",
            }
        ],
        static_concepts=["通信服务", "通信工程及服务", "互联网金融", "5G", "阿里巴巴概念"],
        industry="通信服务",
    )

    assert result["primary_theme"] == "算力租赁"
    assert result["candidate_themes"][0]["theme_name"] == "算力租赁"
    assert "通信服务" not in [item["theme_name"] for item in result["candidate_themes"]]


def test_hot_board_overview_has_priority_over_limit_up_tag_without_stock_membership_match():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="000889.SZ",
        stock_name="中嘉博创",
        trade_date="20260508",
        lu_desc="5G消息+通信服务",
        hot_boards=[{"name": "算力租赁", "rank": 12, "up_nums": 2, "source": "industry_overview"}],
        static_concepts=["通信服务", "5G"],
    )

    assert result["primary_theme"] == "算力租赁"


def test_news_relation_matches_stock_name_after_whitespace_normalization():
    scorer = ThemeAttributionScorer()

    result = scorer.score(
        ts_code="002081.SZ",
        stock_name="金 螳 螂",
        trade_date="20260508",
        lu_desc="半导体洁净室+海外EPC",
        news_relations=[
            {
                "ts_code": "002081.SZ",
                "stock_name": "金螳螂",
                "normalized_theme_name": "商业航天",
                "role": "leader",
                "action": "连板",
                "title": "人气板块及个股点评",
                "publish_time": "2026-05-08 09:00:00",
            }
        ],
    )

    assert result["primary_theme"] == "商业航天"
