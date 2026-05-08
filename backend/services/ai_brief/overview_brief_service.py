"""
综合概览服务 - 编排AI调用/fallback生成/持久化
AI不可用时自动降级为本地模板
"""
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.database import SessionLocal
from backend.models import StockOverviewBrief
from backend.services.scoring_v2 import (
    AlphaScoreService, RiskScoreService, FinalScoreService, DecisionEngine,
    StockScoringV2Service, is_score_v2_enabled,
)
from backend.models import StockScoreV2, SelectedStock, SelectionRecord
from backend.models.stock_risk import DragonLeaderScore
from backend.services.ai_brief.ai_client import get_ai_client, AIClient
from backend.services.ai_brief.tag_builder import TagBuilder
from backend.services.ai_brief.overview_prompt_builder import OverviewPromptBuilder
from backend.services.ai_brief.output_validator import OutputValidator

logger = logging.getLogger(__name__)

DISCLAIMER = "本内容由系统根据结构化数据和公开信息整理生成，仅供参考，不构成投资建议。"


class OverviewBriefService:

    @staticmethod
    def get_or_build(stock_code: str, stock_name: Optional[str] = None,
                     trade_date: Optional[str] = None, record_id: Optional[int] = None) -> Dict[str, Any]:
        """获取或构建综合概览 - 有有效缓存直接返回，无缓存再调AI"""
        ai_client = get_ai_client()

        # 检查DB缓存
        db = SessionLocal()
        cached = None
        try:
            cached = db.query(StockOverviewBrief).filter(
                StockOverviewBrief.stock_code == stock_code,
                StockOverviewBrief.trade_date == trade_date,
            ).first()
        except Exception:
            pass
        finally:
            db.close()

        # 有有效缓存 → 直接返回，不再调AI
        if cached and cached.output_status in ("available", "partial"):
            return OverviewBriefService._to_dict(cached)

        # AI可用 → 生成新内容
        if ai_client.available:
            input_data = OverviewBriefService._build_input(stock_code, stock_name, trade_date, record_id)
            result = OverviewBriefService._generate(input_data)
            if result.get("data_status") != "fallback_generated":
                return result

        # AI不可用或生成失败 → 用缓存（即使状态是失败的）
        if cached:
            return OverviewBriefService._to_dict(cached)

        # 完全没有缓存 → fallback生成
        input_data = OverviewBriefService._build_input(stock_code, stock_name, trade_date, record_id)
        return OverviewBriefService._generate(input_data)

    @staticmethod
    def _build_input(stock_code: str, stock_name: Optional[str],
                     trade_date: Optional[str], record_id: Optional[int]) -> Dict[str, Any]:
        """构建AI输入的结构化数据"""
        import time

        # 多线程环境SQLite可能偶发竞争，最多重试3次
        for attempt in range(3):
            db = None
            data = {
                "stock": {"stock_code": stock_code, "stock_name": stock_name, "trade_date": trade_date},
                "score": {},
                "decision": {},
                "risk": {},
                "event_driver": {},
                "sector": {},
                "liquidity": {},
                "market_background": {},
            }
            try:
                db = SessionLocal()
                # 获取评分V2数据
                if record_id or trade_date:
                    score = db.query(StockScoreV2).filter(
                        StockScoreV2.stock_code == stock_code
                    )
                    if record_id:
                        score = score.filter(StockScoreV2.selection_record_id == record_id)
                    if trade_date:
                        score = score.filter(StockScoreV2.trade_date == trade_date)
                    score = score.order_by(StockScoreV2.id.desc()).first()

                    if score:
                        data["score"] = {
                            "alpha_score": score.alpha_score,
                            "risk_score": score.risk_score,
                            "final_score": score.final_score,
                            "score_grade": score.score_grade,
                            "trade_value_score": score.alpha_score,
                            "event_score": (score.alpha_score or 0) * 0.3 if score.alpha_score else None,
                            "liquidity_score": (score.alpha_score or 0) * 0.4 if score.alpha_score else None,
                            "sector_score": (score.alpha_score or 0) * 0.25 if score.alpha_score else None,
                            "market_regime_score": 55,
                        }
                        data["decision"] = {
                            "action_level": score.action_level,
                            "position_suggestion": score.position_suggestion,
                            "entry_suggestion": score.entry_suggestion,
                        }
                        data["risk"] = {
                            "risk_score": score.risk_score,
                            "risk_items": json.loads(score.risk_flags) if score.risk_flags else [],
                        }

                # 获取龙头战法评分
                dl_score = db.query(DragonLeaderScore).filter(
                    DragonLeaderScore.ts_code == stock_code,
                    DragonLeaderScore.trade_date == trade_date,
                ).order_by(DragonLeaderScore.id.desc()).first()
                if dl_score:
                    data["dragon_leader"] = {
                        "leader_strength_score": dl_score.leader_strength_score,
                        "retreat_risk_score": dl_score.retreat_risk_score,
                        "health_score": dl_score.health_score,
                        "leader_level": dl_score.leader_level,
                        "cycle_stage": dl_score.cycle_stage,
                        "lhb_alpha_score": dl_score.lhb_alpha_score or 0,
                        "announcement_alpha_score": dl_score.announcement_alpha_score or 0,
                    }

                # 获取选股数据（行情背景）
                if not stock_name:
                    if record_id:
                        stock_db = db.query(SelectedStock).filter(
                            SelectedStock.record_id == record_id,
                            SelectedStock.ts_code == stock_code,
                        ).first()
                        if stock_db:
                            stock_name = stock_db.name
                            data["stock"]["stock_name"] = stock_name
                            data["market_background"] = {
                                "is_limit_up": stock_db.change_pct is not None and stock_db.change_pct >= 9.8,
                                "pct_chg": f"{stock_db.change_pct:.2f}%" if stock_db.change_pct else None,
                                "current_limitup_streak": 1 if stock_db.pre_change_pct is not None and stock_db.pre_change_pct >= 9.5 else 0,
                            }
                            data["liquidity"] = {
                                "circ_mv": stock_db.circ_mv,
                                "auction_turnover_rate": stock_db.auction_turnover_rate,
                                "liquidity_score": 55,
                            }
                            data["sector"] = {
                                "industry": stock_db.industry,
                                "sector_score": 50,
                            }
                elif trade_date:
                    rec = db.query(SelectionRecord).filter(
                        SelectionRecord.trade_date == trade_date,
                        SelectionRecord.status == "success",
                    ).order_by(SelectionRecord.id.desc()).first()
                    if rec:
                        stock_db = db.query(SelectedStock).filter(
                            SelectedStock.record_id == rec.id,
                            SelectedStock.ts_code == stock_code,
                        ).first()
                        if stock_db:
                            data["market_background"]["is_limit_up"] = stock_db.change_pct is not None and stock_db.change_pct >= 9.8
                            data["market_background"]["pct_chg"] = f"{stock_db.change_pct:.2f}%" if stock_db.change_pct else None
                            data["sector"]["industry"] = stock_db.industry
                            data["liquidity"]["circ_mv"] = stock_db.circ_mv

                break  # 成功则退出重试循环
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                logger.warning(f"构建输入数据失败(已重试{attempt}次): {e}")
            finally:
                if db:
                    db.close()

        # 生成正负标签
        data["positive_factors"] = TagBuilder.build_positive(data)
        data["negative_factors"] = TagBuilder.build_negative(data)

        return data

    @staticmethod
    def _generate(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """实际生成综合概览（AI优先，不可用时fallback）"""
        ai_client = get_ai_client()
        logger.info(f"AI客户端状态: available={ai_client.available}, type={type(ai_client).__name__}")

        if ai_client.available:
            try:
                prompt = OverviewPromptBuilder.build(input_data)
                logger.info("开始调用AI生成综合简报...")
                result = ai_client.generate_json(prompt)
                valid, error = OutputValidator.validate(result)
                if valid:
                    sanitized = OutputValidator.sanitize_fallback(result, input_data)
                    logger.info("AI综合简报生成成功")
                    return OverviewBriefService._save(input_data, sanitized, ai_provider=type(ai_client).__name__)
                else:
                    logger.warning(f"AI输出校验失败: {error}")
            except Exception as e:
                logger.warning(f"AI调用失败，降级为fallback: {type(e).__name__}: {e}")

        return OverviewBriefService._fallback(input_data)

    @staticmethod
    def _fallback(data: Dict[str, Any]) -> Dict[str, Any]:
        """AI不可用时基于结构化评分生成简报（不再显示AI不可用提示）"""
        score = data.get("score", {})
        fs = score.get("final_score")
        rs = score.get("risk_score")
        alpha = score.get("alpha_score")
        action = data.get("decision", {}).get("action_level", "观察")
        positives = data.get("positive_factors", [])
        negatives = data.get("negative_factors", [])

        suggestion = action if action in ["不关注", "只观察", "开盘确认", "小仓试错", "不参与"] else "只观察"
        if fs is not None:
            if fs >= 75 and (rs is None or rs <= 40):
                suggestion = "开盘确认"
            elif fs >= 50:
                suggestion = "只观察"
            else:
                suggestion = "不关注"

        brief_parts = []
        if fs is not None:
            brief_parts.append(f"最终评分{fs:.0f}级（{score.get('score_grade', '')}）")
        if alpha is not None:
            brief_parts.append(f"交易价值分{alpha:.0f}")
        if rs is not None:
            brief_parts.append(f"风险评分{rs:.0f}")
        if positives:
            brief_parts.append(f"正面因素：{'、'.join(positives[:3])}")
        if negatives:
            brief_parts.append(f"风险因素：{'、'.join(negatives[:3])}")

        if fs is not None:
            score_desc = "偏强" if fs >= 60 else "中等" if fs >= 40 else "偏弱"
            risk_desc = "风险较低" if rs is not None and rs <= 30 else "风险中等" if rs is not None and rs <= 50 else "风险较高"
            brief = f"该股综合评分{score_desc}（{risk_desc}）。当前建议：{suggestion}。{' '.join(brief_parts)}"
        else:
            if brief_parts:
                brief = f"基于当前数据分析，建议{suggestion}。{' '.join(brief_parts)}"
            else:
                brief = f"暂无足够评分数据，建议谨慎观察。当前建议：{suggestion}。"

        suggestion_reason_parts = []
        if fs is not None:
            suggestion_reason_parts.append(f"最终评分{fs}")
        if rs is not None:
            suggestion_reason_parts.append(f"风险评分{rs}")
        if positives:
            suggestion_reason_parts.append(f"正面因素：{'、'.join(positives[:2])}")
        if negatives:
            suggestion_reason_parts.append(f"风险因素：{'、'.join(negatives[:2])}")
        suggestion_reason = "；".join(suggestion_reason_parts) if suggestion_reason_parts else "基于当前可获取的结构化评分数据"

        key_points = []
        if fs is not None:
            key_points.append(f"最终评分{fs}（{score.get('score_grade', '')}）")
        if rs is not None:
            key_points.append(f"风险评分{rs}")
        if positives:
            key_points.append(f"正面因素：{'、'.join(positives[:3])}")
        if negatives:
            key_points.append(f"关注风险：{'、'.join(negatives[:3])}")
        if not key_points:
            key_points = ["暂无评分数据", "本简报基于结构化数据生成"]

        result = {
            "brief": brief,
            "ai_suggestion": suggestion,
            "suggestion_reason": suggestion_reason,
            "positive_tags": positives or [],
            "negative_tags": negatives or [],
            "key_points": key_points,
            "disclaimer": DISCLAIMER,
        }

        return OverviewBriefService._save(data, result, output_status="fallback_generated")

    @staticmethod
    def _save(input_data: Dict[str, Any], content: Dict[str, Any],
              ai_provider: str = "fallback", output_status: str = "available") -> Dict[str, Any]:
        """保存到数据库"""
        stock = input_data.get("stock", {})
        db = SessionLocal()
        try:
            record = StockOverviewBrief(
                stock_code=stock.get("stock_code", ""),
                stock_name=stock.get("stock_name"),
                trade_date=stock.get("trade_date", ""),
                brief=content.get("brief"),
                ai_suggestion=content.get("ai_suggestion"),
                suggestion_reason=content.get("suggestion_reason"),
                positive_tags_json=json.dumps(content.get("positive_tags", []), ensure_ascii=False),
                negative_tags_json=json.dumps(content.get("negative_tags", []), ensure_ascii=False),
                key_points_json=json.dumps(content.get("key_points", []), ensure_ascii=False),
                input_snapshot_json=json.dumps(input_data, ensure_ascii=False),
                ai_provider=ai_provider,
                output_status=output_status,
                disclaimer=content.get("disclaimer", DISCLAIMER),
            )
            db.add(record)
            db.commit()

            result = {
                "stock_code": record.stock_code,
                "stock_name": record.stock_name,
                "trade_date": record.trade_date,
                "data_status": output_status,
                "brief": content.get("brief"),
                "ai_suggestion": content.get("ai_suggestion"),
                "suggestion_reason": content.get("suggestion_reason"),
                "positive_tags": content.get("positive_tags", []),
                "negative_tags": content.get("negative_tags", []),
                "key_points": content.get("key_points", []),
                "output_status": output_status,
                "disclaimer": content.get("disclaimer", DISCLAIMER),
            }
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"保存综合概览失败: {e}")
            content["data_status"] = "fallback_generated"
            return {
                "stock_code": stock.get("stock_code", ""),
                "data_status": "fallback_generated",
                "brief": content.get("brief", "生成失败"),
                "ai_suggestion": content.get("ai_suggestion", "只观察"),
                "positive_tags": content.get("positive_tags", []),
                "negative_tags": content.get("negative_tags", []),
                "key_points": content.get("key_points", []),
                "disclaimer": DISCLAIMER,
            }
        finally:
            db.close()

    @staticmethod
    def _to_dict(record: StockOverviewBrief) -> Dict[str, Any]:
        return {
            "stock_code": record.stock_code,
            "stock_name": record.stock_name,
            "trade_date": record.trade_date,
            "data_status": record.output_status or "available",
            "brief": record.brief,
            "ai_suggestion": record.ai_suggestion,
            "suggestion_reason": record.suggestion_reason,
            "positive_tags": json.loads(record.positive_tags_json) if record.positive_tags_json else [],
            "negative_tags": json.loads(record.negative_tags_json) if record.negative_tags_json else [],
            "key_points": json.loads(record.key_points_json) if record.key_points_json else [],
            "output_status": record.output_status,
            "disclaimer": record.disclaimer or DISCLAIMER,
        }
