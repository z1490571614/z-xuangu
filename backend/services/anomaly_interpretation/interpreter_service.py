"""
异动解读服务 - 同花顺1:1复刻版（采用与综合概览相同的机制）
集成AI分析，优化数据输入输出流程
"""
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from backend.database import SessionLocal
from backend.models import StockAnomalyInterpretation
from backend.models import SelectedStock, SelectionRecord
from backend.services.integrated_news_service import get_integrated_news_service
from backend.services.ai_brief.ai_client import get_ai_client
from backend.services.anomaly_interpretation.anomaly_prompt_builder import AnomalyPromptBuilder
from backend.services.anomaly_interpretation.output_validator import OutputValidator

logger = logging.getLogger(__name__)

DISCLAIMER = "本内容由AI技术搜集公开信息总结生成，仅供参考，不构成投资建议，以上市公司公告为准。"


class AnomalyInterpretationService:
    """异动解读服务"""

    @staticmethod
    def get_or_build(
        stock_code: str,
        stock_name: Optional[str] = None,
        trade_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """获取缓存或构建异动解读（与综合概览相同的机制）"""
        db = SessionLocal()
        try:
            # 检查缓存（除非强制刷新）
            if trade_date and not force_refresh:
                existing = db.query(StockAnomalyInterpretation).filter(
                    StockAnomalyInterpretation.stock_code == stock_code,
                    StockAnomalyInterpretation.trade_date == trade_date,
                ).first()
                if existing:
                    logger.info(f"使用缓存的异动解读: {stock_code} {trade_date}")
                    return AnomalyInterpretationService._to_dict(existing)
            
            # 强制刷新时删除旧记录
            if trade_date and force_refresh:
                db.query(StockAnomalyInterpretation).filter(
                    StockAnomalyInterpretation.stock_code == stock_code,
                    StockAnomalyInterpretation.trade_date == trade_date,
                ).delete()
                db.commit()
                logger.info(f"已删除旧的异动解读记录: {stock_code} {trade_date}")

        except Exception:
            pass
        finally:
            db.close()

        # 构建输入数据并生成
        input_data = AnomalyInterpretationService._build_input(stock_code, stock_name, trade_date)
        return AnomalyInterpretationService._generate(input_data)

    @staticmethod
    def _build_input(
        stock_code: str,
        stock_name: Optional[str],
        trade_date: Optional[str],
    ) -> Dict[str, Any]:
        """构建输入数据（与综合概览相同的结构）"""
        db = SessionLocal()
        input_data = {
            "stock": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "trade_date": trade_date,
            },
            "news_list": [],
            "industry_news": [],
            "market_data": {},
        }

        try:
            # 从数据库获取新闻（完整正文+情感标签，复用新闻舆情模块已采集的数据）
            news_svc = get_integrated_news_service()
            try:
                news_result = news_svc.get_stock_news(
                    stock_name=stock_name or stock_code.split(".")[0],
                    limit=20,
                    ensure_recent=False  # 调度器已定时采集，避免重复触发
                )
                if news_result.get("code") == 200:
                    raw_list = news_result.get("data", {}).get("news_list", [])
                    # 保留完整字段（title, content, source_name, publish_time, sentiment_type）
                    input_data["news_list"] = raw_list
                    source_dist = news_result.get("data", {}).get("source_distribution", {})
                    logger.info(f"从数据库获取个股新闻：{len(raw_list)}条 (来源分布: {source_dist})")
            except Exception as e:
                logger.warning(f"从数据库获取新闻失败: {e}")
            finally:
                news_svc.close()

            # 获取行情数据
            if trade_date:
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
                        if not stock_name:
                            stock_name = stock_db.name
                            input_data["stock"]["stock_name"] = stock_name
                        input_data["market_data"] = {
                            "price": stock_db.close_price,
                            "pct_chg": stock_db.change_pct,
                            "circ_mv": stock_db.circ_mv,
                        }

        except Exception as e:
            logger.warning(f"构建输入数据时出错: {e}")
        finally:
            db.close()

        return input_data

    @staticmethod
    def _generate(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """实际生成异动解读（AI优先，不可用时fallback，与综合概览相同）"""
        ai_client = get_ai_client()
        logger.info(f"AI客户端状态: available={ai_client.available}, type={type(ai_client).__name__}")

        if ai_client.available:
            try:
                prompt = AnomalyPromptBuilder.build(input_data)
                logger.info(f"开始调用AI生成异动解读... (stock_code={input_data.get('stock', {}).get('stock_code')})")
                
                result = ai_client.generate_json(prompt)
                valid, error = OutputValidator.validate(result)
                if valid:
                    sanitized = OutputValidator.sanitize(result)
                    logger.info("AI异动解读生成成功")
                    return AnomalyInterpretationService._save(input_data, sanitized, ai_provider=type(ai_client).__name__)
                else:
                    logger.warning(f"AI输出校验失败: {error}")
            except Exception as e:
                logger.warning(f"AI调用失败，降级为fallback: {type(e).__name__}: {e}")

        return AnomalyInterpretationService._fallback(input_data)

    @staticmethod
    def _fallback(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI不可用时生成fallback异动解读（与综合概览相同的机制）"""
        stock = input_data.get("stock", {})
        stock_name = stock.get("stock_name", "")
        market_data = input_data.get("market_data", {})

        result = OutputValidator.build_fallback(input_data)

        # 构建完整结果
        full_result = {
            "stock_code": stock.get("stock_code", ""),
            "stock_name": stock_name,
            "trade_date": stock.get("trade_date", ""),
            "news_window_type": "weekly_3d",
            "core_tags_line": result["core_tags_line"],
            "industry_reason": result["industry_reason"],
            "company_reasons": result["company_reasons"],
            "market_background": AnomalyInterpretationService._build_market_background(market_data),
            "disclaimer": DISCLAIMER,
            "data_status": "fallback_generated",
        }

        return AnomalyInterpretationService._save(input_data, full_result, output_status="fallback_generated")

    @staticmethod
    def _save(
        input_data: Dict[str, Any],
        content: Dict[str, Any],
        ai_provider: str = "fallback",
        output_status: str = "available",
    ) -> Dict[str, Any]:
        """保存到数据库（与综合概览相同的机制）"""
        stock = input_data.get("stock", {})
        db = SessionLocal()
        try:
            # 如果 trade_date 为空，使用今天的日期
            trade_date = stock.get("trade_date", "")
            if not trade_date:
                trade_date = datetime.now().strftime("%Y%m%d")
            
            record = StockAnomalyInterpretation(
                stock_code=stock.get("stock_code", ""),
                stock_name=stock.get("stock_name"),
                trade_date=trade_date,
                # 旧版字段（保留兼容）
                summary_title=content.get("core_tags_line", ""),
                summary_text="，".join(content.get("company_reasons", [])),
                main_reasons_json=json.dumps(content.get("company_reasons", []), ensure_ascii=False),
                event_cards_json=json.dumps([], ensure_ascii=False),
                tags_json=json.dumps(content.get("core_tags_line", "").split("+") if content.get("core_tags_line") else [], ensure_ascii=False),
                risk_notes_json=json.dumps([], ensure_ascii=False),
                data_sources_json=json.dumps([], ensure_ascii=False),
                # 新版同花顺字段
                core_tags_line=content.get("core_tags_line", ""),
                industry_reason=content.get("industry_reason", ""),
                company_reasons_json=json.dumps(content.get("company_reasons", []), ensure_ascii=False),
                market_background=content.get("market_background", ""),
                news_window_type=content.get("news_window_type", "weekly_3d"),
                # 其他字段
                generated_by=ai_provider,
                data_status=output_status,
                disclaimer=content.get("disclaimer", DISCLAIMER),
            )
            db.add(record)
            db.commit()

            result = {
                "stock_code": record.stock_code,
                "stock_name": record.stock_name,
                "trade_date": record.trade_date,
                "data_status": output_status,
                "core_tags_line": content.get("core_tags_line", ""),
                "industry_reason": content.get("industry_reason", ""),
                "company_reasons": content.get("company_reasons", []),
                "market_background": content.get("market_background", ""),
                "news_window_type": content.get("news_window_type", "weekly_3d"),
                "disclaimer": content.get("disclaimer", DISCLAIMER),
            }
            logger.info(f"异动解读已保存: {record.stock_code} {record.trade_date}")
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"保存异动解读失败: {e}")
            content["data_status"] = "fallback_generated"
            return {
                "stock_code": stock.get("stock_code", ""),
                "stock_name": stock.get("stock_name"),
                "trade_date": stock.get("trade_date", ""),
                "data_status": "fallback_generated",
                "core_tags_line": content.get("core_tags_line", "无明确催化"),
                "industry_reason": content.get("industry_reason", "行业数据暂时无法获取"),
                "company_reasons": content.get("company_reasons", ["异动解读服务暂时不可用"]),
                "disclaimer": DISCLAIMER,
            }
        finally:
            db.close()

    @staticmethod
    def _build_market_background(market_data: Dict[str, Any]) -> str:
        """构建行情背景字符串"""
        if not market_data:
            return ""

        parts = []
        price = market_data.get("price")
        pct_chg = market_data.get("pct_chg")

        if price is not None:
            parts.append(f"今日竞价：{price}元")
        if pct_chg is not None:
            parts.append(f"涨跌幅{pct_chg:.2f}%")

        return "，".join(parts) if parts else ""

    @staticmethod
    def _to_dict(record: StockAnomalyInterpretation) -> Dict[str, Any]:
        """将数据库记录转换为字典"""
        result = {
            "stock_code": record.stock_code,
            "stock_name": record.stock_name,
            "trade_date": record.trade_date,
            "data_status": record.data_status or "available",
            "disclaimer": record.disclaimer or DISCLAIMER,
        }

        # 优先使用新版同花顺字段
        if record.core_tags_line:
            result.update({
                "core_tags_line": record.core_tags_line,
                "industry_reason": record.industry_reason,
                "company_reasons": json.loads(record.company_reasons_json) if record.company_reasons_json else [],
                "market_background": record.market_background,
                "news_window_type": record.news_window_type,
            })
        else:
            # 兼容旧版数据
            result.update({
                "summary_title": record.summary_title,
                "summary_text": record.summary_text,
                "main_reasons": json.loads(record.main_reasons_json) if record.main_reasons_json else [],
                "event_cards": json.loads(record.event_cards_json) if record.event_cards_json else [],
                "tags": json.loads(record.tags_json) if record.tags_json else [],
            })

        return result


def get_anomaly_interpretation(
    ts_code: str,
    stock_name: Optional[str] = None,
    trade_date: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """获取异动解读（对外接口）"""
    return AnomalyInterpretationService.get_or_build(
        ts_code, stock_name, trade_date, force_refresh
    )
