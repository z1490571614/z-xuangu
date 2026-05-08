"""
统一游资/机构席位库 - lhb_service 和 risk_breakdown_service 共用
"""
from typing import Dict, List, Optional, Tuple

# 散户/砸盘弱势席位（利空，计入风险加分）
SEAT_SCATTER: List[str] = [
    "东方财富证券拉萨",
    "东方财富证券日喀则",
    "东方财富证券林芝",
    "同花顺证券分公司",
    "东方财富分公司",
    "互联网证券营业部",
    "知春路",
    "新闸路",
    "消闲派",
    "紫阳东路",
]

# 核按钮砸盘席位（利空，高分）
SEAT_KNOCK: List[str] = [
    "长城证券仙桃钱沟路",
    "长城仙桃钱沟路",
    "华泰证券成都南一环路",
    "华泰成都南一环路",
]

# 量化席位（砸盘，利空）
SEAT_QUANT: List[str] = [
    "华鑫证券上海分公司",
    "中金公司上海分公司",
    "中金上海分公司",
    "中信证券上海分公司",
]

# 高溢价顶级游资（利好，风险减分、标签高亮）
SEAT_PREMIUM: List[str] = [
    "相城大道",
    "大连黄河路",
    "南京汉中路",
]

# 机构/北向（溢价席位，利好，风险减分）
SEAT_INST: List[str] = ["机构专用", "沪股通", "深股通"]

# 原有一线游资关键词
SEAT_TOP_TRADERS: List[str] = [
    "华泰证券深圳益田路",
    "中信证券杭州延安路",
    "中国银河证券绍兴",
    "国泰君安证券上海江苏路",
    "国泰君安证券南京太平南路",
    "华鑫证券上海分公司",
    "兴业证券陕西分公司",
    "东方证券上海浦东新区源深路",
]


def match_seat_tag(exalter: str) -> Tuple[str, Optional[str]]:
    """
    匹配席位标签
    Returns:
        (tag, detail_type)
        tag: 机构/北向/一线游资/核按钮/散户/高溢价/普通/量化
        detail_type: 具体类型说明（如"余哥关联"）
    """
    normalized = _normalize_seat_name(exalter)

    # 高溢价（优先匹配，包含机构/北向）
    for kw in SEAT_PREMIUM:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("高溢价", kw)

    # 机构/北向（溢价席位）
    for kw in SEAT_INST:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("高溢价", "机构" if kw == "机构专用" else "北向")

    # 核按钮
    for kw in SEAT_KNOCK:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("核按钮", kw)

    # 量化席位（砸盘）
    for kw in SEAT_QUANT:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("量化", kw)

    # 一线游资
    for kw in SEAT_TOP_TRADERS:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("一线游资", None)

    # 散户/砸盘
    for kw in SEAT_SCATTER:
        if _seat_keyword_match(kw, exalter, normalized):
            return ("散户", kw)

    return ("普通", None)


def _normalize_seat_name(exalter: str) -> str:
    text = str(exalter or "")
    for token in ("股份有限公司", "有限责任公司", "有限公司", "证券营业部", "营业部"):
        text = text.replace(token, "")
    return text


def _seat_keyword_match(keyword: str, exalter: str, normalized_exalter: str) -> bool:
    normalized_keyword = _normalize_seat_name(keyword)
    return keyword in exalter or normalized_keyword in normalized_exalter


def is_scatter_seat(exalter: str) -> bool:
    """是否为散户/砸盘弱势席位"""
    return any(kw in exalter for kw in SEAT_SCATTER)


def is_knock_seat(exalter: str) -> bool:
    """是否为核按钮砸盘席位"""
    return any(kw in exalter for kw in SEAT_KNOCK)


def is_premium_seat(exalter: str) -> bool:
    """是否为高溢价顶级游资席位"""
    return any(kw in exalter for kw in SEAT_PREMIUM)


def is_institutional_seat(exalter: str) -> bool:
    """是否为机构/北向席位"""
    return any(kw in exalter for kw in SEAT_INST)


def is_quant_seat(exalter: str) -> bool:
    """是否为量化席位"""
    return any(kw in exalter for kw in SEAT_QUANT)


def get_seat_risk_score(exalter: str) -> int:
    """获取席位对风险评分的贡献值（正=加分，负=减分）"""
    if is_knock_seat(exalter):
        return 5
    if is_quant_seat(exalter):
        return 3  # 量化席位计入砸盘风险
    if is_scatter_seat(exalter):
        return 3
    if is_premium_seat(exalter):
        return -2  # 减分（降低风险）
    if is_institutional_seat(exalter):
        return -2  # 机构/北向作为溢价席位，获得更大减分
    return 0
