"""事件类型识别——先扫描所有候选事件，再按优先级选择"""

from typing import Dict, List, Tuple
from backend.services.news_sentiment.constants import EVENT_PRIORITY

# 各事件类型的识别关键词
EVENT_KEYWORDS: Dict[str, List[str]] = {
    "performance": [
        "业绩预告", "业绩快报", "年度报告", "年报", "一季报", "半年报", "三季报",
        "净利润", "归母净利润", "扣非净利润", "营业收入", "营收",
        "同比增长", "同比下降", "扭亏为盈", "预增", "预亏",
        "续亏", "减亏", "亏损扩大", "不及预期", "超预期",
    ],
    "restructure": [
        "重大资产重组", "重组", "并购", "收购", "资产注入",
        "借壳", "发行股份购买资产", "控制权变更",
        "终止重组", "重组失败", "重组方案调整",
    ],
    "reduce_holding": [
        "减持", "拟减持", "计划减持", "被动减持",
        "清仓式减持", "减持计划实施完毕",
    ],
    "increase_holding": [
        "增持", "拟增持", "计划增持", "增持完成", "已增持",
    ],
    "buyback": [
        "回购", "股份回购", "拟回购", "回购股份",
        "回购方案", "回购注销",
    ],
    "order_contract": [
        "中标", "签订合同", "签订", "重大合同", "订单", "采购合同",
        "销售合同", "供应协议", "框架协议",
    ],
    "regulatory": [
        "立案调查", "被立案", "行政处罚", "监管措施",
        "财务造假", "信息披露违法", "重大违法",
        "欺诈发行", "退市风险", "强制退市", "ST", "*ST",
    ],
    "inquiry": [
        "问询函", "年报问询函", "重组问询函", "关注函", "监管函",
        "问询回复",
    ],
    "risk_warning": [
        "风险提示公告", "交易风险提示", "股票交易风险提示",
        "交易风险", "二级市场交易风险", "业绩风险",
        "市净率远高于行业平均", "远高于行业平均水平",
        "股票价格短期波动较大", "股价短期波动较大",
        "审慎投资",
    ],
    "litigation": [
        "诉讼", "仲裁", "重大诉讼", "重大仲裁", "胜诉", "败诉",
    ],
    "unlock": [
        "解禁", "限售股解禁", "上市流通", "锁定期满",
    ],
    "pledge": [
        "质押", "补充质押", "解除质押", "质押比例",
    ],
    "policy": [
        "国务院", "国家级", "发改委", "工信部", "财政部",
        "地方政府", "地方政策", "政策支持",
    ],
    "product_tech": [
        "量产", "技术突破", "核心技术", "获得认证",
        "通过认证", "取得专利", "发布新产品", "新品发布",
    ],
    "capacity": [
        "正式投产", "建成投产", "试生产", "开工建设",
        "延期投产", "项目延期",
    ],
    "personnel": [
        "辞职", "离职", "聘任", "任命", "换届",
        "董事长辞职", "总经理辞职", "核心技术人员离职",
    ],
    "clarification": [
        "澄清", "传闻不属实", "报道不实", "不涉及", "未涉及",
    ],
    "abnormal_movement": [
        "严重异常波动", "交易异常波动",
    ],
    "process": [
        "召开股东大会", "股东大会", "召开董事会", "董事会决议",
        "监事会决议", "更正公告", "补充公告",
        "公司章程修订", "注册地址变更",
        "工商变更", "投资者关系活动记录表",
        "业绩说明会",
    ],
}


def classify_event_candidates(text: str) -> List[Tuple[str, int]]:
    """扫描文本，返回所有命中的事件类型候选列表（按优先级排序）"""
    candidates: Dict[str, int] = {}
    for event_type, keywords in EVENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                candidates[event_type] = candidates.get(event_type, 0) + 1
                break
    # 按优先级排序
    priority_map = {et: i for i, et in enumerate(EVENT_PRIORITY)}
    sorted_list = sorted(candidates.items(), key=lambda x: priority_map.get(x[0], 999))
    return sorted_list


def select_primary_event(candidates: List[Tuple[str, int]]) -> str:
    """从候选列表中选主事件（最高优先级）"""
    if not candidates:
        return "other"
    return candidates[0][0]
