"""
异动解读输出验证器
"""
import json
from typing import Dict, Any, List, Tuple


class OutputValidator:
    """验证AI输出是否符合要求的格式"""

    @staticmethod
    def validate(result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证输出格式是否正确
        
        Args:
            result: AI返回的结果字典
        
        Returns:
            (是否有效, 错误信息)
        """
        # 检查必要字段
        required_fields = ["core_tags_line", "industry_reason", "company_reasons"]
        for field in required_fields:
            if field not in result:
                return False, f"缺少必要字段: {field}"

        # 验证 core_tags_line
        core_tags = result.get("core_tags_line", "")
        if not isinstance(core_tags, str):
            return False, "core_tags_line 必须是字符串"
        if len(core_tags) > 255:
            return False, "core_tags_line 长度不能超过255字符"

        # 验证 industry_reason
        industry_reason = result.get("industry_reason", "")
        if not isinstance(industry_reason, str):
            return False, "industry_reason 必须是字符串"

        # 验证 company_reasons
        company_reasons = result.get("company_reasons", [])
        if not isinstance(company_reasons, list):
            return False, "company_reasons 必须是数组"
        if len(company_reasons) > 4:
            return False, "company_reasons 最多4条"
        for idx, reason in enumerate(company_reasons, 1):
            if not isinstance(reason, str):
                return False, f"company_reasons 第{idx}条必须是字符串"
            if not reason.startswith(f"{idx}、"):
                # 如果格式不对，尝试修正
                pass

        return True, ""

    @staticmethod
    def sanitize(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理和修正输出
        
        Args:
            result: AI返回的结果
        
        Returns:
            清理后的结果
        """
        cleaned = {}

        # 清理 core_tags_line
        core_tags = result.get("core_tags_line", "")
        # 确保用+连接，最多3个标签
        if core_tags:
            tags = [t.strip() for t in core_tags.replace(" ", "+").split("+") if t.strip()]
            cleaned["core_tags_line"] = "+".join(tags[:3])
        else:
            cleaned["core_tags_line"] = "无明确催化"

        # 清理 industry_reason
        cleaned["industry_reason"] = result.get("industry_reason", "行业整体数据正常，无重大政策或事件驱动").strip()

        # 清理 company_reasons
        company_reasons = result.get("company_reasons", [])
        if not company_reasons:
            cleaned["company_reasons"] = ["近3个交易日无公司重大公告发布，股价异动主要由资金情绪驱动"]
        else:
            # 确保格式正确，用数字+顿号开头
            cleaned_reasons = []
            for idx, reason in enumerate(company_reasons[:4], 1):
                reason_str = str(reason).strip()
                if not reason_str.startswith(f"{idx}、"):
                    # 移除可能存在的旧编号
                    for old_idx in range(1, 10):
                        if reason_str.startswith(f"{old_idx}、"):
                            reason_str = reason_str[len(f"{old_idx}、"):].strip()
                            break
                    reason_str = f"{idx}、{reason_str}"
                cleaned_reasons.append(reason_str)
            cleaned["company_reasons"] = cleaned_reasons

        return cleaned

    @staticmethod
    def build_fallback(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        当AI不可用时，生成fallback结果
        
        Args:
            input_data: 输入数据
        
        Returns:
            fallback结果字典
        """
        news_list = input_data.get("news_list", [])
        market_data = input_data.get("market_data", {})

        # 从新闻中提取简单标签
        tags = []
        keywords = ["业绩", "中标", "签约", "合同", "高送转", "算力", "AI", "新能源", "芯片", "并购", "重组", "分红"]
        for news in news_list[:5]:
            title = news.get("title", "")
            summary = news.get("summary", "")
            text = title + summary
            for kw in keywords:
                if kw in text and kw not in tags:
                    tags.append(kw)
                    if len(tags) >= 3:
                        break
            if len(tags) >= 3:
                break

        core_tags_line = "+".join(tags[:3]) if tags else "无明确催化"

        # 构建公司原因
        company_reasons = []
        for idx, news in enumerate(news_list[:4], 1):
            title = news.get("title", "")
            publish_time = news.get("publish_time", "")
            if title:
                reason = f"{idx}、"
                if publish_time:
                    reason += f"据{publish_time[:10]}公告，"
                reason += title[:50]
                company_reasons.append(reason)

        if not company_reasons:
            company_reasons = ["近3个交易日无公司重大公告发布，股价异动主要由资金情绪驱动"]

        return {
            "core_tags_line": core_tags_line,
            "industry_reason": "行业整体数据正常，无重大政策或事件驱动",
            "company_reasons": company_reasons,
        }
