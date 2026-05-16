"""
模型训练任务服务。
"""
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List

from backend.database import SessionLocal
from backend.models import ModelTrainingJob
from backend.services.model_engine import lightgbm_service
from backend.services.model_engine.model_management_service import activate_model_version
from backend.services.websocket_service import manager


@dataclass
class TrainingParams:
    test_size: float = 0.10
    learning_rate: float = 0.05
    n_estimators: int = 500
    num_leaves: int = 31
    is_unbalance: bool = True
    max_depth: int = -1
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    early_stopping_rounds: int = 50
    random_seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceCriteria:
    min_precision: float = 0.50
    min_hit_count: int = 30
    threshold: float = 0.50
    max_retrain_attempts: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_training_params(params: TrainingParams) -> None:
    if not 0 < params.test_size < 0.5:
        raise ValueError("test_size 必须在 0 和 0.5 之间")
    if not 0 < params.learning_rate <= 1:
        raise ValueError("learning_rate 必须在 0 和 1 之间")
    if not 10 <= params.n_estimators <= 5000:
        raise ValueError("n_estimators 必须在 10 和 5000 之间")
    if not 2 <= params.num_leaves <= 512:
        raise ValueError("num_leaves 必须在 2 和 512 之间")
    if params.max_depth != -1 and not 1 <= params.max_depth <= 64:
        raise ValueError("max_depth 必须为 -1 或 1 到 64")
    if not 0 < params.subsample <= 1:
        raise ValueError("subsample 必须在 0 和 1 之间")
    if not 0 < params.colsample_bytree <= 1:
        raise ValueError("colsample_bytree 必须在 0 和 1 之间")
    if not 1 <= params.early_stopping_rounds <= 500:
        raise ValueError("early_stopping_rounds 必须在 1 和 500 之间")


def validate_acceptance(criteria: AcceptanceCriteria) -> None:
    if not 0 < criteria.min_precision <= 1:
        raise ValueError("min_precision 必须在 0 和 1 之间")
    if criteria.min_hit_count < 1:
        raise ValueError("min_hit_count 必须大于 0")
    if not 0 < criteria.threshold < 1:
        raise ValueError("threshold 必须在 0 和 1 之间")
    if not 1 <= criteria.max_retrain_attempts <= 10:
        raise ValueError("max_retrain_attempts 必须在 1 和 10 之间")


def choose_acceptance_threshold(
    threshold_evaluation: List[Dict[str, Any]],
    criteria: AcceptanceCriteria,
) -> Dict[str, Any]:
    candidates = [
        item
        for item in threshold_evaluation
        if float(item.get("precision") or 0) >= criteria.min_precision
        and int(item.get("hit_count") or 0) >= criteria.min_hit_count
    ]
    if not candidates:
        return {
            "accepted": False,
            "reason": "未找到同时满足胜率和命中数的阈值",
            "min_precision": criteria.min_precision,
            "min_hit_count": criteria.min_hit_count,
        }

    candidates.sort(
        key=lambda item: (
            abs(float(item.get("threshold") or 0) - criteria.threshold),
            -int(item.get("hit_count") or 0),
        )
    )
    best = dict(candidates[0])
    best["accepted"] = True
    best["min_precision"] = criteria.min_precision
    best["min_hit_count"] = criteria.min_hit_count
    return best


def _load_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _append_log(job: ModelTrainingJob, message: str) -> None:
    logs = _load_json(job.logs_json, [])
    logs.append({"time": datetime.now().isoformat(timespec="seconds"), "message": message})
    job.logs_json = _dump_json(logs)


def _broadcast_job_update(payload: Dict[str, Any]) -> None:
    message = {"type": "model_training_job", "job": payload}
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast_to_channel(message, "models"))
    except RuntimeError:
        try:
            asyncio.run(manager.broadcast_to_channel(message, "models"))
        except Exception:
            return


def create_training_job(
    db,
    model_name: str,
    start_date: str,
    end_date: str,
    params: TrainingParams,
    acceptance: AcceptanceCriteria,
    mode: str = "test",
    auto_activate: bool = False,
) -> ModelTrainingJob:
    if mode not in {"test", "formal"}:
        raise ValueError("mode 必须为 test 或 formal")
    validate_training_params(params)
    validate_acceptance(acceptance)
    job = ModelTrainingJob(
        model_name=model_name,
        status="pending",
        phase="prepare",
        progress=0,
        mode=mode,
        auto_activate=1 if auto_activate else 0,
        train_start_date=start_date,
        train_end_date=end_date,
        params_json=_dump_json(params.to_dict()),
        acceptance_json=_dump_json(acceptance.to_dict()),
        attempts_json="[]",
        logs_json="[]",
    )
    _append_log(job, "训练任务已创建")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_training_job(db, job_id: int) -> Dict[str, Any]:
    job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
    if job is None:
        raise ValueError("训练任务不存在")
    return {
        "id": job.id,
        "model_name": job.model_name,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "mode": job.mode,
        "auto_activate": bool(job.auto_activate),
        "train_start_date": job.train_start_date,
        "train_end_date": job.train_end_date,
        "params": _load_json(job.params_json, {}),
        "acceptance": _load_json(job.acceptance_json, {}),
        "attempts": _load_json(job.attempts_json, []),
        "logs": _load_json(job.logs_json, []),
        "best_model_version": job.best_model_version,
        "best_model_path": job.best_model_path,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _save_and_broadcast(db, job: ModelTrainingJob) -> None:
    db.commit()
    db.refresh(job)
    _broadcast_job_update(get_training_job(db, job.id))


def run_training_job_sync(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
        if job is None:
            return

        params = TrainingParams(**_load_json(job.params_json, {}))
        acceptance = AcceptanceCriteria(**_load_json(job.acceptance_json, {}))
        attempts: List[Dict[str, Any]] = []
        job.status = "running"
        job.phase = "train"
        job.progress = 5
        job.started_at = datetime.now()
        _append_log(job, "开始训练")
        _save_and_broadcast(db, job)

        for attempt_no in range(1, acceptance.max_retrain_attempts + 1):
            job.phase = "train"
            job.progress = min(90, 10 + int((attempt_no - 1) / acceptance.max_retrain_attempts * 70))
            _append_log(job, f"开始第 {attempt_no} 次训练")
            _save_and_broadcast(db, job)

            result = lightgbm_service.train_leader_main_t0_lgbm_configurable(
                job.train_start_date,
                job.train_end_date,
                params=params.to_dict(),
                activate=False,
            )
            if not result:
                accepted = {
                    "accepted": False,
                    "reason": "训练未生成模型",
                    "min_precision": acceptance.min_precision,
                    "min_hit_count": acceptance.min_hit_count,
                }
                attempt_payload = {"attempt": attempt_no, **accepted}
                attempts.append(attempt_payload)
                job.attempts_json = _dump_json(attempts)
                _append_log(job, f"第 {attempt_no} 次训练未生成模型")
                _save_and_broadcast(db, job)
                continue

            threshold_evaluation = result.get("metrics", {}).get("threshold_evaluation") or []
            accepted = choose_acceptance_threshold(threshold_evaluation, acceptance)
            attempt_payload = {
                "attempt": attempt_no,
                "version": result.get("version"),
                "model_path": result.get("model_path"),
                "metrics": result.get("metrics", {}),
                **accepted,
            }
            attempts.append(attempt_payload)
            job.attempts_json = _dump_json(attempts)

            if accepted["accepted"]:
                job.status = "passed"
                job.phase = "accepted"
                job.progress = 100
                job.best_model_version = result.get("version")
                job.best_model_path = result.get("model_path")
                job.finished_at = datetime.now()
                _append_log(job, f"第 {attempt_no} 次训练通过验收")
                _save_and_broadcast(db, job)
                if job.auto_activate:
                    activate_model_version(db, job.model_name, result.get("version"))
                    _append_log(job, f"已激活模型版本 {result.get('version')}")
                    _save_and_broadcast(db, job)
                return

            _append_log(job, f"第 {attempt_no} 次训练未通过验收: {accepted.get('reason')}")
            job.progress = min(95, 20 + int(attempt_no / acceptance.max_retrain_attempts * 70))
            _save_and_broadcast(db, job)

        job.status = "rejected"
        job.phase = "rejected"
        job.progress = 100
        job.finished_at = datetime.now()
        _append_log(job, "达到最大重训次数，仍未通过验收")
        _save_and_broadcast(db, job)
    except Exception as exc:
        db.rollback()
        job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
        if job is not None:
            job.status = "failed"
            job.phase = "failed"
            job.progress = 100
            job.error_message = str(exc)
            job.finished_at = datetime.now()
            _append_log(job, f"训练失败: {exc}")
            _save_and_broadcast(db, job)
    finally:
        db.close()
