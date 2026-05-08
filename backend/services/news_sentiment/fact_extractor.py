import re
from typing import Dict, Any
from backend.services.news_sentiment.normalizer import extract_percentage


def extract_performance_facts(text: str) -> Dict[str, Any]:
    facts = {
        "revenue_yoy": None,
        "net_profit_yoy": None,
        "deducted_profit_yoy": None,
        "revenue_qoq": None,
        "net_profit_qoq": None,
        "deducted_profit_qoq": None,
        "is_qoq_turnaround": False,
        "is_yoy_turnaround": False,
        "performance_primary_basis": "yoy",
        "net_profit_value": None,
        "deducted_profit_value": None,
        "is_turnaround": False,
        "is_loss": False,
        "is_loss_reducing": False,
        "is_loss_expanding": False,
        "is_non_recurring_gain": False,
        "is_above_expectation": False,
        "is_below_expectation": False,
    }

    patterns = {
        "net_profit_growth": r"(?:归母净利润|净利润).*?(?:同比)?(?:增长|增加)\s*(\d+\.?\d*)%",
        "net_profit_drop": r"(?:归母净利润|净利润).*?(?:同比)?(?:下降|减少)\s*(\d+\.?\d*)%",
        "deducted_profit_growth": r"扣非净利润.*?(?:同比)?(?:增长|增加)\s*(\d+\.?\d*)%",
        "deducted_profit_drop": r"扣非净利润.*?(?:同比)?(?:下降|减少)\s*(\d+\.?\d*)%",
        "revenue_growth": r"(?:营业收入|营收).*?(?:同比)?(?:增长|增加)\s*(\d+\.?\d*)%",
        "revenue_drop": r"(?:营业收入|营收).*?(?:同比)?(?:下降|减少)\s*(\d+\.?\d*)%",
        "net_profit_value": r"(?:归母净利润|净利润)[\s\S]{0,10}?(\d+\.?\d*)\s*亿元?",
        "deducted_profit_value": r"扣非净利润[\s\S]{0,10}?(\d+\.?\d*)\s*亿元?",
    }

    # YoY
    net_profit_growth = _find_first(patterns["net_profit_growth"], text)
    net_profit_drop = _find_first(patterns["net_profit_drop"], text)
    if net_profit_growth is not None:
        facts["net_profit_yoy"] = net_profit_growth
    elif net_profit_drop is not None:
        facts["net_profit_yoy"] = -net_profit_drop

    deducted_growth = _find_first(patterns["deducted_profit_growth"], text)
    deducted_drop = _find_first(patterns["deducted_profit_drop"], text)
    if deducted_growth is not None:
        facts["deducted_profit_yoy"] = deducted_growth
    elif deducted_drop is not None:
        facts["deducted_profit_yoy"] = -deducted_drop

    revenue_growth = _find_first(patterns["revenue_growth"], text)
    revenue_drop = _find_first(patterns["revenue_drop"], text)
    if revenue_growth is not None:
        facts["revenue_yoy"] = revenue_growth
    elif revenue_drop is not None:
        facts["revenue_yoy"] = -revenue_drop

    # QoQ
    qoq_net_profit_growth = _find_first(r"环比.*(?:增长|增加)\s*(\d+\.?\d*)%", text)
    qoq_net_profit_drop = _find_first(r"环比.*(?:下降|减少)\s*(\d+\.?\d*)%", text)
    if qoq_net_profit_growth is not None:
        facts["net_profit_qoq"] = qoq_net_profit_growth
    elif qoq_net_profit_drop is not None:
        facts["net_profit_qoq"] = -qoq_net_profit_drop
    facts["is_qoq_turnaround"] = "环比扭亏" in text or "环比扭亏为盈" in text

    facts["net_profit_value"] = _find_first(patterns["net_profit_value"], text)
    facts["deducted_profit_value"] = _find_first(patterns["deducted_profit_value"], text)
    facts["is_turnaround"] = "扭亏为盈" in text and "环比" not in text[max(0, text.find("扭亏为盈")-3):text.find("扭亏为盈")]
    facts["is_qoq_turnaround"] = "环比扭亏" in text or "环比扭亏为盈" in text
    facts["is_loss"] = ("亏损" in text or "续亏" in text) and "扭亏" not in text and "亏损收窄" not in text and "亏损减少" not in text
    facts["is_loss_reducing"] = "亏损收窄" in text or "亏损减少" in text or "减亏" in text
    facts["is_loss_expanding"] = "亏损扩大" in text
    facts["is_non_recurring_gain"] = "非经常性损益" in text
    facts["is_above_expectation"] = "超预期" in text
    facts["is_below_expectation"] = "不及预期" in text

    return facts


def extract_reduce_holding_facts(text: str) -> Dict[str, Any]:
    facts = {
        "holder_type": None,
        "reduce_ratio": None,
        "reduce_amount": None,
        "is_passive": False,
        "is_completed": False,
        "is_clearance": False,
    }
    for htype in ["控股股东", "实际控制人", "实控人", "董事", "高管", "董监高", "重要股东"]:
        if htype in text:
            facts["holder_type"] = htype
            break
    import re
    m = re.search(r"(\d+\.?\d*)%", text)
    if m:
        facts["reduce_ratio"] = float(m.group(1))
    facts["is_passive"] = "被动减持" in text
    facts["is_completed"] = "减持计划实施完毕" in text
    facts["is_clearance"] = "清仓式减持" in text
    return facts


def extract_increase_holding_facts(text: str) -> Dict[str, Any]:
    facts = {
        "holder_type": None,
        "increase_amount": None,
    }
    for htype in ["控股股东", "实际控制人", "实控人", "董事长", "董监高", "高管"]:
        if htype in text:
            facts["holder_type"] = htype
            break
    from backend.services.news_sentiment.normalizer import extract_amount
    amounts = extract_amount(text)
    facts["increase_amount"] = max(amounts) if amounts else None
    return facts


def extract_buyback_facts(text: str, context: dict = None) -> Dict[str, Any]:
    facts = {
        "buyback_amount": None,
        "market_cap": context.get("market_cap") if context else None,
        "buyback_ratio_to_market_cap": None,
        "is_completed": False,
        "is_plan": False,
    }
    from backend.services.news_sentiment.normalizer import extract_amount
    amounts = extract_amount(text)
    facts["buyback_amount"] = max(amounts) if amounts else None
    if facts["buyback_amount"] and facts["market_cap"] and facts["market_cap"] > 0:
        facts["buyback_ratio_to_market_cap"] = facts["buyback_amount"] / facts["market_cap"]
    facts["is_completed"] = "已回购" in text or "回购完成" in text
    facts["is_plan"] = "拟回购" in text or "回购方案" in text
    return facts


def extract_order_contract_facts(text: str, context: dict = None) -> Dict[str, Any]:
    facts = {
        "contract_amount": None,
        "last_year_revenue": context.get("last_year_revenue") if context else None,
        "contract_to_revenue_ratio": None,
        "is_framework": False,
        "is_formal_contract": False,
        "customer_quality": None,
    }
    from backend.services.news_sentiment.normalizer import extract_amount
    amounts = extract_amount(text)
    facts["contract_amount"] = max(amounts) if amounts else None
    if facts["contract_amount"] and facts["last_year_revenue"] and facts["last_year_revenue"] > 0:
        facts["contract_to_revenue_ratio"] = facts["contract_amount"] / facts["last_year_revenue"]
    facts["is_framework"] = "框架协议" in text
    facts["is_formal_contract"] = "签订合同" in text or "重大合同" in text or "中标" in text
    return facts


def extract_unlock_facts(text: str, context: dict = None) -> Dict[str, Any]:
    facts = {
        "unlock_market_value": None,
        "float_market_cap": context.get("float_market_cap") if context else None,
        "unlock_ratio_to_float_cap": None,
    }
    from backend.services.news_sentiment.normalizer import extract_amount
    amounts = extract_amount(text)
    facts["unlock_market_value"] = max(amounts) if amounts else None
    if facts["unlock_market_value"] and facts["float_market_cap"] and facts["float_market_cap"] > 0:
        facts["unlock_ratio_to_float_cap"] = facts["unlock_market_value"] / facts["float_market_cap"]
    return facts


def _find_first(pattern: str, text: str):
    m = re.search(pattern, text)
    if m:
        return float(m.group(1))
    return None
