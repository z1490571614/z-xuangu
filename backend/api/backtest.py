"""
竞价增强回测与龙头主升 T+0 模型操作接口。
"""
import json
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database import SessionLocal
from backend.models.auction_backtest import LeaderMainT0TrainingSample
from backend.schemas.common import ApiResponse
from backend.services.auction_data_service import AuctionDataService
from backend.services.backtest.leader_main_t0_feature_builder import LeaderMainT0FeatureBuilder
from backend.services.backtest.leader_main_t0_label_builder import LeaderMainT0LabelBuilder
from backend.services.model_engine.lightgbm_service import train_leader_main_t0_lgbm
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService

router = APIRouter()


class AuctionSyncRequest(BaseModel):
    trade_date: str = Field(..., min_length=8, max_length=8)


class LeaderMainT0BuildRequest(BaseModel):
    trade_dates: List[str] = Field(..., min_length=1)


class DateRangeRequest(BaseModel):
    start_date: str = Field(..., min_length=8, max_length=8)
    end_date: str = Field(..., min_length=8, max_length=8)


class TdxLocalDailySyncRequest(DateRangeRequest):
    ts_codes: List[str] | None = None


class LeaderMainT0RunRequest(DateRangeRequest):
    train_model: bool = False


@router.post("/backtest/auction/sync", tags=["回测"])
async def sync_auction_open(request: AuctionSyncRequest):
    """同步指定交易日的历史开盘集合竞价数据。"""
    try:
        count = AuctionDataService().sync_auction_open(request.trade_date)
        return ApiResponse(
            code=200,
            message="竞价数据同步完成",
            data={"trade_date": request.trade_date, "synced_count": count},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"竞价数据同步失败: {e}")


@router.post("/backtest/auction/sync-range", tags=["回测"])
async def sync_auction_open_range(request: DateRangeRequest):
    """同步日期区间内的历史开盘集合竞价数据。"""
    try:
        result = AuctionDataService().sync_auction_open_date_range(
            request.start_date,
            request.end_date,
        )
        return ApiResponse(
            code=200,
            message="竞价数据区间同步完成",
            data={
                "start_date": request.start_date,
                "end_date": request.end_date,
                **result,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"竞价数据区间同步失败: {e}")


@router.post("/backtest/tdx-local-daily/sync", tags=["回测"])
async def sync_tdx_local_daily(request: TdxLocalDailySyncRequest):
    """将通达信本地 .day 日线同步到 stock_daily_data。"""
    try:
        result = TdxLocalDailySyncService().sync_range(
            request.start_date,
            request.end_date,
            ts_codes=request.ts_codes,
        )
        return ApiResponse(
            code=200,
            message="通达信本地日线同步完成",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"通达信本地日线同步失败: {e}")


@router.post("/backtest/auction/recalculate-ratios", tags=["回测"])
async def recalculate_auction_ratios(request: DateRangeRequest):
    """用本地日线库重算已入库竞价数据的竞昨比。"""
    try:
        result = AuctionDataService().recalculate_auction_ratios_from_daily_cache(
            request.start_date,
            request.end_date,
        )
        return ApiResponse(
            code=200,
            message="竞昨比重算完成",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"竞昨比重算失败: {e}")


@router.post("/backtest/leader-main-t0/build", tags=["回测"])
async def build_leader_main_t0_samples(request: LeaderMainT0BuildRequest):
    """构建龙头主升 T+0 候选训练样本。"""
    try:
        count = LeaderMainT0FeatureBuilder().build_leader_main_t0_range(request.trade_dates)
        return ApiResponse(
            code=200,
            message="龙头主升T+0样本构建完成",
            data={"trade_dates": request.trade_dates, "saved_count": count},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"样本构建失败: {e}")


@router.post("/backtest/leader-main-t0/labels", tags=["回测"])
async def build_leader_main_t0_labels(request: DateRangeRequest):
    """给候选样本生成 T+0 非一字涨停成功标签。"""
    try:
        count = LeaderMainT0LabelBuilder().build_leader_main_t0_labels(
            request.start_date,
            request.end_date,
        )
        return ApiResponse(
            code=200,
            message="龙头主升T+0标签生成完成",
            data={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "updated_count": count,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标签生成失败: {e}")


@router.post("/backtest/leader-main-t0/train", tags=["模型"])
async def train_leader_main_t0(request: DateRangeRequest):
    """训练 leader_main_t0_lgbm 模型。"""
    try:
        model_path = train_leader_main_t0_lgbm(request.start_date, request.end_date)
        return ApiResponse(
            code=200,
            message="龙头主升T+0模型训练完成" if model_path else "训练未生成模型",
            data={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "model_path": model_path,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型训练失败: {e}")


@router.post("/backtest/leader-main-t0/run", tags=["回测"])
async def run_leader_main_t0_pipeline(request: LeaderMainT0RunRequest):
    """按日期区间执行同步竞价、构建样本、生成标签，按需训练模型。"""
    try:
        auction_result = AuctionDataService().sync_auction_open_date_range(
            request.start_date,
            request.end_date,
        )
        trade_dates = auction_result.get("trade_dates", [])
        saved_count = LeaderMainT0FeatureBuilder().build_leader_main_t0_range(trade_dates)
        updated_count = LeaderMainT0LabelBuilder().build_leader_main_t0_labels(
            request.start_date,
            request.end_date,
        )
        model_path = None
        if request.train_model:
            model_path = train_leader_main_t0_lgbm(request.start_date, request.end_date)

        return ApiResponse(
            code=200,
            message="龙头主升T+0回测流程完成",
            data={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "trade_dates": trade_dates,
                "synced_count": auction_result.get("synced_count", 0),
                "saved_count": saved_count,
                "updated_count": updated_count,
                "model_path": model_path,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测流程执行失败: {e}")


@router.get("/backtest/leader-main-t0/samples", tags=["回测"])
async def list_leader_main_t0_samples(
    start_date: str = Query(..., min_length=8, max_length=8),
    end_date: str = Query(..., min_length=8, max_length=8),
    ts_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """查询龙头主升 T+0 回测样本与标签。"""
    db = SessionLocal()
    try:
        query = db.query(LeaderMainT0TrainingSample).filter(
            LeaderMainT0TrainingSample.trade_date.between(start_date, end_date)
        )
        if ts_code:
            query = query.filter(LeaderMainT0TrainingSample.ts_code == ts_code)
        total = query.count()
        rows = query.order_by(
            LeaderMainT0TrainingSample.trade_date.desc(),
            LeaderMainT0TrainingSample.rule_score.desc(),
        ).offset((page - 1) * page_size).limit(page_size).all()
        return ApiResponse(
            code=200,
            message="success",
            data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "samples": [_sample_to_dict(row) for row in rows],
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询样本失败: {e}")
    finally:
        db.close()


def _sample_to_dict(row: LeaderMainT0TrainingSample) -> dict:
    try:
        feature = json.loads(row.feature_json) if row.feature_json else {}
    except Exception:
        feature = {}
    return {
        "trade_date": row.trade_date,
        "ts_code": row.ts_code,
        "name": row.name,
        "auction_ratio": row.auction_ratio,
        "auction_turnover_rate": row.auction_turnover_rate,
        "open_change_pct": row.open_change_pct,
        "pre_change_pct": row.pre_change_pct,
        "rise_10d_pct": row.rise_10d_pct,
        "limit_up_streak": row.limit_up_streak,
        "market_height_rank": row.market_height_rank,
        "limit_up_count_100d": row.limit_up_count_100d,
        "rule_score": row.rule_score,
        "label_t0_limit_success": row.label_t0_limit_success,
        "t0_touched_limit": row.t0_touched_limit,
        "t0_closed_limit": row.t0_closed_limit,
        "is_one_line_limit_up": row.is_one_line_limit_up,
        "t0_high_return": row.t0_high_return,
        "t0_close_return": row.t0_close_return,
        "t0_low_return": row.t0_low_return,
        "feature": feature,
    }
