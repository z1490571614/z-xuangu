"""主题别名标准化。

把新闻主题词、涨停原因自然语言统一到可比较的标准主题。
"""
import re
from typing import Dict, Iterable, List


GENERIC_THEMES = {
    "一带一路", "国企改革", "华为概念", "人工智能", "数字经济",
}


DEFAULT_ALIAS_RULES = [
    ("半导体洁净室", ("半导体", "芯片概念"), 1.0),
    ("半导体", ("半导体",), 1.0),
    ("芯片", ("芯片概念",), 1.0),
    ("AI算力", ("算力租赁", "人工智能", "数据中心"), 1.0),
    ("智算中心", ("算力租赁", "数据中心"), 1.0),
    ("算力", ("算力租赁", "人工智能"), 0.9),
    ("算力租赁", ("算力租赁",), 1.0),
    ("数据中心", ("数据中心",), 1.0),
    ("铜缆高速连接", ("铜缆高速连接", "CPO"), 1.0),
    ("PCB", ("PCB概念",), 1.0),
    ("印制电路板", ("PCB概念",), 1.0),
    ("商业航天", ("商业航天",), 1.0),
    ("卫星互联网", ("卫星互联网",), 1.0),
    ("海外EPC", ("一带一路",), 0.8),
    ("海外工程", ("一带一路",), 0.8),
    ("城市更新", ("城市更新",), 1.0),
    ("华为概念", ("华为概念",), 0.6),
    ("国企改革", ("国企改革",), 0.6),
    ("一带一路", ("一带一路",), 0.6),
    ("人工智能", ("人工智能",), 0.7),
]


class ThemeAliasResolver:
    """轻量主题标准化器，支持一个别名映射多个候选主题。"""

    def __init__(self, alias_rules: Iterable = None):
        self.alias_rules = list(alias_rules or DEFAULT_ALIAS_RULES)

    def resolve_text(self, text: str) -> List[Dict]:
        result: List[Dict] = []
        seen = set()
        for term in self._split_terms(text):
            for item in self.resolve_many(term):
                key = item["normalized_theme_name"]
                if key in seen:
                    continue
                result.append(item)
                seen.add(key)
        return result

    def resolve_many(self, alias_name: str) -> List[Dict]:
        alias_name = str(alias_name or "").strip()
        matches: List[Dict] = []
        for alias, names, weight in self.alias_rules:
            if alias and (alias in alias_name or alias_name in alias):
                for name in names:
                    matches.append(self._build(alias_name, name, weight))
        if matches:
            return matches
        return [self._build(alias_name, alias_name, 1.0)] if alias_name else []

    def resolve_one(self, alias_name: str) -> Dict:
        matches = self.resolve_many(alias_name)
        return matches[0] if matches else self._build("", "", 0.0)

    @staticmethod
    def _split_terms(text: str) -> List[str]:
        return [term.strip() for term in re.split(r"[+＋,，/、;；|｜\s]+", str(text or "")) if term.strip()]

    @staticmethod
    def _build(alias_name: str, normalized_name: str, weight: float) -> Dict:
        is_generic = normalized_name in GENERIC_THEMES
        return {
            "alias_name": alias_name,
            "normalized_theme_name": normalized_name,
            "weight": weight,
            "is_generic": is_generic,
            "penalty": -8 if is_generic else 0,
        }
