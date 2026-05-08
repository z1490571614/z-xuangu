"""置信度计算"""
from typing import Dict, Any


def calculate_confidence(event_type: str, facts: Dict[str, Any], source: str = "", content_len: int = 0) -> float:
    confidence = 0.5
    if event_type != "other":
        confidence += 0.2
    if facts:
        has_value = any(v is not None and v is not False for v in facts.values())
        if has_value:
            confidence += 0.15
    if source in ["公司公告", "交易所公告"]:
        confidence += 0.1
    if content_len < 20:
        confidence -= 0.15
    return max(0.0, min(1.0, confidence))
