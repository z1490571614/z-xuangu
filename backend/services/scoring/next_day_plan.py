"""
次日预案服务 - 基于竞价数据生成次日观察要点
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class NextDayPlanService:

    @classmethod
    def generate(
        cls,
        open_change_pct: Optional[float] = None,
        auction_ratio: Optional[float] = None,
        auction_turnover_rate: Optional[float] = None,
        pre_change_pct: Optional[float] = None,
        seal_rate: Optional[float] = None,
        limit_up_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        plan = {
            "key_observations": [],
            "open_scenario": "",
            "risk_reminder": "",
            "key_factors": {},
        }

        # 开盘情景
        if open_change_pct is not None:
            if open_change_pct > 5:
                plan["open_scenario"] = "大幅高开，注意观察能否快速封板"
                plan["key_observations"].append("高开>5%，关注开盘后5分钟内是否能封板")
                if pre_change_pct is not None and pre_change_pct > 9:
                    plan["key_observations"].append("前一交易日涨停，今日高开，可能走加速")
            elif open_change_pct > 2:
                plan["open_scenario"] = "小幅高开，关注竞价量能配合"
                plan["key_observations"].append(f"高开{open_change_pct:.1f}%，关注量比是否>2")
            elif open_change_pct > -1:
                plan["open_scenario"] = "平开或微幅波动，观察承接力度"
                plan["key_observations"].append("平开附近，关注开盘后30分钟内走势方向")
            elif open_change_pct > -3:
                plan["open_scenario"] = "低开，观察能否快速回升"
                plan["key_observations"].append(f"低开{open_change_pct:.1f}%，关注开盘15分钟内能否翻红")
            else:
                plan["open_scenario"] = "大幅低开，注意风险"
                plan["key_observations"].append(f"大幅低开{open_change_pct:.1f}%，建议谨慎观望")

        # 竞价量能
        if auction_ratio is not None and auction_turnover_rate is not None:
            if auction_ratio > 15 and auction_turnover_rate > 2:
                plan["key_observations"].append("竞价量能充沛，资金抢筹意愿强")
                plan["key_factors"]["auction_quality"] = "强"
            elif auction_ratio > 8:
                plan["key_observations"].append("竞价量能一般，关注开盘后量能持续性")
                plan["key_factors"]["auction_quality"] = "中"
            else:
                plan["key_observations"].append("竞价量能偏弱，需观察开盘后资金动向")
                plan["key_factors"]["auction_quality"] = "弱"

        # 风险提示
        risk_notes = []
        if open_change_pct is not None and open_change_pct < -3:
            risk_notes.append("开盘跌幅较大，风险较高")
        if seal_rate is not None and seal_rate < 60:
            risk_notes.append("历史封板率较低，追高需谨慎")
        if risk_notes:
            plan["risk_reminder"] = "; ".join(risk_notes)
        else:
            plan["risk_reminder"] = "无明显异常信号"

        plan["key_factors"]["open_change_pct"] = open_change_pct
        plan["key_factors"]["auction_ratio"] = auction_ratio
        plan["key_factors"]["auction_turnover_rate"] = auction_turnover_rate
        plan["key_factors"]["pre_change_pct"] = pre_change_pct
        plan["key_factors"]["seal_rate"] = seal_rate
        plan["key_factors"]["limit_up_count"] = limit_up_count

        return plan
