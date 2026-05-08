"""股票-主题归因评分器。

整合涨停原因、新闻关系、热点榜和静态概念，输出主跟随题材及证据。
"""
from datetime import datetime
import re
from typing import Dict, Iterable, List, Optional

from backend.services.theme_alias_resolver import ThemeAliasResolver


class ThemeAttributionScorer:
    def __init__(self, resolver: Optional[ThemeAliasResolver] = None):
        self.resolver = resolver or ThemeAliasResolver()

    def score(
        self,
        ts_code: str,
        stock_name: str,
        trade_date: str,
        lu_desc: str = "",
        news_relations: Optional[List[Dict]] = None,
        hot_boards: Optional[List[Dict]] = None,
        static_concepts: Optional[Iterable[str]] = None,
        selected_concepts: Optional[Iterable[str]] = None,
        industry: str = "",
    ) -> Dict:
        buckets: Dict[str, Dict] = {}

        for theme in self.resolver.resolve_text(lu_desc):
            self._add(
                buckets, theme["normalized_theme_name"],
                35 + int(10 * theme.get("weight", 1.0)) + theme.get("penalty", 0),
                "涨停原因", f"涨停原因“{theme['alias_name']}”映射到{theme['normalized_theme_name']}",
                "涨停原因与标准主题匹配",
                priority=2,
            )

        for relation in news_relations or []:
            if relation.get("ts_code") and relation.get("ts_code") != ts_code:
                continue
            if relation.get("stock_name") and self._normalize_stock_name(relation.get("stock_name")) != self._normalize_stock_name(stock_name):
                continue
            theme_name = self.resolver.resolve_one(relation.get("normalized_theme_name", ""))["normalized_theme_name"]
            role = relation.get("role", "mentioned")
            base = 30 if relation.get("title") and theme_name in relation.get("title", "") else 22
            if role == "leader":
                base += 15
            elif role == "follow":
                base += 10
            elif role == "drag":
                base += 6
            base = int(base * self._time_decay(trade_date, relation.get("publish_time", "")))
            note = "板块归因证据，不构成个股利好/利空判断"
            if relation.get("credibility_level") == "low":
                base = int(base * 0.6)
                note = "复盘/点评类弱关系，仅作低权重参考"
            self._add(
                buckets, theme_name, base,
                "新闻主题关系",
                f"新闻《{relation.get('title', '')}》点名{stock_name}{relation.get('action', '')}",
                note,
                priority=3,
            )

        for board in hot_boards or []:
            theme_name = self.resolver.resolve_one(board.get("name", ""))["normalized_theme_name"]
            rank = int(board.get("rank", 999) or 999)
            score = 32 if rank <= 5 else 24 if rank <= 10 else 12
            if int(board.get("up_nums", 0) or 0) >= 5:
                score += 10
            self._add(
                buckets, theme_name, score,
                "热点榜", f"{board.get('name')}进入热点榜第{rank}名",
                "新闻/行业概览板块直接匹配，优先于个股成分概念",
                priority=3,
            )

        for concept in static_concepts or []:
            resolved = self.resolver.resolve_one(concept)
            self._add(
                buckets, resolved["normalized_theme_name"],
                8 + resolved.get("penalty", 0),
                "同花顺静态概念", f"静态概念包含{concept}",
                "静态归属仅作低权重参考",
                priority=1,
            )

        for concept in selected_concepts or []:
            resolved = self.resolver.resolve_one(concept)
            self._add(
                buckets, resolved["normalized_theme_name"],
                5 + resolved.get("penalty", 0),
                "选股概念字段", f"选股结果概念包含{concept}",
                "低权重补充证据",
                priority=1,
            )

        if industry:
            resolved = self.resolver.resolve_one(industry)
            self._add(
                buckets, resolved["normalized_theme_name"],
                3,
                "行业兜底", f"所属行业为{industry}",
                "行业兜底证据",
                priority=1,
            )

        min_priority = 2 if any(data.get("priority", 0) >= 2 for data in buckets.values()) else 0
        candidates = sorted(
            (
                {
                    "theme_name": name,
                    "score": max(0, data["score"]),
                    "priority": data.get("priority", 0),
                    "evidence": data["evidence"][:5],
                }
                for name, data in buckets.items()
                if name and data.get("priority", 0) >= min_priority
            ),
            key=lambda item: (item["priority"], item["score"]),
            reverse=True,
        )

        primary = candidates[0] if candidates else {"theme_name": "", "score": 0, "evidence": []}
        return {
            "primary_theme": primary["theme_name"],
            "theme_score": primary["score"],
            "evidence_list": primary["evidence"],
            "candidate_themes": candidates[:5],
            "confidence": self._confidence(primary["score"]),
        }

    @staticmethod
    def build_explanation_lines(attribution: Dict) -> List[str]:
        primary_theme = attribution.get("primary_theme") or ""
        if not primary_theme:
            return ["暂无明确主跟随题材"]

        lines = [f"主跟随题材：{primary_theme}"]
        for item in attribution.get("evidence_list", [])[:5]:
            detail = item.get("detail", "")
            note = item.get("note", "")
            if detail:
                lines.append(detail)
            if note and note not in lines:
                lines.append(note)

        candidates = [
            f"{item.get('theme_name')}({item.get('score')}分)"
            for item in attribution.get("candidate_themes", [])[1:4]
            if item.get("theme_name")
        ]
        if candidates:
            lines.append("候选题材：" + "、".join(candidates))
        return lines

    @staticmethod
    def _add(
        buckets: Dict[str, Dict],
        theme_name: str,
        score: int,
        source: str,
        detail: str,
        note: str,
        priority: int = 0,
    ) -> None:
        if not theme_name:
            return
        bucket = buckets.setdefault(theme_name, {"score": 0, "priority": 0, "evidence": []})
        bucket["score"] += score
        bucket["priority"] = max(bucket.get("priority", 0), priority)
        bucket["evidence"].append({
            "source": source,
            "score": score,
            "priority": priority,
            "detail": detail,
            "note": note,
        })

    @staticmethod
    def _confidence(score: int) -> str:
        if score >= 60:
            return "high"
        if score >= 35:
            return "medium"
        if score > 0:
            return "low"
        return "none"

    @staticmethod
    def _normalize_stock_name(name: str) -> str:
        return re.sub(r"\s+", "", str(name or ""))

    @staticmethod
    def _time_decay(trade_date: str, publish_time: str) -> float:
        if not trade_date or not publish_time:
            return 1.0
        try:
            trade = datetime.strptime(str(trade_date), "%Y%m%d").date()
            published = datetime.fromisoformat(str(publish_time).replace("/", "-")).date()
        except ValueError:
            return 1.0
        days = (trade - published).days
        if days <= 0:
            return 1.0
        if days == 1:
            return 0.7
        if days <= 3:
            return 0.4
        return 0.0
