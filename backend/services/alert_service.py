"""
告警服务模块

提供基于阈值的告警和通知功能
"""
import logging
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ALERT_STATE: dict = {}


class AlertRule:
    def __init__(
        self,
        name: str,
        metric_name: str,
        threshold: float,
        comparison: str = "gt",
        cooldown: int = 300,
        message_template: str = "",
    ):
        self.name = name
        self.metric_name = metric_name
        self.threshold = threshold
        self.comparison = comparison
        self.cooldown = cooldown
        self.message_template = message_template or (
            f"告警: {name} - {metric_name} {{{{value}}}} {comparison} {threshold}"
        )

    def should_alert(self, value: float) -> bool:
        if self.comparison == "gt":
            return value > self.threshold
        elif self.comparison == "lt":
            return value < self.threshold
        elif self.comparison == "gte":
            return value >= self.threshold
        elif self.comparison == "lte":
            return value <= self.threshold
        elif self.comparison == "eq":
            return value == self.threshold
        return False

    def is_cooled_down(self) -> bool:
        last_alert = ALERT_STATE.get(self.name, 0)
        return (time.time() - last_alert) >= self.cooldown

    def mark_alerted(self):
        ALERT_STATE[self.name] = time.time()


DEFAULT_ALERT_RULES = [
    AlertRule(
        name="high_error_rate",
        metric_name="error_rate",
        threshold=5.0,
        comparison="gt",
        cooldown=300,
        message_template="告警: 错误率过高 - 当前 {value}% > 5%",
    ),
    AlertRule(
        name="high_response_time",
        metric_name="p95_response_time",
        threshold=2000.0,
        comparison="gt",
        cooldown=300,
        message_template="告警: P95响应时间过长 - 当前 {value}ms > 2000ms",
    ),
    AlertRule(
        name="api_down",
        metric_name="health_check",
        threshold=0.0,
        comparison="eq",
        cooldown=60,
        message_template="告警: API健康检查失败 - 服务可能不可用",
    ),
]


class AlertService:
    def __init__(self, rules: Optional[list] = None, webhook_url: Optional[str] = None):
        self.rules = rules or DEFAULT_ALERT_RULES
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self.client = httpx.Client(timeout=10.0)

    def check_and_alert(self, metric_name: str, value: float) -> bool:
        alerted = False
        for rule in self.rules:
            if rule.metric_name != metric_name:
                continue
            if rule.should_alert(value) and rule.is_cooled_down():
                message = rule.message_template.format(value=value)
                logger.warning(message)
                self._send_alert(message)
                rule.mark_alerted()
                alerted = True
        return alerted

    def _send_alert(self, message: str) -> bool:
        if not self.webhook_url:
            logger.warning(f"告警Webhook未配置，跳过发送: {message}")
            return False
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": "🚨 选股系统告警"},
                        "template": "red",
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "plain_text", "content": message},
                        },
                        {
                            "tag": "div",
                            "text": {
                                "tag": "plain_text",
                                "content": f"来源: 选股通知系统",
                            },
                        },
                    ],
                },
            }
            resp = self.client.post(self.webhook_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"告警已发送: {message}")
                return True
            else:
                logger.error(f"告警发送失败: status={resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"告警发送异常: {e}")
            return False

    def close(self):
        self.client.close()


alert_service = AlertService()
