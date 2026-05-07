"""
龙头战法评分模块 - 单元测试

测试策略：
- ScoreContext 模式下不调外部 API，纯规则验证
- 每个评分函数独立测试
"""
import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TUSHARE_TOKEN", "test_token")

import pytest
from backend.services.dragon_leader.scorer.announcement_alpha import (
    calculate_announcement_alpha,
)
from backend.services.dragon_leader.output import (
    get_leader_level, get_retreat_risk_level, get_health_level,
    get_cycle_stage, collect_positive_tips, collect_negative_tips
)


# ===================== 消息面加减分测试 =====================

class TestAnnouncementAlpha:

    def test_empty_news(self):
        result = calculate_announcement_alpha([])
        assert result["data_status"] == "missing"
        assert result["announcement_alpha_score"] == 0

    def test_positive_sentiment(self):
        """positive情感分析->利好加分"""
        news = [{"title": "公司净利润同比增长85%创新高", "sentiment_type": "positive", "sentiment_score": 0.9}]
        result = calculate_announcement_alpha(news)
        assert result["good_news_score"] > 0
        assert result["announcement_alpha_score"] > 0
        assert result["announcement_bias"] == "positive"

    def test_negative_sentiment(self):
        """negative情感分析->利空扣分"""
        news = [{"title": "净利润同比下降57%", "sentiment_type": "negative", "sentiment_score": 0.9}]
        result = calculate_announcement_alpha(news)
        assert result["bad_news_score"] < 0
        assert result["announcement_alpha_score"] < 0
        assert result["announcement_bias"] == "negative"

    def test_combined_sentiment(self):
        """正负情感新闻混合（新引擎使用事件判定所以不同新闻分别评分）"""
        news = [
            {"title": "净利润同比增长85%创新高", "sentiment_type": "positive", "sentiment_score": 0.7},
            {"title": "净利润下降30%", "sentiment_type": "negative", "sentiment_score": 0.8},
        ]
        result = calculate_announcement_alpha(news)
        assert result["good_news_score"] > 0
        assert result["bad_news_score"] < 0
        assert result["announcement_bias"] in ("mixed", "positive", "negative")

    def test_alpha_limit(self):
        many = [{"title": f"利好{x}", "sentiment_type": "positive", "sentiment_score": 1.0} for x in range(10)]
        result = calculate_announcement_alpha(many)
        assert -20 <= result["announcement_alpha_score"] <= 20

    def test_neutral_sentiment(self):
        """neutral情感->分数为0"""
        news = [{"title": "公司召开股东大会", "sentiment_type": "neutral", "sentiment_score": 0.5}]
        result = calculate_announcement_alpha(news)
        assert result["announcement_alpha_score"] == 0
        assert result["announcement_bias"] == "neutral"

    def test_zero_score_ignored(self):
        """sentiment_score为0时不参与计分"""
        news = [{"title": "某公告", "sentiment_type": "negative", "sentiment_score": 0}]
        result = calculate_announcement_alpha(news)
        assert result["bad_news_score"] == 0

    def test_directional_negation_同比下降(self):
        """"同比下降"经由SentimentAnalyzer判定为negative"""
        news = [{"title": "净利润1421万元同比下降57%", "sentiment_type": "negative", "sentiment_score": 0.85}]
        result = calculate_announcement_alpha(news)
        assert result["bad_news_score"] < 0
        assert result["announcement_bias"] == "negative"

    def test_directional_negation_同比大增(self):
        """"同比增长85%"经由SentimentAnalyzer判定为positive"""
        news = [{"title": "净利润同比增长85%创新高", "sentiment_type": "positive", "sentiment_score": 0.9}]
        result = calculate_announcement_alpha(news)
        assert result["good_news_score"] > 0
        assert result["announcement_bias"] == "positive"


# ===================== 评级函数测试 =====================

class TestRatingLevels:

    def test_leader_level_extreme(self):
        assert get_leader_level(90) == "极强龙头"

    def test_leader_level_strong(self):
        assert get_leader_level(75) == "强势龙头"

    def test_leader_level_suspect(self):
        assert get_leader_level(60) == "疑似龙头"

    def test_leader_level_follower(self):
        assert get_leader_level(45) == "跟风强势股"

    def test_leader_level_none(self):
        assert get_leader_level(20) == "非龙头"

    def test_retreat_level_low(self):
        assert get_retreat_risk_level(20) == "低风险"

    def test_retreat_level_medium(self):
        assert get_retreat_risk_level(35) == "中等风险"

    def test_retreat_level_high(self):
        assert get_retreat_risk_level(55) == "高风险"

    def test_retreat_level_extreme(self):
        assert get_retreat_risk_level(80) == "极高风险"

    def test_health_level_healthy(self):
        assert get_health_level(85) == "龙头健康"

    def test_health_level_strong(self):
        assert get_health_level(70) == "强势可观察"

    def test_health_level_divergence(self):
        assert get_health_level(55) == "分歧加大"

    def test_health_level_retreat_warning(self):
        assert get_health_level(40) == "退潮预警"

    def test_health_level_avoid(self):
        assert get_health_level(20) == "回避"

    def test_cycle_stage_main_rise(self):
        assert get_cycle_stage(70, 20, 75) == "主升期"

    def test_cycle_stage_divergence(self):
        assert get_cycle_stage(55, 40, 55) == "分歧期"

    def test_cycle_stage_retreat(self):
        assert get_cycle_stage(40, 60, 30) == "退潮期"

    def test_cycle_stage_confusion(self):
        assert get_cycle_stage(20, 20, 35) == "混沌期"


# ===================== 提示词收集测试 =====================

class TestTipsCollection:

    def test_collect_positive_empty(self):
        tips = collect_positive_tips({}, {"good_news_score": 0}, {"lhb_bonus_score": 0})
        assert isinstance(tips, list)

    def test_collect_negative_empty(self):
        tips = collect_negative_tips({}, {"bad_news_score": 0}, {"lhb_penalty_score": 0})
        assert isinstance(tips, list)

    def test_collect_positive_with_news(self):
        leader_parts = {
            "leader_status": {"score": 20, "tips": ["3连板，板块先锋"], "data_status": "available"}
        }
        ann_result = {"good_news_score": 8, "bad_news_score": 0, "tips": [], "announcement_alpha_score": 8, "announcement_bias": "positive", "data_status": "available"}
        lhb_result = {"lhb_bonus_score": 0, "lhb_penalty_score": 0, "lhb_alpha_score": 0, "tips": [], "data_status": "not_applicable"}
        tips = collect_positive_tips(leader_parts, ann_result, lhb_result)
        assert len(tips) > 0
        assert any("连板" in t for t in tips)


# ===================== 龙虎榜加减分测试 =====================

class TestLhbAlpha:

    def test_no_lhb_data(self):
        from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
        result = calculate_lhb_alpha(None)
        assert result["data_status"] == "not_applicable"
        assert result["lhb_alpha_score"] == 0

    def test_not_available(self):
        from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
        result = calculate_lhb_alpha({"data_status": "not_on_list"})
        assert result["data_status"] == "not_applicable"

    def test_alpha_limit(self):
        """验证龙虎榜alpha在[-20, 20]区间"""
        from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
        lhb_data = {
            "data_status": "available",
            "buy_top5": [{"exalter": "华泰证券深圳益田路", "buy": 50000000, "sell": 0, "net_buy": 50000000}],
            "sell_top5": [{"exalter": "长城证券仙桃钱沟路", "buy": 0, "sell": 30000000, "net_buy": -30000000}],
            "net_amount": 20000000,
            "buy_amount": 50000000,
            "sell_amount": 30000000,
        }
        result = calculate_lhb_alpha(lhb_data)
        assert -20 <= result["lhb_alpha_score"] <= 20


# ===================== 退出评分函数不崩溃测试 =====================

class TestScorersNoCrash:

    def test_leader_status_empty_ctx(self):
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_leader_status
        result = calculate_leader_status({})
        assert "score" in result
        assert 0 <= result["score"] <= 25

    def test_emotion_cycle_empty(self):
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_emotion_cycle
        result = calculate_emotion_cycle({})
        assert "score" in result

    def test_acceptance_empty(self):
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_acceptance_strength
        result = calculate_acceptance_strength({})
        assert "score" in result

    def test_auction_empty(self):
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_auction_intraday
        result = calculate_auction_intraday({})
        assert "score" in result

    def test_chip_cashout_empty(self):
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_chip_cashout
        result = calculate_chip_cashout({})
        assert "score" in result

    def test_leader_position_loss_empty(self):
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_leader_position_loss
        result = calculate_leader_position_loss({})
        assert "score" in result

    def test_acceptance_failure_empty(self):
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_acceptance_failure
        result = calculate_acceptance_failure({})
        assert "score" in result

    def test_auction_miss_empty(self):
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_auction_miss
        result = calculate_auction_miss({})
        assert "score" in result


# ===================== 阶段2：题材/板块/承接测试 =====================

class TestPhase2ThemeScoring:

    def test_theme_alias_maps_semiconductor_cleanroom_to_chip(self):
        """涨停原因语义匹配：半导体洁净室应优先识别为芯片/半导体题材"""
        from backend.services.dragon_leader.data.theme_context import ThemeContext
        ctx = ThemeContext()
        score, reasons = ctx._theme_match_score(
            {"name": "芯片概念", "rank": 2},
            {"lu_desc": "半导体洁净室+海外EPC+城市更新", "concept": "一带一路", "board_type": "", "industry": "装修装饰"},
        )
        broad_score, _ = ctx._theme_match_score(
            {"name": "一带一路", "rank": 18},
            {"lu_desc": "半导体洁净室+海外EPC+城市更新", "concept": "一带一路", "board_type": "", "industry": "装修装饰"},
        )
        assert score > broad_score
        assert any("语义命中" in reason for reason in reasons)

    def test_theme_strength_with_hot_board(self):
        """题材强度评分：题材上榜排名靠前"""
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_theme_strength
        ctx = {
            "theme": {
                "theme_rank": {
                    "best_rank": 3,
                    "board_count": 2,
                    "hot_boards": [
                        {"name": "芯片概念", "up_nums": 22, "cons_nums": 7,
                         "up_stat": "13天10板", "days": 10, "rank": 1, "pct_chg": 2.86}
                    ]
                }
            }
        }
        result = calculate_theme_strength(ctx)
        assert result["score"] >= 15
        assert result["data_status"] == "available"

    def test_theme_strength_no_match(self):
        """题材强度评分：未上榜"""
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_theme_strength
        ctx = {"theme": {"theme_rank": {"best_rank": 999, "board_count": 0, "hot_boards": []}}}
        result = calculate_theme_strength(ctx)
        assert result["data_status"] == "insufficient_data"
        assert not any("未进入" in tip for tip in result["tips"])

    def test_sector_ladder_strong(self):
        """板块梯队评分：梯队完整"""
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_sector_ladder
        ctx = {
            "theme": {
                "theme_rank": {
                    "hot_boards": [
                        {"name": "机器人概念", "cons_nums": 5, "up_nums": 20, "days": 8}
                    ]
                }
            }
        }
        result = calculate_sector_ladder(ctx)
        assert result["score"] >= 10
        assert result["data_status"] == "available"

    def test_sector_ladder_no_board(self):
        """板块梯队评分：未上榜"""
        from backend.services.dragon_leader.scorer.leader_scorer import calculate_sector_ladder
        ctx = {"theme": {"theme_rank": {"hot_boards": []}}}
        result = calculate_sector_ladder(ctx)
        assert result["score"] <= 3
        assert not any("未进入" in tip for tip in result["tips"])

    def test_acceptance_failure_with_break(self):
        """承接失败：炸板不回封（kpl_list数据）"""
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_acceptance_failure
        ctx = {
            "theme": {
                "kpl_detail": {"is_break": True, "is_limit_up": False}
            },
            "stock": {}, "daily": {}, "capital": {}
        }
        result = calculate_acceptance_failure(ctx)
        assert result["score"] >= 8

    def test_acceptance_failure_with_seal_weak(self):
        """承接失败：封单薄弱"""
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_acceptance_failure
        ctx = {
            "theme": {
                "kpl_detail": {"is_break": False, "is_limit_up": True, "seal_amount": 3000000}
            },
            "stock": {}, "daily": {}, "capital": {}
        }
        result = calculate_acceptance_failure(ctx)
        assert result["score"] >= 3

    def test_ladder_break_with_gaps(self):
        """板块梯队断裂检测"""
        from backend.services.dragon_leader.scorer.retreat_scorer import calculate_ladder_break
        ctx = {
            "theme": {
                "theme_rank": {
                    "best_rank": 30,
                    "hot_boards": [
                        {"name": "芯片概念", "cons_nums": 0, "up_nums": 5, "days": 1}
                    ]
                }
            }
        }
        result = calculate_ladder_break(ctx)
        assert result["score"] >= 5


# ===================== 阶段3：基本面/ST/减持/分时测试 =====================

class TestPhase3DimensionScoring:

    def test_financial_risk_loss_forecast(self):
        """业绩风险：续亏预告 → dimension_scores.financial_risk 为负"""
        news = [{"title": "公司业绩预告续亏", "sentiment_type": "negative", "sentiment_score": 0.9}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("financial_risk", 0) < 0, f"financial_risk应扣分，实际={ds.get('financial_risk')}"

    def test_financial_risk_同比下降(self):
        """业绩风险：同比下降 → dimension_scores.financial_risk 为负"""
        news = [{"title": "公司净利润同比下降57%", "sentiment_type": "negative", "sentiment_score": 0.85}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("financial_risk", 0) < 0

    def test_financial_risk_no_data(self):
        """业绩风险：无新闻 → dimension_scores 为0"""
        result = calculate_announcement_alpha([])
        assert result["data_status"] == "missing"
        assert result["dimension_scores"]["financial_risk"] == 0

    def test_shareholder_risk_reduce(self):
        """股东减持风险 → dimension_scores.shareholder_risk"""
        news = [{"title": "大股东减持计划减持不超过5%股份", "sentiment_type": "negative", "sentiment_score": 0.8}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("shareholder_risk", 0) < 0

    def test_shareholder_risk_increase(self):
        """股东增持利好 → shareholder_risk 不加分"""
        news = [{"title": "大股东增持公司股份金额超1亿元", "sentiment_type": "positive", "sentiment_score": 0.85}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        # 增持是利好，shareholder_risk维度分数>0表示利好
        assert ds.get("shareholder_risk", 0) >= 0

    def test_st_risk_active(self):
        """退市风险 → dimension_scores.regulatory（新引擎退市归入regulatory）"""
        news = [{"title": "公司存在退市风险警示", "sentiment_type": "negative", "sentiment_score": 0.95}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("regulatory", 0) < 0

    def test_st_risk_no_st(self):
        """无ST新闻 → st_risk为0"""
        news = [{"title": "公司召开股东大会", "sentiment_type": "neutral", "sentiment_score": 0.5}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("st_risk", 0) == 0

    def test_shareholder_float_pressure(self):
        """解禁压力 → dimension_scores.shareholder_risk"""
        news = [{"title": "公司限售股解禁金额巨大", "sentiment_type": "negative", "sentiment_score": 0.75}]
        result = calculate_announcement_alpha(news)
        ds = result.get("dimension_scores", {})
        assert ds.get("shareholder_risk", 0) < 0
