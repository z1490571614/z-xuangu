import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 板块名称映射（Tushare概念名→更可读的表述）
SECTOR_NAME_MAP = {
    "专精特新": "专精特新(创新型中小企业)",
    "ST板块": "ST板块(风险警示)",
    "科创板": "科创板(科技创新)",
}


def _fmt_sector(name: str) -> str:
    """格式化板块名称"""
    return SECTOR_NAME_MAP.get(name, name)


def calculate_leader_status(ctx: Dict) -> Dict:
    """龙头地位评分（25分）

    关注：连板高度、封板强度、涨跌幅、涨停原因
    """
    score = 0
    tips = []
    stock = ctx.get("stock", {})
    daily = ctx.get("daily", {})

    stock_tag = stock.get("lu_tag", "")

    # 连板数判断
    try:
        board_count = 0
        if stock_tag:
            match = re.search(r"(\d+)连板", stock_tag)
            if match:
                board_count = int(match.group(1))
            else:
                match = re.search(r"(\d+)天(\d+)板", stock_tag)
                if match:
                    board_count = int(match.group(2))
    except Exception:
        board_count = 0

    limit_count = stock.get("limit_up_count", 0) or 0
    seal_rate = stock.get("seal_rate", 0) or 0

    if board_count >= 5:
        score += 15
        tips.append(f"{board_count}连板，高标龙头")
    elif board_count >= 3:
        score += 12
        tips.append(f"{board_count}连板，板块先锋")
    elif board_count >= 2:
        score += 8
        tips.append(f"{board_count}连板，晋级中")
    elif limit_count >= 5:
        score += 6
        tips.append(f"近100日涨停{limit_count}次，股性活跃")

    if seal_rate >= 85:
        score += 5
        tips.append(f"封成比{seal_rate:.0f}%")
    elif seal_rate >= 70:
        score += 3
        tips.append(f"封成比{seal_rate:.0f}%")

    change_pct = stock.get("change_pct", 0) or daily.get("pct_chg", 0)
    if change_pct >= 10:
        score += 3
        tips.append("当日涨停")
    elif change_pct >= 7:
        score += 2
        tips.append("大涨7%+")
    elif change_pct >= 5:
        score += 1

    industry = stock.get("industry", "")
    if industry:
        tips.append(f"所属行业: {industry}")

    if stock.get("lu_desc", ""):
        desc = stock.get("lu_desc", "")[:30]
        tips.append(f"涨停原因: {desc}")

    return {"score": min(score, 25), "tips": tips[:5], "data_status": "available"}


def calculate_theme_strength(ctx: Dict) -> Dict:
    """题材强度评分（20分）

    数据源：limit_cpt_list（最强板块排行）
    关注：所属题材排名、涨停家数、连板高度、上榜天数
    """
    score = 5
    tips = []
    theme = ctx.get("theme", {})
    theme_rank = theme.get("theme_rank", {})

    best_rank = theme_rank.get("best_rank", 999)
    best_name = theme_rank.get("best_name", "")
    board_count = theme_rank.get("board_count", 0)
    hot_boards = theme_rank.get("hot_boards", [])

    if best_rank <= 3:
        score += 10
        tips.append(f"主跟随题材：{_fmt_sector(best_name)}，排名第{best_rank}，市场主线")
    elif best_rank <= 5:
        score += 8
        tips.append(f"主跟随题材：{_fmt_sector(best_name)}，排名第{best_rank}，强势题材")
    elif best_rank <= 10:
        score += 6
        tips.append(f"主跟随题材：{_fmt_sector(best_name)}，排名第{best_rank}，热点题材")
    elif best_rank <= 20:
        score += 3
        tips.append(f"主跟随题材：{_fmt_sector(best_name)}，排名第{best_rank}")
    else:
        score += 1

    if board_count >= 2:
        score += 3
        names = [
            f"{_fmt_sector(b.get('name', ''))}(第{b.get('rank', '--')})"
            for b in hot_boards[:5] if b.get("name")
        ]
        if names:
            tips.append(f"命中{board_count}个热点题材：" + "、".join(names))
        else:
            tips.append(f"个股属于{board_count}个热点题材")
    elif board_count == 1:
        score += 1

    for board in hot_boards[:3]:
        name = _fmt_sector(board.get("name", ""))
        up = board.get("up_nums", 0)
        days = board.get("days", 0)
        up_stat = board.get("up_stat", "")
        if up >= 15:
            score += 2
            tips.append(f"{name}涨停{up}家，板块效应强")
        elif up >= 10:
            score += 1
        if days >= 5:
            score += 1
            tips.append(f"{name}持续{days}天，题材有持续性")

    return {"score": min(score, 20), "tips": tips[:4], "data_status": "available" if best_rank < 999 else "insufficient_data"}


def calculate_emotion_cycle(ctx: Dict) -> Dict:
    """情绪周期评分（15分）

    关注：连板高度、涨停家数、跌停家数、炸板率
    """
    score = 7
    tips = []
    sentiment = ctx.get("market", {}).get("sentiment", {})

    max_con = sentiment.get("max_connected", 0) or 0
    up_cnt = sentiment.get("limit_up_count", 0) or 0
    down_cnt = sentiment.get("limit_down_count", 0) or 0
    zhaban = sentiment.get("zhaban_rate", 0) or 0

    if max_con >= 7:
        score += 8
        tips.append(f"最高{max_con}板，高度打开")
    elif max_con >= 5:
        score += 5
        tips.append(f"最高{max_con}板，情绪良好")
    elif max_con >= 3:
        score += 3
        tips.append(f"最高{max_con}板")
    elif max_con <= 2 and max_con > 0:
        score -= 3

    if up_cnt > 50:
        score += 3
        tips.append(f"涨停{up_cnt}家，情绪高涨")
    elif up_cnt > 30:
        score += 2
        tips.append(f"涨停{up_cnt}家")
    elif up_cnt > 15:
        score += 1

    if down_cnt > 20:
        score -= 4
        tips.append(f"跌停{down_cnt}家，亏钱效应明显")
    elif down_cnt > 10:
        score -= 2
        tips.append(f"跌停{down_cnt}家")

    if zhaban > 40:
        score -= 2
        tips.append(f"炸板率{zhaban:.0f}%")
    elif zhaban > 25:
        score -= 1

    return {"score": max(0, min(score, 15)), "tips": tips[:4], "data_status": "available"}


def calculate_sector_ladder(ctx: Dict) -> Dict:
    """板块梯队评分（15分）"""
    score = 3
    tips = []
    theme = ctx.get("theme", {})
    theme_rank = theme.get("theme_rank", {})
    hot_boards = theme_rank.get("hot_boards", [])

    for board in hot_boards[:2]:
        name = _fmt_sector(board.get("name", ""))
        cons = board.get("cons_nums", 0)
        up = board.get("up_nums", 0)
        days = board.get("days", 0)

        if cons >= 5:
            score += 6
            tips.append(f"{name}板块有{cons}家连板，梯队完整")
        elif cons >= 3:
            score += 4
            tips.append(f"{name}板块有{cons}家连板，梯队良好")
        elif cons >= 1:
            score += 2
            tips.append(f"{name}板块有{cons}家连板")

        if up >= 20:
            score += 3
            tips.append(f"{name}板块涨停{up}家，扩散性强")
        elif up >= 10:
            score += 1

        if days >= 10:
            score += 3
            tips.append(f"{name}已持续{days}天，主升题材")
        elif days >= 5:
            score += 2
            tips.append(f"{name}持续{days}天")

    if not hot_boards:
        score = 2

    return {"score": min(score, 15), "tips": tips[:4], "data_status": "available" if hot_boards else "insufficient_data"}


def calculate_acceptance_strength(ctx: Dict) -> Dict:
    """承接强度评分（10分）

    数据源：daily(振幅/成交量), moneyflow(资金), kpl_list(封单量),
            stk_factor_pro(volume_ratio), stk_mins(分钟走势)
    关注：涨停质量、资金承接、封单强度、放量合理性
    """
    score = 5
    tips = []
    stock = ctx.get("stock", {})
    daily = ctx.get("daily", {})
    capital = ctx.get("capital", {})
    technical = ctx.get("technical", {})
    theme = ctx.get("theme", {})
    kpl = theme.get("kpl_detail", {})

    change_pct = stock.get("change_pct", 0) or daily.get("pct_chg", 0)
    amplitude = daily.get("amplitude", 0) or 0
    open_change = stock.get("open_change_pct", 0) or 0
    net_mf = capital.get("net_mf_amount", 0) or 0
    volume_ratio = technical.get("volume_ratio", 1) or 1
    seal_amount = kpl.get("seal_amount", 0)

    # 涨停质量
    if change_pct >= 10:
        score += 2
        tips.append("涨停收盘")
        if open_change < 3:
            score += 2
            tips.append("弱转强(低开→涨停)")
        if seal_amount > 50000000:
            score += 1
            tips.append("封单充裕")
    elif change_pct >= 5 and amplitude < 10:
        score += 2
        tips.append("大涨收盘")
    elif change_pct >= 0:
        score += 1

    # 资金承接（来自 moneyflow）
    elg_net = capital.get("elg_net", 0) or 0
    lg_net = capital.get("lg_net", 0) or 0
    if elg_net > 0:
        score += 2
        tips.append("超大单净买入")
    elif lg_net > 0:
        score += 1
        tips.append("大单净买入")

    # 放量合理性（来自 stk_factor_pro.volume_ratio）
    if volume_ratio > 2 and change_pct >= 10:
        score += 1
        tips.append("放量涨停")
    elif volume_ratio > 2 and change_pct < 0:
        score -= 1
        tips.append("放量下跌")
    elif volume_ratio < 0.5 and change_pct >= 10:
        score += 2
        tips.append("缩量涨停(抛压轻)")

    # 资金数据缺失时说明
    if not capital:
        tips.append("资金流向数据缺失")

    return {"score": max(0, min(score, 10)), "tips": tips[:4], "data_status": "available"}


def calculate_auction_intraday(ctx: Dict) -> Dict:
    """竞价分时评分（10分）⚡ MCP数据

    关注：竞昨比、竞价换手率、开涨幅
    """
    score = 5
    tips = []
    stock = ctx.get("stock", {})

    auction_ratio = stock.get("auction_ratio", 0) or 0
    auction_tr = stock.get("auction_turnover_rate", 0) or 0
    open_change = stock.get("open_change_pct", 0) or 0
    pre_change = stock.get("pre_change_pct", 0) or 0

    if auction_ratio >= 15:
        score += 3
        tips.append(f"竞昨比{auction_ratio:.1f}%，竞价量充沛")
    elif auction_ratio >= 8:
        score += 2
        tips.append(f"竞昨比{auction_ratio:.1f}%，竞价活跃")
    elif auction_ratio >= 4:
        score += 1

    if auction_tr >= 3:
        score += 2
        tips.append(f"竞价换手{auction_tr:.1f}%，换手充分")
    elif auction_tr >= 1:
        score += 1
        tips.append(f"竞价换手{auction_tr:.1f}%")

    if open_change > 3:
        score += 2
        tips.append(f"开涨幅{open_change:.1f}%，高开")
    elif open_change > 0:
        score += 1
        tips.append(f"开涨幅{open_change:.1f}%")

    if pre_change >= 10:
        score += 1
        tips.append("昨涨停")

    return {"score": min(score, 10), "tips": tips[:4], "data_status": "available"}


def leader_strength_scoring(ctx: Dict, weights: Dict) -> Dict:
    """计算龙头强度总分"""
    leader_status = calculate_leader_status(ctx)
    theme_strength = calculate_theme_strength(ctx)
    emotion_cycle = calculate_emotion_cycle(ctx)
    sector_ladder = calculate_sector_ladder(ctx)
    acceptance = calculate_acceptance_strength(ctx)
    auction = calculate_auction_intraday(ctx)
    lhb_bonus = {"score": 0, "tips": [], "data_status": "not_applicable"}
    lhb_data = ctx.get("lhb_result")
    if lhb_data and lhb_data.get("data_status") == "available":
        alpha = lhb_data.get("lhb_alpha_score", 0)
        lhb_bonus = {
            "score": max(0, min(5, abs(alpha) // 3)),
            "tips": lhb_data.get("tips", [])[:2],
            "data_status": "available"
        }

    parts = {
        "leader_status": leader_status,
        "theme_strength": theme_strength,
        "emotion_cycle": emotion_cycle,
        "sector_ladder": sector_ladder,
        "acceptance_strength": acceptance,
        "auction_intraday": auction,
        "lhb_bonus": lhb_bonus,
    }

    total = sum(p["score"] for p in parts.values())
    total = min(100, max(0, total))

    return {"total": total, "parts": parts}
