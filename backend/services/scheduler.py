"""
任务调度服务
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from backend.services.stock_selector import select_stocks
from backend.services.notification import FeishuNotifier
from backend.database import SessionLocal
from backend.models import TaskLog, ScheduledTask

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""

    def __init__(self):
        """初始化任务调度器"""
        jobstores = {
            'default': SQLAlchemyJobStore(url='sqlite:///./data/scheduler.db')
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone='Asia/Shanghai'
        )
        self.notifier = FeishuNotifier()

    def start(self) -> None:
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("任务调度器已启动")

            self._load_scheduled_tasks()

    def shutdown(self) -> None:
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("任务调度器已关闭")

    def _load_scheduled_tasks(self) -> None:
        """从数据库加载定时任务"""
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).filter(
                ScheduledTask.enabled == True
            ).all()

            for task in tasks:
                self.add_job(
                    task_id=task.id,
                    task_type=task.task_type,
                    cron_expression=task.cron_expression,
                    config=task.config
                )

            logger.info(f"已加载 {len(tasks)} 个定时任务")
        except Exception as e:
            logger.error(f"加载定时任务失败: {e}")
        finally:
            db.close()

    def add_job(
        self,
        task_id: int,
        task_type: str,
        cron_expression: str,
        config: Optional[str] = None
    ) -> None:
        """
        添加定时任务

        Args:
            task_id: 任务ID
            task_type: 任务类型
            cron_expression: Cron 表达式
            config: 任务配置
        """
        try:
            parts = cron_expression.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
            else:
                raise ValueError(f"无效的 Cron 表达式: {cron_expression}")

            job_id = f"task_{task_id}"

            if task_type == "stock_selection":
                self.scheduler.add_job(
                    self.scheduled_stock_select_job,
                    CronTrigger(
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week,
                        timezone='Asia/Shanghai'
                    ),
                    id=job_id,
                    args=[task_id, config],
                    replace_existing=True
                )
                logger.info(f"已添加定时任务: {job_id}, Cron: {cron_expression}")
            else:
                logger.warning(f"未知的任务类型: {task_type}")

        except Exception as e:
            logger.error(f"添加定时任务失败: {e}")

    def remove_job(self, task_id: int) -> None:
        """
        移除定时任务

        Args:
            task_id: 任务ID
        """
        job_id = f"task_{task_id}"
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"已移除定时任务: {job_id}")
        except Exception as e:
            logger.warning(f"移除定时任务失败: {e}")

    def scheduled_stock_select_job(
        self,
        task_id: int,
        config: Optional[str] = None
    ) -> None:
        """
        定时选股任务

        Args:
            task_id: 任务ID
            config: 任务配置
        """
        db = SessionLocal()
        task_log = None

        try:
            task_log = TaskLog(
                task_type="scheduled",
                trigger_time=datetime.now(),
                status="running"
            )
            db.add(task_log)
            db.commit()

            logger.info(f"开始执行定时选股任务 (ID: {task_id})")

            tdx_mcp_func = self._get_tdx_mcp_func()

            result = select_stocks(
                trade_date=None,
                task_template="default",
                save_result=True,
                tdx_mcp_func=tdx_mcp_func,
            )

            if result.get('passed_count', 0) > 0:
                notification_result = self.notifier.send_selection_result(result)
                if notification_result:
                    logger.info("选股结果通知已发送")
                else:
                    logger.warning("选股结果通知发送失败")

            task_log.status = "success"
            task_log.end_time = datetime.now()
            db.commit()

            logger.info(
                f"定时选股任务完成，选出 {result.get('passed_count', 0)} 只股票"
            )

        except Exception as e:
            logger.error(f"定时选股任务执行失败: {e}", exc_info=True)
            if task_log:
                task_log.status = "failed"
                task_log.error_message = str(e)
                task_log.end_time = datetime.now()
                db.commit()

        finally:
            db.close()

    def execute_immediate_task(
        self,
        task_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        立即执行任务

        Args:
            task_type: 任务类型
            config: 任务配置

        Returns:
            执行结果
        """
        db = SessionLocal()
        task_log = None

        try:
            task_log = TaskLog(
                task_type="manual",
                trigger_time=datetime.now(),
                status="running"
            )
            db.add(task_log)
            db.commit()

            logger.info(f"开始执行手动任务: {task_type}")

            if task_type == "stock_selection":
                result = select_stocks(
                    trade_date=config.get('trade_date') if config else None,
                    task_template=config.get('task_template', 'default') if config else 'default',
                    save_result=True
                )

                if config and config.get('notify', False):
                    if result.get('passed_count', 0) > 0:
                        notification_result = self.notifier.send_selection_result(result)
                        result['notification_sent'] = notification_result

                task_log.status = "success"
                task_log.end_time = datetime.now()
                db.commit()

                return {
                    'success': True,
                    'task_id': task_log.id,
                    'result': result
                }
            else:
                raise ValueError(f"未知的任务类型: {task_type}")

        except Exception as e:
            logger.error(f"手动任务执行失败: {e}", exc_info=True)
            if task_log:
                task_log.status = "failed"
                task_log.error_message = str(e)
                task_log.end_time = datetime.now()
                db.commit()

            return {
                'success': False,
                'task_id': task_log.id if task_log else None,
                'error': str(e)
            }

        finally:
            db.close()

    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        获取所有任务列表

        Returns:
            任务列表
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger)
            })
        return jobs

    def _get_tdx_mcp_func(self):
        """
        获取通达信MCP接口函数

        优先使用外部注入的函数，其次尝试从模块导入
        """
        try:
            from backend.api.stock import _tdx_mcp_func
            if _tdx_mcp_func is not None:
                return _tdx_mcp_func
        except ImportError:
            pass

        try:
            from importlib import import_module
            mcp_module = import_module("mcp_Tong_Da_Xin_MCP_tdx_wenda_quotes")
            return mcp_module.mcp_Tong_Da_Xin_MCP_tdx_wenda_quotes
        except (ImportError, AttributeError):
            logger.info("通达信MCP接口不可用，定时任务将使用降级模式")
            return None


scheduler = TaskScheduler()
