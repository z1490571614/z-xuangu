"""政策题材/产品技术/产能投产/人事变动/流程公告/澄清公告/交易异常波动规则"""
from typing import Dict, Any


def score_policy(text: str) -> float:
    if "国务院" in text or "国家级" in text:
        return 2.0
    if "发改委" in text or "工信部" in text or "财政部" in text:
        return 1.5
    if "地方政府" in text or "地方政策" in text:
        return 0.8
    return 0.5


def score_product_tech(text: str) -> float:
    score = 0.0
    if "量产" in text:
        score += 1.5
    if "技术突破" in text or "核心技术" in text:
        score += 1.2
    if "获得认证" in text or "通过认证" in text:
        score += 0.8
    if "取得专利" in text:
        score += 0.5
    if "发布新产品" in text or "新品发布" in text:
        score += 0.5
    if "尚未产生收入" in text or "尚未形成收入" in text:
        score *= 0.4
    return score


def score_capacity(text: str) -> float:
    if "正式投产" in text or "建成投产" in text:
        return 1.5
    if "试生产" in text:
        return 1.0
    if "开工建设" in text:
        return 0.5
    if "延期投产" in text or "项目延期" in text:
        return -1.5
    return 0.0


def score_personnel(text: str) -> float:
    if "董事长辞职" in text or "总经理辞职" in text:
        return -0.8
    if "核心技术人员离职" in text:
        return -1.5
    if "财务负责人辞职" in text:
        return -1.0
    if "聘任" in text or "任命" in text:
        return 0.1
    return 0.0


def score_clarification(text: str) -> float:
    if "不涉及" in text or "未涉及" in text:
        return -1.0
    if "传闻不属实" in text or "报道不实" in text:
        return 0.3
    return 0.0


def score_abnormal_movement(text: str) -> float:
    if "严重异常波动" in text:
        return -0.8
    if "交易异常波动" in text:
        return -0.3
    if "不存在应披露而未披露的重大事项" in text:
        return 0.0
    return 0.0


def score_process(text: str) -> float:
    return 0.0
