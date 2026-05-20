"""
默认竞价接力 V2 模型中心训练任务编排。
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from backend.database import SessionLocal
from backend.models import DefaultAuctionTrainingSample, ModelTrainingJob, ModelVersion
from backend.services.model_engine import default_auction_model_trainer as trainer
from backend.services.model_engine.default_auction_model_evaluator import (
    TARGET_GATES,
    judge_target_acceptance,
)


DEFAULT_AUCTION_RELAY_MODEL_NAME = "default_auction_relay_v2"

TARGET_MODELS: List[Tuple[str, str]] = [
    ("default_auction_t0_limit_lgbm", "label_t0_limit_success"),
    ("default_auction_t1_premium_lgbm", "label_t1_premium_success"),
    ("default_auction_t1_continue_lgbm", "label_t1_continue_limit"),
]


def _load_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _append_log(job: ModelTrainingJob, message: str) -> None:
    logs = _load_json(job.logs_json, [])
    logs.append({"time": datetime.now().isoformat(timespec="seconds"), "message": message})
    job.logs_json = _dump_json(logs)


def _broadcast_job_update(db, job: ModelTrainingJob) -> None:
    return None


def _save(db, job: ModelTrainingJob) -> None:
    db.commit()
    db.refresh(job)
    _broadcast_job_update(db, job)


DEFAULT_ROLLING_WINDOW_TRADE_DAYS = [120, 100, 90, 84, 70]


def _profiles_from_params(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    profiles = params.get("profiles")
    if isinstance(profiles, list) and profiles:
        normalized = []
        for index, profile in enumerate(profiles):
            if isinstance(profile, dict) and isinstance(profile.get("params"), dict):
                normalized.append({"name": profile.get("name") or f"profile_{index + 1}", "params": profile["params"]})
            elif isinstance(profile, dict):
                normalized.append({"name": profile.get("name") or f"profile_{index + 1}", "params": profile})
        if normalized:
            return normalized
    return trainer.DEFAULT_PARAM_PROFILES


def _rolling_windows_from_params(params: Dict[str, Any]) -> List[int]:
    if params.get("enable_rolling_window_retry") is False:
        return []
    raw_windows = params.get("rolling_window_trade_days", DEFAULT_ROLLING_WINDOW_TRADE_DAYS)
    if not isinstance(raw_windows, list):
        return []
    windows: List[int] = []
    for value in raw_windows:
        try:
            days = int(value)
        except (TypeError, ValueError):
            continue
        if days >= 30 and days not in windows:
            windows.append(days)
    return windows


def _rolling_window_start_dates(
    db,
    label_column: str,
    end_date: str | None,
    windows: List[int],
    min_start_date: str | None = None,
) -> Dict[int, str]:
    label_attr = getattr(DefaultAuctionTrainingSample, label_column, None)
    if label_attr is None or not windows:
        return {}
    query = db.query(DefaultAuctionTrainingSample.trade_date).filter(label_attr.isnot(None))
    if min_start_date:
        query = query.filter(DefaultAuctionTrainingSample.trade_date >= min_start_date)
    if end_date:
        query = query.filter(DefaultAuctionTrainingSample.trade_date <= end_date)
    dates = [
        item[0]
        for item in query.distinct().order_by(DefaultAuctionTrainingSample.trade_date.asc()).all()
        if item[0]
    ]
    result: Dict[int, str] = {}
    for days in windows:
        if len(dates) < days:
            continue
        result[days] = dates[-days]
    return result


def _build_attempt_plans(
    db,
    job: ModelTrainingJob,
    label_column: str,
    profiles: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    for profile in profiles:
        plans.append(
            {
                "profile": profile,
                "training_window": "configured",
                "window_trade_days": None,
                "start_date": job.train_start_date,
                "end_date": job.train_end_date,
            }
        )
    rolling_starts = _rolling_window_start_dates(
        db,
        label_column,
        job.train_end_date,
        _rolling_windows_from_params(params),
        min_start_date=job.train_start_date,
    )
    for days, start_date in rolling_starts.items():
        if start_date == job.train_start_date:
            continue
        for profile in profiles:
            plans.append(
                {
                    "profile": profile,
                    "training_window": f"rolling_{days}_trade_days",
                    "window_trade_days": days,
                    "start_date": start_date,
                    "end_date": job.train_end_date,
                }
            )
    return plans


def _max_attempts(params: Dict[str, Any], attempt_count: int) -> int:
    try:
        value = int(params.get("max_retrain_attempts", attempt_count))
    except (TypeError, ValueError):
        value = attempt_count
    return max(1, min(value, attempt_count))


def _job_payload(job: ModelTrainingJob) -> Dict[str, Any]:
    attempts = _load_json(job.attempts_json, [])
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
        "attempts": attempts,
        "logs": _load_json(job.logs_json, []),
        "diagnostic_report": _build_diagnostic_report(attempts),
        "best_model_version": job.best_model_version,
        "best_model_path": job.best_model_path,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _build_diagnostic_report(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    baseline_rates: Dict[str, Any] = {}
    bucket_report: List[Dict[str, Any]] = []
    failure_reasons: List[str] = []
    continuation_sample_rates: Dict[str, Any] = {}
    for attempt in attempts or []:
        target = attempt.get("target")
        metrics = attempt.get("metrics") or {}
        if target and "baseline_rate" in metrics:
            baseline_rates[target] = metrics.get("baseline_rate")
        if target == "default_auction_t1_continue_lgbm":
            continuation_sample_rates = {
                "baseline_rate": metrics.get("baseline_rate"),
                "top1_rate": metrics.get("top1_rate"),
                "top3_rate": metrics.get("top3_rate"),
                "top5_rate": metrics.get("top5_rate"),
            }
        for item in metrics.get("bucket_report") or []:
            enriched = dict(item)
            enriched["target"] = target
            bucket_report.append(enriched)
        failure_reasons.extend(attempt.get("reject_reasons") or [])

    return {
        "replay_validation_gap": {
            "status": "not_embedded_in_training_job",
            "message": "回放验收结果由 /models/default-auction-replay/validate 提供",
        },
        "baseline_rates": baseline_rates,
        "bucket_report": bucket_report,
        "auction_ratio_bucket_report": [
            item for item in bucket_report if item.get("feature_name") == "auction_ratio"
        ],
        "auction_turnover_bucket_report": [
            item for item in bucket_report if item.get("feature_name") == "auction_turnover_rate"
        ],
        "continuation_sample_rates": continuation_sample_rates,
        "high_score_low_win_commonality": [],
        "low_score_high_win_misses": [],
        "failure_reasons": sorted(set(failure_reasons)),
    }


def _build_acceptance_payload(
    accepted_targets: Dict[str, Dict[str, Any]],
    job: ModelTrainingJob,
    activation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "targets": accepted_targets,
        "all_accepted": len(accepted_targets) == len(TARGET_MODELS)
        and all(item.get("accepted") for item in accepted_targets.values()),
        "auto_activate": bool(job.auto_activate),
        "activation": activation or {"accepted": None, "reject_reasons": []},
    }


def create_default_auction_relay_job(
    db,
    start_date: str,
    end_date: str,
    params: Dict[str, Any],
    auto_activate: bool = False,
) -> ModelTrainingJob:
    job = ModelTrainingJob(
        model_name=DEFAULT_AUCTION_RELAY_MODEL_NAME,
        status="pending",
        phase="prepare",
        progress=0,
        mode=str((params or {}).get("mode", "test")),
        auto_activate=1 if auto_activate else 0,
        train_start_date=start_date,
        train_end_date=end_date,
        params_json=_dump_json(params or {}),
        acceptance_json=_dump_json({"targets": {}, "auto_activate": bool(auto_activate)}),
        attempts_json="[]",
        logs_json="[]",
    )
    _append_log(job, "默认竞价接力三目标训练任务已创建")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _latest_version(db, model_name: str, version: str) -> ModelVersion:
    mv = db.query(ModelVersion).filter(
        ModelVersion.model_name == model_name,
        ModelVersion.version == version,
    ).order_by(ModelVersion.id.desc()).first()
    if mv is None:
        raise ValueError(f"模型版本不存在: {model_name} {version}")
    return mv


def _validate_activation_versions(
    db,
    accepted_targets: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, ModelVersion], Dict[str, Any]]:
    versions: Dict[str, ModelVersion] = {}
    reject_reasons: List[str] = []
    details: Dict[str, Any] = {}

    for model_name, _ in TARGET_MODELS:
        payload = accepted_targets.get(model_name) or {}
        version = payload.get("version")
        if not version:
            reject_reasons.append("missing_version")
            details[model_name] = {"version": version, "reason": "missing_version"}
            continue
        mv = db.query(ModelVersion).filter(
            ModelVersion.model_name == model_name,
            ModelVersion.version == version,
        ).order_by(ModelVersion.id.desc()).first()
        if mv is None:
            reject_reasons.append("version_not_found")
            details[model_name] = {"version": version, "reason": "version_not_found"}
            continue
        if not mv.model_path or not os.path.exists(mv.model_path):
            reject_reasons.append("model_file_missing")
            details[model_name] = {
                "version": version,
                "version_id": mv.id,
                "model_path": mv.model_path,
                "reason": "model_file_missing",
            }
            continue
        versions[model_name] = mv
        details[model_name] = {
            "version": version,
            "version_id": mv.id,
            "model_path": mv.model_path,
            "reason": "",
        }

    return versions, {
        "accepted": not reject_reasons,
        "reject_reasons": sorted(set(reject_reasons)),
        "details": details,
    }


def _reject_job_for_activation(
    db,
    job: ModelTrainingJob,
    accepted_targets: Dict[str, Dict[str, Any]],
    activation: Dict[str, Any],
) -> None:
    job.status = "rejected"
    job.phase = "rejected"
    job.progress = 100
    job.finished_at = datetime.now()
    job.error_message = "模型激活未通过预校验"
    job.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, job, activation))
    _append_log(job, f"模型激活未通过预校验: {activation.get('reject_reasons')}")
    _save(db, job)


def _activate_targets_atomically(
    db,
    job: ModelTrainingJob,
    accepted_targets: Dict[str, Dict[str, Any]],
) -> bool:
    versions, activation = _validate_activation_versions(db, accepted_targets)
    if not activation["accepted"]:
        _reject_job_for_activation(db, job, accepted_targets, activation)
        return False

    try:
        for model_name, mv in versions.items():
            db.query(ModelVersion).filter(ModelVersion.model_name == model_name).update(
                {"is_active": 0},
                synchronize_session=False,
            )
            mv.is_active = 1

        activation = {
            "accepted": True,
            "reject_reasons": [],
            "details": activation["details"],
        }
        job.status = "passed"
        job.phase = "accepted"
        job.progress = 100
        job.finished_at = datetime.now()
        job.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, job, activation))
        _append_log(job, "三目标最新通过版本已原子激活")
        db.commit()
        db.refresh(job)
        _broadcast_job_update(db, job)
        return True
    except Exception as exc:
        db.rollback()
        refreshed = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job.id).first()
        if refreshed is not None:
            activation = {
                "accepted": False,
                "reject_reasons": ["activation_update_error"],
                "error": str(exc),
            }
            refreshed.status = "rejected"
            refreshed.phase = "rejected"
            refreshed.progress = 100
            refreshed.finished_at = datetime.now()
            refreshed.error_message = "模型激活更新失败"
            refreshed.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, refreshed, activation))
            _append_log(refreshed, f"模型激活更新失败: {exc}")
            _save(db, refreshed)
        return False


def _run_one_target(
    db,
    job: ModelTrainingJob,
    target_index: int,
    model_name: str,
    label_column: str,
    profiles: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    attempts = _load_json(job.attempts_json, [])
    gate = TARGET_GATES[model_name]
    target_progress_base = 5 + int(target_index / len(TARGET_MODELS) * 85)
    target_progress_span = max(1, int(85 / len(TARGET_MODELS)))
    accepted_attempts: List[Dict[str, Any]] = []
    attempt_plans = _build_attempt_plans(db, job, label_column, profiles, params)
    max_attempts = _max_attempts(params, len(attempt_plans))

    for attempt_no, plan in enumerate(attempt_plans[:max_attempts], start=1):
        profile = plan["profile"]
        job.phase = f"train:{model_name}"
        job.progress = min(95, target_progress_base + int((attempt_no - 1) / max_attempts * target_progress_span))
        _append_log(
            job,
            f"{model_name} 开始第 {attempt_no} 次训练: {profile.get('name')} "
            f"[{plan['training_window']} {plan['start_date']}~{plan['end_date']}]",
        )
        _save(db, job)

        try:
            result = trainer.train_default_auction_target_model(
                db,
                model_name,
                label_column,
                params=profile.get("params") or {},
                activate=False,
                start_date=plan["start_date"],
                end_date=plan["end_date"],
            )
        except Exception as exc:
            db.rollback()
            job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job.id).first()
            if job is None:
                raise
            attempts = _load_json(job.attempts_json, [])
            acceptance = {
                "accepted": False,
                "reject_reasons": ["training_error"],
                "error": str(exc),
                "gate": gate.to_dict(),
            }
            attempts.append(
                {
                    "target": model_name,
                    "label_column": label_column,
                    "attempt": attempt_no,
                    "attempt_no": attempt_no,
                    "profile": profile.get("name"),
                    "param_profile": profile.get("name"),
                    "training_window": plan["training_window"],
                    "window_trade_days": plan["window_trade_days"],
                    "train_start_date": plan["start_date"],
                    "train_end_date": plan["end_date"],
                    "params": profile.get("params") or {},
                    **acceptance,
                }
            )
            job.attempts_json = _dump_json(attempts)
            _append_log(job, f"{model_name} 第 {attempt_no} 次训练失败: {exc}")
            _save(db, job)
            continue

        metrics = result.get("metrics", {})
        acceptance = judge_target_acceptance(metrics, gate)
        attempt_payload = {
            "target": model_name,
            "label_column": label_column,
            "attempt": attempt_no,
            "attempt_no": attempt_no,
            "profile": profile.get("name"),
            "param_profile": profile.get("name"),
            "training_window": plan["training_window"],
            "window_trade_days": plan["window_trade_days"],
            "train_start_date": plan["start_date"],
            "train_end_date": plan["end_date"],
            "params": profile.get("params") or {},
            "version": result.get("version"),
            "model_version": result.get("version"),
            "model_path": result.get("model_path"),
            "metrics": metrics,
            "sample_count": metrics.get("sample_count"),
            "positive_count": metrics.get("positive_count"),
            "baseline_rate": metrics.get("baseline_rate"),
            "top1_rate": metrics.get("top1_rate"),
            "top3_rate": metrics.get("top3_rate"),
            "top5_rate": metrics.get("top5_rate"),
            "top3_lift": metrics.get("top3_lift"),
            "top5_lift": metrics.get("top5_lift"),
            "auc": metrics.get("auc"),
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            **acceptance,
        }
        attempts.append(attempt_payload)
        job.attempts_json = _dump_json(attempts)

        if acceptance["accepted"]:
            _append_log(job, f"{model_name} 第 {attempt_no} 次训练通过验收")
            accepted_attempts.append(attempt_payload)
            _save(db, job)
            continue

        _append_log(job, f"{model_name} 第 {attempt_no} 次训练未通过验收: {acceptance.get('reject_reasons')}")
        _save(db, job)

    if accepted_attempts:
        best = sorted(
            accepted_attempts,
            key=lambda item: (
                float(item.get("top3_lift") or 0),
                float(item.get("top5_lift") or 0),
                float(item.get("auc") or 0),
                -int(item.get("attempt_no") or 0),
            ),
            reverse=True,
        )[0]
        _append_log(job, f"{model_name} 选择最佳通过版本: {best.get('version')} ({best.get('profile')})")
        _save(db, job)
        return best

    return {
        "target": model_name,
        "label_column": label_column,
        "accepted": False,
        "reject_reasons": ["max_retrain_attempts_exhausted"],
        "gate": gate.to_dict(),
    }


def run_default_auction_relay_training_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
        if job is None:
            return

        params = _load_json(job.params_json, {})
        profiles = _profiles_from_params(params)
        accepted_targets: Dict[str, Dict[str, Any]] = {}

        job.status = "running"
        job.phase = "prepare"
        job.progress = 5
        job.started_at = datetime.now()
        job.error_message = None
        _append_log(job, "开始默认竞价接力三目标训练")
        _save(db, job)

        for index, (model_name, label_column) in enumerate(TARGET_MODELS):
            accepted = _run_one_target(db, job, index, model_name, label_column, profiles, params)
            accepted_targets[model_name] = accepted
            job.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, job))
            _save(db, job)

        rejected_targets = [
            model_name
            for model_name, payload in accepted_targets.items()
            if not payload.get("accepted")
        ]
        if rejected_targets:
            job.status = "rejected"
            job.phase = "rejected"
            job.progress = 100
            job.finished_at = datetime.now()
            job.error_message = "部分目标未通过验收: " + ", ".join(rejected_targets)
            job.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, job))
            _append_log(job, job.error_message)
            _save(db, job)
            return

        job.best_model_version = ",".join(
            f"{model_name}:{payload.get('version')}"
            for model_name, payload in accepted_targets.items()
        )
        job.best_model_path = ",".join(
            str(payload.get("model_path") or "")
            for payload in accepted_targets.values()
        )

        if job.auto_activate:
            job.phase = "activate"
            job.progress = 96
            _append_log(job, "三目标均通过验收，开始原子激活最新通过版本")
            _save(db, job)
            _activate_targets_atomically(db, job, accepted_targets)
            return

        job.status = "passed"
        job.phase = "accepted"
        job.progress = 100
        job.finished_at = datetime.now()
        job.acceptance_json = _dump_json(_build_acceptance_payload(accepted_targets, job))
        _append_log(job, "默认竞价接力三目标训练全部通过")
        _save(db, job)
    except Exception as exc:
        db.rollback()
        job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
        if job is not None:
            job.status = "failed"
            job.phase = "failed"
            job.progress = 100
            job.error_message = str(exc)
            job.finished_at = datetime.now()
            _append_log(job, f"训练任务失败: {exc}")
            _save(db, job)
    finally:
        db.close()


def get_default_auction_relay_diagnostics(db, job_id: int) -> Dict[str, Any]:
    job = db.query(ModelTrainingJob).filter(ModelTrainingJob.id == job_id).first()
    if job is None:
        raise ValueError("训练任务不存在")
    if job.model_name != DEFAULT_AUCTION_RELAY_MODEL_NAME:
        raise ValueError(f"训练任务不是 {DEFAULT_AUCTION_RELAY_MODEL_NAME}: {job.model_name}")
    return _job_payload(job)
