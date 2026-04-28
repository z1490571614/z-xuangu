"""
任务管理 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.schemas import ApiResponse, TaskCreate, TaskUpdate, TaskResponse, TaskLogResponse
from backend.models import ScheduledTask, TaskLog, SelectionRecord
from backend.services.scheduler import scheduler

router = APIRouter()


@router.get("")
async def get_tasks(db: Session = Depends(get_db)):
    """
    获取任务列表（含最新选股执行状态）

    返回定时任务 + 最近选股记录的合并视图
    """
    try:
        tasks = db.query(ScheduledTask).order_by(ScheduledTask.id.desc()).all()

        recent_selections = (
            db.query(SelectionRecord)
            .order_by(SelectionRecord.id.desc())
            .limit(10)
            .all()
        )

        task_list = []
        for task in tasks:
            last_run = None
            if task.last_run_time:
                log = db.query(TaskLog).filter(
                    TaskLog.task_type == task.task_type,
                    TaskLog.trigger_time == task.last_run_time
                ).first()
                if log:
                    last_run = {
                        "status": log.status,
                        "start_time": str(log.start_time) if log.start_time else None,
                        "end_time": str(log.end_time) if log.end_time else None,
                    }

            task_list.append({
                'id': task.id,
                'name': task.name,
                'task_type': task.task_type,
                'cron_expression': task.cron_expression,
                'enabled': task.enabled,
                'last_run_time': task.last_run_time,
                'next_run_time': task.next_run_time,
                'description': task.description,
                'last_run_status': last_run['status'] if last_run else None,
            })

        return {
            "code": 200,
            "message": "success",
            "data": {
                "tasks": task_list,
                "recent_selections": [
                    {
                        "id": s.id,
                        "trade_date": s.trade_date,
                        "total_count": s.total_count,
                        "status": s.status,
                        "execute_time": str(s.execute_time) if s.execute_time else None,
                        "created_at": str(s.created_at),
                    }
                    for s in recent_selections
                ]
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("", response_model=ApiResponse[TaskResponse])
async def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db)
):
    """
    创建定时任务

    创建新的定时任务

    Args:
        task_data: 任务数据
        db: 数据库会话

    Returns:
        创建的任务
    """
    try:
        task = ScheduledTask(
            name=task_data.name,
            task_type=task_data.task_type,
            cron_expression=task_data.cron_expression,
            config=task_data.config,
            description=task_data.description,
            enabled=True
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        scheduler.add_job(
            task_id=task.id,
            task_type=task.task_type,
            cron_expression=task.cron_expression,
            config=task.config
        )

        return ApiResponse(
            code=200,
            message="任务创建成功",
            data={
                'id': task.id,
                'name': task.name,
                'task_type': task.task_type,
                'cron_expression': task.cron_expression,
                'enabled': task.enabled,
                'last_run_time': task.last_run_time,
                'next_run_time': task.next_run_time,
                'description': task.description
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: Session = Depends(get_db)
):
    """
    更新定时任务

    更新指定的定时任务

    Args:
        task_id: 任务ID
        task_data: 任务数据
        db: 数据库会话

    Returns:
        更新后的任务
    """
    try:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        if task_data.name is not None:
            task.name = task_data.name
        if task_data.cron_expression is not None:
            task.cron_expression = task_data.cron_expression
        if task_data.enabled is not None:
            task.enabled = task_data.enabled
        if task_data.config is not None:
            task.config = task_data.config
        if task_data.description is not None:
            task.description = task_data.description

        db.commit()
        db.refresh(task)

        if task.enabled:
            scheduler.add_job(
                task_id=task.id,
                task_type=task.task_type,
                cron_expression=task.cron_expression,
                config=task.config
            )
        else:
            scheduler.remove_job(task.id)

        return ApiResponse(
            code=200,
            message="任务更新成功",
            data={
                'id': task.id,
                'name': task.name,
                'task_type': task.task_type,
                'cron_expression': task.cron_expression,
                'enabled': task.enabled,
                'last_run_time': task.last_run_time,
                'next_run_time': task.next_run_time,
                'description': task.description
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/{task_id}", response_model=ApiResponse[dict])
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    删除定时任务

    删除指定的定时任务

    Args:
        task_id: 任务ID
        db: 数据库会话

    Returns:
        删除结果
    """
    try:
        task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        db.delete(task)
        db.commit()

        scheduler.remove_job(task_id)

        return ApiResponse(
            code=200,
            message="任务删除成功",
            data={'id': task_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/logs", response_model=ApiResponse[List[TaskLogResponse]])
async def get_task_logs(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """
    获取任务日志

    分页获取任务执行日志

    Args:
        page: 页码
        page_size: 每页数量
        db: 数据库会话

    Returns:
        任务日志列表
    """
    try:
        offset = (page - 1) * page_size

        logs = db.query(TaskLog)\
            .order_by(TaskLog.created_at.desc())\
            .offset(offset)\
            .limit(page_size)\
            .all()

        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'task_type': log.task_type,
                'trigger_time': log.trigger_time,
                'start_time': log.start_time,
                'end_time': log.end_time,
                'status': log.status,
                'error_message': log.error_message
            })

        return ApiResponse(
            code=200,
            message="success",
            data=result
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
