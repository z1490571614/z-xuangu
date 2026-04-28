"""
配置相关数据模型
"""
from typing import Optional, Any
from pydantic import BaseModel, Field


class ConfigUpdate(BaseModel):
    """配置更新请求"""

    value: str = Field(description="配置值")
    value_type: Optional[str] = Field(default="string", description="值类型")
    description: Optional[str] = Field(default=None, description="配置描述")

    class Config:
        json_schema_extra = {
            "example": {
                "value": "2000",
                "value_type": "int",
                "description": "最大流通市值(亿)"
            }
        }


class ConfigResponse(BaseModel):
    """配置响应"""

    key: str = Field(description="配置键")
    value: str = Field(description="配置值")
    value_type: str = Field(description="值类型")
    description: Optional[str] = Field(default=None, description="配置描述")

    class Config:
        from_attributes = True
