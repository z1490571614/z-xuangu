"""
统一AI客户端接口 - 方便切换豆包/通义/DeepSeek/OpenAI
使用 OpenAI SDK 兼容格式对接火山方舟等 API

环境变量：
  ARK_API_KEY         - 火山方舟 API Key（https://console.volcengine.com/ark/region:ark+cn-beijing/apikey）
  ARK_MODEL          - 模型名，默认 doubao-seed-2-0-mini-260215
  AI_BRIEF_TIMEOUT   - 超时秒数，默认 15
"""
import os
import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict
from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger(__name__)

# AI请求全局限流：最多3个并发，避免火山方舟API限流超时
_ai_semaphore = threading.Semaphore(int(os.getenv("AI_MAX_CONCURRENT", "3")))


class AIClient(ABC):
    """统一AI客户端抽象接口"""

    @abstractmethod
    def generate_json(self, prompt: str, schema: Optional[dict] = None, use_semaphore: bool = True) -> dict:
        """调用AI并返回结构化JSON"""
        pass

    @property
    @abstractmethod
    def available(self) -> bool:
        """AI客户端是否可用"""
        pass


class DoubaoClient(AIClient):
    """火山方舟豆包 API 客户端（使用 OpenAI SDK）"""

    def __init__(self):
        self.api_key = os.getenv("ARK_API_KEY", "")
        self.model = os.getenv("ARK_MODEL", "doubao-seed-2-0-mini-260215")
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.timeout = int(os.getenv("AI_BRIEF_TIMEOUT", "60"))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, prompt: str, schema: Optional[dict] = None, use_semaphore: bool = True) -> dict:
        if not self.available:
            raise RuntimeError("火山方舟 API Key 未配置。请设置 ARK_API_KEY 环境变量。")

        sem_acquired = False
        if use_semaphore:
            sem_acquired = _ai_semaphore.acquire(timeout=120)
            if not sem_acquired:
                raise RuntimeError("AI请求排队超时（系统负载过高），请稍后重试")

        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=1,
            )

            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个结构化的股票分析助手。请严格按照要求的 JSON 格式输出。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            }

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content
            if not content:
                raise RuntimeError("AI 返回内容为空")
            result = json.loads(content)
            if isinstance(result, str):
                result = json.loads(result)
            if not isinstance(result, dict):
                raise RuntimeError(f"AI 返回格式异常: 期望dict, 得到{type(result).__name__}")
            return result

        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI返回JSON解析失败: {e}")
        except ImportError:
            raise RuntimeError("openai SDK 未安装，请执行: pip install openai")
        except Exception as e:
            raise RuntimeError(f"AI调用失败: {e}")
        finally:
            if sem_acquired:
                _ai_semaphore.release()


class OpenAIClient(AIClient):
    """OpenAI 兼容客户端（通用回退方案）"""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.timeout = int(os.getenv("AI_BRIEF_TIMEOUT", "15"))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, prompt: str, schema: Optional[dict] = None, use_semaphore: bool = True) -> dict:
        if not self.available:
            raise RuntimeError("OpenAI API Key 未配置")

        sem_acquired = False
        if use_semaphore:
            sem_acquired = _ai_semaphore.acquire(timeout=120)
            if not sem_acquired:
                raise RuntimeError("AI请求排队超时（系统负载过高），请稍后重试")

        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )

            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个结构化的股票分析助手。请严格按照要求的 JSON 格式输出。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            }
            if schema:
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content
            if not content:
                raise RuntimeError("AI 返回内容为空")
            result = json.loads(content)
            if isinstance(result, str):
                result = json.loads(result)
            if not isinstance(result, dict):
                raise RuntimeError(f"AI 返回格式异常")
            return result

        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI返回JSON解析失败: {e}")
        except ImportError:
            raise RuntimeError("openai SDK 未安装，请执行: pip install openai")
        except Exception as e:
            raise RuntimeError(f"AI调用失败: {e}")
        finally:
            if sem_acquired:
                _ai_semaphore.release()


def get_ai_client() -> AIClient:
    """获取可用的AI客户端（优先使用火山方舟豆包）"""
    doubao = DoubaoClient()
    if doubao.available:
        logger.info("使用火山方舟豆包AI客户端 (ARK_API_KEY)")
        return doubao

    openai = OpenAIClient()
    if openai.available:
        logger.info("使用OpenAI兼容客户端")
        return openai

    logger.warning("无可用AI客户端（未配置 ARK_API_KEY 或 OPENAI_API_KEY）")
    return doubao