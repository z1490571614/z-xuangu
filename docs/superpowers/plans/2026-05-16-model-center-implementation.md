# 模型中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建独立“模型中心”，支持模型选择、版本激活、刷新预测、参数化训练、实时进度、胜率验收和最多 3 次自动重训。

**Architecture:** 后端新增模型管理 API 与训练任务服务，复用现有 `ModelVersion`、`LeaderMainT0TrainingSample`、`SelectedStock`、`batch_predict_model` 和 WebSocket channel。前端新增 `/models` 页面作为主工作台，结果页只添加轻量“刷新当前记录预测”入口。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、LightGBM、Vue 3、Vue Router、Axios、WebSocket、pytest、Vite。

---

## File Structure

**Create**

- `backend/models/model_training_job.py`：训练任务 ORM 模型。
- `backend/services/model_engine/model_management_service.py`：模型列表、版本激活、刷新预测。
- `backend/services/model_engine/training_job_service.py`：后台训练任务、进度记录、WebSocket 推送、验收与自动重训。
- `backend/api/model_management.py`：模型中心 API 路由。
- `frontend/src/views/ModelCenter.vue`：模型中心页面。
- `tests/backend/unit/test_model_management_api.py`：模型列表、激活、刷新预测 API 测试。
- `tests/backend/unit/test_model_training_job_service.py`：训练任务与验收逻辑测试。
- `frontend/tests/e2e/model-center.spec.js`：模型中心关键 UI 流程。

**Modify**

- `backend/models/__init__.py`：注册 `ModelTrainingJob`。
- `backend/main.py`：引入并注册 `model_management.router`，移除或兼容旧 `/api/v1/model/status`。
- `backend/database/schema_migrations.py`：运行期补齐 `model_training_job` 表。
- `backend/services/model_engine/lightgbm_service.py`：增加参数化训练入口，保留原有训练函数兼容。
- `frontend/src/router/index.js`：新增 `/models`。
- `frontend/src/App.vue`：导航增加“模型中心”。
- `frontend/src/views/StockResults.vue`：增加刷新当前记录预测的轻量入口。
- `frontend/src/views/Dashboard.vue`：LightGBM 状态跳转模型中心。

---

### Task 1: 训练任务数据模型

**Files:**
- Create: `backend/models/model_training_job.py`
- Modify: `backend/models/__init__.py`
- Modify: `backend/database/schema_migrations.py`
- Test: `tests/backend/unit/test_model_training_job_service.py`

- [ ] **Step 1: Write failing ORM registration test**

Add to `tests/backend/unit/test_model_training_job_service.py`:

```python
import json

from backend.database import Base, engine
from backend.models import ModelTrainingJob


def test_model_training_job_model_is_registered(db):
    Base.metadata.create_all(bind=engine)

    job = ModelTrainingJob(
        model_name="leader_main_t0_lgbm",
        status="pending",
        phase="prepare",
        progress=0,
        train_start_date="20250101",
        train_end_date="20260508",
        params_json=json.dumps({"learning_rate": 0.05}, ensure_ascii=False),
        acceptance_json=json.dumps({"min_precision": 0.5}, ensure_ascii=False),
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()

    saved = db.query(ModelTrainingJob).filter_by(model_name="leader_main_t0_lgbm").one()
    assert saved.status == "pending"
    assert saved.phase == "prepare"
    assert saved.progress == 0
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py::test_model_training_job_model_is_registered -q
```

Expected: FAIL with import error for `ModelTrainingJob`.

- [ ] **Step 3: Create ORM model**

Create `backend/models/model_training_job.py`:

```python
"""
模型训练任务表。
"""
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from backend.database import Base


class ModelTrainingJob(Base):
    __tablename__ = "model_training_job"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    phase = Column(String(50), nullable=False, default="prepare")
    progress = Column(Integer, nullable=False, default=0)
    train_start_date = Column(String(10), nullable=False)
    train_end_date = Column(String(10), nullable=False)
    params_json = Column(Text)
    acceptance_json = Column(Text)
    attempts_json = Column(Text)
    logs_json = Column(Text)
    best_model_version = Column(String(50))
    best_model_path = Column(String(500))
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

Modify `backend/models/__init__.py`:

```python
from backend.models.model_training_job import ModelTrainingJob
```

Add `"ModelTrainingJob"` to `__all__`.

- [ ] **Step 4: Add SQLite runtime table creation**

Modify `backend/database/schema_migrations.py`:

```python
def ensure_runtime_columns(engine) -> None:
    """补齐 create_all 不会自动添加的既有表字段。"""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "model_training_job" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE model_training_job (
                    id INTEGER NOT NULL PRIMARY KEY,
                    model_name VARCHAR(100) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    phase VARCHAR(50) NOT NULL,
                    progress INTEGER NOT NULL,
                    train_start_date VARCHAR(10) NOT NULL,
                    train_end_date VARCHAR(10) NOT NULL,
                    params_json TEXT,
                    acceptance_json TEXT,
                    attempts_json TEXT,
                    logs_json TEXT,
                    best_model_version VARCHAR(50),
                    best_model_path VARCHAR(500),
                    error_message TEXT,
                    started_at DATETIME,
                    finished_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX ix_model_training_job_id ON model_training_job (id)"))
            conn.execute(text("CREATE INDEX ix_model_training_job_model_name ON model_training_job (model_name)"))
            conn.execute(text("CREATE INDEX ix_model_training_job_status ON model_training_job (status)"))
            logger.info("数据库表已补齐: model_training_job")
            existing_tables.add("model_training_job")
```

Place this block immediately after `existing_tables = set(inspector.get_table_names())` and before the existing `additions` dictionary in `ensure_runtime_columns`. Do not edit the existing `additions` dictionary or the existing column backfill loop.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py::test_model_training_job_model_is_registered -q
```

Expected: PASS.

---

### Task 2: 训练参数与验收纯函数

**Files:**
- Create: `backend/services/model_engine/training_job_service.py`
- Test: `tests/backend/unit/test_model_training_job_service.py`

- [ ] **Step 1: Write failing tests for defaults, validation, and acceptance**

Append to `tests/backend/unit/test_model_training_job_service.py`:

```python
import pytest

from backend.services.model_engine.training_job_service import (
    TrainingParams,
    AcceptanceCriteria,
    choose_acceptance_threshold,
    validate_training_params,
)


def test_training_params_defaults_are_safe():
    params = TrainingParams()
    assert params.learning_rate == 0.05
    assert params.n_estimators == 500
    assert params.num_leaves == 31
    assert params.is_unbalance is True
    assert params.early_stopping_rounds == 50


def test_validate_training_params_rejects_invalid_ranges():
    params = TrainingParams(learning_rate=2.0)
    with pytest.raises(ValueError, match="learning_rate"):
        validate_training_params(params)


def test_choose_acceptance_threshold_prefers_passing_threshold_with_more_hits():
    criteria = AcceptanceCriteria(min_precision=0.5, min_hit_count=30, threshold=0.5)
    evaluation = [
        {"threshold": 0.4, "precision": 0.52, "hit_count": 45, "recall": 0.4},
        {"threshold": 0.5, "precision": 0.48, "hit_count": 60, "recall": 0.5},
        {"threshold": 0.6, "precision": 0.61, "hit_count": 20, "recall": 0.2},
    ]

    accepted = choose_acceptance_threshold(evaluation, criteria)

    assert accepted["accepted"] is True
    assert accepted["threshold"] == 0.4
    assert accepted["precision"] == 0.52
    assert accepted["hit_count"] == 45


def test_choose_acceptance_threshold_rejects_when_no_threshold_passes():
    criteria = AcceptanceCriteria(min_precision=0.5, min_hit_count=30, threshold=0.5)
    evaluation = [
        {"threshold": 0.4, "precision": 0.49, "hit_count": 45},
        {"threshold": 0.6, "precision": 0.61, "hit_count": 20},
    ]

    accepted = choose_acceptance_threshold(evaluation, criteria)

    assert accepted["accepted"] is False
    assert accepted["reason"] == "未找到同时满足胜率和命中数的阈值"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py -q
```

Expected: FAIL because `training_job_service` does not exist.

- [ ] **Step 3: Implement pure service primitives**

Create `backend/services/model_engine/training_job_service.py`:

```python
"""
模型训练任务服务。
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


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
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py -q
```

Expected: PASS.

---

### Task 3: 参数化 LightGBM 训练入口

**Files:**
- Modify: `backend/services/model_engine/lightgbm_service.py`
- Test: `tests/backend/unit/test_leader_main_t0_lightgbm.py`

- [ ] **Step 1: Write failing test for configurable training params**

Append to `tests/backend/unit/test_leader_main_t0_lightgbm.py`:

```python
def test_train_leader_main_t0_accepts_configurable_params(db, monkeypatch, tmp_path):
    for i in range(120):
        db.add(
            LeaderMainT0TrainingSample(
                strategy_version="leader_main_t0",
                trade_date=f"209902{(i // 12) + 1:02d}",
                ts_code=f"901{i:03d}.SZ",
                limit_up_streak=1,
                limit_up_count_100d=4,
                seal_rate_100d=90,
                rise_10d_pct=12,
                pre_change_pct=9.8,
                open_change_pct=5,
                auction_ratio=8.0,
                auction_turnover_rate=0.8,
                circ_mv=120,
                label_t0_limit_success=i % 2,
                t0_close_return=5.0,
                t0_low_return=-2.0,
            )
        )
    db.commit()

    captured = {}

    class FakeModel:
        def __init__(self, **params):
            captured["params"] = params
            self.feature_importances_ = np.ones(len(lightgbm_service.LEADER_MAIN_T0_FEATURE_COLS), dtype=int)

        def fit(self, X, y, **kwargs):
            captured["fit_kwargs"] = kwargs
            return self

        def predict_proba(self, X):
            return np.array([[0.2, 0.8] for _ in range(len(X))])

        def get_params(self):
            return captured["params"]

    class FakeJoblib:
        def dump(self, model, path):
            with open(path, "wb") as f:
                f.write(b"fake")

    monkeypatch.setitem(
        sys.modules,
        "lightgbm",
        SimpleNamespace(
            LGBMClassifier=FakeModel,
            early_stopping=lambda rounds: ("early", rounds),
            log_evaluation=lambda period: ("log", period),
        ),
    )
    monkeypatch.setitem(sys.modules, "sklearn", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "sklearn.metrics",
        SimpleNamespace(
            accuracy_score=lambda y_true, y_pred: 0.5,
            precision_score=lambda y_true, y_pred, zero_division=0: 0.5,
            recall_score=lambda y_true, y_pred, zero_division=0: 0.5,
            roc_auc_score=lambda y_true, y_prob: 0.5,
        ),
    )
    monkeypatch.setattr(lightgbm_service, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(lightgbm_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(lightgbm_service, "MODEL_DIR", str(tmp_path))

    result = lightgbm_service.train_leader_main_t0_lgbm_configurable(
        "20990201",
        "20990210",
        params={
            "learning_rate": 0.03,
            "n_estimators": 300,
            "num_leaves": 15,
            "early_stopping_rounds": 25,
            "random_seed": 7,
        },
        activate=False,
    )

    assert result["model_path"]
    assert result["version"]
    assert captured["params"]["learning_rate"] == 0.03
    assert captured["params"]["n_estimators"] == 300
    assert captured["params"]["num_leaves"] == 15
    assert captured["params"]["random_state"] == 7
    assert ("early", 25) in captured["fit_kwargs"]["callbacks"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_leader_main_t0_lightgbm.py::test_train_leader_main_t0_accepts_configurable_params -q
```

Expected: FAIL because `train_leader_main_t0_lgbm_configurable` does not exist.

- [ ] **Step 3: Implement configurable wrapper**

Modify `backend/services/model_engine/lightgbm_service.py`:

```python
DEFAULT_LEADER_MAIN_T0_PARAMS = {
    "test_size": 0.10,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "num_leaves": 31,
    "is_unbalance": True,
    "max_depth": -1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "early_stopping_rounds": 50,
    "random_seed": 42,
}
```

Add a configurable function and make old function delegate to it:

```python
def train_leader_main_t0_lgbm_configurable(
    start_date: str,
    end_date: str,
    params: Optional[Dict[str, Any]] = None,
    activate: bool = True,
) -> Optional[Dict[str, Any]]:
    config = {**DEFAULT_LEADER_MAIN_T0_PARAMS, **(params or {})}
    return _train_leader_main_t0_lgbm_impl(start_date, end_date, config, activate=activate)


def train_leader_main_t0_lgbm(start_date: str, end_date: str) -> Optional[str]:
    result = train_leader_main_t0_lgbm_configurable(start_date, end_date, activate=True)
    return result.get("model_path") if result else None
```

Rename the existing body of `train_leader_main_t0_lgbm` to `_train_leader_main_t0_lgbm_impl(start_date, end_date, config, activate=True)`. Inside the model constructor use:

```python
model = lgb.LGBMClassifier(
    objective="binary",
    boosting_type="gbdt",
    learning_rate=config["learning_rate"],
    num_leaves=config["num_leaves"],
    n_estimators=config["n_estimators"],
    subsample=config["subsample"],
    colsample_bytree=config["colsample_bytree"],
    max_depth=config["max_depth"],
    metric="auc",
    random_state=config["random_seed"],
    verbose=-1,
    is_unbalance=config["is_unbalance"],
)
```

Use `config["early_stopping_rounds"]` in the callback. Only deactivate old versions and set `is_active=1` when `activate` is true. Return:

```python
return {
    "model_path": model_path,
    "version": version,
    "metrics": metrics,
    "params": config,
}
```

- [ ] **Step 4: Verify GREEN and compatibility**

Run:

```powershell
python -m pytest tests/backend/unit/test_leader_main_t0_lightgbm.py -q
```

Expected: PASS.

---

### Task 4: 模型管理服务

**Files:**
- Create: `backend/services/model_engine/model_management_service.py`
- Test: `tests/backend/unit/test_model_management_api.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/backend/unit/test_model_management_api.py`:

```python
import json

from backend.models import ModelVersion, SelectionRecord, SelectedStock
from backend.services.model_engine.model_management_service import (
    activate_model_version,
    list_models,
    refresh_record_predictions,
)


def test_list_models_returns_versions_and_active_flag(db, tmp_path):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"fake")
    db.add(ModelVersion(
        model_name="leader_main_t0_lgbm",
        version="v1",
        model_path=str(model_path),
        feature_cols=json.dumps(["auction_ratio"], ensure_ascii=False),
        model_metrics=json.dumps({"precision": 0.5}, ensure_ascii=False),
        is_active=1,
    ))
    db.commit()

    data = list_models(db)

    assert "leader_main_t0_lgbm" in data["models"]
    version = data["models"]["leader_main_t0_lgbm"]["versions"][0]
    assert version["version"] == "v1"
    assert version["is_active"] is True
    assert version["available"] is True


def test_activate_model_version_rejects_missing_model_file(db):
    db.add(ModelVersion(
        model_name="leader_main_t0_lgbm",
        version="missing",
        model_path="H:/missing/model.pkl",
        feature_cols="[]",
        is_active=0,
    ))
    db.commit()

    result = activate_model_version(db, "leader_main_t0_lgbm", "missing")

    assert result["activated"] is False
    assert "模型文件不存在" in result["message"]


def test_refresh_record_predictions_updates_selected_stocks(db, monkeypatch, tmp_path):
    model_path = tmp_path / "fake.pkl"
    model_path.write_bytes(b"fake")
    db.add(ModelVersion(
        model_name="leader_main_t0_lgbm",
        version="v2",
        model_path=str(model_path),
        feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
        params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
        is_active=1,
    ))
    record = SelectionRecord(trade_date="20260508", total_count=1, status="success")
    db.add(record)
    db.flush()
    db.add(SelectedStock(
        record_id=record.id,
        ts_code="000001.SZ",
        name="平安银行",
        auction_ratio=8.19,
        auction_turnover_rate=0.83,
    ))
    db.commit()

    def fake_predict(model_name, stocks, output_key):
        stocks[0][output_key] = 66.6
        stocks[0][f"{output_key}_model_version"] = "v2"
        return stocks

    monkeypatch.setattr(
        "backend.services.model_engine.model_management_service.batch_predict_model",
        fake_predict,
    )

    result = refresh_record_predictions(db, "leader_main_t0_lgbm", record.id, version=None)

    stock = db.query(SelectedStock).filter_by(record_id=record.id).one()
    assert result["updated_count"] == 1
    assert float(stock.t0_limit_success_prob) == 66.6
    assert stock.t0_limit_success_model_version == "v2"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_management_api.py -q
```

Expected: FAIL because `model_management_service` does not exist.

- [ ] **Step 3: Implement model management service**

Create `backend/services/model_engine/model_management_service.py` with functions:

```python
import json
import os
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.models import ModelVersion, SelectedStock
from backend.services.model_engine.lightgbm_service import batch_predict_model

MODEL_OUTPUT_FIELDS = {
    "leader_main_t0_lgbm": ("t0_limit_success_prob", "t0_limit_success_model_version"),
    "active_auction_lgbm": ("model_score", "model_version"),
}


def _loads(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _version_to_dict(mv: ModelVersion) -> Dict[str, Any]:
    return {
        "id": mv.id,
        "model_name": mv.model_name,
        "version": mv.version,
        "is_active": bool(mv.is_active),
        "available": bool(mv.model_path and os.path.exists(mv.model_path)),
        "model_path": mv.model_path,
        "train_start_date": mv.train_start_date,
        "train_end_date": mv.train_end_date,
        "feature_cols": _loads(mv.feature_cols, []),
        "metrics": _loads(mv.model_metrics, {}),
        "params": _loads(mv.params, {}),
        "created_at": mv.created_at.isoformat() if mv.created_at else None,
    }


def list_models(db: Session) -> Dict[str, Any]:
    versions = db.query(ModelVersion).order_by(ModelVersion.model_name.asc(), ModelVersion.id.desc()).all()
    models: Dict[str, Dict[str, Any]] = {}
    for mv in versions:
        item = models.setdefault(mv.model_name, {"model_name": mv.model_name, "active_version": None, "versions": []})
        payload = _version_to_dict(mv)
        item["versions"].append(payload)
        if payload["is_active"]:
            item["active_version"] = payload
    return {"models": models}


def activate_model_version(db: Session, model_name: str, version: str) -> Dict[str, Any]:
    mv = db.query(ModelVersion).filter_by(model_name=model_name, version=version).first()
    if mv is None:
        return {"activated": False, "message": "模型版本不存在"}
    if not mv.model_path or not os.path.exists(mv.model_path):
        return {"activated": False, "message": "模型文件不存在，不能启用"}
    db.query(ModelVersion).filter_by(model_name=model_name, is_active=1).update({"is_active": 0})
    mv.is_active = 1
    db.commit()
    return {"activated": True, "message": "模型版本已启用", "version": version}


def refresh_record_predictions(
    db: Session,
    model_name: str,
    record_id: int,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    output_key, version_key = MODEL_OUTPUT_FIELDS[model_name]
    rows = db.query(SelectedStock).filter(SelectedStock.record_id == record_id).all()
    stocks = []
    for row in rows:
        stocks.append({
            "ts_code": row.ts_code,
            "limit_up_count_100d": row.limit_up_count,
            "seal_rate_100d": row.seal_rate,
            "rise_10d_pct": row.rise_10d_pct,
            "pre_change_pct": row.pre_change_pct,
            "open_change_pct": row.open_change_pct,
            "auction_ratio": row.auction_ratio,
            "auction_turnover_rate": row.auction_turnover_rate,
            "circ_mv": row.circ_mv,
        })
    predicted = batch_predict_model(model_name, stocks, output_key)
    by_code = {item["ts_code"]: item for item in predicted}
    updated = 0
    failed = []
    for row in rows:
        item = by_code.get(row.ts_code, {})
        prob = item.get(output_key)
        if prob is None:
            failed.append(row.ts_code)
            continue
        setattr(row, output_key, prob)
        setattr(row, version_key, item.get(f"{output_key}_model_version") or version)
        updated += 1
    db.commit()
    return {"record_id": record_id, "updated_count": updated, "failed": failed}
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_management_api.py -q
```

Expected: PASS.

---

### Task 5: 模型管理 API

**Files:**
- Create: `backend/api/model_management.py`
- Modify: `backend/main.py`
- Test: `tests/backend/unit/test_model_management_api.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/backend/unit/test_model_management_api.py`:

```python
def test_models_endpoint_returns_model_list(client, db, tmp_path):
    model_path = tmp_path / "api-model.pkl"
    model_path.write_bytes(b"fake")
    db.add(ModelVersion(
        model_name="leader_main_t0_lgbm",
        version="api-v1",
        model_path=str(model_path),
        feature_cols="[]",
        model_metrics=json.dumps({"precision": 0.5}, ensure_ascii=False),
        is_active=1,
    ))
    db.commit()

    res = client.get("/api/v1/models")

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["models"]["leader_main_t0_lgbm"]["active_version"]["version"] == "api-v1"


def test_activate_endpoint_rejects_missing_file(client, db):
    db.add(ModelVersion(
        model_name="leader_main_t0_lgbm",
        version="api-missing",
        model_path="H:/missing/model.pkl",
        feature_cols="[]",
        is_active=0,
    ))
    db.commit()

    res = client.post("/api/v1/models/leader_main_t0_lgbm/versions/api-missing/activate")

    assert res.status_code == 400
    assert "模型文件不存在" in res.json()["detail"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_management_api.py::test_models_endpoint_returns_model_list tests/backend/unit/test_model_management_api.py::test_activate_endpoint_rejects_missing_file -q
```

Expected: FAIL with 404.

- [ ] **Step 3: Implement API router**

Create `backend/api/model_management.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.common import ApiResponse
from backend.services.model_engine.model_management_service import (
    activate_model_version,
    list_models,
    refresh_record_predictions,
)

router = APIRouter()


class RefreshPredictionsRequest(BaseModel):
    record_id: int = Field(ge=1)
    version: Optional[str] = None


@router.get("/models", tags=["模型"])
async def get_models(db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=list_models(db))


@router.post("/models/{model_name}/versions/{version}/activate", tags=["模型"])
async def activate_model(model_name: str, version: str, db: Session = Depends(get_db)):
    result = activate_model_version(db, model_name, version)
    if not result["activated"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(code=200, message=result["message"], data=result)


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
```

Modify `backend/main.py`:

```python
from backend.api import stock, task, config, strategy, stock_detail, score_v2, anomaly, overview_brief, news_v2, backtest, model_management
app.include_router(model_management.router, prefix="/api/v1")
```

Keep old `/api/v1/model/status` until the new page no longer depends on it.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_management_api.py -q
```

Expected: PASS.

---

### Task 6: 训练任务服务与后台执行

**Files:**
- Modify: `backend/services/model_engine/training_job_service.py`
- Modify: `backend/api/model_management.py`
- Test: `tests/backend/unit/test_model_training_job_service.py`

- [ ] **Step 1: Write failing training job tests**

Append to `tests/backend/unit/test_model_training_job_service.py`:

```python
from backend.services.model_engine.training_job_service import (
    create_training_job,
    get_training_job,
    run_training_job_sync,
)


def test_create_training_job_persists_pending_job(db):
    job = create_training_job(
        db,
        model_name="leader_main_t0_lgbm",
        start_date="20250101",
        end_date="20260508",
        params=TrainingParams(),
        acceptance=AcceptanceCriteria(),
        mode="test",
        auto_activate=False,
    )

    saved = get_training_job(db, job.id)
    assert saved["status"] == "pending"
    assert saved["mode"] == "test"
    assert saved["params"]["learning_rate"] == 0.05


def test_run_training_job_rejects_when_acceptance_fails(db, monkeypatch):
    job = create_training_job(
        db,
        model_name="leader_main_t0_lgbm",
        start_date="20250101",
        end_date="20260508",
        params=TrainingParams(),
        acceptance=AcceptanceCriteria(min_precision=0.9, min_hit_count=30, max_retrain_attempts=2),
        mode="formal",
        auto_activate=False,
    )

    def fake_train(*args, **kwargs):
        return {
            "model_path": "H:/fake/model.pkl",
            "version": "attempt-v1",
            "metrics": {
                "threshold_evaluation": [
                    {"threshold": 0.5, "precision": 0.5, "hit_count": 50}
                ]
            },
            "params": {},
        }

    monkeypatch.setattr(
        "backend.services.model_engine.training_job_service.train_leader_main_t0_lgbm_configurable",
        fake_train,
    )

    result = run_training_job_sync(job.id)

    assert result["status"] == "rejected"
    assert len(result["attempts"]) == 2
    assert result["acceptance"]["accepted"] is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py::test_create_training_job_persists_pending_job tests/backend/unit/test_model_training_job_service.py::test_run_training_job_rejects_when_acceptance_fails -q
```

Expected: FAIL because functions are missing.

- [ ] **Step 3: Implement synchronous core**

In `backend/services/model_engine/training_job_service.py`, add:

```python
import asyncio
import json
from datetime import datetime
from typing import Literal

from backend.database import SessionLocal
from backend.models import ModelTrainingJob
from backend.services.model_engine.lightgbm_service import train_leader_main_t0_lgbm_configurable
from backend.services.websocket_service import manager


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback


def _append_log(job: ModelTrainingJob, message: str, level: str = "info") -> None:
    logs = _loads(job.logs_json, [])
    logs.append({"time": datetime.now().isoformat(), "level": level, "message": message})
    job.logs_json = _json(logs[-300:])


def _job_to_dict(job: ModelTrainingJob) -> Dict[str, Any]:
    return {
        "id": job.id,
        "model_name": job.model_name,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "train_start_date": job.train_start_date,
        "train_end_date": job.train_end_date,
        "params": _loads(job.params_json, {}),
        "acceptance": _loads(job.acceptance_json, {}),
        "attempts": _loads(job.attempts_json, []),
        "logs": _loads(job.logs_json, []),
        "best_model_version": job.best_model_version,
        "best_model_path": job.best_model_path,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "mode": _loads(job.params_json, {}).get("mode", "formal"),
    }


def create_training_job(
    db,
    model_name: str,
    start_date: str,
    end_date: str,
    params: TrainingParams,
    acceptance: AcceptanceCriteria,
    mode: Literal["test", "formal"],
    auto_activate: bool,
) -> ModelTrainingJob:
    validate_training_params(params)
    validate_acceptance(acceptance)
    params_payload = params.to_dict()
    params_payload["mode"] = mode
    params_payload["auto_activate"] = auto_activate
    job = ModelTrainingJob(
        model_name=model_name,
        status="pending",
        phase="prepare",
        progress=0,
        train_start_date=start_date,
        train_end_date=end_date,
        params_json=_json(params_payload),
        acceptance_json=_json(acceptance.to_dict()),
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_training_job(db, job_id: int) -> Dict[str, Any]:
    job = db.query(ModelTrainingJob).filter_by(id=job_id).first()
    if job is None:
        raise ValueError("训练任务不存在")
    return _job_to_dict(job)


def _emit_model_job_event(message: Dict[str, Any]) -> None:
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.broadcast_to_channel(message, "models"))
    finally:
        try:
            loop.close()
        except Exception:
            pass


def _update_job(db, job: ModelTrainingJob, phase: str, progress: int, message: str) -> None:
    job.phase = phase
    job.progress = progress
    _append_log(job, message)
    db.commit()
    _emit_model_job_event({"type": "model_job_update", "job": _job_to_dict(job)})


def run_training_job_sync(job_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        job = db.query(ModelTrainingJob).filter_by(id=job_id).first()
        if job is None:
            raise ValueError("训练任务不存在")
        params_payload = _loads(job.params_json, {})
        acceptance_payload = _loads(job.acceptance_json, {})
        mode = params_payload.get("mode", "formal")
        params = TrainingParams(**{k: v for k, v in params_payload.items() if k in TrainingParams.__annotations__})
        acceptance = AcceptanceCriteria(**acceptance_payload)

        job.status = "running"
        job.started_at = datetime.now()
        _update_job(db, job, "load_samples", 10, "开始加载训练样本")

        attempts = []
        accepted_payload = {"accepted": False, "reason": "未开始评估"}
        max_attempts = acceptance.max_retrain_attempts if mode == "formal" else 1
        for attempt_idx in range(1, max_attempts + 1):
            attempt_params = params.to_dict()
            attempt_params["random_seed"] = params.random_seed + attempt_idx - 1
            _update_job(db, job, "train", 20 + attempt_idx * 15, f"开始第 {attempt_idx} 次训练")
            result = train_leader_main_t0_lgbm_configurable(
                job.train_start_date,
                job.train_end_date,
                params=attempt_params,
                activate=False,
            )
            if not result:
                raise RuntimeError("训练未生成模型")
            metrics = result.get("metrics") or {}
            accepted_payload = choose_acceptance_threshold(
                metrics.get("threshold_evaluation") or [],
                acceptance,
            )
            attempt = {
                "attempt": attempt_idx,
                "version": result.get("version"),
                "model_path": result.get("model_path"),
                "metrics": metrics,
                "acceptance": accepted_payload,
            }
            attempts.append(attempt)
            job.attempts_json = _json(attempts)
            db.commit()
            if accepted_payload["accepted"]:
                job.status = "succeeded"
                job.phase = "persist"
                job.progress = 100
                job.best_model_version = result.get("version")
                job.best_model_path = result.get("model_path")
                job.finished_at = datetime.now()
                _append_log(job, "训练通过验收")
                db.commit()
                _emit_model_job_event({"type": "model_job_completed", "job": _job_to_dict(job)})
                return _job_to_dict(job)

        job.status = "rejected"
        job.phase = "acceptance"
        job.progress = 100
        job.error_message = accepted_payload.get("reason")
        job.finished_at = datetime.now()
        _append_log(job, "训练未通过验收", "warning")
        db.commit()
        _emit_model_job_event({"type": "model_job_rejected", "job": _job_to_dict(job)})
        return _job_to_dict(job)
    except Exception as exc:
        if "job" in locals() and job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now()
            _append_log(job, str(exc), "error")
            db.commit()
        raise
    finally:
        db.close()
```

- [ ] **Step 4: Add API endpoints for jobs**

In `backend/api/model_management.py`, add request model:

```python
class TrainingJobRequest(BaseModel):
    start_date: str = Field(min_length=8, max_length=8)
    end_date: str = Field(min_length=8, max_length=8)
    mode: str = Field("test", pattern="^(test|formal)$")
    auto_activate: bool = False
    params: dict = Field(default_factory=dict)
    acceptance: dict = Field(default_factory=dict)
```

Add endpoints:

```python
from fastapi import BackgroundTasks
from backend.services.model_engine.training_job_service import (
    AcceptanceCriteria,
    TrainingParams,
    create_training_job,
    get_training_job,
    run_training_job_sync,
)


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
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_training_job_service.py tests/backend/unit/test_model_management_api.py -q
```

Expected: PASS.

---

### Task 7: 模型中心页面骨架

**Files:**
- Create: `frontend/src/views/ModelCenter.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`
- Test: `frontend/tests/e2e/model-center.spec.js`

- [ ] **Step 1: Write failing Playwright smoke test**

Create `frontend/tests/e2e/model-center.spec.js`:

```javascript
import { test, expect } from '@playwright/test'

test('model center route renders core sections', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        message: 'success',
        data: {
          models: {
            leader_main_t0_lgbm: {
              model_name: 'leader_main_t0_lgbm',
              active_version: { version: 'v1', metrics: { precision: 0.5, auc: 0.69 }, available: true },
              versions: [{ version: 'v1', is_active: true, available: true, metrics: { precision: 0.5 } }]
            }
          }
        }
      })
    })
  })
  await page.goto('/models')
  await expect(page.getByRole('heading', { name: '模型中心' })).toBeVisible()
  await expect(page.getByText('模型概览')).toBeVisible()
  await expect(page.getByText('预测刷新')).toBeVisible()
  await expect(page.getByText('训练控制台')).toBeVisible()
  await expect(page.getByText('训练任务与日志')).toBeVisible()
})
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: FAIL because `/models` does not exist.

- [ ] **Step 3: Add route and navigation**

Modify `frontend/src/router/index.js`:

```javascript
import ModelCenter from '../views/ModelCenter.vue'
{
  path: '/models',
  name: 'ModelCenter',
  component: ModelCenter
}
```

Modify `frontend/src/App.vue`:

```html
<router-link to="/models" active-class="active">模型中心</router-link>
```

- [ ] **Step 4: Create ModelCenter skeleton with loading/error/empty**

Create `frontend/src/views/ModelCenter.vue`:

```vue
<template>
  <div class="model-center">
    <h2>模型中心</h2>

    <div class="toolbar">
      <button class="btn-primary" @click="loadModels" :disabled="loading">
        {{ loading ? '刷新中' : '刷新模型状态' }}
      </button>
    </div>

    <div v-if="loading" class="state">加载模型中</div>
    <div v-else-if="error" class="state error">
      {{ error }}
      <button @click="loadModels">重试</button>
    </div>
    <div v-else-if="modelNames.length === 0" class="state empty">暂无可用模型</div>

    <template v-else>
      <section class="panel">
        <h3>模型概览</h3>
        <div class="model-grid">
          <div v-for="name in modelNames" :key="name" class="model-card">
            <div class="model-title">{{ name }}</div>
            <div>Active: {{ models[name].active_version?.version || '--' }}</div>
            <div>AUC: {{ fmtMetric(models[name].active_version?.metrics?.auc) }}</div>
            <div>胜率: {{ fmtPct01(models[name].active_version?.metrics?.precision) }}</div>
          </div>
        </div>
      </section>

      <section class="panel"><h3>预测刷新</h3><p class="muted">选择模型版本并刷新指定选股记录。</p></section>
      <section class="panel"><h3>训练控制台</h3><p class="muted">配置参数，先测试训练，再正式训练。</p></section>
      <section class="panel"><h3>训练任务与日志</h3><p class="muted">实时展示训练阶段、日志和验收结果。</p></section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'

const loading = ref(false)
const error = ref('')
const models = ref({})
const modelNames = computed(() => Object.keys(models.value))

onMounted(loadModels)

async function loadModels() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/v1/models')
    models.value = res.data?.data?.models || {}
  } catch (e) {
    error.value = '模型状态加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function fmtMetric(v) { return v == null ? '--' : Number(v).toFixed(4) }
function fmtPct01(v) { return v == null ? '--' : (Number(v) * 100).toFixed(1) + '%' }
</script>

<style scoped>
.model-center { padding: 20px; }
.toolbar { margin: 12px 0; display: flex; gap: 10px; }
.panel { background: white; border-radius: 8px; padding: 18px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,.08); }
.model-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.model-card { border: 1px solid #f0f0f0; border-radius: 8px; padding: 14px; }
.model-title { font-weight: 700; color: #1890ff; margin-bottom: 8px; }
.state { background: white; border-radius: 8px; padding: 24px; }
.state.error { color: #cf1322; }
.state.empty, .muted { color: #999; }
.btn-primary { padding: 8px 14px; border: none; border-radius: 4px; background: #1890ff; color: white; cursor: pointer; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
</style>
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: PASS.

---

### Task 8: 模型版本激活与预测刷新 UI

**Files:**
- Modify: `frontend/src/views/ModelCenter.vue`
- Modify: `frontend/src/views/StockResults.vue`
- Test: `frontend/tests/e2e/model-center.spec.js`

- [ ] **Step 1: Add failing UI test for refresh prediction**

Append to `frontend/tests/e2e/model-center.spec.js`:

```javascript
test('model center refreshes predictions for a record', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          models: {
            leader_main_t0_lgbm: {
              model_name: 'leader_main_t0_lgbm',
              active_version: { version: 'v1', available: true, metrics: {} },
              versions: [{ version: 'v1', is_active: true, available: true, metrics: {} }]
            }
          }
        }
      })
    })
  })
  await page.route('**/api/v1/models/leader_main_t0_lgbm/refresh-predictions', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { updated_count: 3, failed: [] } })
    })
  })
  await page.goto('/models')
  await page.getByLabel('选股记录 ID').fill('46')
  await page.getByRole('button', { name: '刷新预测' }).click()
  await expect(page.getByText('已更新 3 只股票')).toBeVisible()
})
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: FAIL because form fields are missing.

- [ ] **Step 3: Implement prediction refresh panel**

In `ModelCenter.vue`, add state:

```javascript
const selectedModel = ref('leader_main_t0_lgbm')
const selectedVersion = ref('')
const refreshRecordId = ref('')
const refreshStatus = ref('')
const refreshing = ref(false)
```

Add template inside “预测刷新” panel:

```html
<div class="form-row">
  <label>模型</label>
  <select v-model="selectedModel">
    <option v-for="name in modelNames" :key="name" :value="name">{{ name }}</option>
  </select>
  <label>版本</label>
  <select v-model="selectedVersion">
    <option value="">active</option>
    <option v-for="v in models[selectedModel]?.versions || []" :key="v.version" :value="v.version">
      {{ v.version }}{{ v.is_active ? ' (active)' : '' }}
    </option>
  </select>
  <label for="refresh-record-id">选股记录 ID</label>
  <input id="refresh-record-id" v-model="refreshRecordId" placeholder="例如 46" />
  <button class="btn-primary" :disabled="refreshing || !refreshRecordId" @click="refreshPredictions">
    {{ refreshing ? '刷新中' : '刷新预测' }}
  </button>
</div>
<p v-if="refreshStatus" class="status-line">{{ refreshStatus }}</p>
```

Add method:

```javascript
async function refreshPredictions() {
  refreshing.value = true
  refreshStatus.value = ''
  try {
    const res = await axios.post(`/api/v1/models/${selectedModel.value}/refresh-predictions`, {
      record_id: Number(refreshRecordId.value),
      version: selectedVersion.value || null
    })
    const data = res.data?.data || {}
    refreshStatus.value = `已更新 ${data.updated_count || 0} 只股票`
  } catch (e) {
    refreshStatus.value = '刷新失败：' + (e.response?.data?.detail || e.message)
  } finally {
    refreshing.value = false
  }
}
```

- [ ] **Step 4: Add StockResults lightweight entry**

In `frontend/src/views/StockResults.vue`, add button in `.header-actions`:

```html
<button class="btn-clear-cache" :disabled="!currentRecordId" @click="$router.push(`/models?record_id=${currentRecordId}`)">
  刷新模型预测
</button>
```

Import router only if not available; in `<script setup>`:

```javascript
import { useRouter } from 'vue-router'
const router = useRouter()
```

Use `router.push(`/models?record_id=${currentRecordId.value}`)` in a method if template access is not desired.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: PASS.

---

### Task 9: 训练控制台 UI 与 WebSocket 进度

**Files:**
- Modify: `frontend/src/views/ModelCenter.vue`
- Test: `frontend/tests/e2e/model-center.spec.js`

- [ ] **Step 1: Add failing test for starting test training**

Append to `frontend/tests/e2e/model-center.spec.js`:

```javascript
test('model center starts a test training job and shows progress', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { models: { leader_main_t0_lgbm: { model_name: 'leader_main_t0_lgbm', active_version: null, versions: [] } } } })
    })
  })
  await page.route('**/api/v1/models/leader_main_t0_lgbm/training-jobs', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { job_id: 12 } })
    })
  })
  await page.route('**/api/v1/models/training-jobs/12', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: { id: 12, status: 'running', phase: 'train', progress: 55, logs: [{ message: '开始第 1 次训练' }], attempts: [] }
      })
    })
  })
  await page.goto('/models')
  await page.getByLabel('训练开始日期').fill('20250101')
  await page.getByLabel('训练结束日期').fill('20260508')
  await page.getByRole('button', { name: '测试训练' }).click()
  await expect(page.getByText('任务 #12')).toBeVisible()
  await expect(page.getByText('55%')).toBeVisible()
})
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: FAIL because training form is missing.

- [ ] **Step 3: Add training form state**

In `ModelCenter.vue`, add:

```javascript
const training = ref(false)
const currentJob = ref(null)
const trainingForm = ref({
  start_date: '20250101',
  end_date: '',
  learning_rate: 0.05,
  n_estimators: 500,
  num_leaves: 31,
  threshold: 0.5,
  min_precision: 0.5,
  min_hit_count: 30,
  max_retrain_attempts: 3,
  is_unbalance: true,
  max_depth: -1,
  subsample: 0.8,
  colsample_bytree: 0.8,
  early_stopping_rounds: 50,
  random_seed: 42,
})
```

Add method:

```javascript
async function startTraining(mode) {
  training.value = true
  try {
    const payload = {
      start_date: trainingForm.value.start_date,
      end_date: trainingForm.value.end_date,
      mode,
      auto_activate: false,
      params: {
        learning_rate: Number(trainingForm.value.learning_rate),
        n_estimators: Number(trainingForm.value.n_estimators),
        num_leaves: Number(trainingForm.value.num_leaves),
        is_unbalance: Boolean(trainingForm.value.is_unbalance),
        max_depth: Number(trainingForm.value.max_depth),
        subsample: Number(trainingForm.value.subsample),
        colsample_bytree: Number(trainingForm.value.colsample_bytree),
        early_stopping_rounds: Number(trainingForm.value.early_stopping_rounds),
        random_seed: Number(trainingForm.value.random_seed),
      },
      acceptance: {
        threshold: Number(trainingForm.value.threshold),
        min_precision: Number(trainingForm.value.min_precision),
        min_hit_count: Number(trainingForm.value.min_hit_count),
        max_retrain_attempts: Number(trainingForm.value.max_retrain_attempts),
      },
    }
    const res = await axios.post(`/api/v1/models/${selectedModel.value}/training-jobs`, payload)
    currentJob.value = { id: res.data?.data?.job_id, status: 'pending', progress: 0, logs: [] }
    await pollTrainingJob()
  } catch (e) {
    currentJob.value = { status: 'failed', error_message: e.response?.data?.detail || e.message, logs: [] }
  } finally {
    training.value = false
  }
}

async function pollTrainingJob() {
  if (!currentJob.value?.id) return
  const res = await axios.get(`/api/v1/models/training-jobs/${currentJob.value.id}`)
  currentJob.value = res.data?.data || currentJob.value
}
```

- [ ] **Step 4: Add training form template**

Inside “训练控制台” panel:

```html
<div class="training-form">
  <label for="train-start">训练开始日期</label>
  <input id="train-start" v-model="trainingForm.start_date" />
  <label for="train-end">训练结束日期</label>
  <input id="train-end" v-model="trainingForm.end_date" />
  <label>学习率</label>
  <input v-model.number="trainingForm.learning_rate" type="number" step="0.01" />
  <label>树数量</label>
  <input v-model.number="trainingForm.n_estimators" type="number" />
  <label>叶子数</label>
  <input v-model.number="trainingForm.num_leaves" type="number" />
  <label>胜率门槛</label>
  <input v-model.number="trainingForm.min_precision" type="number" step="0.01" />
  <label>最小命中数</label>
  <input v-model.number="trainingForm.min_hit_count" type="number" />
  <label>最大重训次数</label>
  <input v-model.number="trainingForm.max_retrain_attempts" type="number" />
</div>
<div class="toolbar">
  <button class="btn-secondary" :disabled="training" @click="startTraining('test')">测试训练</button>
  <button class="btn-primary" :disabled="training" @click="startTraining('formal')">正式训练</button>
</div>
```

Inside “训练任务与日志” panel:

```html
<div v-if="currentJob" class="job-panel">
  <h4>任务 #{{ currentJob.id || '--' }}</h4>
  <div class="progress"><div class="progress-bar" :style="{ width: `${currentJob.progress || 0}%` }"></div></div>
  <div>{{ currentJob.progress || 0 }}%</div>
  <div class="log-list">
    <div v-for="(log, idx) in currentJob.logs || []" :key="idx">{{ log.message }}</div>
  </div>
</div>
```

- [ ] **Step 5: Add WebSocket subscription**

Add on mount:

```javascript
let ws = null

function connectModelWS() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const apiPort = import.meta.env.VITE_API_PORT || '9999'
  ws = new WebSocket(`${protocol}//${host}:${apiPort}/ws`)
  ws.onopen = () => ws.send(JSON.stringify({ type: 'subscribe', channel: 'models' }))
  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    const job = message.job
    if (job && currentJob.value?.id === job.id) currentJob.value = job
  }
}
```

Call `connectModelWS()` in `onMounted`, close in `onUnmounted`.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: PASS.

---

### Task 10: Full verification

**Files:**
- All files touched by prior tasks.

- [ ] **Step 1: Run backend targeted tests**

Run:

```powershell
python -m pytest tests/backend/unit/test_model_management_api.py tests/backend/unit/test_model_training_job_service.py tests/backend/unit/test_leader_main_t0_lightgbm.py tests/backend/unit/test_model_status_api.py tests/backend/unit/test_stock_api_t0_model_fields.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: exit code 0.

- [ ] **Step 3: Run model center E2E**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/model-center.spec.js --project=chromium
```

Expected: PASS.

- [ ] **Step 4: Manual smoke with services**

Use the existing restart skill or run project scripts:

```powershell
.\start_all.ps1
```

Open:

```text
http://localhost:8080/models
```

Verify:

- 模型列表显示 active 版本。
- 输入最近选股记录 ID 后可以刷新预测。
- 点击测试训练后出现任务 ID、进度和日志。
- 训练不通过验收时状态显示为 `rejected`，active 版本不变。

---

## Execution Notes

- 不新增外部数据源；训练继续复用 `LeaderMainT0TrainingSample`。
- `leader_main_t0_lgbm` 的输出字段是 `t0_limit_success_prob` 和 `t0_limit_success_model_version`。
- `active_auction_lgbm` 的输出字段是 `model_score` 和 `model_version`。
- 结果页刷新预测不得重新选股，不得重跑 AI 概览、龙虎榜、风险拆解或龙头战法。
- 训练任务失败或未通过验收不得覆盖旧 active 模型。
- `.superpowers/brainstorm/` 是视觉辅助产物，不纳入功能提交。
