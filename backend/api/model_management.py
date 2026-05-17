"""
模型中心 API。
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.common import ApiResponse
from backend.services.model_engine.model_management_service import (
    activate_model_version,
    list_models,
    refresh_record_predictions,
)
from backend.services.model_engine.default_auction_replay_service import DefaultAuctionReplayService
from backend.services.model_engine.default_auction_sample_builder import build_samples_from_selected_record
from backend.services.model_engine.default_auction_relay_job_service import (
    create_default_auction_relay_job,
    get_default_auction_relay_diagnostics,
    run_default_auction_relay_training_job,
)
from backend.services.model_engine.replay_validation_service import validate_replay_against_real
from backend.services.model_engine.training_job_service import (
    AcceptanceCriteria,
    TrainingParams,
    create_training_job,
    get_training_job,
    run_training_job_sync,
)

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


class TrainingJobRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    mode: str = "test"
    auto_activate: bool = False
    params: Dict[str, Any] = Field(default_factory=dict)
    acceptance: Dict[str, Any] = Field(default_factory=dict)


class ReplayValidateRequest(BaseModel):
    recent_days: int = Field(default=5, ge=1, le=30)


class DefaultAuctionBuildSamplesRequest(BaseModel):
    record_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sample_source: str = "real_selected"


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


def validate_default_auction_replay(db: Session, recent_days: int) -> Dict[str, Any]:
    replay_service = DefaultAuctionReplayService(db)
    days = []
    for item in replay_service.get_recent_real_selection_days(limit=recent_days):
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
    return result


@router.get("/models", tags=["模型"])
async def get_models(db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=list_models(db))


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
async def build_default_auction_samples_endpoint(
    request: DefaultAuctionBuildSamplesRequest,
    db: Session = Depends(get_db),
):
    if request.record_id is None:
        raise HTTPException(status_code=422, detail="record_id 不能为空")
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


@router.post("/models/{model_name}/versions/{version}/activate", tags=["模型"])
async def activate_version(model_name: str, version: str, db: Session = Depends(get_db)):
    try:
        result = activate_model_version(db, model_name, version)
        return ApiResponse(code=200, message=result["message"], data=result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/models/{model_name}/training-jobs", tags=["模型"])
async def create_model_training_job(
    model_name: str,
    request: TrainingJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        job = create_training_job(
            db,
            model_name=model_name,
            start_date=request.start_date,
            end_date=request.end_date,
            params=TrainingParams(**request.params),
            acceptance=AcceptanceCriteria(**request.acceptance),
            mode=request.mode,
            auto_activate=request.auto_activate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    background_tasks.add_task(run_training_job_sync, job.id)
    return ApiResponse(code=200, message="训练任务已创建", data={"job_id": job.id})


@router.get("/models/training-jobs/{job_id}", tags=["模型"])
async def get_model_training_job(job_id: int, db: Session = Depends(get_db)):
    try:
        return ApiResponse(code=200, message="success", data=get_training_job(db, job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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
