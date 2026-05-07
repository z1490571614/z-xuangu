from typing import Dict, Any, List


NON_RISK_PATTERNS = (
    "无明显断裂",
    "无减持",
    "无ST",
    "无退市",
    "无业绩风险",
    "不适用",
    "有待观察",
)


def get_leader_level(score: int) -> str:
    if score >= 85:
        return "极强龙头"
    if score >= 70:
        return "强势龙头"
    if score >= 55:
        return "疑似龙头"
    if score >= 40:
        return "跟风强势股"
    return "非龙头"


def get_retreat_risk_level(score: int) -> str:
    if score <= 25:
        return "低风险"
    if score <= 45:
        return "中等风险"
    if score <= 65:
        return "高风险"
    return "极高风险"


def get_health_level(score: int) -> str:
    if score >= 80:
        return "龙头健康"
    if score >= 65:
        return "强势可观察"
    if score >= 50:
        return "分歧加大"
    if score >= 35:
        return "退潮预警"
    return "回避"


def get_cycle_stage(leader_total: int, retreat_total: int, health: int) -> str:
    """判断周期阶段"""
    if leader_total >= 60 and retreat_total <= 30:
        return "主升期"
    if leader_total >= 50 and 30 < retreat_total <= 50:
        return "分歧期"
    if retreat_total > 50:
        return "退潮期"
    if leader_total < 30 and retreat_total <= 30:
        return "混沌期"
    return "震荡期"


def collect_positive_tips(leader_parts: Dict, announcement_result: Dict, lhb_result: Dict) -> List[str]:
    tips = []
    for key, part in leader_parts.items():
        if part.get("score", 0) > 0 and part.get("tips"):
            tips.extend(part["tips"][:2])
    if announcement_result.get("good_news_score", 0) > 0:
        tips.append(f"消息面利好+{announcement_result['good_news_score']}")
    if lhb_result.get("lhb_bonus_score", 0) > 0:
        for t in lhb_result.get("tips", []):
            if "买入" in t or "抢筹" in t or "游资" in t:
                tips.append(t)
                break
    return tips[:6]


def collect_negative_tips(retreat_parts: Dict, announcement_result: Dict, lhb_result: Dict) -> List[str]:
    tips = []
    for key, part in retreat_parts.items():
        if part.get("score", 0) <= 0 or not part.get("tips"):
            continue
        for tip in part["tips"][:2]:
            if any(pattern in str(tip) for pattern in NON_RISK_PATTERNS):
                continue
            tips.append(tip)
    if announcement_result.get("bad_news_score", 0) < 0 and not any("利空" in str(t) for t in tips):
        tips.append(f"消息面利空{announcement_result['bad_news_score']}")
    if lhb_result.get("lhb_penalty_score", 0) < 0:
        for t in lhb_result.get("tips", []):
            if "卖出" in t or "砸盘" in t or "散户" in t:
                tips.append(t)
                break
    return tips[:6]


def generate_watch_tips(leader_parts: Dict, retreat_parts: Dict) -> List[str]:
    tips = []
    if any("炸板" in (t or "") for p in retreat_parts.values() for t in (p.get("tips") or [])):
        tips.append("次日竞价是否低于预期")
        tips.append("炸板后能否快速回封")
    if any("卡位" in (t or "") for p in leader_parts.values() for t in (p.get("tips") or [])):
        tips.append("是否被同题材补涨股卡位")
    auction_miss = retreat_parts.get("auction_miss", {})
    if auction_miss.get("score", 0) > 0:
        tips.append("竞价是否转强（弱转强）")
    leader_status = leader_parts.get("leader_status", {})
    if leader_status.get("score", 0) >= 12:
        tips.append("龙头地位是否稳固")
    if not tips:
        tips = ["竞价是否超预期", "板块梯队是否完整", "盘中承接是否有力"]
    return tips[:5]


def _build_simplified_summary(
    leader_level: str, leader_total: int, retreat_total: int, health_score: int,
    cycle_stage: str, positive_tips: List[str], negative_tips: List[str],
    announcement_result: Dict, lhb_result: Dict,
) -> str:
    """生成简化说明"""
    parts = []

    # 龙头地位
    parts.append(f"该股为【{leader_level}】(强度{leader_total}分)，当前处于{cycle_stage}。")

    # 强势总结（取1条最关键）
    if positive_tips:
        top = positive_tips[0]
        if "连板" in top:
            parts.append(f"核心强势：{top}。")
        elif "题材" in top:
            parts.append(f"题材优势：{top}。")
        else:
            parts.append(f"正面信号：{top}。")

    # 风险总结（取1条最关键）
    if negative_tips:
        top = negative_tips[0]
        parts.append(f"主要风险：{top}。")

    # 消息面
    aa = announcement_result.get("announcement_alpha_score", 0) or 0
    if aa > 5:
        parts.append(f"消息面偏正面(净分+{aa})。")
    elif aa < -5:
        parts.append(f"消息面偏负面(净分{aa})。")

    # 健康度
    parts.append(f"综合健康度{health_score}分(退潮风险{retreat_total}分)。")

    return "".join(parts)


def assemble_output(
    ts_code: str, trade_date: str,
    leader_result: Dict, retreat_result: Dict,
    health_score: int,
    announcement_result: Dict, lhb_result: Dict
) -> Dict:
    """组装最终输出，兼容旧字段"""

    leader_total = leader_result["total"]
    retreat_total = retreat_result["total"]

    leader_level = get_leader_level(leader_total)
    risk_level = get_retreat_risk_level(retreat_total)
    health_level = get_health_level(health_score)
    cycle_stage = get_cycle_stage(leader_total, retreat_total, health_score)

    positive_tips = collect_positive_tips(leader_result["parts"], announcement_result, lhb_result)
    negative_tips = collect_negative_tips(retreat_result["parts"], announcement_result, lhb_result)
    watch_tips = generate_watch_tips(leader_result["parts"], retreat_result["parts"])

    def collect_status(parts: Dict) -> str:
        statuses = set()
        for p in parts.values():
            if isinstance(p, dict) and "data_status" in p:
                statuses.add(p["data_status"])
        if "available" in statuses:
            return "available"
        if "insufficient_data" in statuses:
            return "insufficient_data"
        return "missing"

    result = {
        "ts_code": ts_code,
        "trade_date": trade_date,
        "strategy_type": "dragon_leader",
        "leader_strength_score": leader_total,
        "retreat_risk_score": retreat_total,
        "health_score": health_score,
        "leader_level": leader_level,
        "risk_level": risk_level,
        "health_level": health_level,
        "cycle_stage": cycle_stage,
        "announcement_alpha_score": announcement_result.get("announcement_alpha_score", 0),
        "lhb_alpha_score": lhb_result.get("lhb_alpha_score", 0),
        "simplified_summary": _build_simplified_summary(
            leader_level, leader_total, retreat_total, health_score,
            cycle_stage, positive_tips, negative_tips,
            announcement_result, lhb_result,
        ),
        "positive_tips": positive_tips,
        "negative_tips": negative_tips,
        "watch_tips": watch_tips,
        "score_detail": {
            "leader_strength": leader_result["parts"],
            "retreat_risk": retreat_result["parts"],
            "alpha_adjustment": {
                "good_news_score": announcement_result.get("good_news_score", 0),
                "bad_news_score": announcement_result.get("bad_news_score", 0),
                "announcement_alpha_score": announcement_result.get("announcement_alpha_score", 0),
                "lhb_bonus_score": lhb_result.get("lhb_bonus_score", 0),
                "lhb_penalty_score": lhb_result.get("lhb_penalty_score", 0),
                "lhb_alpha_score": lhb_result.get("lhb_alpha_score", 0),
                "announcement_tips": announcement_result.get("tips", []),
                "lhb_tips": lhb_result.get("tips", []),
                # 分维度新闻评分（替代Tushare API直接调用）
                "dimension_scores": announcement_result.get("dimension_scores", {}),
                "dimension_tips": announcement_result.get("dimension_tips", {}),
            }
        },
        "score_labels": {
            "leader_strength": {
                "leader_status": "龙头地位",
                "theme_strength": "题材强度",
                "emotion_cycle": "情绪周期",
                "sector_ladder": "板块梯队",
                "acceptance_strength": "承接强度",
                "auction_intraday": "竞价分时",
                "lhb_bonus": "龙虎榜加成",
            },
            "retreat_risk": {
                "leader_position_loss": "龙头地位动摇",
                "emotion_retreat": "情绪退潮",
                "ladder_break": "板块梯队断裂",
                "acceptance_failure": "承接失败",
                "chip_cashout": "筹码兑现",
                "auction_miss": "竞价低预期",
                "announcement_regulatory": "公告监管风险",
                "financial_risk": "业绩风险",
                "shareholder_risk": "减持解禁",
                "st_risk": "ST退市风险",
            }
        },
        "data_status": {
            "announcement": announcement_result.get("data_status", "missing"),
            "lhb": lhb_result.get("data_status", "not_applicable"),
            "theme_ladder": collect_status({k: v for k, v in leader_result["parts"].items() if k in ("theme_strength", "sector_ladder")}),
            "capital_flow": "available",
        },
        "total_score": retreat_total,
        "total_risk_level": risk_level,
    }

    return result
