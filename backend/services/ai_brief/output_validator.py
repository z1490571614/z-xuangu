"""
AI输出校验器 - 校验AI生成内容的合规性
"""
import json
from typing import Dict, Any, List, Tuple

VALID_SUGGESTIONS = ["不关注", "只观察", "开盘确认", "小仓试错", "不参与"]
FORBIDDEN_WORDS = ["必涨", "稳赚", "一定上涨", "确定涨停", "无风险", "强烈买入", "梭哈", "满仓", "保证收益"]


class OutputValidator:

    @staticmethod
    def validate(output: Dict[str, Any]) -> Tuple[bool, str]:
        """校验AI输出，返回 (是否通过, 错误信息)"""
        errors = []

        # 1. ai_suggestion
        suggestion = output.get("ai_suggestion", "")
        if not suggestion:
            errors.append("ai_suggestion 为空")
        elif suggestion not in VALID_SUGGESTIONS:
            errors.append(f"ai_suggestion '{suggestion}' 不在有效枚举内")
            errors.append(f"有效值：{'/'.join(VALID_SUGGESTIONS)}")

        # 2. brief
        brief = output.get("brief", "")
        if not brief or len(brief) < 20:
            errors.append("brief 为空或过短(<20字)")

        # 3. positive_tags
        pt = output.get("positive_tags", [])
        if not isinstance(pt, list):
            errors.append("positive_tags 必须是数组")
        elif len(pt) < 1:
            errors.append("positive_tags 为空")

        # 4. negative_tags
        nt = output.get("negative_tags", [])
        if not isinstance(nt, list):
            errors.append("negative_tags 必须是数组")
        elif len(nt) < 1:
            errors.append("negative_tags 为空")

        # 5. key_points
        kp = output.get("key_points", [])
        if not isinstance(kp, list) or len(kp) < 1:
            errors.append("key_points 必须是数组且至少1条")

        # 6. 禁止词检查
        text = json.dumps(output, ensure_ascii=False)
        for word in FORBIDDEN_WORDS:
            if word in text:
                errors.append(f"包含禁止词：{word}")

        # 7. disclaimer
        if "仅供参考" not in output.get("disclaimer", ""):
            errors.append("缺少免责声明")

        if errors:
            return False, "; ".join(errors)
        return True, ""

    @staticmethod
    def sanitize_fallback(output: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """修复AI小问题，如果严重则返回None触发fallback"""
        # 修正ai_suggestion
        suggestion = output.get("ai_suggestion", "")
        if suggestion not in VALID_SUGGESTIONS:
            fs = input_data.get("score", {}).get("final_score", 50)
            if fs >= 75:
                output["ai_suggestion"] = "开盘确认"
            elif fs >= 50:
                output["ai_suggestion"] = "只观察"
            else:
                output["ai_suggestion"] = "不关注"

        # 补全disclaimer
        if "仅供参考" not in output.get("disclaimer", ""):
            output["disclaimer"] = "本内容由系统根据结构化数据和公开信息整理生成，仅供参考，不构成投资建议。"

        return output
