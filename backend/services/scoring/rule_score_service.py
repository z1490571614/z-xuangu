"""
规则评分服务 - 涨停基因/封板可靠性/趋势/竞价/风险 五维评分
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class RuleScoreService:
    """
    规则评分引擎
    五维加权评分，满分100分
    """

    # 各维度权重
    WEIGHTS = {
        "limit_up_gene": 25,       # 涨停基因
        "seal_reliability": 25,    # 封板可靠性
        "trend_strength": 15,      # 短期趋势
        "auction_momentum": 35,    # 竞价承接
    }
    # 风险扣分上限
    MAX_RISK_DEDUCTION = 30

    @classmethod
    def score_level(cls, score: float) -> str:
        if score >= 85:
            return "A+"
        elif score >= 75:
            return "A"
        elif score >= 65:
            return "B+"
        elif score >= 55:
            return "B"
        elif score >= 45:
            return "C"
        else:
            return "D"

    @classmethod
    def score_limit_up_gene(
        cls,
        limit_up_count: Optional[int],
        seal_rate: Optional[float],
    ) -> tuple:  # (score, reasons)
        """涨停基因评分 (25分)"""
        score = 0
        reasons = []

        if limit_up_count is not None:
            if limit_up_count >= 10:
                score += 15
                reasons.append(f"涨停基因强: 100日内涨停{limit_up_count}次(≥10)")
            elif limit_up_count >= 5:
                score += 10
                reasons.append(f"涨停基因较好: 100日内涨停{limit_up_count}次")
            else:
                score += 5
                reasons.append(f"涨停基因一般: 100日内涨停{limit_up_count}次")

        if seal_rate is not None:
            if seal_rate >= 95:
                score += 10
                reasons.append(f"封板可靠性高: 封板率{seal_rate:.1f}%(≥95%)")
            elif seal_rate >= 85:
                score += 7
                reasons.append(f"封板率较好: {seal_rate:.1f}%")
            elif seal_rate >= 70:
                score += 4
                reasons.append(f"封板率一般: {seal_rate:.1f}%")
            else:
                score += 1
                reasons.append(f"封板率偏低: {seal_rate:.1f}%")

        return score, reasons

    @classmethod
    def score_seal_reliability(
        cls,
        limit_up_count: Optional[int],
        touch_days: Optional[int],
        seal_rate: Optional[float],
    ) -> tuple:
        """封板可靠性评分 (25分)"""
        score = 0
        reasons = []

        if touch_days is not None and limit_up_count is not None:
            ratio = limit_up_count / touch_days if touch_days > 0 else 0.0
            if ratio >= 0.9:
                score += 15
                reasons.append(f"触板封板率高: {ratio:.0%}")
            elif ratio >= 0.7:
                score += 10
                reasons.append(f"触板封板率较好: {ratio:.0%}")
            else:
                score += 5
                reasons.append(f"触板封板率一般: {ratio:.0%}")
        elif limit_up_count is not None:
            score += 8

        if seal_rate is not None:
            if seal_rate >= 90:
                score += 10
            elif seal_rate >= 80:
                score += 7
            elif seal_rate >= 60:
                score += 4
            else:
                score += 1

        return score, reasons

    @classmethod
    def score_trend_strength(
        cls,
        rise_10d_pct: Optional[float],
        pre_change_pct: Optional[float],
    ) -> tuple:
        """短期趋势评分 (15分)"""
        score = 0
        reasons = []

        if rise_10d_pct is not None:
            if rise_10d_pct >= 20:
                score += 8
                reasons.append(f"短期趋势强: 10日涨幅{rise_10d_pct:.1f}%")
            elif rise_10d_pct >= 10:
                score += 6
                reasons.append(f"短期趋势较好: 10日涨幅{rise_10d_pct:.1f}%")
            elif rise_10d_pct >= 5:
                score += 4
                reasons.append(f"短期趋势温和: 10日涨幅{rise_10d_pct:.1f}%")
            elif rise_10d_pct > 0:
                score += 2
                reasons.append(f"短期趋势偏弱: 10日涨幅{rise_10d_pct:.1f}%")
            else:
                reasons.append(f"短期趋势走弱: 10日涨幅{rise_10d_pct:.1f}%")

        if pre_change_pct is not None:
            if pre_change_pct >= 9:
                score += 7
                reasons.append(f"昨日强势涨停: {pre_change_pct:.1f}%")
            elif pre_change_pct >= 5:
                score += 5
                reasons.append(f"昨日大涨: {pre_change_pct:.1f}%")
            elif pre_change_pct >= 2:
                score += 3
                reasons.append(f"昨日上涨: {pre_change_pct:.1f}%")
            elif pre_change_pct < -5:
                reasons.append(f"昨日大跌: {pre_change_pct:.1f}%")

        return min(score, 15), reasons

    @classmethod
    def score_auction_momentum(
        cls,
        auction_ratio: Optional[float],
        auction_turnover_rate: Optional[float],
        open_change_pct: Optional[float],
    ) -> tuple:
        """竞价承接评分 (35分)"""
        score = 0
        reasons = []

        if auction_ratio is not None:
            if auction_ratio >= 20:
                score += 15
                reasons.append(f"竞昨比极高: {auction_ratio:.2f}%(资金抢筹)")
            elif auction_ratio >= 10:
                score += 12
                reasons.append(f"竞昨比较高: {auction_ratio:.2f}%")
            elif auction_ratio >= 5:
                score += 8
                reasons.append(f"竞昨比适中: {auction_ratio:.2f}%")
            elif auction_ratio >= 3:
                score += 5
                reasons.append(f"竞昨比较低: {auction_ratio:.2f}%")
            else:
                score += 2
                reasons.append(f"竞昨比偏低: {auction_ratio:.2f}%")

        if auction_turnover_rate is not None:
            if auction_turnover_rate >= 3:
                score += 12
                reasons.append(f"竞价换手率高: {auction_turnover_rate:.2f}%")
            elif auction_turnover_rate >= 1.5:
                score += 9
                reasons.append(f"竞价换手率适中: {auction_turnover_rate:.2f}%")
            elif auction_turnover_rate >= 0.5:
                score += 5
                reasons.append(f"竞价换手率一般: {auction_turnover_rate:.2f}%")
            else:
                score += 2
                reasons.append(f"竞价换手率低: {auction_turnover_rate:.2f}%")

        if open_change_pct is not None:
            if -1 <= open_change_pct <= 2:
                score += 8
                reasons.append(f"开盘温和: {open_change_pct:.2f}%(利于承接)")
            elif open_change_pct > 5:
                score += 4
                reasons.append(f"开盘涨幅较大: {open_change_pct:.2f}%")
            elif open_change_pct > 2:
                score += 6
                reasons.append(f"开盘小幅走高: {open_change_pct:.2f}%")
            elif open_change_pct < -3:
                score -= 5
                reasons.append(f"开盘跌幅较大: {open_change_pct:.2f}%(风险)")
            else:
                score += 2

        return max(0, min(score, 35)), reasons

    @classmethod
    def score_risk(
        cls,
        open_change_pct: Optional[float] = None,
        circ_mv: Optional[float] = None,
        **kwargs,
    ) -> tuple:
        """风险扣分 (扣分项, 上限30分)"""
        deduction = 0
        risk_tags = []

        if open_change_pct is not None:
            if open_change_pct < -5:
                deduction += 15
                risk_tags.append("开盘暴跌")
            elif open_change_pct < -3:
                deduction += 8
                risk_tags.append("开盘大幅低开")

        if circ_mv is not None:
            if circ_mv > 1000:
                deduction += 5
                risk_tags.append("大盘股")
            elif circ_mv > 500:
                deduction += 2

        return min(deduction, cls.MAX_RISK_DEDUCTION), risk_tags

    @classmethod
    def calculate(
        cls,
        limit_up_count: Optional[int] = None,
        touch_days: Optional[int] = None,
        limit_up_days: Optional[int] = None,
        seal_rate: Optional[float] = None,
        rise_10d_pct: Optional[float] = None,
        pre_change_pct: Optional[float] = None,
        open_change_pct: Optional[float] = None,
        auction_ratio: Optional[float] = None,
        auction_turnover_rate: Optional[float] = None,
        circ_mv: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        计算五维规则评分

        Returns:
            {
                "rule_score": float,  # 最终评分(0-100)
                "score_level": str,   # A+/A/B+/B/C/D
                "score_breakdown": {},  # 各维度得分
                "reasons": [],        # 入选原因列表
                "risk_tags": [],      # 风险标签列表
                "risk_deduction": int, # 风险扣分
            }
        """
        breakdown = {}

        # 涨停基因
        limit_up_score, limit_up_reasons = cls.score_limit_up_gene(limit_up_count, seal_rate)
        breakdown["limit_up_gene"] = {"score": limit_up_score, "max": 25, "reasons": limit_up_reasons}

        # 封板可靠性
        seal_score, seal_reasons = cls.score_seal_reliability(limit_up_count, touch_days, seal_rate)
        breakdown["seal_reliability"] = {"score": seal_score, "max": 25, "reasons": seal_reasons}

        # 短期趋势
        trend_score, trend_reasons = cls.score_trend_strength(rise_10d_pct, pre_change_pct)
        breakdown["trend_strength"] = {"score": trend_score, "max": 15, "reasons": trend_reasons}

        # 竞价承接
        auction_score, auction_reasons = cls.score_auction_momentum(auction_ratio, auction_turnover_rate, open_change_pct)
        breakdown["auction_momentum"] = {"score": auction_score, "max": 35, "reasons": auction_reasons}

        # 风险扣分
        risk_deduction, risk_tags = cls.score_risk(open_change_pct, circ_mv)
        breakdown["risk_deduction"] = {"score": risk_deduction, "max": cls.MAX_RISK_DEDUCTION}

        # 总分 = 各维度得分之和 - 风险扣分
        raw_score = limit_up_score + seal_score + trend_score + auction_score
        rule_score = max(0, raw_score - risk_deduction)

        # 收集原因和风险标签
        all_reasons = []
        for dim in ["limit_up_gene", "seal_reliability", "trend_strength", "auction_momentum"]:
            all_reasons.extend(breakdown[dim].get("reasons", []))

        score_lvl = cls.score_level(rule_score)

        return {
            "rule_score": round(rule_score, 2),
            "score_level": score_lvl,
            "score_breakdown": breakdown,
            "reasons": all_reasons[:8],
            "risk_tags": risk_tags,
            "risk_deduction": risk_deduction,
        }
