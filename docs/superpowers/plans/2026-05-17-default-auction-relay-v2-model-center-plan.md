# Default Auction Relay V2 Model Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `default_auction_relay_v2` 三目标训练体系接入现有模型中心，支持回放验收、样本构建、三模型训练、TopK 验收、预测刷新和前端展示。

**Architecture:** 新增默认竞价接力样本表，训练链路复用现有 `ModelTrainingJob`、`ModelVersion`、`SelectedStock` 和模型中心 API。新增专用服务负责回放验收、样本构建、标签生成、三目标 LightGBM 训练与评估，模型中心前端新增独立区块，不改变默认选股策略。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、LightGBM、scikit-learn、Vue 3、Axios、pytest、Vite。

---

## File Structure

**Create**

- `backend/models/default_auction_training_sample.py`：默认竞价接力训练样本 ORM。
- `backend/services/model_engine/default_auction_replay_service.py`：默认策略历史回放接口和近期真实选股对比输入。
- `backend/services/model_engine/replay_validation_service.py`：回放与真实选股相似度验收。
- `backend/services/model_engine/default_auction_sample_builder.py`：生成特征快照和训练样本。
- `backend/services/model_engine/default_auction_label_builder.py`：生成 T+0 涨停、T+1 高溢价、T+1 连板标签。
- `backend/services/model_engine/default_auction_model_evaluator.py`：TopK、分桶、基准胜率、验收闸门。
- `backend/services/model_engine/default_auction_attribution_service.py`：特征质量、分桶归因、训练归因摘要。
- `backend/services/model_engine/default_auction_model_trainer.py`：三目标训练和多 attempt 参数候选。
- `backend/services/model_engine/default_auction_relay_job_service.py`：模型中心后台任务编排。
- `tests/backend/unit/test_default_auction_training_sample.py`
- `tests/backend/unit/test_default_auction_replay_validation.py`
- `tests/backend/unit/test_default_auction_model_evaluator.py`
- `tests/backend/unit/test_default_auction_attribution_service.py`
- `tests/backend/unit/test_default_auction_model_trainer.py`
- `tests/backend/unit/test_default_auction_model_management_api.py`
- `frontend/tests/e2e/default-auction-relay-model-center.spec.js`

**Modify**

- `backend/models/__init__.py`：注册 `DefaultAuctionTrainingSample`。
- `backend/database/schema_migrations.py`：运行期补齐样本表和 `selected_stock` 预测字段。
- `backend/models/selected_stock.py`：增加 T+1 高溢价概率、T+1 连板概率、综合接力分、接力模型版本字段。
- `backend/api/model_management.py`：新增 default auction relay API。
- `backend/services/model_engine/model_management_service.py`：支持三目标模型和刷新预测写回。
- `backend/services/model_engine/training_job_service.py`：保留旧 `leader_main_t0_lgbm` 任务，新增专用任务入口时不破坏旧接口。
- `frontend/src/views/ModelCenter.vue`：新增 `default_auction_relay_v2` 区块。
- `frontend/src/views/StockResults.vue`：展示三目标概率和综合接力分。

---

## Constants

Use these model names exactly:

```python
DEFAULT_AUCTION_RELAY_STRATEGY = "default_auction_v2"
DEFAULT_AUCTION_RELAY_GROUP = "default_auction_relay_v2"
DEFAULT_AUCTION_T0_LIMIT_MODEL = "default_auction_t0_limit_lgbm"
DEFAULT_AUCTION_T1_PREMIUM_MODEL = "default_auction_t1_premium_lgbm"
DEFAULT_AUCTION_T1_CONTINUE_MODEL = "default_auction_t1_continue_lgbm"
DEFAULT_AUCTION_TARGETS = {
    DEFAULT_AUCTION_T0_LIMIT_MODEL: "label_t0_limit_success",
    DEFAULT_AUCTION_T1_PREMIUM_MODEL: "label_t1_premium_success",
    DEFAULT_AUCTION_T1_CONTINUE_MODEL: "label_t1_continue_limit",
}
DEFAULT_AUCTION_RELAY_WEIGHTS = {
    DEFAULT_AUCTION_T0_LIMIT_MODEL: 0.25,
    DEFAULT_AUCTION_T1_PREMIUM_MODEL: 0.35,
    DEFAULT_AUCTION_T1_CONTINUE_MODEL: 0.40,
}
```

---

### Task 1: 样本表和结果字段

**Files:**
- Create: `backend/models/default_auction_training_sample.py`
- Modify: `backend/models/__init__.py`
- Modify: `backend/models/selected_stock.py`
- Modify: `backend/database/schema_migrations.py`
- Test: `tests/backend/unit/test_default_auction_training_sample.py`

- [ ] **Step 1: Write failing ORM and field test**

Create `tests/backend/unit/test_default_auction_training_sample.py`:

```python
import json

from backend.database import Base, engine
from backend.models import DefaultAuctionTrainingSample, SelectedStock


def test_default_auction_training_sample_is_registered(db):
    Base.metadata.create_all(bind=engine)
    db.query(DefaultAuctionTrainingSample).delete()
    db.commit()

    sample = DefaultAuctionTrainingSample(
        trade_date="20260508",
        ts_code="000001.SZ",
        name="测试股",
        strategy_name="default",
        strategy_version="default_auction_v2",
        sample_source="replay_backtest",
        replay_source="local_replay",
        auction_source="stock_auction_open",
        auction_ratio_unit="percent",
        auction_turnover_rate_basis="free_float",
        feature_snapshot_time="2026-05-08T09:31:00",
        feature_json=json.dumps({"auction_ratio": 8.19}, ensure_ascii=False),
        label_t0_limit_success=1,
        label_t1_premium_success=0,
        label_t1_continue_limit=0,
    )
    db.add(sample)
    db.commit()

    saved = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000001.SZ").one()
    assert saved.strategy_version == "default_auction_v2"
    assert json.loads(saved.feature_json)["auction_ratio"] == 8.19


def test_selected_stock_has_default_auction_relay_prediction_fields():
    columns = {column.name for column in SelectedStock.__table__.columns}
    assert "default_t0_limit_prob" in columns
    assert "default_t1_premium_prob" in columns
    assert "default_t1_continue_prob" in columns
    assert "default_relay_score" in columns
    assert "default_relay_model_version" in columns
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_training_sample.py -q
```

Expected: FAIL because `DefaultAuctionTrainingSample` and `SelectedStock` fields do not exist.

- [ ] **Step 3: Create ORM model**

Create `backend/models/default_auction_training_sample.py`:

```python
"""
默认竞价接力 V2 训练样本。
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from backend.database import Base


class DefaultAuctionTrainingSample(Base):
    __tablename__ = "default_auction_training_sample"

    id = Column(Integer, primary_key=True, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    ts_code = Column(String(20), nullable=False, index=True)
    name = Column(String(50))
    strategy_name = Column(String(50), nullable=False, default="default")
    strategy_version = Column(String(50), nullable=False, default="default_auction_v2")
    sample_source = Column(String(30), nullable=False)
    replay_source = Column(String(30))
    matched_recent_real_sample = Column(Integer, default=0)
    auction_source = Column(String(50))
    auction_ratio_unit = Column(String(20), default="percent")
    auction_turnover_rate_basis = Column(String(50))
    feature_snapshot_time = Column(String(30))
    feature_json = Column(Text, nullable=False)
    label_t0_limit_success = Column(Integer)
    label_t1_premium_success = Column(Integer)
    label_t1_continue_limit = Column(Integer)
    t0_high_return = Column(Float)
    t0_close_return = Column(Float)
    t1_open_return = Column(Float)
    t1_high_return = Column(Float)
    t1_close_return = Column(Float)
    is_t0_limit_up = Column(Integer)
    is_t1_limit_up = Column(Integer)
    is_t0_one_line_limit_up = Column(Integer)
    is_t1_one_line_limit_up = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "strategy_version",
            "trade_date",
            "ts_code",
            "sample_source",
            name="uk_default_auction_sample",
        ),
        Index("idx_default_auction_sample_date", "trade_date"),
        Index("idx_default_auction_sample_labels", "label_t0_limit_success", "label_t1_premium_success", "label_t1_continue_limit"),
    )
```

Modify `backend/models/__init__.py`:

```python
from backend.models.default_auction_training_sample import DefaultAuctionTrainingSample
```

Add `"DefaultAuctionTrainingSample"` to `__all__`.

- [ ] **Step 4: Add selected stock fields**

Modify `backend/models/selected_stock.py` under existing model fields:

```python
    default_t0_limit_prob = Column(DECIMAL(5, 2), nullable=True)
    default_t1_premium_prob = Column(DECIMAL(5, 2), nullable=True)
    default_t1_continue_prob = Column(DECIMAL(5, 2), nullable=True)
    default_relay_score = Column(DECIMAL(5, 2), nullable=True)
    default_relay_model_version = Column(String(100), nullable=True)
```

- [ ] **Step 5: Add runtime migrations**

Modify `backend/database/schema_migrations.py`:

```python
        "selected_stock": {
            "t0_limit_success_prob": "NUMERIC(5, 2)",
            "t0_limit_success_model_version": "VARCHAR(50)",
            "default_t0_limit_prob": "NUMERIC(5, 2)",
            "default_t1_premium_prob": "NUMERIC(5, 2)",
            "default_t1_continue_prob": "NUMERIC(5, 2)",
            "default_relay_score": "NUMERIC(5, 2)",
            "default_relay_model_version": "VARCHAR(100)",
        },
```

Add a table creation block before the existing additions loop:

```python
        if "default_auction_training_sample" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE default_auction_training_sample (
                    id INTEGER NOT NULL PRIMARY KEY,
                    trade_date VARCHAR(10) NOT NULL,
                    ts_code VARCHAR(20) NOT NULL,
                    name VARCHAR(50),
                    strategy_name VARCHAR(50) NOT NULL,
                    strategy_version VARCHAR(50) NOT NULL,
                    sample_source VARCHAR(30) NOT NULL,
                    replay_source VARCHAR(30),
                    matched_recent_real_sample INTEGER DEFAULT 0,
                    auction_source VARCHAR(50),
                    auction_ratio_unit VARCHAR(20) DEFAULT 'percent',
                    auction_turnover_rate_basis VARCHAR(50),
                    feature_snapshot_time VARCHAR(30),
                    feature_json TEXT NOT NULL,
                    label_t0_limit_success INTEGER,
                    label_t1_premium_success INTEGER,
                    label_t1_continue_limit INTEGER,
                    t0_high_return FLOAT,
                    t0_close_return FLOAT,
                    t1_open_return FLOAT,
                    t1_high_return FLOAT,
                    t1_close_return FLOAT,
                    is_t0_limit_up INTEGER,
                    is_t1_limit_up INTEGER,
                    is_t0_one_line_limit_up INTEGER,
                    is_t1_one_line_limit_up INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uk_default_auction_sample UNIQUE (
                        strategy_version,
                        trade_date,
                        ts_code,
                        sample_source
                    )
                )
            """))
            conn.execute(text("CREATE INDEX idx_default_auction_sample_date ON default_auction_training_sample (trade_date)"))
            conn.execute(text("CREATE INDEX idx_default_auction_sample_labels ON default_auction_training_sample (label_t0_limit_success, label_t1_premium_success, label_t1_continue_limit)"))
            logger.info("数据库表已补齐: default_auction_training_sample")
            existing_tables.add("default_auction_training_sample")
```

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_training_sample.py -q
```

Expected: PASS.

---

### Task 2: 回放验收服务

**Files:**
- Create: `backend/services/model_engine/default_auction_replay_service.py`
- Create: `backend/services/model_engine/replay_validation_service.py`
- Test: `tests/backend/unit/test_default_auction_replay_validation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backend/unit/test_default_auction_replay_validation.py`:

```python
from backend.services.model_engine.replay_validation_service import (
    ReplayValidationConfig,
    compare_daily_lists,
    validate_replay_against_real,
)


def test_compare_daily_lists_computes_overlap_metrics():
    result = compare_daily_lists(
        trade_date="20260508",
        real_codes=["000001.SZ", "000002.SZ", "000003.SZ"],
        replay_codes=["000002.SZ", "000003.SZ", "000004.SZ"],
    )

    assert result["recall"] == 0.6667
    assert result["precision"] == 0.6667
    assert result["jaccard"] == 0.5
    assert result["count_error"] == 0.0
    assert result["intersection"] == ["000002.SZ", "000003.SZ"]


def test_validate_replay_rejects_low_overlap():
    days = [
        {"trade_date": "20260508", "real_codes": ["A", "B", "C"], "replay_codes": ["A", "X", "Y"]},
        {"trade_date": "20260515", "real_codes": ["D", "E", "F"], "replay_codes": ["D", "Y", "Z"]},
    ]
    config = ReplayValidationConfig(min_avg_recall=0.8, min_avg_jaccard=0.6, max_daily_count_error=0.3)

    result = validate_replay_against_real(days, config)

    assert result["accepted"] is False
    assert "avg_recall_below_threshold" in result["reject_reasons"]
    assert "avg_jaccard_below_threshold" in result["reject_reasons"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_replay_validation.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement validation service**

Create `backend/services/model_engine/replay_validation_service.py`:

```python
"""
默认竞价策略回放验收。
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class ReplayValidationConfig:
    min_avg_recall: float = 0.80
    min_avg_jaccard: float = 0.60
    max_daily_count_error: float = 0.30

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _round_rate(value: float) -> float:
    return round(float(value), 4)


def compare_daily_lists(trade_date: str, real_codes: List[str], replay_codes: List[str]) -> Dict[str, Any]:
    real_set = set(real_codes)
    replay_set = set(replay_codes)
    intersection = sorted(real_set & replay_set)
    union = real_set | replay_set
    real_count = len(real_set)
    replay_count = len(replay_set)
    recall = len(intersection) / real_count if real_count else 0
    precision = len(intersection) / replay_count if replay_count else 0
    jaccard = len(intersection) / len(union) if union else 0
    count_error = abs(replay_count - real_count) / max(real_count, 1)
    return {
        "trade_date": trade_date,
        "real_count": real_count,
        "replay_count": replay_count,
        "intersection_count": len(intersection),
        "intersection": intersection,
        "missing_from_replay": sorted(real_set - replay_set),
        "extra_in_replay": sorted(replay_set - real_set),
        "recall": _round_rate(recall),
        "precision": _round_rate(precision),
        "jaccard": _round_rate(jaccard),
        "count_error": _round_rate(count_error),
    }


def validate_replay_against_real(days: List[Dict[str, Any]], config: ReplayValidationConfig | None = None) -> Dict[str, Any]:
    config = config or ReplayValidationConfig()
    daily = [
        compare_daily_lists(item["trade_date"], item.get("real_codes", []), item.get("replay_codes", []))
        for item in days
    ]
    avg_recall = _round_rate(sum(item["recall"] for item in daily) / len(daily)) if daily else 0
    avg_jaccard = _round_rate(sum(item["jaccard"] for item in daily) / len(daily)) if daily else 0
    max_count_error = max((item["count_error"] for item in daily), default=1)
    reject_reasons = []
    if avg_recall < config.min_avg_recall:
        reject_reasons.append("avg_recall_below_threshold")
    if avg_jaccard < config.min_avg_jaccard:
        reject_reasons.append("avg_jaccard_below_threshold")
    if max_count_error > config.max_daily_count_error:
        reject_reasons.append("daily_count_error_above_threshold")
    return {
        "accepted": not reject_reasons,
        "reject_reasons": reject_reasons,
        "avg_recall": avg_recall,
        "avg_jaccard": avg_jaccard,
        "max_count_error": _round_rate(max_count_error),
        "daily": daily,
        "config": config.to_dict(),
    }
```

- [ ] **Step 4: Implement replay provider shell**

Create `backend/services/model_engine/default_auction_replay_service.py`:

```python
"""
默认竞价策略历史回放入口。

首版只定义模型中心需要的可测试接口。真实回放优先复用已落库的默认策略结果和历史竞价数据，
不得引入新闻、公告、舆情或 AI 文本特征。
"""
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.models import SelectionRecord, SelectedStock


class DefaultAuctionReplayService:
    def __init__(self, db: Session):
        self.db = db

    def get_recent_real_selection_days(self, limit: int = 5) -> List[Dict[str, Any]]:
        records = (
            self.db.query(SelectionRecord)
            .filter(SelectionRecord.total_count > 0)
            .order_by(SelectionRecord.trade_date.desc(), SelectionRecord.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "trade_date": record.trade_date,
                "record_id": record.id,
                "real_codes": [
                    stock.ts_code
                    for stock in self.db.query(SelectedStock)
                    .filter(SelectedStock.record_id == record.id)
                    .order_by(SelectedStock.id.asc())
                    .all()
                ],
            }
            for record in records
        ]

    def replay_trade_date(self, trade_date: str) -> Dict[str, Any]:
        records = (
            self.db.query(SelectionRecord)
            .filter(SelectionRecord.trade_date == trade_date, SelectionRecord.total_count > 0)
            .order_by(SelectionRecord.id.desc())
            .all()
        )
        if not records:
            return {"trade_date": trade_date, "replay_codes": [], "diagnostics": ["no_real_or_replay_source"]}
        record = records[0]
        stocks = (
            self.db.query(SelectedStock)
            .filter(SelectedStock.record_id == record.id)
            .order_by(SelectedStock.id.asc())
            .all()
        )
        return {
            "trade_date": trade_date,
            "replay_codes": [stock.ts_code for stock in stocks],
            "diagnostics": [],
            "replay_source": "historical_backfill",
        }
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_replay_validation.py -q
```

Expected: PASS.

---

### Task 3: 样本构建和标签生成

**Files:**
- Create: `backend/services/model_engine/default_auction_sample_builder.py`
- Create: `backend/services/model_engine/default_auction_label_builder.py`
- Test: `tests/backend/unit/test_default_auction_training_sample.py`

- [ ] **Step 1: Write failing sample builder test**

Append to `tests/backend/unit/test_default_auction_training_sample.py`:

```python
from backend.models import SelectionRecord, SelectedStock
from backend.services.model_engine.default_auction_sample_builder import build_samples_from_selected_record


def test_build_samples_from_selected_record_excludes_news_features(db):
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.commit()
    db.add(SelectionRecord(id=9001, trade_date="20260508", status="success", total_count=1))
    db.add(SelectedStock(
        record_id=9001,
        ts_code="000001.SZ",
        name="测试股",
        auction_ratio=8.19,
        auction_turnover_rate=0.8,
        open_change_pct=4.2,
        pre_change_pct=9.8,
        limit_up_count=5,
        touch_days=8,
        limit_up_days=6,
        seal_rate=80,
        rise_10d_pct=12,
        circ_mv=120,
        rule_score=70,
        final_score=82,
        score_level="A",
        risk_tags='["资金分歧"]',
    ))
    db.commit()

    result = build_samples_from_selected_record(db, 9001, sample_source="real_selected")

    assert result["created_count"] == 1
    sample = db.query(DefaultAuctionTrainingSample).filter_by(ts_code="000001.SZ").one()
    features = json.loads(sample.feature_json)
    assert features["auction_ratio"] == 8.19
    assert "has_negative_news" not in features
    assert "announcement_alpha_score" not in features
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_training_sample.py::test_build_samples_from_selected_record_excludes_news_features -q
```

Expected: FAIL because builder does not exist.

- [ ] **Step 3: Implement label helpers**

Create `backend/services/model_engine/default_auction_label_builder.py`:

```python
"""
默认竞价接力标签生成。
"""
from typing import Any, Dict


def build_t0_limit_label(row: Dict[str, Any], limit_price: float) -> Dict[str, Any]:
    high = float(row.get("t0_high") or 0)
    close = float(row.get("t0_close") or 0)
    open_price = float(row.get("t0_open") or 0)
    touched = high >= limit_price
    closed = close >= limit_price * 0.997
    return {
        "label_t0_limit_success": 1 if touched and closed else 0,
        "is_t0_limit_up": 1 if touched else 0,
        "is_t0_one_line_limit_up": 1 if touched and open_price >= limit_price * 0.997 and close >= limit_price * 0.997 else 0,
    }


def build_t1_premium_label(row: Dict[str, Any], open_threshold: float = 3, high_threshold: float = 5, close_threshold: float = 3) -> int:
    return 1 if (
        float(row.get("t1_open_return") or 0) >= open_threshold
        or float(row.get("t1_high_return") or 0) >= high_threshold
        or float(row.get("t1_close_return") or 0) >= close_threshold
    ) else 0


def build_t1_continue_label(row: Dict[str, Any], limit_price: float) -> Dict[str, Any]:
    high = float(row.get("t1_high") or 0)
    close = float(row.get("t1_close") or 0)
    open_price = float(row.get("t1_open") or 0)
    touched = high >= limit_price
    closed = close >= limit_price * 0.997
    return {
        "label_t1_continue_limit": 1 if touched and closed else 0,
        "is_t1_limit_up": 1 if touched else 0,
        "is_t1_one_line_limit_up": 1 if touched and open_price >= limit_price * 0.997 and close >= limit_price * 0.997 else 0,
    }
```

- [ ] **Step 4: Implement sample builder from selected stock**

Create `backend/services/model_engine/default_auction_sample_builder.py`:

```python
"""
默认竞价接力样本构建。
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.models import DefaultAuctionTrainingSample, SelectionRecord, SelectedStock


EXCLUDED_NEWS_FEATURES = {
    "integrated_news_service",
    "SentimentAnalyzer",
    "news_sentiment",
    "announcement_alpha_score",
    "has_negative_news",
    "has_reduction_news",
    "has_regulatory_risk",
}

FEATURE_FIELDS = [
    "auction_ratio",
    "auction_turnover_rate",
    "open_change_pct",
    "pre_change_pct",
    "limit_up_count",
    "touch_days",
    "limit_up_days",
    "seal_rate",
    "rise_10d_pct",
    "circ_mv",
    "prev_turnover_rate",
    "lu_tag",
    "lu_status",
    "lu_open_num",
    "limit_up_suc_rate",
    "rule_score",
    "final_score",
    "score_level",
    "risk_tags",
]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def stock_to_default_auction_features(stock: SelectedStock) -> Dict[str, Any]:
    features = {field: _json_safe(getattr(stock, field, None)) for field in FEATURE_FIELDS}
    features["risk_tags_count"] = len(json.loads(stock.risk_tags or "[]")) if stock.risk_tags else 0
    return {key: value for key, value in features.items() if key not in EXCLUDED_NEWS_FEATURES}


def build_samples_from_selected_record(db: Session, record_id: int, sample_source: str = "real_selected") -> Dict[str, Any]:
    record = db.query(SelectionRecord).filter(SelectionRecord.id == record_id).first()
    if record is None:
        raise ValueError("选股记录不存在")
    stocks = db.query(SelectedStock).filter(SelectedStock.record_id == record_id).all()
    created_count = 0
    for stock in stocks:
        features = stock_to_default_auction_features(stock)
        sample = DefaultAuctionTrainingSample(
            trade_date=record.trade_date,
            ts_code=stock.ts_code,
            name=stock.name,
            strategy_name="default",
            strategy_version="default_auction_v2",
            sample_source=sample_source,
            replay_source="real_record" if sample_source == "real_selected" else "historical_backfill",
            matched_recent_real_sample=1 if sample_source == "real_selected" else 0,
            auction_source="selected_stock",
            auction_ratio_unit="percent",
            auction_turnover_rate_basis="production_default",
            feature_snapshot_time=datetime.now().isoformat(timespec="seconds"),
            feature_json=json.dumps(features, ensure_ascii=False, default=str),
        )
        db.merge(sample)
        created_count += 1
    db.commit()
    return {"record_id": record_id, "created_count": created_count}
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_training_sample.py -q
```

Expected: PASS.

---

### Task 4: TopK 评估和验收闸门

**Files:**
- Create: `backend/services/model_engine/default_auction_model_evaluator.py`
- Test: `tests/backend/unit/test_default_auction_model_evaluator.py`

- [ ] **Step 1: Write failing evaluator tests**

Create `tests/backend/unit/test_default_auction_model_evaluator.py`:

```python
from backend.services.model_engine.default_auction_model_evaluator import (
    AcceptanceGate,
    evaluate_topk,
    judge_target_acceptance,
)


def test_evaluate_topk_outputs_baseline_and_lift():
    rows = [
        {"trade_date": "20260501", "prob": 0.9, "label": 1},
        {"trade_date": "20260501", "prob": 0.8, "label": 1},
        {"trade_date": "20260501", "prob": 0.7, "label": 0},
        {"trade_date": "20260502", "prob": 0.9, "label": 1},
        {"trade_date": "20260502", "prob": 0.8, "label": 0},
        {"trade_date": "20260502", "prob": 0.7, "label": 0},
    ]

    result = evaluate_topk(rows)

    assert result["baseline_rate"] == 0.5
    assert result["top1_rate"] == 1.0
    assert result["top3_rate"] == 0.5
    assert result["top1_lift"] == 0.5


def test_judge_target_acceptance_rejects_when_topk_lift_too_low():
    metrics = {
        "baseline_rate": 0.4,
        "top3_rate": 0.42,
        "top5_rate": 0.43,
        "topk_positive_count": 50,
        "auc": 0.6,
    }
    gate = AcceptanceGate(top3_lift=0.10, top5_lift=0.06, min_topk_positive_count=30, min_auc=0.55)

    result = judge_target_acceptance(metrics, gate)

    assert result["accepted"] is False
    assert "top3_lift_below_threshold" in result["reject_reasons"]
    assert "top5_lift_below_threshold" in result["reject_reasons"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_evaluator.py -q
```

Expected: FAIL because evaluator does not exist.

- [ ] **Step 3: Implement evaluator**

Create `backend/services/model_engine/default_auction_model_evaluator.py`:

```python
"""
默认竞价接力模型评估。
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class AcceptanceGate:
    top3_lift: float
    top5_lift: float
    min_topk_positive_count: int
    min_auc: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


TARGET_GATES = {
    "default_auction_t0_limit_lgbm": AcceptanceGate(0.08, 0.05, 20, 0.55),
    "default_auction_t1_premium_lgbm": AcceptanceGate(0.10, 0.06, 25, 0.55),
    "default_auction_t1_continue_lgbm": AcceptanceGate(0.06, 0.04, 10, 0.53),
}


def _rate(items: List[Dict[str, Any]]) -> float:
    if not items:
        return 0
    return round(sum(int(item.get("label") or 0) for item in items) / len(items), 4)


def evaluate_topk(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "baseline_rate": 0,
            "top1_rate": 0,
            "top3_rate": 0,
            "top5_rate": 0,
            "top1_lift": 0,
            "top3_lift": 0,
            "top5_lift": 0,
            "topk_positive_count": 0,
        }
    baseline = _rate(rows)
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(str(row.get("trade_date")), []).append(row)
    top1 = []
    top3 = []
    top5 = []
    for items in by_date.values():
        ranked = sorted(items, key=lambda item: float(item.get("prob") or 0), reverse=True)
        top1.extend(ranked[:1])
        top3.extend(ranked[:3])
        top5.extend(ranked[:5])
    top1_rate = _rate(top1)
    top3_rate = _rate(top3)
    top5_rate = _rate(top5)
    return {
        "sample_count": len(rows),
        "baseline_rate": baseline,
        "top1_rate": top1_rate,
        "top3_rate": top3_rate,
        "top5_rate": top5_rate,
        "top1_lift": round(top1_rate - baseline, 4),
        "top3_lift": round(top3_rate - baseline, 4),
        "top5_lift": round(top5_rate - baseline, 4),
        "topk_positive_count": sum(int(item.get("label") or 0) for item in top5),
    }


def judge_target_acceptance(metrics: Dict[str, Any], gate: AcceptanceGate) -> Dict[str, Any]:
    reject_reasons = []
    if float(metrics.get("top3_rate") or 0) - float(metrics.get("baseline_rate") or 0) < gate.top3_lift:
        reject_reasons.append("top3_lift_below_threshold")
    if float(metrics.get("top5_rate") or 0) - float(metrics.get("baseline_rate") or 0) < gate.top5_lift:
        reject_reasons.append("top5_lift_below_threshold")
    if int(metrics.get("topk_positive_count") or 0) < gate.min_topk_positive_count:
        reject_reasons.append("topk_positive_count_below_threshold")
    auc = metrics.get("auc")
    if auc is None or float(auc) < gate.min_auc:
        reject_reasons.append("auc_below_threshold")
    return {"accepted": not reject_reasons, "reject_reasons": reject_reasons, "gate": gate.to_dict()}
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_evaluator.py -q
```

Expected: PASS.

---

### Task 5: 特征质量和训练归因

**Files:**
- Create: `backend/services/model_engine/default_auction_attribution_service.py`
- Test: `tests/backend/unit/test_default_auction_attribution_service.py`

- [ ] **Step 1: Write failing attribution tests**

Create `tests/backend/unit/test_default_auction_attribution_service.py`:

```python
from backend.services.model_engine.default_auction_attribution_service import (
    build_bucket_report,
    build_feature_quality_report,
    build_training_attribution,
)


def test_feature_quality_report_excludes_high_missing_and_constant_features():
    rows = [
        {"auction_ratio": 8.1, "seal_rate": 80, "empty_feature": None, "constant_feature": 1, "label": 1},
        {"auction_ratio": 12.0, "seal_rate": 90, "empty_feature": None, "constant_feature": 1, "label": 0},
        {"auction_ratio": 15.0, "seal_rate": None, "empty_feature": None, "constant_feature": 1, "label": 1},
    ]

    report = build_feature_quality_report(rows, ["auction_ratio", "seal_rate", "empty_feature", "constant_feature"])

    assert "auction_ratio" in report["usable_features"]
    assert "empty_feature" in report["dropped_features"]
    assert "constant_feature" in report["dropped_features"]
    assert report["features"]["empty_feature"]["missing_rate"] == 1.0


def test_bucket_report_outputs_lift_for_auction_ratio():
    rows = [
        {"auction_ratio": 6.0, "label": 0, "prob": 0.2},
        {"auction_ratio": 10.0, "label": 1, "prob": 0.9},
        {"auction_ratio": 12.0, "label": 1, "prob": 0.8},
        {"auction_ratio": 35.0, "label": 0, "prob": 0.1},
    ]

    report = build_bucket_report(rows, label_key="label", prob_key="prob")

    auction_buckets = [item for item in report if item["feature_name"] == "auction_ratio"]
    assert any(item["bucket"] == "8-15" and item["positive_rate"] == 1.0 for item in auction_buckets)


def test_training_attribution_summarizes_success_and_failure():
    attribution = build_training_attribution(
        feature_importance={"auction_ratio": 10, "seal_rate": 0},
        bucket_report=[{"feature_name": "auction_ratio", "bucket": "8-15", "lift": 0.2}],
        reject_reasons=["top3_lift_below_threshold"],
    )

    assert attribution["top_positive_features"][0] == "auction_ratio"
    assert "seal_rate" in attribution["noise_features"]
    assert "top3_lift_below_threshold" in attribution["failure_reasons"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_attribution_service.py -q
```

Expected: FAIL because attribution service does not exist.

- [ ] **Step 3: Implement attribution service**

Create `backend/services/model_engine/default_auction_attribution_service.py`:

```python
"""
默认竞价接力训练归因。
"""
from typing import Any, Dict, List


BUCKETS = {
    "auction_ratio": [(None, 8, "0-8"), (8, 15, "8-15"), (15, 30, "15-30"), (30, None, "30+")],
    "auction_turnover_rate": [(0.5, 1, "0.5-1"), (1, 3, "1-3"), (3, 5, "3-5"), (5, 10, "5-10"), (10, None, "10+")],
    "open_change_pct": [(None, -3, "<-3"), (-3, 0, "-3-0"), (0, 3, "0-3"), (3, 7, "3-7"), (7, None, "7+")],
    "seal_rate": [(None, 60, "<60"), (60, 80, "60-80"), (80, 90, "80-90"), (90, None, "90+")],
    "rise_10d_pct": [(None, 0, "<0"), (0, 10, "0-10"), (10, 30, "10-30"), (30, None, "30+")],
    "health_score": [(None, 50, "<50"), (50, 65, "50-65"), (65, 80, "65-80"), (80, None, "80+")],
}


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def build_feature_quality_report(rows: List[Dict[str, Any]], feature_cols: List[str]) -> Dict[str, Any]:
    features = {}
    usable_features = []
    dropped_features = []
    total = len(rows)
    for col in feature_cols:
        values = [row.get(col) for row in rows]
        missing_count = sum(1 for value in values if _is_missing(value))
        non_missing = [value for value in values if not _is_missing(value)]
        zero_count = sum(1 for value in non_missing if value == 0)
        unique_count = len(set(non_missing))
        missing_rate = round(missing_count / total, 4) if total else 1
        zero_rate = round(zero_count / len(non_missing), 4) if non_missing else 1
        should_drop = missing_rate >= 0.6 or unique_count <= 1
        if should_drop:
            dropped_features.append(col)
        else:
            usable_features.append(col)
        features[col] = {
            "missing_rate": missing_rate,
            "zero_rate": zero_rate,
            "unique_count": unique_count,
            "drop": should_drop,
        }
    return {"features": features, "usable_features": usable_features, "dropped_features": dropped_features}


def _bucket_name(feature: str, value: Any) -> str | None:
    if feature not in BUCKETS or value is None:
        return None
    number = float(value)
    for lower, upper, name in BUCKETS[feature]:
        lower_ok = lower is None or number >= lower
        upper_ok = upper is None or number < upper
        if lower_ok and upper_ok:
            return name
    return None


def build_bucket_report(rows: List[Dict[str, Any]], label_key: str, prob_key: str = "prob") -> List[Dict[str, Any]]:
    baseline = sum(int(row.get(label_key) or 0) for row in rows) / len(rows) if rows else 0
    report = []
    for feature in BUCKETS:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            bucket = _bucket_name(feature, row.get(feature))
            if bucket:
                buckets.setdefault(bucket, []).append(row)
        for bucket, items in buckets.items():
            positive_rate = sum(int(item.get(label_key) or 0) for item in items) / len(items)
            top_items = sorted(items, key=lambda item: float(item.get(prob_key) or 0), reverse=True)[:5]
            topk_positive_rate = sum(int(item.get(label_key) or 0) for item in top_items) / len(top_items) if top_items else 0
            report.append({
                "feature_name": feature,
                "bucket": bucket,
                "sample_count": len(items),
                "positive_rate": round(positive_rate, 4),
                "baseline_rate": round(baseline, 4),
                "lift": round(positive_rate - baseline, 4),
                "topk_positive_rate": round(topk_positive_rate, 4),
                "conclusion": "高于基准" if positive_rate > baseline else "不高于基准",
            })
    return report


def build_training_attribution(feature_importance: Dict[str, float], bucket_report: List[Dict[str, Any]], reject_reasons: List[str]) -> Dict[str, Any]:
    sorted_features = sorted(feature_importance.items(), key=lambda item: float(item[1] or 0), reverse=True)
    top_positive_features = [name for name, value in sorted_features if value > 0][:8]
    noise_features = [name for name, value in sorted_features if value == 0]
    best_buckets = sorted(bucket_report, key=lambda item: float(item.get("lift") or 0), reverse=True)[:8]
    worst_buckets = sorted(bucket_report, key=lambda item: float(item.get("lift") or 0))[:8]
    return {
        "top_positive_features": top_positive_features,
        "top_negative_features": [],
        "unstable_features": [],
        "noise_features": noise_features,
        "best_buckets": best_buckets,
        "worst_buckets": worst_buckets,
        "failure_reasons": reject_reasons,
        "next_attempt_suggestions": ["尝试更保守参数"] if reject_reasons else [],
    }
```

- [ ] **Step 4: Wire report into trainer**

In `default_auction_model_trainer.py`, import:

```python
from backend.services.model_engine.default_auction_attribution_service import (
    build_bucket_report,
    build_feature_quality_report,
    build_training_attribution,
)
```

Before training, compute feature quality and only train with `usable_features`. After prediction, save:

```python
metrics["feature_quality_report"] = feature_quality_report
metrics["bucket_report"] = bucket_report
metrics["training_attribution"] = build_training_attribution(
    metrics["feature_importance"],
    bucket_report,
    [],
)
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_attribution_service.py -q
```

Expected: PASS.

---

### Task 6: 三目标训练器

**Files:**
- Create: `backend/services/model_engine/default_auction_model_trainer.py`
- Test: `tests/backend/unit/test_default_auction_model_trainer.py`

- [ ] **Step 1: Write failing trainer smoke test**

Create `tests/backend/unit/test_default_auction_model_trainer.py`:

```python
import json
import sys
from types import SimpleNamespace

import numpy as np

from backend.models import DefaultAuctionTrainingSample, ModelVersion
from backend.services.model_engine import default_auction_model_trainer as trainer


def test_train_target_model_creates_model_version(db, monkeypatch, tmp_path):
    db.query(DefaultAuctionTrainingSample).delete()
    db.query(ModelVersion).delete()
    db.commit()
    for i in range(120):
        db.add(DefaultAuctionTrainingSample(
            trade_date=f"209901{(i // 12) + 1:02d}",
            ts_code=f"900{i:03d}.SZ",
            strategy_name="default",
            strategy_version="default_auction_v2",
            sample_source="replay_backtest",
            auction_source="selected_stock",
            auction_ratio_unit="percent",
            auction_turnover_rate_basis="production_default",
            feature_snapshot_time="2099-01-01T09:31:00",
            feature_json=json.dumps({
                "auction_ratio": 8 + i % 5,
                "auction_turnover_rate": 0.8,
                "open_change_pct": 4,
                "pre_change_pct": 9,
                "limit_up_count": 4,
                "seal_rate": 80,
                "rise_10d_pct": 12,
                "circ_mv": 100,
            }, ensure_ascii=False),
            label_t0_limit_success=i % 2,
            label_t1_premium_success=1 if i % 3 == 0 else 0,
            label_t1_continue_limit=1 if i % 5 == 0 else 0,
        ))
    db.commit()

    class FakeModel:
        def __init__(self, **params):
            self.params = params
            self.feature_importances_ = np.ones(len(trainer.DEFAULT_AUCTION_FEATURES), dtype=int)

        def fit(self, X, y, **kwargs):
            return self

        def predict_proba(self, X):
            return np.array([[0.2, 0.8] for _ in range(len(X))])

        def get_params(self):
            return self.params

    class FakeJoblib:
        def dump(self, model, path):
            with open(path, "wb") as f:
                f.write(b"fake")

    monkeypatch.setitem(sys.modules, "lightgbm", SimpleNamespace(
        LGBMClassifier=FakeModel,
        early_stopping=lambda rounds: ("early", rounds),
        log_evaluation=lambda period: ("log", period),
    ))
    monkeypatch.setattr(trainer, "_get_joblib", lambda: FakeJoblib())
    monkeypatch.setattr(trainer, "MODEL_DIR", str(tmp_path))

    result = trainer.train_default_auction_target_model(
        db,
        model_name="default_auction_t0_limit_lgbm",
        label_col="label_t0_limit_success",
        start_date="20990101",
        end_date="20990110",
        params=trainer.DEFAULT_PARAM_PROFILES[0]["params"],
        activate=False,
    )

    assert result["version"]
    assert result["model_path"]
    assert result["metrics"]["sample_count"] == 120
    mv = db.query(ModelVersion).filter_by(model_name="default_auction_t0_limit_lgbm").one()
    assert mv.is_active == 0
    assert json.loads(mv.params)["feature_units"]["auction_ratio"] == "percent"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_trainer.py -q
```

Expected: FAIL because trainer does not exist.

- [ ] **Step 3: Implement trainer with fixed feature list and param profiles**

Create `backend/services/model_engine/default_auction_model_trainer.py` with these public names:

```python
DEFAULT_AUCTION_FEATURES = [
    "auction_ratio",
    "auction_turnover_rate",
    "open_change_pct",
    "pre_change_pct",
    "limit_up_count",
    "touch_days",
    "limit_up_days",
    "seal_rate",
    "rise_10d_pct",
    "circ_mv",
    "prev_turnover_rate",
    "rule_score",
    "final_score",
    "risk_tags_count",
]

DEFAULT_PARAM_PROFILES = [
    {"name": "balanced_default", "params": {"learning_rate": 0.05, "n_estimators": 500, "num_leaves": 31, "max_depth": -1, "min_child_samples": 20, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0, "reg_lambda": 0, "is_unbalance": True, "early_stopping_rounds": 50, "random_seed": 42}},
    {"name": "conservative_regularized", "params": {"learning_rate": 0.03, "n_estimators": 500, "num_leaves": 15, "max_depth": 4, "min_child_samples": 30, "subsample": 0.75, "colsample_bytree": 0.75, "reg_alpha": 0.1, "reg_lambda": 1.0, "is_unbalance": True, "early_stopping_rounds": 50, "random_seed": 42}},
    {"name": "shallow_stable", "params": {"learning_rate": 0.04, "n_estimators": 500, "num_leaves": 7, "max_depth": 3, "min_child_samples": 40, "subsample": 0.9, "colsample_bytree": 0.7, "reg_alpha": 0.2, "reg_lambda": 2.0, "is_unbalance": True, "early_stopping_rounds": 50, "random_seed": 42}},
    {"name": "wider_ranker", "params": {"learning_rate": 0.02, "n_estimators": 700, "num_leaves": 63, "max_depth": 6, "min_child_samples": 15, "subsample": 0.8, "colsample_bytree": 0.9, "reg_alpha": 0.05, "reg_lambda": 0.5, "is_unbalance": True, "early_stopping_rounds": 50, "random_seed": 42}},
    {"name": "seed_retry", "params": {"learning_rate": 0.03, "n_estimators": 500, "num_leaves": 15, "max_depth": 4, "min_child_samples": 30, "subsample": 0.75, "colsample_bytree": 0.75, "reg_alpha": 0.1, "reg_lambda": 1.0, "is_unbalance": True, "early_stopping_rounds": 50, "random_seed": 2026}},
]
```

The function `train_default_auction_target_model(db, model_name, label_col, start_date, end_date, params, activate=False)` must:

- Load `DefaultAuctionTrainingSample` between dates with non-null target label.
- Parse `feature_json`, exclude missing/constant features with `build_feature_quality_report`.
- Split dates by 70/15/15 in chronological order.
- Train `lightgbm.LGBMClassifier`.
- Save `ModelVersion` with `feature_cols`, `model_metrics`, `model_path`, `params`.
- Return `{version, model_path, metrics, params}`.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_trainer.py -q
```

Expected: PASS.

---

### Task 7: 模型中心专用训练任务编排

**Files:**
- Create: `backend/services/model_engine/default_auction_relay_job_service.py`
- Test: `tests/backend/unit/test_default_auction_model_trainer.py`

- [ ] **Step 1: Write failing orchestration test**

Append to `tests/backend/unit/test_default_auction_model_trainer.py`:

```python
from backend.models import ModelTrainingJob
from backend.services.model_engine.default_auction_relay_job_service import run_default_auction_relay_training_job


def test_default_auction_relay_job_trains_three_targets(db, monkeypatch):
    db.query(ModelTrainingJob).delete()
    db.commit()
    job = ModelTrainingJob(
        model_name="default_auction_relay_v2",
        status="pending",
        phase="prepare",
        progress=0,
        mode="test",
        auto_activate=0,
        train_start_date="20990101",
        train_end_date="20990110",
        params_json='{"max_retrain_attempts": 1}',
        acceptance_json="{}",
        attempts_json="[]",
        logs_json="[]",
    )
    db.add(job)
    db.commit()

    from backend.services.model_engine import default_auction_relay_job_service as service
    calls = []

    def fake_train(db_arg, model_name, label_col, start_date, end_date, params, activate):
        calls.append((model_name, label_col, activate))
        return {
            "version": model_name + "_v1",
            "model_path": model_name + ".pkl",
            "metrics": {
                "sample_count": 100,
                "baseline_rate": 0.3,
                "top3_rate": 0.5,
                "top5_rate": 0.45,
                "topk_positive_count": 50,
                "auc": 0.7,
            },
            "params": params,
        }

    monkeypatch.setattr(service, "SessionLocal", lambda: db)
    monkeypatch.setattr(service.trainer, "train_default_auction_target_model", fake_train)
    monkeypatch.setattr(service, "_broadcast_job_update", lambda _db, _job: None)

    run_default_auction_relay_training_job(job.id)

    payload = service.get_default_auction_relay_diagnostics(db, job.id)
    assert payload["status"] == "passed"
    assert len(calls) == 3
    assert all(call[2] is False for call in calls)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_trainer.py::test_default_auction_relay_job_trains_three_targets -q
```

Expected: FAIL because job service does not exist.

- [ ] **Step 3: Implement orchestration**

Create `backend/services/model_engine/default_auction_relay_job_service.py` with public functions:

```python
def create_default_auction_relay_job(db, start_date, end_date, params, auto_activate=False) -> ModelTrainingJob
def run_default_auction_relay_training_job(job_id: int) -> None
def get_default_auction_relay_diagnostics(db, job_id: int) -> dict
```

Behavior:

- `model_name` on `ModelTrainingJob` is `default_auction_relay_v2`.
- Iterate the three target model names and label columns.
- For each target, loop over `DEFAULT_PARAM_PROFILES` up to `max_retrain_attempts`.
- Train with `activate=False`.
- Judge acceptance with target-specific gates from `TARGET_GATES`.
- If all three targets pass and `auto_activate=True`, activate all three target model versions.
- If any target fails, `status="rejected"` and active versions remain unchanged.
- Write per-target attempts into `attempts_json`.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_trainer.py -q
```

Expected: PASS.

---

### Task 8: 模型中心 API 扩展

**Files:**
- Modify: `backend/api/model_management.py`
- Test: `tests/backend/unit/test_default_auction_model_management_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/backend/unit/test_default_auction_model_management_api.py`:

```python
def test_default_auction_replay_validate_api(client, monkeypatch):
    from backend.api import model_management

    monkeypatch.setattr(model_management, "validate_default_auction_replay", lambda db, recent_days: {"accepted": True, "daily": [], "recent_days": recent_days})

    resp = client.post("/api/v1/models/default-auction-replay/validate", json={"recent_days": 3})

    assert resp.status_code == 200
    assert resp.json()["data"]["accepted"] is True


def test_default_auction_relay_train_api_creates_job(client, db, monkeypatch):
    from backend.api import model_management
    from backend.models import ModelTrainingJob

    db.query(ModelTrainingJob).delete()
    db.commit()
    monkeypatch.setattr(model_management, "run_default_auction_relay_training_job", lambda _job_id: None)

    resp = client.post("/api/v1/models/default-auction-relay/train", json={
        "start_date": "20250116",
        "end_date": "20260508",
        "auto_activate": False,
        "params": {"max_retrain_attempts": 1},
    })

    assert resp.status_code == 200
    assert resp.json()["data"]["job_id"] >= 1
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_management_api.py -q
```

Expected: FAIL because routes do not exist.

- [ ] **Step 3: Add request schemas and endpoints**

Modify `backend/api/model_management.py`:

```python
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
```

Add routes:

```python
@router.post("/models/default-auction-replay/validate", tags=["模型"])
async def validate_default_auction_replay_endpoint(request: ReplayValidateRequest, db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=validate_default_auction_replay(db, request.recent_days))


@router.post("/models/default-auction-replay/build-samples", tags=["模型"])
async def build_default_auction_samples_endpoint(request: DefaultAuctionBuildSamplesRequest, db: Session = Depends(get_db)):
    if request.record_id is None:
        raise HTTPException(status_code=422, detail="record_id 不能为空")
    return ApiResponse(code=200, message="样本构建完成", data=build_samples_from_selected_record(db, request.record_id, request.sample_source))


@router.post("/models/default-auction-relay/train", tags=["模型"])
async def train_default_auction_relay_endpoint(request: DefaultAuctionRelayTrainRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = create_default_auction_relay_job(db, request.start_date, request.end_date, request.params, request.auto_activate)
    background_tasks.add_task(run_default_auction_relay_training_job, job.id)
    return ApiResponse(code=200, message="训练任务已创建", data={"job_id": job.id})


@router.get("/models/default-auction-relay/diagnostics/{job_id}", tags=["模型"])
async def default_auction_relay_diagnostics_endpoint(job_id: int, db: Session = Depends(get_db)):
    return ApiResponse(code=200, message="success", data=get_default_auction_relay_diagnostics(db, job_id))
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_management_api.py -q
```

Expected: PASS.

---

### Task 9: 刷新预测写回三目标概率

**Files:**
- Modify: `backend/services/model_engine/model_management_service.py`
- Test: `tests/backend/unit/test_default_auction_model_management_api.py`

- [ ] **Step 1: Write failing refresh test**

Append to `tests/backend/unit/test_default_auction_model_management_api.py`:

```python
import json

from backend.models import ModelVersion, SelectedStock, SelectionRecord
from backend.services.model_engine import model_management_service


def test_refresh_default_auction_relay_predictions_writes_three_probs(db, monkeypatch, tmp_path):
    db.query(SelectedStock).delete()
    db.query(SelectionRecord).delete()
    db.query(ModelVersion).delete()
    db.commit()
    db.add(SelectionRecord(id=9100, trade_date="20260508", status="success", total_count=1))
    db.add(SelectedStock(record_id=9100, ts_code="000001.SZ", name="测试股", auction_ratio=8.19, auction_turnover_rate=0.8))
    for model_name in [
        "default_auction_t0_limit_lgbm",
        "default_auction_t1_premium_lgbm",
        "default_auction_t1_continue_lgbm",
    ]:
        path = tmp_path / f"{model_name}.pkl"
        path.write_bytes(b"fake")
        db.add(ModelVersion(
            model_name=model_name,
            version="v1",
            feature_cols=json.dumps(["auction_ratio", "auction_turnover_rate"], ensure_ascii=False),
            model_path=str(path),
            params=json.dumps({"feature_units": {"auction_ratio": "percent"}}, ensure_ascii=False),
            is_active=1,
        ))
    db.commit()

    probs = {
        "default_auction_t0_limit_lgbm": 40.0,
        "default_auction_t1_premium_lgbm": 50.0,
        "default_auction_t1_continue_lgbm": 60.0,
    }
    monkeypatch.setattr(model_management_service.lightgbm_service, "_predict_with_model_path", lambda model_name, path, cols, features, units: probs[model_name])

    result = model_management_service.refresh_record_predictions(db, "default_auction_relay_v2", 9100)

    stock = db.query(SelectedStock).filter_by(record_id=9100).one()
    assert result["updated_count"] == 1
    assert float(stock.default_t0_limit_prob) == 40.0
    assert float(stock.default_t1_premium_prob) == 50.0
    assert float(stock.default_t1_continue_prob) == 60.0
    assert float(stock.default_relay_score) == 51.5
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_management_api.py::test_refresh_default_auction_relay_predictions_writes_three_probs -q
```

Expected: FAIL because `default_auction_relay_v2` refresh is unsupported.

- [ ] **Step 3: Implement relay refresh**

Modify `backend/services/model_engine/model_management_service.py`:

- Add `default_auction_relay_v2` as a composite model.
- Load active versions for all three target model names.
- Predict all three probabilities per stock.
- Write:

```python
stock.default_t0_limit_prob = t0_prob
stock.default_t1_premium_prob = premium_prob
stock.default_t1_continue_prob = continue_prob
stock.default_relay_score = round(t0_prob * 0.25 + premium_prob * 0.35 + continue_prob * 0.40, 2)
stock.default_relay_model_version = "|".join([t0_version, premium_version, continue_version])
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_model_management_api.py -q
```

Expected: PASS.

---

### Task 10: 模型中心前端区块

**Files:**
- Modify: `frontend/src/views/ModelCenter.vue`
- Test: `frontend/tests/e2e/default-auction-relay-model-center.spec.js`

- [ ] **Step 1: Write failing E2E smoke test**

Create `frontend/tests/e2e/default-auction-relay-model-center.spec.js`:

```javascript
import { test, expect } from '@playwright/test'

test('default auction relay section renders in model center', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          models: {
            default_auction_t0_limit_lgbm: { model_name: 'default_auction_t0_limit_lgbm', active_version: null, versions: [] },
            default_auction_t1_premium_lgbm: { model_name: 'default_auction_t1_premium_lgbm', active_version: null, versions: [] },
            default_auction_t1_continue_lgbm: { model_name: 'default_auction_t1_continue_lgbm', active_version: null, versions: [] }
          }
        }
      })
    })
  })
  await page.goto('http://localhost:8080/models')
  await expect(page.getByRole('heading', { name: '默认竞价接力 V2' })).toBeVisible()
  await expect(page.getByText('回放验收')).toBeVisible()
  await expect(page.getByText('样本构建')).toBeVisible()
  await expect(page.getByText('三目标训练')).toBeVisible()
})
```

- [ ] **Step 2: Run E2E to verify RED**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/default-auction-relay-model-center.spec.js --project=chromium
```

Expected: FAIL because section does not exist. If Chromium is missing, record the browser installation blocker and continue with `npm run build` after implementation.

- [ ] **Step 3: Add section state and actions**

Modify `frontend/src/views/ModelCenter.vue` script:

```javascript
const relay = ref({
  validating: false,
  building: false,
  training: false,
  validation: null,
  buildResult: null,
  diagnostics: null,
  recordId: '',
  startDate: '20250116',
  endDate: '',
  maxRetrainAttempts: 5,
})

async function validateRelayReplay() {
  relay.value.validating = true
  try {
    const res = await axios.post('/api/v1/models/default-auction-replay/validate', { recent_days: 5 })
    relay.value.validation = res.data?.data || null
  } finally {
    relay.value.validating = false
  }
}

async function buildRelaySamples() {
  relay.value.building = true
  try {
    const res = await axios.post('/api/v1/models/default-auction-replay/build-samples', {
      record_id: Number(relay.value.recordId),
      sample_source: 'real_selected',
    })
    relay.value.buildResult = res.data?.data || null
  } finally {
    relay.value.building = false
  }
}

async function startRelayTraining() {
  relay.value.training = true
  try {
    const res = await axios.post('/api/v1/models/default-auction-relay/train', {
      start_date: relay.value.startDate,
      end_date: relay.value.endDate,
      auto_activate: false,
      params: { max_retrain_attempts: Number(relay.value.maxRetrainAttempts) },
    })
    currentJob.value = { id: res.data?.data?.job_id, status: 'pending', progress: 0, logs: [] }
    await pollTrainingJob()
  } finally {
    relay.value.training = false
  }
}
```

- [ ] **Step 4: Add template section with loading/error/empty states**

Add a new panel after model overview:

```html
<section class="panel relay-panel">
  <h3>默认竞价接力 V2</h3>
  <div class="relay-grid">
    <div class="relay-card">
      <h4>回放验收</h4>
      <button class="btn-secondary" :disabled="relay.validating" @click="validateRelayReplay">验证最近真实选股</button>
      <div v-if="relay.validating" class="empty-inline">验收中</div>
      <div v-else-if="relay.validation" class="status-line">
        {{ relay.validation.accepted ? '回放验收通过' : '回放验收未通过' }}
      </div>
      <div v-else class="empty-inline">暂无回放验收结果</div>
    </div>
    <div class="relay-card">
      <h4>样本构建</h4>
      <label>选股记录 ID<input v-model="relay.recordId" /></label>
      <button class="btn-secondary" :disabled="relay.building || !relay.recordId" @click="buildRelaySamples">构建样本</button>
      <div v-if="relay.buildResult" class="status-line">已生成 {{ relay.buildResult.created_count || 0 }} 条样本</div>
      <div v-else class="empty-inline">暂无样本构建结果</div>
    </div>
    <div class="relay-card">
      <h4>三目标训练</h4>
      <label>开始日期<input v-model="relay.startDate" /></label>
      <label>结束日期<input v-model="relay.endDate" /></label>
      <label>最大重训次数<input v-model.number="relay.maxRetrainAttempts" type="number" /></label>
      <button class="btn-primary" :disabled="relay.training" @click="startRelayTraining">启动接力训练</button>
    </div>
  </div>
</section>
```

- [ ] **Step 5: Verify build**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

---

### Task 11: 选股结果页展示

**Files:**
- Modify: `frontend/src/views/StockResults.vue`
- Test: `frontend/tests/e2e/lightgbm-results.spec.js`

- [ ] **Step 1: Add expected columns test**

Append or modify `frontend/tests/e2e/lightgbm-results.spec.js` to assert text:

```javascript
await expect(page.getByText('T+0涨停概率')).toBeVisible()
await expect(page.getByText('T+1高溢价概率')).toBeVisible()
await expect(page.getByText('T+1连板概率')).toBeVisible()
await expect(page.getByText('接力分')).toBeVisible()
```

- [ ] **Step 2: Run E2E to verify RED**

Run:

```powershell
cd frontend
npx playwright test tests/e2e/lightgbm-results.spec.js --project=chromium
```

Expected: FAIL because new columns do not exist, or browser missing.

- [ ] **Step 3: Add columns**

Modify `frontend/src/views/StockResults.vue` table header and row:

```html
<th>T+0涨停概率</th>
<th>T+1高溢价概率</th>
<th>T+1连板概率</th>
<th>接力分</th>
```

```html
<td>{{ formatPercentScore(stock.default_t0_limit_prob) }}</td>
<td>{{ formatPercentScore(stock.default_t1_premium_prob) }}</td>
<td>{{ formatPercentScore(stock.default_t1_continue_prob) }}</td>
<td>{{ formatScore(stock.default_relay_score) }}</td>
```

Add helpers if absent:

```javascript
function formatPercentScore(value) {
  if (value === null || value === undefined) return '--'
  return Number(value).toFixed(1) + '%'
}
```

- [ ] **Step 4: Verify build**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

---

### Task 12: Full verification

**Files:**
- All files touched by prior tasks.

- [ ] **Step 1: Backend targeted tests**

Run:

```powershell
python -m pytest tests/backend/unit/test_default_auction_training_sample.py tests/backend/unit/test_default_auction_replay_validation.py tests/backend/unit/test_default_auction_model_evaluator.py tests/backend/unit/test_default_auction_attribution_service.py tests/backend/unit/test_default_auction_model_trainer.py tests/backend/unit/test_default_auction_model_management_api.py tests/backend/unit/test_model_management_api.py tests/backend/unit/test_model_training_job_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Existing model tests**

Run:

```powershell
python -m pytest tests/backend/unit/test_leader_main_t0_lightgbm.py tests/backend/unit/test_stock_api_t0_model_fields.py tests/backend/unit/test_model_status_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Service smoke**

Restart services:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\z\.codex\skills\restart-xuangu-services\scripts\restart-xuangu-services.ps1
```

Then verify:

```powershell
Invoke-RestMethod http://127.0.0.1:9999/api/v1/models
Invoke-WebRequest http://localhost:8080/models -UseBasicParsing
```

Expected: both return success.

- [ ] **Step 5: Manual smoke**

In `http://localhost:8080/models`:

- Validate default auction replay.
- Build samples for a recent real `record_id`.
- Start relay training in test mode with `max_retrain_attempts=1`.
- Confirm job logs appear.
- Confirm active versions do not change in test mode.
- Refresh predictions for a recent record with `default_auction_relay_v2`.
- Confirm `SelectedStock.default_relay_score` is written.

---

## Implementation Notes

- Do not use news, announcements, sentiment, `integrated_news_service`, `SentimentAnalyzer`, `news_sentiment`, or AI text factors.
- `auction_ratio` stays in percent units: `8.19` means `8.19%`.
- Training and evaluation split by trade date only; random split is not allowed.
- `default_auction_relay_v2` is a composite model group. The stored model versions are the three target models.
- Failed training must not change active versions.
- Existing `leader_main_t0_lgbm` remains available and compatible in model center.
