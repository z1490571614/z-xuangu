"""
风险评分服务单元测试
"""
import pytest
from backend.services.scoring_v2.risk_score_service import RiskScoreService


class TestRiskScoreService:

    def test_calculate_returns_required_fields(self):
        """calculate 应返回包含所有必要字段的 dict"""
        result = RiskScoreService.calculate()
        assert "total_score" in result
        assert "risk_level" in result
        assert "items" in result
        assert isinstance(result["items"], list)
        assert len(result["items"]) == 8

    def test_score_range(self):
        """风险评分应在 0-100 范围内"""
        result = RiskScoreService.calculate()
        assert 0 <= result["total_score"] <= 100

    def test_high_position_risk(self):
        """短期涨幅过高时应产生高位风险标志"""
        result = RiskScoreService.calculate(rise_10d_pct=50.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["高位风险"]["score"] >= 15
        assert "短期涨幅过大" in (result.get("risk_flags") or [])

    def test_low_position_risk(self):
        """短期涨幅温和时高位风险应较低"""
        result = RiskScoreService.calculate(rise_10d_pct=5.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["高位风险"]["score"] <= 5

    def test_open_board_risk_low_seal_rate(self):
        """低封板率应产生较高炸板风险"""
        result = RiskScoreService.calculate(seal_rate=55.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["炸板/失败风险"]["score"] >= 8

    def test_open_board_risk_high_seal_rate(self):
        """高封板率时炸板风险应较低"""
        result = RiskScoreService.calculate(seal_rate=95.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["炸板/失败风险"]["score"] <= 5

    def test_liquidity_risk_low_turnover(self):
        """竞价换手率低时应产生流动性风险"""
        result = RiskScoreService.calculate(auction_turnover_rate=0.2, circ_mv=5.0, auction_ratio=2.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["流动性风险"]["score"] >= 5

    def test_liquidity_risk_high_turnover(self):
        """竞价换手率高时流动性风险应较低"""
        result = RiskScoreService.calculate(auction_turnover_rate=2.0, circ_mv=100.0, auction_ratio=15.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["流动性风险"]["score"] <= 5

    def test_event_missing_high_open(self):
        """高开但缺少催化时应标记事件缺失风险"""
        result = RiskScoreService.calculate(open_change_pct=8.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["事件缺失风险"]["score"] >= 5

    def test_volatility_risk(self):
        """10日波动大时波动风险应较高"""
        result = RiskScoreService.calculate(rise_10d_pct=45.0, pre_change_pct=8.0)
        items = {it["name"]: it for it in result["items"]}
        assert items["波动风险"]["score"] >= 2

    def test_risk_level_mapping(self):
        """风险总分应正确映射到等级"""
        assert RiskScoreService._to_level(10) == "偏低"
        assert RiskScoreService._to_level(30) == "中等偏低"
        assert RiskScoreService._to_level(50) == "中等偏高"
        assert RiskScoreService._to_level(70) == "偏高"
        assert RiskScoreService._to_level(90) == "极高"

    def test_all_dimensions_have_names(self):
        """每个维度都应有名称"""
        result = RiskScoreService.calculate()
        names = [it["name"] for it in result["items"]]
        assert len(names) == 8
        assert "高位风险" in names
        assert "历史回撤风险" in names
        assert "炸板/失败风险" in names
        assert "流动性风险" in names
        assert "市场环境风险" in names
        assert "事件缺失风险" in names
        assert "财务/公告风险" in names
        assert "波动风险" in names

    def test_none_inputs_no_crash(self):
        """None 输入不应导致崩溃"""
        result = RiskScoreService.calculate(
            rise_10d_pct=None,
            pre_change_pct=None,
            open_change_pct=None,
            seal_rate=None,
            limit_up_count=None,
            limit_up_days=None,
            touch_days=None,
            auction_ratio=None,
            auction_turnover_rate=None,
            circ_mv=None,
        )
        assert result["total_score"] is not None
        assert result["risk_level"] is not None

    def test_risk_flags_limit(self):
        """risk_flags 最多返回 6 个"""
        result = RiskScoreService.calculate(
            rise_10d_pct=50.0, seal_rate=50.0, circ_mv=5.0, auction_turnover_rate=0.2
        )
        assert len(result.get("risk_flags", [])) <= 6
