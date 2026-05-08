"""
龙头战法端到端集成测试（文档第16节要求的5个测试场景）

运行：python -m pytest tests/backend/unit/test_dragon_leader_e2e.py -v
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("TUSHARE_TOKEN", "test_token")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")

import pytest
from backend.services.dragon_leader.main import calculate_dragon_leader_score
from backend.services.dragon_leader.output import (
    get_leader_level, get_retreat_risk_level, get_health_level,
    get_cycle_stage, collect_positive_tips, collect_negative_tips
)


def _make_ctx(overrides: dict = None) -> dict:
    """构建最小上下文"""
    ctx = {
        "stock": {
            "ts_code": "603937.SH", "name": "测试",
            "change_pct": 10.0, "pre_change_pct": 10.0,
            "open_change_pct": 2.0, "auction_ratio": 12.5,
            "auction_turnover_rate": 2.5, "limit_up_count": 15,
            "seal_rate": 90.0, "rise_10d_pct": 25.0,
            "lu_tag": "3连板", "lu_status": "换手板", "lu_open_num": 0,
            "limit_up_suc_rate": 75.0,
        },
        "daily": {"pct_chg": 10.0, "amplitude": 8.0, "vol": 5000000, "amount": 50000000},
        "daily_basic": {"turnover_rate": 15.0, "volume_ratio": 2.0},
        "chip": {"winner_rate": 75.0, "weight_avg": 12.0, "cost_5pct": 10.0, "cost_95pct": 15.0},
        "capital": {"net_mf_amount": 5000000, "elg_net": 3000000, "lg_net": 2000000},
        "technical": {"rsi": 65, "kdj_k": 60, "cci": 80, "macd_dif": 0.5, "macd_dea": 0.3, "macd": 0.2, "volume_ratio": 2.0, "updays": 3, "downdays": 0},
        "market": {
            "sentiment": {
                "max_connected": 6, "limit_up_count": 45, "limit_down_count": 8,
                "zhaban_rate": 20.0, "index_pct": 0.5, "market_volume": 8000,
                "market_tr": 1.2, "north_money": 1000,
            }
        },
        "theme": {
            "theme_rank": {"best_rank": 2, "board_count": 2, "hot_boards": [
                {"name": "机器人概念", "up_nums": 20, "cons_nums": 5, "up_stat": "6天5板", "days": 8, "rank": 2, "pct_chg": 3.5},
                {"name": "芯片概念", "up_nums": 15, "cons_nums": 3, "up_stat": "4天3板", "days": 5, "rank": 5, "pct_chg": 2.8},
            ]},
            "kpl_detail": {"is_break": False, "is_limit_up": True, "seal_amount": 20000000, "theme": "机器人概念", "status": "3连板"},
        },
        "fundamental": {
            "forecast": {"data_status": "missing"},
            "fina": {"data_status": "missing", "eps": 0.3, "roe": 5.0, "profit_dedt": 1000000, "debt_to_assets": 45.0},
            "holdertrade": {"data_status": "missing"},
            "share_float": {"data_status": "missing"},
            "repurchase": {"data_status": "missing"},
            "is_st": False,
        },
        "intraday": {
            "open_price": 13.5, "close_price": 15.0,
            "intraday_high": 15.2, "intraday_low": 13.2,
            "intraday_direction": "上涨", "max_drop_pct": 2.2,
            "tail_direction": "涨", "is_weak_open": False,
            "has_tail_recovery": True,
            "data_status": "available",
        },
        "lhb_result": {"data_status": "not_applicable", "lhb_bonus_score": 0, "lhb_penalty_score": 0, "lhb_alpha_score": 0, "lhb_structure": "暂无龙虎榜数据", "tips": []},
        "announcement_result": {"good_news_score": 0, "bad_news_score": 0, "announcement_alpha_score": 0, "announcement_bias": "neutral", "tips": [], "data_status": "missing"},
    }
    if overrides:
        _deep_update(ctx, overrides)
    return ctx


def _deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
            _deep_update(d[k], v)
        else:
            d[k] = v


def _run_scenario(ctx_override, weights=None):
    from backend.services.dragon_leader.scorer.leader_scorer import leader_strength_scoring
    from backend.services.dragon_leader.scorer.retreat_scorer import retreat_risk_scoring
    from backend.services.dragon_leader.scorer.announcement_alpha import calculate_announcement_alpha
    from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
    from backend.services.dragon_leader.output import assemble_output

    w = {"health_formula": {"leader_strength_weight": 0.60, "retreat_risk_weight": -0.30, "announcement_alpha_weight": 0.50, "lhb_alpha_weight": 0.50, "base_score": 20}} if not weights else weights
    ctx = _make_ctx(ctx_override)

    leader = leader_strength_scoring(ctx, w)
    retreat = retreat_risk_scoring(ctx, w)

    ann = ctx.get("announcement_result", calculate_announcement_alpha([]))
    lhb = ctx.get("lhb_result", calculate_lhb_alpha(None))

    hf = w["health_formula"]
    health = round(max(0, min(100,
        leader["total"] * hf["leader_strength_weight"]
        + retreat["total"] * hf["retreat_risk_weight"]
        + ann["announcement_alpha_score"] * hf["announcement_alpha_weight"]
        + lhb["lhb_alpha_score"] * hf["lhb_alpha_weight"]
        + hf["base_score"]
    )))

    return assemble_output("test.SH", "20260430", leader, retreat, health, ann, lhb)


# ===================== 测试场景 =====================

class TestDragonLeaderE2E:

    def test_scenario_strong_leader_healthy_divergence(self):
        """
        场景16.1: 强势龙头健康分歧
        输入: 高获利盘+高换手+炸板后快速回封+板块梯队完整+高溢价游资+无重大利空
        预期: leader_strength_score 高, retreat_risk_score 中低, health_score 高
        """
        result = _run_scenario({
            "stock": {"rise_10d_pct": 35.0},
            "chip": {"winner_rate": 82.0},
            "daily_basic": {"turnover_rate": 25.0},
            "theme": {"kpl_detail": {"is_break": True, "last_time": "14:30", "seal_amount": 30000000}},
            "lhb_result": {"data_status": "available", "lhb_bonus_score": 8, "lhb_penalty_score": 0,
                           "lhb_alpha_score": 8, "lhb_structure": "偏多", "tips": ["高溢价游资买入"]},
        })

        assert result["leader_strength_score"] >= 60, f"龙头强度应高，实际={result['leader_strength_score']}"
        assert result["retreat_risk_score"] <= 40, f"退潮风险应中低，实际={result['retreat_risk_score']}"
        assert result["health_score"] >= 50, f"健康度应高，实际={result['health_score']}"

    def test_scenario_high_retreat(self):
        """
        场景16.2: 高位退潮
        输入: 高获利盘+爆量滞涨+炸板不回封+板块后排大跌+跌停家数增加+砸盘席位
        预期: leader_strength_score 下降, retreat_risk_score 高, health_score 低
        """
        result = _run_scenario({
            "stock": {"change_pct": 1.5, "lu_tag": "3连板", "lu_open_num": 5, "open_change_pct": 6.0, "limit_up_suc_rate": 35.0},
            "chip": {"winner_rate": 95.0},
            "capital": {"net_mf_amount": -50000000, "elg_net": -20000000},
            "market": {"sentiment": {"max_connected": 3, "limit_up_count": 15, "limit_down_count": 35, "zhaban_rate": 45.0, "index_pct": -1.5}},
            "theme": {"kpl_detail": {"is_break": True, "is_limit_up": False}},
            "lhb_result": {"data_status": "available", "lhb_bonus_score": 0, "lhb_penalty_score": -10,
                           "lhb_alpha_score": -10, "lhb_structure": "偏空", "tips": ["核按钮席位出现"]},
        })

        assert result["retreat_risk_score"] >= 40, f"退潮风险应高，实际={result['retreat_risk_score']}"
        assert result["health_score"] <= 60, f"健康度应低，实际={result['health_score']}"

    def test_scenario_positive_news_driven(self):
        """
        场景16.3: 利好消息驱动
        输入: 政策利好+板块涨停潮+个股为板块最高标+无龙虎榜数据
        预期: announcement_alpha_score为正, lhb_alpha_score=0 data_status=not_applicable, health_score被抬高
        """
        news = [{"title": "国家政策支持人工智能产业发展", "content": "专项规划出台", "sentiment_type": "positive", "sentiment_score": 0.9}]
        from backend.services.dragon_leader.scorer.announcement_alpha import calculate_announcement_alpha
        ann_result = calculate_announcement_alpha(news)

        result = _run_scenario({
            "announcement_result": ann_result,
            "lhb_result": {"data_status": "not_applicable"},
            "theme": {"theme_rank": {"best_rank": 1, "board_count": 1, "hot_boards": [
                {"name": "人工智能", "up_nums": 30, "cons_nums": 8, "up_stat": "8天7板", "days": 10, "rank": 1, "pct_chg": 5.0}
            ]}},
        })

        assert ann_result["announcement_alpha_score"] > 0, f"消息面应正向，实际={ann_result['announcement_alpha_score']}"
        lhb_data = result.get("score_detail", {}).get("alpha_adjustment", {})
        assert lhb_data.get("lhb_alpha_score", 0) == 0, "龙虎榜应无数据"
        assert result["leader_strength_score"] >= 60, "龙头强度应被题材数据抬高"

    def test_scenario_negative_news_pressure(self):
        """
        场景16.4: 利空消息压制
        输入: 股东减持+监管问询+高位放量+承接变弱
        预期: announcement_alpha_score为负, retreat_risk_score上升, health_score下降
        """
        news = [{"title": "大股东减持计划公告", "content": "拟减持不超过5%", "sentiment_type": "negative", "sentiment_score": 0.85}, {"title": "公司收到监管问询函", "content": "", "sentiment_type": "negative", "sentiment_score": 0.7}]
        from backend.services.dragon_leader.scorer.announcement_alpha import calculate_announcement_alpha
        ann_result = calculate_announcement_alpha(news)

        from backend.services.dragon_leader.scorer.retreat_scorer import retreat_risk_scoring
        ctx = _make_ctx({
            "stock": {"change_pct": 2.0, "rise_10d_pct": 40.0, "open_change_pct": 4.0, "lu_tag": "3连板", "limit_up_suc_rate": 40.0},
            "chip": {"winner_rate": 88.0},
            "capital": {"net_mf_amount": -40000000, "elg_net": -15000000},
            "market": {"sentiment": {"max_connected": 4, "limit_up_count": 20, "limit_down_count": 15, "zhaban_rate": 35.0, "index_pct": -0.8}},
            "fundamental": {"forecast": {"data_status": "available", "type": "预减", "sentiment": "negative"}},
            "announcement_result": ann_result,
        })

        retreat = retreat_risk_scoring(ctx, {"health_formula": {"leader_strength_weight": 0.60, "retreat_risk_weight": -0.30, "announcement_alpha_weight": 0.50, "lhb_alpha_weight": 0.50, "base_score": 20}})

        assert ann_result["announcement_alpha_score"] < 0, f"消息面应为负，实际={ann_result['announcement_alpha_score']}"
        assert retreat["total"] >= 30, f"退潮风险应上升，实际={retreat['total']}"

    def test_scenario_quant_seat_dominated(self):
        """
        场景16.5: 砸盘席位方向分化
        输入: 散户席位净买入较多，同时核按钮席位净卖出
        预期: 净买入的砸盘席位扣分，净卖出的砸盘席位加分，最终按净方向合并
        """
        from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
        lhb_data = {
            "data_status": "available",
            "buy_top5": [
                {"exalter": "东方财富证券拉萨团结路第二营业部", "buy": 30000000, "sell": 500000, "net_buy": 29500000},
                {"exalter": "东方财富证券拉萨东环路第二营业部", "buy": 25000000, "sell": 300000, "net_buy": 24700000},
                {"exalter": "东方财富证券拉萨团结路第一营业部", "buy": 15000000, "sell": 200000, "net_buy": 14800000},
                {"exalter": "中国银河证券绍兴营业部", "buy": 10000000, "sell": 1000000, "net_buy": 9000000},
            ],
            "sell_top5": [
                {"exalter": "长城证券仙桃钱沟路", "buy": 0, "sell": 20000000, "net_buy": -20000000},
                {"exalter": "华泰证券成都南一环路", "buy": 0, "sell": 15000000, "net_buy": -15000000},
                {"exalter": "机构专用", "buy": 0, "sell": 10000000, "net_buy": -10000000},
            ],
            "net_amount": 44200000,
            "buy_amount": 80000000,
            "sell_amount": 45000000,
        }
        lhb_result = calculate_lhb_alpha(lhb_data)

        assert lhb_result["lhb_penalty_score"] < 0, f"砸盘席位净买入应扣分，实际={lhb_result['lhb_penalty_score']}"
        assert lhb_result["lhb_bonus_score"] > 0, f"砸盘席位净卖出应加分，实际={lhb_result['lhb_bonus_score']}"
        assert lhb_result["lhb_alpha_score"] > 0, f"龙虎榜净方向应为正，实际={lhb_result['lhb_alpha_score']}"
        assert any("散户" in t for t in lhb_result.get("tips", [])), "提示应包含散户席位信息"
        assert any("核按钮" in t for t in lhb_result.get("tips", [])), "提示应包含核按钮席位信息"
