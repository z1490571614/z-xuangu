"""
异动解读提示词构建器
"""
import json
from typing import Dict, Any, List


class AnomalyPromptBuilder:
    """构建异动解读的AI提示词"""

    NEGATIVE_KEYWORDS = [
        "亏损", "预亏", "业绩下滑", "净利润下降", "营收下降", "扣非亏损",
        "商誉减值", "资产减值", "计提减值", "债务违约", "资金链",
        "st", "退市", "立案调查", "监管函", "处罚", "罚款",
        "减持", "质押", "冻结", "诉讼", "仲裁", "违约",
        "毛利率下降", "现金流为负", "应付账款", "应收账款",
        "行业下行", "需求萎缩", "产能过剩", "价格战",
    ]

    @staticmethod
    def build(input_data: Dict[str, Any]) -> str:
        """
        构建完整的异动解读提示词
        
        Args:
            input_data: 包含股票新闻、行情等数据的字典
        
        Returns:
            完整的提示词字符串
        """
        stock = input_data.get("stock", {})
        news_list = input_data.get("news_list", [])
        market_data = input_data.get("market_data", {})

        prompt = f"""你是同花顺异动解读AI，严格按以下规则输出，不要多余文字。
综合分析近3个交易日该股票的新闻舆情数据，识别**所有**对股价有影响的催化因素。

【股票基本信息】
股票代码：{stock.get('stock_code', '')}
股票名称：{stock.get('stock_name', '')}
交易日期：{stock.get('trade_date', '')}

【行情背景】
{AnomalyPromptBuilder._format_market_data(market_data)}

【核心规则】
1. core_tags_line：最多3个核心标签，用"+"连接
   示例：算力租赁+业绩暴增+高送转
2. industry_reason：一段文字，说明行业/板块宏观驱动原因
3. company_reasons：数组，每条是一条公司原因
   每条必须包含：日期、事件、核心数据
   最多4条，按时间倒序
   必须覆盖**所有**新闻类别，尤其是：
   - 🚨 业绩利空/负面消息必须放在第一条重点分析
   - 📈 正面业绩/中标/订单也要说明
   - 📋 公司公告、行业政策变动
4. 禁止出现涨停、连板、封板、竞价抢筹等技术面词汇作为核心原因
5. 技术面词汇只能作为行情背景

【重要约束】
- 仔细阅读每一条新闻的完整正文
- 对于负面/利空新闻（如业绩亏损、利润下降等），必须在 company_reasons 第一条体现
- 如果新闻明确提到"亏损""下降""下滑"等负面关键词，必须识别为利空
- 不要遗漏任何有数据支撑的新闻内容"""

        if news_list:
            prompt += f"\n\n【个股新闻/公告（共{len(news_list)}条）】\n"
            prompt += AnomalyPromptBuilder._format_news_list(news_list)
        else:
            prompt += "\n\n【个股新闻/公告】\n暂无近3个交易日的个股新闻数据"

        prompt += """

【输出JSON格式】
{
    "core_tags_line": "",
    "industry_reason": "",
    "company_reasons": []
}

请直接输出JSON，不要有其他文字说明。"""

        return prompt

    @staticmethod
    def _format_market_data(market_data: Dict[str, Any]) -> str:
        if not market_data:
            return "暂无行情数据"

        parts = []
        if market_data.get("price"):
            parts.append(f"竞价价格：{market_data['price']}元")
        if market_data.get("pct_chg") is not None:
            parts.append(f"涨跌幅：{market_data['pct_chg']:.2f}%")
        if market_data.get("circ_mv"):
            parts.append(f"流通市值：{market_data['circ_mv']}亿")

        return "；".join(parts) if parts else "暂无行情数据"

    @staticmethod
    def _format_news_list(news_list: List[Dict[str, Any]]) -> str:
        if not news_list:
            return "暂无新闻数据"

        parts = []
        for idx, news in enumerate(news_list[:20], 1):
            title = news.get("title", "")
            content = news.get("content", "")
            publish_time = news.get("publish_time", "")
            source_name = news.get("source_name", "")
            sentiment_type = news.get("sentiment_type", "")
            sentiment_score = news.get("sentiment_score")

            # 情感标签
            sentiment_tag = ""
            if sentiment_type == "negative":
                sentiment_tag = "[利空]"
            elif sentiment_type == "positive":
                sentiment_tag = "[利好]"

            # 关键字检测（补充分类）
            title_lower = title.lower()
            content_lower = content.lower()[:200]
            keyword_tag = ""
            for kw in AnomalyPromptBuilder.NEGATIVE_KEYWORDS:
                if kw in title or kw in content_lower:
                    keyword_tag = "🚨 负面关键词匹配"
                    break

            news_str = f"{idx}. "
            if publish_time:
                news_str += f"[{str(publish_time)[:10]}] "
            if sentiment_tag:
                news_str += f"{sentiment_tag} "
            if keyword_tag:
                news_str += f"{keyword_tag} "
            if source_name:
                news_str += f"({source_name}) "
            if title:
                news_str += f"\n   标题：{title}"
            if content:
                # 传完整正文（最多500字）
                content_excerpt = content[:500]
                news_str += f"\n   正文：{content_excerpt}{'...' if len(content) > 500 else ''}"

            parts.append(news_str)

        return "\n\n".join(parts)
