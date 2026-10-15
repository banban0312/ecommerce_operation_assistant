from app.models import Base

# 为 Alembic 提供统一导入路径，确保迁移工具能发现已注册的模型元数据。
__all__ = ["Base"]
