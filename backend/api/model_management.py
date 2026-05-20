"""
模型中心 API。
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import DefaultAuctionTrainingSample
from backend.schemas.common import ApiResponse
from backend.services.model_engine.model_management_service import (
    activate_model_version,
    list_models,
    refresh_record_predictions,
)
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.model_engine.default_auction_sample_builder import (
    build_samples_from_replay_range,
    build_samples_from_selected_record,
)
from backend.services.model_engine.default_auction_relay_job_service import (
    create_default_auction_relay_job,
    get_default_auction_relay_diagnostics,
    run_default_auction_relay_training_job,
)
from backend.services.model_engine.default_auction_auto_learning_service import (
    DefaultAuctionAutoLearningCreate,
    create_or_reuse_auto_learning_run,
    get_auto_learning_run,
    list_auto_learning_runs,
    request_cancel_auto_learning_run,
    run_auto_learning,
)
from backend.services.model_engine.default_auction_raw_data_sync_service import (
    get_default_auction_raw_data_sync_state,
)
from backend.services.model_engine.replay_validation_service import validate_replay_against_real
from backend.services.model_engine.default_auction_backtest_service import run_default_auction_relay_backtest
from backend.services.auction_data_service import AuctionDataService
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService
from backend.services.tdx_local_minute_sync_service import TdxLocalMinuteSyncService

router = APIRouter()

try:
    from pydantic import field_validator, model_validator

    PYDANTIC_V2 = True
except ImportError:
    from pydantic import root_validator, validator

    PYDANTIC_V2 = False


class RefreshPredictionsRequest(BaseModel):
    record_id: int = Field(ge=1)
    version: Optional[str] = None


class ReplayValidateRequest(BaseModel):
    recent_days: int = Field(default=5, ge=1, le=30)


class DefaultAuctionBuildSamplesRequest(BaseModel):
    record_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sample_source: str = "real_selected"


class LocalDailySyncRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    ts_codes: Optional[List[str]] = None
    tdx_vipdoc_path: Optional[str] = None
    commit_every: int = Field(default=5000, ge=1)


class LocalMinuteSyncRequest(LocalDailySyncRequest):
    interval: int = Field(default=1, ge=1)


class DefaultAuctionPipelineRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    ts_codes: Optional[List[str]] = None
    tdx_vipdoc_path: Optional[str] = None
    commit_every: int = Field(default=5000, ge=1)
    minute_interval: int = Field(default=1, ge=1)
    sync_daily: bool = True
    sync_minute: bool = True
    recalculate_auction_ratios: bool = True
    validate_replay: bool = True
    validation_recent_days: int = Field(default=5, ge=1, le=30)
    build_samples: bool = True
    run_backtest: bool = False
    sample_source: str = "replay_backtest"
    run_training: bool = False
    auto_activate: bool = False
    params: Dict[str, Any] = Field(default_factory=dict)


class DefaultAuctionBacktestRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    version: Optional[str] = None


class AuctionRatioRecalculateRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)


class DefaultAuctionAutoLearningRunRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
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
    validation_recent_days: int = Field(default=5, ge=1, le=30)
    recent_record_limit: int = Field(default=5, ge=1, le=50)
    minute_interval: int = Field(default=1, ge=1)
    commit_every: int = Field(default=5000, ge=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    acceptance: Dict[str, Any] = Field(default_factory=dict)


class DefaultAuctionRelayTrainRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    auto_activate: bool = False
    params: Dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def _validate_yyyymmdd(value: str) -> str:
        if not value.isdigit() or len(value) != 8:
            raise ValueError("日期必须是8位数字YYYYMMDD")
        return value

    @staticmethod
    def _validate_date_range_values(start_date: Optional[str], end_date: Optional[str]) -> None:
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date不能晚于end_date")

    if PYDANTIC_V2:

        @field_validator("start_date", "end_date")
        @classmethod
        def validate_yyyymmdd(cls, value: str) -> str:
            return cls._validate_yyyymmdd(value)

        @model_validator(mode="after")
        def validate_date_range(self):
            self._validate_date_range_values(self.start_date, self.end_date)
            return self

    else:

        @validator("start_date", "end_date")
        def validate_yyyymmdd(cls, value: str) -> str:
            return cls._validate_yyyymmdd(value)

        @root_validator(skip_on_failure=True)
        def validate_date_range(cls, values: Dict[str, Any]) -> Dict[str, Any]:
            cls._validate_date_range_values(values.get("start_date"), values.get("end_date"))
            return values


def validate_default_auction_replay(
    db: Session,
    recent_days: int,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    replay_service = DefaultAuctionReplayService(db)
    days = []
    for item in replay_service.get_recent_real_selection_days(limit=recent_days, end_date=end_date):
        replay_result = replay_service.replay_trade_date(item["trade_date"])
        days.append(
            {
                "trade_date": item["trade_date"],
                "real_codes": item.get("real_codes", []),
                "replay_codes": replay_result.get("replay_codes", []),
                "record_id": item.get("record_id"),
                "diagnostics": replay_result.get("diagnostics", []),
            }
        )
    result = validate_replay_against_real(days)
    result["recent_days"] = recent_days
    result["end_date"] = end_date
    return result


def _resolve_pipeline_minute_ts_codes(db: Session, request: DefaultAuctionPipelineRequest) -> List[str]:
    if request.ts_codes is not None:
        return sorted({code for code in request.ts_codes if code})
    rows = (
        db.query(DefaultAuctionTrainingSample.ts_code)
        .filter(
            DefaultAuctionTrainingSample.strategy_version == "default_auction_v2",
            DefaultAuctionTrainingSample.trade_date >= request.start_date,
            DefaultAuctionTrainingSample.trade_date <= request.end_date,
            DefaultAuctionTrainingSample.ts_code.isnot(None),
        )
        .distinct()
        .order_by(DefaultAuctionTrainingSample.ts_code.asc())
        .all()
    )
    return [row[0] for row in rows if row[0]]


@router.get("/models", tags=["模型"])
async def get_models(db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=list_models(db))


@router.get("/models/default-auction-relay/raw-data-sync-state", tags=["模型"])
async def get_default_auction_raw_data_sync_state_endpoint(db: Session = Depends(get_db)):
    return ApiResponse(
        code=200,
        message="success",
        data=get_default_auction_raw_data_sync_state(db),
    )


@router.post("/models/default-auction-replay/validate", tags=["模型"])
async def validate_default_auction_replay_endpoint(
    request: ReplayValidateRequest,
    db: Session = Depends(get_db),
):
    return ApiResponse(
        code=200,
        message="success",
        data=validate_default_auction_replay(db, request.recent_days),
    )


@router.post("/models/default-auction-samples/build", tags=["模型"])
@router.post("/models/default-auction-replay/build-samples", tags=["模型"])
async def build_default_auction_samples_endpoint(
    request: DefaultAuctionBuildSamplesRequest,
    db: Session = Depends(get_db),
):
    if request.record_id is None:
        if not request.start_date or not request.end_date:
            raise HTTPException(status_code=422, detail="record_id 或 start_date/end_date 必须提供")
        try:
            validation = validate_default_auction_replay(db, recent_days=5, end_date=request.end_date)
            if not validation.get("accepted"):
                raise HTTPException(
                    status_code=422,
                    detail=f"回放验收未通过: {validation.get('reject_reasons', [])}",
                )
            result = build_samples_from_replay_range(
                db,
                request.start_date,
                request.end_date,
                request.sample_source,
            )
            return ApiResponse(code=200, message="样本构建完成", data=result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    try:
        result = build_samples_from_selected_record(db, request.record_id, request.sample_source)
        return ApiResponse(code=200, message="样本构建完成", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/models/default-auction-relay/train", tags=["模型"])
async def train_default_auction_relay_endpoint(
    request: DefaultAuctionRelayTrainRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        job = create_default_auction_relay_job(
            db,
            start_date=request.start_date,
            end_date=request.end_date,
            params=request.params,
            auto_activate=request.auto_activate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    background_tasks.add_task(run_default_auction_relay_training_job, job.id)
    return ApiResponse(code=200, message="训练任务已创建", data={"job_id": job.id})


@router.get("/models/default-auction-relay/diagnostics/{job_id}", tags=["模型"])
async def default_auction_relay_diagnostics_endpoint(job_id: int, db: Session = Depends(get_db)):
    try:
        return ApiResponse(code=200, message="success", data=get_default_auction_relay_diagnostics(db, job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/models/default-auction-relay/refresh-predictions", tags=["模型"])
async def refresh_default_auction_relay_predictions(
    request: RefreshPredictionsRequest,
    db: Session = Depends(get_db),
):
    try:
        result = refresh_record_predictions(db, "default_auction_relay_v2", request.record_id, request.version)
        return ApiResponse(code=200, message="预测刷新完成", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/models/default-auction-relay/sync-local-daily", tags=["模型"])
async def sync_default_auction_local_daily(request: LocalDailySyncRequest):
    service = TdxLocalDailySyncService(tdx_vipdoc_path=request.tdx_vipdoc_path)
    result = service.sync_range(
        request.start_date,
        request.end_date,
        ts_codes=request.ts_codes,
        commit_every=request.commit_every,
    )
    return ApiResponse(code=200, message="本地日线同步完成", data=result)


@router.post("/models/default-auction-relay/sync-local-minute", tags=["模型"])
async def sync_default_auction_local_minute(request: LocalMinuteSyncRequest):
    service = TdxLocalMinuteSyncService(tdx_vipdoc_path=request.tdx_vipdoc_path)
    result = service.sync_range(
        request.start_date,
        request.end_date,
        ts_codes=request.ts_codes,
        interval=request.interval,
        commit_every=request.commit_every,
    )
    return ApiResponse(code=200, message="本地分钟线同步完成", data=result)


@router.post("/models/default-auction-relay/recalculate-auction-ratios", tags=["模型"])
async def recalculate_default_auction_ratios(request: AuctionRatioRecalculateRequest):
    result = AuctionDataService().recalculate_auction_ratios_from_daily_cache(
        request.start_date,
        request.end_date,
    )
    return ApiResponse(code=200, message="竞昨比重算完成", data=result)


@router.post("/models/default-auction-relay/auto-learning/runs", tags=["模型"])
async def create_default_auction_auto_learning_run_endpoint(
    request: DefaultAuctionAutoLearningRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        request_payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        payload = DefaultAuctionAutoLearningCreate(**request_payload)
        run, created = create_or_reuse_auto_learning_run(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if created:
        background_tasks.add_task(run_auto_learning, run.id)
    message = "自动学习运行已创建" if created else "已有自动学习运行，已复用"
    return ApiResponse(code=200, message=message, data={"run_id": run.id, "status": run.status, "reused": not created})


@router.get("/models/default-auction-relay/auto-learning/runs", tags=["模型"])
async def list_default_auction_auto_learning_runs_endpoint(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return ApiResponse(code=200, message="success", data=list_auto_learning_runs(db, limit=limit))


@router.get("/models/default-auction-relay/auto-learning/runs/{run_id}", tags=["模型"])
async def get_default_auction_auto_learning_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    try:
        return ApiResponse(code=200, message="success", data=get_auto_learning_run(db, run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/models/default-auction-relay/auto-learning/runs/{run_id}/cancel", tags=["模型"])
async def cancel_default_auction_auto_learning_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    try:
        return ApiResponse(code=200, message="自动学习运行已取消", data=request_cancel_auto_learning_run(db, run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/models/default-auction-relay/rebuild-pipeline", tags=["模型"])
async def rebuild_default_auction_relay_pipeline(
    request: DefaultAuctionPipelineRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    payload: Dict[str, Any] = {
        "daily_sync": None,
        "minute_sync": None,
        "auction_ratio_recalc": None,
        "replay_validation": None,
        "sample_build": None,
        "backtest": None,
        "training_job": None,
    }
    if request.sync_daily:
        payload["daily_sync"] = TdxLocalDailySyncService(
            tdx_vipdoc_path=request.tdx_vipdoc_path
        ).sync_range(
            request.start_date,
            request.end_date,
            ts_codes=request.ts_codes,
            commit_every=request.commit_every,
        )
    if request.sync_minute:
        minute_ts_codes = _resolve_pipeline_minute_ts_codes(db, request)
        payload["minute_sync"] = TdxLocalMinuteSyncService(
            tdx_vipdoc_path=request.tdx_vipdoc_path
        ).sync_range(
            request.start_date,
            request.end_date,
            ts_codes=minute_ts_codes,
            interval=request.minute_interval,
            commit_every=request.commit_every,
        )
    if request.recalculate_auction_ratios:
        payload["auction_ratio_recalc"] = AuctionDataService().recalculate_auction_ratios_from_daily_cache(
            request.start_date,
            request.end_date,
        )
    if request.validate_replay or request.build_samples:
        validation = validate_default_auction_replay(
            db,
            recent_days=request.validation_recent_days,
            end_date=request.end_date,
        )
        payload["replay_validation"] = validation
        if not validation.get("accepted"):
            raise HTTPException(
                status_code=422,
                detail=f"回放验收未通过: {validation.get('reject_reasons', [])}",
            )
    if request.build_samples:
        payload["sample_build"] = build_samples_from_replay_range(
            db,
            request.start_date,
            request.end_date,
            request.sample_source,
        )
    if request.run_backtest:
        try:
            payload["backtest"] = run_default_auction_relay_backtest(
                db,
                start_date=request.start_date,
                end_date=request.end_date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if request.run_training:
        job = create_default_auction_relay_job(
            db,
            start_date=request.start_date,
            end_date=request.end_date,
            params=request.params,
            auto_activate=request.auto_activate,
        )
        background_tasks.add_task(run_default_auction_relay_training_job, job.id)
        payload["training_job"] = {"job_id": job.id}
    return ApiResponse(code=200, message="默认竞价接力管道已触发", data=payload)


@router.post("/models/default-auction-relay/backtest", tags=["模型"])
async def backtest_default_auction_relay_endpoint(
    request: DefaultAuctionBacktestRequest,
    db: Session = Depends(get_db),
):
    try:
        result = run_default_auction_relay_backtest(
            db,
            start_date=request.start_date,
            end_date=request.end_date,
            version=request.version,
        )
        return ApiResponse(code=200, message="回测完成", data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/models/{model_name}/versions/{version}/activate", tags=["模型"])
async def activate_version(model_name: str, version: str, db: Session = Depends(get_db)):
    try:
        result = activate_model_version(db, model_name, version)
        return ApiResponse(code=200, message=result["message"], data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/models/{model_name}/refresh-predictions", tags=["模型"])
async def refresh_predictions(
    model_name: str,
    request: RefreshPredictionsRequest,
    db: Session = Depends(get_db),
):
    try:
        result = refresh_record_predictions(db, model_name, request.record_id, request.version)
        return ApiResponse(code=200, message="预测刷新完成", data=result)
    except KeyError:
        raise HTTPException(status_code=400, detail="不支持的模型")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
