"""
Alpha评分服务单元测试
"""
import pytest
from backend.services.scoring_v2.alpha_score_service import AlphaScoreService


class TestAlphaScoreService:

    def test_calculate_returns_required_fields(self):
        """calculate 应返回包含所有必要字段的 dict"""
        result = AlphaScoreService.calculate()
        assert "total_score" in result
        assert "level" in result
        assert "items" in result
        assert isinstance(result["items"], list)
        assert len(result["items"]) == 6
        assert result["data_status"] == "available"

    def test_calculate_score_range(self):
        """评分应在 0-100 范围内"""
        result = AlphaScoreService.calculate()
        assert 0 <= result["total_score"] <= 100

    def test_trading_value_with_full_data(self):
        """提供完整数据时交易价值维度应返回合理分数"""
        result = AlphaScoreService.calculate(
            limit_up_count_100d=10,
            seal_rate=92.5,
            rise_10d_pct=18.5,
            circ_mv=50.0,
        )
        items = {it["name"]: it for it in result["items"]}
        tv = items["交易价值"]
        assert 5 <= tv["score"] <= 25
        assert tv["data_status"] == "available"
        assert tv["metrics"].get("historical_success_rate")

    def test_liquidity_large_cap(self):
        """大盘股流动性评分应较高"""
        result = AlphaScoreService.calculate(circ_mv=100.0, auction_turnover_rate=2.5, auction_ratio=12.0)
        items = {it["name"]: it for it in result["items"]}
        liq = items["流动性"]
        assert liq["score"] >= 10
        assert liq["data_status"] != "partial"

    def test_liquidity_small_cap(self):
        """小盘股流动性评分应较低"""
        result = AlphaScoreService.calculate(circ_mv=5.0, auction_turnover_rate=0.2, auction_ratio=2.0)
        items = {it["name"]: it for it in result["items"]}
        liq = items["流动性"]
        assert liq["score"] <= 12

    def test_sector_position_active_industry(self):
        """活跃板块应得到更高的板块地位评分"""
        result = AlphaScoreService.calculate(industry="半导体")
        items = {it["name"]: it for it in result["items"]}
        sp = items["板块地位"]
        assert sp["score"] >= 10

    def test_sector_position_unknown_industry(self):
        """非活跃板块应得到基础评分"""
        result = AlphaScoreService.calculate(industry="纺织服饰")
        items = {it["name"]: it for it in result["items"]}
        sp = items["板块地位"]
        assert sp["score"] <= 10

    def test_event_driven_with_news(self):
        """有正向新闻时事件驱动评分应更高"""
        result_with = AlphaScoreService.calculate(has_news_positive=True)
        result_without = AlphaScoreService.calculate(has_news_positive=False)
        items_with = {it["name"]: it for it in result_with["items"]}
        items_without = {it["name"]: it for it in result_without["items"]}
        assert items_with["事件驱动"]["score"] > items_without["事件驱动"]["score"]

    def test_level_mapping(self):
        """总分应正确映射到等级"""
        # 高分
        high = {"total_score": 80, "level": AlphaScoreService._level(80)}
        assert high["level"] == "较高"
        # 中等
        mid = {"total_score": 60, "level": AlphaScoreService._level(60)}
        assert mid["level"] == "中等"
        # 低分
        low = {"total_score": 30, "level": AlphaScoreService._level(30)}
        assert low["level"] == "偏低"

    def test_clamp(self):
        """_clamp 应正确限制范围"""
        assert AlphaScoreService._clamp(-10, 0, 100) == 0
        assert AlphaScoreService._clamp(150, 0, 100) == 100
        assert AlphaScoreService._clamp(50, 0, 100) == 50

    def test_all_dimensions_have_names(self):
        """每个维度都应有名称"""
        result = AlphaScoreService.calculate()
        expected_names = ["交易价值", "预期收益", "流动性", "板块地位", "事件驱动", "市场环境"]
        names = [it["name"] for it in result["items"]]
        assert names == expected_names

    def test_calculate_with_none_inputs(self):
        """None 输入不应导致崩溃"""
        result = AlphaScoreService.calculate(
            limit_up_count_100d=None,
            seal_rate=None,
            rise_10d_pct=None,
            circ_mv=None,
            industry=None,
        )
        assert result["total_score"] is not None

    def test_summary_not_empty(self):
        """summary 不应为空"""
        result = AlphaScoreService.calculate()
        assert result["summary"]
