"""
AI提示词构建器 - 将结构化数据转为AI提示词
"""
import json
from typing import Dict, Any

PROMPT_TEMPLATE = """你是股票数据简报生成器。你只能根据我提供的结构化JSON数据生成简报，不能编造任何输入中不存在的信息。

请注意：
- 涨停、连板、短期涨幅较大、竞价强、封板率高，只能作为行情背景，不能作为核心上涨原因。
- 如果没有公告、财报、新闻、行业、政策或公司经营事件，请明确说明"未匹配到明确催化"。
- 你不能输出"必涨""一定上涨""确定机会"等保证性表达。
- 你不能给出确定投资建议，只能输出系统观察建议。
- 输出必须是合法JSON。

请根据以下数据生成：
1. brief：150-300字简报；
2. ai_suggestion：一句话建议，只能从以下枚举中选择：
   - 不关注
   - 只观察
   - 开盘确认
   - 小仓试错
   - 不参与
3. suggestion_reason：一句话解释建议原因；
4. positive_tags：3-8个正面标签；
5. negative_tags：3-8个负面标签；
6. key_points：3-5条要点；
7. disclaimer：固定的免责声明。

输入数据如下：
{input_json}

输出JSON Schema：
{{
  "brief": "string",
  "ai_suggestion": "不关注 | 只观察 | 开盘确认 | 小仓试错 | 不参与",
  "suggestion_reason": "string",
  "positive_tags": ["string"],
  "negative_tags": ["string"],
  "key_points": ["string"],
  "disclaimer": "本内容由系统根据结构化数据和公开信息整理生成，仅供参考，不构成投资建议。"
}}"""


class OverviewPromptBuilder:

    @staticmethod
    def build(input_data: Dict[str, Any]) -> str:
        cleaned = OverviewPromptBuilder._clean_input(input_data)
        return PROMPT_TEMPLATE.format(input_json=json.dumps(cleaned, ensure_ascii=False, indent=2))

    @staticmethod
    def _clean_input(data: Dict[str, Any]) -> Dict[str, Any]:
        """清洗输入数据，删除无用/重复字段"""
        cleaned = {}

        # stock
        if "stock" in data:
            cleaned["stock"] = {
                "stock_code": data["stock"].get("stock_code", ""),
                "stock_name": data["stock"].get("stock_name", ""),
                "trade_date": data["stock"].get("trade_date", ""),
            }

        # score - 只保留关键字段
        if "score" in data:
            s = data["score"]
            cleaned["score"] = {
                "final_score": s.get("final_score"),
                "score_grade": s.get("score_grade"),
                "trade_value_score": s.get("trade_value_score"),
                "risk_score": s.get("risk_score"),
                "event_score": s.get("event_score"),
                "liquidity_score": s.get("liquidity_score"),
            }

        # decision
        if "decision" in data:
            d = data["decision"]
            cleaned["decision"] = {
                "system_action_level": d.get("action_level", d.get("system_action_level")),
                "position_suggestion": d.get("position_suggestion"),
                "entry_suggestion": d.get("entry_suggestion"),
            }

        # event_driver
        if "event_driver" in data:
            ev = data["event_driver"]
            cleaned["event_driver"] = {
                "event_driver_type": ev.get("event_driver_type", ev.get("data_status")),
                "event_score": ev.get("event_score"),
                "core_events": ev.get("core_events", ev.get("main_reasons", [])),
                "summary_title": ev.get("summary_title"),
            }
        elif "anomaly_interpretation" in data:
            ai = data["anomaly_interpretation"]
            cleaned["event_driver"] = {
                "event_driver_type": ai.get("data_status", "unknown"),
                "core_events": ai.get("main_reasons", []),
                "summary_title": ai.get("summary_title"),
            }

        # sector
        if "sector" in data:
            sec = data["sector"]
            cleaned["sector"] = {
                "sector_name": sec.get("sector_name", sec.get("industry")),
                "sector_score": sec.get("sector_score"),
            }

        # risk - 摘要
        if "risk" in data:
            r = data["risk"]
            risk_items = r.get("risk_items", r.get("items", []))
            cleaned["risk"] = {
                "risk_score": r.get("risk_score"),
                "risk_level": r.get("risk_level"),
                "risk_highlights": [
                    {"name": it.get("name") if isinstance(it, dict) else str(it), 
                     "score": it.get("score", 0) if isinstance(it, dict) else 0, 
                     "reason": it.get("reason") if isinstance(it, dict) else ""}
                    for it in (risk_items if isinstance(risk_items, list) else [])
                    if (isinstance(it, dict) and it.get("score", 0) > 0) or (not isinstance(it, dict))
                ][:3],
            }

        # liquidity
        if "liquidity" in data:
            lq = data["liquidity"]
            cleaned["liquidity"] = {
                "liquidity_score": lq.get("liquidity_score"),
                "amount": lq.get("amount"),
                "turnover_rate": lq.get("turnover_rate"),
            }

        # market_background
        if "market_background" in data:
            mb = data["market_background"]
            cleaned["market_background"] = {
                "is_limit_up": mb.get("is_limit_up", False),
                "pct_chg": mb.get("pct_chg"),
                "note": "涨停、连板仅作为行情背景，不作为核心异动原因。",
            }

        # dragon_leader
        if "dragon_leader" in data:
            dl = data["dragon_leader"]
            cleaned["dragon_leader"] = {
                "leader_level": dl.get("leader_level"),
                "leader_strength_score": dl.get("leader_strength_score"),
                "retreat_risk_score": dl.get("retreat_risk_score"),
                "health_score": dl.get("health_score"),
                "cycle_stage": dl.get("cycle_stage"),
                "lhb_alpha_score": dl.get("lhb_alpha_score"),
                "announcement_alpha_score": dl.get("announcement_alpha_score"),
            }

        # positive/negative factors
        if "positive_factors" in data:
            cleaned["positive_factors"] = data["positive_factors"]
        if "negative_factors" in data:
            cleaned["negative_factors"] = data["negative_factors"]

        # data_status
        if "data_status" in data:
            cleaned["data_status"] = data["data_status"]

        return cleaned
