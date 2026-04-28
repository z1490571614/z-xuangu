"""
选股策略模板 API 路由

提供策略模板的完整 CRUD 操作：
- GET    /api/v1/stock/strategies          - 获取所有策略
- POST   /api/v1/stock/strategies          - 创建自定义策略
- POST   /api/v1/stock/strategies/init     - 初始化预置模板 (必须在动态路由前)
- GET    /api/v1/stock/strategies/{id}     - 获取策略详情
- PUT    /api/v1/stock/strategies/{id}     - 更新策略
- DELETE /api/v1/stock/strategies/{id}     - 删除策略
- PATCH  /api/v1/stock/strategies/{id}/toggle - 切换启用状态
- POST   /api/v1/stock/strategies/{id}/preview - 预览策略查询语句

注意：静态路由必须在动态路由之前定义，否则会被错误匹配！
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import StrategyTemplate
from backend.services.strategy_service import StrategyTemplateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock/strategies", tags=["选股策略"])


class StrategyCreateRequest(BaseModel):
    """创建策略请求"""

    name: str = Field(..., min_length=2, max_length=100, description="策略名称")
    description: Optional[str] = Field(None, max_length=500, description="策略描述")
    task_template: str = Field(
        default="custom",
        description="任务模板类型: default/conservative/aggressive/custom",
    )
    conditions_config: dict = Field(
        ...,
        description="选股条件配置 (JSON格式)",
    )
    strategy_params: Optional[dict] = Field(
        None,
        description="高级策略参数 (可选)",
    )
    is_enabled: bool = Field(default=True, description="是否启用")
    sort_order: int = Field(default=99, description="排序顺序")


class StrategyUpdateRequest(BaseModel):
    """更新策略请求"""

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    task_template: Optional[str] = None
    conditions_config: Optional[dict] = None
    strategy_params: Optional[dict] = None
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class StrategyResponse(BaseModel):
    """策略响应"""

    id: int
    name: str
    description: Optional[str]
    task_template: str
    is_system: bool
    is_enabled: bool
    conditions_config: dict
    strategy_params: Optional[dict]
    sort_order: int
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


# ========== 静态路由（必须在动态路由前）==========

@router.get("", response_model=dict)
async def list_strategies(
    include_disabled: bool = Query(False, description="是否包含已禁用的策略"),
    db: Session = Depends(get_db),
):
    """
    获取所有选股策略模板列表

    返回策略列表，按排序顺序和ID排列。
    默认只返回启用的策略，可通过参数包含禁用的策略。
    """
    service = StrategyTemplateService(db)
    try:
        strategies = service.get_all_strategies(include_disabled=include_disabled)

        return {
            "code": 200,
            "message": "success",
            "data": {
                "total": len(strategies),
                "strategies": [s.to_dict() for s in strategies],
            },
        }
    finally:
        service.close()


@router.post("", response_model=dict)
async def create_strategy(request: StrategyCreateRequest, db: Session = Depends(get_db)):
    """
    创建自定义选股策略

    基于用户提供的条件配置创建新的选股策略模板。
    系统会验证条件配置的有效性。
    """
    service = StrategyTemplateService(db)
    try:
        is_valid, error_msg = service.validate_conditions_config(request.conditions_config)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"条件配置无效: {error_msg}")

        strategy = service.create_strategy(request.model_dump())

        logger.info(f"创建策略成功: ID={strategy.id}, Name={strategy.name}")

        return {
            "code": 200,
            "message": "策略创建成功",
            "data": strategy.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建策略失败: {str(e)}")
    finally:
        service.close()


@router.post("/initialize", response_model=dict)
async def initialize_strategies(db: Session = Depends(get_db)):
    """
    初始化预置策略模板

    如果预置模板（默认、保守、激进）不存在，则自动创建。
    通常在应用首次启动时调用。

    注意：使用 /initialize 避免与 /{strategy_id} 冲突
    """
    service = StrategyTemplateService(db)
    try:
        count = service.initialize_default_strategies()

        return {
            "code": 200,
            "message": f"初始化完成，新增 {count} 个预置策略模板",
            "data": {
                "created_count": count,
                "templates": [
                    t["name"] for t in service.DEFAULT_STRATEGY_TEMPLATES
                ],
            },
        }
    except Exception as e:
        logger.error(f"初始化策略模板失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")
    finally:
        service.close()


# ========== 动态路由（必须在静态路由后）==========

@router.get("/{strategy_id}", response_model=dict)
async def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """获取策略详情"""
    service = StrategyTemplateService(db)
    try:
        strategy = service.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略不存在: ID={strategy_id}")

        return {
            "code": 200,
            "message": "success",
            "data": strategy.to_dict(),
        }
    finally:
        service.close()


@router.put("/{strategy_id}", response_model=dict)
async def update_strategy(
    strategy_id: int, request: StrategyUpdateRequest, db: Session = Depends(get_db)
):
    """
    更新选股策略

    支持部分更新。系统预置模板不允许修改名称。
    如果更新了 conditions_config，会重新验证其有效性。
    """
    service = StrategyTemplateService(db)
    try:
        update_data = request.model_dump(exclude_unset=True)

        if "conditions_config" in update_data and update_data["conditions_config"]:
            is_valid, error_msg = service.validate_conditions_config(
                update_data["conditions_config"]
            )
            if not is_valid:
                raise HTTPException(
                    status_code=400, detail=f"条件配置无效: {error_msg}"
                )

        strategy = service.update_strategy(strategy_id, update_data)

        logger.info(f"更新策略成功: ID={strategy_id}")

        return {
            "code": 200,
            "message": "策略更新成功",
            "data": strategy.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新策略失败: {str(e)}")
    finally:
        service.close()


@router.delete("/{strategy_id}", response_model=dict)
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """
    删除选股策略

    注意：系统预置模板不允许删除。
    """
    service = StrategyTemplateService(db)
    try:
        service.delete_strategy(strategy_id)

        logger.info(f"删除策略成功: ID={strategy_id}")

        return {
            "code": 200,
            "message": "策略删除成功",
            "data": {"deleted_id": strategy_id},
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除策略失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除策略失败: {str(e)}")
    finally:
        service.close()


@router.patch("/{strategy_id}/toggle", response_model=dict)
async def toggle_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """
    切换策略启用/禁用状态

    用于快速启用或禁用某个策略，无需修改完整配置。
    """
    service = StrategyTemplateService(db)
    try:
        strategy = service.toggle_strategy(strategy_id)

        status = "启用" if strategy.is_enabled else "禁用"
        logger.info(f"{status}策略成功: ID={strategy_id}, Name={strategy.name}")

        return {
            "code": 200,
            "message": f"策略已{status}",
            "data": strategy.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"切换策略状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
    finally:
        service.close()


@router.post("/{strategy_id}/preview", response_model=dict)
async def preview_strategy_query(strategy_id: int, db: Session = Depends(get_db)):
    """
    预览策略的查询语句

    根据策略配置生成通达信MCP查询语句，
    用于在前端展示给用户确认。
    """
    service = StrategyTemplateService(db)
    try:
        strategy = service.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略不存在: ID={strategy_id}")

        task_info = service.build_selection_task_from_template(strategy)

        return {
            "code": 200,
            "message": "success",
            "data": {
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "query": task_info["query"],
                "conditions_count": task_info["conditions_count"],
                "task_id": task_info["task"].task_id,
            },
        }
    except Exception as e:
        logger.error(f"预览策略查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")
    finally:
        service.close()
