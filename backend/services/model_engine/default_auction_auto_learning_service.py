"""
默认竞价接力 V2 手动自动学习编排服务。
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    DefaultAuctionAutoLearningRun,
    DefaultAuctionTrainingSample,
    ModelTrainingJob,
    ModelVersion,
    SelectedStock,
    SelectionRecord,
)
from backend.services.auction_data_service import AuctionDataService
from backend.services.model_engine.default_auction_backtest_service import run_default_auction_relay_backtest
from backend.services.model_engine.default_auction_relay_job_service import (
    create_default_auction_relay_job,
    get_default_auction_relay_diagnostics,
    run_default_auction_relay_training_job,
)
from backend.services.model_engine.default_auction_sample_builder import (
    build_samples_from_replay_range,
    build_samples_from_selected_record,
)
from backend.services.model_engine.default_auction_training_data_audit import audit_default_auction_training_data
from backend.services.model_engine.model_management_service import activate_model_version, refresh_record_predictions
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService
from backend.services.tdx_local_minute_sync_service import TdxLocalMinuteSyncService


TARGET_VERSION_FIELDS = {
    "default_auction_t0_limit_lgbm": "min_t0_auc",
    "default_auction_t1_premium_lgbm": "min_t1_premium_auc",
    "default_auction_t1_continue_lgbm": "min_t1_continue_auc",
}

ACTIVE_AUTO_LEARNING_STATUSES = ("pending", "running")
_CREATE_AUTO_LEARNING_RUN_LOCK = Lock()

PHASE_PROGRESS = {
    "prepare": 5,
    "sync_daily": 15,
    "sync_minute": 25,
    "recalculate_auction_ratios": 35,
    "validate_replay": 45,
    "build_real_samples": 52,
    "build_replay_samples": 60,
    "audit_training_data": 68,
    "training": 78,
    "backtest": 88,
    "activate": 94,
    "refresh_predictions": 98,
    "finish": 100,
}


@dataclass
class DefaultAuctionAutoLearningCreate:
    start_date: str
    end_date: str
    tdx_vipdoc_path: Optional[str] = None
    ts_codes: Optional[List[str]] = None
    selected_record_ids: Optional[List[int]] = None
    refresh_record_ids: Optional[List[int]] = None
    sync_daily: bool = True
    sync_minute: bool = True
    recalculate_auction_ratios: bool = True
    validate_replay: bool = True
    build_real_samples: bool = False
    build_replay_samples: bool = False
    audit_training_data: bool = True
    run_training: bool = False
    run_backtest: bool = False
    auto_activate: bool = False
    refresh_predictions: bool = False
    validation_recent_days: int = 5
    recent_record_limit: int = 5
    minute_interval: int = 1
    commit_every: int = 5000
    params: Dict[str, Any] = field(default_factory=dict)
    acceptance: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        for name in ("start_date", "end_date"):
            value = getattr(self, name)
            if not value.isdigit() or len(value) != 8:
                raise ValueError(f"{name} 必须是8位日期YYYYMMDD")
        if self.start_date > self.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        stages = [
            self.sync_daily,
            self.sync_minute,
            self.recalculate_auction_ratios,
            self.validate_replay,
            self.build_real_samples,
            self.build_replay_samples,
            self.audit_training_data,
            self.run_training,
            self.run_backtest,
            self.refresh_predictions,
        ]
        if not any(stages):
            raise ValueError("至少启用一个自动学习阶段")
        if self.auto_activate and not (self.audit_training_data and self.run_training and self.run_backtest):
            raise ValueError("auto_activate=true 时必须启用 audit_training_data、run_training、run_backtest")


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _load_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _append_log(run: DefaultAuctionAutoLearningRun, message: str, level: str = "info") -> None:
    logs = _load_json(run.logs_json, [])
    logs.append({"time": datetime.now().isoformat(timespec="seconds"), "level": level, "message": message})
    run.logs_json = _dump_json(logs)


def find_active_auto_learning_run(db: Session) -> Optional[DefaultAuctionAutoLearningRun]:
    return (
        db.query(DefaultAuctionAutoLearningRun)
        .filter(DefaultAuctionAutoLearningRun.status.in_(ACTIVE_AUTO_LEARNING_STATUSES))
        .order_by(DefaultAuctionAutoLearningRun.id.asc())
        .first()
    )


def create_auto_learning_run(db: Session, request: DefaultAuctionAutoLearningCreate) -> DefaultAuctionAutoLearningRun:
    request.validate()
    options = asdict(request)
    run = DefaultAuctionAutoLearningRun(
        status="pending",
        phase="prepare",
        progress=0,
        start_date=request.start_date,
        end_date=request.end_date,
        tdx_vipdoc_path=request.tdx_vipdoc_path,
        ts_codes_json=_dump_json(request.ts_codes) if request.ts_codes is not None else None,
        selected_record_ids_json=_dump_json(request.selected_record_ids) if request.selected_record_ids else None,
        options_json=_dump_json(options),
        stage_results_json="{}",
        logs_json="[]",
    )
    _append_log(run, "自动学习运行已创建")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_or_reuse_auto_learning_run(
    db: Session, request: DefaultAuctionAutoLearningCreate
) -> Tuple[DefaultAuctionAutoLearningRun, bool]:
    request.validate()
    with _CREATE_AUTO_LEARNING_RUN_LOCK:
        active_run = find_active_auto_learning_run(db)
        if active_run is not None:
            _append_log(active_run, "检测到已有自动学习运行，复用当前运行")
            db.commit()
            db.refresh(active_run)
            return active_run, False
        return create_auto_learning_run(db, request), True


def get_auto_learning_run(db: Session, run_id: int) -> Dict[str, Any]:
    run = db.query(DefaultAuctionAutoLearningRun).filter(DefaultAuctionAutoLearningRun.id == run_id).first()
    if run is None:
        raise ValueError(f"自动学习运行不存在: {run_id}")
    return _run_payload(run)


def list_auto_learning_runs(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        db.query(DefaultAuctionAutoLearningRun)
        .order_by(DefaultAuctionAutoLearningRun.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [_run_payload(row) for row in rows]


def request_cancel_auto_learning_run(db: Session, run_id: int) -> Dict[str, Any]:
    run = db.query(DefaultAuctionAutoLearningRun).filter(DefaultAuctionAutoLearningRun.id == run_id).first()
    if run is None:
        raise ValueError(f"自动学习运行不存在: {run_id}")
    if run.status == "pending":
        run.status = "cancelled"
        run.phase = "finish"
        run.progress = 100
        run.finished_at = datetime.now()
        _append_log(run, "自动学习运行已取消")
    elif run.status == "running":
        options = _load_json(run.options_json, {})
        options["cancel_requested"] = True
        run.options_json = _dump_json(options)
        _append_log(run, "已请求取消，将在阶段边界停止")
    db.commit()
    db.refresh(run)
    return _run_payload(run)


def run_auto_learning(run_id: int) -> None:
    DefaultAuctionAutoLearningService().run_auto_learning(run_id)


class DefaultAuctionAutoLearningService:
    def __init__(
        self,
        session_factory=SessionLocal,
        daily_sync_factory: Callable[[Optional[str]], Any] = lambda path: TdxLocalDailySyncService(tdx_vipdoc_path=path),
        minute_sync_factory: Callable[[Optional[str]], Any] = lambda path: TdxLocalMinuteSyncService(tdx_vipdoc_path=path),
        auction_service_factory: Callable[[], Any] = AuctionDataService,
        validate_replay_func: Optional[Callable[..., Dict[str, Any]]] = None,
        build_real_sample_func: Callable[..., Dict[str, Any]] = build_samples_from_selected_record,
        build_replay_sample_func: Callable[..., Dict[str, Any]] = build_samples_from_replay_range,
        audit_func: Callable[..., Dict[str, Any]] = audit_default_auction_training_data,
        create_job_func: Callable[..., ModelTrainingJob] = create_default_auction_relay_job,
        run_training_func: Callable[[int], None] = run_default_auction_relay_training_job,
        diagnostics_func: Callable[..., Dict[str, Any]] = get_default_auction_relay_diagnostics,
        backtest_func: Callable[..., Dict[str, Any]] = run_default_auction_relay_backtest,
        activate_func: Callable[..., Dict[str, Any]] = activate_model_version,
        refresh_func: Callable[..., Dict[str, Any]] = refresh_record_predictions,
    ):
        self.session_factory = session_factory
        self.daily_sync_factory = daily_sync_factory
        self.minute_sync_factory = minute_sync_factory
        self.auction_service_factory = auction_service_factory
        self.validate_replay_func = validate_replay_func
        self.build_real_sample_func = build_real_sample_func
        self.build_replay_sample_func = build_replay_sample_func
        self.audit_func = audit_func
        self.create_job_func = create_job_func
        self.run_training_func = run_training_func
        self.diagnostics_func = diagnostics_func
        self.backtest_func = backtest_func
        self.activate_func = activate_func
        self.refresh_func = refresh_func

    def run_auto_learning(self, run_id: int) -> None:
        db = self.session_factory()
        try:
            run = self._get_run(db, run_id)
            if run.status == "cancelled":
                return
            options = _load_json(run.options_json, {})
            request = DefaultAuctionAutoLearningCreate(**options)
            request.validate()
            self._mark_running(db, run)

            stage_results: Dict[str, Any] = _load_json(run.stage_results_json, {})
            self._check_cancelled(db, run)

            if request.sync_daily:
                self._set_phase(db, run, "sync_daily", "同步本地日线")
                stage_results["daily_sync"] = self.daily_sync_factory(request.tdx_vipdoc_path).sync_range(
                    request.start_date,
                    request.end_date,
                    ts_codes=request.ts_codes,
                    commit_every=request.commit_every,
                )
                self._save_stage_results(db, run, stage_results)
                self._check_cancelled(db, run)

            if request.sync_minute:
                self._set_phase(db, run, "sync_minute", "同步本地分钟线")
                stage_results["minute_sync"] = self.minute_sync_factory(request.tdx_vipdoc_path).sync_range(
                    request.start_date,
                    request.end_date,
                    ts_codes=self._resolve_minute_ts_codes(db, request),
                    interval=request.minute_interval,
                    commit_every=request.commit_every,
                )
                self._save_stage_results(db, run, stage_results)
                self._check_cancelled(db, run)

            if request.recalculate_auction_ratios:
                self._set_phase(db, run, "recalculate_auction_ratios", "重算竞昨比")
                stage_results["auction_ratio_recalc"] = self.auction_service_factory().recalculate_auction_ratios_from_daily_cache(
                    request.start_date,
                    request.end_date,
                )
                self._save_stage_results(db, run, stage_results)

            if request.validate_replay or request.build_replay_samples:
                self._set_phase(db, run, "validate_replay", "执行回放验收")
                validation = self._validate_replay(db, request)
                stage_results["replay_validation"] = validation
                self._save_stage_results(db, run, stage_results)
                if not validation.get("accepted"):
                    raise ValueError(f"回放验收未通过: {validation.get('reject_reasons', [])}")

            if request.build_real_samples:
                self._set_phase(db, run, "build_real_samples", "构建真实选股样本")
                real_result: Dict[str, Any] = {
                    "created_count": 0,
                    "updated_count": 0,
                    "skipped_count": 0,
                    "deleted_count": 0,
                    "records": {},
                }
                for record_id in self._resolve_selected_record_ids(db, request):
                    item = self.build_real_sample_func(db, record_id, "real_selected")
                    real_result["records"][str(record_id)] = item
                    for key in ("created_count", "updated_count", "skipped_count", "deleted_count"):
                        real_result[key] += int(item.get(key) or 0)
                stage_results.setdefault("sample_build", {})["real"] = real_result
                self._save_stage_results(db, run, stage_results)

            if request.build_replay_samples:
                self._set_phase(db, run, "build_replay_samples", "构建回放样本")
                stage_results.setdefault("sample_build", {})["replay"] = self.build_replay_sample_func(
                    db,
                    request.start_date,
                    request.end_date,
                    "replay_backtest",
                )
                self._save_stage_results(db, run, stage_results)

            if request.audit_training_data:
                self._set_phase(db, run, "audit_training_data", "执行训练数据完整性审计")
                audit = self.audit_func(db)
                run.audit_json = _dump_json(audit)
                stage_results["training_data_audit"] = audit
                self._save_stage_results(db, run, stage_results)
                if not audit.get("ok"):
                    raise ValueError(f"训练数据完整性审计未通过: {audit.get('errors', [])}")

            target_versions: Dict[str, str] = {}
            if request.run_training:
                self._set_phase(db, run, "training", "启动三目标训练")
                job = self.create_job_func(
                    db,
                    request.start_date,
                    request.end_date,
                    request.params,
                    False,
                )
                if job.id is None:
                    db.add(job)
                    db.commit()
                    db.refresh(job)
                run.training_job_id = job.id
                db.commit()
                self.run_training_func(job.id)
                diagnostics = self.diagnostics_func(db, job.id)
                run.training_diagnostics_json = _dump_json(diagnostics)
                target_versions = self._extract_target_versions(diagnostics)
                if diagnostics.get("status") != "passed" or len(target_versions) != len(TARGET_VERSION_FIELDS):
                    raise ValueError("三目标训练未全部通过")
                db.commit()

            if request.run_backtest:
                self._set_phase(db, run, "backtest", "执行离线回测")
                backtest = self.backtest_func(
                    db,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    target_versions=target_versions or None,
                )
                run.backtest_json = _dump_json(backtest)
                stage_results["backtest"] = backtest
                self._save_stage_results(db, run, stage_results)
                self._assert_backtest_accepted(backtest, request.acceptance)

            if request.auto_activate:
                self._set_phase(db, run, "activate", "启用三目标模型")
                previous_versions = self._active_versions(db)
                stage_results["previous_active_versions"] = previous_versions
                activated = {}
                for model_name, version in target_versions.items():
                    self.activate_func(db, model_name, version)
                    activated[model_name] = version
                run.activated_versions_json = _dump_json(activated)
                self._save_stage_results(db, run, stage_results)

            if request.refresh_predictions:
                self._set_phase(db, run, "refresh_predictions", "刷新最新选股预测")
                refreshed_ids = self._resolve_refresh_record_ids(db, request)
                refresh_results = {}
                for record_id in refreshed_ids:
                    refresh_results[str(record_id)] = self.refresh_func(db, "default_auction_relay_v2", record_id, None)
                run.refreshed_record_ids_json = _dump_json(refreshed_ids)
                stage_results["refresh_predictions"] = refresh_results
                self._save_stage_results(db, run, stage_results)

            run.status = "passed"
            run.phase = "finish"
            run.progress = 100
            run.finished_at = datetime.now()
            _append_log(run, "自动学习运行完成")
            db.commit()
        except Exception as exc:
            db.rollback()
            failed = db.query(DefaultAuctionAutoLearningRun).filter(DefaultAuctionAutoLearningRun.id == run_id).first()
            if failed is not None and failed.status != "cancelled":
                failed.status = "failed"
                failed.error_message = str(exc)
                failed.finished_at = datetime.now()
                _append_log(failed, str(exc), level="error")
                db.commit()
        finally:
            if self.session_factory is SessionLocal:
                db.close()

    @staticmethod
    def _get_run(db: Session, run_id: int) -> DefaultAuctionAutoLearningRun:
        run = db.query(DefaultAuctionAutoLearningRun).filter(DefaultAuctionAutoLearningRun.id == run_id).first()
        if run is None:
            raise ValueError(f"自动学习运行不存在: {run_id}")
        return run

    @staticmethod
    def _mark_running(db: Session, run: DefaultAuctionAutoLearningRun) -> None:
        run.status = "running"
        run.phase = "prepare"
        run.progress = PHASE_PROGRESS["prepare"]
        run.started_at = datetime.now()
        run.error_message = None
        _append_log(run, "自动学习运行开始")
        db.commit()

    @staticmethod
    def _set_phase(db: Session, run: DefaultAuctionAutoLearningRun, phase: str, message: str) -> None:
        run.phase = phase
        run.progress = PHASE_PROGRESS[phase]
        _append_log(run, message)
        db.commit()

    @staticmethod
    def _save_stage_results(db: Session, run: DefaultAuctionAutoLearningRun, stage_results: Dict[str, Any]) -> None:
        run.stage_results_json = _dump_json(stage_results)
        db.commit()

    def _validate_replay(self, db: Session, request: DefaultAuctionAutoLearningCreate) -> Dict[str, Any]:
        if self.validate_replay_func is not None:
            return self.validate_replay_func(db, request.validation_recent_days, end_date=request.end_date)
        from backend.api.model_management import validate_default_auction_replay

        return validate_default_auction_replay(db, request.validation_recent_days, end_date=request.end_date)

    @staticmethod
    def _resolve_selected_record_ids(db: Session, request: DefaultAuctionAutoLearningCreate) -> List[int]:
        if request.selected_record_ids:
            return request.selected_record_ids
        rows = (
            db.query(SelectionRecord.id)
            .filter(SelectionRecord.trade_date >= request.start_date, SelectionRecord.trade_date <= request.end_date)
            .order_by(SelectionRecord.id.desc())
            .limit(request.recent_record_limit)
            .all()
        )
        return [row[0] for row in rows]

    @staticmethod
    def _resolve_refresh_record_ids(db: Session, request: DefaultAuctionAutoLearningCreate) -> List[int]:
        if request.refresh_record_ids:
            return request.refresh_record_ids
        return DefaultAuctionAutoLearningService._resolve_selected_record_ids(db, request)

    @staticmethod
    def _resolve_minute_ts_codes(db: Session, request: DefaultAuctionAutoLearningCreate) -> Optional[List[str]]:
        if request.ts_codes is not None:
            return sorted({code for code in request.ts_codes if code})
        if request.selected_record_ids:
            rows = (
                db.query(SelectedStock.ts_code)
                .filter(SelectedStock.record_id.in_(request.selected_record_ids))
                .distinct()
                .all()
            )
            codes = sorted({row[0] for row in rows if row[0]})
            if codes:
                return codes
        rows = (
            db.query(DefaultAuctionTrainingSample.ts_code)
            .filter(
                DefaultAuctionTrainingSample.trade_date >= request.start_date,
                DefaultAuctionTrainingSample.trade_date <= request.end_date,
            )
            .distinct()
            .all()
        )
        codes = sorted({row[0] for row in rows if row[0]})
        return codes if codes else None

    @staticmethod
    def _extract_target_versions(diagnostics: Dict[str, Any]) -> Dict[str, str]:
        targets = ((diagnostics.get("acceptance") or {}).get("targets") or {})
        versions: Dict[str, str] = {}
        for model_name in TARGET_VERSION_FIELDS:
            payload = targets.get(model_name) or {}
            if payload.get("accepted") and payload.get("version"):
                versions[model_name] = payload["version"]
        return versions

    @staticmethod
    def _assert_backtest_accepted(backtest: Dict[str, Any], acceptance: Dict[str, Any]) -> None:
        thresholds = {
            "default_auction_t0_limit_lgbm": float(acceptance.get("min_t0_auc", 0.6)),
            "default_auction_t1_premium_lgbm": float(acceptance.get("min_t1_premium_auc", 0.55)),
            "default_auction_t1_continue_lgbm": float(acceptance.get("min_t1_continue_auc", 0.58)),
        }
        max_failed = int(acceptance.get("max_prediction_failed_count", 0))
        targets = backtest.get("targets") or {}
        for model_name, min_auc in thresholds.items():
            payload = targets.get(model_name)
            if not payload:
                raise ValueError(f"回测缺少目标: {model_name}")
            if int(payload.get("prediction_failed_count") or 0) > max_failed:
                raise ValueError(f"回测预测失败数量超限: {model_name}")
            auc = (payload.get("metrics") or {}).get("auc")
            if auc is not None and float(auc) < min_auc:
                raise ValueError(f"回测 AUC 未达标: {model_name}")

    @staticmethod
    def _active_versions(db: Session) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {}
        for model_name in TARGET_VERSION_FIELDS:
            row = (
                db.query(ModelVersion)
                .filter(ModelVersion.model_name == model_name, ModelVersion.is_active == 1)
                .order_by(ModelVersion.id.desc())
                .first()
            )
            result[model_name] = row.version if row else None
        return result

    @staticmethod
    def _check_cancelled(db: Session, run: DefaultAuctionAutoLearningRun) -> None:
        db.refresh(run)
        options = _load_json(run.options_json, {})
        if options.get("cancel_requested"):
            run.status = "cancelled"
            run.phase = "finish"
            run.progress = 100
            run.finished_at = datetime.now()
            _append_log(run, "自动学习运行已在阶段边界取消")
            db.commit()
            raise ValueError("自动学习运行已取消")


def _run_payload(run: DefaultAuctionAutoLearningRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "phase": run.phase,
        "progress": run.progress,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "tdx_vipdoc_path": run.tdx_vipdoc_path,
        "ts_codes": _load_json(run.ts_codes_json, None),
        "selected_record_ids": _load_json(run.selected_record_ids_json, None),
        "options": _load_json(run.options_json, {}),
        "stage_results": _load_json(run.stage_results_json, {}),
        "audit": _load_json(run.audit_json, None),
        "training_job_id": run.training_job_id,
        "training_diagnostics": _load_json(run.training_diagnostics_json, None),
        "backtest": _load_json(run.backtest_json, None),
        "activated_versions": _load_json(run.activated_versions_json, None),
        "refreshed_record_ids": _load_json(run.refreshed_record_ids_json, None),
        "logs": _load_json(run.logs_json, []),
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }
