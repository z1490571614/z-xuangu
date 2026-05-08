"""重组并购规则"""
from typing import Dict, Any


def score_restructure(text: str, facts: Dict[str, Any]) -> float:
    if "终止重大资产重组" in text or "终止重组" in text:
        return -3.5
    if "重组失败" in text:
        return -3.5
    if "不构成重大调整" in text:
        return 0.0
    if "获得证监会核准" in text or "通过审核" in text or "注册生效" in text:
        return 3.0
    if "签署正式协议" in text or "签订协议" in text:
        return 2.0
    if "筹划重大资产重组" in text:
        return 1.2
    if "拟收购" in text or "拟购买资产" in text:
        return 1.0
    if "收购" in text or "并购" in text or "重组" in text or "资产注入" in text:
        return 0.5
    return 0.0
