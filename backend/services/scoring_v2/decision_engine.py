"""
决策引擎 - 根据评分输出操作建议
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class DecisionEngine:

    @classmethod
    def decide(
        cls,
        final_score: float,
        alpha_score: float,
        risk_score: float,
        risk_flags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        grade = FinalScoreHelper.to_grade(final_score)
        risk_level = RiskLevelHelper.to_level(risk_score)

        # 默认值
        action_level = "观察"
        position_suggestion = "不主动买入"
        entry_suggestion = "观望"
        stop_loss_suggestion = ""
        take_profit_suggestion = ""
        warnings = list(risk_flags or [])

        if risk_score >= 80:
            action_level = "剔除"
            position_suggestion = "不参与"
            entry_suggestion = "风险过高，不参与"
            warnings.append("风险评分≥80，建议剔除")
        elif final_score >= 85 and risk_score <= 30:
            action_level = "可小仓试错"
            position_suggestion = "10%-15% 观察仓"
            entry_suggestion = "竞价后观察3-5分钟确认承接"
            stop_loss_suggestion = "跌破开盘价3%或分时均线离场"
            take_profit_suggestion = "冲高4%-6%分批止盈"
        elif final_score >= 75 and risk_score <= 40:
            action_level = "重点观察"
            position_suggestion = "5%-10% 试错仓"
            entry_suggestion = "开盘后确认承接再考虑"
            stop_loss_suggestion = "跌破入场价3%离场"
            take_profit_suggestion = "冲高4%以上分批止盈"
        elif alpha_score >= 80 and risk_score > 60:
            action_level = "只看不买"
            position_suggestion = "不参与"
            entry_suggestion = "Alpha分高但风险大，等待分歧后观察"
            warnings.append("Alpha分高但风险较大，不宜追高")
        elif final_score >= 65:
            action_level = "谨慎观察"
            position_suggestion = "≤5% 小仓"
            entry_suggestion = "确认板块强度和承接后再决定"
            stop_loss_suggestion = "跌破入场价3%离场"
        elif risk_score > 60:
            action_level = "高危险"
            position_suggestion = "不参与"
            entry_suggestion = "风险偏高，建议回避"
            warnings.append("风险评分较高，谨慎")
        elif final_score < 50:
            action_level = "不关注"
            position_suggestion = "不参与"

        return {
            "action_level": action_level,
            "position_suggestion": position_suggestion,
            "entry_suggestion": entry_suggestion,
            "stop_loss_suggestion": stop_loss_suggestion,
            "take_profit_suggestion": take_profit_suggestion,
            "warnings": warnings,
        }


class FinalScoreHelper:
    @staticmethod
    def to_grade(final_score: float) -> str:
        if final_score >= 85:
            return "S"
        elif final_score >= 75:
            return "A"
        elif final_score >= 65:
            return "B"
        elif final_score >= 50:
            return "C"
        return "D"


class RiskLevelHelper:
    @staticmethod
    def to_level(risk_score: float) -> str:
        if risk_score <= 20:
            return "低风险"
        elif risk_score <= 40:
            return "中低风险"
        elif risk_score <= 60:
            return "中高风险"
        elif risk_score <= 80:
            return "高风险"
        return "极高风险"
