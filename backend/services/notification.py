"""
飞书通知服务
"""
import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class FeishuNotifier:
    """飞书通知器 - 使用同步HTTP客户端避免事件循环冲突"""

    def __init__(self, webhook_url: Optional[str] = None):
        """
        初始化飞书通知器

        Args:
            webhook_url: 飞书 Webhook URL，如果为None则从环境变量获取
        """
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("飞书 Webhook URL 未配置，通知功能将不可用")

        self.max_retries = 3
        self.retry_delay = 5

    def build_selection_message(
        self,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        构建选股结果消息

        Args:
            result: 选股结果

        Returns:
            飞书消息体
        """
        trade_date = result.get('trade_date', '')
        passed_count = result.get('passed_count', 0)
        stocks = result.get('stocks', [])

        if passed_count == 0:
            return {
                "msg_type": "text",
                "content": {
                    "text": f"📊 【选股通知】{trade_date}\n\n今日未选出符合条件的股票"
                }
            }

        content_lines = [
            f"📊 **【选股通知】{trade_date}**",
            f"",
            f"🎯 共选出 **{passed_count}** 只股票",
            f"",
            f"---",
            f""
        ]

        for i, stock in enumerate(stocks[:10], 1):
            ts_code = stock.get('ts_code', '')
            name = stock.get('name', '未知')
            close = stock.get('close', 0) or stock.get('close_price', 0)
            change_pct = stock.get('change_pct', 0)
            circ_mv = stock.get('circ_mv', 0)
            rule_score = stock.get('rule_score')
            score_level = stock.get('score_level', '')
            reasons = stock.get('reasons', [])
            risk_tags = stock.get('risk_tags', [])

            change_emoji = "📈" if change_pct and change_pct > 0 else "📉"

            line = f"**{i}. {name}** ({ts_code})\n"
            line += f"   💰 {close:.2f}元 | {change_emoji} {change_pct:.2f}%"
            if rule_score is not None:
                line += f" | ⭐ 评分: {rule_score:.1f} **{score_level}**"
            if circ_mv:
                line += f"\n   📊 流通市值: {circ_mv:.2f}亿"
            if reasons:
                top_reasons = reasons[:3]
                line += f"\n   📌 {'; '.join(top_reasons)}"
            if risk_tags:
                line += f"\n   ⚠️ 风险: {', '.join(risk_tags[:3])}"

            content_lines.append(line)
            content_lines.append("")

        if passed_count > 10:
            content_lines.append(
                f"_... 还有 {passed_count - 10} 只股票未显示_"
            )

        content = "\n".join(content_lines)

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"选股结果 - {trade_date}"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"执行时间: {result.get('execution_time', 0):.2f}秒"
                            }
                        ]
                    }
                ]
            }
        }

    def send_message(
        self,
        message: Dict[str, Any]
    ) -> bool:
        """
        发送消息 (使用同步HTTP客户端，避免事件循环冲突)

        Args:
            message: 消息体

        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            logger.warning("Webhook URL 未配置，跳过发送")
            return False

        import requests
        import time

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=message,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('StatusCode') == 0:
                        logger.info("飞书消息发送成功")
                        return True
                    else:
                        logger.error(f"飞书消息发送失败: {result}")
                else:
                    logger.error(
                        f"飞书消息发送失败，状态码: {response.status_code}"
                    )

            except requests.exceptions.Timeout:
                logger.warning(f"飞书消息发送超时 (尝试 {attempt + 1}/{self.max_retries})")

            except requests.exceptions.ConnectionError as e:
                logger.error(f"飞书消息连接失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            except Exception as e:
                logger.error(f"飞书消息发送异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        return False

    async def send_message_async(
        self,
        message: Dict[str, Any]
    ) -> bool:
        """
        异步发送消息 (内部调用同步方法)

        Args:
            message: 消息体

        Returns:
            是否发送成功
        """
        return self.send_message(message)

    def send_selection_result(self, result: Dict[str, Any]) -> bool:
        """
        发送选股结果通知

        Args:
            result: 选股结果

        Returns:
            是否发送成功
        """
        message = self.build_selection_message(result)
        return self.send_message(message)

    async def send_test_notification(self) -> bool:
        """
        发送测试通知

        Returns:
            是否发送成功
        """
        message = {
            "msg_type": "text",
            "content": {
                "text": "🔔 选股通知系统测试消息\n\n如果您收到此消息，说明飞书通知配置正确！"
            }
        }
        return await self.send_message_async(message)
