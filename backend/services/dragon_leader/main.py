"""
龙头战法评分主流程 - 生产级版本
特性：权重配置化 + 数据库持久化 + 缓存管理
"""
import json
import logging
import os
from typing import Dict, Any, Optional

import yaml

from backend.database import SessionLocal
from backend.models.stock_risk import DragonLeaderScore
from backend.services.dragon_leader.data.stock_context import StockContext
from backend.services.dragon_leader.data.market_context import MarketContext
from backend.services.dragon_leader.data.theme_context import ThemeContext
from backend.services.dragon_leader.data.fundamental_context import FundamentalContext
from backend.services.dragon_leader.data.intraday_context import IntradayContext
from backend.services.dragon_leader.scorer.announcement_alpha import calculate_announcement_alpha
from backend.services.dragon_leader.lhb_alpha import calculate_lhb_alpha
from backend.services.dragon_leader.scorer.leader_scorer import leader_strength_scoring
from backend.services.dragon_leader.scorer.retreat_scorer import retreat_risk_scoring
from backend.services.dragon_leader.output import assemble_output
from backend.utils.trading_date import get_latest_trading_day

logger = logging.getLogger(__name__)

# 全局缓存过期管理（已迁移到各Context类，此处仅保留痕迹）
# 内存缓存由 _cache_timestamps 和 context 各自的缓存管理
_CACHE_TTL = 3600

# 权重配置（默认值，优先从config.yaml加载）
DRAGON_LEADER_WEIGHTS = {
    "health_formula": {
        "leader_strength_weight": 0.60,
        "retreat_risk_weight": -0.30,
        "announcement_alpha_weight": 0.50,
        "lhb_alpha_weight": 0.50,
        "base_score": 20,
    },
    "leader_strength": {
        "leader_status": 25,
        "theme_strength": 20,
        "emotion_cycle": 15,
        "sector_ladder": 15,
        "acceptance_strength": 10,
        "auction_intraday": 10,
        "lhb_bonus": 5,
    },
    "retreat_risk": {
        "leader_position_loss": 20,
        "emotion_retreat": 20,
        "ladder_break": 15,
        "acceptance_failure": 15,
        "chip_cashout": 10,
        "auction_miss": 10,
        "announcement_regulatory": 10,
    },
    "alpha_limits": {
        "announcement_alpha_min": -20,
        "announcement_alpha_max": 20,
        "lhb_alpha_min": -20,
        "lhb_alpha_max": 20,
    },
}


def _load_config():
    """从 config.yaml 加载权重配置，不存在则用默认值"""
    global DRAGON_LEADER_WEIGHTS
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        return
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg and "dragon_leader" in cfg:
            dl = cfg["dragon_leader"]
            if "health_formula" in dl:
                DRAGON_LEADER_WEIGHTS["health_formula"].update(dl["health_formula"])
            if "leader_strength" in dl:
                DRAGON_LEADER_WEIGHTS["leader_strength"].update(dl["leader_strength"])
            if "retreat_risk" in dl:
                DRAGON_LEADER_WEIGHTS["retreat_risk"].update(dl["retreat_risk"])
            if "alpha_limits" in dl:
                DRAGON_LEADER_WEIGHTS["alpha_limits"].update(dl["alpha_limits"])
            logger.info("✅ 从 config.yaml 加载龙头战法权重配置")
    except Exception as e:
        logger.warning(f"加载config.yaml失败，使用默认权重: {e}")


# 启动时加载一次
_load_config()


def _save_to_db(ts_code: str, trade_date: str, result: Dict):
    """保存评分结果到数据库"""
    db = SessionLocal()
    try:
        existing = db.query(DragonLeaderScore).filter(
            DragonLeaderScore.ts_code == ts_code,
            DragonLeaderScore.trade_date == trade_date,
        ).first()

        full_json = json.dumps(result, ensure_ascii=False, default=str)
        fields = {
            "leader_strength_score": result.get("leader_strength_score", 0),
            "retreat_risk_score": result.get("retreat_risk_score", 0),
            "health_score": result.get("health_score", 0),
            "leader_level": result.get("leader_level", ""),
            "risk_level": result.get("risk_level", ""),
            "health_level": result.get("health_level", ""),
            "cycle_stage": result.get("cycle_stage", ""),
            "announcement_alpha_score": result.get("announcement_alpha_score", 0),
            "lhb_alpha_score": result.get("lhb_alpha_score", 0),
            "full_result_json": full_json,
        }

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            record = DragonLeaderScore(
                ts_code=ts_code, trade_date=trade_date, **fields
            )
            db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"保存龙头战法评分失败 {ts_code}: {e}")
    finally:
        db.close()


def _get_from_db(ts_code: str, trade_date: Optional[str] = None) -> Optional[Dict]:
    """从数据库读取缓存"""
    db = SessionLocal()
    try:
        query = db.query(DragonLeaderScore).filter(DragonLeaderScore.ts_code == ts_code)
        if trade_date:
            query = query.filter(DragonLeaderScore.trade_date == trade_date)
        record = query.order_by(DragonLeaderScore.trade_date.desc()).first()
        if not record:
            return None

        full = json.loads(record.full_result_json) if record.full_result_json else {}
        # 确保关键字段从DB列读取（比JSON更可靠）
        full.update({
            "data_status": "available",
            "strategy_type": "dragon_leader",
            "ts_code": record.ts_code,
            "trade_date": record.trade_date,
            "leader_strength_score": record.leader_strength_score,
            "retreat_risk_score": record.retreat_risk_score,
            "health_score": record.health_score,
            "leader_level": record.leader_level,
            "risk_level": record.risk_level,
            "health_level": record.health_level,
            "cycle_stage": record.cycle_stage,
            "announcement_alpha_score": record.announcement_alpha_score or 0,
            "lhb_alpha_score": record.lhb_alpha_score or 0,
        })
        return full
    except Exception as e:
        logger.warning(f"从数据库读取龙头战法评分失败 {ts_code}: {e}")
        return None
    finally:
        db.close()


def collect_context(ts_code: str, trade_date: str) -> Dict:
    """数据采集（生产级：含缓存管理）"""
    stock_ctx = StockContext()
    market_ctx = MarketContext()
    theme_ctx = ThemeContext()
    fund_ctx = FundamentalContext()
    intraday_ctx = IntradayContext()

    stock_data = stock_ctx.collect(ts_code, trade_date)
    market_data = market_ctx.collect(trade_date)
    theme_data = theme_ctx.collect(ts_code, trade_date)
    fund_data = fund_ctx.collect(ts_code, trade_date)
    intraday_data = intraday_ctx.collect(ts_code, trade_date)

    return {
        "stock": stock_data.get("stock", {}),
        "daily": stock_data.get("daily", {}),
        "daily_basic": stock_data.get("daily_basic", {}),
        "chip": stock_data.get("chip", {}),
        "capital": stock_data.get("capital", {}),
        "technical": stock_data.get("technical", {}),
        "market": market_data,
        "theme": theme_data,
        "fundamental": fund_data,
        "intraday": intraday_data.get("intraday", {}),
    }


def collect_news(ts_code: str, stock_name: str) -> list:
    """采集新闻数据（重新用news_sentiment引擎分析情感）"""
    from backend.services.integrated_news_service import get_integrated_news_service
    from backend.services.news_sentiment.analyzer import analyze_news_event
    svc = get_integrated_news_service()
    try:
        news_result = svc.get_stock_news(stock_name=stock_name, limit=20, ensure_recent=False)
        news_list = news_result.get("data", {}).get("news_list", [])
    except Exception as e:
        logger.warning(f"获取新闻数据失败 {ts_code}: {e}")
        return []
    finally:
        try:
            svc.close()
        except Exception:
            pass

    # 重新用新引擎分析情感
    for i, item in enumerate(news_list):
        result = analyze_news_event(item, debug=False)
        news_list[i]["sentiment_type"] = result["sentiment"]
        news_list[i]["sentiment_score"] = result["confidence"]

    return news_list


def collect_lhb(ts_code: str, trade_date: str) -> Optional[Dict]:
    """采集龙虎榜数据"""
    from backend.services.lhb_service import analyze_lhb
    try:
        return analyze_lhb(ts_code, trade_date, force_refresh=False)
    except Exception as e:
        logger.warning(f"获取龙虎榜数据失败 {ts_code}: {e}")
        return None


def calculate_dragon_leader_score(
    ts_code: str,
    trade_date: Optional[str] = None,
    stock_name: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    龙头战法评分主流程（生产级）

    特性：
    - 权重从 config.yaml 读取
    - 结果写入 DB 持久化
    - 支持 force_refresh 强制重算
    - 支持缓存读取
    """
    if not trade_date:
        trade_date = get_latest_trading_day()

    # 读取缓存（非强制刷新时）
    if not force_refresh:
        cached = _get_from_db(ts_code, trade_date)
        if cached:
            return cached

    # 数据采集
    ctx = collect_context(ts_code, trade_date)

    if not ctx.get("stock"):
        result = {
            "data_status": "source_not_configured",
            "strategy_type": "dragon_leader",
            "leader_strength_score": 0,
            "retreat_risk_score": 0,
            "health_score": 0,
            "leader_level": "非龙头",
            "risk_level": "低风险",
            "health_level": "回避",
            "trade_date": trade_date,
        }
        return result

    if not stock_name:
        stock_name = ctx["stock"].get("name", "")

    # 消息面
    news_items = collect_news(ts_code, stock_name)
    announcement_result = calculate_announcement_alpha(news_items)

    # 龙虎榜
    lhb_data = collect_lhb(ts_code, trade_date)
    lhb_result = calculate_lhb_alpha(lhb_data)
    ctx["lhb_result"] = lhb_result
    ctx["announcement_result"] = announcement_result

    # 龙头强度
    leader_result = leader_strength_scoring(ctx, DRAGON_LEADER_WEIGHTS)

    # 退潮风险
    retreat_result = retreat_risk_scoring(ctx, DRAGON_LEADER_WEIGHTS)

    # 综合健康度
    hf = DRAGON_LEADER_WEIGHTS["health_formula"]
    health = (
        leader_result["total"] * hf["leader_strength_weight"]
        + retreat_result["total"] * hf["retreat_risk_weight"]
        + announcement_result["announcement_alpha_score"] * hf["announcement_alpha_weight"]
        + lhb_result["lhb_alpha_score"] * hf["lhb_alpha_weight"]
        + hf["base_score"]
    )
    health = round(max(0, min(100, health)))

    # 输出
    result = assemble_output(
        ts_code=ts_code, trade_date=trade_date,
        leader_result=leader_result, retreat_result=retreat_result,
        health_score=health,
        announcement_result=announcement_result, lhb_result=lhb_result,
    )

    # 写入数据库持久化
    try:
        _save_to_db(ts_code, trade_date, result)
    except Exception as e:
        logger.warning(f"持久化龙头战法评分失败: {e}")

    return result
