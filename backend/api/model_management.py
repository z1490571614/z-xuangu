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
from backend.services.model_engine.training_job_service import (
    AcceptanceCriteria,
    TrainingParams,
    create_training_job,
    get_training_job,
    run_training_job_sync,
)

router = APIRouter()


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


@router.get("/models", tags=["模型"])
async def get_models(db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=list_models(db))


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
