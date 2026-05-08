"""
开盘预案服务 — 围绕当天9:30后交易场景
不依赖LightGBM, 不实时调用AI, 评分完成后即时生成
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class OpeningPlanService:
    """开盘预案服务"""

    @classmethod
    def generate(
        cls,
        open_change_pct: Optional[float] = None,
        auction_ratio: Optional[float] = None,
        auction_turnover_rate: Optional[float] = None,
        pre_change_pct: Optional[float] = None,
        seal_rate: Optional[float] = None,
        limit_up_count: Optional[int] = None,
        final_score: Optional[float] = None,
        risk_score: Optional[float] = None,
        action_level: str = "",
        position_suggestion: str = "",
    ) -> Dict[str, Any]:
        plan = {
            "general_plan": cls._general_plan(open_change_pct, auction_ratio, pre_change_pct),
            "action_level": action_level or "观察",
            "position_suggestion": position_suggestion or "不主动买入",
            "data_status": "available",
            "generated_at": datetime.now().strftime("%H:%M"),
            "opening_scenarios": cls._build_scenarios(open_change_pct, auction_ratio, auction_turnover_rate),
            "watch_points": cls._build_watch_points(open_change_pct, auction_ratio, auction_turnover_rate, pre_change_pct),
            "cancel_conditions": cls._build_cancel_conditions(open_change_pct, risk_score),
            "stop_loss": cls._build_stop_loss(open_change_pct),
            "take_profit": cls._build_take_profit(pre_change_pct),
            "risk_warnings": cls._build_risk_warnings(open_change_pct, risk_score, seal_rate, limit_up_count),
        }
        return plan

    @classmethod
    def _general_plan(cls, open_change: Optional[float], auction_ratio: Optional[float], pre_change: Optional[float]) -> str:
        if open_change is None:
            return "暂无竞价数据，无法生成开盘预案"
        if open_change > 5:
            if auction_ratio is not None and auction_ratio >= 15:
                return "高开且竞价抢筹明显，关注开盘后是否放量上攻或冲高回落"
            return f"高开{open_change:.1f}%，关注开盘后成交量能否持续，警惕高开低走"
        elif open_change > 2:
            return f"小幅高开{open_change:.1f}%，观察9:30-9:35成交量变化，确认承接"
        elif open_change > -1:
            return "平开附近，观察开盘后方向选择，确认板块带动"
        elif open_change >= -3:
            return f"低开{open_change:.1f}%，观察开盘15分钟内能否快速翻红，若持续走弱则取消"
        else:
            return f"大幅低开{open_change:.1f}%，风险较高，原则上不参与"

    @classmethod
    def _build_scenarios(cls, open_change: Optional[float], auction_ratio: Optional[float], auction_turnover: Optional[float]) -> list:
        scenarios = []
        if open_change is not None:
            scenarios.append({
                "name": "高开强承接",
                "condition": f"开盘{open_change:.1f}%且竞价承接良好",
                "action": "可纳入重点观察，但不追高",
                "probability": "medium" if open_change > 3 else "low",
            })
            scenarios.append({
                "name": "高开低走",
                "condition": "开盘后5分钟内放量下杀",
                "action": "取消参与，不接飞刀",
                "probability": "medium",
            })
            scenarios.append({
                "name": "平开震荡",
                "condition": "开盘后横盘整理，等待方向",
                "action": "等待突破确认后再决定",
                "probability": "medium",
            })
            scenarios.append({
                "name": "低开走弱",
                "condition": "开盘后继续走低，无支撑",
                "action": "不参与，等待下一交易日",
                "probability": "low" if open_change > -2 else "medium",
            })
        return scenarios

    @classmethod
    def _build_watch_points(cls, open_change, auction_ratio, auction_turnover, pre_change) -> list:
        points = []
        points.append("观察9:30-9:35的成交量变化方向")
        points.append("关注板块前排个股走势是否同步")
        if auction_ratio is not None:
            if auction_ratio >= 15:
                points.append("竞价抢筹明显，关注是否出现高开低走出货")
            elif auction_ratio < 5:
                points.append("竞价量能偏弱，需等待开盘后放量确认")
        if auction_turnover is not None and auction_turnover >= 3:
            points.append("竞价换手偏高，注意是否有分歧出货迹象")
        points.append("观察分时均价线是否站稳，跌破分时均价应警惕")
        return points

    @classmethod
    def _build_cancel_conditions(cls, open_change, risk_score) -> list:
        conditions = [
            "今日开盘后5分钟放量下杀超过3%，取消参与计划",
            "板块前排个股走弱或板块整体转弱，取消参与",
            "分时均价线被有效跌破且不收回，取消参与",
        ]
        if risk_score is not None and risk_score >= 60:
            conditions.append("风险评分偏高，原则上只观察不参与")
        if open_change is not None and open_change < -3:
            conditions.append("低开超过3%且迟迟不回升，取消参与")
        return conditions

    @classmethod
    def _build_stop_loss(cls, open_change) -> str:
        if open_change is not None and open_change > 5:
            return "如买入，止损设为入场价下方3%或分时均价线破位"
        return "止损设为入场价下方3%"

    @classmethod
    def _build_take_profit(cls, pre_change) -> str:
        return "冲高4%-6%可分批止盈，连板则继续持有但提高止盈到3%"

    @classmethod
    def _build_risk_warnings(cls, open_change, risk_score, seal_rate, limit_up_count) -> list:
        warnings = []
        warnings.append("本预案仅基于竞价数据生成，实际交易需结合开盘后实时走势判断")
        if risk_score is not None and risk_score >= 50:
            warnings.append(f"当前风险评分{risk_score:.0f}，处于中高区间，需谨慎")
        if seal_rate is not None and seal_rate < 75:
            warnings.append("历史封板率偏低，追高风险较大")
        if open_change is not None and open_change < -3:
            warnings.append("开盘大幅低开，存在不可预知利空风险")
        return warnings
