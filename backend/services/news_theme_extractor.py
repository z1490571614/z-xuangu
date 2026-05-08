"""
新闻主题关系抽取器

用于从板块/概念盘面新闻中抽取：
- 主题/板块名
- 盘面动作
- 被点名股票及其角色
- 时间短语与强度

注意：这里不判断个股新闻利好/利空，只做“新闻 -> 主题 -> 股票”的关系归因。
"""
import re
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple


MARKET_NEWS_HINTS = (
    "板块", "概念", "方向", "产业链", "赛道", "题材", "盘初", "早盘",
    "午后", "尾盘", "拉升", "走强", "走高", "活跃", "爆发", "回落", "走低",
    "领涨", "领跌", "跟涨", "跟跌", "涨停", "跌停", "涨超", "跌超",
    "强势", "连板",
)

POSITIVE_ACTIONS = (
    "涨停", "封板", "涨超", "大涨", "拉升", "走强", "活跃", "爆发",
    "领涨", "续涨", "高开", "反弹", "冲高", "收涨", "跟涨", "强势", "连板",
)

NEGATIVE_ACTIONS = (
    "跌停", "跌超", "大跌", "回落", "走低", "领跌", "下挫", "跳水",
    "低开", "收跌", "跟跌", "承压", "回调",
)

TIME_PHRASES = (
    "盘前", "盘初", "开盘", "早盘", "午后", "尾盘", "盘中", "收盘",
    "昨日", "今日", "近几日", "全天",
)

THEME_STOP_PREFIXES = (
    "美股", "港股", "A股", "今日", "昨日", "盘面上", "板块题材上",
    "相关ETF方面", "消息面上", "截至收盘", "截至", "午评：", "收评：",
    "其中", "带动", "早盘", "盘初", "午后", "尾盘",
    "多家半导体公司一季报强劲推动",
)


@dataclass
class NewsThemeRelation:
    news_id: int
    publish_time: str
    source: str
    title: str
    theme_name: str
    normalized_theme_name: str
    stock_name: str
    ts_code: str
    role: str
    action: str
    action_strength: int
    time_phrase: str
    sentiment_for_theme: str
    confidence: float
    credibility_level: str
    evidence: str


class NewsThemeExtractor:
    """轻量规则抽取器，先覆盖新闻库中的高频板块盘面表达。"""

    def __init__(self, stock_aliases: Optional[Dict[str, str]] = None, include_unmapped_stocks: bool = False):
        # key 为无空格股票名，value 为 ts_code
        self.stock_aliases = stock_aliases or {}
        self.include_unmapped_stocks = include_unmapped_stocks

    @staticmethod
    def normalize_stock_name(name: str) -> str:
        return re.sub(r"\s+", "", str(name or ""))

    @staticmethod
    def normalize_theme_name(name: str) -> str:
        name = str(name or "").strip(" ，。、；;:：")
        for prefix in THEME_STOP_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):]
        replacements = {
            "PCB概念股": "PCB概念",
            "PCB方向": "PCB概念",
            "CPO方向": "CPO",
            "AI产业链方向": "AI产业链",
            "AI应用软件股": "AI应用",
            "算力租赁领域": "算力租赁",
            "半导体板块": "半导体",
            "光通信板块": "光通信",
        }
        return replacements.get(name, name)

    def is_market_theme_news(self, title: str, content: str) -> bool:
        text = f"{title or ''}。{content or ''}"
        return sum(1 for word in MARKET_NEWS_HINTS if word in text) >= 2

    def extract(self, news: Dict) -> List[Dict]:
        title = self._safe_title(news)
        content = str(news.get("content") or "")
        text = f"{title}。{content}"

        if not self.is_market_theme_news(title, content):
            return []

        relations = self._extract_sentence_relations(news, title, content)
        if relations:
            return [asdict(r) for r in relations]

        themes = self._extract_themes(text)
        stocks = self._extract_stocks(text)
        if not themes and not stocks:
            return []

        actions = self._extract_actions(text)
        time_phrase = self._extract_time_phrase(text)
        sentiment = self._theme_sentiment(actions)
        strength = self._action_strength(text, actions, len(stocks))

        if not themes:
            return []

        fallback_relations: List[NewsThemeRelation] = []
        for stock_name, ts_code, evidence in stocks:
            role = self._infer_role(stock_name, text)
            action = self._infer_stock_action(stock_name, text, actions)
            for theme in themes[:4]:
                confidence = self._confidence(theme, stock_name, role, action, text)
                fallback_relations.append(NewsThemeRelation(
                    news_id=int(news.get("id") or 0),
                    publish_time=str(news.get("publish_time") or ""),
                    source=str(news.get("source") or ""),
                    title=title,
                    theme_name=theme,
                    normalized_theme_name=self.normalize_theme_name(theme),
                    stock_name=stock_name,
                    ts_code=ts_code,
                    role=role,
                    action=action,
                    action_strength=strength,
                    time_phrase=time_phrase,
                    sentiment_for_theme=sentiment,
                    confidence=confidence,
                    credibility_level=self._credibility_level(role, action, title),
                    evidence=evidence,
                ))

        return [asdict(r) for r in fallback_relations]

    def _extract_sentence_relations(self, news: Dict, title: str, content: str) -> List[NewsThemeRelation]:
        relations: List[NewsThemeRelation] = []
        text = f"{title}。{content}"
        last_themes: List[str] = []

        for sentence in self._split_sentences(text):
            themes = self._extract_themes(sentence)
            if themes:
                last_themes = themes
            elif self._can_inherit_theme(sentence):
                themes = last_themes

            stocks = self._extract_stocks(sentence)
            if not themes or not stocks:
                continue

            actions = self._extract_actions(sentence)
            time_phrase = self._extract_time_phrase(sentence)
            sentiment = self._theme_sentiment(actions)
            strength = self._action_strength(sentence, actions, len(stocks))

            for stock_name, ts_code, evidence in stocks:
                role = self._infer_role(stock_name, sentence)
                action = self._infer_stock_action(stock_name, sentence, actions)
                for theme in themes[:3]:
                    confidence = self._confidence(theme, stock_name, role, action, sentence)
                    relations.append(NewsThemeRelation(
                        news_id=int(news.get("id") or 0),
                        publish_time=str(news.get("publish_time") or ""),
                        source=str(news.get("source") or ""),
                        title=title,
                        theme_name=theme,
                        normalized_theme_name=self.normalize_theme_name(theme),
                        stock_name=stock_name,
                        ts_code=ts_code,
                        role=role,
                        action=action,
                        action_strength=strength,
                        time_phrase=time_phrase,
                        sentiment_for_theme=sentiment,
                        confidence=confidence,
                        credibility_level=self._credibility_level(role, action, title),
                        evidence=evidence,
                    ))

        return relations

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        parts = re.split(r"[。；;！!\n]+", str(text or ""))
        return [part.strip(" ，,") for part in parts if part.strip(" ，,")]

    @staticmethod
    def _can_inherit_theme(sentence: str) -> bool:
        return sentence.startswith(("其中", "此外", "另一方面", "板块方面"))

    def _safe_title(self, news: Dict) -> str:
        title = str(news.get("title") or "").strip()
        if title.lower() == "nan" or not title:
            content = str(news.get("content") or "")
            m = re.search(r"【([^】]{4,80})】", content)
            if m:
                return m.group(1)
            return content[:60]
        return title

    def _extract_themes(self, text: str) -> List[str]:
        themes: List[str] = []

        # 例：PCB概念股盘初拉升、半导体板块延续涨势、AI产业链方向表现活跃
        for pattern in (
            r"([\u4e00-\u9fa5A-Za-z0-9]+?)(?:概念股|概念|板块|方向|产业链|赛道)(?:盘初|开盘|早盘|午后|尾盘|延续|集体|表现|走势|再度|短线|持续|整体|全天|收盘|走强|走高|活跃|拉升|回落|走低|爆发|领涨|领跌)",
            r"(?:板块题材上|盘面上)[，,]([^。；;]+?)(?:涨幅居前|跌幅居前|表现活跃|领涨|领跌)",
            r"([^。；;，,]+?)(?:ETF|指数).*?(?:涨超|上涨|收涨|回调|下跌)",
        ):
            for m in re.finditer(pattern, text):
                chunk = m.group(1)
                for item in re.split(r"[、,，/和及]+", chunk):
                    item = self.normalize_theme_name(item)
                    if self._is_valid_theme(item):
                        themes.append(item)

        return self._dedup(themes)[:8]

    def _extract_stocks(self, text: str) -> List[Tuple[str, str, str]]:
        found: List[Tuple[str, str, str]] = []
        normalized_text = self.normalize_stock_name(text)

        for alias, ts_code in self.stock_aliases.items():
            if alias and alias in normalized_text:
                evidence = self._window(text, alias)
                found.append((alias, ts_code, evidence))

        if not self.include_unmapped_stocks:
            return found[:30]

        # 补充抽取无法映射 ts_code 的显式股票名：东阳光涨停、合力泰跟涨、ARM跌近8%
        explicit_patterns = (
            r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})(?:20%涨停|涨停|封板|跌停|涨超\d+%|跌超\d+%|涨近\d+%|跌近\d+%|跟涨|跟跌|高开|低开)",
            r"(?:，|、)([\u4e00-\u9fa5A-Za-z0-9]{2,12})(?:、|，|跟涨|跟跌)",
        )
        known = {name for name, _, _ in found}
        for pattern in explicit_patterns:
            for m in re.finditer(pattern, text):
                name = self.normalize_stock_name(m.group(1))
                if not self._is_valid_stock_name(name) or name in known:
                    continue
                found.append((name, self.stock_aliases.get(name, ""), self._window(text, name)))
                known.add(name)

        return found[:30]

    def _extract_actions(self, text: str) -> List[str]:
        actions = [a for a in POSITIVE_ACTIONS + NEGATIVE_ACTIONS if a in text]
        percent_actions = re.findall(r"(?:涨超|跌超|涨近|跌近)\d+(?:\.\d+)?%", text)
        return self._dedup(actions + percent_actions)

    def _extract_time_phrase(self, text: str) -> str:
        for phrase in TIME_PHRASES:
            if phrase in text:
                return phrase
        return ""

    def _theme_sentiment(self, actions: Iterable[str]) -> str:
        actions = list(actions)
        if any(a in NEGATIVE_ACTIONS or str(a).startswith(("跌超", "跌近")) for a in actions):
            if not any(a in POSITIVE_ACTIONS or str(a).startswith(("涨超", "涨近")) for a in actions):
                return "negative"
        if any(a in POSITIVE_ACTIONS or str(a).startswith(("涨超", "涨近")) for a in actions):
            return "positive"
        return "neutral"

    def _action_strength(self, text: str, actions: List[str], stock_count: int) -> int:
        strength = 1
        if "涨停" in text or "跌停" in text:
            strength += 2
        if re.search(r"涨超(?:10|[2-9]\d)%|跌超(?:10|[2-9]\d)%", text):
            strength += 2
        elif re.search(r"涨超\d+%|跌超\d+%", text):
            strength += 1
        if stock_count >= 5:
            strength += 1
        if "ETF" in text or "成交额" in text or "放量" in text:
            strength += 1
        return min(strength, 5)

    def _infer_role(self, stock_name: str, text: str) -> str:
        segment = self._segment(text, stock_name)
        window = self._window(text, stock_name, size=28)
        target_first = f"{stock_name}"

        if any(word in segment for word in ("跟涨", "涨超", "涨近", "冲高", "高开")):
            return "follow"
        if any(word in segment for word in ("跟跌", "跌超", "跌近", "回落", "走低", "下挫")):
            return "drag"
        if re.search(rf"{re.escape(target_first)}[^，。；;、]{{0,8}}\d+天\d+板", window):
            return "leader"
        if re.search(rf"{re.escape(target_first)}[^，。；;、]{{0,8}}(?:20%涨停|涨停|封板|连板)", window):
            return "leader"
        if any(word in window for word in ("龙头", "高标", "核心", "领涨", "率先")):
            return "leader"
        return "mentioned"

    def _infer_stock_action(self, stock_name: str, text: str, fallback_actions: List[str]) -> str:
        segment = self._segment(text, stock_name)
        window = self._window(text, stock_name, size=28)
        for action in ("跟涨", "跟跌", "涨超", "跌超", "涨近", "跌近", "高开", "低开", "回落", "走低"):
            if action in segment:
                return action
        if re.search(rf"{re.escape(stock_name)}[^，。；;、]{{0,8}}\d+天\d+板", window):
            return "连板"
        if re.search(rf"{re.escape(stock_name)}[^，。；;、]{{0,8}}(?:20%涨停|涨停|封板|跌停)", window):
            for action in ("20%涨停", "涨停", "封板", "跌停"):
                if action in window:
                    return action
        for action in ("20%涨停", "涨停", "封板", "跌停", "涨超", "跌超", "涨近", "跌近", "跟涨", "跟跌", "高开", "低开", "回落", "走低"):
            if action in window:
                return action
        return fallback_actions[0] if fallback_actions else ""

    def _segment(self, text: str, keyword: str) -> str:
        normalized_keyword = self.normalize_stock_name(keyword)
        normalized_text = self.normalize_stock_name(text)
        idx = normalized_text.find(normalized_keyword)
        if idx < 0:
            return self._window(text, keyword, size=30)
        start = max(
            normalized_text.rfind("，", 0, idx),
            normalized_text.rfind("。", 0, idx),
            normalized_text.rfind("；", 0, idx),
            normalized_text.rfind("！", 0, idx),
            normalized_text.rfind("？", 0, idx),
        )
        end_candidates = [
            pos for pos in (
                normalized_text.find("，", idx + len(normalized_keyword)),
                normalized_text.find("。", idx + len(normalized_keyword)),
                normalized_text.find("；", idx + len(normalized_keyword)),
                normalized_text.find("！", idx + len(normalized_keyword)),
                normalized_text.find("？", idx + len(normalized_keyword)),
            ) if pos >= 0
        ]
        end = min(end_candidates) if end_candidates else min(len(normalized_text), idx + len(normalized_keyword) + 30)
        return normalized_text[start + 1:end]

    def _confidence(self, theme: str, stock_name: str, role: str, action: str, text: str) -> float:
        score = 0.35
        if theme and theme != "未识别主题":
            score += 0.2
        if stock_name in self.normalize_stock_name(text):
            score += 0.2
        if role in ("leader", "follow", "drag"):
            score += 0.15
        if action:
            score += 0.1
        return round(min(score, 0.95), 2)

    @staticmethod
    def _credibility_level(role: str, action: str, title: str = "") -> str:
        low_credibility_titles = (
            "行情回顾", "昨日行情回顾", "人气板块及个股点评", "个股点评",
            "复盘", "午评", "收评", "盘面回顾", "市场焦点股", "新闻精选",
        )
        if any(marker in str(title or "") for marker in low_credibility_titles):
            return "low"
        if role in ("leader", "follow", "drag") and action:
            return "medium"
        return "low"

    def _window(self, text: str, keyword: str, size: int = 60) -> str:
        normalized_keyword = self.normalize_stock_name(keyword)
        normalized_text = self.normalize_stock_name(text)
        idx = normalized_text.find(normalized_keyword)
        if idx < 0:
            idx = text.find(keyword)
        if idx < 0:
            return text[:size]
        start = max(0, idx - size)
        end = min(len(text), idx + len(keyword) + size)
        return text[start:end]

    @staticmethod
    def _is_valid_theme(theme: str) -> bool:
        if not theme or len(theme) < 2 or len(theme) > 20:
            return False
        bad = ("截至", "标的指数", "联接基金", "换手", "成交额", "成份股中")
        bad += ("三大", "指数", "ETF", "基金", "配置价值", "投资价值", "科创50")
        return not any(word in theme for word in bad)

    @staticmethod
    def _is_valid_stock_name(name: str) -> bool:
        if not name or len(name) < 2 or len(name) > 12:
            return False
        bad = ("财联社", "同花顺", "相关ETF", "消息面", "今日", "昨日", "板块", "概念", "方向", "指数", "成交额")
        return not any(word in name for word in bad)

    @staticmethod
    def _dedup(items: Iterable[str]) -> List[str]:
        seen = set()
        result = []
        for item in items:
            item = str(item or "").strip()
            if item and item not in seen:
                result.append(item)
                seen.add(item)
        return result
