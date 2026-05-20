"""
配置管理 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.schemas import ApiResponse, ConfigUpdate, ConfigResponse
from backend.models import SystemConfig
from backend.services.notification import FeishuNotifier

router = APIRouter()


@router.get("", response_model=ApiResponse[List[ConfigResponse]])
async def get_all_config(db: Session = Depends(get_db)):
    """
    获取所有配置

    获取系统所有配置项

    Args:
        db: 数据库会话

    Returns:
        配置列表
    """
    try:
        configs = db.query(SystemConfig).all()

        result = []
        for config in configs:
            result.append({
                'key': config.key,
                'value': config.value,
                'value_type': config.value_type,
                'description': config.description
            })

        return ApiResponse(
            code=200,
            message="success",
            data=result
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{key}", response_model=ApiResponse[ConfigResponse])
async def get_config(
    key: str,
    db: Session = Depends(get_db)
):
    """
    获取单个配置

    根据键名获取配置值

    Args:
        key: 配置键名
        db: 数据库会话

    Returns:
        配置信息
    """
    try:
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()

        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")

        return ApiResponse(
            code=200,
            message="success",
            data={
                'key': config.key,
                'value': config.value,
                'value_type': config.value_type,
                'description': config.description
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.put("/{key}", response_model=ApiResponse[ConfigResponse])
async def update_config(
    key: str,
    config_data: ConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    更新配置

    更新指定配置项的值

    Args:
        key: 配置键名
        config_data: 配置数据
        db: 数据库会话

    Returns:
        更新后的配置
    """
    try:
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()

        if not config:
            config = SystemConfig(
                key=key,
                value=config_data.value,
                value_type=config_data.value_type or "string",
                description=config_data.description
            )
            db.add(config)
        else:
            config.value = config_data.value
            if config_data.value_type:
                config.value_type = config_data.value_type
            if config_data.description:
                config.description = config_data.description

        db.commit()
        db.refresh(config)

        return ApiResponse(
            code=200,
            message="配置更新成功",
            data={
                'key': config.key,
                'value': config.value,
                'value_type': config.value_type,
                'description': config.description
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.post("/test-notification", response_model=ApiResponse[dict])
async def test_notification(db: Session = Depends(get_db)):
    """
    发送飞书通知（最近一次选股结果）

    从数据库读取最新一次选股记录，将实际选股结果发送到飞书
    """
    try:
        from backend.models.selection_record import SelectionRecord
        from backend.models.selected_stock import SelectedStock

        latest_record = db.query(SelectionRecord).order_by(
            SelectionRecord.id.desc()
        ).first()

        if not latest_record:
            return ApiResponse(
                code=200,
                message="暂无选股记录",
                data={'success': False, 'reason': 'no_records'}
            )

        stocks_data = db.query(SelectedStock).filter(
            SelectedStock.record_id == latest_record.id
        ).all()

        stocks_list = []
        for s in stocks_data:
            stocks_list.append({
                'ts_code': s.ts_code,
                'name': s.name,
                'close': float(s.close_price or 0),
                'change_pct': float(s.change_pct or 0),
                'pre_change_pct': float(s.pre_change_pct) if s.pre_change_pct is not None else None,
                'open_change_pct': float(s.open_change_pct) if s.open_change_pct is not None else None,
                'lu_tag': s.lu_tag,
                'lu_status': s.lu_status,
                'default_t0_limit_prob': float(s.default_t0_limit_prob) if s.default_t0_limit_prob is not None else None,
                'circ_mv': 0
            })

        notifier = FeishuNotifier()

        success = notifier.send_selection_result({
            "trade_date": str(latest_record.trade_date),
            "passed_count": latest_record.total_count,
            "stocks": stocks_list,
            "execution_time": 0
        })

        if success:
            return ApiResponse(
                code=200,
                message=f"已发送 {latest_record.trade_date} 选股结果（{latest_record.total_count}只股票）",
                data={
                    'success': True,
                    'record_id': latest_record.id,
                    'trade_date': latest_record.trade_date,
                    'stock_count': latest_record.total_count
                }
            )
        else:
            return ApiResponse(
                code=500,
                message="飞书通知发送失败",
                data={'success': False}
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")


@router.post("/init-default", response_model=ApiResponse[dict])
async def init_default_config(db: Session = Depends(get_db)):
    """
    初始化默认配置

    初始化系统默认配置项

    Args:
        db: 数据库会话

    Returns:
        初始化结果
    """
    try:
        default_configs = [
            {
                'key': 'max_circ_mv',
                'value': '2000',
                'value_type': 'int',
                'description': '最大流通市值(亿)'
            },
            {
                'key': 'max_close_price',
                'value': '500',
                'value_type': 'int',
                'description': '最大收盘价(元)'
            },
            {
                'key': 'min_limit_count',
                'value': '3',
                'value_type': 'int',
                'description': '最小涨停次数'
            },
            {
                'key': 'min_success_rate',
                'value': '90',
                'value_type': 'float',
                'description': '最小封板成功率(%)'
            },
            {
                'key': 'notification_enabled',
                'value': 'true',
                'value_type': 'bool',
                'description': '是否启用通知'
            }
        ]

        for config_data in default_configs:
            existing = db.query(SystemConfig).filter(
                SystemConfig.key == config_data['key']
            ).first()

            if not existing:
                config = SystemConfig(**config_data)
                db.add(config)

        db.commit()

        return ApiResponse(
            code=200,
            message="默认配置初始化成功",
            data={'count': len(default_configs)}
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")
