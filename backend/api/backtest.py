"""
竞价增强回测与当日涨停模型日线模拟盘接口。
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.database import SessionLocal
from backend.schemas.common import ApiResponse
from backend.services.auction_data_service import AuctionDataService
from backend.services.model_engine.t0_simulation_backtest_service import (
    T0SimulationBacktestCreate,
    create_t0_simulation_backtest_run,
    get_t0_simulation_backtest_run,
    list_t0_simulation_backtest_runs,
    request_cancel_t0_simulation_backtest_run,
    run_t0_simulation_backtest,
)
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService

router = APIRouter()


class AuctionSyncRequest(BaseModel):
    trade_date: str = Field(..., min_length=8, max_length=8)


class DateRangeRequest(BaseModel):
    start_date: str = Field(..., min_length=8, max_length=8)
    end_date: str = Field(..., min_length=8, max_length=8)


class TdxLocalDailySyncRequest(DateRangeRequest):
    ts_codes: List[str] | None = None


class T0SimulationBacktestRequest(DateRangeRequest):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str | None = None
    sample_source: str = "replay_backtest"
    initial_cash: float = Field(default=100000, gt=0)
    buy_top_n: int = Field(default=2, ge=1)
    max_positions: int = Field(default=4, ge=1)
    min_buy_prob_pct: float = Field(default=50, ge=0, le=100)
    min_open_change_pct: float = -3
    max_open_change_pct: float = 7
    take_profit_pct: float = 8
    high_profit_hold_pct: float = Field(default=13, gt=0)
    profit_pullback_pct: float = Field(default=5, gt=0)
    stop_loss_pct: float = -5
    max_holding_days: int = Field(default=3, ge=1)
    force_close_on_end: bool = False
    cost: dict = Field(default_factory=dict)


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


@router.post("/backtest/t0-simulation/runs", tags=["回测"])
async def create_t0_simulation_backtest_endpoint(
    request: T0SimulationBacktestRequest,
    background_tasks: BackgroundTasks,
):
    db = SessionLocal()
    try:
        payload = T0SimulationBacktestCreate(**(request.model_dump() if hasattr(request, "model_dump") else request.dict()))
        run = create_t0_simulation_backtest_run(db, payload)
        background_tasks.add_task(run_t0_simulation_backtest, None, run.id)
        return ApiResponse(
            code=200,
            message="日线模拟回测已创建",
            data={"run_id": run.id, "status": run.status},
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建日线模拟回测失败: {e}")
    finally:
        db.close()


@router.get("/backtest/t0-simulation/runs", tags=["回测"])
async def list_t0_simulation_backtest_endpoint(limit: int = Query(20, ge=1, le=100)):
    db = SessionLocal()
    try:
        return ApiResponse(code=200, message="success", data=list_t0_simulation_backtest_runs(db, limit=limit))
    finally:
        db.close()


@router.post("/backtest/t0-simulation/runs/{run_id}/cancel", tags=["回测"])
async def cancel_t0_simulation_backtest_endpoint(run_id: int):
    db = SessionLocal()
    try:
        return ApiResponse(
            code=200,
            message="已请求停止日线模拟回测",
            data=request_cancel_t0_simulation_backtest_run(db, run_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        db.close()


@router.get("/backtest/t0-simulation/runs/{run_id}", tags=["回测"])
async def get_t0_simulation_backtest_endpoint(run_id: int):
    db = SessionLocal()
    try:
        return ApiResponse(code=200, message="success", data=get_t0_simulation_backtest_run(db, run_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        db.close()
