"""
风险评分服务 V2 — 八维下行风险 (满分100, 越高越危险)
每个维度: name/score/max_score/metrics/reason/data_status
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RiskScoreService:
    """风险评分服务：评价股票下行风险"""

    MAX_RISK = {
        "high_position": 20,
        "historical_drawdown": 18,
        "open_board_failure": 15,
        "liquidity": 15,
        "market_env": 15,
        "event_missing": 10,
        "financial_news": 12,
        "volatility": 5,
    }

    @classmethod
    def calculate(
        cls,
        rise_10d_pct: Optional[float] = None,
        pre_change_pct: Optional[float] = None,
        open_change_pct: Optional[float] = None,
        seal_rate: Optional[float] = None,
        limit_up_count: Optional[int] = None,
        limit_up_days: Optional[int] = None,
        touch_days: Optional[int] = None,
        auction_ratio: Optional[float] = None,
        auction_turnover_rate: Optional[float] = None,
        circ_mv: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        items = []
        risk_flags = []

        # 1. 高位风险 (20)
        hp_score, hp_metrics, hp_reason = cls._score_high_position(rise_10d_pct, pre_change_pct)
        items.append(cls._item("高位风险", hp_score, 20, hp_metrics, hp_reason, "available"))
        if hp_score >= 15:
            risk_flags.append("短期涨幅过大")
        elif hp_score >= 8:
            risk_flags.append("短期涨幅偏大")

        # 2. 历史回撤风险 (18)
        hd_score, hd_metrics, hd_reason = cls._score_historical_drawdown(rise_10d_pct, seal_rate,
                                                                         limit_up_count, touch_days, limit_up_days)
        items.append(cls._item("历史回撤风险", hd_score, 18, hd_metrics, hd_reason, "available"))
        if hd_score >= 10:
            risk_flags.append("历史回撤风险偏高")

        # 3. 炸板/失败风险 (15)
        ob_score, ob_metrics, ob_reason = cls._score_open_board(seal_rate, limit_up_days, touch_days)
        items.append(cls._item("炸板/失败风险", ob_score, 15, ob_metrics, ob_reason, "available"))
        if ob_score >= 10:
            risk_flags.append("炸板/封板失败风险")

        # 4. 流动性风险 (15)
        liq_score, liq_metrics, liq_reason = cls._score_liquidity(auction_turnover_rate, circ_mv, auction_ratio)
        items.append(cls._item("流动性风险", liq_score, 15, liq_metrics, liq_reason, "available"))

        # 5. 市场环境风险 (15)
        me_score, me_metrics, me_reason = cls._score_market_env()
        items.append(cls._item("市场环境风险", me_score, 15, me_metrics, me_reason, "partial"))

        # 6. 事件缺失风险 (10)
        em_score, em_metrics, em_reason = cls._score_event_missing(open_change_pct, pre_change_pct)
        items.append(cls._item("事件缺失风险", em_score, 10, em_metrics, em_reason, "available"))

        # 7. 财务/公告风险 (12)
        fn_score, fn_metrics, fn_reason = cls._score_financial()
        items.append(cls._item("财务/公告风险", fn_score, 12, fn_metrics, fn_reason, "not_integrated"))
        if fn_score > 0:
            risk_flags.append("财务数据未接入")

        # 8. 波动风险 (5)
        vol_score, vol_metrics, vol_reason = cls._score_volatility(rise_10d_pct, pre_change_pct)
        items.append(cls._item("波动风险", vol_score, 5, vol_metrics, vol_reason, "available"))

        total = sum(it["score"] for it in items)

        return {
            "total_score": round(total, 2),
            "risk_level": cls._to_level(total),
            "data_status": "available",
            "items": items,
            "risk_flags": risk_flags[:6],
        }

    @staticmethod
    def _item(name: str, score: float, max_s: int, metrics: dict, reason: str, status: str) -> dict:
        return {
            "name": name,
            "score": round(score, 2),
            "max_score": max_s,
            "metrics": metrics or {},
            "reason": reason or "数据有限",
            "data_status": status,
        }

    @staticmethod
    def _to_level(score: float) -> str:
        if score <= 20: return "偏低"
        if score <= 40: return "中等偏低"
        if score <= 60: return "中等偏高"
        if score <= 80: return "偏高"
        return "极高"

    # ── 维度1：高位风险 ──
    @classmethod
    def _score_high_position(cls, rise_10d: Optional[float], pre_change: Optional[float]) -> tuple:
        score = 0
        metrics = {
            "pct_chg_10d": f"{rise_10d:.1f}%" if rise_10d is not None else None,
            "pre_change_pct": f"{pre_change:.1f}%" if pre_change is not None else None,
        }
        reason_parts = []
        if rise_10d is not None:
            if rise_10d > 45:
                score += 20
                reason_parts.append(f"近10日涨幅{rise_10d:.1f}%，短期累积风险极高")
            elif rise_10d > 30:
                score += 15
                reason_parts.append(f"近10日涨幅{rise_10d:.1f}%，存在较大兑现压力")
            elif rise_10d > 20:
                score += 8
                reason_parts.append(f"近10日涨幅{rise_10d:.1f}%，短期偏热")
            elif rise_10d > 10:
                score += 4
                reason_parts.append(f"短期涨幅适中")
            else:
                reason_parts.append(f"短期涨幅温和，高位风险较低")
        if pre_change is not None and pre_change > 9.5:
            score += 2
            metrics["pre_change_pct"] = f"{pre_change:.1f}%"
            reason_parts.append("前日涨停，存在连板失败风险")
        return min(score, 20), metrics, "；".join(reason_parts) if reason_parts else "暂无高位风险数据"

    # ── 维度2：历史回撤风险 ──
    @classmethod
    def _score_historical_drawdown(cls, rise_10d: Optional[float], seal_rate: Optional[float],
                                   limit_up: Optional[int], touch_days: Optional[int],
                                   limit_up_days: Optional[int]) -> tuple:
        score = 4
        metrics = {}
        parts = []
        if rise_10d is not None:
            if rise_10d > 30:
                score += 10
                metrics["pct_chg_10d"] = f"{rise_10d:.1f}%"
                parts.append(f"近10日涨幅{rise_10d:.1f}%，短期回撤风险上升")
            elif rise_10d > 15:
                score += 4
                metrics["pct_chg_10d"] = f"{rise_10d:.1f}%"
                parts.append(f"近10日涨幅{rise_10d:.1f}%，回撤风险中等")
            else:
                parts.append("短期回撤风险较低")

        if seal_rate is not None and seal_rate < 70:
            score += 6
            metrics["seal_rate"] = f"{seal_rate:.1f}%"
            parts.append(f"封板率{seal_rate:.1f}%，成功封板概率偏低")
        elif seal_rate is not None:
            metrics["seal_rate"] = f"{seal_rate:.1f}%"

        if touch_days is not None and limit_up_days is not None and touch_days > 0:
            ratio = limit_up_days / touch_days
            metrics["touch_seal_ratio"] = f"{ratio:.0%}"
            if ratio < 0.5:
                score += 4
                parts.append(f"触板封板比{ratio:.0%}，封板成功率偏低")

        return min(score, 18), metrics, "；".join(parts)

    # ── 维度3：炸板/失败风险 ──
    @classmethod
    def _score_open_board(cls, seal_rate: Optional[float], limit_up_days: Optional[int],
                          touch_days: Optional[int]) -> tuple:
        score = 0
        metrics = {}
        parts = []
        if seal_rate is not None:
            metrics["seal_rate"] = f"{seal_rate:.1f}%"
            if seal_rate < 60:
                score += 10
                parts.append(f"封板率仅{seal_rate:.1f}%，炸板风险高")
            elif seal_rate < 75:
                score += 6
                parts.append(f"封板率{seal_rate:.1f}%，存在炸板风险")
            elif seal_rate < 85:
                score += 3
                parts.append(f"封板率{seal_rate:.1f}%，略低于优选区间")
            else:
                parts.append("封板率较高")
        if touch_days is not None and touch_days > 0 and limit_up_days is not None:
            gap = touch_days - limit_up_days
            metrics["open_board_gap"] = gap
            if gap >= 5:
                score += 5
                parts.append(f"触板与封板差{gap}次，多次封板失败")
            elif gap >= 2:
                score += 2
        if not metrics:
            return 0, {}, "无封板数据"
        return min(score, 15), metrics, "；".join(parts)

    # ── 维度4：流动性风险 ──
    @classmethod
    def _score_liquidity(cls, auction_turnover: Optional[float], circ_mv: Optional[float],
                         auction_ratio: Optional[float]) -> tuple:
        score = 0
        metrics = {}
        parts = []
        if auction_turnover is not None:
            metrics["auction_turnover_rate"] = f"{auction_turnover:.2f}%"
            if auction_turnover < 0.3:
                score += 8
                parts.append(f"竞价换手率仅{auction_turnover:.2f}%，承接不足")
            elif auction_turnover < 0.5:
                score += 3
                parts.append(f"竞价换手率{auction_turnover:.2f}%，偏低")
            else:
                parts.append("竞价换手正常")
        if auction_ratio is not None:
            metrics["auction_ratio"] = f"{auction_ratio:.1f}%"
            if auction_ratio < 3:
                score += 5
                parts.append(f"竞昨比{auction_ratio:.1f}%过低")
        if circ_mv is not None:
            metrics["circ_mv"] = f"{circ_mv:.0f}亿"
            if circ_mv < 10:
                score += 3
                parts.append("市值过小，流动性受限")
        if not parts:
            return 2, {}, "流动性正常"
        return min(score, 15), metrics, "；".join(parts)

    # ── 维度5：市场环境风险 ──
    @classmethod
    def _score_market_env(cls) -> tuple:
        return 4, {"data_source": "static_reference"}, "市场环境参考值（后续接入实时数据）"

    # ── 维度6：事件缺失风险 ──
    @classmethod
    def _score_event_missing(cls, open_change: Optional[float], pre_change: Optional[float]) -> tuple:
        score = 3
        metrics = {}
        parts = ["未匹配到明确基本面催化，仅行情异动"]
        if open_change is not None and open_change > 5:
            score += 4
            metrics["open_change_pct"] = f"{open_change:.1f}%"
            parts.append(f"高开{open_change:.1f}%但缺少催化支撑")
        elif open_change is not None and open_change < -3:
            score += 3
            parts.append(f"低开{open_change:.1f}%，需关注原因")
        return min(score, 10), metrics, "；".join(parts)

    # ── 维度7：财务/公告风险 ──
    @classmethod
    def _score_financial(cls) -> tuple:
        return 0, {}, "财务/公告数据暂未接入（not_integrated）"

    # ── 维度8：波动风险 ──
    @classmethod
    def _score_volatility(cls, rise_10d: Optional[float], pre_change: Optional[float]) -> tuple:
        score = 1
        metrics = {}
        parts = []
        if rise_10d is not None and abs(rise_10d) > 40:
            score += 3
            metrics["pct_chg_10d"] = f"{rise_10d:.1f}%"
            parts.append(f"10日波动{rise_10d:.1f}%偏高")
        else:
            parts.append("波动率正常")
        if pre_change is not None and abs(pre_change) > 7:
            score += 1
            metrics["pre_change_pct"] = f"{pre_change:.1f}%"
        return min(score, 5), metrics, "；".join(parts)
