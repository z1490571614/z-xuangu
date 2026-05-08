"""
标签生成器 - 基于结构化数据生成候选标签
标签不完全依赖AI，先由规则引擎生成候选标签
"""
from typing import List, Dict, Any


class TagBuilder:

    @staticmethod
    def build_positive(data: Dict[str, Any]) -> List[str]:
        tags = []
        score = data.get("score", {})
        risk = data.get("risk", {})
        liquidity = data.get("liquidity", {})
        sector = data.get("sector", {})
        event = data.get("event_driver", {})
        anomaly = data.get("anomaly_interpretation", {})
        news = data.get("news", {})
        dl = data.get("dragon_leader", {})

        # 流动性
        ls = liquidity.get("liquidity_score") or score.get("liquidity_score")
        if ls is not None and ls >= 70:
            tags.append("流动性较好")
        elif ls is not None and ls >= 50:
            tags.append("流动性尚可")

        # 事件驱动
        es = event.get("event_score") or score.get("event_score")
        if es is not None and es >= 70:
            tags.append("明确事件驱动")
        elif es is not None and es >= 50:
            tags.append("有一定事件关注")

        # 板块地位
        ss = sector.get("sector_score") or score.get("sector_score")
        if ss is not None and ss >= 70:
            tags.append("板块地位较好")
        elif ss is not None and ss >= 50:
            tags.append("板块地位一般")

        # 交易价值
        tv = score.get("trade_value_score") or score.get("alpha_score")
        if tv is not None and tv >= 70:
            tags.append("交易价值较高")
        elif tv is not None and tv >= 55:
            tags.append("交易价值中等")

        # 公告/新闻利好
        if anomaly.get("main_reasons") and len(anomaly["main_reasons"]) > 0:
            tags.append("事件催化")

        if news and isinstance(news, dict):
            articles = news.get("articles", [])
            if any(a.get("sentiment") == "positive" for a in articles):
                tags.append("公告利好")

        # 龙头战法正面标签
        if dl:
            lvl = dl.get("leader_level", "")
            if lvl in ("极强龙头", "强势龙头"):
                tags.append(f"{lvl}地位")
            elif lvl in ("疑似龙头",):
                tags.append("疑似龙头标的")
            cycle = dl.get("cycle_stage", "")
            if cycle in ("主升期",):
                tags.append("处于主升周期")
            hs = dl.get("health_score", 0) or 0
            if hs >= 70:
                tags.append("综合健康度高")
            elif hs >= 55:
                tags.append("健康度尚可")
            aa = dl.get("announcement_alpha_score", 0) or 0
            if aa > 5:
                tags.append("消息面偏正面")

        # 事件缺失时补充
        if len(tags) == 0:
            tags.append("基础数据正常")

        return tags[:8]

    @staticmethod
    def build_negative(data: Dict[str, Any]) -> List[str]:
        tags = []
        score = data.get("score", {})
        risk = data.get("risk", {})
        sector = data.get("sector", {})
        event = data.get("event_driver", {})
        anomaly = data.get("anomaly_interpretation", {})
        dl = data.get("dragon_leader", {})

        # 风险
        rs = risk.get("risk_score") or score.get("risk_score")
        if rs is not None and rs >= 60:
            tags.append("风险评分偏高")
        elif rs is not None and rs >= 40:
            tags.append("风险评分中等")

        # 事件缺失
        es = event.get("event_score") or score.get("event_score")
        if es is not None and es < 30:
            tags.append("缺少明确催化")
        elif anomaly.get("data_status") == "generated_from_market_only":
            tags.append("仅行情异动")

        # 板块地位弱
        ss = sector.get("sector_score") or score.get("sector_score")
        if ss is not None and ss < 40:
            tags.append("板块地位较弱")

        # 高位风险
        risk_items = risk.get("risk_items", [])
        if isinstance(risk_items, list) and any(
            isinstance(it, dict) and it.get("name") == "高位风险" and it.get("score", 0) >= 10
            for it in risk_items
        ):
            tags.append("短期涨幅偏大")

        # Alpha评分低
        alpha = score.get("alpha_score")
        if alpha is not None and alpha < 50:
            tags.append("交易价值不突出")

        # 龙头战法负面标签
        if dl:
            lvl = dl.get("leader_level", "")
            if lvl == "非龙头":
                tags.append("非龙头标的")
            cycle = dl.get("cycle_stage", "")
            if cycle in ("退潮期",):
                tags.append("市场处于退潮期")
            rr = dl.get("retreat_risk_score", 0) or 0
            if rr >= 50:
                tags.append("退潮风险较高")
            elif rr >= 30:
                tags.append("退潮风险中等")
            hs = dl.get("health_score", 0) or 0
            if hs < 35:
                tags.append("综合健康度偏低")
            aa = dl.get("announcement_alpha_score", 0) or 0
            if aa < -5:
                tags.append("消息面偏负面")

        if len(tags) == 0:
            tags.append("无明显负面信号")

        return tags[:8]

    @staticmethod
    def build_key_points(data: Dict[str, Any]) -> List[str]:
        points = []
        score = data.get("score", {})
        anomaly = data.get("anomaly_interpretation", {})
        dl = data.get("dragon_leader", {})

        # 事件
        main_reasons = anomaly.get("main_reasons", [])
        if main_reasons:
            for r in main_reasons[:2]:
                points.append(f"核心驱动：{r}")

        # 风险
        risk_items = []
        rb = data.get("risk_breakdown", [])
        if isinstance(rb, list):
            risk_items = rb
        elif isinstance(rb, dict):
            risk_items = rb.get("items", [])
        if risk_items:
            top = risk_items[0] if isinstance(risk_items[0], dict) else {}
            if top.get("name") and top.get("score", 0) > 0:
                points.append(f"主要风险：{top['name']}({top['score']}/{top['max_score']})")

        # 评分
        fs = score.get("final_score")
        if fs is not None:
            if fs >= 75:
                points.append(f"最终评分{fs:.0f}，综合条件较好")
            elif fs >= 50:
                points.append(f"最终评分{fs:.0f}，一般")
            else:
                points.append(f"最终评分{fs:.0f}，偏低")

        # 龙头战法关键点
        if dl:
            lvl = dl.get("leader_level", "")
            hs = dl.get("health_score", 0) or 0
            rr = dl.get("retreat_risk_score", 0) or 0
            ls = dl.get("leader_strength_score", 0) or 0
            if lvl:
                points.append(f"龙头地位：{lvl}(强度{ls}/退潮{rr}/健康{hs})")
            aa = dl.get("announcement_alpha_score", 0) or 0
            if aa > 5:
                points.append(f"消息面加分{aa}")
            elif aa < -5:
                points.append(f"消息面扣分{aa}")
            la = dl.get("lhb_alpha_score", 0) or 0
            if la > 5:
                points.append(f"龙虎榜席位加分{la}")
            elif la < -5:
                points.append(f"龙虎榜席位扣分{la}")

        # 流动性
        liquidity = data.get("liquidity", {})
        amount = liquidity.get("amount")
        if amount:
            points.append(f"成交额{amount}，流动性{'充足' if liquidity.get('liquidity_score', 0) >= 70 else '一般'}")

        if not points:
            points.append("系统未匹配到明确公告、财报或政策催化。")

        return points[:5]
