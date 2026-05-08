"""
pytest 全局配置和共享 fixture
"""
import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("LOG_LEVEL", "CRITICAL")
os.environ.setdefault("TUSHARE_TOKEN", "test_token")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_purposes_only")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_xuangu.db")
os.environ.setdefault("ALLOWED_ORIGINS", "http://testserver")
os.environ.setdefault("LOG_DIR", "logs")

from backend.database import engine, Base, SessionLocal
import backend.models  # noqa: F401 - register all ORM models before create_all
from backend.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """测试数据库初始化"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client():
    """FastAPI 测试客户端"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db():
    """每个测试函数的独立数据库会话"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def auth_headers(client):
    """注册+登录，返回认证请求头"""
    register_data = {"username": "testuser", "password": "testpass123", "email": "test@example.com"}
    client.post("/api/v1/auth/register", json=register_data)

    login_data = {"username": "testuser", "password": "testpass123"}
    resp = client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
