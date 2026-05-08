"""常量、关键词、事件枚举——集中配置"""

SENTIMENT = {
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "mixed": "多空混合",
    "unknown": "无法判断",
}

EVENT_TYPES = {
    "performance": "业绩类",
    "restructure": "重组并购",
    "order_contract": "订单合同",
    "buyback": "回购",
    "increase_holding": "增持",
    "reduce_holding": "减持",
    "unlock": "解禁",
    "pledge": "股权质押",
    "regulatory": "监管处罚",
    "inquiry": "问询关注",
    "litigation": "诉讼仲裁",
    "policy": "政策题材",
    "product_tech": "产品技术",
    "capacity": "产能投产",
    "personnel": "人事变动",
    "clarification": "澄清公告",
    "abnormal_movement": "交易异常波动",
    "process": "流程公告",
    "other": "其他",
}

CERTAINTY_TYPES = {
    "completed": "已完成",
    "signed": "已签署",
    "approved": "已审议通过",
    "forecast": "预计",
    "planned": "拟/计划",
    "preliminary": "筹划/初步意向",
    "framework": "框架协议",
    "uncertain": "存在不确定性",
    "unknown": "未知",
}

CERTAINTY_FACTOR = {
    "completed": 1.00,
    "signed": 0.95,
    "approved": 0.90,
    "forecast": 0.85,
    "planned": 0.70,
    "preliminary": 0.55,
    "framework": 0.45,
    "uncertain": 0.35,
    "unknown": 1.00,
}

# 载体词——不参与情感判断
CARRIER_WORDS = [
    "公告", "公告称", "发布公告", "披露", "信息披露",
    "发布", "刊发", "刊登", "表示", "称", "显示",
]

# 不确定性词——只影响 certainty
UNCERTAINTY_WORDS = [
    "拟", "计划", "筹划", "预计", "有望", "或将",
    "拟议", "意向", "框架协议", "战略合作意向",
    "初步意向", "预案", "草案", "征求意见稿",
    "尚存在不确定性", "存在不确定性",
]

# 新闻范围分类
NEWS_SCOPE_TYPES = {
    "single_stock": "单股新闻/单股公告",
    "multi_stock": "多股新闻/盘面综述/板块点评",
    "market_overview": "市场综述",
    "not_applicable": "非财经文本",
    "unknown": "无法判断",
}

# 市场综述中的正面词——不能直接作为单股强利好
MARKET_CONTEXT_POSITIVE_WORDS = [
    "市场情绪整体回暖",
    "全市场逾百股涨停",
    "做多氛围浓厚",
    "补涨机会",
    "反弹",
    "修复",
    "活跃",
    "涨停",
    "连板",
    "高开",
    "竞价涨停",
    "拿下2连板",
    "业绩超预期利好催化",
]

# 事件识别优先级（数字越小优先级越高）
EVENT_PRIORITY = [
    "regulatory",
    "reduce_holding",
    "unlock",
    "pledge",
    "litigation",
    "performance",
    "restructure",
    "inquiry",
    "order_contract",
    "buyback",
    "increase_holding",
    "policy",
    "product_tech",
    "capacity",
    "clarification",
    "abnormal_movement",
    "personnel",
    "process",
    "other",
]


def score_to_impact_level(score: float) -> str:
    abs_score = abs(score)
    if abs_score >= 4.0:
        return "critical"
    elif abs_score >= 3.0:
        return "strong"
    elif abs_score >= 1.5:
        return "medium"
    elif abs_score >= 0.3:
        return "weak"
    else:
        return "none"


def score_to_sentiment(score: float, positive_score: float = 0, negative_score: float = 0) -> str:
    if positive_score >= 1.5 and negative_score <= -1.5:
        if abs(negative_score) >= 3.0:
            return "negative"
        return "mixed"
    if score > 0.2:
        return "positive"
    elif score < -0.2:
        return "negative"
    else:
        return "neutral"
