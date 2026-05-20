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

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _fmt_pct(cls, value: Any, digits: int = 2) -> str:
        num = cls._float_or_none(value)
        if num is None:
            return "--"
        return f"{num:.{digits}f}%"

    @classmethod
    def _sort_by_t0_limit_prob(cls, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            stocks,
            key=lambda stock: cls._float_or_none(stock.get("default_t0_limit_prob")) or -1,
            reverse=True,
        )

    @staticmethod
    def _limit_tag(stock: Dict[str, Any]) -> str:
        return stock.get("lu_tag") or stock.get("lu_status") or "--"

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

        sorted_stocks = self._sort_by_t0_limit_prob(stocks)
        content_lines = [
            f"**【选股通知】{trade_date}**",
            "",
            f"共选出 **{passed_count}** 只股票，按当日涨停概率从高到低排序。",
            "",
        ]

        for i, stock in enumerate(sorted_stocks, 1):
            ts_code = stock.get('ts_code', '')
            name = stock.get('name', '未知')
            line = f"**{i}. {name} {ts_code}**\n"
            line += (
                f"涨停标签：{self._limit_tag(stock)} | "
                f"开涨幅：{self._fmt_pct(stock.get('open_change_pct'))} | "
                f"昨涨幅：{self._fmt_pct(stock.get('pre_change_pct'))} | "
                f"当日涨停概率：{self._fmt_pct(stock.get('default_t0_limit_prob'), 1)}"
            )

            content_lines.append(line)
            content_lines.append("")

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
