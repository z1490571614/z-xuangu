import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


SECTOR_NAME_MAP = {
    "专精特新": "专精特新(创新型中小企业)",
    "ST板块": "ST板块(风险警示)",
    "科创板": "科创板(科技创新)",
}

DICTIONARY_BOARD_MATCHES = {
    "news_theme_board",
    "limit_tag_board",
    "selected_concept_board",
    "selected_board_type_board",
    "selected_industry_board",
    "exact_lu_desc_board",
    "exact_hint_board",
}
REFERENCE_BOARD_MATCHES = {"limit_cpt_list_reference", "semantic_reference_board"}


def _fmt_sector(name: str) -> str:
    return SECTOR_NAME_MAP.get(name, name)


def _evidence_boards(boards):
    return [board for board in boards if board.get("matched_from") not in REFERENCE_BOARD_MATCHES]


def _has_ladder_data(board: Dict[str, Any]) -> bool:
    try:
        rank = int(board.get("rank", 999) or 999)
    except (TypeError, ValueError):
        rank = 999
    return rank < 999 or (board.get("up_nums", 0) or 0) > 0 or (board.get("days", 0) or 0) > 0


def calculate_leader_position_loss(ctx: Dict) -> Dict:
    """龙头地位动摇（20分）

    数据源：limit_list_ths(连板数), kpl_list(炸板回封), daily(涨跌幅), stock(前日涨跌幅)
    关注：是否断板、是否炸板不回封、是否被卡位
    约束：非连板背景股不触发断板报警
    """
    score = 0
    tips = []
    stock = ctx.get("stock", {})
    daily = ctx.get("daily", {})
    theme = ctx.get("theme", {})
    kpl = theme.get("kpl_detail", {})

    change_pct = stock.get("change_pct", 0) or daily.get("pct_chg", 0)
    open_num = stock.get("lu_open_num", 0) or 0
    pre_change = stock.get("pre_change_pct", 0) or 0

    # 判断是否有涨停背景（前日涨停 或 有连板标签）
    has_limit_context = pre_change >= 9.5 or "连板" in str(stock.get("lu_tag", ""))

    # 断板判断：只有连板股才需要检查
    if has_limit_context and change_pct < 10:
        if "连板" in str(stock.get("lu_tag", "")):
            score += 15
            tips.append("涨停失败，断板")
        elif change_pct > 5:
            score += 10
            tips.append("连板股未涨停")

    # 炸板不回封（kpl_list数据）
    is_break = kpl.get("is_break", False)
    last_time = kpl.get("last_time")
    if is_break and not last_time:
        score += 10
        tips.append("炸板不回封")
    elif is_break and last_time:
        score += 5
        tips.append("炸板后回封，分歧已显现")

    # 开板次数
    if open_num >= 3:
        score += 8
        tips.append(f"开板{open_num}次，分歧加大")
    elif open_num >= 1:
        score += 3
        tips.append(f"开板{open_num}次")

    if not has_limit_context and score == 0:
        tips.append("非连板股，不适用龙头地位动摇判断")

    return {"score": min(score, 20), "tips": tips[:3], "data_status": "available"}


def calculate_emotion_retreat(ctx: Dict) -> Dict:
    """情绪退潮（20分）

    关注：连板高度下降、跌停家数增多、炸板率高
    """
    score = 0
    tips = []
    sentiment = ctx.get("market", {}).get("sentiment", {})

    max_con = sentiment.get("max_connected", 0) or 0
    up_cnt = sentiment.get("limit_up_count", 0) or 0
    down_cnt = sentiment.get("limit_down_count", 0) or 0
    zhaban = sentiment.get("zhaban_rate", 0) or 0

    if 0 < max_con <= 2:
        score += 8
        tips.append(f"最高仅{max_con}板，短线冰点")
    elif 0 < max_con <= 3:
        score += 4
        tips.append(f"最高{max_con}板，高度压缩")

    if down_cnt > 30:
        score += 8
        tips.append(f"跌停{down_cnt}家，恐慌情绪")
    elif down_cnt > 15:
        score += 5
        tips.append(f"跌停{down_cnt}家")
    elif down_cnt > 5:
        score += 2

    ratio = up_cnt / max(down_cnt, 1)
    if (up_cnt + down_cnt) > 0 and ratio < 1:
        score += 5
        tips.append("涨跌比<1，空头占优")

    if zhaban > 40:
        score += 5
        tips.append(f"炸板率{zhaban:.0f}%，封板意愿极弱")
    elif zhaban > 25:
        score += 2
        tips.append(f"炸板率{zhaban:.0f}%")

    return {"score": min(score, 20), "tips": tips[:4], "data_status": "available"}


def calculate_ladder_break(ctx: Dict) -> Dict:
    """板块梯队断裂（15分）

    数据源：limit_cpt_list
    关注：所属题材排名大幅下降、连板数断裂、涨停数减少
    """
    score = 0
    tips = []
    theme = ctx.get("theme", {})
    theme_rank = theme.get("theme_rank", {})
    hot_boards = _evidence_boards(theme_rank.get("hot_boards", []))
    primary_board = theme_rank.get("primary_board", {}) or {}
    primary_matched_from = primary_board.get("matched_from", "")
    has_confirmed_primary = primary_matched_from in DICTIONARY_BOARD_MATCHES

    best_rank = theme_rank.get("best_rank", 999)
    if best_rank > 20 and not has_confirmed_primary:
        score += 5
        tips.append("所属题材未进热点排行，梯队偏弱")

    for board in hot_boards[:2]:
        if not _has_ladder_data(board):
            continue
        name = _fmt_sector(board.get("name", ""))
        cons = board.get("cons_nums", 0)
        up = board.get("up_nums", 0)
        days = board.get("days", 0)

        if cons == 0 and up > 0:
            score += 4
            tips.append(f"{name}无连板股")
        elif cons <= 1:
            score += 2
            tips.append(f"{name}连板股稀少")

        # 首日爆发说明题材刚发酵，更多是持续性观察项，不应直接作为退潮风险扣分。

    return {"score": min(score, 15), "tips": tips[:3], "data_status": "available" if hot_boards else "insufficient_data"}


def calculate_acceptance_failure(ctx: Dict) -> Dict:
    """承接失败（15分）

    数据源：kpl_list(炸板回封), daily(振幅), moneyflow(资金),
            stk_factor_pro(volume_ratio), stk_mins(分钟走势)
    关注：炸板不回封、封单薄弱、高开低走、放量滞涨
    """
    score = 0
    tips = []
    stock = ctx.get("stock", {})
    daily = ctx.get("daily", {})
    capital = ctx.get("capital", {})
    technical = ctx.get("technical", {})
    theme = ctx.get("theme", {})
    kpl = theme.get("kpl_detail", {})

    open_change = stock.get("open_change_pct", 0) or 0
    change_pct = stock.get("change_pct", 0) or daily.get("pct_chg", 0)
    amplitude = daily.get("amplitude", 0) or 0
    net_mf = capital.get("net_mf_amount", 0) or 0
    elg_net = capital.get("elg_net", 0) or 0
    volume_ratio = technical.get("volume_ratio", 1) or 1

    # kpl_list: 炸板判断
    is_break = kpl.get("is_break", False)
    is_limit_up = kpl.get("is_limit_up", False)
    open_time = kpl.get("open_time")
    last_time = kpl.get("last_time")
    seal_amount = kpl.get("seal_amount", 0)

    # 炸板不回封 → 最严重的承接失败
    if is_break and not last_time:
        score += 10
        tips.append("炸板不回封，承接极差")
    elif is_break and last_time:
        score += 5
        tips.append("炸板后回封，但分歧已显现")
    elif is_limit_up and not is_break:
        pass  # 封板成功，不加分

    # 尾盘封单稀少（漏单嫌疑）
    if is_limit_up and seal_amount > 0 and seal_amount < 5000000:
        score += 4
        tips.append(f"尾盘封单仅{seal_amount/10000:.0f}万，漏单风险")
    elif is_limit_up and seal_amount < 20000000:
        score += 2
        tips.append(f"封单{seal_amount/10000:.0f}万，封板一般")

    # 高开低走
    if open_change > 5 and change_pct < 2:
        score += 8
        tips.append("高开低走，承接乏力")
    elif open_change > 3 and change_pct < 0:
        score += 6
        tips.append("高开低走，分歧明显")

    # 大幅波动未收高
    if amplitude > 10 and change_pct < 2:
        score += 5
        tips.append("大幅波动未收高")
    elif amplitude > 8 and change_pct < 0:
        score += 6
        tips.append("放量大振幅收跌")

    # 放量滞涨（来自 stk_factor_pro.volume_ratio）
    if volume_ratio > 2 and change_pct < 3 and change_pct >= 0:
        score += 4
        tips.append("放量滞涨")
    elif volume_ratio > 2 and change_pct < 0:
        score += 3

    # 资金出逃
    if net_mf < -30000000 and elg_net < -10000000:
        score += 5
        tips.append("主力+超大单资金出逃")

    return {"score": min(score, 15), "tips": tips[:3], "data_status": "available"}


def calculate_chip_cashout(ctx: Dict) -> Dict:
    """筹码兑现（10分）

    注意：高获利盘不是天然风险，需结合承接判断
    """
    score = 0
    tips = []
    stock = ctx.get("stock", {})
    chip = ctx.get("chip", {})
    daily = ctx.get("daily", {})
    capital = ctx.get("capital", {})

    winner_rate = chip.get("winner_rate", 0) or 0
    rise_10d = stock.get("rise_10d_pct", 0) or 0
    net_mf = capital.get("net_mf_amount", 0) or 0
    amplitude = daily.get("amplitude", 0) or 0

    if winner_rate > 85 and net_mf < -10000000:
        score += 7
        tips.append(f"高获利盘{winner_rate:.0f}%+资金流出，兑现压力大")
    elif winner_rate > 85:
        score += 3
        tips.append(f"获利盘{winner_rate:.0f}%，关注兑现")
    elif winner_rate > 70:
        score += 1

    if rise_10d > 40 and amplitude > 12:
        score += 5
        tips.append(f"10日涨幅{rise_10d:.0f}%+大振幅，高位震荡")
    elif rise_10d > 40:
        score += 3
        tips.append(f"10日涨幅{rise_10d:.0f}%")

    return {"score": min(score, 10), "tips": tips[:3], "data_status": "available"}


def calculate_auction_miss(ctx: Dict) -> Dict:
    """竞价低预期（10分）⚡ MCP数据"""
    score = 0
    tips = []
    stock = ctx.get("stock", {})

    auction_ratio = stock.get("auction_ratio", 0) or 0
    open_change = stock.get("open_change_pct", 0) or 0
    pre_change = stock.get("pre_change_pct", 0) or 0

    if pre_change >= 10 and open_change < 2:
        score += 8
        tips.append("昨涨停但竞价低开，低于预期")
    elif pre_change >= 5 and open_change < 0:
        score += 5
        tips.append(f"昨涨{pre_change:.1f}%但今绿盘开")

    if auction_ratio < 3 and open_change < 0:
        score += 5
        tips.append(f"竞价量比{auction_ratio:.1f}%+低开，竞价偏弱")
    elif auction_ratio < 3:
        score += 2
        tips.append(f"竞昨比仅{auction_ratio:.1f}%，竞价不活跃")

    return {"score": min(score, 10), "tips": tips[:3], "data_status": "available"}


def calculate_announcement_regulatory(announcement_result: Dict) -> Dict:
    """公告监管风险（10分）

    直接复用消息面结果中的利空部分
    """
    score = 0
    tips = []

    dim_scores = announcement_result.get("dimension_scores", {}) or {}
    dim_tips = announcement_result.get("dimension_tips", {}) or {}
    regulatory_score = dim_scores.get("regulatory", 0) or 0
    if regulatory_score < 0:
        score = min(10, abs(regulatory_score))
        tips.extend(dim_tips.get("regulatory", []) or ["存在监管类利空"])

    return {"score": min(score, 10), "tips": tips[:3], "data_status": announcement_result.get("data_status", "available")}


def retreat_risk_scoring(ctx: Dict, weights: Dict) -> Dict:
    """计算退潮风险总分"""
    position_loss = calculate_leader_position_loss(ctx)
    emotion_retreat = calculate_emotion_retreat(ctx)
    ladder_break = calculate_ladder_break(ctx)
    acceptance_failure = calculate_acceptance_failure(ctx)
    chip_cashout = calculate_chip_cashout(ctx)
    auction_miss = calculate_auction_miss(ctx)
    regulatory = calculate_announcement_regulatory(ctx.get("announcement_result", {}))
    # 以下3个维度从新闻情感分析（announcement_result.dimension_scores）读取
    ann = ctx.get("announcement_result", {})
    dim_scores = ann.get("dimension_scores", {})
    dim_tips = ann.get("dimension_tips", {})

    def _from_news(dim_key: str, max_score: int, label: str) -> Dict:
        raw = dim_scores.get(dim_key, 0) or 0
        tips = dim_tips.get(dim_key, [])
        # negative → 正数扣分; positive → 负数(=加分)
        score = abs(raw) if raw < 0 else 0
        score = min(score, max_score)
        risk_tips = tips if score > 0 else []
        return {"score": score, "tips": risk_tips, "data_status": "available"}

    financial = _from_news("financial_risk", 10, "业绩风险")
    shareholder = _from_news("shareholder_risk", 10, "减持解禁")
    st = _from_news("st_risk", 15, "ST退市")

    parts = {
        "leader_position_loss": position_loss,
        "emotion_retreat": emotion_retreat,
        "ladder_break": ladder_break,
        "acceptance_failure": acceptance_failure,
        "chip_cashout": chip_cashout,
        "auction_miss": auction_miss,
        "announcement_regulatory": regulatory,
        "financial_risk": financial,
        "shareholder_risk": shareholder,
        "st_risk": st,
    }

    total = sum(p["score"] for p in parts.values())
    total = min(100, max(0, total))

    return {"total": total, "parts": parts}
