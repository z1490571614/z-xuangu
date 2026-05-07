"""
Tushare 新闻服务 - 基于 Tushare news 接口封装
优化版：三级去重 + 双校验情感分类 + 真实交易日历
"""
import os
import logging
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import tushare as ts

from backend.utils.trading_date import get_date_range_for_trading_days
from backend.utils.tushare_client import get_tushare_pro, get_tushare_token

logger = logging.getLogger(__name__)


# ==========================================
# SimHash 实现 (用于内容相似度去重)
# ==========================================
def _hash_func(token):
    """简单的哈希函数"""
    return int(hashlib.md5(token.encode()).hexdigest(), 16)


class SimHash:
    """SimHash 计算类"""
    
    def __init__(self, text, bits=64):
        self.bits = bits
        self.value = self._compute(text)
    
    def _tokenize(self, text):
        """简单分词（按字符或2-gram）"""
        text = str(text).lower()
        # 使用2-gram分词
        tokens = []
        for i in range(len(text) - 1):
            tokens.append(text[i:i+2])
        return tokens
    
    def _compute(self, text):
        """计算SimHash值"""
        v = [0] * self.bits
        tokens = self._tokenize(text)
        
        for token in tokens:
            h = _hash_func(token)
            for i in range(self.bits):
                bitmask = 1 << i
                if h & bitmask:
                    v[i] += 1
                else:
                    v[i] -= 1
        
        fingerprint = 0
        for i in range(self.bits):
            if v[i] >= 0:
                fingerprint |= 1 << i
        return fingerprint
    
    @staticmethod
    def hamming_distance(hash1, hash2):
        """计算汉明距离"""
        x = hash1 ^ hash2
        dist = 0
        while x:
            dist += 1
            x &= x - 1
        return dist


# ==========================================
# 新闻服务主类
# ==========================================
class TushareNewsService:
    """Tushare 新闻搜索服务"""

    # 类级别的内存缓存（跨实例共享）
    _news_cache = {}  # key: f"{ts_code}_{trade_date}", value: {result, timestamp}
    _cache_timeout = 300  # 缓存超时时间（秒），5分钟

    def __init__(self, token: Optional[str] = None):
        # 优先使用传入的 token，否则从环境变量获取
        self.token = get_tushare_token(token)
        
        self._available = False
        self._pro = None
        
        if self.token:
            try:
                cache_path = os.getenv("TUSHARE_CACHE_PATH", "./data/tushare_cache")
                os.makedirs(cache_path, exist_ok=True)
                os.environ['TUSHARE_PRO_SAVE_PATH'] = cache_path
                
                self._pro = get_tushare_pro(self.token)
                self._available = True
                logger.info(f"Tushare 新闻服务初始化成功，缓存目录: {cache_path}")
                logger.info(f"Tushare Token: {self.token[:20]}...")
            except Exception as e:
                logger.warning(f"Tushare 初始化失败: {e}")
                self._available = False
                self._pro = None

    @property
    def available(self) -> bool:
        return self._available and self._pro is not None
    
    def _get_cache_key(self, ts_code: str, trade_date: str) -> str:
        """生成缓存key"""
        return f"{ts_code}_{trade_date}"
    
    def _get_cached_result(self, ts_code: str, trade_date: str):
        """获取缓存结果"""
        key = self._get_cache_key(ts_code, trade_date)
        cached = self._news_cache.get(key)
        if cached:
            timestamp = cached.get("timestamp", 0)
            if datetime.now().timestamp() - timestamp < self._cache_timeout:
                logger.info(f"使用新闻缓存: {ts_code} {trade_date}")
                return cached.get("result")
            else:
                logger.info(f"缓存已过期，重新获取: {ts_code} {trade_date}")
                del self._news_cache[key]
        return None
    
    def _set_cache_result(self, ts_code: str, trade_date: str, result):
        """保存缓存结果"""
        key = self._get_cache_key(ts_code, trade_date)
        self._news_cache[key] = {
            "result": result,
            "timestamp": datetime.now().timestamp()
        }
        logger.info(f"新闻缓存已保存: {ts_code} {trade_date}")
    
    # ==========================================
    # 工具方法
    # ==========================================
    def _get_date_range(self, trade_date: str = None, days: int = 3) -> tuple:
        """获取日期范围，基于真实交易日历计算"""
        # 使用增强的交易日工具获取包含N个交易日的日期范围
        return get_date_range_for_trading_days(days, trade_date)
    
    def _compute_title_hash(self, title: str) -> str:
        """计算标题MD5哈希"""
        return hashlib.md5(str(title).encode()).hexdigest()
    
    def _compute_content_simhash(self, content: str) -> int:
        """计算内容SimHash"""
        return SimHash(content).value
    
    def _compute_event_id(self, news: Dict) -> str:
        """计算事件ID（用于同事件多轮推送去重）"""
        title = str(news.get("title", ""))
        # 提取标题中"："前面的部分作为事件标识
        event_key_part = title.split("：")[0].split(":")[0] if title else ""
        # 取发布日期的日期部分
        publish_date = str(news.get("publish_time", "")).split(" ")[0]
        event_key = f"{event_key_part}_{publish_date}"
        return hashlib.md5(event_key.encode()).hexdigest()
    
    # ==========================================
    # 三级去重逻辑
    # ==========================================
    def _deduplicate_news(self, news_list: List[Dict]) -> List[Dict]:
        """
        三级去重：
        1. 一级：标题哈希去重
        2. 二级：内容SimHash去重（汉明距离<3视为重复）
        3. 三级：事件ID去重（同事件只保留最新）
        """
        if not news_list:
            return []
        
        # ========== 第一步：先统计各源的数量 ==========
        source_count_before = {}
        for news in news_list:
            src = news.get("source", "unknown")
            source_count_before[src] = source_count_before.get(src, 0) + 1
        logger.info(f"去重前各源数量: {source_count_before}")
        
        # ========== 第二步：按时间排序（最新的在前） ==========
        # 纯粹按时间排序，不考虑来源优先级
        def sort_key(news):
            time_str = news.get("publish_time", "")
            # 返回 -时间戳，这样排序后时间新的在前
            return -int(time_str.replace("-", "").replace(":", "").replace(" ", "")) if time_str else 0
        
        news_list = sorted(news_list, key=sort_key)
        
        # 一级去重：标题哈希
        seen_title_hashes = set()
        dedup1 = []
        for news in news_list:
            title_hash = self._compute_title_hash(news.get("title", ""))
            if title_hash not in seen_title_hashes:
                seen_title_hashes.add(title_hash)
                news["title_hash"] = title_hash
                dedup1.append(news)
        
        # 二级去重：内容SimHash
        seen_simhashes = []
        dedup2 = []
        for news in dedup1:
            content = news.get("content", "") or news.get("title", "")
            simhash_val = self._compute_content_simhash(content)
            # 检查是否与已有的SimHash足够相似
            is_duplicate = False
            for seen_hash in seen_simhashes:
                if SimHash.hamming_distance(simhash_val, seen_hash) < 3:
                    is_duplicate = True
                    break
            if not is_duplicate:
                seen_simhashes.append(simhash_val)
                news["content_simhash"] = simhash_val
                dedup2.append(news)
        
        # 三级去重：事件ID
        seen_event_ids = set()
        final_dedup = []
        for news in dedup2:
            event_id = self._compute_event_id(news)
            if event_id not in seen_event_ids:
                seen_event_ids.add(event_id)
                news["event_id"] = event_id
                final_dedup.append(news)
        
        # 统计去重后各源的数量
        source_count_after = {}
        for news in final_dedup:
            src = news.get("source", "unknown")
            source_count_after[src] = source_count_after.get(src, 0) + 1
        
        logger.info(f"去重完成：原始{len(news_list)}条 → 最终{len(final_dedup)}条")
        logger.info(f"去重后各源数量: {source_count_after}")
        return final_dedup
    
    # ==========================================
    # 新闻类型分类
    # ==========================================
    def _classify_news_category(self, news: Dict, stock_name: Optional[str] = None) -> str:
        """
        分类新闻类型：个股/行业/市场
        """
        title = str(news.get("title", "")).lower()
        content = str(news.get("content", "")).lower()
        text = title + " " + content
        
        # 市场新闻关键词
        market_keywords = ["竞价", "大盘", "沪指", "深指", "创业板", "上证指数", "深证成指", 
                          "a股", "股市", "行情", "市场", "开盘", "收盘", "涨停潮", "跌停潮"]
        # 行业新闻关键词
        industry_keywords = ["板块", "行业", "概念", "产业链", "半导体", "新能源", "人工智能", 
                            "医药", "消费", "金融", "地产", "科技"]
        
        # 检查是否是个股新闻（如果提供了股票名称）
        if stock_name and stock_name in text:
            return "个股"
        
        # 检查是否是市场新闻
        for kw in market_keywords:
            if kw in text:
                return "市场"
        
        # 检查是否是行业新闻
        for kw in industry_keywords:
            if kw in text:
                return "行业"
        
        # 默认按个股处理
        return "个股"
    
    # ==========================================
    # 规则层情感分类
    # ==========================================
    def _rule_based_sentiment(self, news: Dict, stock_sector: Optional[str] = None) -> str:
        """
        规则层情感分类——已废弃，情感模块改为拉取时实时分析
        """
        return ""
    
    # ==========================================
    # AI层情感分类（可选，用于复杂场景）
    # ==========================================
    def _ai_sentiment_check(self, news: Dict, stock_name: Optional[str] = None, 
                           stock_sector: Optional[str] = None) -> str:
        """
        AI二次校验情感分类（降级策略：如果AI不可用则使用规则层结果）
        """
        try:
            from backend.services.ai_brief.ai_client import get_ai_client
            ai_client = get_ai_client()
            
            if not ai_client.available:
                logger.debug("AI客户端不可用，使用规则层结果")
                return self._rule_based_sentiment(news, stock_sector)
            
            # 构建提示词
            category = news.get("news_category", "个股")
            title = news.get("title", "")
            content = news.get("content", "")
            
            prompt = f"""
你是专业的股票新闻情感分析师，请严格按照以下规则判断新闻情感：

1. 新闻类型：{category}
2. 相关股票：{stock_name or '未提供'}
3. 所属板块：{stock_sector or '未提供'}

情感判断规则：
- 利好(positive)：对个股或相关板块有明显正面影响
- 利空(negative)：对个股或相关板块有明显负面影响
- 中性(neutral)：无明显影响，或只是市场/行情描述

特别注意：
- 仅判断"对个股股价的影响"，禁止将"涨停/连板/竞价"等技术面表述误判为利好
- 市场分析类新闻（如竞价看龙头、大盘点评）一律标"中性"
- 行业新闻仅当与个股所属板块直接相关时，才标利好/利空，否则中性

新闻标题：{title}
新闻内容：{content}

请仅输出一个词：positive / negative / neutral
"""
            
            # 调用AI
            result = ai_client.generate_json(prompt)
            sentiment = result.get("sentiment", "neutral") if isinstance(result, dict) else str(result).strip().lower()
            
            # 验证输出
            if sentiment not in ["positive", "negative", "neutral"]:
                sentiment = "neutral"
            
            return sentiment
            
        except Exception as e:
            logger.debug(f"AI情感分类失败，使用规则层: {e}")
            return self._rule_based_sentiment(news, stock_sector)
    
    # ==========================================
    # 双校验情感分类（主入口）
    # ==========================================
    def _classify_sentiment(self, news: Dict, stock_name: Optional[str] = None,
                           stock_sector: Optional[str] = None, use_ai: bool = False) -> Dict:
        """
        双校验情感分类：规则层 + 可选AI层
        返回：{sentiment_type, confidence}
        """
        # 规则层
        rule_result = self._rule_based_sentiment(news, stock_sector)
        
        # AI层（可选）
        if use_ai:
            ai_result = self._ai_sentiment_check(news, stock_name, stock_sector)
            if rule_result == ai_result:
                confidence = 1.0
                final_sentiment = rule_result
            else:
                confidence = 0.7
                final_sentiment = ai_result  # 复杂场景信任AI
        else:
            final_sentiment = rule_result
            confidence = 0.8
        
        return {
            "sentiment_type": final_sentiment,
            "sentiment_confidence": confidence
        }
    
    # ==========================================
    # 新闻获取与处理
    # ==========================================
    def _fetch_news_from_source(self, source: str, start_date: str, end_date: str) -> List[Dict]:
        """从指定源获取新闻"""
        try:
            df = self._pro.news(src=source, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return []
            
            news_list = []
            for _, row in df.iterrows():
                news_list.append({
                    "title": str(row.get("title", "")),
                    "content": str(row.get("content", "")),
                    "url": str(row.get("url", "")),
                    "publish_time": str(row.get("datetime", "")),
                    "source": source
                })
            
            logger.info(f"从 {source} 获取到 {len(news_list)} 条新闻")
            return news_list
            
        except Exception as e:
            logger.warning(f"从 {source} 获取新闻失败: {e}")
            return []
    
    def _filter_by_stock(self, news_list: List[Dict], stock_name: str) -> List[Dict]:
        """按股票名称过滤新闻"""
        if not stock_name:
            return news_list
        
        filtered = []
        stock_name_lower = stock_name.lower()
        
        # 统计过滤前各源的数量
        before_source_count = {}
        for news in news_list:
            src = news.get("source", "unknown")
            before_source_count[src] = before_source_count.get(src, 0) + 1
        
        logger.info(f"股票过滤前各源: {before_source_count}")
        
        for news in news_list:
            title = str(news.get("title", "")).lower()
            content = str(news.get("content", "")).lower()
            if stock_name_lower in title or stock_name_lower in content:
                filtered.append(news)
        
        # 统计过滤后各源的数量
        after_source_count = {}
        for news in filtered:
            src = news.get("source", "unknown")
            after_source_count[src] = after_source_count.get(src, 0) + 1
        
        logger.info(f"股票过滤后各源: {after_source_count}")
        logger.info(f"股票过滤结果: 保留 {len(filtered)} 条，过滤掉 {len(news_list) - len(filtered)} 条")
        
        return filtered
    
    # ==========================================
    # 公共API
    # ==========================================
    def get_stock_news_v2(
        self,
        ts_code: str,
        stock_name: Optional[str] = None,
        trade_date: Optional[str] = None,
        limit: int = 20,
        use_ai: bool = False,
        deduplicate: bool = True,
        stock_sector: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        V2版获取个股新闻（已去重+情感分类）
        
        Args:
            ts_code: 股票代码
            stock_name: 股票名称
            trade_date: 交易日期
            limit: 返回条数
            use_ai: 是否使用AI二次校验
            deduplicate: 是否去重
            stock_sector: 所属板块（用于行业新闻情感判断）
        
        Returns:
            {
                code: 200/500,
                message: str,
                data: {
                    news_list: [...],
                    sentiment_count: {positive: x, negative: y, neutral: z},
                    source_status: str
                }
            }
        """
        if not self.available:
            return {
                "code": 500,
                "message": "Tushare Token未配置",
                "data": {
                    "news_list": [],
                    "sentiment_count": {"positive": 0, "negative": 0, "neutral": 0},
                    "source_status": "TUSHARE_UNAVAILABLE"
                }
            }
        
        # 检查缓存
        cached_result = self._get_cached_result(ts_code, trade_date)
        if cached_result:
            return cached_result
        
        try:
            start_date, end_date = self._get_date_range(trade_date=trade_date, days=5)
            logger.info(f"获取新闻时间范围: {start_date} 到 {end_date}")
            
            # 获取新闻（多个源）
            all_news = []
            sources = ["cls", "10jqka"]  # 财联社 + 同花顺
            source_counts = {}
            source_titles = {}  # 保存每个源的标题用于调试
            
            for source in sources:
                news_from_source = self._fetch_news_from_source(source, start_date, end_date)
                source_counts[source] = len(news_from_source)
                source_titles[source] = [n["title"][:30] for n in news_from_source[:3]]  # 前3条标题
                all_news.extend(news_from_source)
                logger.info(f"从 {source} 获取到 {len(news_from_source)} 条原始新闻")
                if news_from_source:
                    logger.info(f"  前3条标题: {source_titles[source]}")
            
            logger.info(f"总共获取到 {len(all_news)} 条原始新闻: {source_counts}")
            
            # 按股票过滤
            if stock_name:
                before_filter = len(all_news)
                all_news = self._filter_by_stock(all_news, stock_name)
                logger.info(f"按股票名 [{stock_name}] 过滤后: {len(all_news)} 条 (过滤掉 {before_filter - len(all_news)} 条)")
            
            # 去重
            if deduplicate:
                before_dedup = len(all_news)
                all_news = self._deduplicate_news(all_news)
                logger.info(f"去重后: {len(all_news)} 条 (去重掉 {before_dedup - len(all_news)} 条)")
            
            # 处理每条新闻：分类 + 情感分析
            processed_news = []
            for news in all_news:
                # 新闻类型分类
                category = self._classify_news_category(news, stock_name)
                news["news_category"] = category
                
                # 情感分类
                sentiment_result = self._classify_sentiment(news, stock_name, stock_sector, use_ai)
                news["sentiment_type"] = sentiment_result["sentiment_type"]
                news["sentiment_confidence"] = sentiment_result["sentiment_confidence"]
                
                processed_news.append(news)
            
            # 按时间排序，取前limit条
            processed_news = sorted(processed_news, 
                                   key=lambda x: x.get("publish_time", ""), 
                                   reverse=True)[:limit]
            
            # 统计情感分布
            sentiment_count = {
                "positive": 0,
                "negative": 0,
                "neutral": 0
            }
            for news in processed_news:
                st = news.get("sentiment_type", "neutral")
                if st in sentiment_count:
                    sentiment_count[st] += 1
            
            result = {
                "code": 200,
                "message": "success",
                "data": {
                    "news_list": processed_news,
                    "sentiment_count": sentiment_count,
                    "source_status": "OK",
                    "ts_code": ts_code,
                    "stock_name": stock_name
                }
            }
            
            # 保存缓存
            self._set_cache_result(ts_code, trade_date, result)
            
            return result
            
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return {
                "code": 500,
                "message": str(e),
                "data": {
                    "news_list": [],
                    "sentiment_count": {"positive": 0, "negative": 0, "neutral": 0},
                    "source_status": "ERROR"
                }
            }
    
    # ==========================================
    # 兼容旧版API
    # ==========================================
    def search(self, query: str, limit: int = 10, trade_date: str = None) -> Dict[str, Any]:
        """搜索财经新闻（兼容旧版）"""
        if not self.available:
            return {
                "success": False,
                "articles": [],
                "total": 0,
                "error": "TUSHARE_TOKEN 未配置",
            }

        try:
            start_date, end_date = self._get_date_range(trade_date=trade_date)
            
            all_articles = []
            sources = ["cls"]
            
            for src in sources:
                try:
                    df = self._pro.news(src=src, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            title = str(row.get("title", ""))
                            content = str(row.get("content", ""))
                            if query in title or query in content:
                                sentiment = "neutral"  # 简化版
                                all_articles.append({
                                    "title": title,
                                    "summary": content if content else title,
                                    "url": "",
                                    "publish_time": row.get("datetime", ""),
                                    "source": "财联社",
                                    "sentiment": sentiment,
                                })
                except Exception as e:
                    logger.warning(f"Tushare新闻源 {src} 获取失败: {e}")
                    continue
            
            all_articles.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
            all_articles = all_articles[:limit]
            
            return {
                "success": True,
                "articles": all_articles,
                "total": len(all_articles),
                "error": "",
            }
            
        except Exception as e:
            logger.error(f"Tushare新闻搜索异常: {e}")
            return {"success": False, "articles": [], "total": 0, "error": str(e)}
    
    def search_stock_news(
        self,
        ts_code: str,
        stock_name: Optional[str] = None,
        limit: int = 10,
        trade_date: str = None,
    ) -> Dict[str, Any]:
        """搜索特定股票的新闻（兼容旧版）"""
        if not stock_name:
            logger.warning("search_stock_news 需要提供 stock_name 参数")
            return {"success": False, "articles": [], "total": 0, "error": "缺少股票名称"}
        
        result = self.get_stock_news_v2(ts_code, stock_name, trade_date, limit, use_ai=False)
        
        if result["code"] == 200:
            # 转换为旧版格式
            articles = []
            for news in result["data"]["news_list"]:
                articles.append({
                    "title": news["title"],
                    "summary": news.get("content", "") or news["title"],
                    "url": news.get("url", ""),
                    "publish_time": news.get("publish_time", ""),
                    "source": news.get("source", ""),
                    "sentiment": news.get("sentiment_type", "neutral")
                })
            return {
                "success": True,
                "articles": articles,
                "total": len(articles),
                "error": ""
            }
        else:
            return {"success": False, "articles": [], "total": 0, "error": result["message"]}
    
    def search_announcements(self, query: str, limit: int = 10, trade_date: str = None) -> Dict[str, Any]:
        """搜索公司公告（兼容旧版）"""
        if not self.available:
            return {"success": False, "articles": [], "total": 0, "error": "未配置"}
        
        try:
            start_date, end_date = self._get_date_range(trade_date=trade_date)
            articles = []
            source = "10jqka"
            
            try:
                df = self._pro.news(src=source, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        title = str(row.get("title", ""))
                        content = str(row.get("content", ""))
                        if query in title or query in content:
                            articles.append({
                                "title": title,
                                "summary": content if content else title,
                                "url": "",
                                "publish_time": row.get("datetime", ""),
                                "source": "同花顺",
                                "sentiment": "neutral",
                            })
            except Exception as e:
                logger.warning(f"Tushare公告源 {source} 获取失败: {e}")
            
            articles.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
            articles = articles[:limit]
            
            return {
                "success": True,
                "articles": articles,
                "total": len(articles),
                "error": "",
            }
            
        except Exception as e:
            logger.warning(f"Tushare公告搜索失败: {e}")
            return {"success": False, "articles": [], "total": 0, "error": str(e)}
    
    def search_research_reports(self, query: str, limit: int = 10, trade_date: str = None) -> Dict[str, Any]:
        """搜索研报（兼容旧版）"""
        if not self.available:
            return {"success": False, "articles": [], "total": 0, "error": "未配置"}
        
        try:
            start_date, end_date = self._get_date_range(trade_date=trade_date)
            df = self._pro.research_report(start_date=start_date[:10], end_date=end_date[:10])
            
            articles = []
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    title = str(row.get("title", ""))
                    if query in title:
                        articles.append({
                            "title": title,
                            "summary": str(row.get("content", ""))[:200],
                            "url": row.get("pdf_url", ""),
                            "publish_time": row.get("pub_date", ""),
                            "source": row.get("org_name", "券商"),
                            "sentiment": "neutral",
                        })
            
            articles.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
            articles = articles[:limit]
            
            return {
                "success": True,
                "articles": articles,
                "total": len(articles),
                "error": "",
            }
            
        except Exception as e:
            logger.warning(f"Tushare研报搜索失败: {e}")
            return {"success": False, "articles": [], "total": 0, "error": str(e)}


# ==========================================
# 单例实例
# ==========================================
_news_service: Optional[TushareNewsService] = None


def get_news_service() -> TushareNewsService:
    global _news_service
    if _news_service is None:
        _news_service = TushareNewsService()
    return _news_service
