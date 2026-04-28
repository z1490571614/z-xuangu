"""
初始化管理员用户脚本
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.auth.models import User
from backend.auth.jwt_handler import get_password_hash


def create_admin_user():
    """创建默认管理员用户"""
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.username == "admin").first()
        if existing_user:
            print("管理员用户已存在")
            return
        
        admin_user = User(
            username="admin",
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            is_superuser=True
        )
        
        db.add(admin_user)
        db.commit()
        print("✅ 管理员用户创建成功")
        print("   用户名: admin")
        print("   密码: admin123")
        print("   ⚠️  请在生产环境中修改默认密码！")
    except Exception as e:
        print(f"❌ 创建管理员用户失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
