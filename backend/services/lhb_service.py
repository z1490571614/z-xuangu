"""
龙虎榜数据服务 - 数据采集+席位分析+行为判定+永久存储
"""
import json
import math
import logging
from typing import Dict, Any, Optional, List, Tuple

from backend.database import SessionLocal
from backend.models.stock_lhb import StockLhb

logger = logging.getLogger(__name__)

# 游资/机构席位匹配规则 - 使用统一席位库
from backend.services.seat_library import (
    match_seat_tag,
)

# 游资风格标签（辅助识别游资接力价值）
STYLE_TAGS: Dict[str, str] = {
    "华泰证券深圳益田路": "隔日砸盘",
    "中信证券杭州延安路": "连板接力",
    "中国银河证券绍兴": "趋势持有",
    "华鑫证券上海分公司": "首板挖掘",
    "华泰证券成都南一环路": "一日游",
}


def _match_style_tag(exalter: str) -> Optional[str]:
    """匹配游资风格标签"""
    for keyword, tag in STYLE_TAGS.items():
        if keyword in exalter:
            return tag
    return None


def _format_amount(val: Optional[float]) -> str:
    """格式化金额"""
    if val is None:
        return "--"
    abs_val = abs(val)
    if abs_val >= 100000000:
        return f"{val / 100000000:.2f}亿"
    return f"{val / 10000:.0f}万"


def _analyze_action(buy_amount: float, sell_amount: float, net_amount: float) -> Tuple[str, str]:
    """
    行为判定
    
    Returns:
        (action_tag, main_type)
    """
    total = buy_amount + sell_amount
    if total == 0:
        return "主力分歧", "混合"

    buy_ratio = buy_amount / total
    sell_ratio = sell_amount / total
    net_ratio = net_amount / total if total else 0

    # 判断主力类型
    main_type = "混合"
    if buy_ratio > 0.7:
        main_type = "买入主导"
    elif sell_ratio > 0.7:
        main_type = "卖出主导"

    # 判断行为
    if net_amount > 0:
        if buy_amount / max(sell_amount, 1) > 1.8:
            return "一致抢筹", main_type
        elif buy_amount / max(sell_amount, 1) > 1.2:
            return "温和抢筹", main_type
        else:
            return "主力分歧", main_type
    elif abs(net_amount) < 5000000:
        return "主力分歧", main_type
    else:
        if sell_amount / max(buy_amount, 1) > 1.5:
            return "一致砸盘", main_type
        else:
            return "温和出货", main_type


def _build_seat_tags_list(detail: List[Dict], service: Optional['LhbService'] = None) -> List[Dict]:
    """为席位明细添加标签和游资别名"""
    result = []
    for s in detail:
        tag, detail_type = match_seat_tag(s.get("exalter", ""))
        style = _match_style_tag(s.get("exalter", ""))
        trader = None
        if service:
            trader = service._match_trader(s["exalter"])
        result.append({
            "exalter": s["exalter"],
            "side": _pyint(s.get("side", 0)),
            "buy": _pyfloat(s.get("buy", 0)) or 0,
            "sell": _pyfloat(s.get("sell", 0)) or 0,
            "net_buy": _pyfloat(s.get("net_buy", 0)) or 0,
            "tag": tag,
            "detail_type": detail_type,
            "style": style,
            "trader": trader,
        })
    return result


def _pyfloat(v):
    """numpy float → Python float（安全处理 NaN）"""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _pyint(v):
    """numpy int → Python int"""
    if v is None:
        return None
    return int(v)


def _generate_tags(buy_details: List[Dict], sell_details: List[Dict],
                   action_tag: str, net_amount: float) -> List[str]:
    """生成游资行为标签"""
    tags = []

    # 检查是否有机构买入（高溢价席位）
    has_inst_buy = any(d.get("tag") == "高溢价" and d.get("detail_type") == "机构" for d in buy_details)
    if has_inst_buy:
        tags.append("机构净买入")

    # 检查一线游资
    has_top_trader = any(d.get("tag") == "一线游资" for d in buy_details)
    if has_top_trader:
        tags.append("一线游资抢筹")

    # 检查北向（通过 detail_type 判断）
    has_north = any(d.get("tag") == "高溢价" and d.get("detail_type") == "北向" for d in buy_details)
    if has_north:
        tags.append("北向加仓")

    # 检查高溢价游资买入
    has_premium = any(
        d.get("tag") == "高溢价" and d.get("detail_type") not in ("机构", "北向")
        for d in buy_details
    )
    if has_premium:
        tags.append("顶级游资买入")

    # 核按钮
    has_knife = any(d.get("tag") == "核按钮" for d in sell_details)
    if has_knife:
        tags.append("核按钮游资卖出")

    # 量化席位卖出
    has_quant_sell = any(d.get("tag") == "量化" for d in sell_details)
    if has_quant_sell:
        tags.append("量化资金卖出")

    # 分歧
    if action_tag == "主力分歧":
        tags.append("主力分歧")

    # 砸盘
    if action_tag in ("一致砸盘", "温和出货"):
        tags.append("高位砸盘")

    return tags


def _generate_risk_tips(buy_details: List[Dict], sell_details: List[Dict],
                        action_tag: str, net_amount: float) -> List[str]:
    """生成实战风险提示"""
    tips = []

    # 核按钮风险
    knife_in_buy = [d for d in buy_details if d.get("tag") == "核按钮"]
    knife_in_sell = [d for d in sell_details if d.get("tag") == "核按钮"]
    if knife_in_sell:
        names = [d["exalter"] for d in knife_in_sell[:2]]
        tips.append(f"核按钮席位卖出：{'、'.join(names)}")
    if knife_in_buy:
        names = [d["exalter"] for d in knife_in_buy[:2]]
        tips.append(f"核按钮席位买入（需警惕隔日砸盘）：{'、'.join(names)}")

    # 量化席位风险
    quant_in_sell = [d for d in sell_details if d.get("tag") == "量化"]
    if quant_in_sell:
        names = [d["exalter"] for d in quant_in_sell[:2]]
        tips.append(f"量化席位卖出：{'、'.join(names)}")

    # 资金分歧
    if action_tag == "主力分歧":
        tips.append("主力分歧较大，需观察开盘方向选择")

    # 资金流出
    if net_amount < -50000000:
        tips.append("净流出超5000万，资金出逃明显")

    # 散户集中
    retail_buy = [d for d in buy_details if d.get("tag") == "散户"]
    retail_sell = [d for d in sell_details if d.get("tag") == "散户"]
    if retail_buy and sum(d.get("buy", 0) for d in retail_buy) > 30000000:
        tips.append("散户接盘明显，注意风险")

    if not tips:
        tips.append("无核按钮砸盘风险")

    return tips


class LhbService:
    """龙虎榜服务"""

    def __init__(self):
        self._pro = None
        self._seat_to_trader: Optional[Dict[str, str]] = None

    def _load_trader_map(self) -> Dict[str, str]:
        """从 Tushare hm_list 加载游资映射（营业部→游资别名）"""
        if self._seat_to_trader is not None:
            return self._seat_to_trader

        result: Dict[str, str] = {}
        if not self.pro:
            logger.warning("TUSHARE_TOKEN 未配置，无法加载游资名录")
            self._seat_to_trader = result
            return result

        try:
            df = self.pro.hm_list()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    trader_name = str(row.get("name", "")).strip()
                    orgs = str(row.get("orgs", "")).strip()
                    if not trader_name or not orgs or orgs == "nan":
                        continue
                    # 一个游资可能关联多个营业部（用、或,分隔）
                    for org in orgs.replace("、", ",").replace("，", ",").split(","):
                        org = org.strip()
                        if org and org != "nan":
                            # 多个游资可能对应同一营业部，用 / 连接
                            if org in result:
                                if trader_name not in result[org]:
                                    result[org] += f"/{trader_name}"
                            else:
                                result[org] = trader_name
                logger.info(f"游资映射加载完成: {len(result)} 条映射 ({len(df)} 条记录)")
            else:
                logger.info("hm_list 返回空数据")
        except Exception as e:
            logger.warning(f"加载游资名录失败: {e}")

        self._seat_to_trader = result
        return result

    def _match_trader(self, exalter: str) -> Optional[str]:
        """匹配营业部对应的游资别名"""
        # 精确匹配
        if exalter in self._seat_to_trader:
            return self._seat_to_trader[exalter]
        # 子串匹配
        for seat, trader in self._seat_to_trader.items():
            if seat in exalter or exalter in seat:
                return trader
        return None

    @property
    def pro(self):
        if self._pro is None:
            from backend.utils.tushare_client import get_tushare_pro
            self._pro = get_tushare_pro()
            if not self._pro:
                logger.warning("TUSHARE_TOKEN 未配置")
        return self._pro

    def fetch_lhb_data(self, ts_code: str, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取个股龙虎榜数据
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期（可选，默认最新交易日）
            
        Returns:
            lhb_data dict
        """
        if not self.pro:
            return {"data_status": "source_not_configured"}

        try:
            # 未指定日期时自动获取最新交易日
            if not trade_date:
                from backend.utils.trading_date import get_latest_trading_day
                trade_date = get_latest_trading_day()

            # 加载游资名录映射
            self._load_trader_map()

            # 1. 获取 top_list 基础数据
            top_df = self.pro.top_list(trade_date=trade_date, ts_code=ts_code)

            if top_df is None or top_df.empty:
                return {"data_status": "not_on_list"}

            # 取最新一条上榜记录
            top_row = top_df.iloc[0].to_dict() if len(top_df) > 0 else None
            if not top_row:
                return {"data_status": "not_on_list"}

            record_trade_date = str(top_row.get("trade_date", trade_date or ""))

            # 2. 获取 top_inst 席位明细
            buy_details = []
            sell_details = []
            try:
                inst_df = self.pro.top_inst(trade_date=record_trade_date, ts_code=ts_code)
                if inst_df is not None and not inst_df.empty:
                    for _, row in inst_df.iterrows():
                        item = {
                            "exalter": str(row.get("exalter", "")),
                            "side": int(row.get("side", 0)),
                            "buy": _pyfloat(row.get("buy")),
                            "sell": _pyfloat(row.get("sell")),
                            "buy_rate": _pyfloat(row.get("buy_rate")),
                            "sell_rate": _pyfloat(row.get("sell_rate")),
                            "net_buy": _pyfloat(row.get("net_buy")),
                        }
                        if item["side"] == 0:
                            buy_details.append(item)
                        else:
                            sell_details.append(item)
            except Exception as e:
                logger.warning(f"获取 top_inst 失败（可能需要更高积分）: {e}")

            # 3. 计算资金汇总
            buy_total = _pyfloat(top_row.get("l_buy")) or sum(d.get("buy", 0) or 0 for d in buy_details)
            sell_total = _pyfloat(top_row.get("l_sell")) or sum(d.get("sell", 0) or 0 for d in sell_details)
            net_total = _pyfloat(top_row.get("net_amount")) or (buy_total - sell_total)

            # 4. 行为分析
            action_tag, main_type = _analyze_action(buy_total, sell_total, net_total)

            # 5. 席位标签
            buy_tagged = _build_seat_tags_list(buy_details, self)
            sell_tagged = _build_seat_tags_list(sell_details, self)

            # 6. 生成标签和风险提示
            tags = _generate_tags(buy_tagged, sell_tagged, action_tag, net_total)
            risk_tips = _generate_risk_tips(buy_tagged, sell_tagged, action_tag, net_total)

            # 7. 组装结果（转换numpy类型为Python原生类型，避免JSON序列化失败）
            result = {
                "data_status": "available",
                "trade_date": record_trade_date,
                "reason": top_row.get("reason", ""),
                "change_pct": _pyfloat(top_row.get("pct_change")),
                "amount": _pyfloat(top_row.get("amount")),
                "turnover_rate": _pyfloat(top_row.get("turnover_rate")),
                "lhb_type": "当日榜",
                "buy_amount": _pyfloat(buy_total),
                "sell_amount": _pyfloat(sell_total),
                "net_amount": _pyfloat(net_total),
                "net_rate": _pyfloat(top_row.get("net_rate")),
                "amount_rate": _pyfloat(top_row.get("amount_rate")),
                "main_type": main_type,
                "action_tag": action_tag,
                "buy_top5": buy_tagged[:5],
                "sell_top5": sell_tagged[:5],
                "tags": tags,
                "risk_tips": risk_tips,
                "seat_tags": {},
            }

            # 8. 保存到永久数据库
            self._save_lhb(ts_code, record_trade_date, result)

            # 9. 获取历史记录
            history = self._get_history(ts_code, record_trade_date)
            if history:
                result["history"] = history

            return result

        except Exception as e:
            logger.error(f"获取龙虎榜失败 {ts_code}: {e}")
            return {"data_status": "fetch_failed", "error": str(e)}

    def _save_lhb(self, ts_code: str, trade_date: str, data: Dict[str, Any]):
        """保存龙虎榜数据到永久数据库"""
        db = SessionLocal()
        try:
            existing = db.query(StockLhb).filter(
                StockLhb.ts_code == ts_code,
                StockLhb.trade_date == trade_date,
            ).first()

            if existing:
                existing.reason = data.get("reason")
                existing.change_pct = data.get("change_pct")
                existing.amount = data.get("amount")
                existing.turnover_rate = data.get("turnover_rate")
                existing.buy_amount = data.get("buy_amount")
                existing.sell_amount = data.get("sell_amount")
                existing.net_amount = data.get("net_amount")
                existing.net_rate = data.get("net_rate")
                existing.amount_rate = data.get("amount_rate")
                existing.main_type = data.get("main_type")
                existing.action_tag = data.get("action_tag")
                existing.detail_json = json.dumps({
                    "buy_top5": data.get("buy_top5", []),
                    "sell_top5": data.get("sell_top5", []),
                    "tags": data.get("tags", []),
                    "risk_tips": data.get("risk_tips", []),
                }, ensure_ascii=False)
            else:
                record = StockLhb(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    reason=data.get("reason"),
                    change_pct=data.get("change_pct"),
                    amount=data.get("amount"),
                    turnover_rate=data.get("turnover_rate"),
                    lhb_type=data.get("lhb_type", "当日榜"),
                    buy_amount=data.get("buy_amount"),
                    sell_amount=data.get("sell_amount"),
                    net_amount=data.get("net_amount"),
                    net_rate=data.get("net_rate"),
                    amount_rate=data.get("amount_rate"),
                    main_type=data.get("main_type"),
                    action_tag=data.get("action_tag"),
                    detail_json=json.dumps({
                        "buy_top5": data.get("buy_top5", []),
                        "sell_top5": data.get("sell_top5", []),
                        "tags": data.get("tags", []),
                        "risk_tips": data.get("risk_tips", []),
                    }, ensure_ascii=False),
                )
                db.add(record)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"保存龙虎榜数据失败 {ts_code}: {e}")
        finally:
            db.close()

    def _get_history(self, ts_code: str, current_date: str) -> List[Dict]:
        """获取历史上榜记录（最多3条）"""
        db = SessionLocal()
        try:
            records = db.query(StockLhb).filter(
                StockLhb.ts_code == ts_code,
                StockLhb.trade_date < current_date,
            ).order_by(StockLhb.trade_date.desc()).limit(3).all()

            result = []
            for r in records:
                result.append({
                    "trade_date": r.trade_date,
                    "net_amount": r.net_amount,
                    "action_tag": r.action_tag,
                    "change_pct": r.change_pct,
                })
            return result
        finally:
            db.close()

    def get_from_db(self, ts_code: str, trade_date: Optional[str] = None) -> Optional[Dict]:
        """从数据库获取龙虎榜缓存"""
        db = SessionLocal()
        try:
            query = db.query(StockLhb).filter(StockLhb.ts_code == ts_code)
            if trade_date:
                query = query.filter(StockLhb.trade_date == trade_date)
            record = query.order_by(StockLhb.trade_date.desc()).first()

            if not record:
                return None

            detail = json.loads(record.detail_json) if record.detail_json else {}

            result = {
                "data_status": "available",
                "trade_date": record.trade_date,
                "reason": record.reason,
                "change_pct": record.change_pct,
                "amount": record.amount,
                "turnover_rate": record.turnover_rate,
                "lhb_type": record.lhb_type,
                "buy_amount": record.buy_amount,
                "sell_amount": record.sell_amount,
                "net_amount": record.net_amount,
                "main_type": record.main_type,
                "action_tag": record.action_tag,
                "buy_top5": detail.get("buy_top5", []),
                "sell_top5": detail.get("sell_top5", []),
                "tags": detail.get("tags", []),
                "risk_tips": detail.get("risk_tips", []),
            }

            # 补充历史
            history = self._get_history(ts_code, record.trade_date)
            if history:
                result["history"] = history

            return result
        except Exception as e:
            logger.warning(f"从数据库读取龙虎榜失败: {e}")
            return None
        finally:
            db.close()


# 全局单例
_lhb_service: Optional[LhbService] = None


def get_lhb_service() -> LhbService:
    global _lhb_service
    if _lhb_service is None:
        _lhb_service = LhbService()
    return _lhb_service


def analyze_lhb(ts_code: str, trade_date: Optional[str] = None,
                force_refresh: bool = False) -> Dict[str, Any]:
    """
    获取个股龙虎榜分析结果（对外接口）
    
    Args:
        ts_code: 股票代码
        trade_date: 交易日期
        force_refresh: 是否强制刷新（从API拉取）
        
    Returns:
        龙虎榜数据字典
    """
    service = get_lhb_service()

    # 非强制刷新时，先从数据库读缓存
    if not force_refresh:
        cached = service.get_from_db(ts_code, trade_date)
        if cached:
            return cached

    # 从API拉取
    return service.fetch_lhb_data(ts_code, trade_date)
