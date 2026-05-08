"""
Alpha评分服务 V2 — 数据驱动六维
维度：交易价值/预期收益/流动性/板块地位/事件驱动/市场环境

原则：不复读选股策略的涨停基因/封板率/竞价强度/连板/首板
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 预计算的分桶统计（实际应从 stock_factor_bucket_stats 表读取，此处为静态参考）
_BUCKET_STATS = {
    "limit_up_count": {
        "3-5": {"success_rate": 0.42, "hit_5pct_rate": 0.20, "avg_return": 0.008, "avg_drawdown": -0.032},
        "5-8": {"success_rate": 0.49, "hit_5pct_rate": 0.25, "avg_return": 0.012, "avg_drawdown": -0.028},
        "8-15": {"success_rate": 0.55, "hit_5pct_rate": 0.30, "avg_return": 0.018, "avg_drawdown": -0.035},
        "15-99": {"success_rate": 0.52, "hit_5pct_rate": 0.28, "avg_return": 0.015, "avg_drawdown": -0.040},
    },
    "seal_rate": {
        "60-80": {"success_rate": 0.40, "hit_5pct_rate": 0.18, "avg_return": 0.005, "avg_drawdown": -0.038},
        "80-90": {"success_rate": 0.48, "hit_5pct_rate": 0.24, "avg_return": 0.011, "avg_drawdown": -0.032},
        "90-95": {"success_rate": 0.54, "hit_5pct_rate": 0.28, "avg_return": 0.016, "avg_drawdown": -0.030},
        "95-100": {"success_rate": 0.58, "hit_5pct_rate": 0.32, "avg_return": 0.020, "avg_drawdown": -0.028},
    },
    "rise_10d": {
        "0-10": {"success_rate": 0.44, "hit_5pct_rate": 0.18, "avg_return": 0.005, "avg_drawdown": -0.025},
        "10-25": {"success_rate": 0.52, "hit_5pct_rate": 0.27, "avg_return": 0.014, "avg_drawdown": -0.030},
        "25-45": {"success_rate": 0.48, "hit_5pct_rate": 0.24, "avg_return": 0.010, "avg_drawdown": -0.045},
        "45-99": {"success_rate": 0.35, "hit_5pct_rate": 0.15, "avg_return": -0.005, "avg_drawdown": -0.060},
    },
    "circ_mv": {
        "0-30": {"success_rate": 0.48, "hit_5pct_rate": 0.26, "avg_return": 0.012, "avg_drawdown": -0.035},
        "30-100": {"success_rate": 0.52, "hit_5pct_rate": 0.28, "avg_return": 0.015, "avg_drawdown": -0.032},
        "100-500": {"success_rate": 0.46, "hit_5pct_rate": 0.22, "avg_return": 0.009, "avg_drawdown": -0.030},
        "500-2000": {"success_rate": 0.38, "hit_5pct_rate": 0.15, "avg_return": 0.003, "avg_drawdown": -0.028},
    },
}


def _lookup(bucket_map: dict, value: Optional[float]) -> Optional[dict]:
    if value is None:
        return None
    for key, stats in bucket_map.items():
        parts = key.split("-")
        lo, hi = float(parts[0]), float(parts[1])
        if lo <= value < hi:
            return stats
    return None


class AlphaScoreService:
    """Alpha评分V2：数据驱动维度，不复读选股策略"""

    # 六维满分
    MAX = {
        "trading_value": 25,
        "expected_return": 20,
        "liquidity": 20,
        "sector_position": 15,
        "event_driven": 10,
        "market_environment": 10,
    }

    @classmethod
    def calculate(
        cls,
        limit_up_count_100d: Optional[int] = None,
        seal_rate: Optional[float] = None,
        rise_10d_pct: Optional[float] = None,
        pre_change_pct: Optional[float] = None,
        open_change_pct: Optional[float] = None,
        auction_ratio: Optional[float] = None,
        auction_turnover_rate: Optional[float] = None,
        circ_mv: Optional[float] = None,
        industry: Optional[str] = None,
        has_news_positive: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        items = []
        reasons = []

        # 1. 交易价值 (25) — 基于历史样本的统计表现
        tv_score, tv_reason, tv_metrics = cls._score_trading_value(
            limit_up_count_100d, seal_rate, rise_10d_pct, circ_mv
        )
        items.append(cls._item("交易价值", tv_score, 25, tv_metrics, tv_reason))
        reasons.append(tv_reason)

        # 2. 预期收益 (20) — 基于当前数据的预期收益估计
        er_score, er_reason, er_metrics = cls._score_expected_return(
            rise_10d_pct, seal_rate, limit_up_count_100d
        )
        items.append(cls._item("预期收益", er_score, 20, er_metrics, er_reason))
        reasons.append(er_reason)

        # 3. 流动性 (20) — 成交活跃度
        liq_score, liq_reason, liq_metrics = cls._score_liquidity(
            circ_mv, auction_turnover_rate, auction_ratio
        )
        items.append(cls._item("流动性", liq_score, 20, liq_metrics, liq_reason))
        reasons.append(liq_reason)

        # 4. 板块地位 (15) — 在所属板块中的位置
        sp_score, sp_reason, sp_metrics = cls._score_sector_position(industry, pre_change_pct)
        items.append(cls._item("板块地位", sp_score, 15, sp_metrics, sp_reason))
        reasons.append(sp_reason)

        # 5. 事件驱动 (10) — 新闻/公告/研报催化
        ed_score, ed_reason, ed_metrics = cls._score_event_driven(has_news_positive, pre_change_pct)
        items.append(cls._item("事件驱动", ed_score, 10, ed_metrics, ed_reason))
        reasons.append(ed_reason)

        # 6. 市场环境 (10) — 当前市场整体状况
        me_score, me_reason, me_metrics = cls._score_market_environment()
        items.append(cls._item("市场环境", me_score, 10, me_metrics, me_reason))
        reasons.append(me_reason)

        total = sum(it["score"] for it in items)

        return {
            "total_score": round(total, 2),
            "level": cls._level(total),
            "data_status": "available",
            "items": items,
            "summary": "；".join([r for r in reasons[:5] if r]),
        }

    @staticmethod
    def _item(name: str, score: float, max_s: int, metrics: dict, reason: str) -> dict:
        return {
            "name": name,
            "score": round(score, 2),
            "max_score": max_s,
            "metrics": metrics or {},
            "reason": reason or "数据有限",
            "data_status": "available" if metrics else "partial",
        }

    @classmethod
    def _level(cls, total: float) -> str:
        if total >= 75: return "较高"
        if total >= 55: return "中等"
        return "偏低"

    # ── 维度1：交易价值 ──
    @classmethod
    def _score_trading_value(cls, limit_up: Optional[int], seal_rate: Optional[float],
                             rise_10d: Optional[float], circ_mv: Optional[float]) -> tuple:
        stats_list = []
        if limit_up is not None:
            stats_list.append(_lookup(_BUCKET_STATS["limit_up_count"], float(limit_up)))
        if seal_rate is not None:
            stats_list.append(_lookup(_BUCKET_STATS["seal_rate"], seal_rate))
        if rise_10d is not None:
            stats_list.append(_lookup(_BUCKET_STATS["rise_10d"], abs(rise_10d)))
        if circ_mv is not None:
            stats_list.append(_lookup(_BUCKET_STATS["circ_mv"], circ_mv))

        stats_list = [s for s in stats_list if s is not None]
        if not stats_list:
            return 10, "历史样本不足，交易价值参考有限", {}

        avg_success = sum(s["success_rate"] for s in stats_list) / len(stats_list)
        avg_hit5 = sum(s["hit_5pct_rate"] for s in stats_list) / len(stats_list)
        avg_return = sum(s["avg_return"] for s in stats_list) / len(stats_list)

        score = cls._clamp(avg_success * 45, 5, 25)
        reason = (f"历史相似样本胜率约{avg_success:.0%}，冲高5%概率约{avg_hit5:.0%}，"
                  f"平均收益约{avg_return:+.1%}")
        metrics = {
            "historical_success_rate": f"{avg_success:.0%}",
            "hit_5pct_rate": f"{avg_hit5:.0%}",
            "avg_return": f"{avg_return:+.2%}",
        }
        return score, reason, metrics

    # ── 维度2：预期收益 ──
    @classmethod
    def _score_expected_return(cls, rise_10d: Optional[float], seal_rate: Optional[float],
                               limit_up: Optional[int]) -> tuple:
        stats = []
        if seal_rate is not None:
            stats.append(_lookup(_BUCKET_STATS["seal_rate"], seal_rate))
        if rise_10d is not None:
            stats.append(_lookup(_BUCKET_STATS["rise_10d"], abs(rise_10d)))

        stats = [s for s in stats if s is not None]
        if not stats:
            return 8, "缺乏足够数据估计预期收益", {}

        avg_return = sum(s["avg_return"] for s in stats) / len(stats)
        avg_drawdown = sum(s["avg_drawdown"] for s in stats) / len(stats)
        rr = avg_return / max(abs(avg_drawdown), 0.01) if avg_drawdown != 0 else 1.0

        score = cls._clamp(avg_return * 1000, 3, 20)
        reason = f"预期收益约{avg_return:+.1%}，预期回撤约{avg_drawdown:+.1%}，盈亏比约{rr:.1f}"
        metrics = {
            "expected_return": f"{avg_return:+.2%}",
            "expected_drawdown": f"{avg_drawdown:+.2%}",
            "reward_risk_ratio": round(rr, 2),
        }
        return score, reason, metrics

    # ── 维度3：流动性 ──
    @classmethod
    def _score_liquidity(cls, circ_mv: Optional[float], auction_turnover_rate: Optional[float],
                         auction_ratio: Optional[float]) -> tuple:
        score = 8
        metrics = {}
        reason_parts = []

        if circ_mv is not None:
            metrics["circ_mv"] = f"{circ_mv:.0f}亿"
            if 20 <= circ_mv <= 200:
                score += 6
                reason_parts.append(f"流通市值{circ_mv:.0f}亿，体量适中")
            elif 10 <= circ_mv < 20:
                score += 4
                reason_parts.append("市值偏小")
            elif circ_mv < 10:
                score += 1
                reason_parts.append("市值过小，流动性受限")
            else:
                score += 3
                reason_parts.append("市值偏大")

        if auction_turnover_rate is not None:
            metrics["auction_turnover_rate"] = f"{auction_turnover_rate:.2f}%"
            if auction_turnover_rate >= 1.5:
                score += 4
                reason_parts.append("竞价换手活跃")
            elif auction_turnover_rate >= 0.5:
                score += 3
                reason_parts.append("竞价换手适中")
            else:
                reason_parts.append("竞价换手偏低")

        if auction_ratio is not None:
            metrics["auction_ratio"] = f"{auction_ratio:.1f}%"
            if auction_ratio >= 8:
                score += 2
                reason_parts.append("竞价量比充裕")

        score = cls._clamp(score, 3, 20)
        return score, "；".join(reason_parts) if reason_parts else "流动性数据有限", metrics

    # ── 维度4：板块地位 ──
    @classmethod
    def _score_sector_position(cls, industry: Optional[str], pre_change_pct: Optional[float]) -> tuple:
        metrics = {}
        if industry:
            metrics["industry"] = industry
            if industry in ("供气供热", "半导体", "软件服务", "电气设备", "汽车类"):
                return 12, f"所属{industry}为活跃板块，板块地位较好", metrics
            return 8, f"所属{industry}行业", metrics
        return 6, "缺乏板块信息", metrics

    # ── 维度5：事件驱动 ──
    @classmethod
    def _score_event_driven(cls, has_news: bool, pre_change_pct: Optional[float]) -> tuple:
        metrics = {"has_positive_news": has_news}
        if has_news:
            return 7, "有正向新闻催化，事件驱动明确", metrics
        return 4, "未匹配到明确催化事件", metrics

    # ── 维度6：市场环境 ──
    @classmethod
    def _score_market_environment(cls) -> tuple:
        # MVP: 静态参考值，后续接入 market 数据
        return 6, "市场环境参考（后续接入实时数据）", {"data_source": "static_reference"}

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
