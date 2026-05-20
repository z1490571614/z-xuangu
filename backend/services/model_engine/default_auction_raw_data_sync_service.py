"""
默认竞价接力 V2 训练原始数据同步守护。

只同步训练前依赖的原始数据表：
- stock_daily_data
- stock_minute_bar
- stock_auction_open

不写 default_auction_training_sample，样本构建仍由手动自动学习流程触发。
"""
import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func

from backend.database import SessionLocal
from backend.models import StockAuctionOpen, StockMinuteBar, SystemConfig
from backend.models.seal_rate import StockDailyData
from backend.services.auction_data_service import AuctionDataService
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService
from backend.services.tdx_local_minute_sync_service import TdxLocalMinuteSyncService
from backend.utils.trading_date import get_latest_trading_day, get_previous_trading_day

logger = logging.getLogger(__name__)

RAW_SYNC_STATE_KEY = "default_auction_raw_data_sync_state"
RAW_SYNC_JOB_ID = "default_auction_raw_data_sync_2300"


class DefaultAuctionRawDataSyncService:
    """同步默认竞价模型训练所需原始数据，并记录同交易日成功状态。"""

    def __init__(
        self,
        session_factory=SessionLocal,
        trade_date_provider: Optional[Callable[[], str]] = None,
        daily_sync_factory: Optional[Callable[[], Any]] = None,
        minute_sync_factory: Optional[Callable[[], Any]] = None,
        auction_service_factory: Optional[Callable[[], Any]] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        tdx_vipdoc_path: Optional[str] = None,
        minute_interval: Optional[int] = None,
        commit_every: Optional[int] = None,
    ):
        self.session_factory = session_factory
        self.trade_date_provider = trade_date_provider or get_latest_trading_day
        self.now_provider = now_provider or datetime.now
        self.tdx_vipdoc_path = tdx_vipdoc_path or os.getenv("TDX_VIPDOC_PATH")
        self.minute_interval = minute_interval or int(os.getenv("DEFAULT_AUCTION_RAW_SYNC_MINUTE_INTERVAL", "1"))
        self.commit_every = commit_every or int(os.getenv("DEFAULT_AUCTION_RAW_SYNC_COMMIT_EVERY", "5000"))
        self.daily_sync_factory = daily_sync_factory or self._make_daily_sync_service
        self.minute_sync_factory = minute_sync_factory or self._make_minute_sync_service
        self.auction_service_factory = auction_service_factory or AuctionDataService

    def run_once_if_needed(self, trigger: str) -> Dict[str, Any]:
        """同一交易日已成功同步则跳过，否则执行一次完整原始数据同步。"""
        db = self.session_factory()
        try:
            trade_date = self._resolve_trade_date(trigger)
            state = self._load_state(db)
            if state.get("trade_date") == trade_date and state.get("status") == "success":
                return {"status": "skipped", "trade_date": trade_date, "reason": "already_synced"}
            existing_counts = self._raw_data_counts(db, trade_date)
            if all(int(existing_counts.get(key) or 0) > 0 for key in ("daily", "minute", "auction")):
                result = self._already_present_result(trade_date, trigger, existing_counts)
                self._save_state(db, result)
                return result

            result = self._sync_trade_date(trade_date, trigger)
            self._save_state(db, result)
            return result
        finally:
            close = getattr(db, "close", None)
            if callable(close) and self.session_factory is SessionLocal:
                close()

    def _resolve_trade_date(self, trigger: str) -> str:
        trade_date = self.trade_date_provider()
        if trigger != "startup":
            return trade_date

        now = self.now_provider()
        today = now.strftime("%Y%m%d")
        if trade_date >= today and now.hour < 23:
            return get_previous_trading_day(trade_date)
        return trade_date

    @staticmethod
    def _raw_data_counts(db, trade_date: str) -> Dict[str, int]:
        return {
            "daily": db.query(func.count(StockDailyData.id))
            .filter(StockDailyData.trade_date == trade_date)
            .scalar()
            or 0,
            "minute": db.query(func.count(StockMinuteBar.id))
            .filter(StockMinuteBar.trade_date == trade_date)
            .scalar()
            or 0,
            "auction": db.query(func.count(StockAuctionOpen.id))
            .filter(StockAuctionOpen.trade_date == trade_date)
            .scalar()
            or 0,
        }

    def _already_present_result(
        self,
        trade_date: str,
        trigger: str,
        counts: Dict[str, int],
    ) -> Dict[str, Any]:
        now = self.now_provider().isoformat(timespec="seconds")
        return {
            "trade_date": trade_date,
            "status": "success",
            "trigger": trigger,
            "started_at": now,
            "finished_at": now,
            "stage_results": {
                "daily_sync": {"rows_existing": counts.get("daily", 0), "skipped": True},
                "minute_sync": {"rows_existing": counts.get("minute", 0), "skipped": True},
                "auction_sync": {"rows_existing": counts.get("auction", 0), "skipped": True},
            },
            "error_message": None,
            "reason": "raw_data_already_present",
        }

    def _sync_trade_date(self, trade_date: str, trigger: str) -> Dict[str, Any]:
        started_at = self.now_provider()
        stage_results: Dict[str, Any] = {}
        status = "success"
        error_message = None
        try:
            daily_result = self.daily_sync_factory().sync_range(
                trade_date,
                trade_date,
                ts_codes=None,
                commit_every=self.commit_every,
            )
            stage_results["daily_sync"] = daily_result
            self._assert_stage_has_rows("daily_sync", daily_result, ["rows_synced", "stocks_with_rows"])

            minute_result = self.minute_sync_factory().sync_range(
                trade_date,
                trade_date,
                ts_codes=None,
                interval=self.minute_interval,
                commit_every=self.commit_every,
            )
            stage_results["minute_sync"] = minute_result
            self._assert_stage_has_rows(
                "minute_sync",
                minute_result,
                ["rows_synced", "rows_skipped_existing", "stocks_with_rows"],
            )

            auction_service = self.auction_service_factory()
            auction_count = auction_service.sync_auction_open(trade_date)
            stage_results["auction_sync"] = {"rows_synced": auction_count}
            if int(auction_count or 0) <= 0:
                raise ValueError(f"auction_sync 未同步到 {trade_date} 的 stk_auction 原始数据")

            recalc_result = auction_service.recalculate_auction_ratios_from_daily_cache(trade_date, trade_date)
            stage_results["auction_ratio_recalculate"] = recalc_result
        except Exception as exc:
            logger.exception("默认竞价训练原始数据同步失败: %s trigger=%s", trade_date, trigger)
            status = "failed"
            error_message = str(exc)

        finished_at = self.now_provider()
        return {
            "trade_date": trade_date,
            "status": status,
            "trigger": trigger,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "stage_results": stage_results,
            "error_message": error_message,
        }

    @staticmethod
    def _assert_stage_has_rows(stage: str, result: Dict[str, Any], keys: list[str]) -> None:
        if any(int(result.get(key) or 0) > 0 for key in keys):
            return
        raise ValueError(f"{stage} 未同步到原始数据: {result}")

    def _make_daily_sync_service(self) -> TdxLocalDailySyncService:
        return TdxLocalDailySyncService(tdx_vipdoc_path=self.tdx_vipdoc_path)

    def _make_minute_sync_service(self) -> TdxLocalMinuteSyncService:
        return TdxLocalMinuteSyncService(tdx_vipdoc_path=self.tdx_vipdoc_path)

    @staticmethod
    def _load_state(db) -> Dict[str, Any]:
        row = db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).first()
        if row is None or not row.value:
            return {}
        try:
            value = json.loads(row.value)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _save_state(db, payload: Dict[str, Any]) -> None:
        row = db.query(SystemConfig).filter(SystemConfig.key == RAW_SYNC_STATE_KEY).first()
        if row is None:
            row = SystemConfig(
                key=RAW_SYNC_STATE_KEY,
                value_type="json",
                description="默认竞价接力 V2 训练原始数据最近一次同步状态",
            )
            db.add(row)
        row.value = json.dumps(payload, ensure_ascii=False, default=str)
        row.value_type = "json"
        row.description = "默认竞价接力 V2 训练原始数据最近一次同步状态"
        db.commit()


class DefaultAuctionRawDataSyncScheduler:
    """启动时触发一次，并在每天 23:00 再同步一次原始训练数据。"""

    def __init__(
        self,
        scheduler: Optional[Any] = None,
        service_factory: Optional[Callable[[], DefaultAuctionRawDataSyncService]] = None,
    ):
        self.scheduler = scheduler or BackgroundScheduler(timezone="Asia/Shanghai")
        self.service_factory = service_factory or DefaultAuctionRawDataSyncService

    def start(self) -> None:
        if getattr(self.scheduler, "running", False):
            return
        self.scheduler.add_job(
            self._run_daily_2300,
            CronTrigger(hour=23, minute=0, timezone="Asia/Shanghai"),
            id=RAW_SYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        logger.info("默认竞价训练原始数据同步调度器已启动，每天 23:00 执行")

    def run_startup_once_async(self) -> None:
        thread = threading.Thread(target=self._run_startup, daemon=True)
        thread.start()

    def stop(self) -> None:
        if getattr(self.scheduler, "running", False):
            self.scheduler.shutdown(wait=False)
            logger.info("默认竞价训练原始数据同步调度器已停止")

    def _run_startup(self) -> None:
        try:
            self.service_factory().run_once_if_needed(trigger="startup")
        except Exception:
            logger.exception("默认竞价训练原始数据启动同步异常")

    def _run_daily_2300(self) -> None:
        try:
            self.service_factory().run_once_if_needed(trigger="daily_2300")
        except Exception:
            logger.exception("默认竞价训练原始数据 23 点同步异常")


def get_default_auction_raw_data_sync_scheduler() -> DefaultAuctionRawDataSyncScheduler:
    if not hasattr(get_default_auction_raw_data_sync_scheduler, "_instance"):
        get_default_auction_raw_data_sync_scheduler._instance = DefaultAuctionRawDataSyncScheduler()
    return get_default_auction_raw_data_sync_scheduler._instance


def get_default_auction_raw_data_sync_state(db) -> Dict[str, Any]:
    """返回默认竞价训练原始数据最近一次同步状态，供模型中心展示水位。"""
    state = DefaultAuctionRawDataSyncService._load_state(db)
    data_max_dates = {
        "daily": db.query(func.max(StockDailyData.trade_date)).scalar(),
        "minute": db.query(func.max(StockMinuteBar.trade_date)).scalar(),
        "auction": db.query(func.max(StockAuctionOpen.trade_date)).scalar(),
    }
    present_dates = [value for value in data_max_dates.values() if value]
    synced_to_date = min(present_dates) if len(present_dates) == len(data_max_dates) else None
    if not state:
        return {
            "trade_date": None,
            "synced_to_date": synced_to_date,
            "status": "not_synced",
            "trigger": None,
            "started_at": None,
            "finished_at": None,
            "data_max_dates": data_max_dates,
            "stage_results": {},
            "error_message": None,
        }
    return {
        "trade_date": state.get("trade_date"),
        "synced_to_date": synced_to_date or state.get("trade_date"),
        "status": state.get("status") or "unknown",
        "trigger": state.get("trigger"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "data_max_dates": data_max_dates,
        "stage_results": state.get("stage_results") or {},
        "error_message": state.get("error_message"),
    }
