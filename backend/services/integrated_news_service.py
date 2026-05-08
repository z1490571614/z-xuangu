"""
集成新闻服务 - 优先从数据库获取，按需从API补充
"""
import os
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy import or_

from backend.services.news_database import (
    get_session, NewsData, NewsStockThemeAttribution, NewsThemeRelation
)
from backend.services.news_collector import get_news_collector
from backend.services.news_theme_extractor import NewsThemeExtractor
from backend.services.stock_alias_service import StockAliasService
from backend.services.theme_attribution_scorer import ThemeAttributionScorer
from backend.utils.trading_date import get_recent_trading_days

logger = logging.getLogger(__name__)


class IntegratedNewsService:
    """
    集成新闻服务 - 统一新闻获取接口
    优先从数据库获取，数据库数据不足时从API补充
    """

    def __init__(self):
        self.session = get_session()
        self.collector = get_news_collector()

    @staticmethod
    def _normalize_title(title: str) -> str:
        """归一化标题：去除标点符号和空格，转小写"""
        return re.sub(r'[^\w\u4e00-\u9fff]', '', title).lower()

    @staticmethod
    def _is_title_duplicate(norm1: str, norm2: str) -> bool:
        """判断两个归一化标题是否属于同一新闻

        匹配规则：
        1. 完全一致 → 重复
        2. 包含关系（较长的一方包含较短的一方，且长度比 ≥ 60%）→ 重复
        """
        if not norm1 or not norm2:
            return False
        if norm1 == norm2:
            return True
        if len(norm1) >= 5 and len(norm2) >= 5:
            shorter, longer = (norm1, norm2) if len(norm1) < len(norm2) else (norm2, norm1)
            if len(shorter) / len(longer) >= 0.6 and shorter in longer:
                return True
        return False

    def _deduplicate_cross_source(self, news_list: List[Dict]) -> List[Dict]:
        """跨源去重：同花顺和财联社报道相同新闻时，优先保留财联社

        来源优先级（越小越优先）：
          cls(财联社) → 0
          10jqka(同花顺) → 1
          other → 2

        去重依据：归一化标题精确匹配 + 标题包含关系
        """
        if not news_list:
            return []

        SOURCE_PRIORITY = {"cls": 0, "10jqka": 1}

        kept: List[Tuple[str, int]] = []   # (normalized_title, priority)
        result: List[Dict] = []

        for news in news_list:
            title = news.get("title", "")
            norm = self._normalize_title(title)
            source = news.get("source", "")
            priority = SOURCE_PRIORITY.get(source, 2)

            if not norm:
                result.append(news)
                continue

            found_dup = False
            for i, (kept_norm, kept_priority) in enumerate(kept):
                if self._is_title_duplicate(norm, kept_norm):
                    if priority < kept_priority:
                        kept[i] = (norm, priority)
                        result[i] = news
                    found_dup = True
                    break

            if not found_dup:
                kept.append((norm, priority))
                result.append(news)

        logger.info(
            f"跨源去重: {len(news_list)} → {len(result)} 条 "
            f"(去重掉 {len(news_list) - len(result)} 条)"
        )
        return result

    def get_stock_news_from_db(self, stock_name: str, limit: int = 20) -> List[Dict]:
        """
        从数据库获取指定股票的新闻

        Args:
            stock_name: 股票名称
            limit: 返回条数限制

        Returns:
            新闻列表（已跨源去重，优先保留财联社）
        """
        # 多取一些原始数据，确保去重后有足够的返回量
        raw_limit = limit * 3

        news_list = self.session.query(NewsData)\
            .filter(
                (NewsData.title.like(f"%{stock_name}%")) |
                (NewsData.content.like(f"%{stock_name}%"))
            )\
            .order_by(NewsData.publish_time.desc())\
            .limit(raw_limit)\
            .all()

        result = []
        for news in news_list:
            source_name = "财联社" if news.source == 'cls' else "同花顺" if news.source == '10jqka' else news.source

            pub_date = news.publish_time.strftime("%Y-%m-%d")

            result.append({
                "title": news.title,
                "content": news.content,
                "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": news.source,
                "source_name": source_name,
                "news_category": news.news_category,
                "sentiment_type": "",
                "sentiment_score": 0,
                "_pub_date": pub_date,
                "_content_preview": (news.content or "")[:80],
            })

        # 跨源去重：相同新闻保留财联社
        result = self._deduplicate_cross_source(result)

        # 清理内部字段 + 限制返回条数
        for item in result:
            item.pop("_pub_date", None)
            item.pop("_content_preview", None)

        return result[:limit]

    def extract_theme_relations_from_rows(
        self,
        rows: List[Any],
        stock_aliases: Dict[str, str],
        target_ts_code: Optional[str] = None,
    ) -> List[Dict]:
        """从新闻行中抽取目标股票相关的板块主题关系。

        该方法只服务板块归因，不参与个股新闻情感评分。
        """
        extractor = NewsThemeExtractor(stock_aliases)
        result: List[Dict] = []
        seen = set()

        for row in rows:
            publish_time = getattr(row, "publish_time", "")
            if hasattr(publish_time, "strftime"):
                publish_time = publish_time.strftime("%Y-%m-%d %H:%M:%S")
            news = {
                "id": getattr(row, "id", 0),
                "title": getattr(row, "title", "") or "",
                "content": getattr(row, "content", "") or "",
                "publish_time": publish_time,
                "source": getattr(row, "source", "") or "",
            }
            for relation in extractor.extract(news):
                if target_ts_code and relation.get("ts_code") != target_ts_code:
                    continue
                key = (
                    relation.get("news_id"),
                    relation.get("normalized_theme_name"),
                    relation.get("ts_code"),
                    relation.get("role"),
                    relation.get("action"),
                )
                if key in seen:
                    continue
                seen.add(key)
                result.append(relation)

        return result

    def build_theme_attribution_from_rows(
        self,
        rows: List[Any],
        ts_code: str,
        stock_name: str,
        trade_date: str,
        stock_aliases: Dict[str, str],
        lu_desc: str = "",
        hot_boards: Optional[List[Dict]] = None,
        static_concepts: Optional[List[str]] = None,
        selected_concepts: Optional[List[str]] = None,
        industry: str = "",
        force_refresh: bool = False,
    ) -> Dict:
        """基于新闻行构建股票主题归因结果。"""
        relations = self.extract_theme_relations_from_rows(
            rows,
            stock_aliases=stock_aliases,
            target_ts_code=ts_code,
        )
        attribution = ThemeAttributionScorer().score(
            ts_code=ts_code,
            stock_name=stock_name,
            trade_date=trade_date,
            lu_desc=lu_desc,
            news_relations=relations,
            hot_boards=hot_boards or [],
            static_concepts=static_concepts or [],
            selected_concepts=selected_concepts or [],
            industry=industry,
        )
        attribution["theme_relations"] = relations
        attribution["stock_sentiment_policy"] = "sector_news_neutral"
        attribution["explanation_lines"] = ThemeAttributionScorer.build_explanation_lines(attribution)
        return attribution

    def get_market_theme_news_rows(self, limit: int = 300) -> List[Any]:
        """读取近期板块盘面新闻候选。

        不按股票名过滤，避免漏掉“不在标题中、只在正文点名”的跟随股。
        """
        patterns = [
            "概念", "板块", "方向", "产业链", "赛道", "题材",
            "盘初", "早盘", "午后", "尾盘", "拉升", "走强",
            "走高", "活跃", "爆发", "回落", "走低", "跟涨", "跟跌",
        ]
        filters = []
        for pattern in patterns:
            filters.append(NewsData.title.like(f"%{pattern}%"))
            filters.append(NewsData.content.like(f"%{pattern}%"))

        return self.session.query(NewsData).filter(or_(*filters)).order_by(
            NewsData.publish_time.desc()
        ).limit(limit).all()

    def get_stock_theme_attribution(
        self,
        ts_code: str,
        stock_name: str,
        trade_date: str,
        limit: int = 300,
        ensure_recent: bool = True,
        lu_desc: str = "",
        hot_boards: Optional[List[Dict]] = None,
        static_concepts: Optional[List[str]] = None,
        selected_concepts: Optional[List[str]] = None,
        industry: str = "",
        force_refresh: bool = False,
    ) -> Dict:
        """获取个股板块主题归因。

        该接口面向“市场在炒什么”，不会改写个股新闻情感。
        """
        if ensure_recent:
            self.ensure_recent_data()

        cached_attribution = None if force_refresh else self.get_cached_stock_theme_attribution(ts_code, trade_date)
        if cached_attribution:
            cached_attribution["cache_hit"] = True
            cached_attribution["cache_level"] = "attribution"
            cached_attribution["scanned_news_count"] = 0
            return cached_attribution

        cached_relations = [] if force_refresh else self.get_cached_theme_relations(ts_code, trade_date)
        if cached_relations:
            attribution = self.build_theme_attribution_from_relations(
                cached_relations,
                ts_code=ts_code,
                stock_name=NewsThemeExtractor.normalize_stock_name(stock_name),
                trade_date=trade_date,
                lu_desc=lu_desc,
                hot_boards=hot_boards or [],
                static_concepts=static_concepts or [],
                selected_concepts=selected_concepts or [],
                industry=industry,
            )
            attribution["ts_code"] = ts_code
            attribution["stock_name"] = stock_name
            attribution["trade_date"] = trade_date
            attribution["scanned_news_count"] = 0
            attribution["cached_relation_count"] = len(cached_relations)
            attribution["cache_hit"] = True
            attribution["cache_level"] = "relations"
            self.save_stock_theme_attribution(attribution)
            return attribution

        rows = self.get_market_theme_news_rows(limit=limit)
        stock_aliases = StockAliasService.load_aliases()
        stock_aliases[NewsThemeExtractor.normalize_stock_name(stock_name)] = ts_code
        attribution = self.build_theme_attribution_from_rows(
            rows,
            ts_code=ts_code,
            stock_name=NewsThemeExtractor.normalize_stock_name(stock_name),
            trade_date=trade_date,
            stock_aliases=stock_aliases,
            lu_desc=lu_desc,
            hot_boards=hot_boards or [],
            static_concepts=static_concepts or [],
            selected_concepts=selected_concepts or [],
            industry=industry,
        )
        attribution["ts_code"] = ts_code
        attribution["stock_name"] = stock_name
        attribution["trade_date"] = trade_date
        attribution["scanned_news_count"] = len(rows)
        attribution["cache_hit"] = False
        attribution["cache_level"] = "miss"
        try:
            attribution["cached_relation_count"] = self.save_theme_relations(
                attribution.get("theme_relations", []),
                trade_date=trade_date,
            )
        except Exception as e:
            logger.warning(f"保存新闻主题关系失败，降级为仅返回实时结果: {e}")
            attribution["cached_relation_count"] = 0
        try:
            self.save_stock_theme_attribution(attribution)
        except Exception as e:
            logger.warning(f"保存股票主题归因失败，降级为仅返回实时结果: {e}")
        return attribution

    def build_theme_attribution_from_relations(
        self,
        relations: List[Dict],
        ts_code: str,
        stock_name: str,
        trade_date: str,
        lu_desc: str = "",
        hot_boards: Optional[List[Dict]] = None,
        static_concepts: Optional[List[str]] = None,
        selected_concepts: Optional[List[str]] = None,
        industry: str = "",
    ) -> Dict:
        attribution = ThemeAttributionScorer().score(
            ts_code=ts_code,
            stock_name=stock_name,
            trade_date=trade_date,
            lu_desc=lu_desc,
            news_relations=relations,
            hot_boards=hot_boards or [],
            static_concepts=static_concepts or [],
            selected_concepts=selected_concepts or [],
            industry=industry,
        )
        attribution["theme_relations"] = relations
        attribution["stock_sentiment_policy"] = "sector_news_neutral"
        attribution["explanation_lines"] = ThemeAttributionScorer.build_explanation_lines(attribution)
        return attribution

    def get_cached_theme_relations(self, ts_code: str, trade_date: str) -> List[Dict]:
        rows = self.session.query(NewsThemeRelation).filter(
            NewsThemeRelation.ts_code == ts_code,
            NewsThemeRelation.trade_date == trade_date,
        ).order_by(
            NewsThemeRelation.publish_time.desc(),
            NewsThemeRelation.confidence.desc(),
        ).all()
        return [self._theme_relation_to_dict(row) for row in rows]

    def save_stock_theme_attribution(self, attribution: Dict) -> int:
        ts_code = attribution.get("ts_code") or ""
        trade_date = attribution.get("trade_date") or ""
        if not ts_code or not trade_date:
            return 0

        row = self.session.query(NewsStockThemeAttribution).filter(
            NewsStockThemeAttribution.ts_code == ts_code,
            NewsStockThemeAttribution.trade_date == trade_date,
        ).first()
        if row is None:
            row = NewsStockThemeAttribution(ts_code=ts_code, trade_date=trade_date)
            self.session.add(row)

        row.stock_name = attribution.get("stock_name", "")
        row.primary_theme = attribution.get("primary_theme", "")
        row.theme_score = int(attribution.get("theme_score") or 0)
        row.confidence = attribution.get("confidence", "")
        row.candidate_themes_json = json.dumps(attribution.get("candidate_themes", []), ensure_ascii=False)
        row.evidence_list_json = json.dumps(attribution.get("evidence_list", []), ensure_ascii=False)
        row.explanation_lines_json = json.dumps(attribution.get("explanation_lines", []), ensure_ascii=False)
        row.stock_sentiment_policy = attribution.get("stock_sentiment_policy", "sector_news_neutral")
        row.updated_at = datetime.now()
        self.session.commit()
        return 1

    def get_cached_stock_theme_attribution(self, ts_code: str, trade_date: str) -> Optional[Dict]:
        row = self.session.query(NewsStockThemeAttribution).filter(
            NewsStockThemeAttribution.ts_code == ts_code,
            NewsStockThemeAttribution.trade_date == trade_date,
        ).first()
        if not row:
            return None
        return {
            "ts_code": row.ts_code,
            "stock_name": row.stock_name or "",
            "trade_date": row.trade_date,
            "primary_theme": row.primary_theme or "",
            "theme_score": row.theme_score or 0,
            "confidence": row.confidence or "",
            "candidate_themes": self._load_json_list(row.candidate_themes_json),
            "evidence_list": self._load_json_list(row.evidence_list_json),
            "explanation_lines": self._load_json_list(row.explanation_lines_json),
            "theme_relations": self.get_cached_theme_relations(ts_code, trade_date),
            "stock_sentiment_policy": row.stock_sentiment_policy or "sector_news_neutral",
        }

    @staticmethod
    def _load_json_list(value: str) -> List:
        if not value:
            return []
        try:
            data = json.loads(value)
            return data if isinstance(data, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def _theme_relation_to_dict(row: NewsThemeRelation) -> Dict:
        publish_time = row.publish_time.strftime("%Y-%m-%d %H:%M:%S") if row.publish_time else ""
        return {
            "news_id": row.news_id,
            "publish_time": publish_time,
            "source": row.source or "",
            "title": row.title or "",
            "theme_name": row.theme_name or "",
            "normalized_theme_name": row.normalized_theme_name or "",
            "stock_name": row.stock_name or "",
            "ts_code": row.ts_code or "",
            "role": row.role or "",
            "action": row.action or "",
            "action_strength": row.action_strength or 0,
            "time_phrase": row.time_phrase or "",
            "sentiment_for_theme": row.sentiment_for_theme or "",
            "confidence": row.confidence or 0,
            "credibility_level": row.credibility_level or "",
            "evidence": row.evidence or "",
        }

    def save_theme_relations(self, relations: List[Dict], trade_date: Optional[str] = None) -> int:
        """保存新闻主题关系，按新闻-主题-股票去重更新。"""
        saved = 0
        for relation in relations:
            news_id = int(relation.get("news_id") or 0)
            theme_name = relation.get("normalized_theme_name") or relation.get("theme_name") or ""
            ts_code = relation.get("ts_code") or ""
            if not news_id or not theme_name or not ts_code:
                continue

            row = self.session.query(NewsThemeRelation).filter(
                NewsThemeRelation.news_id == news_id,
                NewsThemeRelation.normalized_theme_name == theme_name,
                NewsThemeRelation.ts_code == ts_code,
            ).first()
            if row is None:
                row = NewsThemeRelation(
                    news_id=news_id,
                    normalized_theme_name=theme_name,
                    ts_code=ts_code,
                )
                self.session.add(row)

            publish_time = self._parse_datetime(relation.get("publish_time"))
            row.trade_date = trade_date or row.trade_date
            row.publish_time = publish_time
            row.source = relation.get("source", "")
            row.title = relation.get("title", "")
            row.theme_name = relation.get("theme_name", theme_name)
            row.stock_name = relation.get("stock_name", "")
            row.role = relation.get("role", "")
            row.action = relation.get("action", "")
            row.action_strength = int(relation.get("action_strength") or 0)
            row.time_phrase = relation.get("time_phrase", "")
            row.sentiment_for_theme = relation.get("sentiment_for_theme", "")
            row.confidence = float(relation.get("confidence") or 0)
            row.credibility_level = relation.get("credibility_level", "")
            row.evidence = relation.get("evidence", "")
            row.updated_at = datetime.now()
            saved += 1

        if saved:
            self.session.commit()
        return saved

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("/", "-"))
        except ValueError:
            return None

    def ensure_recent_data(self, days: int = 5):
        """
        确保每个新闻源都有最近N个交易日的数据（按5个交易日窗口补全）
        每个源独立检查，避免某个源的数据缺失影响其他源
        """
        recent_days = get_recent_trading_days(days)
        if not recent_days:
            logger.warning("无法获取交易日历")
            return

        sources_to_fetch = ["cls", "10jqka"]
        end_dt = datetime.now()

        for source in sources_to_fetch:
            # 独立检查每个源的最新发布时间
            latest_time = self.session.query(NewsData.publish_time)\
                .filter(NewsData.source == source)\
                .order_by(NewsData.publish_time.desc())\
                .first()

            if latest_time:
                latest_dt = latest_time if isinstance(latest_time, datetime) else latest_time[0]
                if (datetime.now() - latest_dt).total_seconds() < 3600:
                    logger.info(f"{source} 数据已更新（{latest_dt}），无需补充")
                    continue

            # 按5个交易日窗口扩展：从最早缺失时间或5天前开始
            if latest_time:
                start_dt = latest_dt - timedelta(hours=1)
            else:
                start_dt = end_dt - timedelta(days=days + 1)

            start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            logger.info(f"{source} 数据需要补充，时间范围: {start_str} ~ {end_str}")
            try:
                self.collector.fetch_historical_data(source, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"), segment_hours=6)
                logger.info(f"{source} 数据补充完成")
            except Exception as e:
                logger.error(f"补充{source}数据失败: {e}")

    def get_stock_news(self, stock_name: str, limit: int = 20, ensure_recent: bool = True) -> Dict[str, Any]:
        """
        获取指定股票的新闻（集成接口）
        
        Args:
            stock_name: 股票名称
            limit: 返回条数限制
            ensure_recent: 是否确保数据是最新的
            
        Returns:
            包含新闻列表和统计信息的字典
        """
        # 确保数据最新
        if ensure_recent:
            self.ensure_recent_data()

        # 从数据库获取新闻
        news_list = self.get_stock_news_from_db(stock_name, limit)

        # 统计来源分布
        source_counts = {}
        for news in news_list:
            source = news["source"]
            source_counts[source] = source_counts.get(source, 0) + 1

        return {
            "code": 200,
            "message": "success",
            "data": {
                "stock_name": stock_name,
                "news_list": news_list,
                "total_count": len(news_list),
                "source_distribution": source_counts,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    def get_news_count(self, source: Optional[str] = None) -> int:
        """获取数据库中新闻总数"""
        query = self.session.query(NewsData)
        if source:
            query = query.filter(NewsData.source == source)
        return query.count()

    def close(self):
        """关闭资源"""
        self.session.close()
        self.collector.close()


def get_integrated_news_service() -> IntegratedNewsService:
    """获取集成新闻服务实例"""
    return IntegratedNewsService()
